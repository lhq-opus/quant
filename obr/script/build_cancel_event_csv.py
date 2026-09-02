#!/usr/bin/env python3
"""Build event.csv from order rows and cancellation trade rows.

This is a small validation utility.  A cancellation row normally carries a zero
TradePrice, so the script looks up the referenced order and copies its Price into
the cancellation event before order and trade events are merged by arrival time.
"""

import argparse
import os
import sys
import tempfile
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

ORDER_COLUMNS = ["Side", "OrderType", "Price", "OrderQty"]
TRADE_COLUMNS = ["ExecType", "TradeQty", "TradePrice"]
EVENT_COLUMNS = ["caa"] + ORDER_COLUMNS + TRADE_COLUMNS


class EventCsvError(Exception):
    """An expected input-contract error shown without a Python traceback."""


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Keep orders and ExecType=4 trades, fill cancellation TradePrice from "
            "the referenced order, sort by arrival time, and write event.csv."
        )
    )
    parser.add_argument("--order", required=True, type=Path, help="Input order.csv")
    parser.add_argument("--trade", required=True, type=Path, help="Input trade.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("event.csv"),
        help="Output CSV path (default: ./event.csv)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output, but never either input file",
    )
    return parser.parse_args()


def validate_header(header, path):
    if not header:
        raise EventCsvError("%s: CSV header is empty" % path)
    if any(column == "" for column in header):
        raise EventCsvError("%s: CSV header contains an empty column name" % path)

    seen = set()
    duplicates = []
    for column in header:
        if column in seen and column not in duplicates:
            duplicates.append(column)
        seen.add(column)
    if duplicates:
        raise EventCsvError(
            "%s: duplicate CSV column name(s): %s" % (path, ", ".join(duplicates))
        )


def read_csv_as_strings(path):
    """Read every field as text and retain strict header/row validation."""
    try:
        # Reading the header as row zero keeps duplicate names visible to us.
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
        raise EventCsvError("%s: CSV file is empty" % path)
    except pd.errors.ParserError as error:
        raise EventCsvError("%s: malformed CSV data: %s" % (path, error))
    except OSError as error:
        raise EventCsvError("cannot open %s: %s" % (path, error))

    header = ["" if pd.isna(value) else str(value) for value in raw_frame.iloc[0]]
    validate_header(header, path)

    frame = raw_frame.iloc[1:].reset_index(drop=True)
    missing_rows = frame.isna().any(axis=1)
    if missing_rows.any():
        row_index = missing_rows[missing_rows].index[0]
        actual_columns = int(frame.loc[row_index].notna().sum())
        raise EventCsvError(
            "%s:%d: expected %d columns, found %d"
            % (path, row_index + 2, len(header), actual_columns)
        )

    frame.columns = header
    return frame


def require_columns(frame, required_columns, path):
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise EventCsvError(
            "%s: missing required column(s): %s" % (path, ", ".join(missing))
        )


def find_time_column(frame, path):
    for column in TIME_COLUMN_CANDIDATES:
        if column in frame.columns:
            return column
    raise EventCsvError(
        "%s: no arrival-time column found; tried %s"
        % (path, ", ".join(TIME_COLUMN_CANDIDATES))
    )


def parse_integer(raw_value, field, path, line_number, minimum):
    try:
        value = int(raw_value)
    except ValueError:
        raise EventCsvError(
            "%s:%d column %s: invalid integer %r"
            % (path, line_number, field, raw_value)
        )
    if value < minimum:
        raise EventCsvError(
            "%s:%d column %s: value must be at least %d"
            % (path, line_number, field, minimum)
        )
    return value


def require_non_empty(raw_value, field, path, line_number):
    if raw_value == "":
        raise EventCsvError(
            "%s:%d column %s: value is empty" % (path, line_number, field)
        )


def build_order_price_index(order_frame, order_path):
    """Map the exchange-scoped order reference to its original price text."""
    prices = {}
    fields = ["ChannelNo", "ApplSeqNum"] + ORDER_COLUMNS
    for line_number, values in enumerate(
        order_frame[fields].itertuples(index=False, name=None), start=2
    ):
        raw_channel, raw_asn, side, order_type, price, order_qty = values
        channel = parse_integer(raw_channel, "ChannelNo", order_path, line_number, 1)
        asn = parse_integer(raw_asn, "ApplSeqNum", order_path, line_number, 1)
        for field, raw_value in (
            ("Side", side),
            ("OrderType", order_type),
            ("Price", price),
            ("OrderQty", order_qty),
        ):
            require_non_empty(raw_value, field, order_path, line_number)

        key = (channel, asn)
        if key in prices:
            previous_line = prices[key][1]
            raise EventCsvError(
                "%s:%d: duplicate order key ChannelNo=%d, ApplSeqNum=%d; "
                "first seen on line %d"
                % (order_path, line_number, channel, asn, previous_line)
            )
        prices[key] = (price, line_number)
    return prices


