"""按 snapshot 分组，再合并为全天固定分组的第一版 baseline。"""

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import pandas as pd

from .clock_delta import find_abrupt_increase


REQUIRED_COLUMNS = ["clock", "stock_id", "time"]
OUTPUT_COLUMNS = ["stock_id", "group_id"]


def group_one_snapshot(snapshot: pd.DataFrame, threshold: int) -> list[list[str]]:
    """按照相邻 ``clock`` 差值，对一个 snapshot 中的股票分组。

    处理过程很直接：先按 ``clock`` 从小到大排序；如果当前行与上一行的
    ``clock`` 差值大于或等于 ``threshold``，当前行就作为一个新组的
    第一只股票。返回值形如 ``[["1", "3"], ["2", "6"]]``。

    这是单个 snapshot 的分组方法。以后想替换局部分组算法时，只需实现
    相同输入输出形式的新函数，再传给 ``infer_fixed_groups``。
    """

    ordered = snapshot.sort_values("clock", kind="stable").copy()

    # 第一行没有上一行，diff 的结果为 NaN，ge(threshold) 会得到 False，
    # 所以它自然属于第 0 个局部组。后面每遇到一个大 gap，组号就加 1。
    ordered["local_group_id"] = ordered["clock"].diff().ge(threshold).cumsum()

    return [
        group["stock_id"].astype(str).tolist()
        for _, group in ordered.groupby("local_group_id", sort=False)
    ]


def group_all_snapshots(
    data: pd.DataFrame,
    threshold: int,
    snapshot_grouping_method=group_one_snapshot,
) -> dict[str, list[list[str]]]:
    """逐个处理所有 ``time``，保留每个 snapshot 的局部分组结果。

    ``snapshot_grouping_method`` 就是第一层可插拔接口。默认使用相邻
    ``clock`` gap，也可以直接传入另一个 ``方法(snapshot, threshold)``。
    """

    snapshot_groups: dict[str, list[list[str]]] = {}

    for time_value, snapshot in data.groupby("time", sort=False):
        snapshot_groups[str(time_value)] = snapshot_grouping_method(
            snapshot,
            threshold,
        )

    return snapshot_groups


def _stock_pair(stock_a: str, stock_b: str) -> tuple[str, str]:
    """把股票对固定为同一个顺序，方便放进 set。"""

    return tuple(sorted((stock_a, stock_b)))


def group_by_permanent_separation(
    snapshot_groups: dict[str, list[list[str]]],
    stock_ids: list[str],
) -> list[list[str]]:
    """使用“只要被分开过，就永远不同组”的规则生成最终分组。

    第一步遍历所有 snapshot。只要两只股票在某个 snapshot 的两个不同
    局部组中，就把这对股票记入 ``different_pairs``。

    第二步按股票 ID 顺序逐只放入最终组。股票会进入第一个与它没有
    ``different_pairs`` 冲突的组；如果所有已有组都冲突，就新建一个组。
    这是一版简单、确定性的贪心 baseline，不追求全局最优。

    这是第二层可插拔接口。以后修改最终分组规则时，可以写一个接收
    ``snapshot_groups, stock_ids`` 并返回 ``list[list[str]]`` 的新函数，
    然后传给 ``infer_fixed_groups``，无需修改 snapshot 分组代码。
    """

    different_pairs: set[tuple[str, str]] = set()

    # 一个 snapshot 中任意两个不同局部组之间的股票对，都是永久冲突对。
    for groups in snapshot_groups.values():
        for first_group, second_group in combinations(groups, 2):
            for stock_a in first_group:
                for stock_b in second_group:
                    different_pairs.add(_stock_pair(stock_a, stock_b))

    final_groups: list[list[str]] = []

    # 按固定顺序执行 first-fit，保证相同输入每次得到相同结果。
    for stock_id in sorted(stock_ids):
        for final_group in final_groups:
            can_join = all(
                _stock_pair(stock_id, member) not in different_pairs
                for member in final_group
            )
            if can_join:
                final_group.append(stock_id)
                break
        else:
            final_groups.append([stock_id])

    return final_groups


