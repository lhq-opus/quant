"""使用余弦相似度恢复股票固定分组。

V2 只负责分组，不再生成向量 CSV 或图片。从 ``quant/`` 目录运行：

    python -m mds.relative_clock_grouping_v2 INPUT.csv GROUPS.csv

输入仍然只使用 ``clock``、``stock_id``、``time`` 三列；输出包括：

- ``GROUPS.csv``：``stock_id,group_id`` 映射；
- ``GROUPS_cosine_similarity.csv``：股票两两余弦相似度矩阵；
- ``GROUPS_common_counts.csv``：股票两两共同 snapshot 数矩阵；
- ``GROUPS_compatibility.csv``：应用当前阈值后的股票两两兼容矩阵。

后三个文件默认根据 ``GROUPS.csv`` 的文件名生成，也可用命令行参数指定路径。
矩阵 CSV 的第一列和第一行都保存 ``stock_id``；证据不足的余弦相似度为空值。

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


REQUIRED_COLUMNS = ["clock", "stock_id", "time"]
DEFAULT_MIN_CLOSE_SNAPSHOTS = 2
DEFAULT_MIN_CLOSE_RATE = 0.5
DEFAULT_MAX_EXACT_COMPONENT_STOCKS = 60
DEFAULT_EXACT_SEARCH_NODE_LIMIT = 200_000
DEFAULT_MIN_COSINE_SIMILARITY = 0.99
COSINE_GROUPING_METHOD_MINIMIZE = "minimize"
COSINE_GROUPING_METHOD_GREEDY = "cosine_greedy"
COSINE_GROUPING_METHODS = (
    COSINE_GROUPING_METHOD_MINIMIZE,
    COSINE_GROUPING_METHOD_GREEDY,
)
DEFAULT_COSINE_GROUPING_METHOD = COSINE_GROUPING_METHOD_MINIMIZE


def resolve_relationship_matrix_csv_path(
    groups_csv: Path | str,
    requested_csv: Path | str | None,
    matrix_name: str,
) -> Path:
    """使用指定的矩阵 CSV 路径，未指定时根据分组 CSV 的文件名生成。

    例如分组文件为 ``groups.csv``、矩阵名为 ``cosine_similarity`` 时，
    矩阵文件为同目录下的 ``groups_cosine_similarity.csv``。
    """

    if requested_csv is not None:
        return Path(requested_csv)

    groups_path = Path(groups_csv)
    return groups_path.with_name(f"{groups_path.stem}_{matrix_name}.csv")


def write_relationship_matrix_csv(
    matrix: pd.DataFrame,
    output_csv: Path | str,
) -> None:
    """将股票关系矩阵写入 CSV，第一列保留行股票 ID。

    index 和 columns 分别表示一对股票的两端。保留 index，并将它的列名设为
    ``stock_id``，就能从输出文件直接读出每个数值对应哪一对股票。余弦矩阵的
    ``NaN`` 写成空单元格，继续表示共同维度证据不足。
    """

    matrix.to_csv(output_csv, index=True, index_label="stock_id")


def build_relative_clock_vectors(data: pd.DataFrame) -> pd.DataFrame:
    """生成每行一只股票、每列一个 snapshot 的相对 clock 向量表。

    输入约定每个 snapshot 内已经按 clock 升序排列，而且同一股票至多一行。
    因此直接用该 snapshot 的第一条 clock 作为零点，单位仍然是微秒。
    """

    relative_data = data.copy()
    # transform("first") 把每个 time 的首个 clock 对应回该 snapshot 的所有行，
    # 返回序列与输入逐行对齐，可以直接做减法。
    snapshot_start = relative_data.groupby("time", sort=False)["clock"].transform(
        "first"
    )
    relative_data["relative_clock"] = relative_data["clock"] - snapshot_start

    # pivot 将记录长表转成股票 × snapshot 宽表；最后恢复 time 在输入中的
    # 首次出现顺序，并按 stock_id 排列各行，使向量与后续矩阵顺序稳定。
    snapshot_order = relative_data["time"].drop_duplicates().tolist()
    vectors = relative_data.pivot(
        index="stock_id",
        columns="time",
        values="relative_clock",
    )
    # 缺失维度必须保留为空。0 表示真实观测恰好位于 snapshot 零点，不能拿来
    # 代替缺失。pandas 的 Int64 类型可以同时保存整数微秒和空值。
    return vectors.reindex(columns=snapshot_order).sort_index().astype("Int64")


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
    因而也判为不兼容。输入是合法的对称矩阵，行列使用相同股票 ID。
    对角线固定为 ``True``，因为一只股票单独成组总是合法。
    """

    # 两个轴都按 stock_id 排列。后续用位置编号处理股票，位置越小就表示 ID
    # 顺序越靠前，因而相同相似度下的贪心处理顺序也能保持稳定。
    ordered = similarity_matrix.sort_index()
    ordered = ordered.loc[:, ordered.index]
    # NaN 与阈值比较的结果为 False，证据不足自然不会形成兼容关系。
    compatibility = ordered.to_numpy(dtype="float64") >= min_cosine_similarity
    np.fill_diagonal(compatibility, True)
    return pd.DataFrame(
        compatibility,
        index=ordered.index,
        columns=ordered.columns,
    )


