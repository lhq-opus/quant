#!/usr/bin/env python3
"""A small, heavily commented order-book reconstruction demo.

The production implementation remains C++. This Python program exists so that the
state transitions can be read and experimented with in one file.
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print(
        "error: pandas is required; install quant/obr/requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)


ORDER_HEADER = [
    "clockAtArrival",
    "sequenceNo",
    "exchld",
    "securityType",
    "__isRepeadted",
    "TransactTime",
    "ChannelNo",
    "ApplSeqNum",
    "SecurityID",
    "secid",
    "mdSource",
    "Side",
    "OrderType",
    "__origTickSeq",
    "Price",
    "OrderQty",
    "OrderIndex",
    "BizIndex",
    "PacketID",
    "IsLastMsg",
]

TRADE_HEADER = [
    "clockAtArrival",
    "sequenceNo",
    "exchld",
    "securityType",
    "__isRepeadted",
    "TransactTime",
    "ChannelNo",
    "ApplSeqNum",
    "SecurityID",
    "secid",
    "mdSource",
    "ExecType",
    "TradeBSFlag",
    "__origTickSeq",
    "TradePrice",
    "TradeQty",
    "TradyMoney",
    "BidApplSeqNum",
    "OfferApplSeqNum",
    "BizIndex",
    "PacketID",
    "IsLastMsg",
]

BOOK_HEADER = [
    "caa",
    "secid",
    "sno",
    "asn",
    "tst",
    "nts",
    "cvl",
    "cto",
    "lpr",
    "opx",
    "bp5",
    "bo4",
    "bp3",
    "bp2",
    "bp1",
    "ap1",
    "ap2",
    "ap3",
    "ap4",
    "ap5",
    "bs5",
    "bs4",
    "bs3",
    "bs2",
    "bs1",
    "as1",
    "as2",
    "as3",
    "as4",
    "as5",
]

FOUR_DECIMAL_PLACES = Decimal("0.0001")


class DemoError(Exception):
    """A data-contract error that can be reported without a Python traceback."""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Reconstruct a simple single-instrument order book into book.csv."
    )
    parser.add_argument("--order", required=True, type=Path, help="Input order.csv")
    parser.add_argument("--trade", required=True, type=Path, help="Input trade.csv")
    parser.add_argument("--output", required=True, type=Path, help="Output book.csv")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file, but never either input file",
    )
    return parser.parse_args()


def context(record, field=None):
    location = "%s:%d" % (record["path"], record["line_number"])
    return "%s column %s" % (location, field) if field else location


def read_csv(path, expected_header, source):
    """Read one raw CSV and preserve the source path and line for diagnostics."""
    try:
        # header=None preserves duplicate names instead of letting pandas rename them.
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
        raise DemoError("%s: CSV file is empty" % path)
    except pd.errors.ParserError as error:
        raise DemoError("%s: malformed CSV data: %s" % (path, error))
    except OSError as error:
        raise DemoError("cannot open %s: %s" % (path, error))

    actual_header = [
        "" if pd.isna(value) else str(value) for value in raw_frame.iloc[0]
    ]
    if actual_header != expected_header:
        raise DemoError(
            "%s: unexpected %s header\nexpected: %s\nactual:   %s"
            % (path, source, ",".join(expected_header), ",".join(actual_header))
        )

    frame = raw_frame.iloc[1:].reset_index(drop=True)
    missing_rows = frame.isna().any(axis=1)
    if missing_rows.any():
        row_index = missing_rows[missing_rows].index[0]
        actual_columns = int(frame.loc[row_index].notna().sum())
        raise DemoError(
            "%s:%d: expected %d columns, found %d"
            % (path, row_index + 2, len(expected_header), actual_columns)
        )

    frame.columns = actual_header
    records = []
    for line_number, values in enumerate(
        frame.itertuples(index=False, name=None), start=2
    ):
        records.append(
            {
                "source": source,
                "path": path,
                "line_number": line_number,
                "row": dict(zip(expected_header, values)),
            }
        )

    return records


def parse_integer(record, field, minimum):
    raw_value = record["row"][field]
    try:
        value = int(raw_value)
    except ValueError:
        raise DemoError("%s: invalid integer %r" % (context(record, field), raw_value))
    if value < minimum:
        raise DemoError(
            "%s: value must be at least %d, found %d"
            % (context(record, field), minimum, value)
        )
    return value


def parse_price(record, field, allow_zero=False):
    raw_value = record["row"][field]
    try:
        value = Decimal(raw_value)
        rounded = value.quantize(FOUR_DECIMAL_PLACES)
    except InvalidOperation:
        raise DemoError(
            "%s: invalid decimal price %r" % (context(record, field), raw_value)
        )

    if not value.is_finite():
        raise DemoError("%s: price must be finite" % context(record, field))
    if value < 0 or (value == 0 and not allow_zero):
        requirement = "non-negative" if allow_zero else "positive"
        raise DemoError("%s: price must be %s" % (context(record, field), requirement))
    if rounded != value:
        raise DemoError(
            "%s: price has more than four decimal places" % context(record, field)
        )
    return value


def parse_trading_day(record):
    raw_value = record["row"]["clockAtArrival"]
    normalized = raw_value[:-1] + "+00:00" if raw_value.endswith("Z") else raw_value
    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError as error:
        raise DemoError(
            "%s: invalid ISO 8601 timestamp %r: %s"
            % (context(record, "clockAtArrival"), raw_value, error)
        )


def normalize_record(record):
    """Convert one raw row into the small event model used by the demo."""
    row = record["row"]
    event = {
        "source": record["source"],
        "location": context(record),
        "trading_day": parse_trading_day(record),
        "channel": parse_integer(record, "ChannelNo", 1),
        "asn": parse_integer(record, "ApplSeqNum", 1),
        "security_id": row["SecurityID"],
        "secid": row["secid"],
        "clock_at_arrival": row["clockAtArrival"],
        "sequence_no": row["sequenceNo"],
        "transact_time": row["TransactTime"],
    }

    for field in ("SecurityID", "secid", "sequenceNo", "TransactTime"):
        if row[field] == "":
            raise DemoError("%s: required value is empty" % context(record, field))

    if row["__isRepeadted"] not in ("", "0"):
        raise DemoError("%s: repeated source rows are not accepted" % context(record))

    if record["source"] == "order":
        if row["Side"] not in ("1", "2"):
            raise DemoError(
                "%s: Side must be 1 (buy) or 2 (sell)"
                % context(record, "Side")
            )
        if row["OrderType"] != "2":
            raise DemoError(
                "%s: demo supports OrderType=2 (limit) only"
                % context(record, "OrderType")
            )

        event["event_type"] = "add"
        event["side"] = "buy" if row["Side"] == "1" else "sell"
        event["price"] = parse_price(record, "Price")
        event["quantity"] = parse_integer(record, "OrderQty", 1)
        event["order_key"] = (
            event["trading_day"],
            event["channel"],
            event["asn"],
        )
        return event

    if row["TradeBSFlag"] != "":
        raise DemoError(
            "%s: non-empty TradeBSFlag needs an upstream data dictionary"
            % context(record, "TradeBSFlag")
        )

    event["quantity"] = parse_integer(record, "TradeQty", 1)
    bid_asn = parse_integer(record, "BidApplSeqNum", 0)
    ask_asn = parse_integer(record, "OfferApplSeqNum", 0)
    event["bid_order_key"] = (
        event["trading_day"],
        event["channel"],
        bid_asn,
    )
    event["ask_order_key"] = (
        event["trading_day"],
        event["channel"],
        ask_asn,
    )

    if row["ExecType"] == "F":
        if bid_asn == 0 or ask_asn == 0:
            raise DemoError(
                "%s: trade must reference both buy and sell orders" % context(record)
            )
        event["event_type"] = "trade"
        event["trade_price"] = parse_price(record, "TradePrice")
        return event

    if row["ExecType"] == "4":
        if (bid_asn == 0) == (ask_asn == 0):
            raise DemoError(
                "%s: cancel must reference exactly one buy or sell order"
                % context(record)
            )
        parse_price(record, "TradePrice", allow_zero=True)
        event["event_type"] = "cancel"
        event["side"] = "buy" if bid_asn != 0 else "sell"
        event["order_key"] = (
            event["bid_order_key"] if bid_asn != 0 else event["ask_order_key"]
        )
        return event

    raise DemoError(
        "%s: ExecType must be F (trade) or 4 (cancel)" % context(record, "ExecType")
    )


def load_events(order_path, trade_path):
    raw_records = read_csv(order_path, ORDER_HEADER, "order")
    raw_records += read_csv(trade_path, TRADE_HEADER, "trade")
    events = [normalize_record(record) for record in raw_records]

    # The demo supports one channel, so ApplSeqNum gives one deterministic event order.
    events.sort(key=lambda event: (event["channel"], event["asn"]))
    if not events:
        return events

    first = events[0]
    previous_asn = None
    for event in events:
        if event["trading_day"] != first["trading_day"]:
            raise DemoError(
                "%s: demo supports one trading day only" % event["location"]
            )
        if event["channel"] != first["channel"]:
            raise DemoError("%s: demo supports one channel only" % event["location"])
        if (
            event["security_id"] != first["security_id"]
            or event["secid"] != first["secid"]
        ):
            raise DemoError("%s: demo supports one security only" % event["location"])

        if previous_asn is not None:
            if event["asn"] == previous_asn:
                raise DemoError(
                    "%s: duplicate ApplSeqNum %d"
                    % (event["location"], event["asn"])
                )
            # ASN 在整个频道内编号；筛出单证券后，中间序号可能属于其他证券。
            # 因此这里只拒绝重复 ASN，不把单证券文件中的跳号判成行情丢失。
        previous_asn = event["asn"]

    return events


class OrderBookDemo:
    """One instrument's live orders, full-depth levels, and trade statistics."""

    def __init__(self):
        # orders keeps order-level state needed by later trade and cancel references.
        self.orders = {}

        # Levels aggregate all live order quantities at the same side and price.
        self.bid_levels = {}
        self.ask_levels = {}

        self.num_trades = 0
        self.traded_volume = 0
        self.turnover = Decimal("0")
        self.last_price = None
        self.open_price = None

    def apply(self, event):
        if event["event_type"] == "add":
            self._apply_add(event)
        elif event["event_type"] == "cancel":
            self._apply_cancel(event)
        else:
            self._apply_trade(event)

        self._validate_invariants(event)
        return self._make_snapshot(event)

    def _apply_add(self, event):
        order_key = event["order_key"]
        if order_key in self.orders:
            raise DemoError("%s: duplicate live order id" % event["location"])

        self.orders[order_key] = {
            "side": event["side"],
            "price": event["price"],
            "remaining": event["quantity"],
        }

        levels = self.bid_levels if event["side"] == "buy" else self.ask_levels
        levels[event["price"]] = levels.get(event["price"], 0) + event["quantity"]

    def _validate_reduction(self, event, order_key, expected_side):
        if order_key not in self.orders:
            raise DemoError(
                "%s: event references an unknown live order" % event["location"]
            )

        order = self.orders[order_key]
        if order["side"] != expected_side:
            raise DemoError(
                "%s: referenced order has the wrong side" % event["location"]
            )
        if event["quantity"] > order["remaining"]:
            raise DemoError(
                "%s: quantity %d exceeds remaining order quantity %d"
                % (event["location"], event["quantity"], order["remaining"])
            )
        return order

    def _apply_cancel(self, event):
        self._validate_reduction(event, event["order_key"], event["side"])
        self._reduce_order(event["order_key"], event["quantity"])

    def _apply_trade(self, event):
        if event["bid_order_key"] == event["ask_order_key"]:
            raise DemoError(
                "%s: trade references the same order twice" % event["location"]
            )

        # Validate both sides first. A bad ask must not leave the bid partially changed.
        self._validate_reduction(event, event["bid_order_key"], "buy")
        self._validate_reduction(event, event["ask_order_key"], "sell")

        self._reduce_order(event["bid_order_key"], event["quantity"])
        self._reduce_order(event["ask_order_key"], event["quantity"])

        self.num_trades += 1
        self.traded_volume += event["quantity"]
        self.turnover += event["trade_price"] * event["quantity"]
        self.last_price = event["trade_price"]
        if self.open_price is None:
            self.open_price = event["trade_price"]

    def _reduce_order(self, order_key, quantity):
        order = self.orders[order_key]
        levels = self.bid_levels if order["side"] == "buy" else self.ask_levels

        order["remaining"] -= quantity
        levels[order["price"]] -= quantity

        if order["remaining"] == 0:
            del self.orders[order_key]
        if levels[order["price"]] == 0:
            del levels[order["price"]]

    def _validate_invariants(self, event):
        """Recompute every level from live orders; simple and ideal for a demo."""
        expected_bids = {}
        expected_asks = {}
        for order in self.orders.values():
            if order["remaining"] <= 0:
                raise DemoError(
                    "%s: live order has non-positive quantity" % event["location"]
                )
            levels = expected_bids if order["side"] == "buy" else expected_asks
            levels[order["price"]] = levels.get(order["price"], 0) + order["remaining"]

        if expected_bids != self.bid_levels:
            raise DemoError(
                "%s: internal bid-level invariant failed" % event["location"]
            )
        if expected_asks != self.ask_levels:
            raise DemoError(
                "%s: internal ask-level invariant failed" % event["location"]
            )

    @staticmethod
    def _format_price(value):
        return "" if value is None else format(value, ".4f")

    @staticmethod
    def _price_cell(prices, index):
        return "" if index >= len(prices) else format(prices[index], ".4f")

    @staticmethod
    def _quantity_cell(prices, levels, index):
        return "" if index >= len(prices) else str(levels[prices[index]])

    def _make_snapshot(self, event):
        # Full depth stays in the dictionaries; only this projection takes five levels.
        bid_prices = sorted(self.bid_levels, reverse=True)[:5]
        ask_prices = sorted(self.ask_levels)[:5]

        bid_output_order = (4, 3, 2, 1, 0)
        ask_output_order = (0, 1, 2, 3, 4)

        row = [
            event["clock_at_arrival"],
            event["secid"],
            event["sequence_no"],
            str(event["asn"]),
            event["transact_time"],
            str(self.num_trades),
            str(self.traded_volume),
            format(self.turnover, ".4f"),
            self._format_price(self.last_price),
            self._format_price(self.open_price),
        ]
        row += [self._price_cell(bid_prices, index) for index in bid_output_order]
        row += [self._price_cell(ask_prices, index) for index in ask_output_order]
        row += [
            self._quantity_cell(bid_prices, self.bid_levels, index)
            for index in bid_output_order
        ]
        row += [
            self._quantity_cell(ask_prices, self.ask_levels, index)
            for index in ask_output_order
        ]
        return row


def validate_output_path(order_path, trade_path, output_path, overwrite):
    if output_path.resolve() in (order_path.resolve(), trade_path.resolve()):
        raise DemoError("output path would overwrite an input file: %s" % output_path)
    if output_path.exists() and not overwrite:
        raise DemoError(
            "output already exists: %s (use --overwrite to replace it)" % output_path
        )


def write_book(path, rows):
    """Write through a temporary file so a failed write does not leave a partial CSV."""
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
            frame = pd.DataFrame(rows, columns=BOOK_HEADER)
            frame.to_csv(output_file, index=False, lineterminator="\n")
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(str(temporary_path), str(path))
    except OSError as error:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        raise DemoError("cannot write %s: %s" % (path, error))


def main():
    args = parse_args()
    try:
        validate_output_path(args.order, args.trade, args.output, args.overwrite)
        events = load_events(args.order, args.trade)

        book = OrderBookDemo()
        output_rows = [book.apply(event) for event in events]

        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_book(args.output, output_rows)
        print("reconstructed %d events -> %s" % (len(events), args.output))
    except (DemoError, OSError, UnicodeError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
