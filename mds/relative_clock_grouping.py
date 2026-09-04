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
    """把两张证据矩阵转换成“能否进入同组”的布尔矩阵。"""

    if min_close_snapshots < 1:
        raise ValueError("min_close_snapshots must be at least 1")
    if not 0 <= min_close_rate <= 1:
        raise ValueError("min_close_rate must be between 0 and 1")

    ordered_counts = match_counts.copy()
    ordered_counts.index = ordered_counts.index.astype(str)
    ordered_counts.columns = ordered_counts.columns.astype(str)
    ordered_counts = ordered_counts.sort_index().reindex(columns=ordered_counts.index)
    ordered_rates = match_rates.copy()
    ordered_rates.index = ordered_rates.index.astype(str)
    ordered_rates.columns = ordered_rates.columns.astype(str)
    ordered_rates = ordered_rates.reindex(
        index=ordered_counts.index,
        columns=ordered_counts.columns,
    )

    compatibility = (ordered_counts.to_numpy() >= min_close_snapshots) & (
        ordered_rates.to_numpy(dtype="float64") >= min_close_rate
    )

    # 生成逻辑本来就是对称的；这里取双向交集，使任意外部传入的矩阵也必须在
    # (i,j) 与 (j,i) 两个方向都通过。对角线固定为 True，因为单例组总是合法。
    compatibility &= compatibility.T
    np.fill_diagonal(compatibility, True)
    return pd.DataFrame(
        compatibility,
        index=ordered_counts.index,
        columns=ordered_counts.columns,
    )


def _boolean_matrix_to_bit_masks(matrix: np.ndarray) -> list[int]:
    """把布尔矩阵每一行压成 Python 整数，便于快速做图集合运算。"""

    if not len(matrix):
        return []
    all_vertices = (1 << len(matrix)) - 1
    packed_rows = np.packbits(matrix, axis=1, bitorder="little")
    return [
        int.from_bytes(row.tobytes(), byteorder="little") & all_vertices
        for row in packed_rows
    ]


def _vertices_from_mask(mask: int) -> list[int]:
    """按编号升序展开 bit mask。"""

    vertices: list[int] = []
    while mask:
        lowest_bit = mask & -mask
        vertices.append(lowest_bit.bit_length() - 1)
        mask ^= lowest_bit
    return vertices


def _connected_components(adjacency_masks: list[int]) -> list[list[int]]:
    """求兼容图连通分量；不同分量的股票不可能放进同一个 clique。"""

    remaining = (1 << len(adjacency_masks)) - 1
    components: list[list[int]] = []

    while remaining:
        seed = remaining & -remaining
        remaining ^= seed
        frontier = seed
        component_mask = 0

        while frontier:
            vertex_bit = frontier & -frontier
            frontier ^= vertex_bit
            component_mask |= vertex_bit
            vertex = vertex_bit.bit_length() - 1

            new_neighbors = adjacency_masks[vertex] & remaining
            remaining ^= new_neighbors
            frontier |= new_neighbors

        components.append(_vertices_from_mask(component_mask))

    return components


def _dsatur_greedy_coloring(conflict_masks: list[int]) -> list[int]:
    """用 DSATUR 贪心给“不兼容图”着色，快速得到分组数上界。"""

    vertex_count = len(conflict_masks)
    colors = [-1] * vertex_count
    neighbor_color_masks = [0] * vertex_count
    degrees = [neighbors.bit_count() for neighbors in conflict_masks]
    uncolored = (1 << vertex_count) - 1
    color_count = 0

    while uncolored:
        # DSATUR 优先选择“已看到颜色种类最多”的股票；并列时优先冲突度高、
        # stock_id 顺序靠前者。这通常比按 stock_id 直接 first-fit 使用更少颜色。
        vertex = max(
            _vertices_from_mask(uncolored),
            key=lambda candidate: (
                neighbor_color_masks[candidate].bit_count(),
                degrees[candidate],
                -candidate,
            ),
        )
        blocked_colors = neighbor_color_masks[vertex]

        for color in range(color_count):
            if not blocked_colors & (1 << color):
                break
        else:
            color = color_count
            color_count += 1

        colors[vertex] = color
        uncolored ^= 1 << vertex

        neighbors = conflict_masks[vertex] & uncolored
        while neighbors:
            neighbor_bit = neighbors & -neighbors
            neighbors ^= neighbor_bit
            neighbor = neighbor_bit.bit_length() - 1
            neighbor_color_masks[neighbor] |= 1 << color

    return colors


