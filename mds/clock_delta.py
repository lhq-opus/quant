"""Calculate and inspect adjacent clock differences in market data CSV files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Sequence

import pandas as pd
from pandas.api.types import is_integer_dtype, is_unsigned_integer_dtype


REQUIRED_COLUMNS = ("clock", "stock_id", "time")
OUTPUT_COLUMNS = ("stock_id", "delta_clock")
MAX_INT64 = 2**63 - 1
DEFAULT_ROBUST_Z_THRESHOLD = 6.0
DEFAULT_MIN_SLOPE_MULTIPLIER = 5.0
DEFAULT_MIN_SEGMENT_SIZE = 2
MIN_BASELINE_SLOPES = 3
MAD_TO_STANDARD_DEVIATION = 1.4826


@dataclass(frozen=True)
class AbruptIncrease:
    """Describe an anomalous jump in sorted positive ``delta_clock`` values."""

    delta_clock: int
    previous_delta_clock: int
    slope: int
    slope_threshold: float
    robust_z_score: float
    slope_multiplier: float
    lower_count: int
    upper_count: int


def calculate_clock_deltas(data: pd.DataFrame) -> pd.DataFrame:
    """Return ``stock_id`` and the adjacent ``clock`` difference.

    Input row order is preserved. The first delta is zero. Every later delta is
    also zero when its ``time`` differs from the preceding row; otherwise it is
    the current ``clock`` minus the preceding row's ``clock``.
    """

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"missing required CSV column(s): {missing}")

    if data["stock_id"].isna().any():
        raise ValueError("stock_id contains missing values")
    if data["time"].isna().any():
        raise ValueError("time contains missing values")
    if data["clock"].isna().any():
        raise ValueError("clock contains missing values")

    if data.empty:
        return pd.DataFrame(
            {
                "stock_id": data["stock_id"].copy(),
                "delta_clock": pd.Series(index=data.index, dtype="int64"),
            }
        )

    try:
        clock = pd.to_numeric(data["clock"], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError("clock must contain integer microsecond timestamps") from error

    if not is_integer_dtype(clock.dtype):
        raise ValueError("clock must contain integer microsecond timestamps")
    if is_unsigned_integer_dtype(clock.dtype) and clock.max() > MAX_INT64:
        raise ValueError("clock contains a value outside the signed 64-bit range")

    clock = clock.astype("int64")
    previous_clock = clock.shift(1, fill_value=clock.iloc[0])
    same_time_as_previous = data["time"].eq(data["time"].shift(1)).fillna(False)
    delta_clock = (
        clock.sub(previous_clock)
        .where(same_time_as_previous, other=0)
        .astype("int64")
    )

    return pd.DataFrame(
        {
            "stock_id": data["stock_id"].copy(),
            "delta_clock": delta_clock,
        }
    )


def sort_clock_deltas(data: pd.DataFrame) -> pd.DataFrame:
    """Return rows stably sorted by ``delta_clock`` in ascending order."""

    if "delta_clock" not in data:
        raise ValueError("missing required column: delta_clock")

    return data.sort_values("delta_clock", kind="stable", ignore_index=True)


def find_abrupt_increase(
    data: pd.DataFrame,
    *,
    robust_z_threshold: float = DEFAULT_ROBUST_Z_THRESHOLD,
    min_slope_multiplier: float = DEFAULT_MIN_SLOPE_MULTIPLIER,
    min_segment_size: int = DEFAULT_MIN_SEGMENT_SIZE,
) -> AbruptIncrease | None:
    """Find the first anomalously large slope in sorted positive deltas.

    A slope is the difference between two adjacent, sorted ``delta_clock``
    values. Zero deltas are ``time``-boundary sentinels and negative deltas
    indicate decreasing input clocks, so neither participates in detection.

    The normal slope scale is estimated robustly with the median and MAD. A
    candidate must exceed both the robust threshold and a multiple of the
    median positive slope. Requiring samples on both sides avoids treating a
    single extreme tail value as a reliable change point.
    """

    if not isfinite(robust_z_threshold) or robust_z_threshold < 0:
        raise ValueError("robust_z_threshold must be finite and non-negative")
    if not isfinite(min_slope_multiplier) or min_slope_multiplier <= 1:
        raise ValueError("min_slope_multiplier must be finite and greater than 1")
    if min_segment_size < 1:
        raise ValueError("min_segment_size must be at least 1")
    if "delta_clock" not in data:
        raise ValueError("missing required column: delta_clock")

    try:
        delta_clock = pd.to_numeric(data["delta_clock"], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError("delta_clock must contain integer values") from error

    if delta_clock.isna().any() or not is_integer_dtype(delta_clock.dtype):
        raise ValueError("delta_clock must contain integer values")
    if is_unsigned_integer_dtype(delta_clock.dtype) and delta_clock.max() > MAX_INT64:
        raise ValueError("delta_clock contains a value outside the signed 64-bit range")

    positive_deltas = (
        delta_clock.loc[delta_clock.gt(0)]
        .astype("int64")
        .sort_values(kind="stable")
        .reset_index(drop=True)
    )
    if len(positive_deltas) < 2 * min_segment_size:
        return None

    slopes = positive_deltas.diff()
    positive_slopes = slopes.loc[slopes.gt(0)]
    if len(positive_slopes) < MIN_BASELINE_SLOPES:
        return None

    median_slope = float(positive_slopes.median())
    median_absolute_deviation = float(
        positive_slopes.sub(median_slope).abs().median()
    )
    robust_scale = MAD_TO_STANDARD_DEVIATION * median_absolute_deviation
    robust_threshold = median_slope + robust_z_threshold * robust_scale
    multiplier_threshold = median_slope * min_slope_multiplier
    slope_threshold = max(robust_threshold, multiplier_threshold)

    positions = pd.Series(range(len(positive_deltas)), index=positive_deltas.index)
    eligible = (
        slopes.gt(slope_threshold)
        & positions.ge(min_segment_size)
        & positions.le(len(positive_deltas) - min_segment_size)
    )
    candidate_positions = positions.loc[eligible]
    if candidate_positions.empty:
        return None

    position = int(candidate_positions.iloc[0])
    slope = int(slopes.iloc[position])
    if robust_scale == 0:
        robust_z_score = float("inf")
    else:
        robust_z_score = (slope - median_slope) / robust_scale

    return AbruptIncrease(
        delta_clock=int(positive_deltas.iloc[position]),
        previous_delta_clock=int(positive_deltas.iloc[position - 1]),
        slope=slope,
        slope_threshold=slope_threshold,
        robust_z_score=robust_z_score,
        slope_multiplier=slope / median_slope,
        lower_count=position,
        upper_count=len(positive_deltas) - position,
    )


def process_csv(
    input_csv: Path | str,
    output_csv: Path | str,
    *,
    robust_z_threshold: float = DEFAULT_ROBUST_Z_THRESHOLD,
    min_slope_multiplier: float = DEFAULT_MIN_SLOPE_MULTIPLIER,
    min_segment_size: int = DEFAULT_MIN_SEGMENT_SIZE,
) -> AbruptIncrease | None:
    """Calculate deltas, sort the output, detect a jump, and write the CSV."""

    data = pd.read_csv(
        input_csv,
        usecols=list(REQUIRED_COLUMNS),
        dtype={"clock": "string", "stock_id": "string", "time": "string"},
    )
    result = sort_clock_deltas(calculate_clock_deltas(data))
    abrupt_increase = find_abrupt_increase(
        result,
        robust_z_threshold=robust_z_threshold,
        min_slope_multiplier=min_slope_multiplier,
        min_segment_size=min_segment_size,
    )
    result.to_csv(output_csv, columns=list(OUTPUT_COLUMNS), index=False)
    return abrupt_increase


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate each row's clock difference from the preceding input row. "
            "Sort the output by delta_clock and report the first anomalous "
            "increase. The delta is zero for the first row and whenever time "
            "changes."
        )
    )
    parser.add_argument("input_csv", type=Path, help="source market data CSV")
    parser.add_argument("output_csv", type=Path, help="destination CSV")
    parser.add_argument(
        "--robust-z-threshold",
        type=float,
        default=DEFAULT_ROBUST_Z_THRESHOLD,
        help="MAD-based slope anomaly threshold (default: %(default)s)",
    )
    parser.add_argument(
        "--min-slope-multiplier",
        type=float,
        default=DEFAULT_MIN_SLOPE_MULTIPLIER,
        help="minimum slope divided by the median positive slope (default: %(default)s)",
    )
    parser.add_argument(
        "--min-segment-size",
        type=int,
        default=DEFAULT_MIN_SEGMENT_SIZE,
        help="minimum positive delta count on each side (default: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)

    try:
        abrupt_increase = process_csv(
            arguments.input_csv,
            arguments.output_csv,
            robust_z_threshold=arguments.robust_z_threshold,
            min_slope_multiplier=arguments.min_slope_multiplier,
            min_segment_size=arguments.min_segment_size,
        )
    except (OSError, ValueError) as error:
        parser.exit(status=1, message=f"error: {error}\n")

    if abrupt_increase is None:
        print("No abrupt delta_clock increase detected.")
    else:
        print(
            "Detected abrupt delta_clock increase: "
            f"value={abrupt_increase.delta_clock}, "
            f"previous={abrupt_increase.previous_delta_clock}, "
            f"slope={abrupt_increase.slope}, "
            f"robust_z={abrupt_increase.robust_z_score:.2f}, "
            f"slope_multiplier={abrupt_increase.slope_multiplier:.2f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
