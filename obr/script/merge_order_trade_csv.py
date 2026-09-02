#!/usr/bin/env python3
"""Merge order and trade CSV files by arrival time using their ordered column union."""

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
TYPE_COLUMN = "type"


class CsvToolError(Exception):
    """An input or command-line contract error that should be shown to the user."""


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Merge order and trade CSV rows, add type=order|trade, take the ordered "
            "union of both headers, and sort stably by arrival time."
        )
    )
    parser.add_argument(
        "--order", required=True, type=Path, help="Path to input order CSV"
    )
    parser.add_argument(
        "--trade", required=True, type=Path, help="Path to input trade CSV"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Path to merged output CSV"
    )
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
        "--overwrite",
        action="store_true",
        help="Allow replacement of an existing output CSV file",
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
    if TYPE_COLUMN in header:
        raise CsvToolError(
            "%s: input already contains reserved output column %r" % (path, TYPE_COLUMN)
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


def read_csv_records(path, explicit_time_column, time_format):
    try:
        # Reading the header as row zero preserves duplicate names for validation.
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
    timestamps = []
    for row_index, raw_time in enumerate(frame[time_column], start=2):
        timestamps.append(
            parse_timestamp(
                raw_time,
                time_format,
                "%s:%d column %s" % (path, row_index, time_column),
            )
        )

    return header, frame, timestamps, time_column


def build_ordered_union(order_header, trade_header):
    output_header = [TYPE_COLUMN]
    output_header.extend(order_header)
    for column in trade_header:
        if column not in order_header:
            output_header.append(column)
    return output_header


def validate_timezone_compatibility(records):
    if not records:
        return

    expected_awareness = is_timezone_aware(records[0][0])
    for row_time, source_type in records[1:]:
        if is_timezone_aware(row_time) != expected_awareness:
            raise CsvToolError(
                "timezone-aware and timezone-naive timestamps cannot be mixed; "
                "found mismatch in %s input" % source_type
            )


def ensure_output_path(order_path, trade_path, output_path, overwrite):
    resolved_output = output_path.resolve()
    if (
        resolved_output == order_path.resolve()
        or resolved_output == trade_path.resolve()
    ):
        raise CsvToolError(
            "output path would overwrite an input file: %s" % output_path
        )
    if output_path.exists() and not overwrite:
        raise CsvToolError(
            "output already exists: %s (use --overwrite to replace it)" % output_path
        )


def write_merged_csv(path, frame):
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
        order_header, order_frame, order_times, order_time_column = read_csv_records(
            args.order, args.order_time_column, args.time_format
        )
        trade_header, trade_frame, trade_times, trade_time_column = read_csv_records(
            args.trade, args.trade_time_column, args.time_format
        )

        timestamp_records = [(value, "order") for value in order_times]
        timestamp_records += [(value, "trade") for value in trade_times]
        validate_timezone_compatibility(timestamp_records)

        output_header = build_ordered_union(order_header, trade_header)
        data_columns = output_header[1:]

        order_output = order_frame.reindex(columns=data_columns, fill_value="")
        order_output.insert(0, TYPE_COLUMN, "order")
        trade_output = trade_frame.reindex(columns=data_columns, fill_value="")
        trade_output.insert(0, TYPE_COLUMN, "trade")

        merged_frame = pd.concat(
            [order_output, trade_output], ignore_index=True, sort=False
        )
        all_times = order_times + trade_times
        stable_order = sorted(range(len(all_times)), key=lambda index: all_times[index])
        merged_frame = merged_frame.iloc[stable_order].reset_index(drop=True)
        merged_frame = merged_frame.loc[:, output_header]

        args.output.parent.mkdir(parents=True, exist_ok=True)
        ensure_output_path(args.order, args.trade, args.output, args.overwrite)
        write_merged_csv(args.output, merged_frame)

        print(
            "merged %d order rows and %d trade rows using %s/%s -> %s"
            % (
                len(order_frame),
                len(trade_frame),
                order_time_column,
                trade_time_column,
                args.output,
            )
        )
    except (CsvToolError, OSError, UnicodeError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
