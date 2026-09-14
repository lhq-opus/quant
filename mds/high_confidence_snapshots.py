"""从 stock_id 顺序切分结果中导出高可信的完整候选 snapshot。

这里的“高可信”是多项顺序证据通过筛选，不是经过真实标签校准的概率。
除了比较参数，还检查整段位置分布和相邻短段，避免把稳定的短尾误切
冒充确定边界。输出保留候选编号的跳号，原始记录范围另存于复核表。
"""

import argparse
import csv
import json
from itertools import pairwise
from pathlib import Path

import numpy as np

from mds.snapshot_segmentation import learn_stock_positions, segment_snapshots


def filter_candidate_snapshots(
    sequence: np.ndarray,
    positions: np.ndarray,
    candidate_cuts: np.ndarray,
    comparison_cuts: list[np.ndarray],
    complete_prefix_count: int = 40,
    short_size: int = 100,
    edge_window: int = 17,
    max_start_position: float = 0.15,
    min_end_position: float = 0.8,
    min_position_span: float = 0.6,
) -> list[dict]:
    """逐段筛选，并为保留和排除的候选都返回原始行范围与原因。

    长度和位置门槛仅控制此次导出的可信程度，不是业务中的最小轮长度。
    short_size 标记当前或相邻的小片段，不把它们直接合并到其他 snapshot。
    """
    common = set(map(int, comparison_cuts[0]))
    for cuts in comparison_cuts[1:]:
        common.intersection_update(map(int, cuts))
    alternatives = np.unique(np.concatenate(comparison_cuts))
    sizes = np.diff(candidate_cuts)
    result = []

    for index, (start, end) in enumerate(pairwise(candidate_cuts)):
        stocks = sequence[start:end]
        phase = positions[stocks]
        window = min(edge_window, len(stocks))
        start_position = float(np.median(phase[:window]))
        end_position = float(np.median(phase[-window:]))
        # 用中间80%记录的位置跨度，避免少量首尾离群股票撑大整段跨度。
        span = float(np.quantile(phase, 0.9) - np.quantile(phase, 0.1))
        # 两端相同不代表整段一致：其他设置可能在该段内部另加一个边界。
        # searchsorted 返回插入点，两者之差就是严格落在内部的候选点数。
        internal_count = int(
            np.searchsorted(alternatives, end, side="left")
            - np.searchsorted(alternatives, start, side="right")
        )
        nearby_sizes = sizes[max(0, index - 1) : min(len(sizes), index + 2)]
        near_short = bool(np.any(nearby_sizes <= short_size))
        duplicate_count = len(stocks) - len(np.unique(stocks))
        reasons = []

        if duplicate_count:
            reasons.append("duplicate_stock")
        if index < complete_prefix_count:
            # 已知前缀来自用户给定的全量轮条件，不能因邻轮不确定而排除。
            if len(stocks) != len(positions) or duplicate_count:
                raise ValueError("已知完整前缀不满足股票全集各出现一次")
        else:
            if start not in common:
                reasons.append("unstable_start_boundary")
            if end not in common:
                reasons.append("unstable_end_boundary")
            if internal_count:
                reasons.append("alternative_internal_boundary")
            if near_short:
                reasons.append("short_segment_or_neighbor")
            if start_position > max_start_position:
                reasons.append("start_not_early")
            if end_position < min_end_position:
                reasons.append("end_not_late")
            if span < min_position_span:
                reasons.append("limited_position_span")

        result.append(
            {
                "snapshot_id": index + 1,
                "start_data_row": int(start) + 1,
                "end_data_row": int(end),
                "record_count": len(stocks),
                "selected": not reasons,
                "reason": ";".join(reasons)
                if reasons
                else "known_complete_prefix"
                if index < complete_prefix_count
                else "high_confidence_order_evidence",
                "start_position_median": start_position,
                "end_position_median": end_position,
                "position_p90_minus_p10": span,
                "alternative_internal_boundaries": internal_count,
                "start_boundary_stable": start in common,
                "end_boundary_stable": end in common,
                "short_segment_or_neighbor": near_short,
                "duplicate_stock_count": duplicate_count,
            }
        )
    return result


