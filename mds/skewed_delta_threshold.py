#!/usr/bin/env python3
"""Locate the onset of a small, rapidly growing ``delta_clock`` upper tail.

This executable is an experimental alternative to the slope/MAD detector in
``mds.clock_delta``.  The old detector remains unchanged as a baseline.

The estimator compares local regression slopes immediately before and after
candidate points on the upper empirical-quantile curve.  It seeks the final
small tail where ``log1p(delta_clock)`` starts growing much faster with rank,
not the edge of the dominant low-value histogram peak.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, isfinite
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_integer_dtype, is_unsigned_integer_dtype

DELTA_COLUMN = "delta_clock"
METHOD_NAME = "upper_quantile_local_slope_ensemble"
MAX_INT64 = 2**63 - 1

# 只分析排序分布的上部 10%，从而跳过 <20 微秒超高密度主峰的边缘。
DEFAULT_ANALYSIS_START_QUANTILE = 0.90

# 最顶部 0.05% 不参与局部回归，避免单个 980000 一类的值支配拟合；
# 它们仍会进入最终 tail_count 等统计。
DEFAULT_UPPER_QUANTILE = 0.9995
DEFAULT_QUANTILE_POINTS = 4096

# 用不同宽度的 rank 窗口重复检测。真正的上尾起点不应随着平滑尺度变化
# 而大幅移动；三个窗口在 498 万条数据上分别约含 4980/9960/19920 条。
DEFAULT_WINDOW_FRACTIONS = (0.001, 0.002, 0.004)

# 用户确认组间 gap 只占很小一部分。默认在“尾部占 0.5%–5%”的范围内
# 搜索。这是显式业务先验，可通过 CLI 调整，不是普适统计常数。
DEFAULT_MIN_TAIL_FRACTION = 0.005
DEFAULT_MAX_TAIL_FRACTION = 0.05

# 候选点右侧局部斜率至少为左侧的 3 倍；左右分别拟合两条线，相对整个
# 局部窗口只拟合一条线，残差平方和至少降低 25%。
DEFAULT_MIN_SLOPE_RATIO = 3.0
DEFAULT_MIN_FIT_IMPROVEMENT = 0.25

# 不同窗口宽度得到的折点 rank 相差不得超过 0.5 个百分点，候选微秒值
# 最大值不得超过最小值的 2 倍。
DEFAULT_MAX_BREAKPOINT_QUANTILE_SPREAD = 0.005
DEFAULT_MAX_THRESHOLD_SPREAD = 2.0

MIN_WINDOW_CONFIGURATIONS = 3
MIN_POSITIVE_DELTAS = 1_000
MIN_TAIL_OBSERVATIONS = 50
MIN_QUANTILE_POINTS = 512
MIN_LOCAL_GRID_POINTS = 12
NUMERICAL_EPSILON = 1e-12


@dataclass(frozen=True)
class LocalSlopeCandidate:
    """One upper-tail breakpoint found with one local window width."""

    window_fraction: float
    breakpoint_quantile: float
    threshold: int
    rank_index: int
    left_slope: float
    right_slope: float
    slope_ratio: float
    fit_improvement: float
    left_sse: float
    right_sse: float
    single_line_sse: float


@dataclass(frozen=True)
class SkewedThresholdResult:
    """Final upper-tail threshold and diagnostics for judging its stability."""

    threshold: int
    total_count: int
    positive_count: int
    ignored_nonpositive_count: int
    body_count: int
    tail_count: int
    tail_fraction: float
    analysis_start_quantile: float
    upper_quantile: float
    upper_excluded_count: int
    quantile_points: int
    min_tail_fraction: float
    max_tail_fraction: float
    threshold_spread_ratio: float
    breakpoint_quantile_spread: float
    candidates: tuple[LocalSlopeCandidate, ...]

    @property
    def candidate_thresholds(self) -> tuple[int, ...]:
        """Return per-window thresholds in configured order."""

        return tuple(candidate.threshold for candidate in self.candidates)

    @property
    def candidate_breakpoint_quantiles(self) -> tuple[float, ...]:
        """Return per-window breakpoint quantiles."""

        return tuple(candidate.breakpoint_quantile for candidate in self.candidates)


def _normalize_delta_clock(data: pd.DataFrame) -> np.ndarray:
    """Validate ``delta_clock`` and return a signed 64-bit NumPy array."""

    if DELTA_COLUMN not in data:
        raise ValueError(f"missing required column: {DELTA_COLUMN}")
    if data[DELTA_COLUMN].isna().any():
        raise ValueError("delta_clock contains missing values")

    try:
        delta_clock = pd.to_numeric(data[DELTA_COLUMN], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError("delta_clock must contain integer values") from error

    if not is_integer_dtype(delta_clock.dtype):
        raise ValueError("delta_clock must contain integer values")
    if is_unsigned_integer_dtype(delta_clock.dtype) and delta_clock.max() > MAX_INT64:
        raise ValueError("delta_clock contains a value outside the signed 64-bit range")

    return delta_clock.astype("int64").to_numpy(copy=False)


def _validate_parameters(
    *,
    analysis_start_quantile: float,
    upper_quantile: float,
    quantile_points: int,
    window_fractions: Sequence[float],
    min_tail_fraction: float,
    max_tail_fraction: float,
    min_slope_ratio: float,
    min_fit_improvement: float,
    max_breakpoint_quantile_spread: float,
    max_threshold_spread: float,
) -> tuple[float, ...]:
    """Validate settings and normalize local-window fractions."""

    if (
        not isfinite(analysis_start_quantile)
        or not isfinite(upper_quantile)
        or not 0 < analysis_start_quantile < upper_quantile < 1
    ):
        raise ValueError(
            "quantile bounds must satisfy 0 < analysis_start_quantile "
            "< upper_quantile < 1"
        )
    if isinstance(quantile_points, bool) or not isinstance(
        quantile_points, (int, np.integer)
    ):
        raise TypeError("quantile_points must be an integer")
    if quantile_points < MIN_QUANTILE_POINTS:
        raise ValueError(f"quantile_points must be at least {MIN_QUANTILE_POINTS}")
    if (
        not isfinite(min_tail_fraction)
        or not isfinite(max_tail_fraction)
        or not 0 < min_tail_fraction < max_tail_fraction < 0.5
    ):
        raise ValueError(
            "tail fractions must satisfy 0 < min_tail_fraction "
            "< max_tail_fraction < 0.5"
        )
    if analysis_start_quantile >= 1 - max_tail_fraction:
        raise ValueError(
            "analysis_start_quantile must be below the earliest tail breakpoint"
        )
    if not isfinite(min_slope_ratio) or min_slope_ratio <= 1:
        raise ValueError("min_slope_ratio must be finite and greater than 1")
    if not isfinite(min_fit_improvement) or not 0 < min_fit_improvement < 1:
        raise ValueError("min_fit_improvement must be finite and between 0 and 1")
    if (
        not isfinite(max_breakpoint_quantile_spread)
        or max_breakpoint_quantile_spread <= 0
    ):
        raise ValueError("max_breakpoint_quantile_spread must be finite and positive")
    if not isfinite(max_threshold_spread) or max_threshold_spread < 1:
        raise ValueError("max_threshold_spread must be finite and at least 1")

    normalized_windows: list[float] = []
    for window_fraction in window_fractions:
        if not isinstance(window_fraction, (int, float, np.integer, np.floating)):
            raise TypeError("window_fractions must contain numbers")
        normalized_window = float(window_fraction)
        if not isfinite(normalized_window) or normalized_window <= 0:
            raise ValueError("each window fraction must be finite and positive")
        if normalized_window not in normalized_windows:
            normalized_windows.append(normalized_window)

    if len(normalized_windows) < MIN_WINDOW_CONFIGURATIONS:
        raise ValueError(
            "window_fractions must contain at least "
            f"{MIN_WINDOW_CONFIGURATIONS} distinct values"
        )

    largest_window = max(normalized_windows)
    earliest_breakpoint = 1.0 - max_tail_fraction
    latest_breakpoint = 1.0 - min_tail_fraction
    if earliest_breakpoint - largest_window <= analysis_start_quantile:
        raise ValueError(
            "analysis_start_quantile does not leave a full left local window"
        )
    if latest_breakpoint + largest_window >= upper_quantile:
        raise ValueError("upper_quantile does not leave a full right local window")

    quantile_step = (upper_quantile - analysis_start_quantile) / (quantile_points - 1)
    if min(normalized_windows) / quantile_step < MIN_LOCAL_GRID_POINTS:
        raise ValueError("quantile_points is too small for the narrowest local window")
    return tuple(normalized_windows)


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Return ordinary-least-squares slope and residual sum of squares."""

    centered_x = x - float(x.mean())
    centered_y = y - float(y.mean())
    denominator = float(centered_x @ centered_x)
    if denominator <= NUMERICAL_EPSILON:
        return 0.0, float(centered_y @ centered_y)

    slope = float((centered_x @ centered_y) / denominator)
    if slope < 0:
        return 0.0, float(centered_y @ centered_y)
    intercept = float(y.mean()) - slope * float(x.mean())
    residuals = y - (intercept + slope * x)
    return slope, float(residuals @ residuals)


