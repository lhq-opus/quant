from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from mds.relative_clock_grouping import (
    build_compatibility_matrix,
    build_relative_clock_vectors,
    calculate_pairwise_match_matrices,
    greedy_group_by_match_rate,
    group_relative_clock_vectors,
    main,
    minimize_compatibility_groups,
    plot_relative_clock_vectors,
    write_relationship_matrix_csv,
)


def make_market_data() -> pd.DataFrame:
    """创建三个 snapshot；组内接近、组间相隔数千微秒。"""

    return pd.DataFrame(
        {
            # 每个 time 内已按 clock 排序，符合新脚本的输入前提。
            "clock": [
                1_000,
                1_020,
                10_000,
                10_020,
                2_000,
                2_010,
                2_500,
                12_000,
                12_020,
                3_000,
                3_030,
                11_000,
                11_020,
            ],
            "stock_id": [
                "a",
                "b",
                "c",
                "d",
                "a",
                "b",
                "e",
                "c",
                "d",
                "a",
                "b",
                "c",
                "d",
            ],
            "time": [
                "t1",
                "t1",
                "t1",
                "t1",
                "t2",
                "t2",
                "t2",
                "t2",
                "t2",
                "t3",
                "t3",
                "t3",
                "t3",
            ],
        }
    ).astype({"clock": "int64", "stock_id": "string", "time": "string"})


def read_relationship_matrix(csv_path: Path) -> pd.DataFrame:
    """回读矩阵 CSV，并恢复第一列为股票行索引。"""

    matrix = pd.read_csv(csv_path, dtype={"stock_id": "string"}).set_index("stock_id")
    matrix.index = matrix.index.astype(str)
    return matrix


