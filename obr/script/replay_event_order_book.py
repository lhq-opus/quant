#!/usr/bin/env python3
"""按到达时间重放开盘集合、连续和收盘集合竞价事件。"""

import argparse
from decimal import Decimal
from pathlib import Path

import pandas as pd

# event.csv 使用约定好的固定结构，TransactionTime 由上游额外带入。
# 第一版直接使用这份确定的结构，不猜测列名，也不兼容其他表头。
EVENT_HEADER = [
    "caa",
    "TransactionTime",
    "Side",
    "OrderType",
    "Price",
    "OrderQty",
    "ExecType",
    "TradeQty",
    "TradePrice",
]

# 深市股票三个竞价阶段。TransactionTime 左补零后是 HHMMSSmmm，
# 判断阶段只需要前六位 HHMMSS。
OPENING_AUCTION = "opening_auction"
CONTINUOUS_AUCTION = "continuous_auction"
CLOSING_AUCTION = "closing_auction"

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

    # 直接选取约定的九列。输入契约保证列名和数据合法，因此这里不再猜测表头、
    # 检查多种格式或捕获并改写 pandas 的异常。
    events = events.loc[:, EVENT_HEADER]

    # caa 使用固定、可按字符串排序的时间格式。stable 保证相同 caa 的原始次序不变。
    return events.sort_values("caa", kind="stable").reset_index(drop=True)


