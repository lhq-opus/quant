from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from mds.baseline_grouping import (
    detect_threshold,
    group_all_snapshots,
    group_by_permanent_separation,
    group_one_snapshot,
    groups_to_mapping,
    infer_fixed_groups,
    main,
    process_csv,
)


class SnapshotGroupingTest(unittest.TestCase):
    def test_one_snapshot_is_sorted_and_split_by_clock_gap(self) -> None:
        snapshot = pd.DataFrame(
            {
                # 输入顺序是 c、b、a，局部分组前必须先按 clock 排成 a、b、c。
                "clock": [2_000, 1_010, 1_000],
                "stock_id": ["c", "b", "a"],
                "time": ["t1", "t1", "t1"],
            }
        )

        groups = group_one_snapshot(snapshot, threshold=100)

        self.assertEqual(groups, [["a", "b"], ["c"]])

    def test_every_time_has_an_independent_snapshot_result(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [1_000, 1_010, 2_000, 3_000, 3_020],
                "stock_id": ["a", "b", "c", "b", "c"],
                "time": ["t1", "t1", "t1", "t2", "t2"],
            }
        )

        snapshots = group_all_snapshots(data, threshold=100)

        self.assertEqual(
            snapshots,
            {
                "t1": [["a", "b"], ["c"]],
                "t2": [["b", "c"]],
            },
        )

    def test_existing_gap_detector_can_still_supply_the_threshold(self) -> None:
        records = []
        for index, gap in enumerate([20, 30, 35, 10_000, 11_000]):
            records.extend(
                [
                    {
                        "clock": index * 100_000,
                        "stock_id": f"a{index}",
                        "time": f"t{index}",
                    },
                    {
                        "clock": index * 100_000 + gap,
                        "stock_id": f"b{index}",
                        "time": f"t{index}",
                    },
                ]
            )

        # 没有手工传 threshold 时，CLI 仍可沿用已有的简单异常 gap 检测。
        self.assertEqual(detect_threshold(pd.DataFrame(records)), 10_000)


class FinalGroupingTest(unittest.TestCase):
    def test_stocks_separated_once_must_be_in_different_final_groups(self) -> None:
        snapshots = {
            "t1": [["a", "b"], ["c", "d"]],
            # 虽然 b、c 后来靠得很近，t1 的永久分离规则仍然优先。
            "t2": [["b", "c"]],
        }

        groups = group_by_permanent_separation(
            snapshots,
            ["a", "b", "c", "d"],
        )

        self.assertEqual(groups, [["a", "b"], ["c", "d"]])

    def test_missing_stock_does_not_create_a_separation_pair(self) -> None:
        snapshots = {
            "t1": [["a", "b"]],
            "t2": [["b", "c"]],
        }

        groups = group_by_permanent_separation(snapshots, ["a", "b", "c"])

        self.assertEqual(groups, [["a", "b", "c"]])

    def test_both_grouping_stages_are_replaceable(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [1_000, 2_000],
                "stock_id": ["a", "b"],
                "time": ["t1", "t1"],
            }
        )

        # 自定义 snapshot 方法故意把每只股票都单独分组。
        def custom_snapshot_method(snapshot, threshold):
            return [[str(stock_id)] for stock_id in snapshot["stock_id"]]

        # 自定义最终方法忽略局部分组，故意把所有股票放回同一组。
        def custom_final_method(snapshot_groups, stock_ids):
            return [sorted(stock_ids)]

        snapshots, groups = infer_fixed_groups(
            data,
            threshold=100,
            snapshot_grouping_method=custom_snapshot_method,
            final_grouping_method=custom_final_method,
        )

        self.assertEqual(snapshots, {"t1": [["a"], ["b"]]})
        self.assertEqual(groups, [["a", "b"]])

    def test_mapping_rows_are_kept_together_by_group(self) -> None:
        mapping = groups_to_mapping([["a", "b"], ["c"]])

        self.assertEqual(
            mapping.to_dict("records"),
            [
                {"stock_id": "a", "group_id": 1},
                {"stock_id": "b", "group_id": 1},
                {"stock_id": "c", "group_id": 2},
            ],
        )


class ProcessCsvTest(unittest.TestCase):
    def test_csv_and_terminal_show_final_groups_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market_data.csv"
            output_csv = directory / "groups.csv"

            # mock 文件只存在于系统临时目录，测试结束后自动删除。
            input_csv.write_text(
                "clock,stock_id,exchange,time,last_price\n"
                "1000,000001,SZ,t1,10.50\n"
                "1010,600001,SH,t1,12.30\n"
                "2000,000002,SZ,t1,8.20\n",
                encoding="utf-8",
            )

            standard_output = io.StringIO()
            with contextlib.redirect_stdout(standard_output):
                exit_code = main(
                    [str(input_csv), str(output_csv), "--threshold", "100"]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                output_csv.read_text(encoding="utf-8"),
                "stock_id,group_id\n"
                "000001,1\n"
                "600001,1\n"
                "000002,2\n",
            )
            self.assertIn("最终分组数：2", standard_output.getvalue())
            self.assertIn("第 1 组（2 只）：000001, 600001", standard_output.getvalue())
            self.assertIn("第 2 组（1 只）：000002", standard_output.getvalue())

    def test_process_csv_returns_both_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market_data.csv"
            output_csv = directory / "groups.csv"
            input_csv.write_text(
                "clock,stock_id,time\n"
                "1000,a,t1\n"
                "1010,b,t1\n",
                encoding="utf-8",
            )

            snapshots, groups, threshold = process_csv(
                input_csv,
                output_csv,
                threshold=100,
            )

            self.assertEqual(snapshots, {"t1": [["a", "b"]]})
            self.assertEqual(groups, [["a", "b"]])
            self.assertEqual(threshold, 100)


if __name__ == "__main__":
    unittest.main()