class RelativeClockVectorTest(unittest.TestCase):
    def test_first_clock_is_zero_and_missing_snapshot_stays_missing(self) -> None:
        vectors = build_relative_clock_vectors(make_market_data())

        self.assertEqual(vectors.columns.tolist(), ["t1", "t2", "t3"])
        self.assertEqual(vectors.index.tolist(), ["a", "b", "c", "d", "e"])
        self.assertEqual(vectors.loc["a"].tolist(), [0, 0, 0])
        self.assertEqual(vectors.loc["b"].tolist(), [20, 10, 30])
        self.assertEqual(vectors.loc["c"].tolist(), [9_000, 10_000, 8_000])
        self.assertTrue(pd.isna(vectors.loc["e", "t1"]))
        self.assertEqual(vectors.loc["e", "t2"], 500)

    def test_grouping_uses_common_dimensions_and_keeps_sparse_stock_single(
        self,
    ) -> None:
        vectors = build_relative_clock_vectors(make_market_data())
        groups = group_relative_clock_vectors(
            vectors,
            max_clock_gap_us=100,
            min_close_snapshots=2,
        )

        mapping = groups.set_index("stock_id")["group_id"].to_dict()
        self.assertEqual(mapping, {"a": 1, "b": 1, "c": 2, "d": 2, "e": 3})

    def test_one_cross_group_collision_is_diluted_by_other_snapshots(self) -> None:
        vectors = pd.DataFrame(
            {
                "t1": [0, 20, 10_000, 10_020],
                # t2 中两个真实组偶然靠近，但另外两个 snapshot 仍相隔很远。
                "t2": [0, 20, 40, 60],
                "t3": [0, 20, 9_000, 9_020],
            },
            index=["a", "b", "c", "d"],
            dtype="Int64",
        )

        groups = group_relative_clock_vectors(
            vectors,
            max_clock_gap_us=100,
            min_close_snapshots=2,
        )

        mapping = groups.set_index("stock_id")["group_id"].to_dict()
        self.assertEqual(mapping, {"a": 1, "b": 1, "c": 2, "d": 2})

    def test_stock_must_match_every_existing_group_member(self) -> None:
        vectors = pd.DataFrame(
            {
                # 每个 snapshot 都有：a-b 差 50、b-c 差 70、a-c 差 120。
                # 阈值为 100 时只有 a-b 和 b-c 建边，a-c 不建边。
                "t1": [0, 50, 120],
                "t2": [0, 50, 120],
                "t3": [0, 50, 120],
            },
            index=["a", "b", "c"],
            dtype="Int64",
        )

        groups = group_relative_clock_vectors(
            vectors,
            max_clock_gap_us=100,
            min_close_snapshots=2,
            min_close_rate=0.5,
        )

        # a、b 先形成组。c 只满足与 b 的阈值，不满足与 a 的阈值，所以不能加入。
        mapping = groups.set_index("stock_id")["group_id"].to_dict()
        self.assertEqual(mapping, {"a": 1, "b": 1, "c": 2})

    def test_close_rate_can_be_adjusted_without_changing_other_stages(self) -> None:
        vectors = pd.DataFrame(
            {
                # a-b 在三个共同维度中有两个维度接近，close_rate = 2 / 3。
                "t1": [0, 20],
                "t2": [0, 20],
                "t3": [0, 500],
            },
            index=["a", "b"],
            dtype="Int64",
        )

        loose_groups = group_relative_clock_vectors(
            vectors,
            max_clock_gap_us=100,
            min_close_snapshots=2,
            min_close_rate=0.5,
        )
        strict_groups = group_relative_clock_vectors(
            vectors,
            max_clock_gap_us=100,
            min_close_snapshots=2,
            min_close_rate=0.8,
        )

        self.assertEqual(loose_groups["group_id"].tolist(), [1, 1])
        self.assertEqual(strict_groups["group_id"].tolist(), [1, 2])

    def test_pairwise_matrices_record_match_count_and_rate(self) -> None:
        vectors = pd.DataFrame(
            {
                # a-b 共同出现 3 次，其中 t1、t2 的差不超过 100 微秒。
                "t1": [0, 20, pd.NA],
                "t2": [0, 80, 5_000],
                "t3": [0, 500, 5_000],
            },
            index=["a", "b", "c"],
            dtype="Int64",
        )

        match_counts, match_rates = calculate_pairwise_match_matrices(
            vectors,
            max_clock_gap_us=100,
        )

        self.assertEqual(match_counts.loc["a", "b"], 2)
        self.assertAlmostEqual(match_rates.loc["a", "b"], 2 / 3)
        self.assertEqual(match_counts.loc["a", "c"], 0)
        self.assertEqual(match_rates.loc["a", "c"], 0)
        self.assertEqual(match_counts.loc["a", "a"], 3)
        self.assertEqual(match_rates.loc["a", "a"], 1)