def trading_session(transaction_time):
    """根据 HHMMSSmmm 形式的 TransactionTime 判断竞价阶段。"""
    # 例如 91500790 左补零后是 091500790，前六位表示 09:15:00。
    hhmmss = int(str(transaction_time).zfill(9)[:6])

    if 91500 <= hhmmss <= 92500:
        return OPENING_AUCTION
    if 93000 <= hhmmss <= 113000 or 130000 <= hhmmss < 145700:
        return CONTINUOUS_AUCTION
    if 145700 <= hhmmss <= 150000:
        return CLOSING_AUCTION

    # 本脚本约定输入都是合法交易时段；这一行只避免意外时静默分错阶段。
    raise ValueError("TransactionTime 不在股票竞价交易时段内")


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

    def apply(self, event, session):
        """应用一条事件；连续竞价立即撮合，集合竞价只把订单放入盘口。"""
        self.event_trade_quantity = 0
        self.event_turnover = Decimal("0")

        if event.ExecType == "4":
            self._apply_cancel(event)
            event_type = "cancel"
        elif session == CONTINUOUS_AUCTION:
            self._apply_continuous_order(event)
            event_type = "order"
        else:
            self._add_order_to_book(event)
            event_type = "order"

        return event_type

    def _add_order_to_book(self, event):
        """集合竞价期间不逐笔撮合，只累计到订单自己的买卖价格档。"""
        price = Decimal(event.Price)
        quantity = int(event.OrderQty)
        levels = self.bids if event.Side == "1" else self.asks
        levels[price] = levels.get(price, 0) + quantity

    def _apply_continuous_order(self, event):
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
            self.asks[limit_price] = self.asks.get(limit_price, 0) + remaining_quantity

    def _record_trade(self, trade_price, trade_quantity):
        """累计一次价格档消耗产生的成交量和成交额。"""
        trade_turnover = trade_price * trade_quantity

        self.event_trade_quantity += trade_quantity
        self.event_turnover += trade_turnover
        self.cumulative_trade_quantity += trade_quantity
        self.cumulative_turnover += trade_turnover

    def finish_call_auction(self):
        """在开盘或收盘集合竞价结束时，以一个成交价统一撮合。"""
        auction_price, trade_quantity = self._find_call_auction_result()
        if auction_price is None:
            return

        # 买方从最高价开始、卖方从最低价开始扣减，体现价格优先。
        bid_prices = sorted(
            (price for price in self.bids if price >= auction_price), reverse=True
        )
        ask_prices = sorted(price for price in self.asks if price <= auction_price)
        self._reduce_levels(self.bids, bid_prices, trade_quantity)
        self._reduce_levels(self.asks, ask_prices, trade_quantity)
        self._record_trade(auction_price, trade_quantity)

    def _find_call_auction_result(self):
        """根据当前买卖盘口选择集合竞价成交价和最大成交量。"""
        # 候选价格来自当前买卖申报价格的并集。
        # 为了让规则一眼可见，demo 对每个价格直接重新求和，不做前缀和优化。
        prices = sorted(set(self.bids) | set(self.asks))
        candidates = []

        for price in prices:
            buy_quantity = sum(
                quantity
                for bid_price, quantity in self.bids.items()
                if bid_price >= price
            )
            sell_quantity = sum(
                quantity
                for ask_price, quantity in self.asks.items()
                if ask_price <= price
            )
            trade_quantity = min(buy_quantity, sell_quantity)
            if trade_quantity == 0:
                continue

            # 严格优于候选价的买卖申报必须全部成交。
            better_buy_quantity = sum(
                quantity
                for bid_price, quantity in self.bids.items()
                if bid_price > price
            )
            better_sell_quantity = sum(
                quantity
                for ask_price, quantity in self.asks.items()
                if ask_price < price
            )
            if (
                better_buy_quantity > trade_quantity
                or better_sell_quantity > trade_quantity
            ):
                continue

            # 候选价上的买方或卖方，至少有一方必须能够全部成交。
            # 某一侧在候选价没有申报时，该侧数量为 0，也自然属于“全部成交”。
            buy_at_price = self.bids.get(price, 0)
            sell_at_price = self.asks.get(price, 0)
            all_buys_at_price_trade = (
                better_buy_quantity + buy_at_price <= trade_quantity
            )
            all_sells_at_price_trade = (
                better_sell_quantity + sell_at_price <= trade_quantity
            )
            if not all_buys_at_price_trade and not all_sells_at_price_trade:
                continue

            # 第二层并列规则比较“严格高价买量”和“严格低价卖量”的差。
            quantity_difference = abs(better_buy_quantity - better_sell_quantity)
            candidates.append((price, trade_quantity, quantity_difference))

        if not candidates:
            return None, 0

        maximum_trade_quantity = max(item[1] for item in candidates)
        candidates = [item for item in candidates if item[1] == maximum_trade_quantity]

        minimum_difference = min(item[2] for item in candidates)
        candidates = [item for item in candidates if item[2] == minimum_difference]

        # demo 约定：经过上述规则后，合法输入只剩一个候选价。
        # 因此开盘和收盘都直接使用订单簿算出的这个价格，不再引入参考价。
        assert len(candidates) == 1
        auction_price = candidates[0][0]
        return auction_price, maximum_trade_quantity

    @staticmethod
    def _reduce_levels(levels, prices, trade_quantity):
        """按已经排好的价格优先顺序，从一侧盘口扣除集合竞价成交量。"""
        quantity_left = trade_quantity
        for price in prices:
            reduced_quantity = min(quantity_left, levels[price])
            levels[price] -= reduced_quantity
            quantity_left -= reduced_quantity

            if levels[price] == 0:
                del levels[price]
            if quantity_left == 0:
                break

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

    def snapshot(self, caa, event_type):
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

    # 先算出每条事件的阶段，便于识别一段集合竞价中的最后一条事件。
    event_rows = list(events.itertuples(index=False))
    sessions = [trading_session(event.TransactionTime) for event in event_rows]
    rows = []

    for index, event in enumerate(event_rows):
        session = sessions[index]
        event_type = order_book.apply(event, session)

        # 集合竞价最后一条输入处理完后统一撮合，再生成这条事件对应的快照。
        # 这样不额外制造 event，输出行数仍与输入行数相同。
        next_session = sessions[index + 1] if index + 1 < len(sessions) else None
        if session in (OPENING_AUCTION, CLOSING_AUCTION) and next_session != session:
            order_book.finish_call_auction()

        rows.append(order_book.snapshot(event.caa, event_type))

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
