from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from mds.skewed_delta_threshold import (
    estimate_skewed_threshold,
    main,
    process_csv,
)


def _extremely_skewed_deltas() -> np.ndarray:
    """Build a 1/100-scale analogue of the user-reported rank distribution."""

    # 40,000 / 49,800 observations are below 20, matching the reported
    # 4,000,000 / 4,980,000 proportion.  Later segments cross roughly 1,200 at
    # rank 43,000 and 3,000 at rank 49,000, followed by a long sparse tail.
    dense_small_values = np.resize(np.arange(1, 20, dtype="int64"), 40_000)
    first_transition = np.linspace(20, 1_200, 3_000, dtype="int64")
    second_transition = np.linspace(1_200, 3_000, 6_000, dtype="int64")
    sparse_tail = np.geomspace(3_000, 980_000, 800).astype("int64")
    return np.concatenate(
        [dense_small_values, first_transition, second_transition, sparse_tail]
    )


class EstimateSkewedThresholdTest(unittest.TestCase):
    def test_finds_dense_to_sparse_boundary_in_extremely_skewed_data(self) -> None:
        values = _extremely_skewed_deltas()

        result = estimate_skewed_threshold(pd.DataFrame({"delta_clock": values}))

        # The estimator should put the boundary just after the dense <=19 us
        # mass, not near 1,200, 3,000, or the 980,000 us maximum.
        self.assertGreater(result.threshold, 20)
        self.assertLess(result.threshold, 100)
        self.assertEqual(result.positive_count, 49_800)
        self.assertGreater(result.below_threshold_fraction, 0.80)
        self.assertLess(result.below_threshold_fraction, 0.82)
        self.assertEqual(len(result.candidates), 4)
        self.assertLess(result.threshold_spread_ratio, 2)

    def test_top_outliers_do_not_move_the_default_threshold(self) -> None:
        original = _extremely_skewed_deltas()
        altered = original.copy()
        altered[-100:] = 900_000_000

        original_result = estimate_skewed_threshold(
            pd.DataFrame({"delta_clock": original})
        )
        altered_result = estimate_skewed_threshold(
            pd.DataFrame({"delta_clock": altered})
        )

        # The changed values are within the clipped top 0.5%, so they should
        # not alter the geometry used to locate the dense-to-sparse boundary.
        self.assertEqual(altered_result.threshold, original_result.threshold)
        self.assertEqual(
            altered_result.candidate_thresholds,
            original_result.candidate_thresholds,
        )

    def test_reports_and_ignores_nonpositive_boundary_values(self) -> None:
        values = np.concatenate([_extremely_skewed_deltas(), [0, 0, -5]])

        result = estimate_skewed_threshold(pd.DataFrame({"delta_clock": values}))

        self.assertEqual(result.total_count, 49_803)
        self.assertEqual(result.positive_count, 49_800)
        self.assertEqual(result.ignored_nonpositive_count, 3)

    def test_rejects_distribution_without_positive_value_variation(self) -> None:
        data = pd.DataFrame({"delta_clock": np.full(1_000, 10, dtype="int64")})

        with self.assertRaisesRegex(ValueError, "no variation"):
            estimate_skewed_threshold(data)

    def test_rejects_candidates_that_disagree_too_much(self) -> None:
        data = pd.DataFrame({"delta_clock": _extremely_skewed_deltas()})

        with self.assertRaisesRegex(ValueError, "unstable triangle threshold"):
            estimate_skewed_threshold(data, max_threshold_spread=1.01)

    def test_rejects_fractional_delta_clock(self) -> None:
        data = pd.DataFrame({"delta_clock": [1.0, 2.5] * 100})

        with self.assertRaisesRegex(ValueError, "integer values"):
            estimate_skewed_threshold(data)


class ProcessCsvTest(unittest.TestCase):
    def test_writes_summary_and_per_resolution_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "clock_delta.csv"
            output_csv = directory / "threshold.csv"
            diagnostics_csv = directory / "diagnostics.csv"
            values = _extremely_skewed_deltas()
            pd.DataFrame(
                {
                    "stock_id": np.resize(["000001", "600001"], values.size),
                    "delta_clock": values,
                }
            ).to_csv(input_csv, index=False)

            result = process_csv(
                input_csv,
                output_csv,
                diagnostics_csv=diagnostics_csv,
            )

            summary = pd.read_csv(output_csv)
            diagnostics = pd.read_csv(diagnostics_csv)
            self.assertEqual(int(summary.loc[0, "threshold"]), result.threshold)
            self.assertEqual(
                summary.loc[0, "method"], "log_histogram_triangle_ensemble"
            )
            self.assertEqual(len(diagnostics), 4)
            self.assertEqual(
                diagnostics["candidate_threshold"].astype(int).tolist(),
                list(result.candidate_thresholds),
            )

    def test_cli_reports_frequency_aware_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "clock_delta.csv"
            output_csv = directory / "threshold.csv"
            pd.DataFrame({"delta_clock": _extremely_skewed_deltas()}).to_csv(
                input_csv, index=False
            )
            standard_output = io.StringIO()

            with contextlib.redirect_stdout(standard_output):
                exit_code = main([str(input_csv), str(output_csv)])

            self.assertEqual(exit_code, 0)
            self.assertIn(
                "Detected frequency-aware delta_clock threshold",
                standard_output.getvalue(),
            )
            self.assertIn("candidates=[", standard_output.getvalue())


if __name__ == "__main__":
    unittest.main()
