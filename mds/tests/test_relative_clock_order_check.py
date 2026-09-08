from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from mds.relative_clock_order_check import (
    check_relative_clock_order,
    main,
    read_relative_clock_vectors,
)


def make_vectors() -> pd.DataFrame:
    """构造包含正差值、零差值和缺失维度的小型向量表。"""

    return pd.DataFrame(
        {
            "t1": [0, 20, pd.NA, 5],
            "t2": [0, 10, 15, pd.NA],
            "t3": [pd.NA, 30, 25, 8],
        },
        index=pd.Index(["000001", "000002", "600000", "600001"], name="stock_id"),
        dtype="Int64",
    )


class RelativeClockOrderCheckTest(unittest.TestCase):
    def test_read_vectors_preserves_stock_id_and_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            vectors_csv = Path(temporary_directory) / "vectors.csv"
            make_vectors().to_csv(vectors_csv)
            vectors = read_relative_clock_vectors(vectors_csv)

        self.assertEqual(vectors.index.tolist()[0], "000001")
        self.assertTrue(pd.isna(vectors.loc["000001", "t3"]))

    def test_all_positive_uses_only_common_snapshots(self) -> None:
        result, details = check_relative_clock_order(
            make_vectors(),
            "000002",
            "000001",
        )

        # t3 中 000001 缺失，所以只比较 t1、t2：差值分别是 20 和 10。
        self.assertIs(result, True)
        self.assertEqual(details["snapshot"].tolist(), ["t1", "t2"])
        self.assertEqual(details["difference_a_minus_b"].tolist(), [20, 10])

    def test_zero_or_negative_difference_fails_strict_comparison(self) -> None:
        vectors = pd.DataFrame(
            {"t1": [20, 0], "t2": [10, 10], "t3": [5, 8]},
            index=pd.Index(["a", "b"], name="stock_id"),
        )
        result, details = check_relative_clock_order(vectors, "a", "b")

        self.assertIs(result, False)
        failed = details.loc[~details["is_strictly_positive"]]
        self.assertEqual(failed["snapshot"].tolist(), ["t2", "t3"])
        self.assertEqual(failed["difference_a_minus_b"].tolist(), [0, -3])

    def test_no_common_snapshot_returns_insufficient_evidence(self) -> None:
        vectors = pd.DataFrame(
            {"t1": [10, pd.NA], "t2": [pd.NA, 20]},
            index=pd.Index(["a", "b"], name="stock_id"),
            dtype="Int64",
        )
        result, details = check_relative_clock_order(vectors, "a", "b")

        self.assertIsNone(result)
        self.assertTrue(details.empty)

    def test_cli_prints_direction_counts_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            vectors_csv = Path(temporary_directory) / "vectors.csv"
            make_vectors().to_csv(vectors_csv)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main([str(vectors_csv), "000002", "000001"])

        self.assertEqual(exit_code, 0)
        self.assertIn("比较方向：000002 - 000001", output.getvalue())
        self.assertIn("共同 snapshot 数：2", output.getvalue())
        self.assertIn("判断结果：是", output.getvalue())


if __name__ == "__main__":
    unittest.main()