# V2 独立维护自己的图分组实现；修改本文件不会改变 V1 的算法。
def _boolean_matrix_to_bit_masks(matrix: np.ndarray) -> list[int]:
    """把每行布尔值存成一个整数，快速表示股票集合。

    例如 [True, False, True] 表示位置 0、2，在二进制中写成 101。
    1 << i 表示只包含位置 i；a & b 取交集，a | b 取并集。
    这些位运算在底层一次处理多个成员，避免在搜索中反复逐股票比较。
    """

    # packbits 把每 8 个布尔值打包成一个字节；不足 8 位的部分自动补 0。
    # 两处 little 都表示编号小的股票放低位，保证股票位置与二进制位一一对应。
    packed_rows = np.packbits(matrix, axis=1, bitorder="little")
    masks = []
    for row in packed_rows:
        masks.append(int.from_bytes(row.tobytes(), byteorder="little"))
    return masks


def _vertices_from_mask(mask: int) -> list[int]:
    """把整数集合展开为升序位置列表，例如二进制 101 变为 [0, 2]。"""

    vertices = []
    while mask:
        # mask & -mask 只保留最右边的 1，例如 10100 变成 00100。
        # bit_length() - 1 得到这一位从 0 开始的编号，此例中是 2。
        lowest_bit = mask & -mask
        vertices.append(lowest_bit.bit_length() - 1)
        mask ^= lowest_bit  # 用异或清掉刚处理的这一位。
    return vertices


def _connected_components(adjacency_masks: list[int]) -> list[list[int]]:
    """按编号查找图中互相可达的部分；兼容图和冲突图都可使用。"""

    # 例如有 3 个顶点时，(1 << 3) - 1 是二进制 111，即所有顶点尚未访问。
    remaining = (1 << len(adjacency_masks)) - 1
    components = []

    while remaining:
        seed = remaining & -remaining
        remaining ^= seed
        frontier = seed  # 已发现、还没检查邻居的顶点集合。
        component_mask = 0

        while frontier:
            vertex_bit = frontier & -frontier
            frontier ^= vertex_bit
            component_mask |= vertex_bit
            vertex = vertex_bit.bit_length() - 1

            # 邻居与 remaining 取交集，只加入从未发现的顶点，避免重复遍历。
            new_neighbors = adjacency_masks[vertex] & remaining
            remaining ^= new_neighbors
            frontier |= new_neighbors

        components.append(_vertices_from_mask(component_mask))

    return components


def _select_dsatur_vertex(
    uncolored: int,
    neighbor_color_masks: list[int],
    degrees: list[int],
) -> int:
    """选出最受约束的未分组股票，供贪心着色和精确搜索使用。"""

    best_vertex = -1
    best_priority = (-1, -1, 0)
    for vertex in _vertices_from_mask(uncolored):
        # DSATUR 的第一优先级是邻居已占用的颜色种类数，即当前禁用的组数。
        # bit_count() 数整数中有几个 1。并列时比较冲突度，再优先编号小者。
        # Python 从左往右比较元组，所以三项自然构成三层排序条件。
        priority = (
            neighbor_color_masks[vertex].bit_count(),
            degrees[vertex],
            -vertex,
        )
        if priority > best_priority:
            best_priority = priority
            best_vertex = vertex
    return best_vertex


