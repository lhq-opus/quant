"""用 30 秒周期和固定股票顺序识别全量扫描，保留其余记录。

数据中可见的扫描段允许缺项；不能把附近出现过的缺项股票补删掉。
所有表处理使用 pandas，不读取任何历史六组映射。
"""

from pathlib import Path

import pandas as pd


METHOD = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
INPUT = ROOT / "quant/mds/data_v2.csv"
OUTPUT = ROOT / "v2_grouping_exploration_20260916/method6"


def scan_template(data):
    initial = data.iloc[:data.stock_id.nunique()].copy()
    # 首行明确归入 0 号片段，不依赖带空值的整数转换。
    initial["scan_group"] = initial.clock.diff().gt(100_000).cumsum()
    initial["scan_rank"] = initial.groupby("scan_group", sort=False).cumcount()
    initial["scan_size"] = initial.groupby("scan_group").stock_id.transform("size")
    assert initial.stock_id.nunique() == len(initial)
    assert initial.scan_group.nunique() == 30
    return initial.set_index("stock_id")


def ordered_runs(work, allow_skips):
    jump = work.scan_rank.diff()
    rank_break = jump.le(0) if allow_skips else jump.ne(1)
    work["run_id"] = (work.scan_group.ne(work.scan_group.shift())
                      | rank_break | work.clock.diff().gt(200_000)).cumsum()
    return work.groupby("run_id", sort=False).agg(
        scan_group=("scan_group", "first"), rows=("stock_id", "size"),
        expected_rows=("scan_size", "first"), first_rank=("scan_rank", "first"),
        last_rank=("scan_rank", "last"), first_clock=("clock", "first"),
        last_clock=("clock", "last"), first_row=("source_row", "first"),
        last_row=("source_row", "last"),
    )


