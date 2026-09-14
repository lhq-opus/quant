from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mds.high_confidence_snapshots import filter_candidate_snapshots, process_csv


class HighConfidenceSnapshotsTest(unittest.TestCase):
    def test_known_complete_prefix_survives_uncertain_order_evidence(self) -> None:
        # 第一轮虽然倒序且比较切分在其内部有分歧，但用户已声明它完整。
        sequence = np.array(list(reversed(range(20))) + list(range(20)))
        positions = np.linspace(0, 1, 20)
        cuts = np.array([0, 20, 40])

        decisions = filter_candidate_snapshots(
            sequence,
            positions,
            cuts,
            [cuts, np.array([0, 10, 20, 40])],
            complete_prefix_count=1,
            short_size=25,
            edge_window=3,
        )

        self.assertTrue(decisions[0]["selected"])
        self.assertEqual(decisions[0]["reason"], "known_complete_prefix")
        self.assertFalse(decisions[1]["selected"])

    def test_edge_medians_exclude_bad_segments_and_keep_original_ids(self) -> None:
        normal = list(range(20))
        # 第一只/最后一只看起来正常，但首尾窗口的多数股票位置异常。
        # 每轮仍各包含所有股票一次，避免把重复或缺失混入本检查。
        late_start = [0, 6, 7, 1, 2, 3, 4, 5, 8] + list(range(9, 20))
        early_end = [0, 1, 2] + list(range(5, 19)) + [3, 4, 19]
        sequence = np.array(normal + late_start + normal + early_end + normal)
        positions = np.linspace(0, 1, 20)
        cuts = np.arange(0, 101, 20)

        decisions = filter_candidate_snapshots(
            sequence,
            positions,
            cuts,
            [cuts],
            complete_prefix_count=1,
            short_size=3,
            edge_window=3,
        )

        self.assertEqual(
            [row["snapshot_id"] for row in decisions if row["selected"]], [1, 3, 5]
        )
        self.assertIn("start_not_early", decisions[1]["reason"])
        self.assertIn("end_not_late", decisions[3]["reason"])
        self.assertEqual(decisions[2]["start_data_row"], 41)
        self.assertEqual(decisions[2]["end_data_row"], 60)

    def test_comparison_requires_both_stable_edges_and_no_internal_split(self) -> None:
        sequence = np.tile(np.arange(20), 3)
        positions = np.linspace(0, 1, 20)
        cuts = np.array([0, 20, 40, 60])
        for alternative, expected_reason, expected_selected in (
            ([0, 20, 39, 60], "unstable_end_boundary", [1]),
            ([0, 20, 30, 40, 60], "alternative_internal_boundary", [1, 3]),
        ):
            with self.subTest(alternative=alternative):
                decisions = filter_candidate_snapshots(
                    sequence,
                    positions,
                    cuts,
                    [cuts, np.array(alternative)],
                    complete_prefix_count=1,
                    short_size=3,
                    edge_window=3,
                )

                self.assertFalse(decisions[1]["selected"])
                self.assertIn(expected_reason, decisions[1]["reason"])
                self.assertEqual(
                    [row["snapshot_id"] for row in decisions if row["selected"]],
                    expected_selected,
                )
                if alternative == [0, 20, 39, 60]:
                    self.assertIn("unstable_start_boundary", decisions[2]["reason"])

    def test_short_segment_excludes_itself_and_both_neighbors(self) -> None:
        normal = list(range(10))
        sequence = np.array(normal * 2 + [0, 9] + normal * 3)
        positions = np.linspace(0, 1, 10)
        cuts = np.array([0, 10, 20, 22, 32, 42, 52])

        decisions = filter_candidate_snapshots(
            sequence,
            positions,
            cuts,
            [cuts],
            complete_prefix_count=1,
            short_size=2,
            edge_window=1,
        )

        self.assertEqual(
            [row["snapshot_id"] for row in decisions if row["selected"]], [1, 5, 6]
        )
        for index in (1, 2, 3):
            self.assertIn("short_segment_or_neighbor", decisions[index]["reason"])

    def test_few_extreme_stocks_do_not_make_a_narrow_middle_span_reliable(self) -> None:
        # 首尾各三只确实很早/很晚，但其余 94 只都挤在中段，不能仅靠
        # 极少数端点把整轮的位置跨度撑大。这里没有段内重复或边界分歧。
        positions = np.concatenate(
            (
                np.linspace(0, 0.02, 3),
                np.linspace(0.45, 0.55, 94),
                np.linspace(0.98, 1, 3),
            )
        )
        sequence = np.arange(100)
        cuts = np.array([0, 100])

        decisions = filter_candidate_snapshots(
            sequence,
            positions,
            cuts,
            [cuts],
            complete_prefix_count=0,
            short_size=3,
            edge_window=3,
        )

        self.assertFalse(decisions[0]["selected"])
        self.assertEqual(decisions[0]["reason"], "limited_position_span")

    def test_csv_keeps_original_stock_text_and_candidate_number_gaps(self) -> None:
        # 首两轮用于训练。中间一个单记录候选及其后邻轮被排除，后面的
        # 第 5、6 轮重新满足筛选条件；输出编号必须保留为 1、2、5、6。
        complete_round = [f"{stock:06d}" for stock in range(1, 201)]
        stocks = complete_round * 2 + [complete_round[0]] + complete_round * 3
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "data.csv"
            output_path = Path(temporary_directory) / "selected.csv"
            review_path = Path(temporary_directory) / "review.csv"
            input_path.write_text(
                "stock_id\n" + "\n".join(stocks) + "\n", encoding="utf-8"
            )
            original_input = input_path.read_bytes()

            stats = process_csv(
                input_path,
                output_path,
                review_path,
                stock_count=200,
                complete_prefix_count=2,
            )

            with output_path.open(encoding="utf-8", newline="") as output_file:
                reader = csv.DictReader(output_file)
                self.assertEqual(reader.fieldnames, ["stock_id", "snapshot_id"])
                rows = list(reader)
            with review_path.open(encoding="utf-8", newline="") as review_file:
                review = list(csv.DictReader(review_file))
            self.assertEqual(input_path.read_bytes(), original_input)

        self.assertEqual([row["stock_id"] for row in rows], complete_round * 4)
        self.assertEqual(
            [int(row["snapshot_id"]) for row in rows],
            [1] * 200 + [2] * 200 + [5] * 200 + [6] * 200,
        )
        self.assertEqual(
            [int(row["snapshot_id"]) for row in review if row["selected"] == "True"],
            [1, 2, 5, 6],
        )
        self.assertEqual(stats["input_rows"], 1001)
        self.assertEqual(stats["candidate_snapshots"], 6)
        self.assertEqual(stats["selected_rows"], 800)
        self.assertEqual(stats["selected_snapshots"], 4)
        self.assertEqual(stats["excluded_rows"], 201)


if __name__ == "__main__":
    unittest.main()