def _fit_local_slope_candidate(
    sorted_positive_values: np.ndarray,
    *,
    quantiles: np.ndarray,
    rank_indices: np.ndarray,
    log_quantile_values: np.ndarray,
    window_fraction: float,
    min_tail_fraction: float,
    max_tail_fraction: float,
    min_slope_ratio: float,
    min_fit_improvement: float,
) -> tuple[LocalSlopeCandidate | None, str | None]:
    """Find the strongest local slope increase for one window width.

    For every permitted candidate rank ``q``:

    1. fit a line on ``[q-window, q)``;
    2. fit another line on ``[q, q+window]``;
    3. compare their slopes;
    4. compare the two-line residual with a single line over the whole window.

    The candidate with the largest right/left slope ratio is selected first;
    only then are the minimum ratio and fit-improvement rules applied.  This
    prevents searching until some weaker, convenient point happens to pass.
    """

    earliest_breakpoint = 1.0 - max_tail_fraction
    latest_breakpoint = 1.0 - min_tail_fraction
    eligible = np.flatnonzero(
        (quantiles >= earliest_breakpoint)
        & (quantiles <= latest_breakpoint)
        & (quantiles - window_fraction >= quantiles[0])
        & (quantiles + window_fraction <= quantiles[-1])
    )
    if eligible.size < 3:
        return None, "tail and window bounds leave too few candidate ranks"

    best_score: tuple[float, float, float, float] | None = None
    best_candidate: LocalSlopeCandidate | None = None

    for breakpoint_index in eligible:
        breakpoint_quantile = float(quantiles[breakpoint_index])
        left_start = int(
            np.searchsorted(
                quantiles,
                breakpoint_quantile - window_fraction,
                side="left",
            )
        )
        right_stop = int(
            np.searchsorted(
                quantiles,
                breakpoint_quantile + window_fraction,
                side="right",
            )
        )
        if (
            breakpoint_index - left_start < MIN_LOCAL_GRID_POINTS
            or right_stop - breakpoint_index < MIN_LOCAL_GRID_POINTS
        ):
            continue

        # 左右不重复使用折点：左侧是 [left_start, breakpoint)，右侧是
        # [breakpoint, right_stop)。这样 two-line SSE 与整个窗口 single-line
        # SSE 使用完全相同的观测点，可以直接比较。
        left_x = quantiles[left_start:breakpoint_index]
        left_y = log_quantile_values[left_start:breakpoint_index]
        right_x = quantiles[breakpoint_index:right_stop]
        right_y = log_quantile_values[breakpoint_index:right_stop]
        full_x = quantiles[left_start:right_stop]
        full_y = log_quantile_values[left_start:right_stop]

        left_slope, left_sse = _linear_fit(left_x, left_y)
        right_slope, right_sse = _linear_fit(right_x, right_y)
        _, single_line_sse = _linear_fit(full_x, full_y)

        if left_slope <= NUMERICAL_EPSILON:
            slope_ratio = float("inf") if right_slope > 0 else 1.0
        else:
            slope_ratio = right_slope / left_slope
        if single_line_sse <= NUMERICAL_EPSILON:
            fit_improvement = 0.0
        else:
            fit_improvement = 1.0 - (left_sse + right_sse) / single_line_sse

        # ratio 是主要目标。若平坦区令多个 ratio 都为 inf，则依次偏好更大
        # 的右斜率、更好的拟合改善和更早的 rank，保证确定且保守的结果。
        score = (
            slope_ratio,
            right_slope,
            fit_improvement,
            -breakpoint_quantile,
        )
        if best_score is None or score > best_score:
            rank_index = int(rank_indices[breakpoint_index])
            best_score = score
            best_candidate = LocalSlopeCandidate(
                window_fraction=window_fraction,
                breakpoint_quantile=breakpoint_quantile,
                threshold=int(sorted_positive_values[rank_index]),
                rank_index=rank_index,
                left_slope=left_slope,
                right_slope=right_slope,
                slope_ratio=slope_ratio,
                fit_improvement=fit_improvement,
                left_sse=left_sse,
                right_sse=right_sse,
                single_line_sse=single_line_sse,
            )

    if best_candidate is None:
        return None, "no candidate has enough local curve points"
    if best_candidate.breakpoint_quantile in (
        float(quantiles[eligible[0]]),
        float(quantiles[eligible[-1]]),
    ):
        return None, "strongest slope change lies on a tail-fraction boundary"
    if best_candidate.slope_ratio < min_slope_ratio:
        return None, (
            f"best slope ratio {best_candidate.slope_ratio:.3f} is below "
            f"{min_slope_ratio:.3f}"
        )
    if best_candidate.fit_improvement < min_fit_improvement:
        return None, (
            f"best two-line fit improvement {best_candidate.fit_improvement:.3f} "
            f"is below {min_fit_improvement:.3f}"
        )
    return best_candidate, None


