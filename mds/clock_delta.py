"""Calculate adjacent clock differences for market data CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd
from pandas.api.types import is_integer_dtype, is_unsigned_integer_dtype


REQUIRED_COLUMNS = ("clock", "stock_id", "time")
OUTPUT_COLUMNS = ("stock_id", "delta_clock")
MAX_INT64 = 2**63 - 1


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


def process_csv(input_csv: Path | str, output_csv: Path | str) -> None:
    """Read a market data CSV, calculate deltas, and write the result CSV."""

    data = pd.read_csv(
        input_csv,
        usecols=list(REQUIRED_COLUMNS),
        dtype={"clock": "string", "stock_id": "string", "time": "string"},
    )
    result = calculate_clock_deltas(data)
    result.to_csv(output_csv, columns=list(OUTPUT_COLUMNS), index=False)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate each row's clock difference from the preceding input row. "
            "The delta is zero for the first row and whenever time changes."
        )
    )
    parser.add_argument("input_csv", type=Path, help="source market data CSV")
    parser.add_argument("output_csv", type=Path, help="destination CSV")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)

    try:
        process_csv(arguments.input_csv, arguments.output_csv)
    except (OSError, ValueError) as error:
        parser.exit(status=1, message=f"error: {error}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
