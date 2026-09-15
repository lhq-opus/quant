from pathlib import Path

import pandas as pd
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[6]
counts = pd.read_pickle(ROOT / "mds_v2_exploration_20260915/clock_counts_3000.pkl")
freq = pd.Series(counts.to_numpy().diagonal(), index=counts.index)
ref = (
    pd.read_csv(ROOT / "quant/mds/v2_grouping/method1/stock_groups.csv")
    .set_index("stock_id")
    .group_id
)
rate = counts.div(freq.pow(0.5), axis=0).div(freq.pow(0.5), axis=1)
for s in rate.index:
    rate.at[s, s] = 0
profiles = rate.div(rate.pow(2).sum(axis=1).pow(0.5), axis=0)
sim = profiles @ profiles.T
rows = []
for threshold in [0.72, 0.73, 0.74, 0.75, 0.76, 0.77, 0.78, 0.79, 0.8, 0.82]:
    adj = sim.ge(threshold)
    for s in adj.index:
        adj.at[s, s] = False
    n, l = connected_components(adj.to_numpy(), directed=False)
    labels = pd.Series(l, index=adj.index)
    group = labels.value_counts()
    stats = {
        "threshold": threshold,
        "n": n,
        "sizes": "/".join(group.head(20).astype(str)),
    }
    large = labels.loc[labels.map(group).ge(50)]
    purity = (
        pd.DataFrame({"label": large, "ref": ref.loc[large.index]})
        .groupby("label")
        .ref.nunique()
    )
    stats["mixed_large"] = int(purity.gt(1).sum())
    stats["largecoverage"] = len(large)
    rows.append(stats)
    print(stats, flush=True)
pd.DataFrame(rows).to_csv(
    ROOT / "v2_grouping_exploration_20260915/clock/profile_explore.csv", index=False
)