def estimate_skewed_threshold(
    data: pd.DataFrame,
    *,
    analysis_start_quantile: float = DEFAULT_ANALYSIS_START_QUANTILE,
    upper_quantile: float = DEFAULT_UPPER_QUANTILE,
    quantile_points: int = DEFAULT_QUANTILE_POINTS,
    window_fractions: Sequence[float] = DEFAULT_WINDOW_FRACTIONS,
    min_tail_fraction: float = DEFAULT_MIN_TAIL_FRACTION,
    max_tail_fraction: float = DEFAULT_MAX_TAIL_FRACTION,
    min_slope_ratio: float = DEFAULT_MIN_SLOPE_RATIO,
    min_fit_improvement: float = DEFAULT_MIN_FIT_IMPROVEMENT,
    max_breakpoint_quantile_spread: float = (DEFAULT_MAX_BREAKPOINT_QUANTILE_SPREAD),
    max_threshold_spread: float = DEFAULT_MAX_THRESHOLD_SPREAD,
) -> SkewedThresholdResult:
    """Find a stable local-slope changepoint at a small upper-tail onset.

    The method encodes three user-confirmed assumptions: most gaps are
    within-group, between-group gaps form a small upper tail, and the sorted
    curve grows much faster on entering that tail.  These assumptions cannot
    be proven from one unlabeled distribution, so unstable candidates raise
    ``ValueError`` instead of producing an arbitrary threshold.
    """

    normalized_windows = _validate_parameters(
        analysis_start_quantile=analysis_start_quantile,
        upper_quantile=upper_quantile,
        quantile_points=quantile_points,
        window_fractions=window_fractions,
        min_tail_fraction=min_tail_fraction,
        max_tail_fraction=max_tail_fraction,
        min_slope_ratio=min_slope_ratio,
        min_fit_improvement=min_fit_improvement,
        max_breakpoint_quantile_spread=max_breakpoint_quantile_spread,
        max_threshold_spread=max_threshold_spread,
    )
    delta_clock = _normalize_delta_clock(data)
    sorted_positive_values = np.sort(delta_clock[delta_clock > 0])
    positive_count = int(sorted_positive_values.size)
    if positive_count < MIN_POSITIVE_DELTAS:
        raise ValueError(
            f"at least {MIN_POSITIVE_DELTAS} positive delta_clock observations "
            "are required"
        )
    if ceil(positive_count * min_tail_fraction) < MIN_TAIL_OBSERVATIONS:
        raise ValueError(
            "min_tail_fraction leaves fewer than "
            f"{MIN_TAIL_OBSERVATIONS} observations in the smallest allowed tail"
        )
    if sorted_positive_values[0] == sorted_positive_values[-1]:
        raise ValueError("positive delta_clock values have no variation")

    # 等距 empirical-rank 采样保留频数：大量重复小值会占据大量 rank，
    # 而不是在 unique 或“只保留正 slope”后被压成一个值。
    quantiles = np.linspace(
        analysis_start_quantile,
        upper_quantile,
        quantile_points,
        dtype="float64",
    )
    rank_indices = np.floor(quantiles * (positive_count - 1)).astype("int64")
    if np.unique(rank_indices).size < 2 * MIN_LOCAL_GRID_POINTS + 1:
        raise ValueError("too few distinct empirical ranks in the quantile curve")
    log_quantile_values = np.log1p(
        sorted_positive_values[rank_indices].astype("float64", copy=False)
    )

    candidates: list[LocalSlopeCandidate] = []
    failures: list[str] = []
    for window_fraction in normalized_windows:
        candidate, failure = _fit_local_slope_candidate(
            sorted_positive_values,
            quantiles=quantiles,
            rank_indices=rank_indices,
            log_quantile_values=log_quantile_values,
            window_fraction=window_fraction,
            min_tail_fraction=min_tail_fraction,
            max_tail_fraction=max_tail_fraction,
            min_slope_ratio=min_slope_ratio,
            min_fit_improvement=min_fit_improvement,
        )
        if candidate is None:
            failures.append(f"window={window_fraction:.4f}: {failure}")
        else:
            candidates.append(candidate)

    # 三种平滑尺度必须全部找到有效折点；只保留碰巧成功的窗口会产生选择
    # 偏差，也无法说明检测到的是同一个上尾起点。
    if failures:
        raise ValueError(
            "no stable upper-tail changepoint across all local windows: "
            + "; ".join(failures)
        )

    candidate_thresholds = np.asarray(
        [candidate.threshold for candidate in candidates], dtype="float64"
    )
    threshold_spread_ratio = float(
        candidate_thresholds.max() / candidate_thresholds.min()
    )
    if threshold_spread_ratio > max_threshold_spread:
        formatted = ", ".join(str(int(value)) for value in candidate_thresholds)
        raise ValueError(
            "unstable upper-tail thresholds across local windows: "
            f"candidates=[{formatted}], "
            f"spread_ratio={threshold_spread_ratio:.3f} exceeds "
            f"{max_threshold_spread:.3f}"
        )

    breakpoint_quantiles = np.asarray(
        [candidate.breakpoint_quantile for candidate in candidates],
        dtype="float64",
    )
    breakpoint_quantile_spread = float(
        breakpoint_quantiles.max() - breakpoint_quantiles.min()
    )
    if breakpoint_quantile_spread > max_breakpoint_quantile_spread:
        formatted = ", ".join(f"{value:.6f}" for value in breakpoint_quantiles)
        raise ValueError(
            "unstable upper-tail breakpoint ranks across local windows: "
            f"quantiles=[{formatted}], "
            f"spread={breakpoint_quantile_spread:.6f} exceeds "
            f"{max_breakpoint_quantile_spread:.6f}"
        )

    threshold = min(
        MAX_INT64,
        max(1, ceil(float(np.median(candidate_thresholds)))),
    )
    body_count = int(np.searchsorted(sorted_positive_values, threshold, side="left"))
    tail_count = positive_count - body_count
    tail_fraction = tail_count / positive_count
    if not min_tail_fraction <= tail_fraction <= max_tail_fraction:
        raise ValueError(
            "selected integer threshold produces a tail fraction outside the "
            "configured bounds, possibly because many observations tie at the "
            f"threshold: tail_fraction={tail_fraction:.6f}"
        )
    upper_last_rank = int(np.floor(upper_quantile * (positive_count - 1)))

    return SkewedThresholdResult(
        threshold=threshold,
        total_count=int(delta_clock.size),
        positive_count=positive_count,
        ignored_nonpositive_count=int(delta_clock.size - positive_count),
        body_count=body_count,
        tail_count=tail_count,
        tail_fraction=tail_fraction,
        analysis_start_quantile=analysis_start_quantile,
        upper_quantile=upper_quantile,
        upper_excluded_count=positive_count - upper_last_rank - 1,
        quantile_points=quantile_points,
        min_tail_fraction=min_tail_fraction,
        max_tail_fraction=max_tail_fraction,
        threshold_spread_ratio=threshold_spread_ratio,
        breakpoint_quantile_spread=breakpoint_quantile_spread,
        candidates=tuple(candidates),
    )