def recover(data, schedule_radius=2_000_000, fragment_radius=200_000):
    template = scan_template(data)
    work = data.assign(source_row=data.index + 1)
    for name in ["scan_group", "scan_rank", "scan_size"]:
        work[name] = work.stock_id.map(template[name])

    # 完整、连续的 30 组模板提供时钟锚；以实测周期校正全天累积漂移。
    exact = ordered_runs(work, allow_skips=False)
    anchors = exact.loc[exact.rows.eq(exact.expected_rows)].copy()
    intervals = anchors.groupby("scan_group").first_clock.diff()
    period = intervals.loc[intervals.between(29_000_000, 31_000_000)].median()
    starts = template.groupby("scan_group").clock.first()
    offsets = starts - starts.iloc[0]
    anchors["scan_cycle"] = ((anchors.first_clock - anchors.scan_group.map(starts))
                             / period).round().astype("int64")
    anchors["scan_slot"] = anchors.scan_cycle * 30 + anchors.scan_group
    assert not anchors.scan_slot.duplicated().any()
    bases = (anchors.first_clock - anchors.scan_group.map(offsets)).groupby(
        anchors.scan_cycle).median()

    runs = ordered_runs(work, allow_skips=True)
    runs["scan_cycle"] = ((runs.first_clock - runs.scan_group.map(starts))
                          / period).round().astype("int64")
    runs["scan_slot"] = runs.scan_cycle * 30 + runs.scan_group
    runs["expected_clock"] = runs.scan_cycle.map(bases) + runs.scan_group.map(offsets)
    runs["clock_residual"] = runs.first_clock - runs.expected_clock
    candidates = runs.loc[runs.clock_residual.abs().le(schedule_radius)
                          & runs.scan_slot.between(0, anchors.scan_slot.max())].copy()
    candidates["abs_residual"] = candidates.clock_residual.abs()
    candidates = candidates.sort_values(
        ["scan_slot", "rows", "abs_residual"], ascending=[True, False, True])
    best = candidates.drop_duplicates("scan_slot").sort_values("scan_slot").copy()
    assert best.scan_slot.to_list() == list(range(int(anchors.scan_slot.max()) + 1))
    assert best.rows.div(best.expected_rows).ge(0.7).all(), "存在无法可靠定位的扫描组"
    second = candidates.loc[~candidates.index.isin(best.index)].groupby("scan_slot").rows.max()
    best["runner_up_rows"] = best.scan_slot.map(second).fillna(0).astype("int64")
    assert best.rows.gt(best.runner_up_rows).all(), "最长有序段有并列候选"

    # 被其他更新穿插打断的头尾：只接回至少 3 条的有序残段。
    # 一两条附近记录无法仅凭这两列辨别来源，保留并单独列为边界候选。
    by_slot = best.set_index("scan_slot")
    before = (runs.last_rank.lt(runs.scan_slot.map(by_slot.first_rank))
              & runs.last_row.lt(runs.scan_slot.map(by_slot.first_row))
              & runs.last_clock.ge(runs.scan_slot.map(by_slot.first_clock) - fragment_radius))
    after = (runs.first_rank.gt(runs.scan_slot.map(by_slot.last_rank))
             & runs.first_row.gt(runs.scan_slot.map(by_slot.last_row))
             & runs.first_clock.le(runs.scan_slot.map(by_slot.last_clock) + fragment_radius))
    nearby = runs.loc[before | after].copy()
    fragments = nearby.loc[nearby.rows.ge(3)].copy()
    unresolved = nearby.loc[nearby.rows.lt(3)].copy()
    all_runs = pd.concat([best.assign(reason="periodic_ordered_run"),
                          fragments.assign(reason="ordered_fragment")])
    assert not all_runs.index.duplicated().any()
    selected = work.loc[work.run_id.isin(all_runs.index)].copy()
    selected["scan_slot"] = selected.run_id.map(all_runs.scan_slot)
    selected["reason"] = selected.run_id.map(all_runs.reason)
    # 删除的每个扫描组仍然是首轮模板的严格递增子序列。
    assert selected.scan_slot.is_monotonic_increasing
    assert selected.groupby("scan_slot").scan_rank.diff().dropna().gt(0).all()
    assert not selected.duplicated(["scan_slot", "stock_id"]).any()
    selected = selected[["source_row", "clock", "stock_id", "scan_slot", "reason"]]
    best["removed_rows"] = best.scan_slot.map(selected.groupby("scan_slot").size())
    best["missing_template_rows"] = best.expected_rows - best.removed_rows
    best["scan_cycle"] = best.scan_slot // 30
    return selected, best, unresolved, template.reset_index(), period


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    removed, scans, unresolved, template, period = recover(data)
    keep = ~(data.index + 1).isin(removed.source_row)
    remaining = data.loc[keep].copy()
    remaining.insert(0, "source_row", remaining.index + 1)
    assert len(removed) + len(remaining) == len(data)
    assert not removed.source_row.duplicated().any()
    assert remaining.clock.is_monotonic_increasing
    remaining.to_csv(OUTPUT / "filtered_updates.csv", index=False)
    removed.to_csv(OUTPUT / "removed_full_updates.csv", index=False)
    scans.to_csv(OUTPUT / "scan_windows.csv", index_label="run_id")
    unresolved.to_csv(OUTPUT / "unresolved_scan_boundaries.csv", index_label="run_id")
    template.to_csv(OUTPUT / "scan_template.csv", index=False)
    pd.DataFrame([{"input_rows": len(data), "removed_rows": len(removed),
                   "remaining_rows": len(remaining), "scan_slots": len(scans),
                   "observed_period": period,
                   "missing_template_rows": scans.missing_template_rows.sum(),
                   "unresolved_boundary_runs": len(unresolved)}]).to_csv(
                       OUTPUT / "filter_summary.csv", index=False)
    print(f"扫描组次 {len(scans)}，实测周期 {period:g} clock 单位")
    print(f"删除 {len(removed)} 行，保留 {len(remaining)} 行")
    print(f"来源未定的短边界段 {len(unresolved)} 个，保留在过滤结果中")


if __name__ == "__main__":
    main()
