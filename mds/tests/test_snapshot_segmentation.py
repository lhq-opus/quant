from __future__ import annotations

import csv
import tempfile
import unittest
from itertools import pairwise
from pathlib import Path

import numpy as np

from mds.snapshot_segmentation import (
    learn_stock_positions,
    process_csv,
    segment_snapshots,
)


class SnapshotSegmentationTest(unittest.TestCase):
    def assert_valid_partition(self, sequence: np.ndarray, cuts: np.ndarray) -> None:
        """独立检查连续覆盖和段内不重复，不借用求解器内部判断。"""

        self.assertEqual(int(cuts[0]), 0)
        self.assertEqual(int(cuts[-1]), len(sequence))
        self.assertTrue(np.all(np.diff(cuts) > 0))
        for start, stop in pairwise(cuts):
            stocks = sequence[int(start) : int(stop)].tolist()
            self.assertEqual(len(stocks), len(set(stocks)))

    def test_learning_uses_each_stocks_median_position(self) -> None:
        # 股票 ID 只是索引，ID 的数值大小不代表它在一轮中的前后位置。
        complete_snapshots = np.array(
            [[3, 0, 2, 1], [0, 3, 2, 1], [3, 0, 1, 2]], dtype=np.int32
        )

        positions = learn_stock_positions(complete_snapshots)

        np.testing.assert_allclose(positions, [1 / 3, 1, 2 / 3, 0])

    def test_missing_stocks_boundary_precedes_first_repeated_stock(self) -> None:
        # 真值是两轮 [0, 3, 7, 9] | [1, 4, 7, 8]。
        # 若等到第一次重复的 7 才切，会把第二轮开头的 1、4 错放到前一轮。
        sequence = np.array([0, 3, 7, 9, 1, 4, 7, 8], dtype=np.int32)
        positions = np.linspace(0, 1, 10)

        cuts = segment_snapshots(sequence, positions)

        np.testing.assert_array_equal(cuts, [0, 4, 8])
        self.assert_valid_partition(sequence, cuts)

    def test_small_local_inversion_does_not_create_a_snapshot(self) -> None:
        # 两轮内都只交换了相邻的两只股票；较小的局部换序不是整轮重启。
        sequence = np.array([0, 1, 3, 2, 4, 5, 0, 2, 1, 3, 4, 5])
        positions = np.linspace(0, 1, 6)

        cuts = segment_snapshots(sequence, positions)

        np.testing.assert_array_equal(cuts, [0, 6, 12])
        self.assert_valid_partition(sequence, cuts)

    def test_repeat_locates_a_weak_reset_before_the_repeated_record(self) -> None:
        # 两轮都缺少首尾股票，6 → 3 的回退不到默认阈值。
        # 后续再次出现 6 时，必须回到两次 6 之间补切，而不能只在重复处切。
        sequence = np.array([2, 4, 6, 3, 5, 6, 8])
        positions = np.linspace(0, 1, 10)

        cuts = segment_snapshots(sequence, positions)

        np.testing.assert_array_equal(cuts, [0, 3, 7])
        self.assert_valid_partition(sequence, cuts)

    def test_repair_preserves_repeat_constraints_in_the_remaining_suffix(self) -> None:
        # 第一次补切后，后缀中的 2 仍然重复，需要继续补切。
        # 4 → 3、3 → 2 的回退相同，约定选择较早的切点。
        sequence = np.array([0, 1, 3, 2, 4, 3, 2])
        positions = np.linspace(0, 1, 5)

        cuts = segment_snapshots(sequence, positions)

        np.testing.assert_array_equal(cuts, [0, 3, 5, 7])
        self.assert_valid_partition(sequence, cuts)

    def test_adjacent_repeats_require_single_record_snapshots(self) -> None:
        sequence = np.array([1, 1, 1])
        positions = np.linspace(0, 1, 3)

        cuts = segment_snapshots(sequence, positions)

        np.testing.assert_array_equal(cuts, [0, 1, 2, 3])
        self.assert_valid_partition(sequence, cuts)

    def test_complete_prefix_is_honored_despite_internal_phase_rollback(self) -> None:
        # 已知完整前缀的边界来自用户给出的长度约束，其内部即使出现
        # 大位置回退也不能被启发式再切开；前缀后的缺失轮仍需正常识别。
        positions = np.array([0.0, 0.9, 0.2, 0.7])
        sequence = np.array([0, 1, 2, 3, 0, 1, 2, 3, 0, 3, 1, 0, 2, 1])

        cuts = segment_snapshots(sequence, positions, complete_prefix_count=2)

        np.testing.assert_array_equal(cuts, [0, 4, 8, 11, 14])
        self.assert_valid_partition(sequence, cuts)

    def test_random_missing_cycles_with_observed_ends_recover_truth(self) -> None:
        # 保留首尾位置是本成功样例的生成条件，不是对真实 CSV 的假设。
        # 中间股票随机缺失，并允许一次相邻换序，真边界单独累计后用于验收。
        random = np.random.default_rng(20260914)
        stock_count = 48
        positions = np.linspace(0, 1, stock_count)
        snapshots = []
        true_cuts = [0]
        for _ in range(100):
            stocks = [0]
            for stock in range(1, stock_count - 1):
                if random.random() < 0.4:
                    stocks.append(stock)
            stocks.append(stock_count - 1)
            if len(stocks) >= 5:
                swap = int(random.integers(1, len(stocks) - 2))
                # 只交换相位差很小的相邻观测，避免人为引入另一种大回退。
                if stocks[swap + 1] - stocks[swap] <= 3:
                    stocks[swap], stocks[swap + 1] = stocks[swap + 1], stocks[swap]
            snapshots.extend(stocks)
            true_cuts.append(len(snapshots))
        sequence = np.array(snapshots)

        cuts = segment_snapshots(sequence, positions)

        np.testing.assert_array_equal(cuts, true_cuts)
        self.assert_valid_partition(sequence, cuts)

    def test_random_sparse_cycles_always_preserve_no_duplicate_constraint(self) -> None:
        # 严重缺失时不要求推断出唯一真边界，但每个输出段仍必须满足硬约束。
        random = np.random.default_rng(19)
        stock_count = 32
        positions = np.linspace(0, 1, stock_count)
        for keep_probability in (0.04, 0.15, 0.6):
            snapshots = []
            for _ in range(120):
                stocks = []
                for stock in range(stock_count):
                    if random.random() < keep_probability:
                        stocks.append(stock)
                if not stocks:
                    stocks.append(int(random.integers(stock_count)))
                snapshots.extend(stocks)
            sequence = np.array(snapshots)
            for threshold in (0.25, 0.5, 0.75):
                with self.subTest(
                    keep_probability=keep_probability, threshold=threshold
                ):
                    cuts = segment_snapshots(sequence, positions, threshold)
                    self.assert_valid_partition(sequence, cuts)

    def test_disjoint_sparse_cycles_are_not_uniquely_identifiable(self) -> None:
        # 同一观测既可来自 [2, 3, 4, 5]，也可来自 [2, 3] | [4, 5]。
        # 两种真值都满足不重复与位置递增，所以仅有一列无法证明哪种正确。
        sequence = np.array([2, 3, 4, 5])
        positions = np.linspace(0, 1, 6)
        possible_single_snapshot = np.array([0, 4])
        possible_two_snapshots = np.array([0, 2, 4])

        self.assert_valid_partition(sequence, possible_single_snapshot)
        self.assert_valid_partition(sequence, possible_two_snapshots)
        cuts = segment_snapshots(sequence, positions)

        # 当前规则在无重启、无重复证据时保留为一段，不能称为真值恢复。
        np.testing.assert_array_equal(cuts, possible_single_snapshot)
        self.assertFalse(np.array_equal(cuts, possible_two_snapshots))

    def test_csv_preserves_original_stock_strings_and_row_order(self) -> None:
        first_round = ["600001", "000003", "000001", "600002", "000002", "600003"]
        stocks = first_round * 2
        stocks.extend(["600001", "000001", "000002", "600003"])
        stocks.extend(["000003", "600002", "600003"])
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "data.csv"
            output_path = Path(temporary_directory) / "snapshots.csv"
            boundary_path = Path(temporary_directory) / "boundaries.csv"
            with input_path.open("w", encoding="utf-8", newline="") as input_file:
                writer = csv.writer(input_file)
                writer.writerow(["stock_id"])
                writer.writerows([[stock] for stock in stocks])
            original_input = input_path.read_bytes()

            stats = process_csv(
                input_path,
                output_path,
                stock_count=6,
                complete_prefix_count=2,
                boundary_csv=boundary_path,
            )

            with output_path.open(encoding="utf-8", newline="") as output_file:
                reader = csv.DictReader(output_file)
                self.assertEqual(reader.fieldnames, ["stock_id", "snapshot_id"])
                rows = list(reader)
            with boundary_path.open(encoding="utf-8", newline="") as boundary_file:
                boundaries = list(csv.DictReader(boundary_file))
            self.assertEqual(input_path.read_bytes(), original_input)

        self.assertEqual([row["stock_id"] for row in rows], stocks)
        self.assertEqual(
            [int(row["snapshot_id"]) for row in rows],
            [1] * 6 + [2] * 6 + [3] * 4 + [4] * 3,
        )
        self.assertEqual(stats["row_count"], len(stocks))
        self.assertEqual(stats["snapshot_count"], 4)
        self.assertEqual(
            [
                (int(row["start_data_row"]), int(row["end_data_row"]))
                for row in boundaries
            ],
            [(1, 6), (7, 12), (13, 16), (17, 19)],
        )
        self.assertEqual([int(row["record_count"]) for row in boundaries], [6, 6, 4, 3])

    def test_csv_rejects_path_collisions_before_overwriting_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "data.csv"
            output_path = Path(temporary_directory) / "snapshots.csv"
            input_path.write_text("stock_id\n1\n2\n", encoding="utf-8")
            output_path.write_text("already exists\n", encoding="utf-8")
            original_input = input_path.read_bytes()
            original_output = output_path.read_bytes()
            for output, boundary in (
                (input_path, None),
                (output_path, input_path),
                (output_path, output_path),
            ):
                with self.subTest(output=output, boundary=boundary):
                    with self.assertRaises(ValueError):
                        process_csv(
                            input_path,
                            output,
                            stock_count=2,
                            complete_prefix_count=1,
                            boundary_csv=boundary,
                        )
                    self.assertEqual(input_path.read_bytes(), original_input)
                    self.assertEqual(output_path.read_bytes(), original_output)


if __name__ == "__main__":
    unittest.main()
