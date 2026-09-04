"""使用余弦相似度恢复股票固定分组。

V2 只负责分组，不再生成向量 CSV 或图片。从 ``quant/`` 目录运行：

    python -m mds.relative_clock_grouping_v2 INPUT.csv GROUPS.csv

输入仍然只使用 ``clock``、``stock_id``、``time`` 三列；输出是
``stock_id,group_id`` 映射。

这是一版用于观察余弦相似度效果的 baseline。余弦相似度只比较向量方向，
忽略绝对大小；默认阈值是可调启发式参数，不是已经确认的业务事实。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from mds.relative_clock_grouping import (
    DEFAULT_MIN_CLOSE_RATE,
    DEFAULT_MIN_CLOSE_SNAPSHOTS,
    REQUIRED_COLUMNS,
    build_relative_clock_vectors,
)

DEFAULT_MIN_COSINE_SIMILARITY = 0.99


def calculate_cosine_similarity_matrix(
    vectors: pd.DataFrame,
    *,
    min_common_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_common_rate: float = DEFAULT_MIN_CLOSE_RATE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """计算每两只股票在共同有效维度上的余弦相似度。

    对股票 ``i`` 和 ``j``，先过滤任意一方缺失的维度，只保留共同维度集合
    ``K_ij``，再计算：

    ``similarity(i, j) = dot(x_i, x_j) / (norm(x_i) * norm(x_j))``

    点积和两个范数都只使用 ``K_ij``。这样某只股票没有出现在一个 snapshot
    时，该维度既不增加相似度，也不降低相似度。

    余弦相似度通常位于 ``[-1, 1]``：

    - 越接近 1，两个向量方向越一致；
    - 接近 0，方向关系较弱；
    - 越接近 -1，方向越相反。

    本项目的相对 clock 通常非负，因此实际结果多数落在 ``[0, 1]``。需要注意，
    `[1, 2]` 与 `[100, 200]` 的相似度是 1；余弦相似度不会认为二者的绝对
    clock 差很大。这是 V2 有意实验的性质，也是它可能误合并不同组的风险。

    为避免只凭一两个共同维度判断，还要求：

    - ``common_count >= min_common_snapshots``；
    - ``common_count / min(active_i, active_j) >= min_common_rate``。

    不满足证据门槛的股票对返回 ``NaN``，表示无法判断，而不是不相似。
    函数同时返回共同维度数量矩阵，便于测试和后续分析。
    """

    if min_common_snapshots < 1:
        raise ValueError("min_common_snapshots must be at least 1")
    if not 0 <= min_common_rate <= 1:
        raise ValueError("min_common_rate must be between 0 and 1")

    ordered_vectors = vectors.sort_index()
    stock_ids = ordered_vectors.index.astype(str).tolist()
    values = ordered_vectors.to_numpy(dtype="float64", na_value=np.nan)

    # present 中非缺失为 1、缺失为 0。present @ present.T 的第 (i, j) 个元素
    # 就是股票 i、j 同时出现的维度数。
    present = (~np.isnan(values)).astype("float64")
    common_counts = (present @ present.T).astype("int64")
    active_counts = present.sum(axis=1)

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

    # 缺失位置临时填 0 只用于矩阵运算。因为另一侧的缺失也被 present 控制，
    # 这些 0 不会作为真实相对 clock 参与某一股票对的共同维度计算。
    filled_values = np.nan_to_num(values, nan=0.0)

    # zeros_filled @ zeros_filled.T 得到每对股票在共同维度上的点积。
    dot_products = filled_values @ filled_values.T

    # squared_norms_on_common[i, j] 表示股票 i 只在 i、j 共同维度上的平方和。
    # 它与转置位置 [j, i] 分别构成余弦公式分母中的两个范数。
    squared_values = filled_values * filled_values
    squared_norms_on_common = squared_values @ present.T
    denominators = np.sqrt(squared_norms_on_common * squared_norms_on_common.T)

    similarities = np.full(dot_products.shape, np.nan, dtype="float64")
    normal_pairs = enough_evidence & (denominators > 0)
    np.divide(
        dot_products,
        denominators,
        out=similarities,
        where=normal_pairs,
    )

    # 零向量的余弦在数学上没有定义。这里采用明确、可复现的 baseline 约定：
    # 双方在所有共同维度上都为 0，视为完全相同，similarity=1；只有一方为
    # 零向量，视为没有方向相似性，similarity=0。
    first_norm_is_zero = squared_norms_on_common == 0
    second_norm_is_zero = squared_norms_on_common.T == 0
    both_zero = enough_evidence & first_norm_is_zero & second_norm_is_zero
    one_zero = enough_evidence & (first_norm_is_zero ^ second_norm_is_zero)
    similarities[both_zero] = 1.0
    similarities[one_zero] = 0.0

    # 浮点运算可能产生 1.0000000000000002 一类微小越界，裁剪回理论区间。
    np.clip(similarities, -1.0, 1.0, out=similarities)
    np.fill_diagonal(similarities, 1.0)

    labels = pd.Index(stock_ids, name="stock_id")
    similarity_frame = pd.DataFrame(similarities, index=labels, columns=labels)
    common_count_frame = pd.DataFrame(common_counts, index=labels, columns=labels)
    return similarity_frame, common_count_frame


def group_by_cosine_similarity(
    similarity_matrix: pd.DataFrame,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
) -> pd.DataFrame:
    """按组内全配对相似度约束执行稳定 first-fit 分组。

    候选股票只有与已有组内的每一只股票都满足
    ``similarity >= min_cosine_similarity`` 时，才能进入该组。NaN 表示证据不足，
    也不满足入组要求。

    例如 ``a-b`` 和 ``b-c`` 通过阈值，但 ``a-c`` 不通过，则结果不会是
    ``{a,b,c}``。按稳定股票顺序处理时，通常得到 ``{a,b}`` 与 ``{c}``。
    """

    if not -1 <= min_cosine_similarity <= 1:
        raise ValueError("min_cosine_similarity must be between -1 and 1")

    # 排序保证相同输入每次都按相同顺序执行 first-fit。
    ordered_similarities = similarity_matrix.sort_index()
    ordered_similarities = ordered_similarities.reindex(
        columns=ordered_similarities.index
    )
    stock_ids = ordered_similarities.index.astype(str).tolist()
    groups: list[list[str]] = []

    for stock_id in stock_ids:
        for group in groups:
            # all(...) 是本版最关键的约束：不是与组内任意一只相似即可，而是
            # 必须与每个已有成员都达到阈值。NaN 与阈值比较会得到 False。
            can_join = all(
                ordered_similarities.loc[stock_id, member] >= min_cosine_similarity
                for member in group
            )
            if can_join:
                group.append(stock_id)
                break
        else:
            groups.append([stock_id])

    # 这是简单且确定的 greedy clique partition，不保证得到全局最少组数。
    # 如果一只股票同时满足多个组，它进入最先建立的那个组。
    rows = [
        (stock_id, group_id)
        for group_id, group in enumerate(groups, start=1)
        for stock_id in group
    ]
    return pd.DataFrame(rows, columns=["stock_id", "group_id"])


def group_relative_clock_vectors_v2(
    vectors: pd.DataFrame,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
    min_common_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_common_rate: float = DEFAULT_MIN_CLOSE_RATE,
) -> pd.DataFrame:
    """V2 主入口：计算余弦相似度，再执行组内全配对分组。"""

    similarity_matrix, _ = calculate_cosine_similarity_matrix(
        vectors,
        min_common_snapshots=min_common_snapshots,
        min_common_rate=min_common_rate,
    )
    return group_by_cosine_similarity(
        similarity_matrix,
        min_cosine_similarity=min_cosine_similarity,
    )


# 暴露简短同名入口，调用方可以继续写 group_relative_clock_vectors(...)。
group_relative_clock_vectors = group_relative_clock_vectors_v2


def process_csv(
    input_csv: Path | str,
    groups_csv: Path | str,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
    min_common_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_common_rate: float = DEFAULT_MIN_CLOSE_RATE,
) -> pd.DataFrame:
    """读取 market data CSV，只输出最终股票分组 CSV。"""

    data = pd.read_csv(
        input_csv,
        usecols=REQUIRED_COLUMNS,
        dtype={"clock": "int64", "stock_id": "string", "time": "string"},
    )
    vectors = build_relative_clock_vectors(data)
    groups = group_relative_clock_vectors_v2(
        vectors,
        min_cosine_similarity=min_cosine_similarity,
        min_common_snapshots=min_common_snapshots,
        min_common_rate=min_common_rate,
    )
    groups.to_csv(groups_csv, index=False)
    return groups


def build_argument_parser() -> argparse.ArgumentParser:
    """创建纯分组命令行参数。"""

    parser = argparse.ArgumentParser(
        description="按共同有效维度的余弦相似度恢复股票固定分组。"
    )
    parser.add_argument("input_csv", type=Path, help="输入 market data CSV")
    parser.add_argument("groups_csv", type=Path, help="输出股票分组 CSV")
    parser.add_argument(
        "--min-cosine-similarity",
        type=float,
        default=DEFAULT_MIN_COSINE_SIMILARITY,
        help="组内任意股票对的最小余弦相似度（默认：%(default)s）",
    )
    parser.add_argument(
        "--min-common-snapshots",
        type=int,
        default=DEFAULT_MIN_CLOSE_SNAPSHOTS,
        help="计算有效相似度所需的最少共同 snapshot 数（默认：%(default)s）",
    )
    parser.add_argument(
        "--min-common-rate",
        type=float,
        default=DEFAULT_MIN_CLOSE_RATE,
        help="较少出现股票所需的最小共同维度比例（默认：%(default)s）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行命令行程序并打印结果摘要。"""

    arguments = build_argument_parser().parse_args(argv)
    groups = process_csv(
        arguments.input_csv,
        arguments.groups_csv,
        min_cosine_similarity=arguments.min_cosine_similarity,
        min_common_snapshots=arguments.min_common_snapshots,
        min_common_rate=arguments.min_common_rate,
    )

    print(f"股票数：{len(groups)}")
    print(f"最终分组数：{groups['group_id'].nunique()}")
    print(f"分组 CSV：{arguments.groups_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