def infer_fixed_groups(
    data: pd.DataFrame,
    threshold: int,
    snapshot_grouping_method=group_one_snapshot,
    final_grouping_method=group_by_permanent_separation,
) -> tuple[dict[str, list[list[str]]], list[list[str]]]:
    """依次执行“每个 snapshot 分组”和“全天最终分组”两个阶段。

    两个方法都通过参数传入，因此可以彼此独立替换。返回值同时保留全部
    snapshot 的中间结果和最终结果，便于直接检查每一层发生了什么。
    """

    snapshot_groups = group_all_snapshots(
        data,
        threshold,
        snapshot_grouping_method,
    )
    stock_ids = data["stock_id"].astype(str).unique().tolist()
    final_groups = final_grouping_method(snapshot_groups, stock_ids)
    return snapshot_groups, final_groups


def detect_threshold(data: pd.DataFrame) -> int:
    """沿用已有的异常 gap 方法，为没有手工阈值的运行提供默认值。"""

    all_gaps: list[pd.Series] = []

    for _, snapshot in data.groupby("time", sort=False):
        ordered = snapshot.sort_values("clock", kind="stable")
        all_gaps.append(ordered["clock"].diff().dropna().astype("int64"))

    gaps = pd.concat(all_gaps, ignore_index=True)
    candidate = find_abrupt_increase(pd.DataFrame({"delta_clock": gaps}))

    if candidate is None:
        raise ValueError("没有自动找到 clock gap 阈值，请通过 --threshold 指定")

    return candidate.delta_clock


def groups_to_mapping(final_groups: list[list[str]]) -> pd.DataFrame:
    """把按组排列的结果转换成 ``stock_id,group_id`` CSV 结构。"""

    rows = [
        (stock_id, group_id)
        for group_id, group in enumerate(final_groups, start=1)
        for stock_id in group
    ]
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def print_final_groups(final_groups: list[list[str]]) -> None:
    """在终端直观打印组数以及每一组包含的股票。"""

    print(f"最终分组数：{len(final_groups)}")
    for group_id, group in enumerate(final_groups, start=1):
        print(f"第 {group_id} 组（{len(group)} 只）：{', '.join(group)}")


def process_csv(
    input_csv: Path | str,
    output_csv: Path | str,
    threshold: int | None = None,
    snapshot_grouping_method=group_one_snapshot,
    final_grouping_method=group_by_permanent_separation,
) -> tuple[dict[str, list[list[str]]], list[list[str]], int]:
    """读取固定格式 CSV，执行两层分组并写出最终映射。"""

    # 输入格式由业务保证固定，因此只按已知表头读取真正需要的三列。
    data = pd.read_csv(
        input_csv,
        usecols=REQUIRED_COLUMNS,
        dtype={"clock": "int64", "stock_id": "string", "time": "string"},
    )

    if threshold is None:
        threshold = detect_threshold(data)

    snapshot_groups, final_groups = infer_fixed_groups(
        data,
        threshold,
        snapshot_grouping_method,
        final_grouping_method,
    )
    groups_to_mapping(final_groups).to_csv(output_csv, index=False)
    return snapshot_groups, final_groups, threshold


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数。"""

    parser = argparse.ArgumentParser(
        description="先对每个 time snapshot 分组，再生成全天固定股票分组。"
    )
    parser.add_argument("input_csv", type=Path, help="输入 market data CSV")
    parser.add_argument("output_csv", type=Path, help="输出 stock 分组 CSV")
    parser.add_argument(
        "--threshold",
        type=int,
        help="snapshot 内切分组的 clock gap 阈值；不传则沿用自动检测",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行命令行程序并打印最终分组。"""

    arguments = build_argument_parser().parse_args(argv)
    _, final_groups, threshold = process_csv(
        arguments.input_csv,
        arguments.output_csv,
        arguments.threshold,
    )

    print(f"clock gap 阈值：{threshold} 微秒")
    print_final_groups(final_groups)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
