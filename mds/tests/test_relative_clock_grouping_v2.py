from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from mds.relative_clock_grouping_v2 import (
    COSINE_GROUPING_METHOD_GREEDY,
    COSINE_GROUPING_METHOD_MINIMIZE,
    build_cosine_compatibility_matrix,
    calculate_cosine_similarity_matrix,
    greedy_group_by_cosine_similarity,
    group_by_cosine_similarity,
    group_relative_clock_vectors,
    group_relative_clock_vectors_v2,
    main,
    minimize_cosine_similarity_groups,
)


def make_market_data() -> pd.DataFrame:
    """构造方向相同的 a/b、方向不同的 c，以及零向量 z。"""

    return pd.DataFrame(
        {
            # 每个 time 内按 clock 升序排列。以 z 为零点后：
            # a = [100, 200, 300]
            # b = [200, 400, 600]，与 a 的余弦相似度为 1
            # c = [300, 100, 400]，与 a/b 的相似度约为 0.891
            # z = [0, 0, 0]
            "clock": [
                1_000,
                1_100,
                1_200,
                1_300,
                2_000,
                2_100,
                2_200,
                2_400,
                3_000,
                3_300,
                3_400,
                3_600,
            ],
            "stock_id": [
                "z",
                "a",
                "b",
                "c",
                "z",
                "c",
                "a",
                "b",
                "z",
                "a",
                "c",
                "b",
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
                "t3",
                "t3",
                "t3",
                "t3",
            ],
        }
    ).astype({"clock": "int64", "stock_id": "string", "time": "string"})


class CosineSimilarityTest(unittest.TestCase):
    def test_similarity_uses_only_common_dimensions_and_ignores_scale(self) -> None:
        vectors = pd.DataFrame(
            {
                # a-b 只共同拥有 t1、t2；b 在 t3 的 999 不参与这对股票的计算。
                "t1": [1, 10, pd.NA],
                "t2": [2, 20, pd.NA],
                "t3": [pd.NA, 999, 1],
            },
            index=["a", "b", "c"],
            dtype="Int64",
        )

        similarities, common_counts = calculate_cosine_similarity_matrix(
            vectors,
            min_common_snapshots=2,
            min_common_rate=0.5,
        )

        # [1, 2] 与 [10, 20] 方向相同，虽然绝对大小相差 10 倍，余弦仍为 1。
        self.assertAlmostEqual(similarities.loc["a", "b"], 1.0)
        self.assertEqual(common_counts.loc["a", "b"], 2)

        # b-c 只有一个共同维度，没有达到最少 2 个共同 snapshot。
        self.assertTrue(np.isnan(similarities.loc["b", "c"]))
        self.assertEqual(common_counts.loc["b", "c"], 1)

    def test_common_rate_filters_pairs_with_too_little_overlap(self) -> None:
        vectors = pd.DataFrame(
            {
                # 两只股票各出现 4 次，但只有 t1、t2 重合，common_rate = 2 / 4。
                "t1": [1, 10],
                "t2": [2, 20],
                "t3": [3, pd.NA],
                "t4": [4, pd.NA],
                "t5": [pd.NA, 30],
                "t6": [pd.NA, 40],
            },
            index=["a", "b"],
            dtype="Int64",
        )

        accepted, _ = calculate_cosine_similarity_matrix(
            vectors,
            min_common_snapshots=2,
            min_common_rate=0.5,
        )
        rejected, _ = calculate_cosine_similarity_matrix(
            vectors,
            min_common_snapshots=2,
            min_common_rate=0.75,
        )

        self.assertAlmostEqual(accepted.loc["a", "b"], 1.0)
        self.assertTrue(np.isnan(rejected.loc["a", "b"]))

    def test_zero_vector_rule_is_explicit(self) -> None:
        vectors = pd.DataFrame(
            {
                "t1": [0, 0, 1],
                "t2": [0, 0, 2],
            },
            index=["zero_a", "zero_b", "nonzero"],
            dtype="Int64",
        )

        similarities, _ = calculate_cosine_similarity_matrix(
            vectors,
            min_common_snapshots=2,
            min_common_rate=1.0,
        )

        self.assertEqual(similarities.loc["zero_a", "zero_b"], 1.0)
        self.assertEqual(similarities.loc["zero_a", "nonzero"], 0.0)


