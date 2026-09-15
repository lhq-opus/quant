from pathlib import Path

import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[6]
data = pd.read_csv(ROOT / "quant/mds/data_v2.csv")
ids = pd.Index(data.stock_id.drop_duplicates().sort_values(), name="stock_id")
ref = (
    pd.read_csv(ROOT / "quant/mds/v2_grouping/method1/stock_groups.csv")
    .set_index("stock_id")
    .group_id
)
out = ROOT / "v2_grouping_exploration_20260915/clock"
rows = []
for threshold in [20, 50, 100, 200, 500, 1000, 1800, 3000]:
    df = data.assign(cluster=data.clock.diff().gt(threshold).cumsum())
    sizes = df.groupby("cluster").stock_id.size()
    for minsize in [30, 40, 50, 60, 70, 100]:
        take = df.loc[df.cluster.map(sizes).ge(minsize)].copy()
        presence = take.drop_duplicates(["cluster", "stock_id"])
        c, cs = pd.factorize(presence.cluster)
        mat = coo_matrix(
            (
                pd.Series(1, index=presence.index),
                (c, ids.get_indexer(presence.stock_id)),
            ),
            shape=(len(cs), len(ids)),
        ).tocsr()
        adj = mat.T @ mat
        n, l = connected_components(adj, directed=False)
        labels = pd.Series(l, index=ids)
        purity = (
            take.assign(ref=take.stock_id.map(ref)).groupby("cluster").ref.nunique()
        )
        stats = {
            "gap": threshold,
            "minimum_cluster": minsize,
            "selected_clusters": len(cs),
            "rows": len(take),
            "stocks": take.stock_id.nunique(),
            "components": n,
            "sizes": "/".join(
                labels.value_counts().sort_values(ascending=False).head(12).astype(str)
            ),
            "mixed_clusters": int(purity.gt(1).sum()),
            "mixed_rows": int(take.cluster.isin(purity[purity.gt(1)].index).sum()),
        }
        rows.append(stats)
        print(stats, flush=True)
        pd.DataFrame(rows).to_csv(out / "size_filter.csv", index=False)
