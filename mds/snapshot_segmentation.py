"""只根据 stock_id 的出现顺序恢复 snapshot，并给原 CSV 增加 snapshot_id。

前 complete_prefix_count 轮是用户提供的完整 snapshot，用来学习股票通常
出现在一轮的什么位置。后续允许缺失，也允许小幅换序；明显从后段回到
前段时切开。重复股票说明两次出现之间必须切开，但不直接把第二次出现
当作边界，而是在两次之间寻找最明显的位置回退。

reset_threshold 是推断参数，不是业务保证。仅凭一列 ID，极稀疏的相邻
snapshot 可能无法区别；输出的是一份具体推断，不表示边界都有真实标签。
人工核查得到的必切/禁切反馈可单独传入，优先于位置回退启发式。
"""

import argparse
import csv
from itertools import pairwise
from pathlib import Path

import numpy as np


def learn_stock_positions(prefix: np.ndarray) -> np.ndarray:
    """输入完整排列，返回每只股票在一轮中的典型相对位置（0 到 1）。"""
    # prefix 使用连续编号 0..股票数-1。argsort 反转“位置 -> 股票”映射，
    # 得到每轮每只股票的位置；跨轮取中位数，降低偶尔提前/延后的影响。
    observed_positions = np.argsort(prefix, axis=1)
    stock_count = prefix.shape[1]
    return np.median(observed_positions, axis=0) / max(stock_count - 1, 1)


def segment_snapshots(
    sequence: np.ndarray,
    positions: np.ndarray,
    reset_threshold: float = 0.5,
    complete_prefix_count: int = 0,
    required_boundaries: tuple[int, ...] = (),
    forbidden_boundaries: tuple[int, ...] = (),
) -> np.ndarray:
    """返回从 0 开始的切点偏移，包括文件起点 0 和终点 len(sequence)。

    例如 [0, 5, 8] 表示数据行 1..5、6..8 两个 snapshot。
    complete_prefix_count 仅用于已知完整前缀，不推断后面也有固定长度。
    required_boundaries / forbidden_boundaries 分别指定必切 / 禁切偏移。
    偏移 N 就是在第 N 条数据后切分，行号不含表头；不按短段长度自动合并。
    """
    # 比较的是学习得到的位置，而不是 stock_id 的数值大小。
    drops = positions[sequence[:-1]] - positions[sequence[1:]]
    strong_cuts = np.flatnonzero(drops > reset_threshold) + 1
    prefix_end = complete_prefix_count * len(positions)
    required = set(required_boundaries)
    forbidden = set(forbidden_boundaries)
    if complete_prefix_count:
        # 已知完整轮的内部不得另切；最后一轮完整前缀之后可以开始缺失。
        prefix_cuts = np.arange(1, complete_prefix_count + 1) * len(positions)
        if any(cut < prefix_end and cut % len(positions) for cut in required):
            raise ValueError("必切反馈不能拆开已知完整前缀")
        required.update(int(cut) for cut in prefix_cuts if cut < len(sequence))
        strong_cuts = np.unique(
            np.concatenate((prefix_cuts, strong_cuts[strong_cuts > prefix_end]))
        )
    strong_cuts = strong_cuts[strong_cuts < len(sequence)]
    if required & forbidden:
        raise ValueError("同一边界同时被要求切分和禁止切分")
    if any(cut <= 0 or cut >= len(sequence) for cut in required | forbidden):
        raise ValueError("反馈边界必须位于第一条数据之后、最后一条数据之前")
    # 经人工核查的约束优先于回退分数，重新运行时也不能把禁切点加回来。
    strong_cuts = np.array(
        sorted((set(map(int, strong_cuts)) | required) - forbidden), dtype=np.int64
    )
    anchors = np.concatenate(([0], strong_cuts, [len(sequence)]))
    cuts = set(map(int, strong_cuts))
    last_seen = np.full(len(positions), -1, dtype=np.int64)

    # pairwise 依次取两个相邻切点，表示一段左闭右开的记录范围。
    for start, end in pairwise(anchors):
        current_start = int(start)
        for row_index in range(int(start), int(end)):
            stock = int(sequence[row_index])
            previous = int(last_seen[stock])
            if previous >= current_start:
                # 两次相同股票之间必有边界，合法候选偏移为 previous+1
                # 到 row_index（含端点）。最大回退并列时取最早者。
                # 新切点落在此前无重复的前缀内，因此被切出的左段合法；
                # 右段的历史 last_seen 仍然有效，不需要清空再重复扫描。
                low = previous + 1
                candidate_drops = drops[previous:row_index]
                excluded = [cut for cut in forbidden if low <= cut <= row_index]
                if excluded:
                    candidate_drops = candidate_drops.copy()
                    for cut in excluded:
                        candidate_drops[cut - low] = -np.inf
                    if np.all(np.isneginf(candidate_drops)):
                        raise ValueError("禁切反馈与 snapshot 内股票不得重复的约束冲突")
                cut = low + int(np.argmax(candidate_drops))
                cuts.add(cut)
                current_start = cut
            last_seen[stock] = row_index

    return np.array([0, *sorted(cuts), len(sequence)], dtype=np.int64)


