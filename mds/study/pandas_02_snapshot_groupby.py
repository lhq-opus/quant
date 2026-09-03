"""第二课：排序、groupby、diff、布尔掩码和 cumsum。

运行方式（先进入 ``quant/`` 目录）：

    python -m mds.study.pandas_02_snapshot_groupby

本课复刻 MDS 当前 baseline 的核心 pandas 操作，但输出只表示 snapshot 内的
候选局部分组，不能把一次局部时间簇当成全天固定股票组。
"""

from __future__ import annotations

import pandas as pd

from .pandas_01_io_selection import load_example_market_data


def add_snapshot_deltas_and_groups(
    data: pd.DataFrame,
    threshold: int = 1_000,
) -> pd.DataFrame:
    """在每个 time 内按 clock 排序、计算 gap，并产生候选局部组号。"""

    # sort=False 让 snapshot 按它们首次出现在输入中的顺序迭代；每个 snapshot
    # 再单独按 clock 排序。kind="stable" 表示 clock 相等时保留原行顺序，
    # 使结果可复现。最后用 concat 把各 snapshot 放回一张记录级表。
    ordered_parts = [
        snapshot.sort_values("clock", kind="stable")
        for _, snapshot in data.groupby("time", sort=False)
    ]
    ordered = pd.concat(ordered_parts, ignore_index=True).copy()

    # 关键点：先 groupby("time")，再 diff()。这样每个 snapshot 的第一行
    # 都是 <NA>，不会错误地减去上一个 time 的最后一条 clock。
    #
    # diff 是 transformation：结果和原数据行数相同、索引对齐，所以能直接
    # 赋回 ordered。转成可空 Int64 后，第一行仍可保留缺失而不是变成小数。
    ordered["delta_clock"] = (
        ordered.groupby("time", sort=False)["clock"].diff().astype("Int64")
    )

    # 每个 snapshot 的第一行一定开启第 0 组；后续 gap >= threshold 时开新组。
    starts_new_group = ordered["delta_clock"].isna() | (
        ordered["delta_clock"].ge(threshold).fillna(False)
    )

    # 对 True/False 做 cumsum：False 不加，True 加 1。再次按 time 分组，保证
    # local_group_id 在每个 snapshot 都从 0 重新开始。
    ordered["local_group_id"] = (
        starts_new_group.groupby(ordered["time"], sort=False)
        .cumsum()
        .sub(1)
        .astype("int64")
    )

    # cumcount 是每组内从 0 开始的行号；transform("size") 把每个 snapshot
    # 的总行数广播回原来的每一行。二者都保持原索引，适合增加特征列。
    snapshot_group = ordered.groupby("time", sort=False)
    ordered["row_in_snapshot"] = snapshot_group.cumcount()
    ordered["snapshot_size"] = snapshot_group["stock_id"].transform("size")

    return ordered


def summarize_local_groups(grouped: pd.DataFrame) -> pd.DataFrame:
    """把记录级结果压缩成每个候选局部组一行。"""

    # agg 是 aggregation：多行被压缩成一行，所以结果行数通常会减少。
    # 下面叫“命名聚合”：新列名 = (来源列, 聚合函数)。
    summary = (
        grouped.groupby(["time", "local_group_id"], sort=False, as_index=False)
        .agg(
            record_count=("stock_id", "size"),
            unique_stock_count=("stock_id", "nunique"),
            first_clock=("clock", "min"),
            last_clock=("clock", "max"),
            # tuple 方便教学时直接看成员。全市场大数据中不要随意为每组
            # 物化 Python tuple；能用内置 count/min/max 就优先用内置聚合。
            stocks=("stock_id", lambda values: tuple(values.astype(str))),
        )
        .assign(clock_span=lambda frame: frame["last_clock"] - frame["first_clock"])
    )
    return summary


def compare_global_and_grouped_diff(data: pd.DataFrame) -> pd.DataFrame:
    """并排展示全局 diff 与按 time diff 的边界差异。"""

    ordered = data.sort_values(["time", "clock"], ignore_index=True).copy()
    ordered["wrong_global_delta"] = ordered["clock"].diff().astype("Int64")
    ordered["correct_snapshot_delta"] = (
        ordered.groupby("time", sort=False)["clock"].diff().astype("Int64")
    )
    return ordered[
        ["time", "stock_id", "clock", "wrong_global_delta", "correct_snapshot_delta"]
    ]


def describe_delta_distribution(grouped: pd.DataFrame) -> pd.Series:
    """用 pandas 描述 gap 分布，不把描述统计量直接当成业务阈值。"""

    deltas = grouped["delta_clock"].dropna().astype("int64")
    median = float(deltas.median())

    # sub -> abs -> median 正是 MAD 的 pandas 写法：先算每个值离中位数多远，
    # 再取这些距离的中位数。它适合描述稳健离散程度，但本项目的极端长尾
    # threshold 不能仅靠全局 MAD 决定；已有 baseline 的局限仍然成立。
    mad = float(deltas.sub(median).abs().median())

    # quantile 按排名位置给出分位数。p90=90% 数据不超过的值；它描述分布，
    # 但“90%”本身没有组内/组间含义，不能未经验证就作为分类阈值。
    return pd.Series(
        {
            "count": float(deltas.size),
            "median": median,
            "mad": mad,
            "p90": float(deltas.quantile(0.90)),
            "maximum": float(deltas.max()),
        }
    )


def main() -> int:
    data = load_example_market_data()
    grouped = add_snapshot_deltas_and_groups(data, threshold=1_000)
    summary = summarize_local_groups(grouped)
    delta_comparison = compare_global_and_grouped_diff(data)
    distribution = describe_delta_distribution(grouped)

    print("\n[1] 每条记录的 snapshot 内 gap 与候选局部组")
    print(grouped.to_string(index=False))

    print("\n[2] groupby + agg 得到的候选局部组摘要")
    print(summary.to_string(index=False))

    print("\n[3] 为什么不能直接对全天 clock 做 diff")
    boundary_rows = delta_comparison.loc[
        delta_comparison["correct_snapshot_delta"].isna()
    ]
    print(boundary_rows.to_string(index=False))

    print("\n[4] gap 的描述统计（不是自动 threshold）")
    print(distribution.to_string())

    print(
        "\n注意：local_group_id 只是记录级候选时间簇，"
        "不是隐藏 push_id，也不是最终固定 group_id。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
