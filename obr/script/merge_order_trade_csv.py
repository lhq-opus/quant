#!/usr/bin/env python3
"""Merge order and trade CSV files by arrival time using their ordered column union."""

import argparse
import csv
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path


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
    parser.add_argument("--order", required=True, type=Path, help="Path to input order CSV")
    parser.add_argument("--trade", required=True, type=Path, help="Path to input trade CSV")
    parser.add_argument("--output", required=True, type=Path, help="Path to merged output CSV")
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


def read_csv_records(path, source_type, explicit_time_column, time_format):
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
        records = []

        try:
            for line_number, row in enumerate(reader, start=2):
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
                values = dict(zip(header, row))
                records.append((row_time, source_type, values))
        except csv.Error as error:
            raise CsvToolError("%s: malformed CSV data: %s" % (path, error))

    return header, records, time_column


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
    for row_time, source_type, _ in records[1:]:
        if is_timezone_aware(row_time) != expected_awareness:
            raise CsvToolError(
                "timezone-aware and timezone-naive timestamps cannot be mixed; "
                "found mismatch in %s input" % source_type
            )


def ensure_output_path(order_path, trade_path, output_path, overwrite):
    resolved_output = output_path.resolve()
    if resolved_output == order_path.resolve() or resolved_output == trade_path.resolve():
        raise CsvToolError("output path would overwrite an input file: %s" % output_path)
    if output_path.exists() and not overwrite:
        raise CsvToolError(
            "output already exists: %s (use --overwrite to replace it)" % output_path
        )


def write_merged_csv(path, header, records):
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
            for _, source_type, values in records:
                writer.writerow(
                    [source_type]
                    + [values.get(column, "") for column in header if column != TYPE_COLUMN]
                )
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
        order_header, order_records, order_time_column = read_csv_records(
            args.order, "order", args.order_time_column, args.time_format
        )
        trade_header, trade_records, trade_time_column = read_csv_records(
            args.trade, "trade", args.trade_time_column, args.time_format
        )

        records = order_records + trade_records
        validate_timezone_compatibility(records)
        records.sort(key=lambda record: record[0])

        output_header = build_ordered_union(order_header, trade_header)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        ensure_output_path(args.order, args.trade, args.output, args.overwrite)
        write_merged_csv(args.output, output_header, records)

        print(
            "merged %d order rows and %d trade rows using %s/%s -> %s"
            % (
                len(order_records),
                len(trade_records),
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
