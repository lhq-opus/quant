#!/usr/bin/env python3
"""Create order, trade, and book CSV subsets for an inclusive arrival-time range."""

import argparse
import csv
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path


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
    parser.add_argument("--order", required=True, type=Path, help="Path to input order CSV")
    parser.add_argument("--trade", required=True, type=Path, help="Path to input trade CSV")
    parser.add_argument("--book", required=True, type=Path, help="Path to input book CSV")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory that will receive order.csv, trade.csv, and book.csv",
    )
    parser.add_argument("--start-time", required=True, help="Inclusive start arrival time")
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
    try:
        input_file = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as error:
        raise CsvToolError("cannot open %s: %s" % (path, error))

    with input_file:
        reader = csv.reader(input_file, strict=True)
        try:
            header = next(reader)
        except StopIteration:
            raise CsvToolError("%s: CSV file is empty" % path)
        except csv.Error as error:
            raise CsvToolError("%s: cannot read CSV header: %s" % (path, error))

        validate_header(header, path)
        time_column = resolve_time_column(header, explicit_time_column, path)
        time_index = header.index(time_column)
        selected_rows = []
        total_rows = 0

        try:
            for line_number, row in enumerate(reader, start=2):
                total_rows += 1
                if len(row) != len(header):
                    raise CsvToolError(
                        "%s:%d: expected %d columns, found %d"
                        % (path, line_number, len(header), len(row))
                    )

                row_time = parse_timestamp(
                    row[time_index],
                    time_format,
                    "%s:%d column %s" % (path, line_number, time_column),
                )
                validate_time_compatibility(
                    row_time, start_time, "%s:%d" % (path, line_number)
                )
                if start_time <= row_time <= end_time:
                    selected_rows.append(row)
        except csv.Error as error:
            raise CsvToolError("%s: malformed CSV data: %s" % (path, error))

    return header, selected_rows, total_rows, time_column


def ensure_output_paths(inputs, outputs, overwrite):
    input_paths = set(path.resolve() for path in inputs)
    for output_path in outputs:
        if output_path.resolve() in input_paths:
            raise CsvToolError("output path would overwrite an input file: %s" % output_path)
        if output_path.exists() and not overwrite:
            raise CsvToolError(
                "output already exists: %s (use --overwrite to replace it)" % output_path
            )


def write_csv_atomically(path, header, rows):
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
            writer = csv.writer(output_file, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
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
            raise CsvToolError("--start-time must be earlier than or equal to --end-time")

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

        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_paths = [args.output_dir / (label + ".csv") for label, _, _ in results]
        ensure_output_paths(
            [args.order, args.trade, args.book], output_paths, args.overwrite
        )

        for output_path, result_item in zip(output_paths, results):
            label, _, result = result_item
            header, rows, total_rows, time_column = result
            write_csv_atomically(output_path, header, rows)
            print(
                "%s: kept %d of %d rows using %s -> %s"
                % (label, len(rows), total_rows, time_column, output_path)
            )
    except (CsvToolError, OSError, UnicodeError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
