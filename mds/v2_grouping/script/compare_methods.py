"""回读四份实际分组交付，核对完整覆盖和成员关系；不运行单元测试。"""

import ast
import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
METHODS = ROOT / "quant/mds/v2_grouping"
OUT = ROOT / "v2_grouping_exploration_20260915/validation"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / "quant/mds/data_v2.csv"
    before = sha256(source)
    data = pd.read_csv(source, dtype={"clock": "int64", "stock_id": "int64"})
    universe = pd.Index(data.stock_id.drop_duplicates().sort_values(), name="stock_id")
    checks, sizes, hashes = [], [], []
    baseline = None
    for name in ["method1", "method2", "method3", "method4"]:
        path = METHODS / name / "stock_groups.csv"
        groups = pd.read_csv(path)
        assert groups.columns.tolist() == ["stock_id", "group_id"], name
        assert len(groups) == len(universe), name
        assert groups.stock_id.is_unique and groups.notna().all().all(), name
        assert pd.Index(groups.stock_id.sort_values()).equals(universe), name
        assert groups.group_id.eq(groups.group_id.astype("int64")).all(), name
        assert groups.group_id.gt(0).all(), name
        labels = groups.set_index("stock_id").group_id.reindex(universe)
        if baseline is None:
            baseline = labels
        comparison = pd.crosstab(baseline, labels)
        # 双向均一一对应才是同一个成员划分，不把组号重命名算作变化。
        same_partition = bool(comparison.gt(0).sum(axis=0).eq(1).all()
                              and comparison.gt(0).sum(axis=1).eq(1).all())
        checks.append({"method": name, "rows": len(groups), "groups": labels.nunique(),
                       "missing_stocks": len(universe.difference(groups.stock_id)),
                       "duplicate_stocks": int(groups.stock_id.duplicated().sum()),
                       "null_group_ids": int(groups.group_id.isna().sum()),
                       "different_labels_from_method1": int(labels.ne(baseline).sum()),
                       "same_partition_as_method1": same_partition})
        sizes.append(labels.value_counts().sort_index().rename("stocks").rename_axis("group_id")
                     .reset_index().assign(method=name))
        hashes.append({"file": str(path.relative_to(ROOT)), "sha256": sha256(path)})
        assert same_partition, name
    for path in sorted(METHODS.rglob("*.py")):
        ast.parse(path.read_text(), filename=str(path))
        hashes.append({"file": str(path.relative_to(ROOT)), "sha256": sha256(path)})
    after = sha256(source)
    assert before == after
    # 与开始本轮时重新从源文件计算的指纹比较，确认未改原始数据。
    assert after == "614b05d0f0b03239c18a42284a8ec41052ff804809dda7e8b3ccdf6562cf2fda"
    hashes.insert(0, {"file": str(source.relative_to(ROOT)), "sha256": after})
    pd.DataFrame(checks).to_csv(OUT / "mapping_checks.csv", index=False)
    pd.concat(sizes, ignore_index=True).to_csv(OUT / "group_sizes.csv", index=False)
    pd.DataFrame(hashes).to_csv(OUT / "file_hashes.csv", index=False)
    pd.DataFrame([{"data_rows": len(data), "stock_count": len(universe),
                   "clock_strictly_increasing": bool(data.clock.diff().iloc[1:].gt(0).all()),
                   "first_full_prefix_unique": bool(data.iloc[:len(universe)].stock_id.is_unique),
                   "source_unchanged": before == after}]).to_csv(OUT / "source_checks.csv", index=False)
    print(pd.DataFrame(checks).to_string(index=False))
    print("Group sizes:", baseline.value_counts().sort_index().to_dict())
    print("Source SHA-256:", after)


if __name__ == "__main__":
    main()