def fill_cancel_prices(trade_frame, order_prices, trade_path):
    """Keep ExecType=4 rows and replace TradePrice with the order's Price."""
    cancel_frame = trade_frame.loc[trade_frame["ExecType"] == "4"].copy()
    lookup_fields = ["ChannelNo", "BidApplSeqNum", "OfferApplSeqNum"]
    resolved_prices = []

    for row_index, values in cancel_frame[lookup_fields].iterrows():
        line_number = int(row_index) + 2
        require_non_empty(
            cancel_frame.loc[row_index, "TradeQty"],
            "TradeQty",
            trade_path,
            line_number,
        )
        channel = parse_integer(
            values["ChannelNo"], "ChannelNo", trade_path, line_number, 1
        )
        bid_asn = parse_integer(
            values["BidApplSeqNum"],
            "BidApplSeqNum",
            trade_path,
            line_number,
            0,
        )
        offer_asn = parse_integer(
            values["OfferApplSeqNum"],
            "OfferApplSeqNum",
            trade_path,
            line_number,
            0,
        )

        # Exactly one side identifies the canceled order; zero is not an order ID.
        if (bid_asn == 0) == (offer_asn == 0):
            raise EventCsvError(
                "%s:%d: ExecType=4 requires exactly one non-zero order reference"
                % (trade_path, line_number)
            )

        referenced_asn = bid_asn if bid_asn != 0 else offer_asn
        key = (channel, referenced_asn)
        if key not in order_prices:
            raise EventCsvError(
                "%s:%d: referenced order not found: ChannelNo=%d, ApplSeqNum=%d"
                % (trade_path, line_number, channel, referenced_asn)
            )
        resolved_prices.append(order_prices[key][0])

    cancel_frame["TradePrice"] = resolved_prices
    return cancel_frame


def parse_arrival_times(values):
    if (values == "").any():
        row_index = values[values == ""].index[0]
        raise EventCsvError("event row %d: caa is empty" % (int(row_index) + 2))
    try:
        return pd.to_datetime(values, format="ISO8601", errors="raise", utc=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise EventCsvError("cannot parse caa as ISO 8601 timestamp: %s" % error)


def build_events(order_frame, cancel_frame, order_time_column, trade_time_column):
    order_events = order_frame[[order_time_column] + ORDER_COLUMNS].copy()
    order_events = order_events.rename(columns={order_time_column: "caa"})

    trade_events = cancel_frame[[trade_time_column] + TRADE_COLUMNS].copy()
    trade_events = trade_events.rename(columns={trade_time_column: "caa"})

    # Reindex fills fields that belong only to the other event type with empty text.
    order_events = order_events.reindex(columns=EVENT_COLUMNS, fill_value="")
    trade_events = trade_events.reindex(columns=EVENT_COLUMNS, fill_value="")
    events = pd.concat([order_events, trade_events], ignore_index=True, sort=False)

    sort_times = parse_arrival_times(events["caa"])
    events["__sort_time"] = sort_times
    events = events.sort_values("__sort_time", kind="stable")
    return events.drop(columns="__sort_time").reset_index(drop=True)


def validate_output_path(order_path, trade_path, output_path, overwrite):
    resolved_output = output_path.resolve()
    if (
        resolved_output == order_path.resolve()
        or resolved_output == trade_path.resolve()
    ):
        raise EventCsvError(
            "output path would overwrite an input file: %s" % output_path
        )
    if output_path.exists() and not overwrite:
        raise EventCsvError(
            "output already exists: %s (use --overwrite to replace it)" % output_path
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
        raise EventCsvError("cannot write %s: %s" % (path, error))


def main():
    args = parse_args()
    try:
        validate_output_path(args.order, args.trade, args.output, args.overwrite)

        order_frame = read_csv_as_strings(args.order)
        trade_frame = read_csv_as_strings(args.trade)
        order_time_column = find_time_column(order_frame, args.order)
        trade_time_column = find_time_column(trade_frame, args.trade)

        require_columns(
            order_frame,
            ["ChannelNo", "ApplSeqNum"] + ORDER_COLUMNS,
            args.order,
        )
        require_columns(
            trade_frame,
            [
                "ChannelNo",
                "ExecType",
                "TradeQty",
                "BidApplSeqNum",
                "OfferApplSeqNum",
            ],
            args.trade,
        )

        order_prices = build_order_price_index(order_frame, args.order)
        cancel_frame = fill_cancel_prices(trade_frame, order_prices, args.trade)
        events = build_events(
            order_frame, cancel_frame, order_time_column, trade_time_column
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_csv_atomically(args.output, events)
        print(
            "wrote %d order rows and %d cancellation rows -> %s"
            % (len(order_frame), len(cancel_frame), args.output)
        )
    except (EventCsvError, OSError, UnicodeError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