def _dsatur_greedy_coloring(conflict_masks: list[int]) -> list[int]:
    """在冲突图上快速找一个合法分组，组数作为精确搜索的上界。

    颜色就是组号：有冲突的两只股票不能同色。贪心每次优先安排最受约束
    的股票，再给它最小可用颜色；这个结果合法，但未必使用最少颜色。
    """

    vertex_count = len(conflict_masks)
    colors = [-1] * vertex_count  # -1 表示尚未安排颜色。
    neighbor_color_masks = [0] * vertex_count
    degrees = [neighbors.bit_count() for neighbors in conflict_masks]
    uncolored = (1 << vertex_count) - 1

    while uncolored:
        vertex = _select_dsatur_vertex(uncolored, neighbor_color_masks, degrees)
        blocked_colors = neighbor_color_masks[vertex]

        color = 0
        while blocked_colors & (1 << color):
            color += 1
        colors[vertex] = color
        uncolored ^= 1 << vertex

        # 给 vertex 安排颜色后，它所有还未着色的冲突邻居都不能再使用此颜色。
        for neighbor in _vertices_from_mask(conflict_masks[vertex] & uncolored):
            neighbor_color_masks[neighbor] |= 1 << color

    return colors


def _greedy_conflict_clique_lower_bound(conflict_masks: list[int]) -> int:
    """寻找一批两两冲突的股票，其数量是至少需要的组数。"""

    if not conflict_masks:
        return 0
    degrees = [neighbors.bit_count() for neighbors in conflict_masks]
    # lambda 只定义这里的排序键：冲突度降序，编号升序。
    seed_order = sorted(
        range(len(conflict_masks)), key=lambda vertex: (-degrees[vertex], vertex)
    )
    best_size = 1

    # 最多尝试 16 个高冲突起点，只求一个可靠下界，不穷举最大冲突团。
    for seed in seed_order[:16]:
        clique_size = 1
        candidates = conflict_masks[seed]
        # 优先级固定，候选只会减少，所以扫描一次已有顺序即可。
        # 每轮重新展开 candidates 再 max 会重复大量工作，选择结果却相同。
        for vertex in seed_order:
            if candidates & (1 << vertex):
                clique_size += 1
                candidates &= conflict_masks[vertex]
        best_size = max(best_size, clique_size)

    return best_size


def _search_minimum_coloring(
    conflict_masks: list[int],
    initial_colors: list[int],
    lower_bound: int,
    *,
    search_node_limit: int,
) -> tuple[list[int], bool, int]:
    """尝试减少颜色数，返回最好着色、是否证明最优、实际搜索节点数。

    颜色就是组号，冲突边的两端不能同组。每层先选择一只股票，依次尝试
    可用组，递归安排剩余股票；返回时撤销本次安排，再尝试其他组。
    """

    vertex_count = len(conflict_masks)
    best_colors = initial_colors.copy()
    best_color_count = max(initial_colors, default=-1) + 1
    degrees = [neighbors.bit_count() for neighbors in conflict_masks]
    colors = [-1] * vertex_count
    neighbor_color_masks = [0] * vertex_count
    color_sizes = [0] * vertex_count
    searched_nodes = 0
    search_was_cut_off = False

    def search(uncolored: int, used_color_count: int) -> None:
        # nonlocal 表示修改外层函数保存的“当前最好结果”和预算状态。
        # 所有递归分支共享这些结果，不能在每层创建同名局部变量。
        nonlocal best_colors, best_color_count, searched_nodes, search_was_cut_off

        if best_color_count == lower_bound or search_was_cut_off:
            return
        # 只搜索能严格改善上界的分支；检查放在叶子前，避免覆盖更好的结果。
        if used_color_count >= best_color_count:
            return
        if not uncolored:
            best_colors = colors.copy()
            best_color_count = used_color_count
            return
        if search_node_limit and searched_nodes >= search_node_limit:
            search_was_cut_off = True
            return
        searched_nodes += 1

        vertex = _select_dsatur_vertex(uncolored, neighbor_color_masks, degrees)
        remaining = uncolored ^ (1 << vertex)
        blocked_colors = neighbor_color_masks[vertex]

        available_colors = []
        for color in range(used_color_count):
            if not (blocked_colors & (1 << color)):
                available_colors.append(color)
        # 优先尝试成员较多的已有组；lambda 的两个排序条件分别是人数降序、组号升序。
        available_colors.sort(key=lambda color: (-color_sizes[color], color))
        # 所有未用过的组号意义相同，只试下一个编号，省去纯组号置换的重复解。
        available_colors.append(used_color_count)

        # 已有组和新组共用这段“安排 -> 更新 -> 递归 -> 撤销”，避免两份状态逻辑。
        for color in available_colors:
            next_color_count = max(used_color_count, color + 1)
            # 前一分支可能刚降低了上界，所以这里每次都要重新比较。
            if next_color_count >= best_color_count:
                continue

            colors[vertex] = color
            color_sizes[color] += 1
            changed_neighbors = []
            color_bit = 1 << color
            for neighbor in _vertices_from_mask(conflict_masks[vertex] & remaining):
                old_mask = neighbor_color_masks[neighbor]
                if not (old_mask & color_bit):
                    changed_neighbors.append((neighbor, old_mask))
                    neighbor_color_masks[neighbor] = old_mask | color_bit

            search(remaining, next_color_count)

            # 邻居可能原本就因其他股票禁用了此颜色。保存旧值后恢复，不能直接
            # 把所有邻居的该位清零，否则会丢失进入此分支前已经存在的冲突。
            for neighbor, old_mask in changed_neighbors:
                neighbor_color_masks[neighbor] = old_mask
            color_sizes[color] -= 1
            colors[vertex] = -1

            if best_color_count == lower_bound or search_was_cut_off:
                return

    search((1 << vertex_count) - 1, 0)
    # 达到下界，或穷尽所有可能改善的分支，才能证明最优；预算耗尽不算证明。
    is_optimal = best_color_count == lower_bound or not search_was_cut_off
    return best_colors, is_optimal, searched_nodes


