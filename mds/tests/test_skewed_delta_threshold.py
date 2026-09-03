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


def _mock_delta_clock() -> np.ndarray:
    """按用户描述的排名比例，构造一份缩小后的长尾数据。"""

    # 前 49,000 个值代表组内 gap：40,000 个集中在 20 微秒以下，
    # 接着逐渐增长到 1200 和 3000 微秒。
    dense_small_values = np.resize(np.arange(1, 20, dtype="int64"), 40_000)
    middle_values = np.concatenate(
        [
            np.linspace(20, 1_200, 3_000, dtype="int64"),
            np.linspace(1_200, 3_000, 6_000, dtype="int64"),
        ]
    )

    # 最后 800 个值代表快速增长的组间长尾。
    long_tail = np.geomspace(3_000, 980_000, 800).astype("int64")
    return np.concatenate([dense_small_values, middle_values, long_tail])


class EstimateThresholdTest(unittest.TestCase):
    def test_finds_the_start_of_the_small_upper_tail(self) -> None:
        values = _mock_delta_clock()

        threshold = estimate_skewed_threshold(
            pd.DataFrame({"delta_clock": values})
        )

        # 目标是最后一段长尾在约 3000 微秒处的起点，而不是 20 微秒附近
        # 的高密度主体边缘。模拟数据只是验证算法方向，不是真实业务阈值。
        self.assertGreaterEqual(threshold, 2_800)
        self.assertLessEqual(threshold, 3_500)

    def test_zero_and_negative_values_do_not_change_the_threshold(self) -> None:
        values = _mock_delta_clock()
        original = estimate_skewed_threshold(
            pd.DataFrame({"delta_clock": values})
        )
        with_boundaries = estimate_skewed_threshold(
            pd.DataFrame({"delta_clock": np.concatenate([values, [0, 0, -5]])})
        )

        # 0 是新 snapshot 的边界标记，负数也不属于正 gap 分布。
        self.assertEqual(with_boundaries, original)


class ProcessCsvTest(unittest.TestCase):
    def test_writes_one_threshold_to_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "clock_delta.csv"
            output_csv = directory / "threshold.csv"

            # mock CSV 只存在于系统临时目录，测试完成后自动删除。
            pd.DataFrame({"delta_clock": _mock_delta_clock()}).to_csv(
                input_csv,
                index=False,
            )

            threshold = process_csv(input_csv, output_csv)

            result = pd.read_csv(output_csv)
            self.assertEqual(result.columns.tolist(), ["threshold"])
            self.assertEqual(int(result.loc[0, "threshold"]), threshold)

    def test_cli_prints_chinese_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_csv = directory / "clock_delta.csv"
            output_csv = directory / "threshold.csv"
            pd.DataFrame({"delta_clock": _mock_delta_clock()}).to_csv(
                input_csv,
                index=False,
            )
            standard_output = io.StringIO()

            with contextlib.redirect_stdout(standard_output):
                exit_code = main([str(input_csv), str(output_csv)])

            self.assertEqual(exit_code, 0)
            self.assertIn("候选阈值", standard_output.getvalue())
            self.assertIn("微秒", standard_output.getvalue())


if __name__ == "__main__":
    unittest.main()