def _greedy_conflict_clique_lower_bound(conflict_masks: list[int]) -> int:
    """在不兼容图中寻找一个 clique，作为最少颜色数的可靠下界。"""

    vertex_count = len(conflict_masks)
    if vertex_count == 0:
        return 0

    degrees = [neighbors.bit_count() for neighbors in conflict_masks]
    seed_order = sorted(
        range(vertex_count), key=lambda vertex: (-degrees[vertex], vertex)
    )
    best_size = 1

    # 任意冲突 clique 中的成员都必须使用不同颜色。这里只尝试若干高冲突起点，
    # 目的是快速得到“至少需要多少组”的下界，而不是在这里再解一次最大 clique。
    for seed in seed_order[: min(vertex_count, 16)]:
        clique_size = 1
        candidates = conflict_masks[seed]
        while candidates:
            vertex = max(
                _vertices_from_mask(candidates),
                key=lambda candidate: (degrees[candidate], -candidate),
            )
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
    """按匹配率从高到低贪心合并，同时维持组内全配对约束。

    算法从“每只股票各自一组”开始，只保留同时通过匹配次数和匹配率阈值的
    股票对，并按以下稳定顺序处理：

    1. 匹配率从高到低；
    2. 匹配率相同时，匹配次数从高到低；
    3. 两项都相同时，按两个 ``stock_id`` 排序。

    处理一对股票时，如果它们已经在同一组就跳过；否则尝试合并它们当前所在
    的两个组。只有两个组之间的每一个交叉股票对都通过阈值，才真正合并。因此
    输出仍保证组内任意成员两两兼容。

    这种方法优先保留证据最强的股票对，但早期合并不会回退，所以不保证使用
    最少组数。返回结果会在 ``DataFrame.attrs`` 中报告当前上下界和是否碰巧已
    由上下界相等证明最优，便于与 minimum clique partition 方法直接比较。
    """

    compatibility_frame = build_compatibility_matrix(
        match_counts,
        match_rates,
        min_close_snapshots=min_close_snapshots,
        min_close_rate=min_close_rate,
    )
    stock_ids = compatibility_frame.index.tolist()
    stock_count = len(stock_ids)
    compatibility = compatibility_frame.to_numpy(dtype=bool)
    compatibility_masks = _boolean_matrix_to_bit_masks(compatibility)

    ordered_counts = match_counts.copy()
    ordered_counts.index = ordered_counts.index.astype(str)
    ordered_counts.columns = ordered_counts.columns.astype(str)
    ordered_counts = ordered_counts.reindex(index=stock_ids, columns=stock_ids)
    ordered_rates = match_rates.copy()
    ordered_rates.index = ordered_rates.index.astype(str)
    ordered_rates.columns = ordered_rates.columns.astype(str)
    ordered_rates = ordered_rates.reindex(index=stock_ids, columns=stock_ids)
    count_values = ordered_counts.to_numpy()
    rate_values = ordered_rates.to_numpy(dtype="float64")

    candidate_pairs: list[tuple[float, int, str, str, int, int]] = []
    for first_stock in range(stock_count):
        for second_stock in range(first_stock + 1, stock_count):
            if not compatibility[first_stock, second_stock]:
                continue

            # build_compatibility_matrix 已要求两个方向都通过。排序强度也保守地
            # 取双向较小值；由本脚本生成的证据矩阵本来就是完全对称的。
            pair_rate = min(
                rate_values[first_stock, second_stock],
                rate_values[second_stock, first_stock],
            )
            pair_count = int(
                min(
                    count_values[first_stock, second_stock],
                    count_values[second_stock, first_stock],
                )
            )
            candidate_pairs.append(
                (
                    -pair_rate,
                    -pair_count,
                    stock_ids[first_stock],
                    stock_ids[second_stock],
                    first_stock,
                    second_stock,
                )
            )

    candidate_pairs.sort()

    # group_of 记录每只股票当前所属组；group_masks 用一个整数保存组内成员集合。
    # bit mask 可以快速检查“另一组的所有成员是否都在某股票的兼容集合里”。
    group_of = list(range(stock_count))
    group_masks = {stock: 1 << stock for stock in range(stock_count)}

    for _, _, _, _, first_stock, second_stock in candidate_pairs:
        first_group = group_of[first_stock]
        second_group = group_of[second_stock]
        if first_group == second_group:
            continue

        first_members = group_masks[first_group]
        second_members = group_masks[second_group]
        can_merge = all(
            compatibility_masks[member] & second_members == second_members
            for member in _vertices_from_mask(first_members)
        )
        if not can_merge:
            continue

        # 总是保留编号较小的内部组 ID，只用于让过程可复现，不影响最终 group_id。
        kept_group = min(first_group, second_group)
        removed_group = max(first_group, second_group)
        removed_members = group_masks[removed_group]
        group_masks[kept_group] |= removed_members
        del group_masks[removed_group]
        for member in _vertices_from_mask(removed_members):
            group_of[member] = kept_group

    groups = [
        [stock_ids[member] for member in _vertices_from_mask(member_mask)]
        for member_mask in group_masks.values()
    ]
    groups = [sorted(group) for group in groups]
    groups.sort(key=lambda group: group[0])
    rows = [
        (stock_id, group_id)
        for group_id, group in enumerate(groups, start=1)
        for stock_id in group
    ]

    # 冲突 clique 给出可靠下界。贪心结果若恰好等于下界，虽然算法本身不是精确
    # 算法，这一个具体输入上的结果仍可被证明为全局最优。
    group_count_lower_bound = 0
    for component in _connected_components(compatibility_masks):
        local_compatibility = compatibility[np.ix_(component, component)]
        local_conflicts = ~local_compatibility
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
    """用 DSATUR 分支限界搜索更少颜色；返回结果、是否已证明最优、节点数。"""

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
        nonlocal best_colors
        nonlocal best_color_count
        nonlocal searched_nodes
        nonlocal search_was_cut_off

        # 已经达到可靠下界时，不可能再找到颜色更少的方案，因而已经证明最优。
        if best_color_count == lower_bound or search_was_cut_off:
            return
        if not uncolored:
            best_colors = colors.copy()
            best_color_count = used_color_count
            return
        if used_color_count >= best_color_count:
            return
        if search_node_limit and searched_nodes >= search_node_limit:
            search_was_cut_off = True
            return
        searched_nodes += 1

        vertex = max(
            _vertices_from_mask(uncolored),
            key=lambda candidate: (
                neighbor_color_masks[candidate].bit_count(),
                degrees[candidate],
                -candidate,
            ),
        )
        remaining = uncolored ^ (1 << vertex)
        blocked_colors = neighbor_color_masks[vertex]

        # 先尝试已有且成员较多的颜色，通常可以更快找到比当前上界更好的方案。
        available_colors = [
            color
            for color in range(used_color_count)
            if not blocked_colors & (1 << color)
        ]
        available_colors.sort(key=lambda color: (-color_sizes[color], color))

        for color in available_colors:
            colors[vertex] = color
            color_sizes[color] += 1
            changed_neighbors: list[tuple[int, int]] = []
            color_bit = 1 << color
            neighbors = conflict_masks[vertex] & remaining
            while neighbors:
                neighbor_bit = neighbors & -neighbors
                neighbors ^= neighbor_bit
                neighbor = neighbor_bit.bit_length() - 1
                old_mask = neighbor_color_masks[neighbor]
                if not old_mask & color_bit:
                    changed_neighbors.append((neighbor, old_mask))
                    neighbor_color_masks[neighbor] = old_mask | color_bit

            search(remaining, used_color_count)

            for neighbor, old_mask in changed_neighbors:
                neighbor_color_masks[neighbor] = old_mask
            color_sizes[color] -= 1
            colors[vertex] = -1
            if best_color_count == lower_bound or search_was_cut_off:
                return

        # 新颜色的编号固定为 used_color_count，避免枚举只是颜色编号不同的重复解。
        # 新建后若已经达到当前最优组数，就不可能改进，因此只尝试严格更小的情况。
        if used_color_count + 1 < best_color_count:
            color = used_color_count
            colors[vertex] = color
            color_sizes[color] = 1
            changed_neighbors = []
            color_bit = 1 << color
            neighbors = conflict_masks[vertex] & remaining
            while neighbors:
                neighbor_bit = neighbors & -neighbors
                neighbors ^= neighbor_bit
                neighbor = neighbor_bit.bit_length() - 1
                old_mask = neighbor_color_masks[neighbor]
                if not old_mask & color_bit:
                    changed_neighbors.append((neighbor, old_mask))
                    neighbor_color_masks[neighbor] = old_mask | color_bit

            search(remaining, used_color_count + 1)

            for neighbor, old_mask in changed_neighbors:
                neighbor_color_masks[neighbor] = old_mask
            color_sizes[color] = 0
            colors[vertex] = -1

    search((1 << vertex_count) - 1, 0)
    is_optimal = best_color_count == lower_bound or not search_was_cut_off
    return best_colors, is_optimal, searched_nodes


