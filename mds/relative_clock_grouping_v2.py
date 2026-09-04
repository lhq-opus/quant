"""使用归一化向量距离观察并恢复股票固定分组。

这个脚本是 ``relative_clock_grouping.py`` 的 V2 baseline。V1 保持不变；
V2 使用完全相同的命令行输入和输出，因此只需要替换模块名：

    python -m mds.relative_clock_grouping_v2 \
        INPUT.csv VECTORS.csv GROUPS.csv VECTORS.png

三个输出文件的格式与 V1 相同：

- ``VECTORS.csv``：每行一只股票，每个 ``time`` 是一个向量维度；
- ``GROUPS.csv``：``stock_id,group_id`` 固定分组映射；
- ``VECTORS.png``：阈值切组前的层次树和归一化距离热图。

V2 只是一版便于观察的距离 baseline。默认阈值和共同维度要求都是启发式
参数，不是已经确认的业务事实。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.metrics.pairwise import nan_euclidean_distances

from mds.relative_clock_grouping import (
    DEFAULT_MAX_CLOCK_GAP_US,
    DEFAULT_MIN_CLOSE_RATE,
    DEFAULT_MIN_CLOSE_SNAPSHOTS,
    REQUIRED_COLUMNS,
    build_relative_clock_vectors,
)


def calculate_normalized_vector_distances(
    vectors: pd.DataFrame,
    *,
    min_common_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_common_rate: float = DEFAULT_MIN_CLOSE_RATE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """计算股票向量之间的归一化欧氏距离。

    对股票 ``i`` 和 ``j``，先只保留双方都有值的维度集合 ``K_ij``。如果共同
    维度数为 ``k``，V2 的距离定义为：

    ``distance(i, j) = sqrt(sum((x_i - x_j)²)) / sqrt(k)``

    它也可以写成 ``sqrt(mean((x_i - x_j)²))``，即 RMSE。与原始欧氏距离
    相比，除以 ``sqrt(k)`` 后不会因为一对股票恰好多了很多共同维度就自然变大，
    而且结果单位仍然是微秒，方便使用微秒阈值解释。

    仅做 ``sqrt(k)`` 归一化仍有一个风险：两只股票可能只共同出现一两次，碰巧
    距离很小。因此这里还设置两道“证据是否足够”的门槛：

    - ``common_count >= min_common_snapshots``；
    - ``common_rate >= min_common_rate``，其中
      ``common_rate = common_count / min(active_i, active_j)``。

    第二个比例表示：以两只股票中出现次数较少的那只为基准，有多少观测能够与
    另一只股票比较。没有通过门槛的股票对距离保留为 ``NaN``，表示“证据不足”，
    而不是武断地赋成一个很大的负面距离。

    返回两个同形矩阵：归一化距离矩阵和共同维度数量矩阵。行列标签都是按
    ``stock_id`` 排序后的股票 ID。
    """

    if min_common_snapshots < 1:
        raise ValueError("min_common_snapshots must be at least 1")
    if not 0 <= min_common_rate <= 1:
        raise ValueError("min_common_rate must be between 0 and 1")

    ordered_vectors = vectors.sort_index()
    stock_ids = ordered_vectors.index.astype(str).tolist()
    values = ordered_vectors.to_numpy(dtype="float64", na_value=np.nan)

    # sklearn 的 nan_euclidean_distances 会逐对忽略任一方缺失的维度，并按
    # “总维度数 / 共同维度数”放大平方距离。再除以 sqrt(总维度数)，正好得到
    # 上面定义的 L2 / sqrt(k)，也就是共同维度上的 RMSE。
    total_dimensions = values.shape[1]
    distances = nan_euclidean_distances(values) / np.sqrt(total_dimensions)

    # present 中出现记为 1、缺失记为 0。矩阵乘法后，第 (i, j) 个元素就是
    # 两只股票都出现的维度数量，比逐个 Python 股票对求交集更直接。
    present = (~np.isnan(values)).astype("int32")
    common_counts = present @ present.T
    active_counts = present.sum(axis=1)

    # 以较少出现的股票为分母。比如 a 出现 1000 次、b 出现 2000 次，双方共同
    # 出现 900 次，则 common_rate = 900 / 1000 = 0.9。
    possible_common_counts = np.minimum.outer(active_counts, active_counts)
    common_rates = np.divide(
        common_counts,
        possible_common_counts,
        out=np.zeros_like(common_counts, dtype="float64"),
        where=possible_common_counts > 0,
    )

    enough_evidence = (common_counts >= min_common_snapshots) & (
        common_rates >= min_common_rate
    )

    # 对角线表示股票与自身的距离，固定为 0；其余证据不足的位置保留 NaN。
    # 这样后续画图会显示灰色，阈值分组也不会把它当成已确认的远距离关系。
    distances[~enough_evidence] = np.nan
    np.fill_diagonal(distances, 0.0)

    labels = pd.Index(stock_ids, name="stock_id")
    distance_frame = pd.DataFrame(distances, index=labels, columns=labels)
    common_count_frame = pd.DataFrame(common_counts, index=labels, columns=labels)
    return distance_frame, common_count_frame


def build_single_linkage(
    distance_matrix: pd.DataFrame,
    *,
    max_clock_gap_us: float,
) -> np.ndarray:
    """把两两距离矩阵转换成一棵 single-linkage 层次树。

    这里还没有产生最终 ``group_id``。层次树只描述“从最近的股票对开始，关系
    如何逐步连接”；下一步才会使用距离阈值切开这棵树。

    证据不足的距离是 NaN，而 SciPy 层次聚类要求输入都是有限值。为了不把缺失
    误当作接近，构树时临时把 NaN 放到所有已观测距离和分组阈值之外。原始距离
    矩阵仍保留 NaN，用于热图显示和解释。
    """

    if max_clock_gap_us < 0:
        raise ValueError("max_clock_gap_us must be non-negative")

    stock_count = len(distance_matrix)
    if stock_count <= 1:
        return np.empty((0, 4), dtype="float64")

    distances = distance_matrix.to_numpy(dtype="float64", copy=True)
    off_diagonal = ~np.eye(stock_count, dtype=bool)
    observed_distances = distances[off_diagonal & np.isfinite(distances)]
    largest_observed = (
        float(observed_distances.max()) if observed_distances.size else 0.0
    )

    # unavailable_distance 必须严格大于阈值。这样按 max_clock_gap_us 切树时，
    # 一个完全没有共同维度的股票对不会被直接合并。
    farthest_relevant_distance = max(largest_observed, float(max_clock_gap_us), 1.0)
    unavailable_distance = farthest_relevant_distance * 1.05 + 1.0
    distances[~np.isfinite(distances)] = unavailable_distance
    np.fill_diagonal(distances, 0.0)

    # squareform 把对称方阵压缩为 SciPy linkage 需要的一维上三角距离数组。
    condensed_distances = squareform(distances, checks=False)

    # single linkage 的含义是两个集合之间取最近成员距离。按阈值切树后，它等价
    # 于“距离不超过阈值就连边，再取连通分量”，所以允许 a-b-c 的间接证据链。
    # optimal_ordering 只调整叶子展示顺序，使热图中相近股票尽量靠在一起，不改变
    # 树的合并距离和最终分组。
    return linkage(
        condensed_distances,
        method="single",
        optimal_ordering=True,
    )


def plot_normalized_distance_clusters(
    distance_matrix: pd.DataFrame,
    linkage_matrix: np.ndarray,
    output_png: Path | str,
    *,
    max_clock_gap_us: float,
) -> None:
    """在阈值切组之前绘制层次树和归一化距离热图。

    本函数只画连续距离结构，不接收也不生成 ``group_id``。上半部分的层次树
    展示股票关系如何从近到远连接，红色虚线表示稍后使用的切组阈值；下半部分
    按层次树叶子顺序展示距离矩阵。如果存在明显聚簇，热图对角线附近应出现
    若干颜色较深的方块。灰色格子代表共同维度证据不足。
    """

    stock_ids = distance_matrix.index.astype(str).tolist()
    stock_count = len(stock_ids)

    figure_width = min(24.0, max(10.0, stock_count / 10))
    figure_height = min(24.0, max(8.0, stock_count / 8))
    figure = Figure(figsize=(figure_width, figure_height))
    FigureCanvasAgg(figure)
    tree_axis, heatmap_axis = figure.subplots(
        2,
        1,
        gridspec_kw={"height_ratios": [1, 3]},
    )

    if stock_count > 1:
        # 此时只画树，还没有调用 fcluster 生成最终分组。所有树枝使用同一种颜色，
        # 防止绘图函数暗中把某次着色误解成已经确定的 group_id。
        tree_result = dendrogram(
            linkage_matrix,
            ax=tree_axis,
            no_labels=True,
            link_color_func=lambda _: "#4c72b0",
        )
        leaf_order = tree_result["leaves"]
    else:
        tree_axis.text(0.5, 0.5, "only one stock", ha="center", va="center")
        tree_axis.set_xticks([])
        tree_axis.set_yticks([])
        leaf_order = [0]

    tree_axis.axhline(
        max_clock_gap_us,
        color="#c44e52",
        linestyle="--",
        linewidth=1.2,
        label=f"distance threshold = {max_clock_gap_us:g} us",
    )
    tree_axis.set_title("Single-linkage tree before threshold grouping")
    tree_axis.set_ylabel("normalized RMSE (microseconds)")
    tree_axis.legend(loc="upper right")

    ordered_distances = distance_matrix.iloc[leaf_order, leaf_order]
    matrix = ordered_distances.to_numpy(dtype="float64")
    masked_matrix = np.ma.masked_invalid(matrix)
    color_map = colormaps["viridis"].with_extremes(bad="#d9d9d9")

    # 极少数巨大距离可能压缩其余颜色差异；仅在显示时用 95% 分位作为色阶上限。
    # 距离计算、层次树和阈值分组仍使用未经裁剪的原始数值。
    finite_distances = matrix[np.isfinite(matrix)]
    display_max = (
        float(np.quantile(finite_distances, 0.95))
        if finite_distances.size
        else float(max_clock_gap_us)
    )
    display_max = max(display_max, 1.0)

    image = heatmap_axis.imshow(
        masked_matrix,
        aspect="auto",
        interpolation="nearest",
        cmap=color_map,
        vmin=0.0,
        vmax=display_max,
    )
    heatmap_axis.set_title("Pairwise normalized vector distances")
    heatmap_axis.set_xlabel("stock ordered by the hierarchy")
    heatmap_axis.set_ylabel("stock ordered by the hierarchy")

    if stock_count <= 60:
        ordered_stock_ids = [stock_ids[position] for position in leaf_order]
        positions = range(stock_count)
        heatmap_axis.set_xticks(positions)
        heatmap_axis.set_yticks(positions)
        heatmap_axis.set_xticklabels(ordered_stock_ids, rotation=90)
        heatmap_axis.set_yticklabels(ordered_stock_ids)
    else:
        heatmap_axis.set_xticks([])
        heatmap_axis.set_yticks([])

    color_bar = figure.colorbar(image, ax=heatmap_axis)
    color_bar.set_label("normalized RMSE (microseconds); gray = insufficient data")
    figure.tight_layout()
    figure.savefig(output_png, dpi=150, bbox_inches="tight")


def cut_single_linkage_groups(
    stock_ids: list[str],
    linkage_matrix: np.ndarray,
    *,
    max_clock_gap_us: float,
) -> pd.DataFrame:
    """在指定距离阈值切开层次树，返回稳定的股票分组映射。"""

    if len(stock_ids) == 1:
        raw_group_ids = np.array([1], dtype="int64")
    else:
        # criterion="distance" 表示：一个组内由层次树连接起来的最大合并距离不能
        # 超过 max_clock_gap_us。对 single linkage，这等价于阈值图的连通分量。
        raw_group_ids = fcluster(
            linkage_matrix,
            t=max_clock_gap_us,
            criterion="distance",
        )

    # SciPy 返回的簇编号不承诺符合 stock_id 顺序。这里按已排序股票第一次遇到
    # 某个簇的顺序重新编号，使 group_id 从 1 开始且每次运行结果一致。
    stable_group_ids: dict[int, int] = {}
    rows: list[tuple[str, int]] = []
    for stock_id, raw_group_id in zip(stock_ids, raw_group_ids, strict=True):
        raw_group_id = int(raw_group_id)
        if raw_group_id not in stable_group_ids:
            stable_group_ids[raw_group_id] = len(stable_group_ids) + 1
        rows.append((stock_id, stable_group_ids[raw_group_id]))

    return pd.DataFrame(rows, columns=["stock_id", "group_id"])


def group_relative_clock_vectors_v2(
    vectors: pd.DataFrame,
    *,
    max_clock_gap_us: int = DEFAULT_MAX_CLOCK_GAP_US,
    min_close_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_close_rate: float = DEFAULT_MIN_CLOSE_RATE,
) -> pd.DataFrame:
    """V2 可替换入口：接收与 V1 相同的参数，返回相同的分组表。

    参数名称为保持可直接替换而沿用 V1，但 V2 中含义略有变化：

    - ``max_clock_gap_us``：归一化 RMSE 的最大组内距离；
    - ``min_close_snapshots``：计算有效距离所需的最少共同维度数；
    - ``min_close_rate``：较少出现股票中至少有多少比例能与另一只比较。

    这个入口不画图，保证分组函数可以被单独调用和测试。独立脚本的
    ``process_csv`` 会复用相同的三个核心步骤，并在切组前调用绘图函数。
    """

    distance_matrix, _ = calculate_normalized_vector_distances(
        vectors,
        min_common_snapshots=min_close_snapshots,
        min_common_rate=min_close_rate,
    )
    linkage_matrix = build_single_linkage(
        distance_matrix,
        max_clock_gap_us=max_clock_gap_us,
    )
    return cut_single_linkage_groups(
        distance_matrix.index.astype(str).tolist(),
        linkage_matrix,
        max_clock_gap_us=max_clock_gap_us,
    )


# 除了带 ``_v2`` 的明确名称，也暴露与 V1 完全相同的函数名。这样调用方只需把
# import 的模块从 ``relative_clock_grouping`` 换成 ``relative_clock_grouping_v2``，
# 后面的函数调用不需要修改。
group_relative_clock_vectors = group_relative_clock_vectors_v2


def process_csv(
    input_csv: Path | str,
    vectors_csv: Path | str,
    groups_csv: Path | str,
    plot_png: Path | str,
    *,
    max_clock_gap_us: int = DEFAULT_MAX_CLOCK_GAP_US,
    min_close_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_close_rate: float = DEFAULT_MIN_CLOSE_RATE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """读取 CSV，画阈值切组前的距离结构，再输出 V2 分组。"""

    data = pd.read_csv(
        input_csv,
        usecols=REQUIRED_COLUMNS,
        dtype={"clock": "int64", "stock_id": "string", "time": "string"},
    )
    vectors = build_relative_clock_vectors(data)
    distance_matrix, _ = calculate_normalized_vector_distances(
        vectors,
        min_common_snapshots=min_close_snapshots,
        min_common_rate=min_close_rate,
    )
    linkage_matrix = build_single_linkage(
        distance_matrix,
        max_clock_gap_us=max_clock_gap_us,
    )

    # 用户希望先通过图观察向量是否形成聚簇，再执行阈值切组。这里有意把 plot
    # 调用放在 cut_single_linkage_groups 之前；绘图函数完全不知道最终 group_id。
    plot_normalized_distance_clusters(
        distance_matrix,
        linkage_matrix,
        plot_png,
        max_clock_gap_us=max_clock_gap_us,
    )
    groups = cut_single_linkage_groups(
        distance_matrix.index.astype(str).tolist(),
        linkage_matrix,
        max_clock_gap_us=max_clock_gap_us,
    )

    vectors.reset_index().to_csv(vectors_csv, index=False)
    groups.to_csv(groups_csv, index=False)
    return vectors, groups


def build_argument_parser() -> argparse.ArgumentParser:
    """创建与 V1 兼容的命令行参数。"""

    parser = argparse.ArgumentParser(
        description="计算股票向量归一化距离、画层次图并按阈值分组。"
    )
    parser.add_argument("input_csv", type=Path, help="输入 market data CSV")
    parser.add_argument("vectors_csv", type=Path, help="输出 n 维向量 CSV")
    parser.add_argument("groups_csv", type=Path, help="输出股票分组 CSV")
    parser.add_argument("plot_png", type=Path, help="输出切组前距离聚簇图 PNG")
    parser.add_argument(
        "--max-clock-gap-us",
        type=int,
        default=DEFAULT_MAX_CLOCK_GAP_US,
        help="归一化 RMSE 的最大组内距离（默认：%(default)s）",
    )
    parser.add_argument(
        "--min-close-snapshots",
        type=int,
        default=DEFAULT_MIN_CLOSE_SNAPSHOTS,
        help="计算有效距离所需的最少共同 snapshot 数（默认：%(default)s）",
    )
    parser.add_argument(
        "--min-close-rate",
        type=float,
        default=DEFAULT_MIN_CLOSE_RATE,
        help="较少出现股票所需的最小共同维度比例（默认：%(default)s）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行命令行程序并打印与 V1 一致的结果摘要。"""

    arguments = build_argument_parser().parse_args(argv)
    vectors, groups = process_csv(
        arguments.input_csv,
        arguments.vectors_csv,
        arguments.groups_csv,
        arguments.plot_png,
        max_clock_gap_us=arguments.max_clock_gap_us,
        min_close_snapshots=arguments.min_close_snapshots,
        min_close_rate=arguments.min_close_rate,
    )

    print(f"snapshot 数：{vectors.shape[1]}")
    print(f"股票数：{vectors.shape[0]}")
    print(f"最终分组数：{groups['group_id'].nunique()}")
    print(f"向量 CSV：{arguments.vectors_csv}")
    print(f"分组 CSV：{arguments.groups_csv}")
    print(f"切组前距离图 PNG：{arguments.plot_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
