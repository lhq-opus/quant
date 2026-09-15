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
rows = []
for mode in ["cosine", "maxconditional", "minconditional"]:
    if mode == "cosine":
        rate = counts.div(freq.pow(0.5), axis=0).div(freq.pow(0.5), axis=1)
    else:
        a = counts.div(freq, axis=0)
        b = counts.div(freq, axis=1)
        rate = a.where(a.ge(b), b) if mode == "maxconditional" else a.where(a.le(b), b)
    for threshold in [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        adj = rate.ge(threshold)
        for s in counts.index:
            adj.at[s, s] = False
        n, l = connected_components(adj.to_numpy(), directed=False)
        labs = pd.Series(l, index=counts.index)
        cross = adj.where(
            pd.DataFrame({s: ref.ne(ref.at[s]) for s in counts.index}), False
        )
        stats = {
            "mode": mode,
            "threshold": threshold,
            "n": n,
            "sizes": "/".join(labs.value_counts().head(20).astype(str)),
            "crossedges": int(cross.sum().sum() // 2),
            "min_degree": int(adj.sum().min()),
        }
        rows.append(stats)
        print(stats, flush=True)
pd.DataFrame(rows).to_csv(
    ROOT / "v2_grouping_exploration_20260915/clock/rate_explore.csv", index=False
)
