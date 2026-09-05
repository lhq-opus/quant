"""把每只股票表示成跨 snapshot 的相对 clock 向量，并做简单分组。

从 ``quant/`` 目录运行：

    python -m mds.relative_clock_grouping \
        INPUT.csv VECTORS.csv GROUPS.csv VECTORS.png

输出：

- ``VECTORS.csv``：每行一只股票，每个 ``time`` 是一个向量维度；
- ``GROUPS.csv``：``stock_id,group_id`` 映射；
- ``VECTORS.png``：按推断组排序后的相对 clock 向量热图。
- ``GROUPS_match_counts.csv``：股票两两匹配次数矩阵；
- ``GROUPS_match_rates.csv``：股票两两匹配率矩阵；
- ``GROUPS_compatibility.csv``：应用当前阈值后的股票两两兼容矩阵。

后三个文件默认根据 ``GROUPS.csv`` 的文件名生成，也可以使用对应命令行参数
指定其他路径。矩阵 CSV 的第一列和第一行都保存 ``stock_id``。

这是一版便于观察向量结构的简单 baseline，不是最终分组算法。默认参数是
探索性启发式，不是已经确认的业务阈值。默认使用 ``minimize`` 尽量减少组数；
也可用 ``--grouping-method rate_greedy`` 按匹配率从高到低贪心合并。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

REQUIRED_COLUMNS = ["clock", "stock_id", "time"]
DEFAULT_MAX_CLOCK_GAP_US = 1_000
DEFAULT_MIN_CLOSE_SNAPSHOTS = 2
DEFAULT_MIN_CLOSE_RATE = 0.5
DEFAULT_MAX_EXACT_COMPONENT_STOCKS = 60
DEFAULT_EXACT_SEARCH_NODE_LIMIT = 200_000
GROUPING_METHOD_MINIMIZE = "minimize"
GROUPING_METHOD_RATE_GREEDY = "rate_greedy"
GROUPING_METHODS = (GROUPING_METHOD_MINIMIZE, GROUPING_METHOD_RATE_GREEDY)
DEFAULT_GROUPING_METHOD = GROUPING_METHOD_MINIMIZE


def resolve_relationship_matrix_csv_path(
    groups_csv: Path | str,
    requested_csv: Path | str | None,
    matrix_name: str,
) -> Path:
    """确定一个股票关系矩阵的输出路径。

    调用方显式传入路径时直接使用；否则在 ``groups_csv`` 同一目录中自动生成。
    例如 ``groups.csv`` 与 ``matrix_name="match_counts"`` 会得到
    ``groups_match_counts.csv``。单独放在这个小函数里，可确保 V1、V2 的默认
    命名规则完全一致。
    """

    if requested_csv is not None:
        return Path(requested_csv)

    groups_path = Path(groups_csv)
    return groups_path.with_name(f"{groups_path.stem}_{matrix_name}.csv")


def write_relationship_matrix_csv(
    matrix: pd.DataFrame,
    output_csv: Path | str,
) -> None:
    """把 ``stock_id × stock_id`` 关系矩阵写成可直接回读的 CSV。

    DataFrame 的 index 表示第一只股票，columns 表示第二只股票。普通
    ``to_csv(index=False)`` 会丢失行对应的股票 ID，所以这里必须保留 index，
    并把左上角第一列表头明确写成 ``stock_id``。CSV 结构示例：

    ``stock_id,000001,600000,...``

    余弦相似度矩阵中的 ``NaN`` 会写成空单元格，继续表示“共同维度证据不足”。
    """

    matrix.to_csv(output_csv, index=True, index_label="stock_id")


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


def calculate_pairwise_match_matrices(
    vectors: pd.DataFrame,
    *,
    max_clock_gap_us: int = DEFAULT_MAX_CLOCK_GAP_US,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """计算股票两两之间的匹配次数矩阵和匹配率矩阵。

    两只股票在同一个 snapshot 都有值，并且相对 ``clock`` 之差不超过
    ``max_clock_gap_us``，就记作一次匹配。匹配率定义为：

    ``match_rate(i, j) = match_count(i, j) / common_count(i, j)``

    其中 ``common_count`` 是两只股票同时出现的 snapshot 数。没有匹配的股票对
    在两个矩阵中都保留为 0；由于后续要求最少匹配次数大于 0，它们一定不会被
    判为兼容。矩阵对称，行列均按 ``stock_id`` 排序。
    """

    if max_clock_gap_us < 0:
        raise ValueError("max_clock_gap_us must be non-negative")

    ordered_vectors = vectors.copy()
    ordered_vectors.index = ordered_vectors.index.astype(str)
    ordered_vectors = ordered_vectors.sort_index()
    stock_ids = ordered_vectors.index.tolist()
    stock_positions = {
        stock_id: position for position, stock_id in enumerate(stock_ids)
    }
    stock_count = len(stock_ids)

    # 一个 int32 单元格足以容纳一天约数千个 3 秒 snapshot 的计数。矩阵直接
    # 暴露给下一阶段，因此可以独立检查任意股票对的证据。
    match_counts = np.zeros((stock_count, stock_count), dtype="int32")
    # Python 整数的每一位代表一个 snapshot 是否出现。相比为每只股票保存一组
    # Python int，bit mask 更省内存，两个 mask 做 & 后 bit_count 即共同维度数。
    active_snapshot_masks = [0] * stock_count
    matched_pairs: list[tuple[int, int]] = []

    # 每个 snapshot 内仍使用滑动窗口，只枚举 clock 差能够通过阈值的股票对；
    # 避免在每个 snapshot 中对所有已出现股票做 Python 层的两两比较。
    for snapshot_position, time_value in enumerate(ordered_vectors.columns):
        observed = ordered_vectors[time_value].dropna().sort_values(kind="stable")
        observed_stocks = observed.index.tolist()
        observed_positions = [stock_positions[stock_id] for stock_id in observed_stocks]
        observed_clocks = observed.to_numpy(dtype="int64")

        for stock_position in observed_positions:
            active_snapshot_masks[stock_position] |= 1 << snapshot_position

        window_start = 0
        for current_position, current_clock in enumerate(observed_clocks):
            while current_clock - observed_clocks[window_start] > max_clock_gap_us:
                window_start += 1

            current_stock = observed_positions[current_position]
            for previous_position in range(window_start, current_position):
                previous_stock = observed_positions[previous_position]
                if match_counts[current_stock, previous_stock] == 0:
                    matched_pairs.append(
                        (
                            min(current_stock, previous_stock),
                            max(current_stock, previous_stock),
                        )
                    )
                match_counts[current_stock, previous_stock] += 1
                match_counts[previous_stock, current_stock] += 1

    match_rates = np.zeros((stock_count, stock_count), dtype="float64")

    # 对角线只用于让矩阵便于阅读：股票与自身的匹配次数等于它出现的 snapshot
    # 数，匹配率记为 1。最终约束只检查不同股票之间的单元格。
    for stock_position, snapshot_mask in enumerate(active_snapshot_masks):
        match_counts[stock_position, stock_position] = snapshot_mask.bit_count()
        match_rates[stock_position, stock_position] = 1.0

    # 只有 match_count > 0 的股票对才可能通过“最少匹配次数”门槛，因此只为
    # 这些位置计算集合交集。match_count=0 的位置保持 rate=0，不影响最终判定。
    for first_stock, second_stock in matched_pairs:
        common_count = (
            active_snapshot_masks[first_stock] & active_snapshot_masks[second_stock]
        ).bit_count()
        match_rate = match_counts[first_stock, second_stock] / common_count
        match_rates[first_stock, second_stock] = match_rate
        match_rates[second_stock, first_stock] = match_rate

    labels = pd.Index(stock_ids, name="stock_id")
    return (
        pd.DataFrame(match_counts, index=labels, columns=labels),
        pd.DataFrame(match_rates, index=labels, columns=labels),
    )


def build_compatibility_matrix(
    match_counts: pd.DataFrame,
    match_rates: pd.DataFrame,
    *,
    min_close_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_close_rate: float = DEFAULT_MIN_CLOSE_RATE,
) -> pd.DataFrame:
    """把匹配次数、匹配率转换为同组条件。

    两张矩阵由上一步生成：行列均为同一顺序的字符串 stock_id，数值对称。
    本函数直接使用这个约定，不再复制矩阵做类型推测和非对称输入兼容。
    """

    compatibility = (match_counts.to_numpy() >= min_close_snapshots) & (
        match_rates.to_numpy() >= min_close_rate
    )
    # 两道门槛都通过才允许同组；单只股票无论证据多少都可以独立成组。
    np.fill_diagonal(compatibility, True)
    return pd.DataFrame(
        compatibility,
        index=match_counts.index,
        columns=match_counts.columns,
    )


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


def greedy_group_by_match_rate(
    match_counts: pd.DataFrame,
    match_rates: pd.DataFrame,
    *,
    min_close_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_close_rate: float = DEFAULT_MIN_CLOSE_RATE,
) -> pd.DataFrame:
    """按匹配率、匹配次数降序合组，并保持组内任意两只股票兼容。

    每只股票先独立成组，再依次处理达标的股票对。尝试合并的是股票当前
    所在的两个完整组；不能只凭这一对股票达标就合并。早期选择不回退，
    所以这个方法优先保留强关系，但不保证组数最少。
    """

    compatibility_frame = build_compatibility_matrix(
        match_counts,
        match_rates,
        min_close_snapshots=min_close_snapshots,
        min_close_rate=min_close_rate,
    )
    # 排序只为固定并列时的处理次序；两轴均使用同一 stock_id 顺序。
    stock_ids = sorted(compatibility_frame.index)
    compatibility = compatibility_frame.loc[stock_ids, stock_ids].to_numpy()
    count_values = match_counts.loc[stock_ids, stock_ids].to_numpy()
    rate_values = match_rates.loc[stock_ids, stock_ids].to_numpy()
    stock_count = len(stock_ids)
    compatibility_masks = _boolean_matrix_to_bit_masks(compatibility)

    candidate_pairs = []
    for first_stock in range(stock_count):
        for second_stock in range(first_stock + 1, stock_count):
            if compatibility[first_stock, second_stock]:
                # 元组从左向右排序。取负号把升序变成匹配率、匹配次数降序；
                # 股票位置已经按 ID 排序，不必在每个候选中再存两份 ID 字符串。
                candidate_pairs.append((
                    -rate_values[first_stock, second_stock],
                    -int(count_values[first_stock, second_stock]),
                    first_stock,
                    second_stock,
                ))
    candidate_pairs.sort()

    group_of = list(range(stock_count))
    group_masks = {}
    for stock in range(stock_count):
        group_masks[stock] = 1 << stock

    # allowed_masks[G] 保存“与 G 组所有成员都兼容”的股票集合。
    # 单例组的集合就是该股票的兼容行；之后只在成功合并时更新交集。
    allowed_masks = compatibility_masks.copy()
    for _, _, first_stock, second_stock in candidate_pairs:
        first_group = group_of[first_stock]
        second_group = group_of[second_stock]
        if first_group == second_group:
            continue

        second_members = group_masks[second_group]
        # B 的所有成员都在 allowed[A] 中，等价于 A、B 之间全配对通过。
        # 整数 & 取集合交集，再与 B 比较，省去每次遍历 A 的所有成员。
        if (allowed_masks[first_group] & second_members) != second_members:
            continue

        kept_group = min(first_group, second_group)
        removed_group = max(first_group, second_group)
        removed_members = group_masks.pop(removed_group)
        group_masks[kept_group] |= removed_members
        # 新组允许的股票必须同时兼容两个旧组；交集不能换成并集。
        allowed_masks[kept_group] &= allowed_masks[removed_group]
        for member in _vertices_from_mask(removed_members):
            group_of[member] = kept_group

    groups = []
    for member_mask in group_masks.values():
        members = []
        for position in _vertices_from_mask(member_mask):
            members.append(stock_ids[position])
        groups.append(members)
    groups.sort(key=lambda group: group[0])

    rows = []
    for group_id, members in enumerate(groups, start=1):
        for stock_id in members:
            rows.append((stock_id, group_id))

    # 贪心结果恰好达到冲突团下界时，也能证明这次的组数已经最少。
    group_count_lower_bound = 0
    for component in _connected_components(compatibility_masks):
        # np.ix_ 取这些股票两两之间的完整子矩阵，而非只取对应的对角元素。
        local_conflicts = ~compatibility[np.ix_(component, component)]
        np.fill_diagonal(local_conflicts, False)
        group_count_lower_bound += _greedy_conflict_clique_lower_bound(
            _boolean_matrix_to_bit_masks(local_conflicts)
        )

    result = pd.DataFrame(rows, columns=["stock_id", "group_id"])
    result.attrs["grouping_method"] = GROUPING_METHOD_RATE_GREEDY
    result.attrs["optimal_group_count_proven"] = len(groups) == group_count_lower_bound
    result.attrs["group_count_lower_bound"] = group_count_lower_bound
    result.attrs["group_count_upper_bound"] = len(groups)
    result.attrs["exact_search_nodes"] = 0
    return result


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


def group_pairwise_match_matrices(
    match_counts: pd.DataFrame,
    match_rates: pd.DataFrame,
    *,
    min_close_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_close_rate: float = DEFAULT_MIN_CLOSE_RATE,
    grouping_method: str = DEFAULT_GROUPING_METHOD,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
) -> pd.DataFrame:
    """直接从已计算的匹配次数/匹配率矩阵执行指定分组方法。

    这个入口把“计算股票关系矩阵”与“使用关系矩阵分组”分开。CSV 流程因此
    可以先计算一次矩阵，同时将它们写盘和传给分组逻辑，不必为了输出诊断
    文件再重复扫描全部 snapshot。
    """

    if grouping_method not in GROUPING_METHODS:
        raise ValueError(
            f"grouping_method must be one of {', '.join(GROUPING_METHODS)}"
        )

    if grouping_method == GROUPING_METHOD_RATE_GREEDY:
        return greedy_group_by_match_rate(
            match_counts,
            match_rates,
            min_close_snapshots=min_close_snapshots,
            min_close_rate=min_close_rate,
        )

    compatibility = build_compatibility_matrix(
        match_counts,
        match_rates,
        min_close_snapshots=min_close_snapshots,
        min_close_rate=min_close_rate,
    )
    return minimize_compatibility_groups(
        compatibility,
        max_exact_component_stocks=max_exact_component_stocks,
        exact_search_node_limit=exact_search_node_limit,
    )


def group_relative_clock_vectors(
    vectors: pd.DataFrame,
    *,
    max_clock_gap_us: int = DEFAULT_MAX_CLOCK_GAP_US,
    min_close_snapshots: int = DEFAULT_MIN_CLOSE_SNAPSHOTS,
    min_close_rate: float = DEFAULT_MIN_CLOSE_RATE,
    grouping_method: str = DEFAULT_GROUPING_METHOD,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
) -> pd.DataFrame:
    """构造两两证据矩阵，并使用指定方法生成全配对兼容组。

    逻辑明确拆成三步，后续可以分别替换：

    1. 从相对 ``clock`` 向量计算匹配数和匹配率；
    2. 用两个阈值生成兼容矩阵；
    3. 选择 ``minimize`` 做最少 clique partition，或者选择 ``rate_greedy``
       按匹配率从高到低贪心合并。

    两种方法都保证组内任意股票对通过次数和比例阈值；只有 ``minimize`` 会执行
    精确搜索，``rate_greedy`` 不保证最少组数。
    """

    match_counts, match_rates = calculate_pairwise_match_matrices(
        vectors,
        max_clock_gap_us=max_clock_gap_us,
    )
    return group_pairwise_match_matrices(
        match_counts,
        match_rates,
        min_close_snapshots=min_close_snapshots,
        min_close_rate=min_close_rate,
        grouping_method=grouping_method,
        max_exact_component_stocks=max_exact_component_stocks,
        exact_search_node_limit=exact_search_node_limit,
    )


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
    min_close_rate: float = DEFAULT_MIN_CLOSE_RATE,
    grouping_method: str = DEFAULT_GROUPING_METHOD,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
    match_counts_csv: Path | str | None = None,
    match_rates_csv: Path | str | None = None,
    compatibility_csv: Path | str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """读取 CSV，构造向量和分组，并写出结果及三张股票关系矩阵。"""

    # 输入格式由业务保证正确，因此只读取真正需要的三列，不增加多层清洗逻辑。
    data = pd.read_csv(
        input_csv,
        usecols=REQUIRED_COLUMNS,
        dtype={"clock": "int64", "stock_id": "string", "time": "string"},
    )
    vectors = build_relative_clock_vectors(data)
    match_counts, match_rates = calculate_pairwise_match_matrices(
        vectors,
        max_clock_gap_us=max_clock_gap_us,
    )
    compatibility = build_compatibility_matrix(
        match_counts,
        match_rates,
        min_close_snapshots=min_close_snapshots,
        min_close_rate=min_close_rate,
    )
    groups = group_pairwise_match_matrices(
        match_counts,
        match_rates,
        min_close_snapshots=min_close_snapshots,
        min_close_rate=min_close_rate,
        grouping_method=grouping_method,
        max_exact_component_stocks=max_exact_component_stocks,
        exact_search_node_limit=exact_search_node_limit,
    )

    resolved_match_counts_csv = resolve_relationship_matrix_csv_path(
        groups_csv,
        match_counts_csv,
        "match_counts",
    )
    resolved_match_rates_csv = resolve_relationship_matrix_csv_path(
        groups_csv,
        match_rates_csv,
        "match_rates",
    )
    resolved_compatibility_csv = resolve_relationship_matrix_csv_path(
        groups_csv,
        compatibility_csv,
        "compatibility",
    )

    vectors.reset_index().to_csv(vectors_csv, index=False)
    groups.to_csv(groups_csv, index=False)
    write_relationship_matrix_csv(match_counts, resolved_match_counts_csv)
    write_relationship_matrix_csv(match_rates, resolved_match_rates_csv)
    write_relationship_matrix_csv(compatibility, resolved_compatibility_csv)
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
    parser.add_argument(
        "--min-close-rate",
        type=float,
        default=DEFAULT_MIN_CLOSE_RATE,
        help="接近次数占共同 snapshot 数的最小比例（默认：%(default)s）",
    )
    parser.add_argument(
        "--grouping-method",
        choices=GROUPING_METHODS,
        default=DEFAULT_GROUPING_METHOD,
        help=(
            "分组方法：minimize 尽量减少组数；rate_greedy 按匹配率降序贪心合并"
            "（默认：%(default)s）"
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
        "--match-counts-csv",
        type=Path,
        help="匹配次数矩阵 CSV；默认写到 GROUPS 同目录的 *_match_counts.csv",
    )
    parser.add_argument(
        "--match-rates-csv",
        type=Path,
        help="匹配率矩阵 CSV；默认写到 GROUPS 同目录的 *_match_rates.csv",
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
    match_counts_csv = resolve_relationship_matrix_csv_path(
        arguments.groups_csv,
        arguments.match_counts_csv,
        "match_counts",
    )
    match_rates_csv = resolve_relationship_matrix_csv_path(
        arguments.groups_csv,
        arguments.match_rates_csv,
        "match_rates",
    )
    compatibility_csv = resolve_relationship_matrix_csv_path(
        arguments.groups_csv,
        arguments.compatibility_csv,
        "compatibility",
    )
    vectors, groups = process_csv(
        arguments.input_csv,
        arguments.vectors_csv,
        arguments.groups_csv,
        arguments.plot_png,
        max_clock_gap_us=arguments.max_clock_gap_us,
        min_close_snapshots=arguments.min_close_snapshots,
        min_close_rate=arguments.min_close_rate,
        grouping_method=arguments.grouping_method,
        max_exact_component_stocks=arguments.max_exact_component_stocks,
        exact_search_node_limit=arguments.exact_search_node_limit,
        match_counts_csv=match_counts_csv,
        match_rates_csv=match_rates_csv,
        compatibility_csv=compatibility_csv,
    )

    print(f"snapshot 数：{vectors.shape[1]}")
    print(f"股票数：{vectors.shape[0]}")
    print(f"最终分组数：{groups['group_id'].nunique()}")
    if groups.attrs["grouping_method"] == GROUPING_METHOD_RATE_GREEDY:
        print("分组方法：按匹配率降序贪心合并")
    else:
        print("分组方法：minimum clique partition")
    if groups.attrs["optimal_group_count_proven"]:
        print("最少分组证明：已证明当前分组数为全局最少")
    else:
        print(
            "最少分组证明：尚未证明；"
            f"已知下界={groups.attrs['group_count_lower_bound']}，"
            f"当前上界={groups.attrs['group_count_upper_bound']}"
        )
    print(f"向量 CSV：{arguments.vectors_csv}")
    print(f"分组 CSV：{arguments.groups_csv}")
    print(f"匹配次数矩阵 CSV：{match_counts_csv}")
    print(f"匹配率矩阵 CSV：{match_rates_csv}")
    print(f"兼容矩阵 CSV：{compatibility_csv}")
    print(f"热图 PNG：{arguments.plot_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