class AllPairsGroupingTest(unittest.TestCase):
    def test_stock_must_match_every_existing_group_member(self) -> None:
        # 三个二维向量方向约为 0°、30°、60°。
        # 阈值 0.8 下 a-b、b-c 通过，而 a-c 不通过。
        vectors = pd.DataFrame(
            {
                "t1": [100, 87, 50],
                "t2": [0, 50, 87],
            },
            index=["a", "b", "c"],
            dtype="Int64",
        )

        groups = group_relative_clock_vectors_v2(
            vectors,
            min_cosine_similarity=0.8,
            min_common_snapshots=2,
            min_common_rate=1.0,
        )

        mapping = groups.set_index("stock_id")["group_id"].to_dict()
        self.assertEqual(mapping, {"a": 1, "b": 1, "c": 2})

    def test_nan_similarity_does_not_satisfy_the_group_threshold(self) -> None:
        similarities = pd.DataFrame(
            [[1.0, np.nan], [np.nan, 1.0]],
            index=["a", "b"],
            columns=["a", "b"],
        )

        groups = group_by_cosine_similarity(
            similarities,
            min_cosine_similarity=0.9,
        )

        self.assertEqual(groups["group_id"].tolist(), [1, 2])

    def test_minimization_and_cosine_greedy_differ_on_counterexample(self) -> None:
        # 达到 0.8 阈值的兼容边只有 a-c、a-d、b-c。
        # a-c 相似度最高，所以 cosine_greedy 会先固定 {a,c}。此后 b 不能和 a
        # 同组、d 不能和 c 同组，而且 b-d 也不兼容，最终只能得到 3 组。
        # 最少分组方法不受这个局部选择限制，可找到 {a,d}、{b,c} 两组。
        stock_ids = ["a", "b", "c", "d"]
        similarities = pd.DataFrame(0.1, index=stock_ids, columns=stock_ids)
        for stock_id in stock_ids:
            similarities.loc[stock_id, stock_id] = 1.0
        for (first_stock, second_stock), similarity in {
            ("a", "c"): 0.99,
            ("a", "d"): 0.90,
            ("b", "c"): 0.90,
        }.items():
            similarities.loc[first_stock, second_stock] = similarity
            similarities.loc[second_stock, first_stock] = similarity

        compatibility = build_cosine_compatibility_matrix(
            similarities,
            min_cosine_similarity=0.8,
        )
        minimum_groups = minimize_cosine_similarity_groups(
            similarities,
            min_cosine_similarity=0.8,
        )
        greedy_groups = greedy_group_by_cosine_similarity(
            similarities,
            min_cosine_similarity=0.8,
        )

        self.assertTrue(compatibility.loc["a", "c"])
        self.assertFalse(compatibility.loc["a", "b"])
        minimum_grouped_stocks = {
            frozenset(group["stock_id"])
            for _, group in minimum_groups.groupby("group_id", sort=True)
        }
        self.assertEqual(
            minimum_grouped_stocks,
            {frozenset({"a", "d"}), frozenset({"b", "c"})},
        )
        self.assertEqual(
            minimum_groups.attrs["grouping_method"],
            COSINE_GROUPING_METHOD_MINIMIZE,
        )
        self.assertTrue(minimum_groups.attrs["optimal_group_count_proven"])

        greedy_grouped_stocks = {
            frozenset(group["stock_id"])
            for _, group in greedy_groups.groupby("group_id", sort=True)
        }
        self.assertEqual(
            greedy_grouped_stocks,
            {frozenset({"a", "c"}), frozenset({"b"}), frozenset({"d"})},
        )
        self.assertEqual(
            greedy_groups.attrs["grouping_method"],
            COSINE_GROUPING_METHOD_GREEDY,
        )
        self.assertFalse(greedy_groups.attrs["optimal_group_count_proven"])
        self.assertEqual(greedy_groups.attrs["group_count_upper_bound"], 3)

    def test_dispatcher_can_select_cosine_greedy(self) -> None:
        similarities = pd.DataFrame(
            [[1.0, 0.95], [0.95, 1.0]],
            index=["a", "b"],
            columns=["a", "b"],
        )

        groups = group_by_cosine_similarity(
            similarities,
            min_cosine_similarity=0.9,
            grouping_method=COSINE_GROUPING_METHOD_GREEDY,
        )

        self.assertEqual(groups["group_id"].tolist(), [1, 1])
        self.assertEqual(
            groups.attrs["grouping_method"],
            COSINE_GROUPING_METHOD_GREEDY,
        )

    def test_short_alias_points_to_the_v2_grouping_function(self) -> None:
        self.assertIs(group_relative_clock_vectors, group_relative_clock_vectors_v2)


class V2CommandLineTest(unittest.TestCase):
    def test_cli_only_writes_the_grouping_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market.csv"
            groups_csv = directory / "groups.csv"
            make_market_data().to_csv(input_csv, index=False)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        str(input_csv),
                        str(groups_csv),
                        "--min-cosine-similarity",
                        "0.99",
                        "--min-common-snapshots",
                        "3",
                        "--min-common-rate",
                        "1.0",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                pd.read_csv(groups_csv).to_dict("records"),
                [
                    {"stock_id": "a", "group_id": 1},
                    {"stock_id": "b", "group_id": 1},
                    {"stock_id": "c", "group_id": 2},
                    {"stock_id": "z", "group_id": 3},
                ],
            )
            self.assertEqual(set(directory.iterdir()), {input_csv, groups_csv})
            self.assertIn("最终分组数：3", output.getvalue())
            self.assertIn(
                "分组方法：minimum clique partition（余弦兼容矩阵）",
                output.getvalue(),
            )
            self.assertIn("已证明当前分组数为全局最少", output.getvalue())

    def test_cli_can_select_cosine_greedy_grouping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market.csv"
            groups_csv = directory / "groups.csv"
            make_market_data().to_csv(input_csv, index=False)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(
                    [
                        str(input_csv),
                        str(groups_csv),
                        "--min-cosine-similarity",
                        "0.99",
                        "--min-common-snapshots",
                        "3",
                        "--min-common-rate",
                        "1.0",
                        "--grouping-method",
                        "cosine_greedy",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(set(directory.iterdir()), {input_csv, groups_csv})
            self.assertIn("最终分组数：3", output.getvalue())
            self.assertIn("分组方法：按余弦相似度降序贪心合并", output.getvalue())
            self.assertIn("贪心方法不保证当前分组数为全局最少", output.getvalue())


if __name__ == "__main__":
    unittest.main()