class MinimumGroupPartitionTest(unittest.TestCase):
    def test_minimization_and_rate_greedy_differ_on_counterexample(self) -> None:
        # 通过阈值的兼容边只有 a-c、a-d、b-c。
        # a-c 匹配率最高，所以 rate_greedy 会先固定 {a,c}，最终需要 3 组；
        # minimum clique partition 则找到 {a,d}、{b,c}，只需要 2 组。
        stock_ids = ["a", "b", "c", "d"]
        match_counts = pd.DataFrame(0, index=stock_ids, columns=stock_ids)
        match_rates = pd.DataFrame(0.0, index=stock_ids, columns=stock_ids)
        for stock_id in stock_ids:
            match_counts.loc[stock_id, stock_id] = 3
            match_rates.loc[stock_id, stock_id] = 1.0
        pair_rates = {("a", "c"): 0.99, ("a", "d"): 0.8, ("b", "c"): 0.8}
        for (first_stock, second_stock), match_rate in pair_rates.items():
            match_counts.loc[first_stock, second_stock] = 3
            match_counts.loc[second_stock, first_stock] = 3
            match_rates.loc[first_stock, second_stock] = match_rate
            match_rates.loc[second_stock, first_stock] = match_rate

        compatibility = build_compatibility_matrix(
            match_counts,
            match_rates,
            min_close_snapshots=2,
            min_close_rate=0.5,
        )
        groups = minimize_compatibility_groups(compatibility)
        greedy_groups = greedy_group_by_match_rate(
            match_counts,
            match_rates,
            min_close_snapshots=2,
            min_close_rate=0.5,
        )

        grouped_stocks = {
            frozenset(group["stock_id"])
            for _, group in groups.groupby("group_id", sort=True)
        }
        self.assertEqual(grouped_stocks, {frozenset({"a", "d"}), frozenset({"b", "c"})})
        self.assertTrue(groups.attrs["optimal_group_count_proven"])
        self.assertEqual(groups.attrs["group_count_lower_bound"], 2)
        self.assertEqual(groups.attrs["group_count_upper_bound"], 2)

        greedy_grouped_stocks = {
            frozenset(group["stock_id"])
            for _, group in greedy_groups.groupby("group_id", sort=True)
        }
        self.assertEqual(
            greedy_grouped_stocks,
            {frozenset({"a", "c"}), frozenset({"b"}), frozenset({"d"})},
        )
        self.assertFalse(greedy_groups.attrs["optimal_group_count_proven"])
        self.assertEqual(greedy_groups.attrs["group_count_lower_bound"], 2)
        self.assertEqual(greedy_groups.attrs["group_count_upper_bound"], 3)

    def test_exact_search_and_best_effort_status_are_distinguished(self) -> None:
        # 不兼容图是长度为 5 的奇环：最大冲突 clique 只有 2 个点，但至少需要
        # 3 种颜色。它迫使分支限界真正搜索，不能只靠上下界立即得出结论。
        stock_ids = ["a", "b", "c", "d", "e"]
        compatibility = pd.DataFrame(True, index=stock_ids, columns=stock_ids)
        for first_stock, second_stock in [
            ("a", "b"),
            ("b", "c"),
            ("c", "d"),
            ("d", "e"),
            ("e", "a"),
        ]:
            compatibility.loc[first_stock, second_stock] = False
            compatibility.loc[second_stock, first_stock] = False

        exact_groups = minimize_compatibility_groups(compatibility)
        best_effort_groups = minimize_compatibility_groups(
            compatibility,
            max_exact_component_stocks=0,
        )

        self.assertEqual(exact_groups["group_id"].nunique(), 3)
        self.assertTrue(exact_groups.attrs["optimal_group_count_proven"])
        self.assertGreater(exact_groups.attrs["exact_search_nodes"], 0)
        self.assertEqual(best_effort_groups["group_id"].nunique(), 3)
        self.assertFalse(best_effort_groups.attrs["optimal_group_count_proven"])
        self.assertEqual(best_effort_groups.attrs["group_count_lower_bound"], 2)
        self.assertEqual(best_effort_groups.attrs["group_count_upper_bound"], 3)