def process_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    review_csv: str | Path,
    *,
    stock_count: int = 2203,
    complete_prefix_count: int = 40,
    boundary_feedback_csv: str | Path | None = None,
) -> dict:
    """重新从源文件建立各位置模板，筛选后只写保留片段的两个字段。"""
    source = Path(input_csv)
    output = Path(output_csv)
    review = Path(review_csv)
    paths = [source.resolve(), output.resolve(), review.resolve()]
    if boundary_feedback_csv is not None:
        paths.append(Path(boundary_feedback_csv).resolve())
    if len(set(paths)) != len(paths):
        raise ValueError("源文件、两个输出和边界反馈必须使用不同路径")

    required = []
    forbidden = []
    if boundary_feedback_csv is not None:
        with Path(boundary_feedback_csv).open(newline="") as file:
            for row in csv.DictReader(file):
                cut = int(row["end_data_row"])
                if row["action"] == "require":
                    required.append(cut)
                elif row["action"] == "forbid":
                    forbidden.append(cut)
                else:
                    raise ValueError("反馈 action 必须为 require 或 forbid")

    raw_ids = np.loadtxt(source, dtype=np.int64, skiprows=1, ndmin=1)
    labels, sequence = np.unique(raw_ids, return_inverse=True)
    del raw_ids
    sequence = sequence.astype(np.int32)
    prefix = sequence[: stock_count * complete_prefix_count].reshape(
        complete_prefix_count, stock_count
    )
    if len(labels) != stock_count or not np.all(
        np.sort(prefix, axis=1) == np.arange(stock_count)
    ):
        raise ValueError("股票总数或完整前缀与用户给定条件不符")

    midpoint = complete_prefix_count // 2
    templates = {
        "all_prefix": learn_stock_positions(prefix),
        "first_half": learn_stock_positions(prefix[:midpoint]),
        "last_half": learn_stock_positions(prefix[midpoint:]),
    }
    models = {}
    for name, positions in templates.items():
        thresholds = (
            (0.3, 0.4, 0.5, 0.6, 0.7) if name == "all_prefix" else (0.4, 0.5, 0.6)
        )
        for threshold in thresholds:
            models[f"{name}_{threshold}"] = segment_snapshots(
                sequence,
                positions,
                threshold,
                complete_prefix_count,
                tuple(required),
                tuple(forbidden),
            )
    cuts = models["all_prefix_0.5"]
    decisions = filter_candidate_snapshots(
        sequence,
        templates["all_prefix"],
        cuts,
        list(models.values()),
        complete_prefix_count,
    )
    with review.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(decisions[0]))
        writer.writeheader()
        writer.writerows(decisions)

    selected = [row["selected"] for row in decisions]
    with source.open(newline="") as source_file, output.open("w", newline="") as target:
        reader = csv.reader(source_file)
        next(reader)
        writer = csv.writer(target)
        writer.writerow(["stock_id", "snapshot_id"])
        segment = 0
        for row_index, row in enumerate(reader):
            if row_index == cuts[segment + 1]:
                segment += 1
            if selected[segment]:
                # 保留候选编号，因此可能跳号；不能让略过的范围看似不存在。
                writer.writerow([row[0], segment + 1])

    kept_count = sum(selected)
    kept_rows = sum(row["record_count"] for row in decisions if row["selected"])
    return {
        "input_rows": len(sequence),
        "candidate_snapshots": len(decisions),
        "selected_snapshots": kept_count,
        "selected_rows": kept_rows,
        "excluded_candidates": len(decisions) - kept_count,
        "excluded_rows": len(sequence) - kept_rows,
        "retained_row_fraction": kept_rows / len(sequence),
        "model_snapshot_counts": {name: len(cuts) - 1 for name, cuts in models.items()},
        "source_row_numbers_exclude_header": True,
        "snapshot_ids_retain_candidate_numbers_and_may_have_gaps": True,
        "meaning": "高可信顺序推断；未用真实标签校准概率",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("review_csv", type=Path)
    parser.add_argument("--boundary-feedback-csv", type=Path)
    parser.add_argument("--stock-count", type=int, default=2203)
    parser.add_argument("--complete-prefix-count", type=int, default=40)
    args = parser.parse_args()
    result = process_csv(
        args.input_csv,
        args.output_csv,
        args.review_csv,
        stock_count=args.stock_count,
        complete_prefix_count=args.complete_prefix_count,
        boundary_feedback_csv=args.boundary_feedback_csv,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
