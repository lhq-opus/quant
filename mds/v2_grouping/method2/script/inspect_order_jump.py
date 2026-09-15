"""method2 的全量实测、参数平台、分片与冻结留出检查；不是单元测试。"""

import pandas as pd

from group_by_order_jump import INPUT, METHOD, count_edges, group_edges, prepare_observations


ROOT = METHOD.parents[3]
OUT = ROOT / "v2_grouping_exploration_20260915/order"


def describe(name, ids, edges, groups, full_groups, maximum_gap=100, excluded_steps=10):
    sizes = groups.groupby("group_id").size()
    aligned = groups.merge(full_groups, on="stock_id", suffixes=("", "_full"))
    # 一组在全量结果内是否被拆散，用于比较成员集合，不靠组号数值相等。
    merged_full_groups = int(aligned.groupby("group_id").group_id_full.nunique().gt(1).sum())
    return {
        "part": name, "maximum_clock_gap": maximum_gap,
        "excluded_forward_steps": excluded_steps, "groups": len(sizes),
        "isolated_stocks": int(sizes.eq(1).sum()),
        "connected_stocks": int(sizes.loc[sizes.gt(1)].sum()),
        "different_directed_pairs": len(edges),
        "qualifying_observations": int(edges.observations.sum()),
        "sizes_sorted": "/".join(sizes.sort_values().astype(str)),
        "components_merging_full_groups": merged_full_groups,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT, usecols=["clock", "stock_id"])
    ids, initial, observations = prepare_observations(data)
    full_edges = count_edges(observations)
    full_groups = group_edges(ids, full_edges)
    full_groups.to_csv(METHOD / "stock_groups.csv", index=False, lineterminator="\n")
    full_edges.to_csv(OUT / "method2_edges.csv", index=False)
    initial.to_csv(OUT / "method2_initial_template.csv", index=False)
    full_labels = full_groups.set_index("stock_id").group_id

    # 先聚合各时差下全部相邻边，再扫描排名过滤宽度；分组不读取任何已有标签。
    sensitivity = []
    for gap in [5, 10, 20, 50, 100, 200, 211, 250, 500]:
        all_edges = count_edges(observations, gap, 0)
        for steps in [0, 1, 2, 3, 4, 5, 6, 10, 20, 50, 100, 200, 500, 1000]:
            edges = all_edges.loc[~all_edges.rank_jump.between(1, steps)]
            groups = group_edges(ids, edges)
            sensitivity.append(describe("full", ids, edges, groups, full_groups, gap, steps))
    pd.DataFrame(sensitivity).to_csv(OUT / "method2_sensitivity.csv", index=False)

    # 每个切片包含原始左、右两条记录；不把跨分片边归入其中一边。
    n = len(data)
    ranges = [("first_half", 0, n // 2), ("last_half", n // 2, n)]
    ranges += [(f"quarter_{i+1}", n*i//4, n*(i+1)//4) for i in range(4)]
    slices, split_groups = [], {}
    for name, start, stop in ranges:
        part = observations.loc[
            observations.right_data_row.gt(start + 1)
            & observations.right_data_row.le(stop)
        ]
        for gap in [10, 20, 50, 100, 200]:
            for steps in [5, 10, 20, 100]:
                edges = count_edges(part, gap, steps)
                groups = group_edges(ids, edges)
                slices.append(describe(name, ids, edges, groups, full_groups, gap, steps))
                if gap == 100 and steps == 10:
                    split_groups[name] = groups
    pd.DataFrame(slices).to_csv(OUT / "method2_slices.csv", index=False)

    # 先冻结前半的非单例成员，后半只做相邻关系预测核验，不更改这些成员。
    train = split_groups["first_half"]
    train_sizes = train.groupby("group_id").size()
    core = train.loc[train.group_id.map(train_sizes).gt(1)].set_index("stock_id").group_id
    test = observations.loc[observations.right_data_row.gt(n // 2 + 1)]
    test_edges = count_edges(test)
    test_edges["left_train_group"] = test_edges.left_stock_id.map(core)
    test_edges["right_train_group"] = test_edges.right_stock_id.map(core)
    known = test_edges.left_train_group.notna() & test_edges.right_train_group.notna()
    conflicts = known & test_edges.left_train_group.ne(test_edges.right_train_group)
    holdout = pd.DataFrame([{
        "frozen_core_stocks": len(core), "unknown_training_stocks": len(ids) - len(core),
        "test_known_observations": int(test_edges.loc[known, "observations"].sum()),
        "test_known_pairs": int(known.sum()),
        "test_conflicting_observations": int(test_edges.loc[conflicts, "observations"].sum()),
        "test_conflicting_pairs": int(conflicts.sum()),
        "test_observations_with_unknown_endpoint": int(test_edges.loc[~known, "observations"].sum()),
    }])
    holdout.to_csv(OUT / "method2_holdout.csv", index=False)

    left_support = full_edges[["left_stock_id", "right_stock_id", "observations"]].rename(
        columns={"left_stock_id": "stock_id", "right_stock_id": "neighbor"})
    right_support = full_edges[["right_stock_id", "left_stock_id", "observations"]].rename(
        columns={"right_stock_id": "stock_id", "left_stock_id": "neighbor"})
    support = pd.concat([left_support, right_support]).groupby("stock_id").agg(
        different_neighbors=("neighbor", "nunique"),
        qualifying_observations=("observations", "sum"),
    ).reset_index().merge(full_groups, on="stock_id")
    support["isolated_in_first_half"] = ~support.stock_id.isin(core.index)
    support.to_csv(OUT / "method2_member_support.csv", index=False)

    # 参考完整前缀不事后排序：开头重复排列一致到哪条，直接与首排列比较。
    ranks = initial.set_index("stock_id").initial_rank
    matches = data.stock_id.map(ranks).eq(data.index % len(initial))
    first_change = int(matches.eq(False).idxmax())
    template = pd.DataFrame([{
        "total_rows": n, "total_stocks": len(ids),
        "initial_stocks": len(initial),
        "initial_is_universe": initial.stock_id.sort_values().reset_index(drop=True).equals(ids),
        "identical_complete_prefix_permutations": first_change // len(initial),
        "additional_matching_rows": first_change % len(initial),
        "first_different_data_row": first_change + 1,
    }])
    template.to_csv(OUT / "method2_template_summary.csv", index=False)

    # 以首股票的再次出现划候选区间，先只检查长度/全集，之后才核对顺序。
    # 这避免“只寻找与模板相同的片段，再说模板没有反例”的循环筛选。
    candidates = data[["stock_id"]].copy()
    candidates["candidate"] = candidates.stock_id.eq(initial.stock_id.iloc[0]).cumsum()
    candidates["position"] = candidates.groupby("candidate", sort=False).cumcount()
    candidates["same_position"] = candidates.stock_id.map(ranks).eq(candidates.position)
    candidates["data_row"] = candidates.index + 1
    candidate_summary = candidates.groupby("candidate", sort=False).agg(
        rows=("stock_id", "size"), stocks=("stock_id", "nunique"),
        same_order=("same_position", "all"),
        first_data_row=("data_row", "first"), last_data_row=("data_row", "last"),
    )
    complete = candidate_summary.loc[
        candidate_summary.rows.eq(len(ids)) & candidate_summary.stocks.eq(len(ids))
    ]
    complete.to_csv(OUT / "method2_full_template_candidates.csv", index=False)
    later = complete.loc[complete.first_data_row.gt(n // 2)].iloc[0]
    alternative = data.iloc[int(later.first_data_row)-1:int(later.last_data_row)]
    alternative_ranks = pd.Series(range(len(alternative)), index=alternative.stock_id)
    alternate_observations = observations.assign(rank_jump=(
        observations.right_stock_id.map(alternative_ranks)
        - observations.left_stock_id.map(alternative_ranks)
    ))
    alternate_groups = group_edges(ids, count_edges(alternate_observations))
    pd.DataFrame([{
        "complete_candidate_permutations": len(complete),
        "different_order_candidates": int((~complete.same_order).sum()),
        "later_half_complete_candidates": int(complete.first_data_row.gt(n // 2).sum()),
        "later_reference_first_data_row": int(later.first_data_row),
        "later_reference_last_data_row": int(later.last_data_row),
        "later_reference_same_grouping": alternate_groups.equals(full_groups),
    }]).to_csv(OUT / "method2_template_holdout.csv", index=False)

    # 有意放松规则后的真实反例；此处才读取本次全量结果进行事后对照。
    cross = observations.left_stock_id.map(full_labels).ne(observations.right_stock_id.map(full_labels))
    short_cross = observations.loc[cross & observations.clock_gap.le(100)]
    short_cross.nlargest(20, "rank_jump").to_csv(OUT / "method2_order_counterexamples.csv", index=False)
    observations.loc[cross & ~observations.rank_jump.between(1, 10)].nsmallest(
        20, "clock_gap"
    ).to_csv(OUT / "method2_clock_counterexamples.csv", index=False)
    reference = pd.read_csv(METHOD.parent / "method1/stock_groups.csv")
    compared = full_groups.merge(reference, on="stock_id", suffixes=("", "_method1"))
    comparison = pd.DataFrame([{
        "rows": len(full_groups), "unique_stocks": full_groups.stock_id.nunique(),
        "missing_labels": int(full_groups.group_id.isna().sum()),
        "same_named_members_as_method1": int(compared.group_id.eq(compared.group_id_method1).sum()),
        "same_universe_as_source": full_groups.stock_id.equals(ids),
    }])
    comparison.to_csv(OUT / "method2_comparison.csv", index=False)
    print(template.to_string(index=False))
    print(full_groups.groupby("group_id").size().to_string())
    print(holdout.to_string(index=False))
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
