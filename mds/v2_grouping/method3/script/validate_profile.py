"""实际数据探索与留出核验；不运行单元测试。"""

import pandas as pd
from profile_grouping import EVIDENCE, INPUT, ROOT, infer_groups, observations
from scipy.sparse.csgraph import connected_components


def run():
    data = pd.read_csv(INPUT, dtype={"clock": "int64", "stock_id": "int64"})
    ref = (
        pd.read_csv(ROOT / "quant/mds/v2_grouping/method1/stock_groups.csv")
        .set_index("stock_id")
        .group_id
    )
    summary = []
    for gap in [1800, 2000, 3000, 5000, 10000]:
        for threshold in [0.85, 0.9, 0.95]:
            try:
                labels, _members, _records, stats = infer_groups(
                    data, gap=gap, profile_threshold=threshold
                )
                stats["same_as_method1"] = bool(labels.eq(ref).all())
                stats["status"] = "complete"
            except ValueError as error:
                stats = {
                    "gap": gap,
                    "profile_threshold": threshold,
                    "status": str(error),
                }
            summary.append(stats)
            print(stats, flush=True)
            pd.DataFrame(summary).to_csv(
                EVIDENCE / "parameter_validation.csv", index=False
            )
    # 用未读参考标签的前半大分量作为锚，考察后半时间簇中的固定成员。
    half = len(data) // 2
    first = data.iloc[:half]
    last = data.iloc[half:]
    _first_rows, _first_affinity, similarity = observations(first, 3000)
    edges = similarity.ge(0.9)
    for stock in edges.index:
        edges.at[stock, stock] = False
    _first_n, l = connected_components(edges.to_numpy(), directed=False)
    components = pd.Series(l, index=edges.index, name="component")
    size = components.value_counts()
    core = components.loc[components.map(size).ge(50)]
    minima = core.reset_index().groupby("component").stock_id.min().sort_values()
    core = core.map(pd.Series(range(1, len(minima) + 1), index=minima.index)).rename(
        "group_id"
    )
    after = last.assign(cluster=last.clock.diff().gt(3000).cumsum())
    annotated = after.assign(core_group=after.stock_id.map(core))
    detail = (
        annotated.loc[annotated.core_group.notna()]
        .groupby("cluster")
        .agg(
            core_groups=("core_group", "nunique"),
            core_members=("stock_id", "nunique"),
            group_id=("core_group", "first"),
        )
    )
    eligible = detail.loc[detail.core_groups.eq(1) & detail.core_members.ge(20)]
    unknown = annotated.loc[
        annotated.core_group.isna() & annotated.cluster.isin(eligible.index)
    ].copy()
    unknown["group_id"] = unknown.cluster.map(eligible.group_id)
    support = unknown.groupby("stock_id").agg(
        groups=("group_id", "nunique"),
        group_id=("group_id", "first"),
        records=("stock_id", "size"),
        clusters=("cluster", "nunique"),
    )
    result = pd.concat([core, support.group_id]).sort_index().astype("int64")
    holdout = {
        "training_rows": len(first),
        "holdout_rows": len(last),
        "first_half_core_components": core.nunique(),
        "first_half_core_stocks": len(core),
        "unknowns_supported_in_last": len(support),
        "conflicting_unknowns": int(support.groups.gt(1).sum()),
        "supported_unknown_records": len(unknown),
        "covered": len(result),
        "same_as_method1": bool(result.eq(ref).all()),
    }
    print(holdout, flush=True)
    pd.DataFrame([holdout]).to_csv(EVIDENCE / "holdout_completion.csv", index=False)
    support.reset_index().to_csv(EVIDENCE / "holdout_member_support.csv", index=False)
    # 前后半各自构造轮廓图，比较其大分量中的共同成员；组号按最小ID标准化。
    for name, sample in [
        ("last_half", last),
        ("first_quarter", data.iloc[: len(data) // 4]),
        ("second_quarter", data.iloc[len(data) // 4 : len(data) // 2]),
        ("third_quarter", data.iloc[len(data) // 2 : 3 * len(data) // 4]),
        ("fourth_quarter", data.iloc[3 * len(data) // 4 :]),
    ]:
        _rows, _affinity, sim = observations(sample, 3000)
        edges = sim.ge(0.9)
        for stock in edges.index:
            edges.at[stock, stock] = False
        _n, l = connected_components(edges.to_numpy(), directed=False)
        components = pd.Series(l, index=edges.index, name="component")
        size = components.value_counts()
        core = components.loc[components.map(size).ge(50)]
        minima = core.reset_index().groupby("component").stock_id.min().sort_values()
        core = core.map(
            pd.Series(range(1, len(minima) + 1), index=minima.index)
        ).rename("group_id")
        stats = {
            "sample": name,
            "rows": len(sample),
            "major_components": core.nunique(),
            "core_members": len(core),
            "same_as_method1_core": bool(core.eq(ref.loc[core.index]).all()),
            "uncovered": len(ref) - len(core),
        }
        print(stats, flush=True)
        summary.append(stats)
        pd.DataFrame(summary).to_csv(EVIDENCE / "parameter_validation.csv", index=False)


if __name__ == "__main__":
    run()
