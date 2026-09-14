"""从同目录 data.csv 的 stock_id,snapshot_id 两列恢复固定递增组。

输入由用户保证准确；使用 pandas 读取，保留每个 snapshot 的原始股票顺序。
输出同目录 stock_groups.csv，只有 stock_id,group_id 两列。
"""

from pathlib import Path

import pandas as pd

INPUT_CSV = Path(__file__).with_name("data.csv")
OUTPUT_CSV = Path(__file__).with_name("stock_groups.csv")


def mask_members(mask: int):
    """整数的第 i 位代表股票 i；逐次取出最低的非零位，避免遍历空位。"""
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def build_conflicts(data: pd.DataFrame, stock_count: int):
    """汇总所有逆序对，复杂度主要随记录数及不同冲突对数量增长。

    股票索引按真实 ID 升序排列。seen 的第 i 位表示本轮已见股票 i。
    右移再左移会清空小于等于当前股票的位，留下之前出现过的较大 ID。
    整数位集合可一次处理这些逆序，避免逐轮枚举数百万股票对。
    """
    upper = [0] * stock_count
    # sort=False 保持 snapshot 首次出现的顺序，组内记录也保持输入原序。
    for _, stocks in data.groupby("snapshot_id", sort=False)["stock_index"]:
        seen = 0
        for stock in stocks.tolist():
            upper[stock] |= (seen >> (stock + 1)) << (stock + 1)
            seen |= 1 << stock

    adjacency = upper.copy()
    for stock, neighbors in enumerate(upper):
        for other in mask_members(neighbors):
            adjacency[other] |= 1 << stock
    return adjacency


def color_conflicts(adjacency: list[int]):
    """DSATUR 贪心：优先分配已经接触最多不同组的股票。

    每次选择禁用组最多的股票，同分时选冲突邻居更多、ID 更小的股票。
    分配最小可用组号，并把该组加入未分配邻居的禁用组集合。
    该方法保证冲突股票不在同组，但贪心结果不一般性保证组数最少。
    """
    count = len(adjacency)
    colors = [-1] * count
    degrees = [neighbors.bit_count() for neighbors in adjacency]
    forbidden = [0] * count
    remaining = set(range(count))
    while remaining:
        stock = max(
            remaining,
            key=lambda value: (forbidden[value].bit_count(), degrees[value], -value),
        )
        color = 0
        while forbidden[stock] & (1 << color):
            color += 1
        colors[stock] = color
        remaining.remove(stock)
        for other in mask_members(adjacency[stock]):
            if colors[other] < 0:
                forbidden[other] |= 1 << color

    # 组号只是标签，按每组最小 stock_id 排成 1、2、……，便于稳定复现。
    color_order = sorted(set(colors), key=colors.index)
    labels = {color: index + 1 for index, color in enumerate(color_order)}
    return [labels[color] for color in colors]


def main():
    data = pd.read_csv(
        INPUT_CSV,
        encoding="utf-8",
        dtype={"stock_id": "int64", "snapshot_id": "int64"},
    )
    # factorize 为每股建立整数索引。sort=True 只将股票字典按数值排序，
    # 不改变 data 的行顺序，所以索引大小仍能表达真实 stock_id 的大小。
    data["stock_index"], stock_ids = pd.factorize(data["stock_id"], sort=True)
    stock_ids = stock_ids.tolist()
    adjacency = build_conflicts(data, len(stock_ids))
    groups = color_conflicts(adjacency)
    mapping = pd.DataFrame({"stock_id": stock_ids, "group_id": groups})
    mapping.to_csv(OUTPUT_CSV, index=False, encoding="utf-8", lineterminator="\n")


if __name__ == "__main__":
    main()
