from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from mds.relative_clock_grouping import (
    build_relative_clock_vectors,
    group_relative_clock_vectors,
    main,
    plot_relative_clock_vectors,
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


class RelativeClockVisualizationTest(unittest.TestCase):
    def test_visualization_and_cli_write_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market.csv"
            vectors_csv = directory / "vectors.csv"
            groups_csv = directory / "groups.csv"
            plot_png = directory / "vectors.png"
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
            self.assertIn("snapshot 数：3", output.getvalue())
            self.assertIn("最终分组数：3", output.getvalue())

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
