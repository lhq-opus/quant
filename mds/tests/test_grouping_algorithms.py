"""用独立的小规模穷举和朴素合并，检查 V1/V2 分组优化没有改变约束。"""

import os
from pathlib import Path
import random
import subprocess
import sys
import unittest

import numpy as np
import pandas as pd

from mds import relative_clock_grouping as v1
from mds import relative_clock_grouping_v2 as v2


def make_compatibility(conflicts: np.ndarray) -> pd.DataFrame:
    """冲突矩阵取反就是兼容矩阵；测试股票 ID 按相同顺序放在两个轴上。"""

    stock_ids = [f"s{position:03d}" for position in range(len(conflicts))]
    return pd.DataFrame(~conflicts, index=stock_ids, columns=stock_ids)


def brute_force_minimum(conflicts: np.ndarray) -> int:
    """按固定股票顺序枚举分区，不使用 DSATUR、位集合或待测函数。"""

    groups = []
    best_count = len(conflicts)

    def visit(stock: int) -> None:
        # nonlocal 让递归调用共同维护外层的最好组数。
        nonlocal best_count
        if stock == len(conflicts):
            best_count = min(best_count, len(groups))
            return
        if len(groups) >= best_count:
            return

        for group in groups:
            can_join = True
            for member in group:
                if conflicts[stock, member]:
                    can_join = False
                    break
            if can_join:
                group.append(stock)
                visit(stock + 1)
                group.pop()

        groups.append([stock])
        visit(stock + 1)
        groups.pop()

    visit(0)
    return best_count


def old_clique_lower_bound(conflicts: np.ndarray) -> int:
    """保留优化前的静态冲突度选点规则，逐次扫描候选集合求最大值。"""

    degrees = conflicts.sum(axis=1).tolist()
    seeds = sorted(range(len(conflicts)), key=lambda stock: (-degrees[stock], stock))
    best_size = 0
    for seed in seeds[:16]:
        size = 1
        candidates = set(np.flatnonzero(conflicts[seed]).tolist())
        while candidates:
            stock = max(candidates, key=lambda member: (degrees[member], -member))
            size += 1
            candidates.intersection_update(np.flatnonzero(conflicts[stock]).tolist())
        best_size = max(best_size, size)
    return best_size


def plain_greedy_partition(compatibility: np.ndarray, ranked_pairs: list) -> list:
    """逐个交叉成员检查合并条件，作为位集合优化之外的独立参考。"""

    groups = [[stock] for stock in range(len(compatibility))]
    for first_stock, second_stock in ranked_pairs:
        for position, group in enumerate(groups):
            if first_stock in group:
                first_group = position
            if second_stock in group:
                second_group = position
        if first_group == second_group:
            continue

        can_merge = True
        for first_member in groups[first_group]:
            for second_member in groups[second_group]:
                if not compatibility[first_member, second_member]:
                    can_merge = False
        if can_merge:
            kept = min(first_group, second_group)
            removed = max(first_group, second_group)
            groups[kept].extend(groups[removed])
            groups[removed] = []

    return sorted(tuple(sorted(group)) for group in groups if group)