def _summary_frame(result: SkewedThresholdResult) -> pd.DataFrame:
    """Convert one result into the single-row CSV form used by the CLI."""

    return pd.DataFrame.from_records(
        [
            {
                "method": METHOD_NAME,
                "threshold": result.threshold,
                "total_count": result.total_count,
                "positive_count": result.positive_count,
                "ignored_nonpositive_count": result.ignored_nonpositive_count,
                "body_count": result.body_count,
                "tail_count": result.tail_count,
                "tail_fraction": result.tail_fraction,
                "analysis_start_quantile": result.analysis_start_quantile,
                "upper_quantile": result.upper_quantile,
                "upper_excluded_count": result.upper_excluded_count,
                "quantile_points": result.quantile_points,
                "min_tail_fraction": result.min_tail_fraction,
                "max_tail_fraction": result.max_tail_fraction,
                "candidate_thresholds": ";".join(
                    str(value) for value in result.candidate_thresholds
                ),
                "candidate_breakpoint_quantiles": ";".join(
                    f"{value:.9f}" for value in result.candidate_breakpoint_quantiles
                ),
                "threshold_spread_ratio": result.threshold_spread_ratio,
                "breakpoint_quantile_spread": result.breakpoint_quantile_spread,
            }
        ]
    )


def _diagnostics_frame(result: SkewedThresholdResult) -> pd.DataFrame:
    """Convert per-window local fits into a diagnostic CSV."""

    return pd.DataFrame.from_records(
        [
            {
                "window_fraction": candidate.window_fraction,
                "breakpoint_quantile": candidate.breakpoint_quantile,
                "candidate_threshold": candidate.threshold,
                "rank_index": candidate.rank_index,
                "left_slope": candidate.left_slope,
                "right_slope": candidate.right_slope,
                "slope_ratio": candidate.slope_ratio,
                "fit_improvement": candidate.fit_improvement,
                "left_sse": candidate.left_sse,
                "right_sse": candidate.right_sse,
                "single_line_sse": candidate.single_line_sse,
            }
            for candidate in result.candidates
        ]
    )