def minimize_compatibility_groups(
    compatibility_matrix: pd.DataFrame,
    *,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
) -> pd.DataFrame:
    """求尽量少的全配对兼容组，并报告上下界及最优性。

    输入是本版生成的对称布尔矩阵，两轴使用相同的字符串 stock_id。
    每个合法组在兼容图中是 clique，即成员两两相连；在冲突图中则是一个
    颜色，即成员之间没有冲突。最少分组因此等价于冲突图的最少着色。

    先拆兼容分量，再在各自内部拆冲突分量。精确搜索的股票数限制和节点
    预算都作用于最终的每个冲突分量。超过限制时保留合法解及可靠下界，
    不把“当前找到的最好解”当成已经证明最少。节点预算 0 表示不限制。
    """

    # 排序使并列选择和最终组号可复现；输入合法，不再做类型/标签/对称性校验。
    ordered = compatibility_matrix.sort_index().sort_index(axis=1)
    stock_ids = ordered.index.tolist()
    compatibility = ordered.to_numpy(dtype=bool, copy=True)
    np.fill_diagonal(compatibility, True)
    compatibility_masks = _boolean_matrix_to_bit_masks(compatibility)

    groups = []
    total_lower_bound = 0
    total_searched_nodes = 0

    # 不同兼容分量之间没有兼容边，股票不能跨分量同组：组数应相加。
    for component in _connected_components(compatibility_masks):
        # np.ix_(rows, columns) 取行列的所有组合，得到分量内部的完整子矩阵。
        # ~ 对布尔值取反，把“兼容”变成“冲突”；股票与自己永远没有冲突。
        local_conflicts = ~compatibility[np.ix_(component, component)]
        np.fill_diagonal(local_conflicts, False)
        conflict_masks = _boolean_matrix_to_bit_masks(local_conflicts)
        component_colors = [-1] * len(component)
        component_lower_bound = 0

        # 不同冲突分量之间没有冲突，可以复用同一批颜色：组数取最大值。
        # 例如两个各需 3 组的独立冲突问题，合起来仍然只需 3 组，而不是 6 组。
        for conflict_component in _connected_components(conflict_masks):
            sub_conflicts = local_conflicts[np.ix_(
                conflict_component, conflict_component
            )]
            sub_masks = _boolean_matrix_to_bit_masks(sub_conflicts)
            colors = _dsatur_greedy_coloring(sub_masks)
            color_count = max(colors) + 1
            lower_bound = _greedy_conflict_clique_lower_bound(sub_masks)
            is_optimal = color_count == lower_bound

            if not is_optimal and len(conflict_component) <= max_exact_component_stocks:
                colors, is_optimal, searched_nodes = _search_minimum_coloring(
                    sub_masks,
                    colors,
                    lower_bound,
                    search_node_limit=exact_search_node_limit,
                )
                color_count = max(colors) + 1
                total_searched_nodes += searched_nodes

            if is_optimal:
                lower_bound = color_count
            component_lower_bound = max(component_lower_bound, lower_bound)

            # 子问题颜色从 0 开始，不加偏移：跨冲突分量的同色成员可以安全合组。
            for sub_position, color in enumerate(colors):
                local_position = conflict_component[sub_position]
                component_colors[local_position] = color

        total_lower_bound += component_lower_bound
        groups_by_color = {}
        for local_position, color in enumerate(component_colors):
            if color not in groups_by_color:
                groups_by_color[color] = []
            global_position = component[local_position]
            groups_by_color[color].append(stock_ids[global_position])
        groups.extend(groups_by_color.values())

    # 内部颜色仅用于求解。对成员及各组排序，再从 1 编号，保证 CSV 易读且稳定。
    for group in groups:
        group.sort()
    groups.sort(key=lambda group: group[0])
    rows = []
    for group_id, members in enumerate(groups, start=1):
        for stock_id in members:
            rows.append((stock_id, group_id))

    result = pd.DataFrame(rows, columns=["stock_id", "group_id"])
    result.attrs["grouping_method"] = "minimize"
    # 用最终上下界判断即可，不要求每个冲突子问题都独立完成证明。
    # 例如一个子问题已证需 3 组，另一个只知需 2–3 组，复用颜色后整体仍已证为 3。
    result.attrs["optimal_group_count_proven"] = total_lower_bound == len(groups)
    result.attrs["group_count_lower_bound"] = total_lower_bound
    result.attrs["group_count_upper_bound"] = len(groups)
    result.attrs["exact_search_nodes"] = total_searched_nodes
    return result



