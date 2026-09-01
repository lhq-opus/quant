from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from mds.clock_delta import calculate_clock_deltas, process_csv


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


class ProcessCsvTest(unittest.TestCase):
    def test_reads_only_required_columns_and_preserves_stock_id_text(self) -> None:
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

            process_csv(input_csv, output_csv)

            self.assertEqual(
                output_csv.read_text(encoding="utf-8"),
                "stock_id,delta_clock\n"
                "000001,0\n"
                "600001,60\n"
                "000002,0\n",
            )


if __name__ == "__main__":
    unittest.main()
