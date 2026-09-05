#!/usr/bin/env python3
"""用固定结构的深交所 order/trade 生成价格档重放所需的 event.csv。

order 和撤单各生成一条事件；真实成交只提供集合竞价成交价，不生成扣量事件。
输入约定为单证券、单交易日的完整合法数据，不做列名猜测或其他格式兼容。
"""

import argparse
from pathlib import Path

import pandas as pd

EVENT_COLUMNS = [
    "caa",
    "TransactionTime",
    "Side",
    "OrderType",
    "Price",
    "OrderQty",
    "ExecType",
    "TradeQty",
    "TradePrice",
    "ChannelNo",
    "OrderApplSeqNum",
    "AuctionPrice",
]


def parse_args():
    """每个脚本可独立运行，只需要指定输入和输出路径。"""
    parser = argparse.ArgumentParser(
        description="合并 order 和撤单 trade，补全原订单引用及集合竞价成交价。"
    )
    parser.add_argument("--order", required=True, type=Path, help="输入 order.csv")
    parser.add_argument("--trade", required=True, type=Path, help="输入 trade.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("event.csv"),
        help="输出路径，默认 event.csv",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="允许覆盖已有输出，但不能覆盖输入文件"
    )
    return parser.parse_args()


def read_csv_as_strings(path):
    """所有列按字符串读取，保留证券代码、时间前导零和空字段。"""
    return pd.read_csv(
        path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8-sig"
    )


def fill_cancel_order_fields(order_frame, trade_frame):
    """按频道和原订单 ASN 查回撤单方向、原始价格和订单引用。"""
    order_index = {}
    fields = ["ChannelNo", "ApplSeqNum", "Price", "Side"]
    for channel, asn, price, side in order_frame[fields].itertuples(
        index=False, name=None
    ):
        order_index[(int(channel), int(asn))] = (price, side)

    # 合法的深市撤单只有一侧引用非零；不要把 trade 自己的 ASN 当成被撤订单 ASN。
    cancels = trade_frame.loc[trade_frame["ExecType"] == "4"].copy()
    prices, sides, order_asns = [], [], []
    fields = ["ChannelNo", "BidApplSeqNum", "OfferApplSeqNum"]
    for channel, bid_asn, offer_asn in cancels[fields].itertuples(
        index=False, name=None
    ):
        order_asn = bid_asn if int(bid_asn) != 0 else offer_asn
        price, side = order_index[(int(channel), int(order_asn))]
        prices.append(price)
        sides.append(side)
        order_asns.append(order_asn)

    # TradePrice 保留原始申报价，仅供查看。1/U 的原始 Price 可能是 0，真实挂单价
    # 必须由重放器在订单到达时计算并记住；撤单靠订单引用查该价格，不靠本列定位。
    cancels["TradePrice"] = prices
    cancels["Side"] = sides
    cancels["OrderApplSeqNum"] = order_asns
    return cancels


def build_events(order_frame, trade_frame):
    """生成固定十二列；保持 order/cancel 与输出事件的一一对应。"""
    cancels = fill_cancel_order_fields(order_frame, trade_frame)
    rename = {"clockAtArrival": "caa", "TransactTime": "TransactionTime"}
    orders = order_frame.rename(columns={**rename, "ApplSeqNum": "OrderApplSeqNum"})
    cancels = cancels.rename(columns=rename)
    events = pd.concat(
        [
            orders.reindex(columns=EVENT_COLUMNS, fill_value=""),
            cancels.reindex(columns=EVENT_COLUMNS, fill_value=""),
        ],
        ignore_index=True,
    )

    # 用户确认原始 TransactTime 固定为 HHMMSSmmm 数字，例如 91500790。
    # 只左补零成 091500790，不推测 ISO 字符串、时间单位或时区。
    events["TransactionTime"] = events["TransactionTime"].str.zfill(9)
    event_times = events["TransactionTime"].str[:6].astype(int)
    trade_times = trade_frame["TransactTime"].str.zfill(9).str[:6].astype(int)

    # 一次集合竞价的所有真实成交价格相同，开盘、收盘分别取各自的实际价格。
    # 把价格附在该阶段的事件上，供重放器阶段收尾时消除候选价并列。
    # 这是读取完整文件的离线处理，不能把它理解为盘中已知的未来价格。
    for begin, end in ((91500, 92500), (145700, 150000)):
        auction_trades = trade_frame.loc[
            (trade_frame["ExecType"] == "F") & trade_times.between(begin, end)
        ]
        if not auction_trades.empty:
            events.loc[event_times.between(begin, end), "AuctionPrice"] = (
                auction_trades.iloc[0]["TradePrice"]
            )

    # F 不生成事件，否则重放器自身的价格档撮合和真实成交会重复扣量。
    # 保持现有 CAA 稳定排序；本 demo 按用户约定不存在同 CAA 的业务顺序问题。
    return events.sort_values("caa", kind="stable").reset_index(drop=True)


def main():
    """读原始两表、合并事件、写文件；运行失败直接保留原始异常。"""
    args = parse_args()
    output_path = args.output.resolve()
    # 这两个检查保护用户文件，与输入格式兼容或非法行处理无关。
    if output_path in (args.order.resolve(), args.trade.resolve()):
        raise ValueError("输出路径不能与任一输入文件相同")
    if output_path.exists() and not args.overwrite:
        raise FileExistsError("输出文件已存在；如需覆盖，请使用 --overwrite")

    events = build_events(
        read_csv_as_strings(args.order), read_csv_as_strings(args.trade)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(output_path, index=False, encoding="utf-8")
    print("已写入 %d 条 order/撤单事件：%s" % (len(events), output_path))


if __name__ == "__main__":
    main()