def process_csv(
    input_csv: Path | str,
    output_csv: Path | str,
    *,
    diagnostics_csv: Path | str | None = None,
    analysis_start_quantile: float = DEFAULT_ANALYSIS_START_QUANTILE,
    upper_quantile: float = DEFAULT_UPPER_QUANTILE,
    quantile_points: int = DEFAULT_QUANTILE_POINTS,
    window_fractions: Sequence[float] = DEFAULT_WINDOW_FRACTIONS,
    min_tail_fraction: float = DEFAULT_MIN_TAIL_FRACTION,
    max_tail_fraction: float = DEFAULT_MAX_TAIL_FRACTION,
    min_slope_ratio: float = DEFAULT_MIN_SLOPE_RATIO,
    min_fit_improvement: float = DEFAULT_MIN_FIT_IMPROVEMENT,
    max_breakpoint_quantile_spread: float = (DEFAULT_MAX_BREAKPOINT_QUANTILE_SPREAD),
    max_threshold_spread: float = DEFAULT_MAX_THRESHOLD_SPREAD,
) -> SkewedThresholdResult:
    """Read deltas, estimate the upper-tail onset, and write diagnostics."""

    input_path = Path(input_csv)
    output_path = Path(output_csv)
    diagnostics_path = Path(diagnostics_csv) if diagnostics_csv is not None else None
    if input_path.resolve() == output_path.resolve():
        raise ValueError("input_csv and output_csv must be different files")
    if diagnostics_path is not None:
        if diagnostics_path.resolve() == input_path.resolve():
            raise ValueError("diagnostics_csv and input_csv must be different files")
        if diagnostics_path.resolve() == output_path.resolve():
            raise ValueError("diagnostics_csv and output_csv must be different files")

    data = pd.read_csv(
        input_path,
        usecols=[DELTA_COLUMN],
        # 直接使用 pandas nullable integer，避免 498 万条数字先以 Python
        # 字符串常驻内存；缺失和非整数仍由统一校验或 CSV parser 明确拒绝。
        dtype={DELTA_COLUMN: "Int64"},
    )
    result = estimate_skewed_threshold(
        data,
        analysis_start_quantile=analysis_start_quantile,
        upper_quantile=upper_quantile,
        quantile_points=quantile_points,
        window_fractions=window_fractions,
        min_tail_fraction=min_tail_fraction,
        max_tail_fraction=max_tail_fraction,
        min_slope_ratio=min_slope_ratio,
        min_fit_improvement=min_fit_improvement,
        max_breakpoint_quantile_spread=max_breakpoint_quantile_spread,
        max_threshold_spread=max_threshold_spread,
    )
    _summary_frame(result).to_csv(output_path, index=False)
    if diagnostics_path is not None:
        _diagnostics_frame(result).to_csv(diagnostics_path, index=False)
    return result