def process_csv(
    input_path: str | Path,
    output_path: str | Path,
    *,
    stock_count: int = 2203,
    complete_prefix_count: int = 40,
    reset_threshold: float = 0.5,
    boundary_csv: str | Path | None = None,
    boundary_feedback_csv: str | Path | None = None,
    complete_prefix_only: bool = False,
) -> dict:
    """读取固定的单列 stock_id CSV，保持原始值和行序，写出两个字段。"""
    input_path = Path(input_path)
    output_path = Path(output_path)
    # 防止输出流覆盖仍需读取的源文件；不对业务输入做格式猜测或清洗。
    paths = [input_path.resolve(), output_path.resolve()]
    if boundary_csv is not None:
        paths.append(Path(boundary_csv).resolve())
    if len(set(paths)) != len(paths):
        raise ValueError("输入、输出和边界表必须使用不同路径")
    required_boundaries = []
    forbidden_boundaries = []
    if boundary_feedback_csv is not None:
        if Path(boundary_feedback_csv).resolve() in paths:
            raise ValueError("边界反馈文件必须与输入、输出和边界表使用不同路径")
        with Path(boundary_feedback_csv).open(newline="") as file:
            for row in csv.DictReader(file):
                cut = int(row["end_data_row"])
                if row["action"] == "require":
                    required_boundaries.append(cut)
                elif row["action"] == "forbid":
                    forbidden_boundaries.append(cut)
                else:
                    raise ValueError("边界反馈 action 必须为 require 或 forbid")

    prefix_end = stock_count * complete_prefix_count
    # 用户只要已确认部分时，只读取其声明完整的前缀。之后即使出现全集
    # 或模型一致，也不能据此证明完整 snapshot 的边界，不混入此次导出。
    stock_ids = np.loadtxt(
        input_path,
        dtype=np.int64,
        skiprows=1,
        ndmin=1,
        max_rows=prefix_end if complete_prefix_only else None,
    )
    labels, sequence = np.unique(stock_ids, return_inverse=True)
    del stock_ids
    sequence = sequence.astype(np.int32)
    prefix = sequence[:prefix_end].reshape(complete_prefix_count, stock_count)
    # 这是对训练依据的核实：若前缀不是给定股票全集的完整排列，不能继续
    # 使用“每 stock_count 行是一轮”训练。它不是重复记录的自动清洗。
    if len(labels) != stock_count or not np.all(
        np.sort(prefix, axis=1) == np.arange(stock_count)
    ):
        raise ValueError("股票总数或完整前缀与给定的训练条件不符")
    positions = learn_stock_positions(prefix)
    cuts = segment_snapshots(
        sequence,
        positions,
        reset_threshold,
        complete_prefix_count,
        tuple(required_boundaries),
        tuple(forbidden_boundaries),
    )

    # 输出前逐段独立验证硬约束；回退阈值本身不保证段内不重复。
    for start, end in pairwise(cuts):
        if len(np.unique(sequence[start:end])) != end - start:
            raise AssertionError(f"推断段内存在重复：数据行 {start + 1}..{end}")

    # 第二次流式读取保留 ID 的原始文本（包括前导零），不排序、不删行。
    # 不构建 800 万个 Python 行对象，也不把 snapshot_id 当作时间戳。
    with (
        input_path.open(newline="") as source,
        output_path.open("w", newline="") as target,
    ):
        reader = csv.reader(source)
        next(reader)
        writer = csv.writer(target)
        writer.writerow(["stock_id", "snapshot_id"])
        snapshot_id = 1
        for row_index, row in enumerate(reader):
            if row_index == len(sequence):
                break
            if row_index == cuts[snapshot_id]:
                snapshot_id += 1
            writer.writerow([row[0], snapshot_id])

    if boundary_csv is not None:
        with Path(boundary_csv).open("w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "snapshot_id",
                    "start_data_row",
                    "end_data_row",
                    "record_count",
                    "end_position_drop",
                    "end_reason",
                ]
            )
            for snapshot_id, (start, end) in enumerate(pairwise(cuts), 1):
                drop = ""
                if complete_prefix_only:
                    reason = "known_complete_prefix"
                elif end == len(sequence):
                    reason = "file_end"
                else:
                    drop = float(
                        positions[sequence[end - 1]] - positions[sequence[end]]
                    )
                    if end in required_boundaries:
                        reason = "user_required_boundary"
                    elif end <= prefix_end:
                        reason = "known_complete_prefix"
                    elif drop > reset_threshold:
                        reason = "position_reset"
                    else:
                        reason = "repeat_constraint_best_position_reset"
                writer.writerow(
                    [snapshot_id, start + 1, end, end - start, drop, reason]
                )

    lengths = np.diff(cuts)
    return {
        "row_count": len(sequence),
        "stock_count": len(labels),
        "snapshot_count": len(lengths),
        "complete_prefix_count": complete_prefix_count,
        "complete_prefix_only": complete_prefix_only,
        "reset_threshold": reset_threshold,
        "required_boundary_count": len(required_boundaries),
        "forbidden_boundary_count": len(forbidden_boundaries),
        "min_snapshot_size": int(lengths.min()),
        "median_snapshot_size": float(np.median(lengths)),
        "max_snapshot_size": int(lengths.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--stock-count", type=int, default=2203)
    parser.add_argument("--complete-prefix-count", type=int, default=40)
    parser.add_argument("--reset-threshold", type=float, default=0.5)
    parser.add_argument("--boundary-csv", type=Path)
    parser.add_argument(
        "--complete-prefix-only",
        action="store_true",
        help="只导出用户声明的完整前缀（默认前40轮），不推断后续snapshot",
    )
    parser.add_argument(
        "--boundary-feedback-csv",
        type=Path,
        help="含 end_data_row,action 的核查反馈；action 为 require 或 forbid",
    )
    args = parser.parse_args()
    summary = process_csv(
        args.input_csv,
        args.output_csv,
        stock_count=args.stock_count,
        complete_prefix_count=args.complete_prefix_count,
        reset_threshold=args.reset_threshold,
        boundary_csv=args.boundary_csv,
        boundary_feedback_csv=args.boundary_feedback_csv,
        complete_prefix_only=args.complete_prefix_only,
    )
    source = "已知完整前缀" if args.complete_prefix_only else "推断"
    print(
        f"已写出 {summary['row_count']} 行，"
        f"{source} {summary['snapshot_count']} 个 snapshot；snapshot_id 从 1 开始。"
    )


if __name__ == "__main__":
    main()
