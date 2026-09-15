"""用首轮排名跳变和短 clock 间隔独立分组；只依赖原始 CSV。"""

from pathlib import Path

import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


METHOD = Path(__file__).resolve().parents[1]
MDS = METHOD.parents[1]
INPUT = MDS / "data_v2.csv"
OUTPUT = METHOD / "stock_groups.csv"
MAXIMUM_CLOCK_GAP = 100
EXCLUDED_FORWARD_STEPS = 10


def prepare_observations(data):
    """首个重复 ID 之前作为参考排列；保留原序，不按股票重新排列记录。"""
    first_repeat = int(data.stock_id.duplicated().idxmax())
    initial = data.iloc[:first_repeat].copy()
    initial["initial_rank"] = range(len(initial))
    ranks = initial.set_index("stock_id").initial_rank
    ids = data.stock_id.drop_duplicates().sort_values().reset_index(drop=True)
    observations = pd.DataFrame({
        "left_stock_id": data.stock_id.shift(),
        "right_stock_id": data.stock_id,
        "clock_gap": data.clock.diff(),
        "right_data_row": data.index + 1,
    }).iloc[1:].copy()
    observations["left_stock_id"] = observations.left_stock_id.astype("int64")
    observations["clock_gap"] = observations.clock_gap.astype("int64")
    observations["rank_jump"] = (
        observations.right_stock_id.map(ranks)
        - observations.left_stock_id.map(ranks)
    )
    return ids, initial, observations


def count_edges(observations, maximum_gap=MAXIMUM_CLOCK_GAP,
                excluded_steps=EXCLUDED_FORWARD_STEPS):
    """排除首轮顺序中向前走 1..L 位的局部相邻；两道条件均不读取组号。"""
    selected = observations.loc[
        observations.clock_gap.between(1, maximum_gap)
        & ~observations.rank_jump.between(1, excluded_steps)
    ]
    return selected.groupby(["left_stock_id", "right_stock_id"], sort=False).agg(
        observations=("right_data_row", "size"),
        rank_jump=("rank_jump", "first"),
        minimum_clock_gap=("clock_gap", "min"),
        maximum_clock_gap=("clock_gap", "max"),
        first_right_data_row=("right_data_row", "min"),
        last_right_data_row=("right_data_row", "max"),
    ).reset_index()


def group_edges(ids, edges):
    """按无向联系的连通分量分组，不预设组数；组号按组内最小 ID 编排。"""
    stock_index = pd.Series(ids.index, index=ids)
    graph = csr_matrix(
        (edges.observations,
         (edges.left_stock_id.map(stock_index), edges.right_stock_id.map(stock_index))),
        shape=(len(ids), len(ids)),
    )
    _, labels = connected_components(graph, directed=False)
    groups = pd.DataFrame({"stock_id": ids, "component": labels})
    minima = groups.groupby("component").stock_id.min().sort_values()
    component_to_group = pd.Series(range(1, len(minima) + 1), index=minima.index)
    groups["group_id"] = groups.component.map(component_to_group)
    return groups[["stock_id", "group_id"]]


def main():
    data = pd.read_csv(INPUT, usecols=["clock", "stock_id"])
    ids, _, observations = prepare_observations(data)
    groups = group_edges(ids, count_edges(observations))
    groups.to_csv(OUTPUT, index=False, lineterminator="\n")
    print(groups.groupby("group_id").size().to_string())
    print(f"已覆盖 {len(groups)} 股，写入 {OUTPUT}")


if __name__ == "__main__":
    main()