def _parse_fractions(value: str) -> tuple[float, ...]:
    """Parse a comma-separated CLI fraction list."""

    try:
        values = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "fractions must be comma-separated numbers, for example 0.001,0.002,0.004"
        ) from error
    if not values:
        raise argparse.ArgumentTypeError("fractions must not be empty")
    return values


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the standalone command-line interface."""

    parser = argparse.ArgumentParser(
        description=(
            "Find the onset of a small, rapidly growing delta_clock upper tail "
            "by comparing local regression slopes on empirical quantiles. "
            "Input must contain a delta_clock column."
        )
    )
    parser.add_argument("input_csv", type=Path, help="CSV containing delta_clock")
    parser.add_argument("output_csv", type=Path, help="one-row threshold summary CSV")
    parser.add_argument(
        "--diagnostics-csv",
        type=Path,
        help="optional per-window diagnostics CSV",
    )
    parser.add_argument(
        "--analysis-start-quantile",
        type=float,
        default=DEFAULT_ANALYSIS_START_QUANTILE,
        help="lowest quantile sampled for local fits (default: %(default)s)",
    )
    parser.add_argument(
        "--upper-quantile",
        type=float,
        default=DEFAULT_UPPER_QUANTILE,
        help="highest quantile sampled for local fits (default: %(default)s)",
    )
    parser.add_argument(
        "--quantile-points",
        type=int,
        default=DEFAULT_QUANTILE_POINTS,
        help="points sampled on the quantile curve (default: %(default)s)",
    )
    parser.add_argument(
        "--window-fractions",
        type=_parse_fractions,
        default=DEFAULT_WINDOW_FRACTIONS,
        help="comma-separated local half-window sizes (default: 0.001,0.002,0.004)",
    )
    parser.add_argument(
        "--min-tail-fraction",
        type=float,
        default=DEFAULT_MIN_TAIL_FRACTION,
        help="smallest permitted tail fraction (default: %(default)s)",
    )
    parser.add_argument(
        "--max-tail-fraction",
        type=float,
        default=DEFAULT_MAX_TAIL_FRACTION,
        help="largest permitted tail fraction (default: %(default)s)",
    )
    parser.add_argument(
        "--min-slope-ratio",
        type=float,
        default=DEFAULT_MIN_SLOPE_RATIO,
        help="minimum right/left local slope ratio (default: %(default)s)",
    )
    parser.add_argument(
        "--min-fit-improvement",
        type=float,
        default=DEFAULT_MIN_FIT_IMPROVEMENT,
        help="minimum two-line SSE reduction (default: %(default)s)",
    )
    parser.add_argument(
        "--max-breakpoint-quantile-spread",
        type=float,
        default=DEFAULT_MAX_BREAKPOINT_QUANTILE_SPREAD,
        help="maximum breakpoint-rank spread (default: %(default)s)",
    )
    parser.add_argument(
        "--max-threshold-spread",
        type=float,
        default=DEFAULT_MAX_THRESHOLD_SPREAD,
        help="maximum max/min candidate threshold ratio (default: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the estimator as a standalone command."""

    parser = build_argument_parser()
    arguments = parser.parse_args(argv)
    try:
        result = process_csv(
            arguments.input_csv,
            arguments.output_csv,
            diagnostics_csv=arguments.diagnostics_csv,
            analysis_start_quantile=arguments.analysis_start_quantile,
            upper_quantile=arguments.upper_quantile,
            quantile_points=arguments.quantile_points,
            window_fractions=arguments.window_fractions,
            min_tail_fraction=arguments.min_tail_fraction,
            max_tail_fraction=arguments.max_tail_fraction,
            min_slope_ratio=arguments.min_slope_ratio,
            min_fit_improvement=arguments.min_fit_improvement,
            max_breakpoint_quantile_spread=(arguments.max_breakpoint_quantile_spread),
            max_threshold_spread=arguments.max_threshold_spread,
        )
    except (OSError, TypeError, ValueError) as error:
        parser.exit(status=1, message=f"error: {error}\n")

    thresholds = ",".join(str(value) for value in result.candidate_thresholds)
    breakpoint_quantiles = ",".join(
        f"{value:.6f}" for value in result.candidate_breakpoint_quantiles
    )
    slope_ratios = ",".join(
        "inf" if not isfinite(candidate.slope_ratio) else f"{candidate.slope_ratio:.2f}"
        for candidate in result.candidates
    )
    print(
        "Detected upper-tail delta_clock threshold: "
        f"threshold={result.threshold} us, "
        f"tail={result.tail_count}/{result.positive_count} "
        f"({result.tail_fraction:.2%}), "
        f"candidates=[{thresholds}], "
        f"breakpoint_quantiles=[{breakpoint_quantiles}], "
        f"slope_ratios=[{slope_ratios}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
