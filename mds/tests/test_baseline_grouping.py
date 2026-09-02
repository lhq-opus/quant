from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from mds.baseline_grouping import infer_fixed_groups, main, process_csv


def _group_sets(mapping: pd.DataFrame) -> set[frozenset[str]]:
    """Convert a mapping DataFrame into group member sets for readable tests."""

    return {
        frozenset(group["stock_id"].astype(str).tolist())
        for _, group in mapping.groupby("group_id", sort=False)
    }


class InferFixedGroupsTest(unittest.TestCase):
    def test_permanent_separation_overrides_later_same_group_evidence(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [1_000, 1_010, 2_000, 2_010, 3_000, 3_010],
                "stock_id": ["a", "b", "c", "d", "b", "c"],
                "time": ["t1", "t1", "t1", "t1", "t2", "t2"],
            }
        )

        result = infer_fixed_groups(data, threshold=100)

        # t1 gives {a,b} and {c,d}. Although t2 puts b and c together, their
        # t1 separation is permanent and must win.
        self.assertEqual(
            _group_sets(result.mapping),
            {frozenset({"a", "b"}), frozenset({"c", "d"})},
        )
        self.assertEqual(result.blocked_merge_count, 1)

    def test_missing_stocks_allow_indirect_merge(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [1_000, 1_010, 2_000, 2_010],
                "stock_id": ["a", "b", "b", "c"],
                "time": ["t1", "t1", "t2", "t2"],
            }
        )

        result = infer_fixed_groups(data, threshold=100)

        # a is absent from t2 and c is absent from t1. Absence adds no negative
        # evidence, so the a-b-c evidence chain can form one final group.
        self.assertEqual(_group_sets(result.mapping), {frozenset({"a", "b", "c"})})

    def test_indirect_merge_cannot_cross_a_permanently_separated_pair(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [1_000, 2_000, 3_000, 3_010, 4_000, 4_010],
                "stock_id": ["a", "c", "a", "b", "b", "c"],
                "time": ["t1", "t1", "t2", "t2", "t3", "t3"],
            }
        )

        result = infer_fixed_groups(data, threshold=100)

        # a-b and b-c each have positive evidence, but t1 permanently separates
        # a and c. Component-level checking prevents the transitive false merge.
        self.assertEqual(
            _group_sets(result.mapping),
            {frozenset({"a", "b"}), frozenset({"c"})},
        )
        self.assertEqual(result.blocked_merge_count, 1)

    def test_same_pair_is_split_if_separated_in_any_later_snapshot(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [1_000, 1_010, 2_000, 3_000],
                "stock_id": ["a", "b", "a", "b"],
                "time": ["t1", "t1", "t2", "t2"],
            }
        )

        result = infer_fixed_groups(data, threshold=100)

        self.assertEqual(
            _group_sets(result.mapping),
            {frozenset({"a"}), frozenset({"b"})},
        )

    def test_gap_equal_to_threshold_starts_a_new_local_group(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [1_000, 1_100],
                "stock_id": ["a", "b"],
                "time": ["t1", "t1"],
            }
        )

        result = infer_fixed_groups(data, threshold=100)

        self.assertEqual(
            _group_sets(result.mapping),
            {frozenset({"a"}), frozenset({"b"})},
        )

    def test_sorts_each_snapshot_by_clock_before_cutting_groups(self) -> None:
        data = pd.DataFrame(
            {
                # Physical row order is c, b, a; clock order is a, b, c.
                "clock": [2_000, 1_010, 1_000],
                "stock_id": ["c", "b", "a"],
                "time": ["t1", "t1", "t1"],
            }
        )

        result = infer_fixed_groups(data, threshold=100)

        self.assertEqual(
            _group_sets(result.mapping),
            {frozenset({"a", "b"}), frozenset({"c"})},
        )

    def test_stronger_positive_edge_is_considered_first_during_conflict(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [
                    1_000,
                    2_000,
                    3_000,
                    3_010,
                    4_000,
                    4_010,
                    5_000,
                    5_010,
                ],
                "stock_id": ["a", "c", "a", "b", "b", "c", "b", "c"],
                "time": ["t0", "t0", "t1", "t1", "t2", "t2", "t3", "t3"],
            }
        )

        result = infer_fixed_groups(data, threshold=100)

        # b-c has two positive observations and a-b has one. b-c is therefore
        # merged first; the later a-b proposal is blocked by the hard a-c split.
        self.assertEqual(
            _group_sets(result.mapping),
            {frozenset({"a"}), frozenset({"b", "c"})},
        )

    def test_automatically_detects_threshold_from_snapshot_gaps(self) -> None:
        gaps = [20, 30, 35, 10_000, 11_000]
        records: list[dict[str, object]] = []
        for index, gap in enumerate(gaps):
            time_value = f"t{index}"
            records.extend(
                [
                    {
                        "clock": index * 100_000,
                        "stock_id": f"a{index}",
                        "time": time_value,
                    },
                    {
                        "clock": index * 100_000 + gap,
                        "stock_id": f"b{index}",
                        "time": time_value,
                    },
                ]
            )

        result = infer_fixed_groups(pd.DataFrame.from_records(records))

        self.assertEqual(result.threshold, 10_000)
        self.assertEqual(result.threshold_source, "automatic")
        self.assertEqual(result.snapshot_count, 5)

    def test_requires_manual_threshold_when_distribution_has_no_abrupt_jump(self) -> None:
        records: list[dict[str, object]] = []
        for index, gap in enumerate([20, 30, 40, 50, 60]):
            records.extend(
                [
                    {"clock": 0, "stock_id": f"a{index}", "time": f"t{index}"},
                    {
                        "clock": gap,
                        "stock_id": f"b{index}",
                        "time": f"t{index}",
                    },
                ]
            )

        with self.assertRaisesRegex(ValueError, "provide --threshold"):
            infer_fixed_groups(pd.DataFrame.from_records(records))

    def test_rejects_multiple_rows_for_one_stock_in_one_snapshot(self) -> None:
        data = pd.DataFrame(
            {
                "clock": [1_000, 1_010],
                "stock_id": ["a", "a"],
                "time": ["t1", "t1"],
            }
        )

        with self.assertRaisesRegex(ValueError, "at most one row"):
            infer_fixed_groups(data, threshold=100)


class ProcessCsvTest(unittest.TestCase):
    def test_ignores_extra_columns_and_preserves_leading_zero_stock_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market_data.csv"
            output_csv = directory / "groups.csv"
            input_csv.write_text(
                "clock,stock_id,exchange,time,last_price\n"
                "1000,000001,SZ,t1,10.50\n"
                "1010,600001,SH,t1,12.30\n"
                "2000,600001,SH,t2,12.35\n",
                encoding="utf-8",
            )

            result = process_csv(input_csv, output_csv, threshold=100)

            self.assertEqual(result.final_group_count, 1)
            self.assertEqual(
                output_csv.read_text(encoding="utf-8"),
                "stock_id,group_id\n"
                "000001,0\n"
                "600001,0\n",
            )

    def test_cli_reports_baseline_diagnostics(self) -> None:
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
            standard_output = io.StringIO()

            with contextlib.redirect_stdout(standard_output):
                exit_code = main(
                    [str(input_csv), str(output_csv), "--threshold", "100"]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("threshold=100 (manual)", standard_output.getvalue())
            self.assertIn("final_groups=1", standard_output.getvalue())


if __name__ == "__main__":
    unittest.main()
