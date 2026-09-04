"""把每只股票表示成跨 snapshot 的相对 clock 向量，并做简单分组。

从 ``quant/`` 目录运行：

    python -m mds.relative_clock_grouping \
        INPUT.csv VECTORS.csv GROUPS.csv VECTORS.png

输出：

- ``VECTORS.csv``：每行一只股票，每个 ``time`` 是一个向量维度；
- ``GROUPS.csv``：``stock_id,group_id`` 映射；
- ``VECTORS.png``：按推断组排序后的相对 clock 向量热图。

这是一版便于观察向量结构的简单 baseline，不是最终分组算法。默认参数是
探索性启发式，不是已经确认的业务阈值。
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

REQUIRED_COLUMNS = ["clock", "stock_id", "time"]
DEFAULT_MAX_CLOCK_GAP_US = 1_000
DEFAULT_MIN_CLOSE_SNAPSHOTS = 2


def build_relative_clock_vectors(data: pd.DataFrame) -> pd.DataFrame:
    """生成 ``stock_id × time`` 的相对 clock 向量表。

    输入已经满足两个前提：

    1. 同一个 ``time`` 表示同一个 snapshot；
    2. 每个 snapshot 内已经按 ``clock`` 升序排列。

    本函数还采用“同一只股票在同一个 snapshot 至多一行”的显式假设。
    ``pivot`` 在该假设被违反时会直接报错，不会静默挑选其中一行。
    """

    relative_data = data.copy()

    # transform("first") 会把每个 snapshot 的第一个 clock 广播回该 snapshot
    # 的每一行，所以结果与原表具有完全相同的行数和索引。
    snapshot_start = relative_data.groupby("time", sort=False)["clock"].transform(
        "first"
    )

    # 以 snapshot 第一条记录为零点。由于输入已按 clock 排序，相对 clock
    # 应从 0 开始并且非负，单位仍然是微秒。
    relative_data["relative_clock"] = relative_data["clock"] - snapshot_start

    # 保存 time 在输入中的首次出现顺序。pivot 默认可能重排列标签，最后用
    # reindex 恢复这个顺序，保证第 1...n 维与原始 snapshot 顺序一致。
    snapshot_order = relative_data["time"].drop_duplicates().tolist()
    vectors = relative_data.pivot(
        index="stock_id",
        columns="time",
        values="relative_clock",
    )

    # 股票未出现在某个 snapshot 时，该维保持 <NA>。绝不能填 0，因为 0 的
    # 真实含义是“它恰好是该 snapshot 的第一条记录”，不是“没有数据”。
    return vectors.reindex(columns=snapshot_order).sort_index().astype("Int64")


def group_relative_clock_vectors(
    vectors: pd.DataFrame,
    *,
    max_clock_gap_us: int = DEFAULT_MAX_CLOCK_GAP_US,
    min_close_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
) -> pd.DataFrame:
    """根据相对 clock 向量的重复接近程度生成简单固定分组。

    观察依据是：同组股票在共同出现的 snapshot 中，其相对 clock 应反复接近；
    不同组即使偶尔同时到达，也不应在大多数共同维度上持续接近。

    两只股票满足以下条件时连接一条相似边：

    - 至少在 ``min_close_snapshots`` 个共同维度上，clock 差不大于
      ``max_clock_gap_us``；
    - 接近次数至少占两只股票共同出现次数的一半。

    最终以相似图的连通分量作为组。缺失维度不算正证据，也不算负证据；共同
    数据不足的股票会保留为单例。连通分量存在链式误合并风险，所以这只是
    透明、易检查的第一版，而不是最终统计方案。
    """

    if max_clock_gap_us < 0:
        raise ValueError("max_clock_gap_us must be non-negative")
    if min_close_snapshots < 1:
        raise ValueError("min_close_snapshots must be at least 1")

    ordered_vectors = vectors.sort_index()
    stock_ids = ordered_vectors.index.astype(str).tolist()
    adjacency: dict[str, set[str]] = {stock_id: set() for stock_id in stock_ids}

    # 对每只股票记录它出现过的维度，用集合交集即可得到两只股票共同出现次数。
    active_snapshots: dict[str, set[int]] = {stock_id: set() for stock_id in stock_ids}
    close_counts: Counter[tuple[str, str]] = Counter()

    # 不枚举全市场所有股票对。每个向量维度内先按相对 clock 排序，再用滑动
    # 窗口只生成 clock 差不超过阈值的候选对。通常这远少于 O(股票数²)，同时
    # 仍然直接使用 n 维向量中每一个 snapshot 的坐标。
    for snapshot_position, time_value in enumerate(ordered_vectors.columns):
        observed = ordered_vectors[time_value].dropna().sort_values(kind="stable")
        observed_stocks = observed.index.astype(str).tolist()
        observed_clocks = observed.to_numpy(dtype="int64")

        for stock_id in observed_stocks:
            active_snapshots[stock_id].add(snapshot_position)

        window_start = 0
        for current_position, current_clock in enumerate(observed_clocks):
            while current_clock - observed_clocks[window_start] > max_clock_gap_us:
                window_start += 1

            for previous_position in range(window_start, current_position):
                pair = tuple(
                    sorted(
                        (
                            observed_stocks[previous_position],
                            observed_stocks[current_position],
                        )
                    )
                )
                close_counts[pair] += 1

    # 一次接近只是弱证据。只有重复接近，并且接近次数至少占共同出现机会的一半，
    # 才建立相似边；不同组偶尔同时推送通常会被其余共同维度稀释。
    for (first_stock, second_stock), close_count in sorted(close_counts.items()):
        common_count = len(
            active_snapshots[first_stock] & active_snapshots[second_stock]
        )
        if close_count < min_close_snapshots or 2 * close_count < common_count:
            continue

        adjacency[first_stock].add(second_stock)
        adjacency[second_stock].add(first_stock)

    # 用简单的深度优先遍历寻找连通分量。按 stock_id 稳定遍历和排序，使相同
    # 输入每次产生相同 group_id；group_id 从 1 开始。
    visited: set[str] = set()
    rows: list[tuple[str, int]] = []
    group_id = 0

    for first_stock in stock_ids:
        if first_stock in visited:
            continue

        group_id += 1
        component: list[str] = []
        stack = [first_stock]
        visited.add(first_stock)

        while stack:
            stock_id = stack.pop()
            component.append(stock_id)

            for neighbor in sorted(adjacency[stock_id], reverse=True):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)

        rows.extend((stock_id, group_id) for stock_id in sorted(component))

    return pd.DataFrame(rows, columns=["stock_id", "group_id"])


def plot_relative_clock_vectors(
    vectors: pd.DataFrame,
    groups: pd.DataFrame,
    output_png: Path | str,
) -> None:
    """绘制按 group_id 排序的向量热图；本函数不负责推断分组。"""

    # 可视化函数只接收已经算好的 vectors 和 groups，不调用分组函数。这样以后
    # 更换算法时，画图逻辑可以原样复用；反过来，分组也完全不依赖 matplotlib。
    ordered_groups = groups.sort_values(
        ["group_id", "stock_id"],
        ignore_index=True,
    )
    stock_order = ordered_groups["stock_id"].tolist()
    ordered_vectors = vectors.reindex(stock_order)
    matrix = ordered_vectors.to_numpy(dtype="float64", na_value=np.nan)

    # masked_invalid 让缺失维度使用单独颜色显示，而不是错误地画成相对 clock=0。
    masked_matrix = np.ma.masked_invalid(matrix)
    color_map = colormaps["viridis"].with_extremes(bad="#d9d9d9")

    figure_width = min(24.0, max(10.0, len(vectors.columns) / 20))
    figure_height = min(24.0, max(5.0, len(vectors.index) / 8))
    figure = Figure(figsize=(figure_width, figure_height))
    FigureCanvasAgg(figure)
    axis = figure.subplots()

    image = axis.imshow(
        masked_matrix,
        aspect="auto",
        interpolation="nearest",
        cmap=color_map,
    )
    axis.set_title("Relative clock vectors ordered by inferred group")
    axis.set_xlabel("snapshot (time)")
    axis.set_ylabel("stock / inferred group")

    # snapshot 很多时只显示少量均匀采样的 x 轴标签，避免文字完全重叠。
    snapshot_count = len(vectors.columns)
    tick_count = min(snapshot_count, 12)
    x_positions = np.unique(
        np.linspace(0, snapshot_count - 1, num=tick_count, dtype=int)
    )
    axis.set_xticks(x_positions)
    axis.set_xticklabels(
        [str(vectors.columns[position]) for position in x_positions],
        rotation=45,
        ha="right",
    )

    # 股票较少时逐只标注；股票很多时，每个组只在中间位置标一个 group_id。
    if len(stock_order) <= 60:
        y_labels = [
            f"G{group_id} {stock_id}"
            for stock_id, group_id in ordered_groups[
                ["stock_id", "group_id"]
            ].itertuples(index=False, name=None)
        ]
        axis.set_yticks(range(len(stock_order)))
        axis.set_yticklabels(y_labels)
    else:
        group_sizes = ordered_groups.groupby("group_id", sort=True).size()
        group_ends = group_sizes.cumsum().to_numpy()
        group_starts = np.r_[0, group_ends[:-1]]
        group_centers = (group_starts + group_ends - 1) / 2
        axis.set_yticks(group_centers)
        axis.set_yticklabels([f"Group {group_id}" for group_id in group_sizes.index])

    # 横线明确标出相邻推断组的边界。
    group_sizes = ordered_groups.groupby("group_id", sort=True).size()
    for boundary in group_sizes.cumsum().iloc[:-1]:
        axis.axhline(float(boundary) - 0.5, color="white", linewidth=1.2)

    color_bar = figure.colorbar(image, ax=axis)
    color_bar.set_label("relative clock (microseconds); gray = missing")
    figure.tight_layout()
    figure.savefig(output_png, dpi=150, bbox_inches="tight")


def process_csv(
    input_csv: Path | str,
    vectors_csv: Path | str,
    groups_csv: Path | str,
    plot_png: Path | str,
    *,
    max_clock_gap_us: int = DEFAULT_MAX_CLOCK_GAP_US,
    min_close_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """读取 CSV，依次构造向量、分组并写出三个结果文件。"""

    # 输入格式由业务保证正确，因此只读取真正需要的三列，不增加多层清洗逻辑。
    data = pd.read_csv(
        input_csv,
        usecols=REQUIRED_COLUMNS,
        dtype={"clock": "int64", "stock_id": "string", "time": "string"},
    )
    vectors = build_relative_clock_vectors(data)
    groups = group_relative_clock_vectors(
        vectors,
        max_clock_gap_us=max_clock_gap_us,
        min_close_snapshots=min_close_snapshots,
    )

    vectors.reset_index().to_csv(vectors_csv, index=False)
    groups.to_csv(groups_csv, index=False)
    plot_relative_clock_vectors(vectors, groups, plot_png)
    return vectors, groups


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数。"""

    parser = argparse.ArgumentParser(
        description="构造股票的 snapshot 相对 clock 向量、分组并绘制热图。"
    )
    parser.add_argument("input_csv", type=Path, help="输入 market data CSV")
    parser.add_argument("vectors_csv", type=Path, help="输出 n 维向量 CSV")
    parser.add_argument("groups_csv", type=Path, help="输出股票分组 CSV")
    parser.add_argument("plot_png", type=Path, help="输出向量热图 PNG")
    parser.add_argument(
        "--max-clock-gap-us",
        type=int,
        default=DEFAULT_MAX_CLOCK_GAP_US,
        help="单个 snapshot 内视为接近的最大 clock 差（默认：%(default)s）",
    )
    parser.add_argument(
        "--min-close-snapshots",
        type=int,
        default=DEFAULT_MIN_CLOSE_SNAPSHOTS,
        help="建立相似边所需的最少接近 snapshot 数（默认：%(default)s）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行命令行程序并打印结果摘要。"""

    arguments = build_argument_parser().parse_args(argv)
    vectors, groups = process_csv(
        arguments.input_csv,
        arguments.vectors_csv,
        arguments.groups_csv,
        arguments.plot_png,
        max_clock_gap_us=arguments.max_clock_gap_us,
        min_close_snapshots=arguments.min_close_snapshots,
    )

    print(f"snapshot 数：{vectors.shape[1]}")
    print(f"股票数：{vectors.shape[0]}")
    print(f"最终分组数：{groups['group_id'].nunique()}")
    print(f"向量 CSV：{arguments.vectors_csv}")
    print(f"分组 CSV：{arguments.groups_csv}")
    print(f"热图 PNG：{arguments.plot_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
