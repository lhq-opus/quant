#!/usr/bin/env python3
"""按到达时间重放 order 和撤单事件，并输出每个事件后的五档订单簿。"""

import argparse
from decimal import Decimal
from pathlib import Path

import pandas as pd


# event.csv 的列由 build_cancel_event_csv.py 固定生成。
# 第一版直接使用这份确定的结构，不猜测列名，也不兼容其他表头。
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

# 输出按“买一价、买一量……卖五价、卖五量”的顺序展开。
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


def parse_args():
    """读取命令行参数。"""
    parser = argparse.ArgumentParser(
        description="重放 event.csv 中的 order 和撤单，并输出逐事件五档订单簿。"
    )
    parser.add_argument("--event", required=True, type=Path, help="输入 event.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("book.csv"),
        help="输出订单簿路径，默认是当前目录下的 book.csv",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="允许覆盖已有输出文件，但不能覆盖输入文件",
    )
    return parser.parse_args()


def read_events(path):
    """按照固定表头读取事件，并按 caa 稳定排序。"""
    events = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        encoding="utf-8-sig",
    )

    # 直接选取约定的八列。输入契约保证列名和数据合法，因此这里不再猜测表头、
    # 检查多种格式或捕获并改写 pandas 的异常。
    events = events.loc[:, EVENT_HEADER]

    # caa 使用固定、可按字符串排序的时间格式。stable 保证相同 caa 的原始次序不变。
    return events.sort_values("caa", kind="stable").reset_index(drop=True)


class EventOrderBook:
    """维护全深度聚合盘口，并在价格档层面处理可成交数量。"""

    def __init__(self):
        # bids 和 asks 都是“价格 -> 当前聚合数量”。
        # 订单簿只需要价格档总量，因此不为同价订单维护 FIFO 队列。
        self.bids = {}
        self.asks = {}

        # 价格档撮合能够确定成交总量和成交额，但不能确定实际成交消息笔数。
        # 这两个累计值供后续完整 book.csv 的 cvl、cto 字段使用。
        self.cumulative_trade_quantity = 0
        self.cumulative_turnover = Decimal("0")

        # 保存当前 order 在各价格档推导出的成交量和成交额，便于观察单条事件的结果。
        # 撤单不会产生成交，因此应用每个新事件前都重置为 0。
        self.event_trade_quantity = 0
        self.event_turnover = Decimal("0")

    def apply(self, event):
        """应用一条事件，并立即生成与该事件 caa 对应的订单簿快照。"""
        self.event_trade_quantity = 0
        self.event_turnover = Decimal("0")

        if event.ExecType == "4":
            self._apply_cancel(event)
            event_type = "cancel"
        else:
            self._apply_order(event)
            event_type = "order"

        # 每个输入事件只生成一行输出，且 caa 原样取自当前事件。
        return self._snapshot(event.caa, event_type)

    def _apply_order(self, event):
        """按价格优先逐档消耗对手盘，再把未成交数量加入本方盘口。"""
        limit_price = Decimal(event.Price)
        remaining_quantity = int(event.OrderQty)

        if event.Side == "1":
            # 买单从最低卖价开始成交。只要卖一不高于买入限价，就继续看下一卖价。
            while remaining_quantity > 0 and self.asks:
                best_ask_price = min(self.asks)
                if best_ask_price > limit_price:
                    break

                traded_quantity = min(
                    remaining_quantity,
                    self.asks[best_ask_price],
                )
                self._record_trade(best_ask_price, traded_quantity)

                remaining_quantity -= traded_quantity
                self.asks[best_ask_price] -= traded_quantity
                if self.asks[best_ask_price] == 0:
                    del self.asks[best_ask_price]

            # 买单仍有剩余，说明剩余数量无法继续成交，应进入买盘的委托价格档。
            if remaining_quantity > 0:
                self.bids[limit_price] = (
                    self.bids.get(limit_price, 0) + remaining_quantity
                )
            return

        # 卖单与买单完全对称：从最高买价开始成交，再依次查看买二、买三。
        while remaining_quantity > 0 and self.bids:
            best_bid_price = max(self.bids)
            if best_bid_price < limit_price:
                break

            traded_quantity = min(
                remaining_quantity,
                self.bids[best_bid_price],
            )
            self._record_trade(best_bid_price, traded_quantity)

            remaining_quantity -= traded_quantity
            self.bids[best_bid_price] -= traded_quantity
            if self.bids[best_bid_price] == 0:
                del self.bids[best_bid_price]

        # 卖单仍有剩余时，把剩余数量加入卖盘的委托价格档。
        if remaining_quantity > 0:
            self.asks[limit_price] = (
                self.asks.get(limit_price, 0) + remaining_quantity
            )

    def _record_trade(self, trade_price, trade_quantity):
        """累计一次价格档消耗产生的成交量和成交额。"""
        trade_turnover = trade_price * trade_quantity

        self.event_trade_quantity += trade_quantity
        self.event_turnover += trade_turnover
        self.cumulative_trade_quantity += trade_quantity
        self.cumulative_turnover += trade_turnover

    def _apply_cancel(self, event):
        """从撤单价格所在的一侧扣减聚合数量。"""
        price = Decimal(event.TradePrice)
        quantity = int(event.TradeQty)

        # build_cancel_event_csv.py 已经用原始订单引用补全了撤单价格。
        # 第一版输入保证该价格能够唯一定位到买盘或卖盘，因此无需订单级 FIFO，
        # 只需修改对应价格档的聚合数量。
        levels = self.bids if price in self.bids else self.asks
        levels[price] -= quantity

        # 一个价格档被完全撤空后，不应继续出现在订单簿中。
        if levels[price] == 0:
            del levels[price]

    @staticmethod
    def _format_level(prices, levels, index):
        """把指定档位格式化为四位小数价格和整数数量。"""
        if index >= len(prices):
            return "", ""

        price = prices[index]
        return format(price, ".4f"), str(levels[price])

    def _snapshot(self, caa, event_type):
        """从全深度买卖盘截取前五档。"""
        # 买盘价格越高越优，卖盘价格越低越优。
        bid_prices = sorted(self.bids, reverse=True)[:5]
        ask_prices = sorted(self.asks)[:5]

        row = [caa, event_type]
        for index in range(5):
            row.extend(self._format_level(bid_prices, self.bids, index))
        for index in range(5):
            row.extend(self._format_level(ask_prices, self.asks, index))
        return row


def validate_output_path(event_path, output_path, overwrite):
    """避免误覆盖输入文件，并要求显式允许覆盖已有输出。"""
    if output_path.resolve() == event_path.resolve():
        raise ValueError("输出路径不能覆盖输入 event.csv")
    if output_path.exists() and not overwrite:
        raise FileExistsError("输出文件已存在；如需覆盖请添加 --overwrite")


def main():
    """执行完整的读取、重放和输出流程。"""
    args = parse_args()
    validate_output_path(args.event, args.output, args.overwrite)

    events = read_events(args.event)
    order_book = EventOrderBook()

    # itertuples 比逐行 Series 更直接；一条输入事件严格对应一条输出快照。
    rows = [order_book.apply(event) for event in events.itertuples(index=False)]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=BOOK_HEADER).to_csv(
        args.output,
        index=False,
        lineterminator="\n",
    )

    print(
        "已重放 %d 条事件，推导成交量 %d，推导成交额 %s，输出 %s"
        % (
            len(rows),
            order_book.cumulative_trade_quantity,
            format(order_book.cumulative_turnover, ".4f"),
            args.output,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
