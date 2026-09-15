"""补充大分量门槛、后半关系边及原始簇排除统计。"""

import pandas as pd
from profile_grouping import EVIDENCE, INPUT, infer_groups, observations
from scipy.sparse.csgraph import connected_components


def large_components(similarity, minimum=50):
    edges = similarity.ge(0.9)
    for stock in edges.index:
        edges.at[stock, stock] = False
    _n, labels = connected_components(edges.to_numpy(), directed=False)
    labels = pd.Series(labels, index=similarity.index, name="component")
    sizes = labels.value_counts()
    core = labels.loc[labels.map(sizes).ge(minimum)]
    minima = core.reset_index().groupby("component").stock_id.min().sort_values()
    core = core.map(pd.Series(range(1, len(minima) + 1), index=minima.index)).rename(
        "group_id"
    )
    return core, sizes, edges


def main():
    data = pd.read_csv(INPUT, dtype={"clock": "int64", "stock_id": "int64"})
    full, members, _records, _stats = infer_groups(data)
    members.copy()
    core = members.loc[members.is_profile_core].group_id
    rows, _affinity, sim = observations(data, 3000)
    diagnostics = []
    for minimum in [20, 30, 50, 80, 100]:
        other, sizes, _edges = large_components(sim, minimum)
        diagnostics.append(
            {
                "minimum_core_component_size": minimum,
                "core_stocks": len(other),
                "core_groups": other.nunique(),
                "minimum_major_component": int(sizes[sizes.ge(minimum)].min()),
                "maximum_small_component": int(sizes[sizes.lt(minimum)].max()),
                "same_core_members_and_labels": bool(other.equals(core)),
            }
        )
    pd.DataFrame(diagnostics).to_csv(EVIDENCE / "core_size_validation.csv", index=False)
    print(diagnostics, flush=True)
    # 必须统计未用于补全的混组簇，不能以筛完之后的纯度反证筛选正确。
    annotated = rows.assign(core_group=rows.stock_id.map(core))
    detail = annotated.groupby("cluster").agg(
        records=("stock_id", "size"),
        all_stocks=("stock_id", "nunique"),
        core_groups=("core_group", "nunique"),
    )
    known = (
        annotated.loc[annotated.core_group.notna()]
        .groupby("cluster")
        .stock_id.nunique()
    )
    detail["core_members"] = known.reindex(detail.index, fill_value=0)
    detail["classification"] = "too_few_core_members"
    detail.loc[detail.core_groups.gt(1), "classification"] = "mixed_core_groups"
    detail.loc[
        detail.core_groups.eq(1) & detail.core_members.ge(20), "classification"
    ] = "eligible_single_core_group"
    detail["contains_noncore"] = detail.all_stocks.gt(detail.core_members)
    detail.reset_index().groupby("classification").agg(
        clusters=("cluster", "size"),
        records=("records", "sum"),
        clusters_with_noncore=("contains_noncore", "sum"),
    ).to_csv(EVIDENCE / "cluster_screening.csv")
    print(
        detail.groupby("classification")
        .agg(
            clusters=("records", "size"),
            records=("records", "sum"),
            clusters_with_noncore=("contains_noncore", "sum"),
        )
        .to_string(),
        flush=True,
    )
    # 独立构造后半的所有轮廓边，使用前半冻结核心判断，不筛“纯”的边。
    half = len(data) // 2
    _first_rows, _first_affinity, first_sim = observations(data.iloc[:half], 3000)
    first_core, _first_sizes, _first_edges = large_components(first_sim)
    _unused, _unused_affinity, last_sim = observations(data.iloc[half:], 3000)
    last_core, _last_sizes, last_edges = large_components(last_sim)
    comparable = last_edges.loc[first_core.index, first_core.index]
    same = pd.DataFrame(
        {stock: first_core.eq(first_core.at[stock]) for stock in first_core.index}
    )
    crosses = comparable & ~same
    result = {
        "first_half_frozen_core_stocks": len(first_core),
        "first_half_core_groups": first_core.nunique(),
        "last_half_profile_edges": int(last_edges.sum().sum() // 2),
        "known_endpoint_edges": int(comparable.sum().sum() // 2),
        "cross_frozen_group_edges": int(crosses.sum().sum() // 2),
        "last_half_core_stocks": len(last_core),
        "last_half_core_groups": last_core.nunique(),
    }
    print(result, flush=True)
    pd.DataFrame([result]).to_csv(EVIDENCE / "holdout_profile_edges.csv", index=False)
    cross_pairs = (
        crosses.rename_axis(index="left", columns="right")
        .stack()
        .rename("cross")
        .reset_index()
    )
    cross_pairs.loc[
        cross_pairs.cross & cross_pairs.left.lt(cross_pairs.right), ["left", "right"]
    ].to_csv(EVIDENCE / "holdout_edge_counterexamples.csv", index=False)
    # 补全最小簇规模的敏感性，不只检查选中的默认20。
    completion = []
    for minimum in [10, 20, 30, 50]:
        try:
            labels, _ev, _rec, info = infer_groups(data, min_core_members=minimum)
            info["same_complete_mapping"] = bool(labels.equals(full))
            info["status"] = "complete"
        except ValueError as error:
            info = {"min_core_members": minimum, "status": str(error)}
        print(info, flush=True)
        completion.append(info)
    pd.DataFrame(completion).to_csv(
        EVIDENCE / "completion_size_validation.csv", index=False
    )


if __name__ == "__main__":
    main()
