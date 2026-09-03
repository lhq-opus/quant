from __future__ import annotations

import contextlib
import io
import unittest

import pandas as pd

from mds.study.pandas_01_io_selection import (
    example_data_quality_report,
    example_safe_assignment,
    example_select_rows,
    example_series_and_dataframe,
    example_write_csv,
    load_example_market_data,
)
from mds.study.pandas_02_snapshot_groupby import (
    add_snapshot_deltas_and_groups,
    compare_global_and_grouped_diff,
    describe_delta_distribution,
    summarize_local_groups,
)
from mds.study.pandas_03_aggregate_merge import (
    aggregate_stock_activity,
    attach_example_group_mapping,
    build_presence_matrix,
    calculate_candidate_pair_scores,
)
from mds.study.pandas_04_time_large_data import (
    add_trading_session,
    build_session_activity_table,
    compare_memory_usage,
    count_updates_with_chunks,
    snapshot_sizes_with_boundary_carry,
)
from mds.study.run_all import main as run_all_lessons


class IoAndSelectionLessonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_example_market_data()

    def test_csv_types_columns_and_leading_zero_are_preserved(self) -> None:
        self.assertEqual(self.data.columns.tolist(), ["clock", "stock_id", "time"])
        self.assertEqual(self.data.shape, (12, 3))
        self.assertEqual(self.data.loc[2, "stock_id"], "000001")
        self.assertTrue(pd.api.types.is_integer_dtype(self.data["clock"].dtype))

    def test_series_dataframe_selection_and_safe_assignment(self) -> None:
        stock_series, stock_frame = example_series_and_dataframe(self.data)
        self.assertIsInstance(stock_series, pd.Series)
        self.assertIsInstance(stock_frame, pd.DataFrame)

        selected = example_select_rows(self.data)
        self.assertEqual(selected["stock_id"].tolist(), ["000001", "000002"])

        annotated = example_safe_assignment(self.data)
        self.assertEqual(annotated.loc[0, "snapshot_label"], "opening_example")
        self.assertEqual(annotated.loc[4, "snapshot_label"], "other")
        self.assertNotIn("clock_ms", self.data.columns)

    def test_quality_report_finds_constructed_missing_and_duplicate_rows(self) -> None:
        missing_counts, duplicate_rows = example_data_quality_report(self.data)
        self.assertEqual(
            missing_counts.to_dict(), {"clock": 1, "stock_id": 0, "time": 0}
        )
        self.assertEqual(len(duplicate_rows), 2)
        self.assertEqual(set(duplicate_rows["stock_id"]), {"600000"})

        output_csv = example_write_csv(self.data.head(1))
        self.assertEqual(
            output_csv,
            "clock,stock_id,time\n1000035,600000,09:30:00\n",
        )


class SnapshotGroupbyLessonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_example_market_data()
        self.grouped = add_snapshot_deltas_and_groups(self.data, threshold=1_000)

    def test_each_snapshot_is_sorted_and_group_ids_restart_from_zero(self) -> None:
        first = self.grouped.loc[self.grouped["time"].eq("09:30:00")]
        self.assertEqual(
            first["stock_id"].tolist(),
            ["000001", "000002", "600000", "600001"],
        )
        self.assertTrue(pd.isna(first["delta_clock"].iloc[0]))
        self.assertEqual(first["delta_clock"].iloc[1:].tolist(), [20, 15, 9_965])
        self.assertEqual(first["local_group_id"].tolist(), [0, 0, 0, 1])

        first_group_ids = self.grouped.groupby("time", sort=False)[
            "local_group_id"
        ].first()
        self.assertTrue(first_group_ids.eq(0).all())

    def test_group_summary_and_diff_boundary(self) -> None:
        summary = summarize_local_groups(self.grouped)
        self.assertEqual(len(summary), 7)
        first_group = summary.loc[
            summary["time"].eq("09:30:00") & summary["local_group_id"].eq(0)
        ].iloc[0]
        self.assertEqual(first_group["stocks"], ("000001", "000002", "600000"))
        self.assertEqual(first_group["clock_span"], 35)

        comparison = compare_global_and_grouped_diff(self.data)
        self.assertEqual(comparison["wrong_global_delta"].isna().sum(), 1)
        self.assertEqual(comparison["correct_snapshot_delta"].isna().sum(), 4)

        distribution = describe_delta_distribution(self.grouped)
        self.assertEqual(distribution["count"], 8)
        self.assertEqual(distribution["median"], 27.5)


class AggregateAndMergeLessonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_example_market_data()
        self.grouped = add_snapshot_deltas_and_groups(self.data)

    def _score(self, stock_a: str, stock_b: str) -> pd.Series:
        scores = calculate_candidate_pair_scores(self.grouped)
        return scores.loc[
            scores["stock_id_a"].eq(stock_a) & scores["stock_id_b"].eq(stock_b)
        ].iloc[0]

    def test_activity_and_candidate_pair_scores(self) -> None:
        activity = aggregate_stock_activity(self.data).set_index("stock_id")
        self.assertEqual(activity.loc["000001", "record_count"], 4)
        self.assertEqual(activity.loc["000003", "active_snapshot_count"], 1)

        close_pair = self._score("000001", "000002")
        self.assertEqual(close_pair["common_snapshot_count"], 2)
        self.assertEqual(close_pair["same_local_group_count"], 2)
        self.assertEqual(close_pair["same_local_group_fraction"], 1.0)

        separated_pair = self._score("000001", "600001")
        self.assertEqual(separated_pair["common_snapshot_count"], 3)
        self.assertEqual(separated_pair["same_local_group_count"], 0)

    def test_merge_indicator_and_presence_matrix(self) -> None:
        enriched = attach_example_group_mapping(self.data)
        unmapped = enriched.loc[enriched["stock_id"].eq("000003")].iloc[0]
        self.assertTrue(pd.isna(unmapped["group_id"]))
        self.assertEqual(unmapped["mapping_status"], "left_only")

        presence = build_presence_matrix(self.data)
        self.assertEqual(presence.shape, (5, 4))
        self.assertEqual(presence.loc["000001", "09:30:00"], 1)
        self.assertEqual(presence.loc["000003", "09:30:00"], 0)


class TimeAndLargeDataLessonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_example_market_data()

    def test_time_slice_and_pivot(self) -> None:
        timed = add_trading_session(self.data)
        self.assertEqual(
            timed["session"].value_counts().to_dict(), {"morning": 7, "afternoon": 5}
        )

        activity = build_session_activity_table(timed).set_index("stock_id")
        self.assertEqual(activity.loc["000001", "morning"], 2)
        self.assertEqual(activity.loc["000001", "afternoon"], 2)
        self.assertEqual(activity.loc["000003", "morning"], 0)

    def test_chunk_accumulator_and_snapshot_boundary_carry(self) -> None:
        counts = count_updates_with_chunks(chunksize=4)
        self.assertEqual(
            counts.to_dict(),
            {"000001": 4, "000002": 2, "000003": 1, "600000": 2, "600001": 3},
        )

        snapshot_sizes = snapshot_sizes_with_boundary_carry(chunksize=3)
        self.assertEqual(
            snapshot_sizes.to_dict(),
            {"09:30:00": 4, "09:30:03": 3, "13:00:00": 3, "13:00:03": 2},
        )

    def test_category_example_measures_memory(self) -> None:
        usage = compare_memory_usage(self.data, repeats=1_000)
        self.assertGreater(usage["string_bytes"], usage["category_bytes"])


class RunAllLessonsTest(unittest.TestCase):
    def test_all_examples_are_executable(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = run_all_lessons()

        self.assertEqual(exit_code, 0)
        self.assertIn("第一课：CSV、类型与筛选", output.getvalue())
        self.assertIn("local_group_id 只是记录级候选时间簇", output.getvalue())
        self.assertIn("跨 chunk 保留完整 snapshot", output.getvalue())


if __name__ == "__main__":
    unittest.main()
