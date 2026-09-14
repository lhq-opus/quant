"""根据已切好的 snapshot 中的股票顺序恢复固定递增组。

输入固定为 stock_id,snapshot_id 两列，按原始记录顺序排列。
同一轮中若较大的 ID 先出现，两只股票就不能同组；跨轮取这些冲突的并集。
用图着色寻找合法组，再用两两冲突的股票集证明组数下界。
最少组数是本次求解目标，不是用户已确认的业务组数。
"""

import argparse
import csv
import hashlib
import json
from collections import deque
from itertools import combinations, pairwise
from pathlib import Path

import numpy as np


def mask_members(mask: int):
    """整数的第 i 位代表股票 i；逐次取出最低的非零位，避免遍历空位。"""
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def build_conflicts(sequence: np.ndarray, boundaries: np.ndarray, stock_count: int):
    """汇总所有逆序对，复杂度主要随记录数及不同冲突对数量增长。

    股票索引按真实 ID 升序排列。seen 的第 i 位表示本轮已见股票 i。
    右移再左移会清空小于等于当前股票的位，留下之前出现过的较大 ID。
    整数位集合可一次处理这些逆序，避免逐轮枚举数百万股票对。
    """
    upper = [0] * stock_count
    for start, end in pairwise(boundaries):
        seen = 0
        for stock in sequence[start:end].tolist():
            upper[stock] |= (seen >> (stock + 1)) << (stock + 1)
            seen |= 1 << stock

    adjacency = upper.copy()
    for stock, neighbors in enumerate(upper):
        for other in mask_members(neighbors):
            adjacency[other] |= 1 << stock
    return adjacency, sum(neighbors.bit_count() for neighbors in upper)


def color_conflicts(adjacency: list[int]):
    """DSATUR 贪心：优先分配已经接触最多不同组的股票。

    每次选择禁用组最多的股票，同分时选冲突邻居更多、ID 更小的股票。
    分配最小可用组号，并把该组加入未分配邻居的禁用组集合。
    该方法保证合法，不一般性保证最优；最优性由后续下界证据确认。
    """
    count = len(adjacency)
    colors = [-1] * count
    degrees = [neighbors.bit_count() for neighbors in adjacency]
    forbidden = [0] * count
    remaining = set(range(count))
    while remaining:
        stock = max(
            remaining,
            key=lambda value: (forbidden[value].bit_count(), degrees[value], -value),
        )
        color = 0
        while forbidden[stock] & (1 << color):
            color += 1
        colors[stock] = color
        remaining.remove(stock)
        for other in mask_members(adjacency[stock]):
            if colors[other] < 0:
                forbidden[other] |= 1 << color

    # 组号只是标签，按每组最小 stock_id 排成 1、2、……，便于稳定复现。
    color_order = sorted(set(colors), key=colors.index)
    labels = {color: index + 1 for index, color in enumerate(color_order)}
    return [labels[color] for color in colors]


def find_clique(adjacency: list[int], target_size: int):
    """寻找两两冲突的股票集，提供组数下界；不把贪心下界当精确值。

    新成员必须与此前所有成员冲突，因此每加入一股，就对候选取邻居交集。
    当下界等于已经找到的合法组数时，最少组数得到证明，可以立即结束。
    """
    degrees = [neighbors.bit_count() for neighbors in adjacency]
    seeds = sorted(range(len(adjacency)), key=lambda value: (-degrees[value], value))
    best = []
    for seed in seeds[:16]:
        clique = [seed]
        candidates = adjacency[seed]
        while candidates:
            stock = max(
                mask_members(candidates), key=lambda value: (degrees[value], -value)
            )
            clique.append(stock)
            candidates &= adjacency[stock]
        if len(clique) > len(best):
            best = clique
        if len(best) == target_size:
            break
    return best


def prove_uniqueness(adjacency, groups, clique, stock_ids):
    """固定满大小冲突团后，只用必然的禁组传播证明唯一性。

    任意最优解中，团内各股票必须分属不同组，故可通过重命名对齐这些锚。
    若一股已经与其余 K-1 组的已确定股票冲突，它就只能在剩下的一组。
    保存按推导顺序排列的见证；若无法推到所有股票，只报告未证明唯一。
    """
    group_count = max(groups)
    if len(clique) != group_count:
        return [], False
    domains = [(1 << group_count) - 1 for _ in groups]
    excluded_by = [{} for _ in groups]
    queue = deque(clique)
    anchors = set(clique)
    processed = set()
    trace = []
    for stock in clique:
        domains[stock] = 1 << (groups[stock] - 1)

    while queue:
        stock = queue.popleft()
        if stock in processed:
            continue
        processed.add(stock)
        group = domains[stock].bit_length()
        trace.append(
            {
                "step": len(trace) + 1,
                "stock_id": int(stock_ids[stock]),
                "group_id": group,
                "anchor": stock in anchors,
                "excluded_groups": {
                    str(label): int(stock_ids[witness])
                    for label, witness in sorted(excluded_by[stock].items())
                },
            }
        )
        for other in mask_members(adjacency[stock]):
            if domains[other] & domains[stock]:
                domains[other] &= ~domains[stock]
                excluded_by[other][group] = stock
                if not domains[other]:
                    raise ValueError("冲突传播没有剩余可用组")
                if domains[other].bit_count() == 1:
                    queue.append(other)
    return trace, len(processed) == len(groups)


