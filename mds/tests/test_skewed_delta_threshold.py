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


def _within_group_body() -> np.ndarray:
    """Build the within-group body from the user-reported rank landmarks."""

    # 49,000 body observations represent within-group gaps.  They reproduce
    # the reported landmarks: 40,000 below 20, about 1,200 at rank 43,000, and
    # 3,000 at rank 49,000.
    dense_small_values = np.resize(np.arange(1, 20, dtype="int64"), 40_000)
    first_body_transition = np.linspace(20, 1_200, 3_000, dtype="int64")
    second_body_transition = np.linspace(1_200, 3_000, 6_000, dtype="int64")
    return np.concatenate(
        [dense_small_values, first_body_transition, second_body_transition]
    )


def _small_body_with_long_tail() -> tuple[np.ndarray, np.ndarray]:
    """Build a labeled 1/100-scale analogue of the reported rank curve."""

    body = _within_group_body()
    between_group_tail = np.geomspace(3_000, 980_000, 800).astype("int64")
    values = np.concatenate([body, between_group_tail])
    is_between_group = np.concatenate(
        [
            np.zeros(49_000, dtype="bool"),
            np.ones(800, dtype="bool"),
        ]
    )
    return values, is_between_group


class EstimateSkewedThresholdTest(unittest.TestCase):
    def test_finds_start_of_small_rapidly_growing_tail(self) -> None:
        values, is_between_group = _small_body_with_long_tail()

        result = estimate_skewed_threshold(pd.DataFrame({"delta_clock": values}))

        # The target is the final tail near 3,000 us, not the first density
        # shoulder immediately after the 1..19 us mass.
        self.assertGreaterEqual(result.threshold, 2_800)
        self.assertLessEqual(result.threshold, 3_500)
        self.assertLess(result.tail_fraction, 0.02)
        self.assertLess(result.breakpoint_quantile_spread, 0.001)
        self.assertLess(result.threshold_spread_ratio, 1.2)

        predicted_between_group = values >= result.threshold
        true_positive = np.count_nonzero(predicted_between_group & is_between_group)
        predicted_positive = np.count_nonzero(predicted_between_group)
        precision = true_positive / predicted_positive
        recall = true_positive / np.count_nonzero(is_between_group)
        self.assertGreater(precision, 0.99)
        self.assertGreater(recall, 0.98)

    def test_finds_same_onset_for_different_tail_shapes(self) -> None:
        body = _within_group_body()
        random = np.random.default_rng(20260902)
        tails = {
            "linear": np.linspace(3_000, 980_000, 800).astype("int64"),
            "pareto": np.sort(
                np.minimum(
                    980_000,
                    (3_000 * (random.pareto(1.2, 800) + 1)).astype("int64"),
                )
            ),
            "lognormal": np.sort(
                np.minimum(
                    980_000,
                    np.maximum(
                        3_000,
                        np.exp(random.normal(np.log(12_000), 1.1, 800)),
                    ).astype("int64"),
                )
            ),
        }

        for name, tail in tails.items():
            with self.subTest(tail_shape=name):
                values = np.concatenate([body, tail])
                result = estimate_skewed_threshold(
                    pd.DataFrame({"delta_clock": values})
                )

                self.assertGreaterEqual(result.threshold, 2_800)
                self.assertLessEqual(result.threshold, 3_500)
                predicted_tail = values >= result.threshold
                true_tail = np.arange(values.size) >= body.size
                true_positive = np.count_nonzero(predicted_tail & true_tail)
                precision = true_positive / np.count_nonzero(predicted_tail)
                recall = true_positive / tail.size
                self.assertGreater(precision, 0.90)
                # The clipped lognormal case deliberately has tail records
                # tied with body records at 3,000.  No scalar threshold can
                # perfectly separate those identical observed values.
                self.assertGreater(recall, 0.90)

    def test_top_outliers_do_not_move_threshold(self) -> None:
        values, _ = _small_body_with_long_tail()
        altered = values.copy()
        altered[-10:] = 900_000_000

        original_result = estimate_skewed_threshold(
            pd.DataFrame({"delta_clock": values})
        )
        altered_result = estimate_skewed_threshold(
            pd.DataFrame({"delta_clock": altered})
        )

        # At this sample size the top ten values are above the default 99.95%
        # regression endpoint.  They remain counted as tail observations but
        # cannot pull the fitted breakpoint to the right.
        self.assertEqual(altered_result.threshold, original_result.threshold)
        self.assertEqual(
            altered_result.candidate_thresholds,
            original_result.candidate_thresholds,
        )

    def test_reports_and_ignores_nonpositive_boundary_values(self) -> None:
        values, _ = _small_body_with_long_tail()
        values = np.concatenate([values, [0, 0, -5]])

        result = estimate_skewed_threshold(pd.DataFrame({"delta_clock": values}))

        self.assertEqual(result.total_count, 49_803)
        self.assertEqual(result.positive_count, 49_800)
        self.assertEqual(result.ignored_nonpositive_count, 3)

    def test_rejects_smooth_curve_without_tail_changepoint(self) -> None:
        # log1p(delta_clock) grows almost linearly across rank, so there is no
        # distinct late acceleration that could separate two regimes.
        values = np.expm1(np.linspace(np.log1p(2), np.log1p(980_000), 49_800)).astype(
            "int64"
        )

        with self.assertRaisesRegex(ValueError, "no stable upper-tail changepoint"):
            estimate_skewed_threshold(pd.DataFrame({"delta_clock": values}))

    def test_rejects_window_dependent_breakpoint_in_one_smooth_distribution(
        self,
    ) -> None:
        # A single exponential distribution has a smoothly curving upper
        # quantile function.  A two-line fit can approximate that curvature,
        # but its apparent breakpoint moves when the observation window moves.
        quantiles = (np.arange(49_800, dtype="float64") + 0.5) / 49_800
        values = np.ceil(-100 * np.log1p(-quantiles)).astype("int64")

        with self.assertRaisesRegex(ValueError, "no stable upper-tail changepoint"):
            estimate_skewed_threshold(pd.DataFrame({"delta_clock": values}))

    def test_rejects_distribution_without_positive_value_variation(self) -> None:
        data = pd.DataFrame({"delta_clock": np.full(49_800, 10, dtype="int64")})

        with self.assertRaisesRegex(ValueError, "no variation"):
            estimate_skewed_threshold(data)

    def test_rejects_fractional_delta_clock(self) -> None:
        data = pd.DataFrame({"delta_clock": [1.0, 2.5] * 1_000})

        with self.assertRaisesRegex(ValueError, "integer values"):
            estimate_skewed_threshold(data)


class ProcessCsvTest(unittest.TestCase):
    def test_writes_summary_and_per_window_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "clock_delta.csv"
            output_csv = directory / "threshold.csv"
            diagnostics_csv = directory / "diagnostics.csv"
            values, _ = _small_body_with_long_tail()
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
                summary.loc[0, "method"],
                "upper_quantile_local_slope_ensemble",
            )
            self.assertEqual(len(diagnostics), 3)
            self.assertEqual(
                diagnostics["candidate_threshold"].astype(int).tolist(),
                list(result.candidate_thresholds),
            )

    def test_cli_reports_upper_tail_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "clock_delta.csv"
            output_csv = directory / "threshold.csv"
            values, _ = _small_body_with_long_tail()
            pd.DataFrame({"delta_clock": values}).to_csv(input_csv, index=False)
            standard_output = io.StringIO()

            with contextlib.redirect_stdout(standard_output):
                exit_code = main([str(input_csv), str(output_csv)])

            self.assertEqual(exit_code, 0)
            self.assertIn(
                "Detected upper-tail delta_clock threshold",
                standard_output.getvalue(),
            )
            self.assertIn("breakpoint_quantiles=[", standard_output.getvalue())


if __name__ == "__main__":
    unittest.main()
