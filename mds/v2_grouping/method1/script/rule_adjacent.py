"""不读取候选标签构图，检查跨初始扫描片段的短时间相邻关系。

从首轮独立学习扫描片段，短相邻边的连通分量作为规则推导的组。
其他阈值只与本次默认规则解事后比较，不依赖历史候选文件。
"""

from pathlib import Path

import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


METHOD = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / "v2_grouping_exploration_20260915/method1"


def infer(stocks, pairs):
    """无向连通分量允许间接联系，同一集合内不要求每对都有直接边。"""
    graph = coo_matrix((pd.Series(1, index=pairs.index),
        (stocks.get_indexer(pairs.stock_a), stocks.get_indexer(pairs.stock_b))),
        shape=(len(stocks), len(stocks))).tocsr()
    number, components = connected_components(graph, directed=False)
    groups = pd.Series(components, index=stocks, name="group_id")
    minima = groups.reset_index().groupby("group_id").stock_id.min().sort_values()
    rename = pd.Series(range(1, number + 1), index=minima.index)
    return groups.map(rename)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(ROOT / "quant/mds/data_v2.csv")
    stocks = pd.Index(data.stock_id.drop_duplicates().sort_values(), name="stock_id")
    prefix = data.iloc[:len(stocks)].copy()
    prefix["phase"] = prefix.clock.diff().gt(100000).cumsum() + 1
    phases = prefix.set_index("stock_id").phase
    assert len(prefix) == prefix.stock_id.nunique() == len(stocks)
    pairs = pd.DataFrame({
        "stock_a": data.stock_id.shift(), "stock_b": data.stock_id,
        "data_row_b": data.index + 1, "gap": data.clock.diff(),
    }).iloc[1:].astype("int64")
    pairs = pairs.loc[pairs.stock_a.map(phases).ne(pairs.stock_b.map(phases))]
    summaries = []
    maps = []
    samples = {"all": (0, len(data)), "first_half": (0, len(data)//2),
               "last_half": (len(data)//2, len(data))}
    for sample, (start, stop) in samples.items():
        for threshold in [5, 10, 20, 50, 100, 200, 500, 1000]:
            selected = pairs.loc[pairs.gap.le(threshold)
                & pairs.data_row_b.gt(start + 1) & pairs.data_row_b.le(stop)]
            edges = selected.groupby(["stock_a", "stock_b"], sort=False).size().rename("records").reset_index()
            labels = infer(stocks, edges)
            sizes = labels.value_counts()
            summaries.append({"sample": sample, "threshold": threshold,
                "components": labels.nunique(), "isolated_stocks": int(sizes.eq(1).sum()),
                "stocks_in_nontrivial_components": int(sizes.loc[sizes.gt(1)].sum()),
                "edges": len(edges), "observations": len(selected),
                "sizes": "/".join(sizes.sort_values(ascending=False).astype(str))})
            maps.append(labels.reset_index().assign(sample=sample, threshold=threshold))
            if sample == "all" and threshold == 100:
                labels.to_csv(METHOD / "stock_groups.csv")
                labels.to_csv(OUT / "rule_adjacent_groups.csv")
                edges.to_csv(OUT / "rule_adjacent_edges.csv", index=False)
                # 一条相邻观测为双方各提供一次邻居支持，按股票汇总。
                both = pd.concat([
                    edges.rename(columns={"stock_a": "stock_id", "stock_b": "neighbor"}),
                    edges.rename(columns={"stock_b": "stock_id", "stock_a": "neighbor"}),
                ], ignore_index=True)
                support = both.groupby("stock_id").agg(
                    neighbors=("neighbor", "nunique"),
                    adjacent_observations=("records", "sum"),
                ).reindex(stocks, fill_value=0)
                support["group_id"] = labels
                support.to_csv(OUT / "rule_adjacent_member_support.csv")

    all_maps = pd.concat(maps, ignore_index=True)
    # 只把本次全量 gap=100 解当作参数敏感性的比较基准，不读取历史标签。
    # 此处的一致性不属于独立真实标签验证。
    reference = all_maps.loc[all_maps["sample"].eq("all")
        & all_maps.threshold.eq(100)].set_index("stock_id").group_id
    all_maps["reference_group"] = all_maps.stock_id.map(reference)
    all_maps.to_csv(OUT / "rule_adjacent_mappings.csv", index=False)
    # 冻结前半独立得到的非孤立集合，在后半检查新联系是否违背它们。
    # 这里使用前半生成标签，不以完整映射作为训练参照。
    first = all_maps.loc[all_maps["sample"].eq("first_half")
        & all_maps.threshold.eq(100)].set_index("stock_id").group_id
    first = first.loc[first.map(first.value_counts()).gt(1)]
    heldout = pairs.loc[pairs.data_row_b.gt(len(data)//2 + 1)
        & pairs.gap.le(100) & pairs.stock_a.isin(first.index)
        & pairs.stock_b.isin(first.index)]
    violations = heldout.stock_a.map(first).ne(heldout.stock_b.map(first)).sum()
    pd.DataFrame([{
        "training": "first_half", "validation": "last_half", "threshold": 100,
        "training_core_stocks": len(first),
        "validation_comparable_observations": len(heldout),
        "violations": int(violations), "training_isolated_stocks": len(stocks)-len(first),
    }]).to_csv(OUT / "rule_adjacent_holdout.csv", index=False)
    summary = pd.DataFrame(summaries)
    summary.to_csv(OUT / "rule_adjacent_summary.csv", index=False)
    cross = pairs.loc[pairs.stock_a.map(reference).ne(pairs.stock_b.map(reference))].nsmallest(20, "gap")
    cross.to_csv(OUT / "rule_adjacent_first_cross_examples.csv", index=False)
    print(summary.to_string(index=False))
    print("First cross-group, cross-phase adjacent records:")
    print(cross.head(5).to_string(index=False))
    print("Comparison for full data threshold 100:")
    selected = all_maps.loc[all_maps['sample'].eq('all') & all_maps.threshold.eq(100)]
    print(pd.crosstab(selected.group_id, selected.reference_group).to_string())
    print("Initial phase within-gap maximum and between-gap minimum:")
    gap = prefix.clock.diff()
    print(gap.loc[prefix.phase.eq(prefix.phase.shift())].max(), gap.loc[prefix.phase.ne(prefix.phase.shift())].min())


if __name__ == "__main__":
    main()