class RelationshipMatrixCsvTest(unittest.TestCase):
    def test_matrix_csv_keeps_stock_ids_on_both_axes(self) -> None:
        matrix = pd.DataFrame(
            [[1.0, 0.25], [0.25, 1.0]],
            index=["000001", "600000"],
            columns=["000001", "600000"],
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_csv = Path(temporary_directory) / "matrix.csv"
            write_relationship_matrix_csv(matrix, output_csv)
            written = read_relationship_matrix(output_csv)

        self.assertEqual(
            written.index.tolist(),
            ["000001", "600000"],
        )
        self.assertEqual(
            written.columns.tolist(),
            ["000001", "600000"],
        )
        np.testing.assert_allclose(written.to_numpy(), matrix.to_numpy())


class RelativeClockVisualizationTest(unittest.TestCase):
    def test_visualization_and_cli_write_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market.csv"
            vectors_csv = directory / "vectors.csv"
            groups_csv = directory / "groups.csv"
            plot_png = directory / "vectors.png"
            match_counts_csv = directory / "groups_match_counts.csv"
            match_rates_csv = directory / "groups_match_rates.csv"
            compatibility_csv = directory / "groups_compatibility.csv"
            make_market_data().to_csv(input_csv, index=False)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        str(input_csv),
                        str(vectors_csv),
                        str(groups_csv),
                        str(plot_png),
                        "--max-clock-gap-us",
                        "100",
                        "--min-close-snapshots",
                        "2",
                        "--min-close-rate",
                        "0.5",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                pd.read_csv(groups_csv).to_dict("records"),
                [
                    {"stock_id": "a", "group_id": 1},
                    {"stock_id": "b", "group_id": 1},
                    {"stock_id": "c", "group_id": 2},
                    {"stock_id": "d", "group_id": 2},
                    {"stock_id": "e", "group_id": 3},
                ],
            )
            self.assertEqual(
                pd.read_csv(vectors_csv).columns.tolist(),
                ["stock_id", "t1", "t2", "t3"],
            )
            self.assertTrue(plot_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            expected_vectors = build_relative_clock_vectors(make_market_data())
            expected_counts, expected_rates = calculate_pairwise_match_matrices(
                expected_vectors,
                max_clock_gap_us=100,
            )
            expected_compatibility = build_compatibility_matrix(
                expected_counts,
                expected_rates,
                min_close_snapshots=2,
                min_close_rate=0.5,
            )
            written_counts = read_relationship_matrix(match_counts_csv)
            written_rates = read_relationship_matrix(match_rates_csv)
            written_compatibility = read_relationship_matrix(compatibility_csv)

            self.assertEqual(
                written_counts.index.tolist(), expected_counts.index.tolist()
            )
            self.assertEqual(
                written_counts.columns.tolist(),
                expected_counts.columns.tolist(),
            )
            np.testing.assert_array_equal(
                written_counts.to_numpy(),
                expected_counts.to_numpy(),
            )
            np.testing.assert_allclose(
                written_rates.to_numpy(),
                expected_rates.to_numpy(),
            )
            np.testing.assert_array_equal(
                written_compatibility.to_numpy(),
                expected_compatibility.to_numpy(),
            )
            self.assertEqual(
                set(directory.iterdir()),
                {
                    input_csv,
                    vectors_csv,
                    groups_csv,
                    plot_png,
                    match_counts_csv,
                    match_rates_csv,
                    compatibility_csv,
                },
            )
            self.assertIn("snapshot 数：3", output.getvalue())
            self.assertIn("最终分组数：3", output.getvalue())
            self.assertIn("已证明当前分组数为全局最少", output.getvalue())
            self.assertIn(f"匹配次数矩阵 CSV：{match_counts_csv}", output.getvalue())
            self.assertIn(f"匹配率矩阵 CSV：{match_rates_csv}", output.getvalue())
            self.assertIn(f"兼容矩阵 CSV：{compatibility_csv}", output.getvalue())

    def test_cli_can_select_rate_greedy_grouping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market.csv"
            match_counts_csv = directory / "custom-counts.csv"
            match_rates_csv = directory / "custom-rates.csv"
            compatibility_csv = directory / "custom-compatibility.csv"
            make_market_data().to_csv(input_csv, index=False)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        str(input_csv),
                        str(directory / "vectors.csv"),
                        str(directory / "groups.csv"),
                        str(directory / "vectors.png"),
                        "--max-clock-gap-us",
                        "100",
                        "--min-close-snapshots",
                        "2",
                        "--grouping-method",
                        "rate_greedy",
                        "--match-counts-csv",
                        str(match_counts_csv),
                        "--match-rates-csv",
                        str(match_rates_csv),
                        "--compatibility-csv",
                        str(compatibility_csv),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(match_counts_csv.is_file())
            self.assertTrue(match_rates_csv.is_file())
            self.assertTrue(compatibility_csv.is_file())
            self.assertIn("分组方法：按匹配率降序贪心合并", output.getvalue())

    def test_plot_function_is_callable_without_grouping_function(self) -> None:
        vectors = build_relative_clock_vectors(make_market_data())
        manual_groups = pd.DataFrame(
            {
                "stock_id": ["a", "b", "c", "d", "e"],
                "group_id": [1, 1, 2, 2, 3],
            }
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_png = Path(temporary_directory) / "manual-groups.png"
            plot_relative_clock_vectors(vectors, manual_groups, output_png)
            self.assertGreater(output_png.stat().st_size, 1_000)


if __name__ == "__main__":
    unittest.main()
