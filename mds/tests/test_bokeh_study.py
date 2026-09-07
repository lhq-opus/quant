from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from mds.study.bokeh_06_mds_visualization import (
    EXAMPLE_VISUAL_GROUPS,
    build_mds_dashboard,
    load_example_mds_data,
    load_relationship_matrix_csv,
    make_example_relationship_matrix,
    prepare_relative_clock_heatmap_data,
    prepare_snapshot_arrivals,
    relationship_matrix_to_long_form,
    save_mds_dashboard,
)


class BokehStudyLessonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_example_mds_data()

    def test_snapshot_arrivals_keep_order_and_split_large_gaps(self) -> None:
        arrivals = prepare_snapshot_arrivals(
            self.data,
            "09:30:00",
            gap_threshold_us=1_000,
        )

        self.assertEqual(
            arrivals["relative_clock_us"].tolist(),
            [0, 25, 10_000, 10_030, 22_000],
        )
        self.assertEqual(
            arrivals["previous_gap_us"].tolist(),
            [0, 25, 9_975, 30, 11_970],
        )
        self.assertEqual(arrivals["candidate_group_id"].tolist(), [0, 0, 1, 1, 2])

    def test_relative_clock_heatmap_keeps_missing_dimensions(self) -> None:
        cells, snapshot_order, stock_order = prepare_relative_clock_heatmap_data(
            self.data,
            group_mapping=EXAMPLE_VISUAL_GROUPS,
        )

        # 5 只股票 × 6 个 snapshot，完整网格应有 30 个格子；其中 5 格缺失。
        self.assertEqual(len(cells), 30)
        self.assertEqual(cells["relative_clock_us"].isna().sum(), 5)
        self.assertEqual(snapshot_order[0], "09:30:00")
        self.assertEqual(stock_order[:2], ["000001", "000002"])

        collision = cells.loc[
            cells["stock_id"].eq("600000") & cells["time"].eq("09:30:09")
        ].iloc[0]
        self.assertEqual(collision["relative_clock_us"], 55)

        missing = cells.loc[
            cells["stock_id"].eq("000001") & cells["time"].eq("09:30:15")
        ].iloc[0]
        self.assertTrue(pd.isna(missing["relative_clock_us"]))
        self.assertEqual(missing["relative_clock_text"], "该 snapshot 未出现")

    def test_relationship_matrix_can_round_trip_through_v1_v2_csv_shape(self) -> None:
        matrix = make_example_relationship_matrix()
        long_form = relationship_matrix_to_long_form(matrix)
        self.assertEqual(len(long_form), 25)
        self.assertEqual(
            long_form.loc[
                long_form["stock_a"].eq("000001") & long_form["stock_b"].eq("000002"),
                "value",
            ].iloc[0],
            0.97,
        )
        self.assertIn("证据不足", long_form["value_text"].tolist())

        with tempfile.TemporaryDirectory() as temporary_directory:
            matrix_csv = Path(temporary_directory) / "groups_match_rates.csv"
            matrix.to_csv(matrix_csv, index=True, index_label="stock_id")
            loaded = load_relationship_matrix_csv(matrix_csv)

        pd.testing.assert_frame_equal(loaded, matrix)
        self.assertIn("000001", loaded.index)

    def test_dashboard_is_saved_as_standalone_html(self) -> None:
        # 先单独构造一次布局，确保四张图可以在当前 Bokeh 版本下完成组装。
        self.assertIsNotNone(build_mds_dashboard())

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_html = Path(temporary_directory) / "mds_bokeh.html"
            result = save_mds_dashboard(output_html)
            html = output_html.read_text(encoding="utf-8")

        self.assertEqual(result, output_html)
        self.assertIn("<html", html.lower())
        self.assertIn("Bokeh", html)
        self.assertIn("MDS Bokeh 可交互可视化", html)
        # mode="inline" 应把运行时资源放进同一个 HTML，而不是依赖外部 CDN。
        self.assertNotIn("cdn.bokeh.org", html)


if __name__ == "__main__":
    unittest.main()