def audit_snapshots(sequence, boundaries, snapshot_ids, groups):
    """直接按 snapshot 原序抽取各组，核对严格递增，绝不先排序再核对。"""
    labels = np.asarray(groups)
    rows = []
    for index, (start, end) in enumerate(pairwise(boundaries)):
        stocks = sequence[start:end]
        snapshot_groups = labels[stocks]
        row = {
            "snapshot_id": int(snapshot_ids[index]),
            "stock_count": len(stocks),
            "duplicate_count": len(stocks) - len(np.unique(stocks)),
            "order_violations": 0,
        }
        for group in range(1, max(groups) + 1):
            members = stocks[snapshot_groups == group]
            row[f"group_{group}_count"] = len(members)
            row["order_violations"] += int(np.count_nonzero(np.diff(members) <= 0))
        rows.append(row)
    return rows


def find_witnesses(
    sequence, boundaries, snapshot_ids, stock_ids, groups, clique, trace
):
    """为团和唯一性推导中的冲突边找一处真实逆序及数据行号。

    positions 保存本轮每股出现位置，-1 表示缺失。只查仍缺证据的股票对，
    一旦发现较大 ID 在前，就记录位置并从待查集合删除。
    """
    index_of = {int(stock): index for index, stock in enumerate(stock_ids)}
    pairs = {tuple(sorted(pair)) for pair in combinations(clique, 2)}
    for step in trace:
        stock = index_of[step["stock_id"]]
        for witness in step["excluded_groups"].values():
            pairs.add(tuple(sorted((stock, index_of[witness]))))
    if not pairs:
        return []
    unresolved = np.asarray(sorted(pairs), dtype=np.int32)
    rows = []
    for index, (start, end) in enumerate(pairwise(boundaries)):
        positions = np.full(len(stock_ids), -1, dtype=np.int32)
        positions[sequence[start:end]] = np.arange(end - start)
        left_positions = positions[unresolved[:, 0]]
        right_positions = positions[unresolved[:, 1]]
        found = (right_positions >= 0) & (left_positions > right_positions)
        for smaller, larger in unresolved[found].tolist():
            rows.append(
                {
                    "smaller_stock_id": int(stock_ids[smaller]),
                    "larger_stock_id": int(stock_ids[larger]),
                    "smaller_group_id": groups[smaller],
                    "larger_group_id": groups[larger],
                    "snapshot_id": int(snapshot_ids[index]),
                    "larger_input_data_row": int(start + positions[larger] + 1),
                    "smaller_input_data_row": int(start + positions[smaller] + 1),
                }
            )
        unresolved = unresolved[~found]
        if not len(unresolved):
            break
    if len(unresolved):
        raise ValueError("部分证明用的冲突边未找到实际逆序")
    return sorted(
        rows, key=lambda row: (row["smaller_stock_id"], row["larger_stock_id"])
    )


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def group_stocks(input_csv: Path, output_dir: Path):
    # 输入格式已由本项目确定，不猜测表头，不清洗或重排原始记录。
    data = np.loadtxt(input_csv, delimiter=",", skiprows=1, dtype=np.int64, ndmin=2)
    stock_ids = np.unique(data[:, 0])
    sequence = np.searchsorted(stock_ids, data[:, 0]).astype(np.int32)
    boundaries = np.r_[0, np.flatnonzero(np.diff(data[:, 1])) + 1, len(data)]
    snapshot_ids = data[boundaries[:-1], 1]
    del data
    adjacency, edge_count = build_conflicts(sequence, boundaries, len(stock_ids))
    groups = color_conflicts(adjacency)
    clique = find_clique(adjacency, max(groups))
    trace, unique = prove_uniqueness(adjacency, groups, clique, stock_ids)
    audit = audit_snapshots(sequence, boundaries, snapshot_ids, groups)
    if any(row["duplicate_count"] or row["order_violations"] for row in audit):
        raise ValueError("实际 snapshot 含重复股票或组内逆序，未导出分组")
    witnesses = find_witnesses(
        sequence, boundaries, snapshot_ids, stock_ids, groups, clique, trace
    )
    mapping = [
        {"stock_id": int(stock), "group_id": group}
        for stock, group in zip(stock_ids, groups, strict=True)
    ]
    summary_rows = []
    for group in range(1, max(groups) + 1):
        members = [row["stock_id"] for row in mapping if row["group_id"] == group]
        summary_rows.append(
            {
                "group_id": group,
                "stock_count": len(members),
                "min_stock_id": min(members),
                "max_stock_id": max(members),
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "stock_groups.csv", mapping)
    write_csv(output_dir / "group_summary.csv", summary_rows)
    write_csv(output_dir / "snapshot_audit.csv", audit)
    if witnesses:
        write_csv(output_dir / "conflict_witnesses.csv", witnesses)
    certificate = {"group_count": max(groups), "unique_proved": unique, "trace": trace}
    (output_dir / "uniqueness_certificate.json").write_text(
        json.dumps(certificate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with input_csv.open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    summary = {
        "input_csv": str(input_csv.resolve()),
        "input_sha256": source_hash,
        "row_count": len(sequence),
        "snapshot_count": len(snapshot_ids),
        "stock_count": len(stock_ids),
        "conflict_pair_count": edge_count,
        "group_count": max(groups),
        "group_count_lower_bound": len(clique),
        "minimum_group_count_proved": len(clique) == max(groups),
        "unique_minimum_partition_proved": unique,
        "uniqueness_fixed_stock_count": len(trace),
        "clique_stock_ids": [int(stock_ids[stock]) for stock in clique],
        "snapshot_order_violations": sum(row["order_violations"] for row in audit),
        "snapshot_duplicate_count": sum(row["duplicate_count"] for row in audit),
        "proof_witness_pair_count": len(witnesses),
        "groups": summary_rows,
        "assumption": "组数最少；只约束每组原序子序列递增，不要求组内记录连续",
        "scope": "结论以输入snapshot切分与用户给定的组内递增规则成立为前提",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = group_stocks(args.input_csv, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
