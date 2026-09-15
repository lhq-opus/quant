"""固定时间网格、谱分组与中心时间窗口补全；仅依赖原始 CSV。

不使用首轮位置、初始扫描片段、相邻 gap 切簇或关系轮廓余弦。
表处理全部使用 pandas；SciPy/sklearn 只辅助矩阵分解与聚类。
"""
from pathlib import Path

import pandas as pd
from scipy.linalg import eigh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import laplacian
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parents[5]
INPUT = ROOT / "quant/mds/data_v2.csv"
OUTPUT = Path(__file__).resolve().parents[1] / "stock_groups.csv"
EVIDENCE = ROOT / "v2_grouping_exploration_20260915/method4"


def grid_affinity(data, width=30000, offsets=4):
    """多次平移网格，平均双方二元出现轨迹的直接同步程度。"""
    stocks = pd.Index(data.stock_id.drop_duplicates().sort_values(), name="stock_id")
    total = None
    for part in range(offsets):
        shift = part * width // offsets
        cells = data.assign(cell=(data.clock + shift) // width)
        presence = cells.drop_duplicates(["cell", "stock_id"])
        codes, bins = pd.factorize(presence.cell, sort=False)
        matrix = coo_matrix((pd.Series(1, index=presence.index),
                            (codes, stocks.get_indexer(presence.stock_id))),
                            shape=(len(bins), len(stocks))).tocsr()
        product = matrix.T @ matrix
        counts = pd.DataFrame(product.toarray(), index=stocks, columns=stocks)
        exposure = pd.Series(product.diagonal(), index=stocks)
        normalized = counts.div(exposure.pow(.5), axis=0).div(exposure.pow(.5), axis=1)
        total = normalized if total is None else total + normalized
    weights = total / offsets
    for stock in stocks:
        weights.at[stock, stock] = 0
    return weights


def canonical(labels):
    """组号按组内最小股票 ID 规范化，不改变成员。"""
    minima = labels.rename("group_id").reset_index().groupby("group_id").stock_id.min().sort_values()
    return labels.map(pd.Series(range(1, len(minima) + 1), index=minima.index)).rename("group_id")


def spectral_groups(weights):
    """最大相邻特征值间隙选择 1–30 组；六组不是输入参数。"""
    last = min(30, len(weights) - 1)
    values, vectors = eigh(laplacian(weights.to_numpy(), normed=True),
                           subset_by_index=[0, last])
    spectrum = pd.DataFrame({"eigenvalue": values})
    spectrum["gap_before"] = spectrum.eigenvalue.diff()
    number = int(spectrum.gap_before.iloc[1:].idxmax())
    embedding = pd.DataFrame(vectors[:, :number], index=weights.index)
    embedding = embedding.div(embedding.pow(2).sum(axis=1).pow(.5), axis=0)
    labels = pd.Series(KMeans(number, n_init=10, random_state=20260915).fit_predict(embedding),
                       index=weights.index, name="group_id")
    return canonical(labels), spectrum


def member_scores(weights, labels):
    """按冻结成员计算平均同步，组内平均不把股票自己算进去。"""
    sizes = labels.value_counts()
    means = weights.loc[:, labels.index].T.groupby(labels).sum().T.div(sizes, axis=1)
    rows = []
    for stock, group in labels.items():
        inside = means.at[stock, group] * sizes.at[group] / (sizes.at[group] - 1)
        outside = means.loc[stock].drop(group).max() if len(sizes) > 1 else 0.0
        rows.append({"stock_id": stock, "group_id": group, "within": inside,
                     "outside": outside, "margin": inside - outside})
    return pd.DataFrame(rows).set_index("stock_id")


def learn_core(data, width=30000, offsets=4, core_threshold=.05):
    weights = grid_affinity(data, width, offsets)
    provisional, spectrum = spectral_groups(weights)
    scores = member_scores(weights, provisional)
    core = provisional.loc[scores.within.ge(core_threshold) & scores.margin.gt(0)]
    return core, provisional, weights, scores, spectrum


def centered_support(data, core, radius=10000, min_core=20):
    """对每条待补记录查固定 ±radius 窗口；不按相邻 gap 扩展窗口。

    所有合格窗口的候选标签必须一致。混核心窗口与核心数不足窗口保留
    计数，但不提供归属。一次原始目标到达只计一次，不把左右边重复计数。
    """
    unknown = data.loc[~data.stock_id.isin(core.index)]
    starts = pd.Series(data.clock.searchsorted(unknown.clock - radius), index=unknown.index)
    stops = pd.Series(data.clock.searchsorted(unknown.clock + radius, side="right"), index=unknown.index)
    core_ids = data.stock_id.map(core)
    records = []
    screening = []
    for index, target in unknown.iterrows():
        first, last = int(starts.at[index]), int(stops.at[index])
        local = data.iloc[first:last][["stock_id"]].copy()
        local["core_group"] = core_ids.iloc[first:last]
        local = local.dropna().drop_duplicates("stock_id")
        group_count = local.core_group.nunique()
        if group_count == 1 and len(local) >= min_core:
            state = "supported"
            records.append({"stock_id": int(target.stock_id), "data_row": int(index)+1,
                            "clock": int(target.clock), "group_id": int(local.core_group.iloc[0]),
                            "core_members": len(local), "window_first_data_row": first+1,
                            "window_last_data_row": last})
        else:
            state = "mixed_core" if group_count > 1 else "insufficient_core"
        screening.append({"stock_id": int(target.stock_id), "state": state})
    columns = ["stock_id", "data_row", "clock", "group_id", "core_members",
               "window_first_data_row", "window_last_data_row"]
    observations = pd.DataFrame(records, columns=columns)
    support = observations.groupby("stock_id").agg(group_id=("group_id", "first"),
                    groups=("group_id", "nunique"), records=("group_id", "size"))
    counts = pd.DataFrame(screening, columns=["stock_id", "state"]).groupby(["stock_id", "state"]).size()
    return support, observations, counts.rename("records").reset_index()


def infer_groups(data, width=30000, offsets=4, core_threshold=.05, radius=10000, min_core=20):
    core, provisional, weights, scores, spectrum = learn_core(data, width, offsets, core_threshold)
    support, observations, screening = centered_support(data, core, radius, min_core)
    full = pd.concat([core, support.group_id]).sort_index().astype("int64")
    missing = weights.index.difference(full.index)
    conflicts = support.loc[support.groups.ne(1)]
    if len(missing) or len(conflicts):
        raise ValueError(f"当前设置不能一致覆盖：缺失{missing.tolist()}，冲突{conflicts.index.tolist()}")
    full = canonical(full)
    scores["provisional_group"] = provisional
    scores["group_id"] = full
    scores["is_core"] = scores.index.isin(core.index)
    scores["local_support_records"] = scores.index.to_series().map(support.records).fillna(0).astype("int64")
    summary = {"width": width, "offsets": offsets, "core_threshold": core_threshold,
               "radius": radius, "min_core": min_core, "spectral_groups": provisional.nunique(),
               "core_stocks": len(core), "completion_stocks": len(support),
               "completion_records": len(observations), "stocks": len(full), "groups": full.nunique()}
    return full, scores, observations, screening, spectrum, summary


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT, dtype={"clock": "int64", "stock_id": "int64"})
    full, scores, observations, screening, spectrum, summary = infer_groups(data)
    full.to_csv(OUTPUT)
    scores.to_csv(EVIDENCE / "member_support.csv")
    observations.to_csv(EVIDENCE / "completion_records.csv", index=False)
    screening.to_csv(EVIDENCE / "completion_screening.csv", index=False)
    spectrum.to_csv(EVIDENCE / "spectrum.csv", index=False)
    pd.DataFrame([summary]).to_csv(EVIDENCE / "summary.csv", index=False)
    print(summary)
    print(full.value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
