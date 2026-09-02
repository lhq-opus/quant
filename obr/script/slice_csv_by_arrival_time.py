#!/usr/bin/env python3
"""Create order, trade, and book CSV subsets for an inclusive arrival-time range."""

import argparse
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print(
        "error: pandas is required; install quant/obr/requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)


TIME_COLUMN_CANDIDATES = ("clockAtArrivalTime", "clockAtArrival", "caa")


class CsvToolError(Exception):
    """An input or command-line contract error that should be shown to the user."""


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Filter order, trade, and book CSV files into the inclusive arrival-time "
            "range [START, END]."
        )
    )
    parser.add_argument(
        "--order", required=True, type=Path, help="Path to input order CSV"
    )
    parser.add_argument(
        "--trade", required=True, type=Path, help="Path to input trade CSV"
    )
    parser.add_argument(
        "--book", required=True, type=Path, help="Path to input book CSV"
    )
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument(
        "--output-path",
        dest="output_path",
        type=Path,
        help="Output directory for order.csv, trade.csv, and book.csv",
    )
    output_group.add_argument(
        "--output-dir",
        dest="output_path",
        type=Path,
        help="Deprecated alias for --output-path",
    )
    parser.add_argument(
        "--start-time", required=True, help="Inclusive start arrival time"
    )
    parser.add_argument("--end-time", required=True, help="Inclusive end arrival time")
    parser.add_argument(
        "--time-format",
        default="iso8601",
        help=(
            "Timestamp parser: 'iso8601' (default), or an explicit datetime.strptime "
            "format such as '%%Y%%m%%d%%H%%M%%S%%f'"
        ),
    )
    parser.add_argument(
        "--order-time-column",
        help="Explicit order arrival-time column; otherwise auto-detected",
    )
    parser.add_argument(
        "--trade-time-column",
        help="Explicit trade arrival-time column; otherwise auto-detected",
    )
    parser.add_argument(
        "--book-time-column",
        help="Explicit book arrival-time column; otherwise auto-detected",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacement of existing output CSV files",
    )
    return parser.parse_args()


def parse_timestamp(value, time_format, context):
    if value == "":
        raise CsvToolError("%s: timestamp is empty" % context)

    try:
        if time_format == "iso8601":
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            return datetime.fromisoformat(normalized)
        return datetime.strptime(value, time_format)
    except ValueError as error:
        raise CsvToolError(
            "%s: invalid timestamp %r for format %r: %s"
            % (context, value, time_format, error)
        )


def is_timezone_aware(value):
    return value.utcoffset() is not None


def validate_time_compatibility(value, reference, context):
    if is_timezone_aware(value) != is_timezone_aware(reference):
        raise CsvToolError(
            "%s: timezone-aware and timezone-naive timestamps cannot be mixed" % context
        )


def validate_header(header, path):
    if not header:
        raise CsvToolError("%s: CSV header is empty" % path)
    if any(column == "" for column in header):
        raise CsvToolError("%s: CSV header contains an empty column name" % path)

    seen = set()
    duplicates = []
    for column in header:
        if column in seen and column not in duplicates:
            duplicates.append(column)
        seen.add(column)
    if duplicates:
        raise CsvToolError(
            "%s: duplicate CSV column name(s): %s" % (path, ", ".join(duplicates))
        )


def resolve_time_column(header, explicit_column, path):
    if explicit_column:
        if explicit_column not in header:
            raise CsvToolError(
                "%s: requested time column %r is missing" % (path, explicit_column)
            )
        return explicit_column

    for candidate in TIME_COLUMN_CANDIDATES:
        if candidate in header:
            return candidate

    raise CsvToolError(
        "%s: no arrival-time column found; tried %s"
        % (path, ", ".join(TIME_COLUMN_CANDIDATES))
    )


