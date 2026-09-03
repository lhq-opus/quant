"""第三课：聚合、股票对统计、merge 和交叉表。

运行方式（先进入 ``quant/`` 目录）：

    python -m mds.study.pandas_03_aggregate_merge

这些统计量是为了学习 pandas。一次同局部组只是弱正证据，原始次数也没有
校正股票活跃度和偶然碰撞，不能直接当成最终同组结论。
"""

from __future__ import annotations

import pandas as pd

from .pandas_01_io_selection import load_example_market_data
from .pandas_02_snapshot_groupby import add_snapshot_deltas_and_groups


def aggregate_stock_activity(data: pd.DataFrame) -> pd.DataFrame:
    """用命名聚合统计每只股票的更新活跃度。"""

    activity = (
        data.groupby("stock_id", as_index=False, sort=True)
        .agg(
            record_count=("time", "size"),
            active_snapshot_count=("time", "nunique"),
            first_clock=("clock", "min"),
            last_clock=("clock", "max"),
        )
        .sort_values(
            ["record_count", "stock_id"],
            ascending=[False, True],
            ignore_index=True,
        )
    )
    return activity


def _unordered_pairs(
    membership: pd.DataFrame,
    join_columns: list[str],
) -> pd.DataFrame:
    """在相同 join_columns 内生成不重复的无序股票对。"""

    # DataFrame 和自己 merge 会得到同一块内的笛卡尔积。例如成员 a、b、c
    # 会产生 9 行：(a,a)、(a,b)…。随后只保留 stock_a < stock_b，正好留下
    # (a,b)、(a,c)、(b,c)，同时去掉自身配对和左右反向重复。
    pairs = membership.merge(
        membership,
        on=join_columns,
        how="inner",
        suffixes=("_a", "_b"),
        # 这里有意进行 many-to-many merge。写出 validate 是在说明预期，
        # 但它不会限制结果大小；大组仍会产生平方级数量的股票对。
        validate="many_to_many",
    )
    return pairs.loc[
        pairs["stock_id_a"].lt(pairs["stock_id_b"]),
        [*join_columns, "stock_id_a", "stock_id_b"],
    ]


def calculate_candidate_pair_scores(grouped: pd.DataFrame) -> pd.DataFrame:
    """统计共同出现机会和落在同一候选局部组的次数。"""

    # drop_duplicates 防止相同成员关系被意外重复计算。它不是对原始 market
    # data 的清洗规则，只是在构造“每只股票是否出现”这一集合型中间表。
    presence = grouped[["time", "stock_id"]].drop_duplicates()
    local_membership = grouped[["time", "local_group_id", "stock_id"]].drop_duplicates()

    # 共同出现在同一个 time，表示这对股票有一次可以比较 clock 的机会；
    # 它本身不是同组证据。
    opportunity_pairs = _unordered_pairs(presence, ["time"])
    opportunities = (
        opportunity_pairs.groupby(["stock_id_a", "stock_id_b"], sort=True)
        .size()
        .rename("common_snapshot_count")
        .reset_index()
    )

    # 同 time 且同 local_group_id 是一次候选近时间证据，仍可能由跨组偶然
    # 同时推送造成，因此只能跨很多 snapshot 汇总后继续建模。
    local_pairs = _unordered_pairs(
        local_membership,
        ["time", "local_group_id"],
    )
    same_group_counts = (
        local_pairs.groupby(["stock_id_a", "stock_id_b"], sort=True)
        .size()
        .rename("same_local_group_count")
        .reset_index()
    )

    # left merge 保留每一对有比较机会的股票。validate="one_to_one" 会检查
    # 两边键是否真的唯一，防止上游聚合遗漏导致行数悄悄膨胀。
    scores = opportunities.merge(
        same_group_counts,
        on=["stock_id_a", "stock_id_b"],
        how="left",
        validate="one_to_one",
    )
    scores["same_local_group_count"] = (
        scores["same_local_group_count"].fillna(0).astype("int64")
    )
    scores["same_local_group_fraction"] = (
        scores["same_local_group_count"] / scores["common_snapshot_count"]
    )
    return scores.sort_values(
        [
            "same_local_group_fraction",
            "common_snapshot_count",
            "stock_id_a",
            "stock_id_b",
        ],
        ascending=[False, False, True, True],
        ignore_index=True,
    )


def attach_example_group_mapping(data: pd.DataFrame) -> pd.DataFrame:
    """演示把 stock_id -> group_id 映射安全地连接回记录表。"""

    # 这是教学映射，不是真值。故意不放 000003，用来展示未分配股票。
    mapping = pd.DataFrame(
        {
            "stock_id": pd.Series(
                ["000001", "000002", "600000", "600001"],
                dtype="string",
            ),
            "group_id": pd.Series([1, 1, 1, 2], dtype="int64"),
        }
    )

    enriched = data.merge(
        mapping,
        on="stock_id",
        how="left",
        # market data 中一个 stock_id 可有很多行；映射表中每只股票必须唯一。
        validate="many_to_one",
        # indicator 会解释每行来自哪边。这里 left_only 就是映射中缺失的股票。
        indicator="mapping_status",
    )
    enriched["group_id"] = enriched["group_id"].astype("Int64")
    return enriched


def build_presence_matrix(data: pd.DataFrame) -> pd.DataFrame:
    """把长表变成 stock_id × time 的 0/1 出现矩阵。"""

    # crosstab 默认给出频数；gt(0) 把频数转成“是否出现”。这个宽表在小型
    # 分析和画图时直观，但全市场 × 全天 snapshot 可能非常宽、非常占内存。
    counts = pd.crosstab(index=data["stock_id"], columns=data["time"])
    return counts.gt(0).astype("int8")


def main() -> int:
    data = load_example_market_data()
    grouped = add_snapshot_deltas_and_groups(data)
    activity = aggregate_stock_activity(data)
    pair_scores = calculate_candidate_pair_scores(grouped)
    enriched = attach_example_group_mapping(data)
    presence_matrix = build_presence_matrix(data)

    print("\n[1] 每只股票的活跃度")
    print(activity.to_string(index=False))
    print("不同股票 ID：", data["stock_id"].unique().tolist())

    print("\n[2] 共同 snapshot 与同候选局部组次数")
    print(pair_scores.to_string(index=False))
    print(
        "提示：自连接会按每个 snapshot 的股票数产生 O(m²) 中间行；"
        "这里只适合小例子。真实全市场计算应先按 clock 邻域生成候选对。"
    )

    print("\n[3] many-to-one merge 和未映射股票")
    print(
        enriched[["stock_id", "time", "group_id", "mapping_status"]]
        .tail(3)
        .to_string(index=False)
    )

    print("\n[4] stock_id × time 出现矩阵")
    print(presence_matrix.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
