from __future__ import annotations

import contextlib
import inspect
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import mds.relative_clock_grouping_v2 as v2_module
from mds.relative_clock_grouping import group_relative_clock_vectors
from mds.relative_clock_grouping_v2 import (
    build_single_linkage,
    calculate_normalized_vector_distances,
    group_relative_clock_vectors_v2,
    main,
    plot_normalized_distance_clusters,
)
from mds.relative_clock_grouping_v2 import (
    group_relative_clock_vectors as compatible_v2_grouping,
)


def make_vectors() -> pd.DataFrame:
    """构造两个清晰组和一只证据不足的股票。"""

    return pd.DataFrame(
        {
            "t1": [0, 20, 5_000, 5_020, pd.NA],
            "t2": [0, 30, 6_000, 6_030, pd.NA],
            "t3": [0, 40, 7_000, 7_040, 5],
        },
        index=["a", "b", "c", "d", "e"],
        dtype="Int64",
    )


def make_market_data() -> pd.DataFrame:
    """把 make_vectors 的结构写成 snapshot 内 clock 已排序的长表。"""

    return pd.DataFrame(
        {
            "clock": [
                1_000,
                1_020,
                6_000,
                6_020,
                2_000,
                2_030,
                8_000,
                8_030,
                3_000,
                3_005,
                3_040,
                10_000,
                10_040,
            ],
            "stock_id": [
                "a",
                "b",
                "c",
                "d",
                "a",
                "b",
                "c",
                "d",
                "a",
                "e",
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
                "t3",
                "t3",
                "t3",
                "t3",
                "t3",
            ],
        }
    ).astype({"clock": "int64", "stock_id": "string", "time": "string"})


class NormalizedVectorDistanceTest(unittest.TestCase):
    def test_distance_ignores_missing_dimensions_and_divides_by_sqrt_k(
        self,
    ) -> None:
        vectors = pd.DataFrame(
            {
                # a-b 只在 t1、t2 共同出现；t3 中 b 的 10000 不参与两者距离。
                "t1": [0, 3, pd.NA],
                "t2": [0, 4, pd.NA],
                "t3": [pd.NA, 10_000, 0],
            },
            index=["a", "b", "c"],
            dtype="Int64",
        )

        distances, common_counts = calculate_normalized_vector_distances(
            vectors,
            min_common_snapshots=2,
            min_common_rate=0.5,
        )

        # sqrt(3² + 4²) / sqrt(2) = 5 / sqrt(2)。
        self.assertAlmostEqual(distances.loc["a", "b"], 5 / np.sqrt(2))
        self.assertEqual(common_counts.loc["a", "b"], 2)

        # b-c 只有一个共同维度，不满足最少 2 个共同维度，因此是“证据不足”。
        self.assertTrue(np.isnan(distances.loc["b", "c"]))
        self.assertEqual(common_counts.loc["b", "c"], 1)

    def test_common_rate_filters_pairs_with_too_little_overlap(self) -> None:
        vectors = pd.DataFrame(
            {
                # 两只股票各出现 4 次，但只有 t1、t2 重合，common_rate = 2 / 4。
                "t1": [0, 0],
                "t2": [10, 10],
                "t3": [20, pd.NA],
                "t4": [30, pd.NA],
                "t5": [pd.NA, 40],
                "t6": [pd.NA, 50],
            },
            index=["a", "b"],
            dtype="Int64",
        )

        accepted, _ = calculate_normalized_vector_distances(
            vectors,
            min_common_snapshots=2,
            min_common_rate=0.5,
        )
        rejected, _ = calculate_normalized_vector_distances(
            vectors,
            min_common_snapshots=2,
            min_common_rate=0.75,
        )

        self.assertEqual(accepted.loc["a", "b"], 0)
        self.assertTrue(np.isnan(rejected.loc["a", "b"]))


class DistanceGroupingTest(unittest.TestCase):
    def test_v2_has_the_same_interface_and_output_schema_as_v1(self) -> None:
        self.assertIs(compatible_v2_grouping, group_relative_clock_vectors_v2)
        self.assertEqual(
            list(inspect.signature(group_relative_clock_vectors).parameters),
            list(inspect.signature(group_relative_clock_vectors_v2).parameters),
        )

        groups = group_relative_clock_vectors_v2(
            make_vectors(),
            max_clock_gap_us=100,
            min_close_snapshots=2,
            min_close_rate=0.5,
        )

        self.assertEqual(
            groups.to_dict("records"),
            [
                {"stock_id": "a", "group_id": 1},
                {"stock_id": "b", "group_id": 1},
                {"stock_id": "c", "group_id": 2},
                {"stock_id": "d", "group_id": 2},
                {"stock_id": "e", "group_id": 3},
            ],
        )

    def test_pre_grouping_plot_is_generated_without_group_ids(self) -> None:
        distances, _ = calculate_normalized_vector_distances(
            make_vectors(),
            min_common_snapshots=2,
            min_common_rate=0.5,
        )
        linkage_matrix = build_single_linkage(
            distances,
            max_clock_gap_us=100,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_png = Path(temporary_directory) / "distance-clusters.png"
            plot_normalized_distance_clusters(
                distances,
                linkage_matrix,
                output_png,
                max_clock_gap_us=100,
            )

            self.assertTrue(output_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(output_png.stat().st_size, 1_000)


class V2CommandLineTest(unittest.TestCase):
    def test_process_plots_before_cutting_the_threshold_groups(self) -> None:
        events: list[str] = []

        def record_plot(*args: object, **kwargs: object) -> None:
            events.append("plot")

        def record_grouping(
            stock_ids: list[str], *args: object, **kwargs: object
        ) -> pd.DataFrame:
            events.append("group")
            return pd.DataFrame(
                {"stock_id": stock_ids, "group_id": range(1, len(stock_ids) + 1)}
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market.csv"
            make_market_data().to_csv(input_csv, index=False)

            with (
                mock.patch.object(
                    v2_module,
                    "plot_normalized_distance_clusters",
                    side_effect=record_plot,
                ),
                mock.patch.object(
                    v2_module,
                    "cut_single_linkage_groups",
                    side_effect=record_grouping,
                ),
            ):
                v2_module.process_csv(
                    input_csv,
                    directory / "vectors.csv",
                    directory / "groups.csv",
                    directory / "vectors.png",
                    max_clock_gap_us=100,
                    min_close_snapshots=2,
                    min_close_rate=0.5,
                )

        self.assertEqual(events, ["plot", "group"])

    def test_cli_keeps_v1_input_and_output_files(self) -> None:
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
                pd.read_csv(vectors_csv).columns.tolist(),
                ["stock_id", "t1", "t2", "t3"],
            )
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
            self.assertTrue(plot_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertIn("最终分组数：3", output.getvalue())
            self.assertIn("切组前距离图 PNG", output.getvalue())


if __name__ == "__main__":
    unittest.main()