def read_filtered_csv(
    path, explicit_time_column, start_time, end_time, time_format
):
    """Read text fields with pandas, then keep rows inside the time range."""
    try:
        # header=None lets us validate duplicate column names before assigning them.
        raw_frame = pd.read_csv(
            path,
            header=None,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            encoding="utf-8-sig",
            engine="python",
            skip_blank_lines=False,
        )
    except pd.errors.EmptyDataError:
        raise CsvToolError("%s: CSV file is empty" % path)
    except pd.errors.ParserError as error:
        raise CsvToolError("%s: malformed CSV data: %s" % (path, error))
    except OSError as error:
        raise CsvToolError("cannot open %s: %s" % (path, error))

    header = ["" if pd.isna(value) else str(value) for value in raw_frame.iloc[0]]
    validate_header(header, path)

    frame = raw_frame.iloc[1:].reset_index(drop=True)
    missing_rows = frame.isna().any(axis=1)
    if missing_rows.any():
        row_index = missing_rows[missing_rows].index[0]
        actual_columns = int(frame.loc[row_index].notna().sum())
        raise CsvToolError(
            "%s:%d: expected %d columns, found %d"
            % (path, row_index + 2, len(header), actual_columns)
        )

    frame.columns = header
    time_column = resolve_time_column(header, explicit_time_column, path)
    selected = []
    for row_index, raw_time in enumerate(frame[time_column], start=2):
        row_time = parse_timestamp(
            raw_time,
            time_format,
            "%s:%d column %s" % (path, row_index, time_column),
        )
        validate_time_compatibility(row_time, start_time, "%s:%d" % (path, row_index))
        selected.append(start_time <= row_time <= end_time)

    mask = pd.Series(selected, index=frame.index, dtype=bool)
    selected_frame = frame.loc[mask].reset_index(drop=True)
    return selected_frame, len(frame), time_column


def ensure_output_paths(inputs, outputs, overwrite):
    input_paths = set(path.resolve() for path in inputs)
    for output_path in outputs:
        if output_path.resolve() in input_paths:
            raise CsvToolError(
                "output path would overwrite an input file: %s" % output_path
            )
        if output_path.exists() and not overwrite:
            raise CsvToolError(
                "output already exists: %s (use --overwrite to replace it)"
                % output_path
            )


def write_csv_atomically(path, frame):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=str(path.parent),
            prefix=".%s." % path.name,
            suffix=".tmp",
            delete=False,
        ) as output_file:
            temporary_path = Path(output_file.name)
            frame.to_csv(output_file, index=False, lineterminator="\n")
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(str(temporary_path), str(path))
    except OSError as error:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        raise CsvToolError("cannot write %s: %s" % (path, error))


def main():
    args = parse_args()

    try:
        start_time = parse_timestamp(args.start_time, args.time_format, "--start-time")
        end_time = parse_timestamp(args.end_time, args.time_format, "--end-time")
        validate_time_compatibility(end_time, start_time, "--start-time/--end-time")
        if start_time > end_time:
            raise CsvToolError(
                "--start-time must be earlier than or equal to --end-time"
            )

        specifications = (
            ("order", args.order, args.order_time_column),
            ("trade", args.trade, args.trade_time_column),
            ("book", args.book, args.book_time_column),
        )
        results = []
        for label, input_path, explicit_column in specifications:
            result = read_filtered_csv(
                input_path,
                explicit_column,
                start_time,
                end_time,
                args.time_format,
            )
            results.append((label, input_path, result))

        args.output_path.mkdir(parents=True, exist_ok=True)
        output_paths = [args.output_path / (label + ".csv") for label, _, _ in results]
        ensure_output_paths(
            [args.order, args.trade, args.book], output_paths, args.overwrite
        )

        for output_path, result_item in zip(output_paths, results):
            label, _, result = result_item
            frame, total_rows, time_column = result
            write_csv_atomically(output_path, frame)
            print(
                "%s: kept %d of %d rows using %s -> %s"
                % (label, len(frame), total_rows, time_column, output_path)
            )
    except (CsvToolError, OSError, UnicodeError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
