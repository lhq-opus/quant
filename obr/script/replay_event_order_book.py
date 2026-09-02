#!/usr/bin/env python3
"""Replay event.csv with limit-order price priority and FIFO time priority."""

import argparse
import os
import sys
import tempfile
from collections import deque
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


EVENT_HEADER = [
    "caa",
    "Side",
    "OrderType",
    "Price",
    "OrderQty",
    "ExecType",
    "TradeQty",
    "TradePrice",
]

BOOK_HEADER = [
    "caa",
    "event_type",
    "bp1",
    "bs1",
    "bp2",
    "bs2",
    "bp3",
    "bs3",
    "bp4",
    "bs4",
    "bp5",
    "bs5",
    "ap1",
    "as1",
    "ap2",
    "as2",
    "ap3",
    "as3",
    "ap4",
    "as4",
    "ap5",
    "as5",
]

FOUR_DECIMAL_PLACES = Decimal("0.0001")


class ReplayError(Exception):
    """An expected input or replay error shown without a Python traceback."""


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Replay event.csv using limit-order price priority and FIFO time "
            "priority, then write one five-level snapshot per event."
        )
    )
    parser.add_argument("--event", required=True, type=Path, help="Input event.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("book.csv"),
        help="Output snapshot CSV path (default: ./book.csv)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output, but never the input file",
    )
    return parser.parse_args()