class GroupingAlgorithmTest(unittest.TestCase):
    def assert_valid_result(self, result, compatibility, optimum) -> None:
        """同时检查覆盖、组内全配对约束、上下界及最优性声明。"""

        self.assertEqual(sorted(result["stock_id"]), compatibility.index.tolist())
        actual_count = result["group_id"].nunique()
        for _, group in result.groupby("group_id"):
            members = group["stock_id"].tolist()
            self.assertTrue(compatibility.loc[members, members].to_numpy().all())
        self.assertEqual(result.attrs["group_count_upper_bound"], actual_count)
        self.assertLessEqual(result.attrs["group_count_lower_bound"], optimum)
        self.assertGreaterEqual(actual_count, optimum)
        if result.attrs["optimal_group_count_proven"]:
            self.assertEqual(actual_count, optimum)
            self.assertEqual(result.attrs["group_count_lower_bound"], optimum)

    def test_all_five_stock_graphs_match_independent_exhaustive_search(self) -> None:
        # 5 个顶点有 10 个可能的无向边，共 2**10 = 1024 种冲突图。
        pairs = []
        for first in range(5):
            for second in range(first + 1, 5):
                pairs.append((first, second))

        for graph_number in range(1 << len(pairs)):
            conflicts = np.zeros((5, 5), dtype=bool)
            for edge_number, (first, second) in enumerate(pairs):
                # 图编号的第 edge_number 位为 1 时，加入这一条冲突边。
                if graph_number & (1 << edge_number):
                    conflicts[first, second] = conflicts[second, first] = True
            compatibility = make_compatibility(conflicts)
            optimum = brute_force_minimum(conflicts)
            for module in (v1, v2):
                with self.subTest(module=module.__name__, graph=graph_number):
                    result = module.minimize_compatibility_groups(
                        compatibility, exact_search_node_limit=0
                    )
                    self.assert_valid_result(result, compatibility, optimum)
                    self.assertTrue(result.attrs["optimal_group_count_proven"])

    def test_search_limits_keep_valid_bounds_without_false_optimality(self) -> None:
        # 五边形冲突图需要 3 色，但其最大冲突 clique 只有 2 个顶点。
        conflicts = np.zeros((5, 5), dtype=bool)
        for stock in range(5):
            other = (stock + 1) % 5
            conflicts[stock, other] = conflicts[other, stock] = True
        compatibility = make_compatibility(conflicts)
        for module in (v1, v2):
            for options in (
                {"max_exact_component_stocks": 0},
                {"exact_search_node_limit": 1},
            ):
                with self.subTest(module=module.__name__, options=options):
                    result = module.minimize_compatibility_groups(compatibility, **options)
                    self.assert_valid_result(result, compatibility, 3)
                    self.assertFalse(result.attrs["optimal_group_count_proven"])
                    self.assertEqual(result.attrs["group_count_lower_bound"], 2)
                    self.assertLessEqual(result.attrs["exact_search_nodes"], 1)

    def test_exact_search_improves_incumbent_without_losing_the_better_result(self) -> None:
        # 该图有合法的 4 色初始解，但最少只需 3 色。它专门覆盖递归过程中
        # 上界下降的路径，防止合并“已有色/新色”分支后又用较差解覆盖新上界。
        edges = [
            (2, 0), (2, 1), (3, 1), (3, 2), (4, 0), (4, 3),
            (5, 1), (5, 2), (6, 0), (6, 4), (6, 5),
        ]
        conflicts = np.zeros((7, 7), dtype=bool)
        masks = [0] * 7
        for first, second in edges:
            conflicts[first, second] = conflicts[second, first] = True
            masks[first] |= 1 << second
            masks[second] |= 1 << first
        self.assertEqual(brute_force_minimum(conflicts), 3)
        for module in (v1, v2):
            colors, proven, nodes = module._search_minimum_coloring(
                masks,
                [1, 1, 0, 2, 0, 2, 3],
                3,
                search_node_limit=0,
            )
            self.assertEqual(max(colors) + 1, 3)
            self.assertTrue(proven)
            self.assertGreater(nodes, 0)
            for first, second in edges:
                self.assertNotEqual(colors[first], colors[second])

    def test_compatibility_components_add_and_conflict_components_share_colors(self) -> None:
        # 100 只股票的冲突图由 20 个互不相连的 C5 构成；每个 C5 都只需 3 色，
        # 不同 C5 可以复用同样的 3 个组号，无须把 100 只股票整体做精确搜索。
        conflicts = np.zeros((100, 100), dtype=bool)
        for start in range(0, 100, 5):
            for offset in range(5):
                first = start + offset
                second = start + (offset + 1) % 5
                conflicts[first, second] = conflicts[second, first] = True

        for add_separate_group in (False, True):
            if add_separate_group:
                # 再添加一个兼容图连通分量：其中 3 只股票相互兼容，但与前 100
                # 只股票都冲突。所以总组数须加 1，不能继续复用前面的颜色。
                extended = np.ones((103, 103), dtype=bool)
                extended[:100, :100] = conflicts
                extended[100:, 100:] = False
                compatibility = make_compatibility(extended)
            else:
                compatibility = make_compatibility(conflicts)
            for module in (v1, v2):
                with self.subTest(module=module.__name__, extra=add_separate_group):
                    result = module.minimize_compatibility_groups(
                        compatibility, max_exact_component_stocks=5
                    )
                    self.assert_valid_result(result, compatibility, 3 + add_separate_group)
                    self.assertTrue(result.attrs["optimal_group_count_proven"])
                    self.assertGreater(result.attrs["exact_search_nodes"], 0)

    def test_overall_bounds_can_prove_optimum_despite_one_unresolved_component(self) -> None:
        # 冲突图是 C5 和 K3 的并集。禁用精确搜索后 C5 只能给出 [2,3]，但 K3
        # 已证明需要 3 色；整体上下界都是 max(...)=3，因此整体仍能证明最优。
        conflicts = np.zeros((8, 8), dtype=bool)
        for stock in range(5):
            other = (stock + 1) % 5
            conflicts[stock, other] = conflicts[other, stock] = True
        conflicts[5:, 5:] = True
        np.fill_diagonal(conflicts, False)
        compatibility = make_compatibility(conflicts)
        for module in (v1, v2):
            result = module.minimize_compatibility_groups(
                compatibility, max_exact_component_stocks=0
            )
            self.assert_valid_result(result, compatibility, 3)
            self.assertTrue(result.attrs["optimal_group_count_proven"])
            self.assertEqual(result.attrs["exact_search_nodes"], 0)

    def test_fixed_order_lower_bound_matches_previous_repeated_scan(self) -> None:
        rng = random.Random(20260905)
        for stock_count in (1, 5, 15, 30):
            for density in (0.0, 0.2, 0.5, 0.8, 1.0):
                for _ in range(5):
                    conflicts = np.zeros((stock_count, stock_count), dtype=bool)
                    masks = [0] * stock_count
                    for first in range(stock_count):
                        for second in range(first + 1, stock_count):
                            if rng.random() < density:
                                conflicts[first, second] = conflicts[second, first] = True
                                masks[first] |= 1 << second
                                masks[second] |= 1 << first
                    expected = old_clique_lower_bound(conflicts)
                    for module in (v1, v2):
                        actual = module._greedy_conflict_clique_lower_bound(masks)
                        self.assertEqual(actual, expected)

    def test_greedy_matches_member_by_member_reference(self) -> None:
        rng = random.Random(20260905)
        examples = []
        # a-b、c-d 先合并；a-c、a-d、b-c 会反复触发两个组之间的失败合并。
        # e 后来可以加入 a-b，合并后仍须保留与 d 不兼容的限制。
        rates = np.array(
            [
                [1.00, 0.99, 0.97, 0.96, 0.94],
                [0.99, 1.00, 0.95, 0.10, 0.93],
                [0.97, 0.95, 1.00, 0.98, 0.92],
                [0.96, 0.10, 0.98, 1.00, 0.10],
                [0.94, 0.93, 0.92, 0.10, 1.00],
            ]
        )
        examples.append((rates, np.full((5, 5), 3)))
        for stock_count in (3, 6, 10, 15):
            for _ in range(15):
                rates = np.eye(stock_count)
                counts = np.full((stock_count, stock_count), 3)
                for first in range(stock_count):
                    for second in range(first + 1, stock_count):
                        # 少量离散分值故意制造大量并列，验证次数和股票 ID 的次序。
                        rate = rng.choice([0.2, 0.5, 0.75, 1.0])
                        rates[first, second] = rates[second, first] = rate
                        counts[first, second] = counts[second, first] = rng.choice([1, 2, 3])
                examples.append((rates, counts))

        for example_number, (rates, counts) in enumerate(examples):
            stock_ids = [f"s{position:03d}" for position in range(len(rates))]
            rate_frame = pd.DataFrame(rates, index=stock_ids, columns=stock_ids)
            count_frame = pd.DataFrame(counts, index=stock_ids, columns=stock_ids)
            for module in (v1, v2):
                compatibility = rates >= 0.5
                if module is v1:
                    compatibility &= counts >= 2
                np.fill_diagonal(compatibility, True)
                ranked = []
                for first in range(len(rates)):
                    for second in range(first + 1, len(rates)):
                        if compatibility[first, second]:
                            # V1 还以匹配次数作为第二排序键；V2 只比较余弦分值。
                            tie_count = -int(counts[first, second]) if module is v1 else 0
                            ranked.append((-rates[first, second], tie_count, first, second))
                ranked.sort()
                pairs = [(first, second) for _, _, first, second in ranked]
                expected = plain_greedy_partition(compatibility, pairs)

                if module is v1:
                    result = module.greedy_group_by_match_rate(
                        count_frame, rate_frame, min_close_snapshots=2, min_close_rate=0.5
                    )
                else:
                    result = module.greedy_group_by_cosine_similarity(
                        rate_frame, min_cosine_similarity=0.5
                    )
                actual = []
                positions = dict(zip(stock_ids, range(len(stock_ids))))
                for _, group in result.groupby("group_id"):
                    actual.append(tuple(sorted(positions[stock] for stock in group["stock_id"])))
                with self.subTest(module=module.__name__, example=example_number):
                    self.assertEqual(sorted(actual), expected)

    def test_v2_import_does_not_load_v1(self) -> None:
        # 当前测试进程已加载两版；另起一个干净解释器，直接检查 V2 的真实导入
        # 行为，不依赖源码文字是否相同，也避免已有 sys.modules 掩盖依赖。
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "import sys\nimport mds.relative_clock_grouping_v2\n"
                "assert 'mds.relative_clock_grouping' not in sys.modules\n",
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
