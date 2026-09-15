"""实际数据参数、留出与弱成员证据核验；不运行单元测试。"""
from time import perf_counter

import pandas as pd

from grid_spectral import (EVIDENCE, INPUT, ROOT, canonical, centered_support,
                           grid_affinity, learn_core, member_scores, spectral_groups)


def finish(data, core, radius=10000, min_core=20):
    support, observations, screening = centered_support(data, core, radius, min_core)
    full = pd.concat([core, support.group_id]).sort_index().astype("int64")
    missing = pd.Index(data.stock_id.unique()).difference(full.index)
    conflict = support.groups.gt(1).sum()
    full = canonical(full)
    return full, {"core_stocks": len(core), "supported_stocks": len(support),
                  "support_records": len(observations), "missing_stocks": len(missing),
                  "conflicting_stocks": int(conflict)}, observations, screening


def run():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    data = pd.read_csv(INPUT)
    reference = pd.read_csv(ROOT / "quant/mds/v2_grouping/method1/stock_groups.csv").set_index("stock_id").group_id
    summary = []
    # 网格宽度、平移次数都重新从原始 CSV 计算；既有标签仅作事后比较。
    baseline = None
    for width, offsets in [(20000,4),(25000,4),(30000,1),(30000,2),(30000,4),
                           (30000,8),(40000,4),(50000,4)]:
        core, provisional, weights, scores, spectrum = learn_core(data, width, offsets)
        labels, details, _, _ = finish(data, core)
        stats = {"kind": "grid", "width": width, "offsets": offsets,
                 "spectral_groups": provisional.nunique(), **details,
                 "same_as_method1": bool(labels.equals(reference)),
                 "elapsed_seconds": perf_counter()-started}
        summary.append(stats)
        if width == 30000 and offsets == 4:
            baseline = (core, weights, scores)
        print(stats, flush=True)
        pd.DataFrame(summary).to_csv(EVIDENCE / "parameter_checks.csv", index=False)

    core, weights, scores = baseline
    completed, _, _, _ = finish(data, core)
    # 直接检验更强的全称说法，不能把核心筛选条件推广到全部最终成员。
    final_scores = member_scores(weights, completed)
    final_scores.to_csv(EVIDENCE / "final_group_average_scores.csv")
    final_scores.loc[final_scores.margin.le(0)].to_csv(EVIDENCE / "average_rule_counterexamples.csv")
    # 阈值与局部窗口检查复用同一张已计算图，避免反复拟合同一模型。
    for threshold in [.03,.04,.05,.06]:
        selected = scores.group_id.loc[scores.within.ge(threshold) & scores.margin.gt(0)]
        labels, details, _, _ = finish(data, selected)
        summary.append({"kind": "core_threshold", "core_threshold": threshold,
                        **details, "same_as_method1": bool(labels.equals(reference))})
    for radius, min_core in [(3000,20),(5000,20),(10000,10),(10000,20),
                            (10000,30),(10000,40),(15000,20),(20000,20)]:
        labels, details, _, _ = finish(data, core, radius, min_core)
        summary.append({"kind": "local_window", "radius": radius, "min_core": min_core,
                        **details, "same_as_method1": bool(labels.equals(reference))})
    pd.DataFrame(summary).to_csv(EVIDENCE / "parameter_checks.csv", index=False)

    half = len(data)//2
    first, last = data.iloc[:half], data.iloc[half:]
    first_core, _, _, _, _ = learn_core(first)
    last_weights = grid_affinity(last)
    frozen_scores = member_scores(last_weights, first_core)
    labels, details, records, _ = finish(last, first_core)
    holdout = {"training_core_stocks": len(first_core),
               "training_core_groups": first_core.nunique(),
               "heldout_stocks_compared": len(frozen_scores),
               "nonpositive_margins": int(frozen_scores.margin.le(0).sum()),
               "minimum_margin": frozen_scores.margin.min(),
               "minimum_ratio": frozen_scores.within.div(frozen_scores.outside).min(),
               **details, "same_complete_labels": bool(labels.equals(reference))}
    pd.DataFrame([holdout]).to_csv(EVIDENCE / "holdout_checks.csv", index=False)
    frozen_scores.to_csv(EVIDENCE / "holdout_member_scores.csv")
    records.to_csv(EVIDENCE / "holdout_completion.csv", index=False)
    print("HOLDOUT", holdout, flush=True)

    # 半片与四分片独立求解；缺少补全证据的片不伪装成完整恢复。
    slices = {"first_half": first, "last_half": last}
    for i in range(4):
        slices[f"quarter{i+1}"] = data.iloc[i*len(data)//4:(i+1)*len(data)//4]
    slice_checks = []
    for name, selected_data in slices.items():
        selected_core, provisional, _, _, _ = learn_core(selected_data)
        labels, details, _, _ = finish(selected_data, selected_core)
        stats = {"sample": name, "spectral_groups": provisional.nunique(),
                 "core_mismatches": int(selected_core.ne(reference.loc[selected_core.index]).sum()),
                 **details, "assigned_mismatches": int(labels.ne(reference.loc[labels.index]).sum())}
        slice_checks.append(stats)
        print("SLICE", stats, flush=True)
    pd.DataFrame(slice_checks).to_csv(EVIDENCE / "slice_checks.csv", index=False)
    print("Total seconds:", perf_counter()-started, flush=True)


if __name__ == "__main__":
    run()