def read_event_csv(path):
    """Use pandas while keeping text, duplicate headers, and short rows visible."""
    try:
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
        raise ReplayError("%s: CSV file is empty" % path)
    except pd.errors.ParserError as error:
        raise ReplayError("%s: malformed CSV data: %s" % (path, error))
    except OSError as error:
        raise ReplayError("cannot open %s: %s" % (path, error))

    actual_header = [
        "" if pd.isna(value) else str(value) for value in raw_frame.iloc[0]
    ]
    if actual_header != EVENT_HEADER:
        raise ReplayError(
            "%s: unexpected event header\nexpected: %s\nactual:   %s"
            % (path, ",".join(EVENT_HEADER), ",".join(actual_header))
        )

    frame = raw_frame.iloc[1:].reset_index(drop=True)
    missing_rows = frame.isna().any(axis=1)
    if missing_rows.any():
        row_index = missing_rows[missing_rows].index[0]
        actual_columns = int(frame.loc[row_index].notna().sum())
        raise ReplayError(
            "%s:%d: expected %d columns, found %d"
            % (path, row_index + 2, len(EVENT_HEADER), actual_columns)
        )

    frame.columns = actual_header
    frame["__line_number"] = frame.index + 2
    if frame.empty:
        return frame
    if (frame["caa"] == "").any():
        row_index = frame.loc[frame["caa"] == ""].index[0]
        raise ReplayError("%s:%d column caa: value is empty" % (path, row_index + 2))

    try:
        frame["__sort_time"] = pd.to_datetime(
            frame["caa"], format="ISO8601", errors="raise", utc=True
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise ReplayError(
            "%s: cannot parse caa as ISO 8601 timestamp: %s" % (path, error)
        )

    frame = frame.sort_values("__sort_time", kind="stable")
    return frame.drop(columns="__sort_time").reset_index(drop=True)


def require_non_empty(row, fields, path, line_number):
    for field in fields:
        if row[field] == "":
            raise ReplayError(
                "%s:%d column %s: value is empty" % (path, line_number, field)
            )


def require_empty(row, fields, path, line_number):
    for field in fields:
        if row[field] != "":
            raise ReplayError(
                "%s:%d column %s: value must be empty for this event"
                % (path, line_number, field)
            )


def parse_price(raw_value, field, path, line_number):
    try:
        price = Decimal(raw_value)
        rounded = price.quantize(FOUR_DECIMAL_PLACES)
    except InvalidOperation:
        raise ReplayError(
            "%s:%d column %s: invalid price %r"
            % (path, line_number, field, raw_value)
        )
    if not price.is_finite() or price <= 0:
        raise ReplayError(
            "%s:%d column %s: price must be positive and finite"
            % (path, line_number, field)
        )
    if rounded != price:
        raise ReplayError(
            "%s:%d column %s: price has more than four decimal places"
            % (path, line_number, field)
        )
    return price


def parse_quantity(raw_value, field, path, line_number):
    try:
        quantity = int(raw_value)
    except ValueError:
        raise ReplayError(
            "%s:%d column %s: invalid integer quantity %r"
            % (path, line_number, field, raw_value)
        )
    if quantity <= 0:
        raise ReplayError(
            "%s:%d column %s: quantity must be positive"
            % (path, line_number, field)
        )
    return quantity


def normalize_events(frame, path):
    """Classify each row as one complete order or one complete cancellation."""
    events = []
    order_fields = ["Side", "OrderType", "Price", "OrderQty"]
    cancel_fields = ["ExecType", "TradeQty", "TradePrice"]

    for _, row in frame.iterrows():
        line_number = int(row["__line_number"])
        has_order_data = any(row[field] != "" for field in order_fields)
        has_cancel_data = any(row[field] != "" for field in cancel_fields)
        if has_order_data == has_cancel_data:
            raise ReplayError(
                "%s:%d: row must contain exactly one order or cancellation event"
                % (path, line_number)
            )

        if has_order_data:
            require_non_empty(row, order_fields, path, line_number)
            require_empty(row, cancel_fields, path, line_number)
            if row["Side"] not in ("1", "2"):
                raise ReplayError(
                    "%s:%d column Side: expected 1 (buy) or 2 (sell)"
                    % (path, line_number)
                )
            if row["OrderType"] != "2":
                raise ReplayError(
                    "%s:%d column OrderType: demo supports limit orders (2) only"
                    % (path, line_number)
                )
            events.append(
                {
                    "location": "%s:%d" % (path, line_number),
                    "caa": row["caa"],
                    "event_type": "order",
                    "side": "buy" if row["Side"] == "1" else "sell",
                    "price": parse_price(row["Price"], "Price", path, line_number),
                    "quantity": parse_quantity(
                        row["OrderQty"], "OrderQty", path, line_number
                    ),
                }
            )
            continue

        require_empty(row, order_fields, path, line_number)
        require_non_empty(row, cancel_fields, path, line_number)
        if row["ExecType"] != "4":
            raise ReplayError(
                "%s:%d column ExecType: expected cancellation value 4"
                % (path, line_number)
            )
        events.append(
            {
                "location": "%s:%d" % (path, line_number),
                "caa": row["caa"],
                "event_type": "cancel",
                "price": parse_price(
                    row["TradePrice"], "TradePrice", path, line_number
                ),
                "quantity": parse_quantity(
                    row["TradeQty"], "TradeQty", path, line_number
                ),
            }
        )

    return events


class PriceTimeOrderBook:
    """Full-depth price levels whose per-price deques preserve arrival order."""

    def __init__(self):
        self.bids = {}
        self.asks = {}

    @staticmethod
    def _level_quantity(levels, price):
        return sum(levels[price])

    @staticmethod
    def _consume_fifo(levels, price, quantity):
        """Consume at most quantity and return the part that was not consumed."""
        orders = levels[price]
        remaining = quantity
        while remaining > 0 and orders:
            first_quantity = orders[0]
            consumed = min(remaining, first_quantity)
            remaining -= consumed
            first_quantity -= consumed
            if first_quantity == 0:
                orders.popleft()
            else:
                orders[0] = first_quantity

        if not orders:
            del levels[price]
        return remaining

    def apply(self, event):
        if event["event_type"] == "order":
            self._apply_order(event)
        else:
            self._apply_cancel(event)
        self._validate_invariants(event)
        return self._snapshot(event)

    def _apply_order(self, event):
        side = event["side"]
        limit_price = event["price"]
        remaining = event["quantity"]

        opposite = self.asks if side == "buy" else self.bids
        while remaining > 0 and opposite:
            best_opposite_price = min(opposite) if side == "buy" else max(opposite)
            can_trade = (
                limit_price >= best_opposite_price
                if side == "buy"
                else limit_price <= best_opposite_price
            )
            if not can_trade:
                break
            remaining = self._consume_fifo(
                opposite, best_opposite_price, remaining
            )

        if remaining > 0:
            own_side = self.bids if side == "buy" else self.asks
            if limit_price not in own_side:
                own_side[limit_price] = deque()
            own_side[limit_price].append(remaining)

    def _apply_cancel(self, event):
        price = event["price"]
        quantity = event["quantity"]
        in_bids = price in self.bids
        in_asks = price in self.asks

        if in_bids == in_asks:
            description = "both sides" if in_bids else "neither side"
            raise ReplayError(
                "%s: cancellation price is present on %s"
                % (event["location"], description)
            )

        levels = self.bids if in_bids else self.asks
        available = self._level_quantity(levels, price)
        if quantity > available:
            raise ReplayError(
                "%s: cancellation quantity %d exceeds level quantity %d"
                % (event["location"], quantity, available)
            )

        remaining = self._consume_fifo(levels, price, quantity)
        if remaining != 0:
            raise ReplayError("%s: internal cancellation error" % event["location"])

    def _validate_invariants(self, event):
        for side_name, levels in (("bid", self.bids), ("ask", self.asks)):
            for price, orders in levels.items():
                if not orders:
                    raise ReplayError(
                        "%s: internal %s level is empty"
                        % (event["location"], side_name)
                    )
                if price <= 0 or any(quantity <= 0 for quantity in orders):
                    raise ReplayError(
                        "%s: internal %s level has an invalid value"
                        % (event["location"], side_name)
                    )

        if self.bids and self.asks and max(self.bids) >= min(self.asks):
            raise ReplayError(
                "%s: crossed book remained after matching" % event["location"]
            )

    @staticmethod
    def _format_level(prices, levels, index):
        if index >= len(prices):
            return "", ""
        price = prices[index]
        return format(price, ".4f"), str(sum(levels[price]))

    def _snapshot(self, event):
        bid_prices = sorted(self.bids, reverse=True)[:5]
        ask_prices = sorted(self.asks)[:5]
        row = [event["caa"], event["event_type"]]
        for index in range(5):
            row.extend(self._format_level(bid_prices, self.bids, index))
        for index in range(5):
            row.extend(self._format_level(ask_prices, self.asks, index))
        return row


def validate_output_path(event_path, output_path, overwrite):
    if output_path.resolve() == event_path.resolve():
        raise ReplayError(
            "output path would overwrite the input file: %s" % output_path
        )
    if output_path.exists() and not overwrite:
        raise ReplayError(
            "output already exists: %s (use --overwrite to replace it)" % output_path
        )


def write_csv_atomically(path, rows):
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
        raise ReplayError("cannot write %s: %s" % (path, error))


def main():
    args = parse_args()
    try:
        validate_output_path(args.event, args.output, args.overwrite)
        frame = read_event_csv(args.event)
        events = normalize_events(frame, args.event)

        book = PriceTimeOrderBook()
        rows = [book.apply(event) for event in events]

        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_csv_atomically(args.output, rows)
        print("replayed %d events -> %s" % (len(events), args.output))
    except (ReplayError, OSError, UnicodeError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
