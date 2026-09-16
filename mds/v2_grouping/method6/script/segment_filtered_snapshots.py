"""从过滤后的原序记录恢复候选三秒 snapshot，不读取任何分组映射。

gap 只用于划出候选轮次；边界稳定、无重复且前后均有三秒节奏的轮次
才用于后续顺序分析。异常片段保留在完整输出中，不强行认证边界。
所有 CSV 及表处理均使用 pandas。
"""

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[5]
DATA = ROOT / "v2_grouping_exploration_20260916/method6"
OUTPUT = DATA / "snapshot_order"
MAIN_GAP = 800_000  # 微秒：0.8 秒，不是同组判定阈值。
BOUNDARY_GAPS = [650_000, 700_000, 750_000, 800_000,
                 850_000, 900_000, 1_000_000]


def summarize(data, ids):
    return data.groupby(ids, sort=False).agg(
        rows=("stock_id", "size"), unique_stocks=("stock_id", "nunique"),
        first_clock=("clock", "first"), last_clock=("clock", "last"),
        first_source_row=("source_row", "first"),
        last_source_row=("source_row", "last"),
    )


def segment(data):
    assert data.source_row.is_monotonic_increasing
    assert data.source_row.is_unique and data.clock.is_monotonic_increasing
    gap = data.clock.diff()
    ids = gap.gt(MAIN_GAP).cumsum() + 1
    ids.name = "snapshot_id"
    ranges = summarize(data, ids)
    ranges["span_us"] = ranges.last_clock - ranges.first_clock
    ranges["start_interval_us"] = ranges.first_clock.diff()
    ranges["start_local"] = pd.to_datetime(
        ranges.first_clock, unit="us", utc=True).dt.tz_convert("Asia/Shanghai")

    # 这些阈值内都存在的切点才是稳定边界；第一行显式处理。
    stable_cut = gap.gt(max(BOUNDARY_GAPS))
    stable_cut.iloc[0] = True
    ranges["stable_start"] = stable_cut.groupby(ids).first()
    ranges["stable_end"] = ranges.stable_start.shift(-1, fill_value=False)
    possible_internal_cut = gap.gt(min(BOUNDARY_GAPS)) & ~gap.gt(MAIN_GAP)
    ranges["uncertain_internal_cuts"] = possible_internal_cut.groupby(ids).sum()
    ranges["no_duplicate_stock"] = ranges.rows.eq(ranges.unique_stocks)
    ranges["regular_cadence"] = (
        ranges.start_interval_us.between(2_700_000, 3_300_000)
        & ranges.start_interval_us.shift(-1).between(2_700_000, 3_300_000)
    )
    ranges["use_for_order"] = (
        ranges.stable_start & ranges.stable_end
        & ranges.uncertain_internal_cuts.eq(0)
        & ranges.no_duplicate_stock & ranges.span_us.lt(2_200_000)
        & ranges.regular_cadence
    )
    reasons = pd.Series("", index=ranges.index)
    exclusions = {
        "unstable_start": ~ranges.stable_start,
        "unstable_end": ~ranges.stable_end,
        "possible_internal_boundary": ranges.uncertain_internal_cuts.gt(0),
        "duplicate_stock": ~ranges.no_duplicate_stock,
        "long_span": ranges.span_us.ge(2_200_000),
        "irregular_cadence": ~ranges.regular_cadence,
    }
    for reason, mask in exclusions.items():
        reasons.loc[mask] = reasons.loc[mask] + reason + ";"
    ranges["exclusion_reasons"] = reasons.str.rstrip(";")

    records = data.assign(snapshot_id=ids)
    records["position"] = records.groupby("snapshot_id", sort=False).cumcount() + 1
    records["use_for_order"] = records.snapshot_id.map(ranges.use_for_order)
    return records, ranges


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(DATA / "filtered_updates.csv")
    records, ranges = segment(data)
    regular = records.loc[records.use_for_order].drop(columns="use_for_order")
    # 原始值、行数及行序不变；只追加标签，不重新排序或删除异常记录。
    assert records[data.columns].equals(data)
    assert not regular.duplicated(["snapshot_id", "stock_id"]).any()
    records.to_csv(OUTPUT / "snapshot_records.csv", index=False)
    regular.to_csv(OUTPUT / "regular_snapshot_records.csv", index=False)
    ranges.to_csv(OUTPUT / "snapshot_ranges.csv")

    coverage = data.groupby("stock_id").agg(
        filtered_rows=("stock_id", "size"), first_clock=("clock", "min"),
        last_clock=("clock", "max"))
    coverage["regular_snapshots"] = regular.groupby("stock_id").snapshot_id.nunique(
        ).reindex(coverage.index, fill_value=0)
    coverage.to_csv(OUTPUT / "stock_snapshot_coverage.csv")
    outside = records.loc[records.stock_id.isin(
        coverage.index[coverage.regular_snapshots.eq(0)])].copy()
    outside["clock_local"] = pd.to_datetime(
        outside.clock, unit="us", utc=True).dt.tz_convert("Asia/Shanghai")
    outside.to_csv(OUTPUT / "stocks_outside_regular_snapshots.csv", index=False)

    sensitivity = []
    for threshold in sorted(set(BOUNDARY_GAPS + [100_000, 200_000, 300_000,
                                                500_000, 1_200_000, 1_500_000])):
        summary = summarize(data, data.clock.diff().gt(threshold).cumsum() + 1)
        span = summary.last_clock - summary.first_clock
        sensitivity.append({
            "gap_us": threshold, "candidate_snapshots": len(summary),
            "snapshots_with_duplicates": int(summary.rows.ne(summary.unique_stocks).sum()),
            "median_rows": summary.rows.median(), "max_rows": summary.rows.max(),
            "median_span_us": span.median(), "max_span_us": span.max(),
            "spans_over_three_seconds": int(span.gt(3_000_000).sum()),
        })
    pd.DataFrame(sensitivity).to_csv(OUTPUT / "segmentation_thresholds.csv", index=False)
    print(f"候选 {len(ranges):,} 轮；用于顺序分析 {int(ranges.use_for_order.sum()):,} 轮，"
          f"{len(regular):,} 行、{regular.stock_id.nunique():,} 股。", flush=True)
    print(f"输出：{OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
