"""通过共同出现关系的相似轮廓分组；不使用首轮模板或其他方法的组号。"""

from pathlib import Path
from time import perf_counter

import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[5]
INPUT = ROOT / "quant/mds/data_v2.csv"
OUTPUT = Path(__file__).resolve().parents[1] / "stock_groups.csv"
EVIDENCE = ROOT / "v2_grouping_exploration_20260915/clock"


def observations(data, threshold):
    """相邻 clock 差超过 threshold 时切开；观测簇不是已知真实推送。"""
    rows = data.assign(cluster=data.clock.diff().gt(threshold).cumsum())
    presence = rows.drop_duplicates(["cluster", "stock_id"])
    stocks = pd.Index(data.stock_id.drop_duplicates().sort_values(), name="stock_id")
    cluster_codes, cluster_ids = pd.factorize(presence.cluster, sort=False)
    # 只把 pandas 准备好的出现表交给 SciPy 做稀疏矩阵乘法。
    matrix = coo_matrix(
        (
            pd.Series(1, index=presence.index),
            (cluster_codes, stocks.get_indexer(presence.stock_id)),
        ),
        shape=(len(cluster_ids), len(stocks)),
    ).tocsr()
    products = matrix.T @ matrix
    counts = pd.DataFrame(products.toarray(), index=stocks, columns=stocks)
    exposure = pd.Series(products.diagonal(), index=stocks)
    affinity = counts.div(exposure.pow(0.5), axis=0).div(exposure.pow(0.5), axis=1)
    # 自己与自己的同步不参与比较“与其他股票的关系轮廓”。
    for stock in stocks:
        affinity.at[stock, stock] = 0
    profiles = affinity.div(affinity.pow(2).sum(axis=1).pow(0.5), axis=0).fillna(0)
    similarity = profiles @ profiles.T
    return rows, affinity, similarity


def infer_groups(
    data, gap=3000, profile_threshold=0.9, core_size=50, min_core_members=20
):
    rows, _affinity, similarity = observations(data, gap)
    edges = similarity.ge(profile_threshold)
    for stock in edges.index:
        edges.at[stock, stock] = False
    number, labels = connected_components(edges.to_numpy(), directed=False)
    components = pd.Series(labels, index=edges.index, name="component")
    sizes = components.value_counts()
    # 小分量容易只是几股共享扫描背景，先只接受有足够成员的大分量。
    core = components.loc[components.map(sizes).ge(core_size)]
    minima = core.reset_index().groupby("component").stock_id.min().sort_values()
    rename = pd.Series(range(1, len(minima) + 1), index=minima.index)
    core = core.map(rename).rename("group_id")
    annotated = rows.assign(core_group=rows.stock_id.map(core))
    core_stats = (
        annotated.loc[annotated.core_group.notna()]
        .groupby("cluster")
        .agg(
            core_groups=("core_group", "nunique"),
            core_members=("stock_id", "nunique"),
            group_id=("core_group", "first"),
        )
    )
    eligible = core_stats.loc[
        core_stats.core_groups.eq(1) & core_stats.core_members.ge(min_core_members)
    ]
    # 不读其他方法的标签。给小分量中的每股查找“至少20只核心股且只有一个
    # 核心组”的观测簇；所有这种支持必须指向同一组，否则拒绝静默投票。
    unknown_rows = annotated.loc[
        annotated.core_group.isna() & annotated.cluster.isin(eligible.index)
    ].copy()
    unknown_rows["group_id"] = unknown_rows.cluster.map(eligible.group_id).astype(
        "int64"
    )
    unknown_rows["core_members"] = unknown_rows.cluster.map(eligible.core_members)
    unknown_rows["data_row"] = unknown_rows.index + 1
    support = unknown_rows.groupby("stock_id").agg(
        groups=("group_id", "nunique"),
        group_id=("group_id", "first"),
        records=("group_id", "size"),
        clusters=("cluster", "nunique"),
    )
    conflicts = support.loc[support.groups.gt(1)]
    missing = components.index.difference(core.index.union(support.index))
    full = pd.concat([core, support.group_id]).sort_index().astype("int64")
    if len(conflicts) or len(missing):
        raise ValueError(
            f"该参数不能无冲突覆盖：冲突{conflicts.to_dict('index')}，缺失{missing.tolist()}"
        )
    # 按最终各组最小ID编号，保证不同参数和样本可直接比较。
    minima = full.reset_index().groupby("group_id").stock_id.min().sort_values()
    rename = pd.Series(range(1, len(minima) + 1), index=minima.index)
    full = full.map(rename).rename("group_id")
    core = core.map(rename)
    unknown_rows["group_id"] = unknown_rows.group_id.map(rename)
    degree = edges.sum(axis=1)
    evidence = full.to_frame().assign(
        is_profile_core=full.index.isin(core.index), profile_neighbors=degree
    )
    evidence["completion_records"] = (
        evidence.index.to_series().map(support.records).fillna(0).astype("int64")
    )
    evidence["completion_clusters"] = (
        evidence.index.to_series().map(support.clusters).fillna(0).astype("int64")
    )
    summary = {
        "gap": gap,
        "profile_threshold": profile_threshold,
        "core_size_threshold": core_size,
        "min_core_members": min_core_members,
        "observations": rows.cluster.nunique(),
        "profile_components": number,
        "core_components": core.nunique(),
        "core_stocks": len(core),
        "completion_stocks": len(support),
        "completion_records": len(unknown_rows),
        "complete_stocks": len(full),
        "sizes": "/".join(full.value_counts().sort_index().astype(str)),
        "core_sizes": "/".join(core.value_counts().sort_index().astype(str)),
        "largest_small_component": int(sizes.loc[sizes.lt(core_size)].max()),
        "eligible_clusters": len(eligible),
        "mixed_core_clusters": int(core_stats.core_groups.gt(1).sum()),
        "clusters_with_unknown_support": unknown_rows.cluster.nunique(),
    }
    return full, evidence, unknown_rows, summary


def main():
    started = perf_counter()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT, dtype={"clock": "int64", "stock_id": "int64"})
    groups, evidence, records, summary = infer_groups(data)
    groups.reset_index().to_csv(OUTPUT, index=False)
    evidence.reset_index().to_csv(EVIDENCE / "member_support.csv", index=False)
    records[
        ["data_row", "clock", "stock_id", "cluster", "group_id", "core_members"]
    ].to_csv(EVIDENCE / "completion_records.csv", index=False)
    summary["elapsed_seconds"] = perf_counter() - started
    pd.DataFrame([summary]).to_csv(EVIDENCE / "summary.csv", index=False)
    print(summary, flush=True)


if __name__ == "__main__":
    main()
