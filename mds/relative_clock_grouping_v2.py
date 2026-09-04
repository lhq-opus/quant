"""使用余弦相似度恢复股票固定分组。

V2 只负责分组，不再生成向量 CSV 或图片。从 ``quant/`` 目录运行：

    python -m mds.relative_clock_grouping_v2 INPUT.csv GROUPS.csv

输入仍然只使用 ``clock``、``stock_id``、``time`` 三列；输出是
``stock_id,group_id`` 映射。

这是一版用于观察余弦相似度效果的 baseline。余弦相似度只比较向量方向，
忽略绝对大小；默认阈值是可调启发式参数，不是已经确认的业务事实。

默认使用 ``minimize`` 尽量减少满足组内全配对约束的组数；也可以用
``--grouping-method cosine_greedy``，按余弦相似度从高到低贪心合并。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from mds.relative_clock_grouping import (
    DEFAULT_EXACT_SEARCH_NODE_LIMIT,
    DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    DEFAULT_MIN_CLOSE_RATE,
    DEFAULT_MIN_CLOSE_SNAPSHOTS,
    REQUIRED_COLUMNS,
    build_relative_clock_vectors,
    minimize_compatibility_groups,
)

DEFAULT_MIN_COSINE_SIMILARITY = 0.99
COSINE_GROUPING_METHOD_MINIMIZE = "minimize"
COSINE_GROUPING_METHOD_GREEDY = "cosine_greedy"
COSINE_GROUPING_METHODS = (
    COSINE_GROUPING_METHOD_MINIMIZE,
    COSINE_GROUPING_METHOD_GREEDY,
)
DEFAULT_COSINE_GROUPING_METHOD = COSINE_GROUPING_METHOD_MINIMIZE


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


def build_cosine_compatibility_matrix(
    similarity_matrix: pd.DataFrame,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
) -> pd.DataFrame:
    """把余弦相似度矩阵转换成“能否进入同组”的布尔矩阵。

    两只股票的余弦相似度达到阈值时才兼容。``NaN`` 表示共同维度证据不足，
    因而也判为不兼容。矩阵理论上应当对称；这里保守地要求 ``(i, j)`` 与
    ``(j, i)`` 两个方向都通过，避免外部传入的非对称矩阵造成单向入组。
    对角线固定为 ``True``，因为一只股票单独成组总是合法。
    """

    if not -1 <= min_cosine_similarity <= 1:
        raise ValueError("min_cosine_similarity must be between -1 and 1")

    ordered = similarity_matrix.copy()
    ordered.index = ordered.index.astype(str)
    ordered.columns = ordered.columns.astype(str)
    ordered = ordered.sort_index()
    if set(ordered.index) != set(ordered.columns):
        raise ValueError("similarity matrix must use the same row and column labels")
    ordered = ordered.reindex(columns=ordered.index)

    compatibility = ordered.to_numpy(dtype="float64") >= min_cosine_similarity
    compatibility &= compatibility.T
    np.fill_diagonal(compatibility, True)
    return pd.DataFrame(
        compatibility,
        index=ordered.index,
        columns=ordered.columns,
    )


def minimize_cosine_similarity_groups(
    similarity_matrix: pd.DataFrame,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
) -> pd.DataFrame:
    """在余弦兼容矩阵上求尽量少的组，并保持组内任意两只股票兼容。

    每个合法组在兼容图中都是一个 clique。函数复用 V1 的 minimum clique
    partition 求解器：先求上下界，再对规模允许的连通分量做精确分支限界。
    如果规模或搜索节点上限阻止了完整搜索，仍返回当前找到的最好结果，并在
    ``DataFrame.attrs["optimal_group_count_proven"]`` 中标记尚未证明全局最优。
    """

    compatibility = build_cosine_compatibility_matrix(
        similarity_matrix,
        min_cosine_similarity=min_cosine_similarity,
    )
    return minimize_compatibility_groups(
        compatibility,
        max_exact_component_stocks=max_exact_component_stocks,
        exact_search_node_limit=exact_search_node_limit,
    )


def greedy_group_by_cosine_similarity(
    similarity_matrix: pd.DataFrame,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
) -> pd.DataFrame:
    """按余弦相似度从高到低贪心合并，并保持组内全配对约束。

    算法从“每只股票各自一组”开始，只处理达到阈值的股票对，并按余弦相似度
    从高到低尝试合并它们当前所在的两个组。相似度相同时按 ``stock_id`` 排序，
    保证相同输入得到稳定结果。

    一次合并必须满足：第一个组中的每只股票，都与第二个组中的每只股票兼容。
    所以最终组内任意成员仍两两达到阈值。早期合并不会回退，因此这种方法优先
    保留最强相似对，但不保证组数最少。
    """

    compatibility_frame = build_cosine_compatibility_matrix(
        similarity_matrix,
        min_cosine_similarity=min_cosine_similarity,
    )
    stock_ids = compatibility_frame.index.tolist()
    stock_count = len(stock_ids)
    compatibility = compatibility_frame.to_numpy(dtype=bool)

    ordered_similarities = similarity_matrix.copy()
    ordered_similarities.index = ordered_similarities.index.astype(str)
    ordered_similarities.columns = ordered_similarities.columns.astype(str)
    ordered_similarities = ordered_similarities.reindex(
        index=stock_ids,
        columns=stock_ids,
    )
    similarity_values = ordered_similarities.to_numpy(dtype="float64")

    candidate_pairs: list[tuple[float, str, str, int, int]] = []
    for first_stock in range(stock_count):
        for second_stock in range(first_stock + 1, stock_count):
            if not compatibility[first_stock, second_stock]:
                continue

            # 兼容矩阵已要求双向相似度都通过。排序时也取较小的双向值，保证
            # 外部传入轻微非对称矩阵时不会高估这一股票对的证据强度。
            pair_similarity = min(
                similarity_values[first_stock, second_stock],
                similarity_values[second_stock, first_stock],
            )
            candidate_pairs.append(
                (
                    -pair_similarity,
                    stock_ids[first_stock],
                    stock_ids[second_stock],
                    first_stock,
                    second_stock,
                )
            )
    candidate_pairs.sort()

    # group_of 保存每只股票当前所属的内部组 ID，groups 保存组内位置编号。
    # 股票规模相对于余弦矩阵的 O(S^2) 存储已经不是额外瓶颈，因此这里使用 set
    # 直接表达“检查两个组的所有交叉股票对”，让后续调整逻辑更容易理解。
    group_of = list(range(stock_count))
    groups: dict[int, set[int]] = {
        stock_position: {stock_position} for stock_position in range(stock_count)
    }

    for _, _, _, first_stock, second_stock in candidate_pairs:
        first_group = group_of[first_stock]
        second_group = group_of[second_stock]
        if first_group == second_group:
            continue

        first_members = groups[first_group]
        second_members = groups[second_group]
        can_merge = all(
            compatibility[first_member, second_member]
            for first_member in first_members
            for second_member in second_members
        )
        if not can_merge:
            continue

        # 保留较小内部 ID 仅用于结果可复现；最终仍会按组内最小 stock_id 编号。
        kept_group = min(first_group, second_group)
        removed_group = max(first_group, second_group)
        removed_members = groups.pop(removed_group)
        groups[kept_group].update(removed_members)
        for member in removed_members:
            group_of[member] = kept_group

    grouped_stock_ids = [
        sorted(stock_ids[position] for position in members)
        for members in groups.values()
    ]
    grouped_stock_ids.sort(key=lambda group: group[0])
    rows = [
        (stock_id, group_id)
        for group_id, group in enumerate(grouped_stock_ids, start=1)
        for stock_id in group
    ]
    result = pd.DataFrame(rows, columns=["stock_id", "group_id"])
    result.attrs["grouping_method"] = COSINE_GROUPING_METHOD_GREEDY
    result.attrs["optimal_group_count_proven"] = False
    result.attrs["group_count_lower_bound"] = None
    result.attrs["group_count_upper_bound"] = len(grouped_stock_ids)
    result.attrs["exact_search_nodes"] = 0
    return result


def group_by_cosine_similarity(
    similarity_matrix: pd.DataFrame,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
    grouping_method: str = DEFAULT_COSINE_GROUPING_METHOD,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
) -> pd.DataFrame:
    """从余弦相似度矩阵选择最少分组或相似度降序贪心分组。

    例如 ``a-b`` 和 ``b-c`` 通过阈值，但 ``a-c`` 不通过，则结果不会是
    ``{a,b,c}``。两种方法都严格保持这项组内全配对约束；区别是：

    - ``minimize`` 尽量减少组数，并报告是否已经证明是全局最少；
    - ``cosine_greedy`` 优先合并相似度最高的股票对，不保证组数最少。
    """

    if grouping_method not in COSINE_GROUPING_METHODS:
        raise ValueError(
            f"grouping_method must be one of {', '.join(COSINE_GROUPING_METHODS)}"
        )

    if grouping_method == COSINE_GROUPING_METHOD_GREEDY:
        return greedy_group_by_cosine_similarity(
            similarity_matrix,
            min_cosine_similarity=min_cosine_similarity,
        )

    return minimize_cosine_similarity_groups(
        similarity_matrix,
        min_cosine_similarity=min_cosine_similarity,
        max_exact_component_stocks=max_exact_component_stocks,
        exact_search_node_limit=exact_search_node_limit,
    )


def group_relative_clock_vectors_v2(
    vectors: pd.DataFrame,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
    min_common_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_common_rate: float = DEFAULT_MIN_CLOSE_RATE,
    grouping_method: str = DEFAULT_COSINE_GROUPING_METHOD,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
) -> pd.DataFrame:
    """V2 主入口：计算余弦相似度，再按指定策略执行全配对分组。"""

    similarity_matrix, _ = calculate_cosine_similarity_matrix(
        vectors,
        min_common_snapshots=min_common_snapshots,
        min_common_rate=min_common_rate,
    )
    return group_by_cosine_similarity(
        similarity_matrix,
        min_cosine_similarity=min_cosine_similarity,
        grouping_method=grouping_method,
        max_exact_component_stocks=max_exact_component_stocks,
        exact_search_node_limit=exact_search_node_limit,
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
    grouping_method: str = DEFAULT_COSINE_GROUPING_METHOD,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
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
        grouping_method=grouping_method,
        max_exact_component_stocks=max_exact_component_stocks,
        exact_search_node_limit=exact_search_node_limit,
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
    parser.add_argument(
        "--grouping-method",
        choices=COSINE_GROUPING_METHODS,
        default=DEFAULT_COSINE_GROUPING_METHOD,
        help=(
            "分组方法：minimize 尽量减少组数；cosine_greedy 按余弦相似度"
            "降序贪心合并（默认：%(default)s）"
        ),
    )
    parser.add_argument(
        "--max-exact-component-stocks",
        type=int,
        default=DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
        help="minimize 方法允许精确搜索的最大连通分量股票数（默认：%(default)s）",
    )
    parser.add_argument(
        "--exact-search-node-limit",
        type=int,
        default=DEFAULT_EXACT_SEARCH_NODE_LIMIT,
        help="minimize 方法每次精确搜索的节点上限；0 表示不限制（默认：%(default)s）",
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
        grouping_method=arguments.grouping_method,
        max_exact_component_stocks=arguments.max_exact_component_stocks,
        exact_search_node_limit=arguments.exact_search_node_limit,
    )

    print(f"股票数：{len(groups)}")
    print(f"最终分组数：{groups['group_id'].nunique()}")
    if groups.attrs["grouping_method"] == COSINE_GROUPING_METHOD_GREEDY:
        print("分组方法：按余弦相似度降序贪心合并")
        print("最少分组证明：贪心方法不保证当前分组数为全局最少")
    else:
        print("分组方法：minimum clique partition（余弦兼容矩阵）")
        if groups.attrs["optimal_group_count_proven"]:
            print("最少分组证明：已证明当前分组数为全局最少")
        else:
            print(
                "最少分组证明：尚未证明；"
                f"已知下界={groups.attrs['group_count_lower_bound']}，"
                f"当前上界={groups.attrs['group_count_upper_bound']}"
            )
    print(f"分组 CSV：{arguments.groups_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
