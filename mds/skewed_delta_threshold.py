#!/usr/bin/env python3
"""Estimate a ``delta_clock`` threshold from an extremely skewed distribution.

This is an experimental, frequency-aware alternative to the slope/MAD detector
in :mod:`mds.clock_delta`.  It deliberately lives in a separate executable
module so the original detector remains available as a baseline.
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
METHOD_NAME = "log_histogram_triangle_ensemble"
MAX_INT64 = 2**63 - 1
DEFAULT_TAIL_QUANTILE = 0.995
DEFAULT_HISTOGRAM_BINS = (32, 48, 64, 96)
DEFAULT_MIN_TRIANGLE_SCORE = 0.05
DEFAULT_MAX_THRESHOLD_SPREAD = 4.0
MIN_HISTOGRAM_BINS = 8
MIN_BIN_CONFIGURATIONS = 3
MIN_POSITIVE_DELTAS = 100


@dataclass(frozen=True)
class TriangleCandidate:
    """One threshold candidate obtained at one histogram resolution."""

    histogram_bins: int
    threshold: int
    raw_threshold: float
    triangle_score: float
    peak_bin: int
    knee_bin: int
    tail_bin: int
    peak_value: float
    peak_count: int
    knee_count: int
    tail_count: int


@dataclass(frozen=True)
class SkewedThresholdResult:
    """Final threshold and diagnostics needed to judge whether it is stable."""

    threshold: int
    total_count: int
    positive_count: int
    ignored_nonpositive_count: int
    tail_quantile: float
    tail_clip_value: float
    tail_clipped_count: int
    histogram_count: int
    below_threshold_count: int
    below_threshold_fraction: float
    threshold_spread_ratio: float
    candidates: tuple[TriangleCandidate, ...]

    @property
    def candidate_thresholds(self) -> tuple[int, ...]:
        """Return the per-resolution thresholds in configured order."""

        return tuple(candidate.threshold for candidate in self.candidates)


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

    # clock 的单位是整数微秒。接受 12.5 之类的小数会让最后的整数阈值
    # 语义不清楚，因此即使它能被 pandas 转成 float，也在这里明确拒绝。
    if not is_integer_dtype(delta_clock.dtype):
        raise ValueError("delta_clock must contain integer values")
    if is_unsigned_integer_dtype(delta_clock.dtype) and delta_clock.max() > MAX_INT64:
        raise ValueError("delta_clock contains a value outside the signed 64-bit range")

    return delta_clock.astype("int64").to_numpy(copy=False)


def _validate_parameters(
    *,
    tail_quantile: float,
    histogram_bins: Sequence[int],
    min_triangle_score: float,
    max_threshold_spread: float,
) -> tuple[int, ...]:
    """Validate estimator settings and normalize histogram resolutions."""

    if not isfinite(tail_quantile) or not 0.5 < tail_quantile < 1:
        raise ValueError("tail_quantile must be finite and between 0.5 and 1")
    if not isfinite(min_triangle_score) or min_triangle_score <= 0:
        raise ValueError("min_triangle_score must be finite and positive")
    if not isfinite(max_threshold_spread) or max_threshold_spread < 1:
        raise ValueError("max_threshold_spread must be finite and at least 1")

    normalized_bins: list[int] = []
    for bin_count in histogram_bins:
        if isinstance(bin_count, bool) or not isinstance(bin_count, (int, np.integer)):
            raise TypeError("histogram_bins must contain integers")
        normalized_bin_count = int(bin_count)
        if normalized_bin_count < MIN_HISTOGRAM_BINS:
            raise ValueError(
                f"each histogram bin count must be at least {MIN_HISTOGRAM_BINS}"
            )
        if normalized_bin_count not in normalized_bins:
            normalized_bins.append(normalized_bin_count)

    if len(normalized_bins) < MIN_BIN_CONFIGURATIONS:
        raise ValueError(
            "histogram_bins must contain at least "
            f"{MIN_BIN_CONFIGURATIONS} distinct resolutions"
        )
    return tuple(normalized_bins)


def _triangle_candidate(
    log_values: np.ndarray,
    *,
    lower_log_value: float,
    upper_log_value: float,
    histogram_bins: int,
    min_triangle_score: float,
) -> TriangleCandidate | None:
    """Apply a right-tail triangle rule at one histogram resolution.

    The histogram peak represents the dense small-gap region.  The last
    occupied bin represents the sparse right tail.  We connect those two
    points with a straight line and find the intermediate histogram bin that
    lies furthest *below* that line.  That bin is the triangle-method knee.

    Both axes are normalized to 0..1 before measuring distance.  Without this
    normalization, changing the number of bins would change the x-axis scale
    and make scores from different resolutions incomparable.
    """

    counts, bin_edges = np.histogram(
        log_values,
        bins=histogram_bins,
        range=(lower_log_value, upper_log_value),
    )
    occupied_bins = np.flatnonzero(counts)
    if occupied_bins.size == 0:
        return None

    # np.argmax chooses the first peak in a tie.  For this right-tail problem,
    # the earlier peak is the conservative choice: it does not silently throw
    # away a dense small-delta mode that happens to tie with a later bin.
    peak_bin = int(np.argmax(counts))
    tail_bin = int(occupied_bins[-1])

    # The two endpoints themselves cannot be a knee.  Requiring at least two
    # bins between them also prevents a very coarse/degenerate histogram from
    # manufacturing a threshold.
    if tail_bin - peak_bin < 3:
        return None

    interior_bins = np.arange(peak_bin + 1, tail_bin, dtype="int64")
    normalized_x = (interior_bins - peak_bin) / (tail_bin - peak_bin)

    peak_count = int(counts[peak_bin])
    tail_count = int(counts[tail_bin])
    normalized_y = counts[interior_bins] / peak_count
    normalized_tail_y = tail_count / peak_count

    # In normalized coordinates the endpoint line is
    # y = 1 + (tail_y - 1) * x.  A rapidly thinning right-skewed histogram lies
    # below this line.  The numerator below is the vertical gap; dividing by
    # sqrt(1 + slope^2) turns it into perpendicular distance to the line.
    line_slope = normalized_tail_y - 1.0
    line_y = 1.0 + line_slope * normalized_x
    perpendicular_distance = (line_y - normalized_y) / np.sqrt(1.0 + line_slope**2)

    best_offset = int(np.argmax(perpendicular_distance))
    triangle_score = float(perpendicular_distance[best_offset])
    if not isfinite(triangle_score) or triangle_score < min_triangle_score:
        return None

    knee_bin = int(interior_bins[best_offset])

    # Use the *upper edge* of the knee bin.  Values below that edge stay on the
    # dense/small-gap side; a value equal to the returned integer threshold is
    # on the large-gap side, matching the baseline grouping rule (gap >= k
    # starts a new local group).  ceil avoids truncating the boundary downward.
    raw_threshold = float(np.expm1(bin_edges[knee_bin + 1]))
    threshold = min(MAX_INT64, max(1, ceil(raw_threshold)))
    peak_value = float(np.expm1((bin_edges[peak_bin] + bin_edges[peak_bin + 1]) / 2.0))

    return TriangleCandidate(
        histogram_bins=histogram_bins,
        threshold=threshold,
        raw_threshold=raw_threshold,
        triangle_score=triangle_score,
        peak_bin=peak_bin,
        knee_bin=knee_bin,
        tail_bin=tail_bin,
        peak_value=peak_value,
        peak_count=peak_count,
        knee_count=int(counts[knee_bin]),
        tail_count=tail_count,
    )


def estimate_skewed_threshold(
    data: pd.DataFrame,
    *,
    tail_quantile: float = DEFAULT_TAIL_QUANTILE,
    histogram_bins: Sequence[int] = DEFAULT_HISTOGRAM_BINS,
    min_triangle_score: float = DEFAULT_MIN_TRIANGLE_SCORE,
    max_threshold_spread: float = DEFAULT_MAX_THRESHOLD_SPREAD,
) -> SkewedThresholdResult:
    """Estimate a stable frequency-aware threshold for skewed ``delta_clock``.

    Why this differs from the old slope/MAD baseline:

    1. Every positive observation is retained in the histogram.  Four million
       repeated small values therefore carry four million observations' worth
       of weight; they are not collapsed into a few non-zero sorted slopes.
    2. ``log1p(delta_clock)`` compresses a right tail such as 3,000..980,000,
       so the maximum cannot consume nearly the entire histogram x-axis.
    3. Values above a high quantile are left out of the histogram geometry.
       They are still reported and still count when describing which side of
       the final threshold each observation falls on.
    4. The triangle knee is repeated at several bin counts.  The median is
       returned only when those candidates agree within a configured ratio.

    This detects a distributional scale change, not a proven business group
    boundary.  The diagnostics should be inspected before using the threshold.
    """

    normalized_bins = _validate_parameters(
        tail_quantile=tail_quantile,
        histogram_bins=histogram_bins,
        min_triangle_score=min_triangle_score,
        max_threshold_spread=max_threshold_spread,
    )
    delta_clock = _normalize_delta_clock(data)
    positive_values = delta_clock[delta_clock > 0]

    if positive_values.size < MIN_POSITIVE_DELTAS:
        raise ValueError(
            "at least "
            f"{MIN_POSITIVE_DELTAS} positive delta_clock observations are required"
        )

    # quantile uses the empirical ranks *with duplicates*.  This is important
    # for the user's distribution: millions of values below 20 must influence
    # the 99.5% cutoff and the histogram, rather than disappearing after a
    # unique-value or non-zero-slope filter.
    tail_clip_value = float(np.quantile(positive_values, tail_quantile))
    histogram_values = positive_values[positive_values <= tail_clip_value]
    tail_clipped_count = int(positive_values.size - histogram_values.size)

    log_values = np.log1p(histogram_values.astype("float64", copy=False))
    lower_log_value = float(log_values.min())
    upper_log_value = float(log_values.max())
    if lower_log_value == upper_log_value:
        raise ValueError(
            "positive delta_clock values have no variation after tail clipping"
        )

    candidates = tuple(
        candidate
        for bin_count in normalized_bins
        if (
            candidate := _triangle_candidate(
                log_values,
                lower_log_value=lower_log_value,
                upper_log_value=upper_log_value,
                histogram_bins=bin_count,
                min_triangle_score=min_triangle_score,
            )
        )
        is not None
    )
    if len(candidates) < MIN_BIN_CONFIGURATIONS:
        raise ValueError(
            "no reliable triangle knee: fewer than "
            f"{MIN_BIN_CONFIGURATIONS} histogram resolutions produced candidates"
        )

    raw_thresholds = np.asarray(
        [candidate.raw_threshold for candidate in candidates], dtype="float64"
    )
    threshold_spread_ratio = float(raw_thresholds.max() / raw_thresholds.min())
    if threshold_spread_ratio > max_threshold_spread:
        formatted_candidates = ", ".join(
            str(candidate.threshold) for candidate in candidates
        )
        raise ValueError(
            "unstable triangle threshold across histogram resolutions: "
            f"candidates=[{formatted_candidates}], "
            f"spread_ratio={threshold_spread_ratio:.3f} exceeds "
            f"{max_threshold_spread:.3f}"
        )

    threshold = min(MAX_INT64, max(1, ceil(float(np.median(raw_thresholds)))))
    below_threshold_count = int(np.count_nonzero(positive_values < threshold))

    return SkewedThresholdResult(
        threshold=threshold,
        total_count=int(delta_clock.size),
        positive_count=int(positive_values.size),
        ignored_nonpositive_count=int(delta_clock.size - positive_values.size),
        tail_quantile=tail_quantile,
        tail_clip_value=tail_clip_value,
        tail_clipped_count=tail_clipped_count,
        histogram_count=int(histogram_values.size),
        below_threshold_count=below_threshold_count,
        below_threshold_fraction=below_threshold_count / positive_values.size,
        threshold_spread_ratio=threshold_spread_ratio,
        candidates=candidates,
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
                "tail_quantile": result.tail_quantile,
                "tail_clip_value": result.tail_clip_value,
                "tail_clipped_count": result.tail_clipped_count,
                "histogram_count": result.histogram_count,
                "below_threshold_count": result.below_threshold_count,
                "below_threshold_fraction": result.below_threshold_fraction,
                "candidate_thresholds": ";".join(
                    str(value) for value in result.candidate_thresholds
                ),
                "threshold_spread_ratio": result.threshold_spread_ratio,
            }
        ]
    )


def _diagnostics_frame(result: SkewedThresholdResult) -> pd.DataFrame:
    """Convert per-resolution candidates into a diagnostic CSV."""

    return pd.DataFrame.from_records(
        [
            {
                "histogram_bins": candidate.histogram_bins,
                "candidate_threshold": candidate.threshold,
                "raw_threshold": candidate.raw_threshold,
                "triangle_score": candidate.triangle_score,
                "peak_bin": candidate.peak_bin,
                "knee_bin": candidate.knee_bin,
                "tail_bin": candidate.tail_bin,
                "peak_value": candidate.peak_value,
                "peak_count": candidate.peak_count,
                "knee_count": candidate.knee_count,
                "tail_count": candidate.tail_count,
            }
            for candidate in result.candidates
        ]
    )


def process_csv(
    input_csv: Path | str,
    output_csv: Path | str,
    *,
    diagnostics_csv: Path | str | None = None,
    tail_quantile: float = DEFAULT_TAIL_QUANTILE,
    histogram_bins: Sequence[int] = DEFAULT_HISTOGRAM_BINS,
    min_triangle_score: float = DEFAULT_MIN_TRIANGLE_SCORE,
    max_threshold_spread: float = DEFAULT_MAX_THRESHOLD_SPREAD,
) -> SkewedThresholdResult:
    """Read deltas, estimate a threshold, and write summary diagnostics."""

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

    # usecols 避免把原始 clock_delta.csv 中可能存在的其他列载入内存。
    # string dtype 先保留 CSV 的字面值，再由统一校验逻辑判断是否为整数。
    data = pd.read_csv(
        input_path,
        usecols=[DELTA_COLUMN],
        dtype={DELTA_COLUMN: "string"},
    )
    result = estimate_skewed_threshold(
        data,
        tail_quantile=tail_quantile,
        histogram_bins=histogram_bins,
        min_triangle_score=min_triangle_score,
        max_threshold_spread=max_threshold_spread,
    )
    _summary_frame(result).to_csv(output_path, index=False)
    if diagnostics_path is not None:
        _diagnostics_frame(result).to_csv(diagnostics_path, index=False)
    return result


def _parse_histogram_bins(value: str) -> tuple[int, ...]:
    """Parse ``--bins 32,48,64,96`` into integer resolutions."""

    try:
        values = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "bins must be comma-separated integers, for example 32,48,64,96"
        ) from error
    if not values:
        raise argparse.ArgumentTypeError("bins must not be empty")
    return values


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the standalone command-line interface."""

    parser = argparse.ArgumentParser(
        description=(
            "Estimate a frequency-aware delta_clock threshold with an ensemble "
            "of triangle knees on log-scaled histograms. Input must contain a "
            "delta_clock column, such as the output of mds.clock_delta."
        )
    )
    parser.add_argument("input_csv", type=Path, help="CSV containing delta_clock")
    parser.add_argument("output_csv", type=Path, help="one-row threshold summary CSV")
    parser.add_argument(
        "--diagnostics-csv",
        type=Path,
        help="optional per-histogram-resolution diagnostics CSV",
    )
    parser.add_argument(
        "--tail-quantile",
        type=float,
        default=DEFAULT_TAIL_QUANTILE,
        help="upper quantile retained in histogram geometry (default: %(default)s)",
    )
    parser.add_argument(
        "--bins",
        type=_parse_histogram_bins,
        default=DEFAULT_HISTOGRAM_BINS,
        help="comma-separated histogram resolutions (default: 32,48,64,96)",
    )
    parser.add_argument(
        "--min-triangle-score",
        type=float,
        default=DEFAULT_MIN_TRIANGLE_SCORE,
        help="minimum normalized triangle distance (default: %(default)s)",
    )
    parser.add_argument(
        "--max-threshold-spread",
        type=float,
        default=DEFAULT_MAX_THRESHOLD_SPREAD,
        help="maximum max/min candidate ratio (default: %(default)s)",
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
            tail_quantile=arguments.tail_quantile,
            histogram_bins=arguments.bins,
            min_triangle_score=arguments.min_triangle_score,
            max_threshold_spread=arguments.max_threshold_spread,
        )
    except (OSError, ValueError) as error:
        parser.exit(status=1, message=f"error: {error}\n")

    candidates = ",".join(str(value) for value in result.candidate_thresholds)
    print(
        "Detected frequency-aware delta_clock threshold: "
        f"threshold={result.threshold} us, "
        f"candidates=[{candidates}], "
        f"spread_ratio={result.threshold_spread_ratio:.3f}, "
        f"below={result.below_threshold_count}/{result.positive_count} "
        f"({result.below_threshold_fraction:.2%}), "
        f"tail_clipped={result.tail_clipped_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
