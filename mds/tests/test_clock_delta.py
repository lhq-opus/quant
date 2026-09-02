from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from mds.clock_delta import (
    calculate_clock_deltas,
    find_abrupt_increase,
    main,
    process_csv,
    sort_clock_deltas,
)


class CalculateClockDeltasTest(unittest.TestCase):
    def test_applies_row_order_and_time_boundary_rules(self) -> None:
        source = pd.DataFrame(
            {
                "clock": [1_000_000, 1_000_080, 2_000_000, 2_000_040, 1_999_990],
                "stock_id": ["600001", "600003", "000001", "000002", "000003"],
                "time": ["09:15:00", "09:15:00", "09:15:03", "09:15:03", "09:15:03"],
            }
        )

        actual = calculate_clock_deltas(source)

        expected = pd.DataFrame(
            {
                "stock_id": ["600001", "600003", "000001", "000002", "000003"],
                "delta_clock": [0, 80, 0, 40, -50],
            }
        )
        assert_frame_equal(actual, expected)

    def test_rejects_non_integer_clock(self) -> None:
        source = pd.DataFrame(
            {
                "clock": ["100.5"],
                "stock_id": ["600001"],
                "time": ["09:15:00"],
            }
        )

        with self.assertRaisesRegex(ValueError, "integer microsecond"):
            calculate_clock_deltas(source)

    def test_empty_input_keeps_output_schema(self) -> None:
        source = pd.DataFrame(columns=["clock", "stock_id", "time"])

        actual = calculate_clock_deltas(source)

        self.assertEqual(actual.columns.tolist(), ["stock_id", "delta_clock"])
        self.assertTrue(actual.empty)


class SortClockDeltasTest(unittest.TestCase):
    def test_sorts_ascending_and_preserves_tie_order(self) -> None:
        source = pd.DataFrame(
            {
                "stock_id": ["a", "b", "c", "d", "e"],
                "delta_clock": [0, 80, 0, 40, -50],
            }
        )

        actual = sort_clock_deltas(source)

        expected = pd.DataFrame(
            {
                "stock_id": ["e", "a", "c", "d", "b"],
                "delta_clock": [-50, 0, 0, 40, 80],
            }
        )
        assert_frame_equal(actual, expected)


class FindAbruptIncreaseTest(unittest.TestCase):
    def test_finds_requested_ideal_jump(self) -> None:
        source = pd.DataFrame(
            {"delta_clock": [20, 30, 35, 10_000, 11_000]}
        )

        actual = find_abrupt_increase(source)

        self.assertIsNotNone(actual)
        assert actual is not None
        self.assertEqual(actual.delta_clock, 10_000)
        self.assertEqual(actual.previous_delta_clock, 35)
        self.assertEqual(actual.slope, 9_965)
        self.assertEqual(actual.lower_count, 3)
        self.assertEqual(actual.upper_count, 2)

    def test_ignores_nonpositive_values_and_duplicate_slopes(self) -> None:
        source = pd.DataFrame(
            {
                "delta_clock": [
                    10_000,
                    0,
                    20,
                    -50,
                    20,
                    11_000,
                    35,
                    10_000,
                    30,
                ]
            }
        )

        actual = find_abrupt_increase(source)

        self.assertIsNotNone(actual)
        assert actual is not None
        self.assertEqual(actual.delta_clock, 10_000)

    def test_returns_first_of_multiple_abnormal_jumps(self) -> None:
        source = pd.DataFrame(
            {"delta_clock": [20, 25, 30, 35, 900, 950, 1_000, 10_000, 11_000]}
        )

        actual = find_abrupt_increase(source)

        self.assertIsNotNone(actual)
        assert actual is not None
        self.assertEqual(actual.delta_clock, 900)
        self.assertEqual(actual.previous_delta_clock, 35)

    def test_returns_none_for_smooth_distribution(self) -> None:
        source = pd.DataFrame(
            {"delta_clock": [20, 30, 40, 50, 60, 70, 80]}
        )

        self.assertIsNone(find_abrupt_increase(source))

    def test_does_not_use_unsupported_single_tail_value(self) -> None:
        source = pd.DataFrame(
            {"delta_clock": [20, 30, 40, 50, 1_000_000]}
        )

        self.assertIsNone(find_abrupt_increase(source))


class ProcessCsvTest(unittest.TestCase):
    def test_reads_required_columns_preserves_ids_and_sorts_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market_data.csv"
            output_csv = directory / "clock_delta.csv"
            input_csv.write_text(
                "clock,stock_id,exchange,time,last_price\n"
                "1000000,000001,SZ,09:15:00,10.50\n"
                "1000060,600001,SH,09:15:00,12.30\n"
                "2000000,000002,SZ,09:15:03,8.20\n",
                encoding="utf-8",
            )

            abrupt_increase = process_csv(input_csv, output_csv)

            self.assertIsNone(abrupt_increase)
            self.assertEqual(
                output_csv.read_text(encoding="utf-8"),
                "stock_id,delta_clock\n"
                "000001,0\n"
                "000002,0\n"
                "600001,60\n",
            )

    def test_reports_detected_value_from_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "market_data.csv"
            output_csv = directory / "clock_delta.csv"
            input_csv.write_text(
                "clock,stock_id,time\n"
                "1000000,000001,09:15:00\n"
                "1000020,000002,09:15:00\n"
                "1000050,000003,09:15:00\n"
                "1000085,000004,09:15:00\n"
                "1010085,000005,09:15:00\n"
                "1021085,000006,09:15:00\n",
                encoding="utf-8",
            )
            standard_output = io.StringIO()

            with contextlib.redirect_stdout(standard_output):
                exit_code = main([str(input_csv), str(output_csv)])

            self.assertEqual(exit_code, 0)
            self.assertIn("value=10000", standard_output.getvalue())
            self.assertIn("previous=35", standard_output.getvalue())


if __name__ == "__main__":
    unittest.main()