def minimize_compatibility_groups(
    compatibility_matrix: pd.DataFrame,
    *,
    max_exact_component_stocks: int = DEFAULT_MAX_EXACT_COMPONENT_STOCKS,
    exact_search_node_limit: int = DEFAULT_EXACT_SEARCH_NODE_LIMIT,
) -> pd.DataFrame:
    """把兼容矩阵划分成尽量少的全配对兼容组。

    在兼容图中，每个合法组必须是 clique。把不兼容关系取补图后，问题等价于
    “用尽量少的颜色给冲突图着色”，一般情形属于 NP-hard 问题。

    本函数先用 DSATUR 得到较好的上界，再用冲突 clique 得到可靠下界：若二者
    相等就已证明最优；否则仅对不超过 ``max_exact_component_stocks`` 的兼容图
    连通分量做分支限界精确搜索。搜索节点达到 ``exact_search_node_limit`` 后
    返回当前最好结果，并通过 DataFrame.attrs 明确标记尚未证明最优。将节点上限
    设为 0 可取消搜索节点限制，但 NP-hard 输入可能运行很久。
    """

    if max_exact_component_stocks < 0:
        raise ValueError("max_exact_component_stocks must be non-negative")
    if exact_search_node_limit < 0:
        raise ValueError("exact_search_node_limit must be non-negative")

    ordered = compatibility_matrix.copy()
    ordered.index = ordered.index.astype(str)
    ordered.columns = ordered.columns.astype(str)
    ordered = ordered.sort_index()
    if set(ordered.index) != set(ordered.columns):
        raise ValueError("compatibility matrix must use the same row and column labels")
    ordered = ordered.reindex(columns=ordered.index)
    if ordered.isna().any().any():
        raise ValueError("compatibility matrix must not contain missing values")

    compatibility = ordered.to_numpy(dtype=bool, copy=True)
    if not np.array_equal(compatibility, compatibility.T):
        raise ValueError("compatibility matrix must be symmetric")
    np.fill_diagonal(compatibility, True)

    stock_ids = ordered.index.tolist()
    compatibility_masks = _boolean_matrix_to_bit_masks(compatibility)
    components = _connected_components(compatibility_masks)

    groups: list[list[str]] = []
    total_lower_bound = 0
    all_components_proven_optimal = True
    total_searched_nodes = 0

    # 不同兼容连通分量之间没有任何兼容边，所以一个合法组不可能跨分量；分别
    # 求解再相加不会损失全局最优性，也能把多数实际问题缩成更小的子问题。
    for component in components:
        local_compatibility = compatibility[np.ix_(component, component)]
        local_conflicts = ~local_compatibility
        np.fill_diagonal(local_conflicts, False)
        conflict_masks = _boolean_matrix_to_bit_masks(local_conflicts)

        colors = _dsatur_greedy_coloring(conflict_masks)
        color_count = max(colors, default=-1) + 1
        lower_bound = _greedy_conflict_clique_lower_bound(conflict_masks)
        component_is_optimal = color_count == lower_bound

        if not component_is_optimal and len(component) <= max_exact_component_stocks:
            colors, component_is_optimal, searched_nodes = _search_minimum_coloring(
                conflict_masks,
                colors,
                lower_bound,
                search_node_limit=exact_search_node_limit,
            )
            color_count = max(colors, default=-1) + 1
            total_searched_nodes += searched_nodes

        if component_is_optimal:
            # 搜索穷尽或上下界相遇后，真实下界就是已经得到的最优组数。
            lower_bound = color_count
        else:
            all_components_proven_optimal = False
        total_lower_bound += lower_bound

        groups_by_color: dict[int, list[str]] = {}
        for local_vertex, color in enumerate(colors):
            global_vertex = component[local_vertex]
            groups_by_color.setdefault(color, []).append(stock_ids[global_vertex])
        groups.extend(groups_by_color.values())

    # 颜色编号只是求解器内部符号。最终按每组最小 stock_id 稳定排序、重新编号，
    # 使同一输入的 CSV 输出可复现。
    groups = [sorted(group) for group in groups]
    groups.sort(key=lambda group: group[0])
    rows = [
        (stock_id, group_id)
        for group_id, group in enumerate(groups, start=1)
        for stock_id in group
    ]
    result = pd.DataFrame(rows, columns=["stock_id", "group_id"])
    result.attrs["grouping_method"] = GROUPING_METHOD_MINIMIZE
    result.attrs["optimal_group_count_proven"] = all_components_proven_optimal
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
        help="minimize 方法允许精确搜索的最大连通分量股票数（默认：%(default)s）",
    )
    parser.add_argument(
        "--exact-search-node-limit",
        type=int,
        default=DEFAULT_EXACT_SEARCH_NODE_LIMIT,
        help="minimize 方法每次精确搜索的节点上限；0 表示不限制（默认：%(default)s）",
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