def minimize_cosine_similarity_groups(
    similarity_matrix: pd.DataFrame,
    *,
    min_cosine_similarity: float = DEFAULT_MIN_COSINE_SIMILARITY,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
) -> pd.DataFrame:
    """在余弦兼容矩阵上求尽量少的组，并保持组内任意两只股票兼容。

    每个合法组在兼容图中都是一个 clique。本文件独立维护求解器：先拆兼容
    分量及其内部的冲突分量，再对规模允许的冲突分量做精确分支限界。
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

    ordered_similarities = similarity_matrix.loc[stock_ids, stock_ids]
    similarity_values = ordered_similarities.to_numpy(dtype="float64")

    candidate_pairs: list[tuple[float, int, int]] = []
    for first_stock in range(stock_count):
        for second_stock in range(first_stock + 1, stock_count):
            if not compatibility[first_stock, second_stock]:
                continue

            pair_similarity = similarity_values[first_stock, second_stock]
            candidate_pairs.append(
                (
                    -pair_similarity,
                    first_stock,
                    second_stock,
                )
            )
    # 元组按各项依次比较。相似度取负数后，升序 sort 等价于相似度降序；
    # 后两项是已经按 stock_id 排好的位置，所以并列时仍按两个 ID 升序。
    candidate_pairs.sort()

    # group_of 保存每只股票当前所属的内部组 ID，groups 保存组内位置编号。
    group_of = list(range(stock_count))
    groups: dict[int, list[int]] = {}
    for stock_position in range(stock_count):
        groups[stock_position] = [stock_position]

    # allowed[g, s] 表示：股票 s 与组 g 的每一个成员都兼容。
    # 初始时每组只有一只股票，所以直接复制兼容矩阵。以后只在真正合并时
    # 更新这一整行，避免每条候选边都重新逐一检查两个组的所有交叉股票对。
    allowed = compatibility.copy()

    for _, first_stock, second_stock in candidate_pairs:
        first_group = group_of[first_stock]
        second_group = group_of[second_stock]
        if first_group == second_group:
            continue

        second_members = groups[second_group]
        # NumPy 的“整数列表索引”一次取出指定行中的多个位置：这里取得的是
        # 第二组每个成员能否与第一组全部成员同组。all() 要求这些值全为 True，
        # 所以仍然严格满足全配对约束，不能仅凭当前候选边就合并两个组。
        if not allowed[first_group, second_members].all():
            continue

        # 保留较小内部 ID 仅用于结果可复现；最终仍会按组内最小 stock_id 编号。
        kept_group = min(first_group, second_group)
        removed_group = max(first_group, second_group)
        # 新组的共同兼容股票必须同时兼容两个旧组。布尔数组上的 & 是逐元素
        # “并且”，&= 将交集写回保留组的那一行；不修改原始兼容矩阵。
        allowed[kept_group] &= allowed[removed_group]
        removed_members = groups.pop(removed_group)
        groups[kept_group].extend(removed_members)
        for member in removed_members:
            group_of[member] = kept_group

    grouped_stock_ids = []
    for members in groups.values():
        member_ids = []
        for position in members:
            member_ids.append(stock_ids[position])
        grouped_stock_ids.append(sorted(member_ids))
    grouped_stock_ids.sort(key=lambda group: group[0])
    rows = []
    for group_id, group in enumerate(grouped_stock_ids, start=1):
        for stock_id in group:
            rows.append((stock_id, group_id))
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
    cosine_similarity_csv: Path | str | None = None,
    common_counts_csv: Path | str | None = None,
    compatibility_csv: Path | str | None = None,
) -> pd.DataFrame:
    """读取 market data CSV，输出分组及三张股票关系矩阵 CSV。"""

    data = pd.read_csv(
        input_csv,
        usecols=REQUIRED_COLUMNS,
        dtype={"clock": "int64", "stock_id": "string", "time": "string"},
    )
    vectors = build_relative_clock_vectors(data)
    similarity_matrix, common_counts = calculate_cosine_similarity_matrix(
        vectors,
        min_common_snapshots=min_common_snapshots,
        min_common_rate=min_common_rate,
    )
    compatibility = build_cosine_compatibility_matrix(
        similarity_matrix,
        min_cosine_similarity=min_cosine_similarity,
    )
    groups = group_by_cosine_similarity(
        similarity_matrix,
        min_cosine_similarity=min_cosine_similarity,
        grouping_method=grouping_method,
        max_exact_component_stocks=max_exact_component_stocks,
        exact_search_node_limit=exact_search_node_limit,
    )

    resolved_cosine_similarity_csv = resolve_relationship_matrix_csv_path(
        groups_csv,
        cosine_similarity_csv,
        "cosine_similarity",
    )
    resolved_common_counts_csv = resolve_relationship_matrix_csv_path(
        groups_csv,
        common_counts_csv,
        "common_counts",
    )
    resolved_compatibility_csv = resolve_relationship_matrix_csv_path(
        groups_csv,
        compatibility_csv,
        "compatibility",
    )

    groups.to_csv(groups_csv, index=False)
    write_relationship_matrix_csv(
        similarity_matrix,
        resolved_cosine_similarity_csv,
    )
    write_relationship_matrix_csv(common_counts, resolved_common_counts_csv)
    write_relationship_matrix_csv(compatibility, resolved_compatibility_csv)
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
        help="minimize 方法允许精确搜索的最大冲突分量股票数（默认：%(default)s）",
    )
    parser.add_argument(
        "--exact-search-node-limit",
        type=int,
        default=DEFAULT_EXACT_SEARCH_NODE_LIMIT,
        help="minimize 方法每个冲突分量的搜索节点上限；0 表示不限制（默认：%(default)s）",
    )
    parser.add_argument(
        "--cosine-similarity-csv",
        type=Path,
        help="余弦相似度矩阵 CSV；默认写到 GROUPS 同目录的 *_cosine_similarity.csv",
    )
    parser.add_argument(
        "--common-counts-csv",
        type=Path,
        help="共同 snapshot 数矩阵 CSV；默认写到 GROUPS 同目录的 *_common_counts.csv",
    )
    parser.add_argument(
        "--compatibility-csv",
        type=Path,
        help="阈值兼容矩阵 CSV；默认写到 GROUPS 同目录的 *_compatibility.csv",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行命令行程序并打印结果摘要。"""

    arguments = build_argument_parser().parse_args(argv)
    cosine_similarity_csv = resolve_relationship_matrix_csv_path(
        arguments.groups_csv,
        arguments.cosine_similarity_csv,
        "cosine_similarity",
    )
    common_counts_csv = resolve_relationship_matrix_csv_path(
        arguments.groups_csv,
        arguments.common_counts_csv,
        "common_counts",
    )
    compatibility_csv = resolve_relationship_matrix_csv_path(
        arguments.groups_csv,
        arguments.compatibility_csv,
        "compatibility",
    )
    groups = process_csv(
        arguments.input_csv,
        arguments.groups_csv,
        min_cosine_similarity=arguments.min_cosine_similarity,
        min_common_snapshots=arguments.min_common_snapshots,
        min_common_rate=arguments.min_common_rate,
        grouping_method=arguments.grouping_method,
        max_exact_component_stocks=arguments.max_exact_component_stocks,
        exact_search_node_limit=arguments.exact_search_node_limit,
        cosine_similarity_csv=cosine_similarity_csv,
        common_counts_csv=common_counts_csv,
        compatibility_csv=compatibility_csv,
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
    print(f"余弦相似度矩阵 CSV：{cosine_similarity_csv}")
    print(f"共同 snapshot 数矩阵 CSV：{common_counts_csv}")
    print(f"兼容矩阵 CSV：{compatibility_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
