from __future__ import annotations

import ast
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from mds.relative_clock_order_check import (
    build_pairwise_sign_consistency,
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

    def test_all_negative_is_also_consistent(self) -> None:
        result, details = check_relative_clock_order(
            make_vectors(),
            "000001",
            "000002",
        )

        # 反向相减后，t1、t2 的差值分别是 -20 和 -10。虽然不大于 0，
        # 但它们全都严格小于 0，因此两只股票的先后顺序仍然一致。
        self.assertIs(result, True)
        self.assertEqual(details["difference_a_minus_b"].tolist(), [-20, -10])
        self.assertTrue(details["is_strictly_negative"].all())

    def test_positive_and_negative_differences_are_inconsistent(self) -> None:
        vectors = pd.DataFrame(
            {"t1": [20, 0], "t2": [5, 8]},
            index=pd.Index(["a", "b"], name="stock_id"),
        )
        result, details = check_relative_clock_order(vectors, "a", "b")

        self.assertIs(result, False)
        self.assertEqual(details["difference_a_minus_b"].tolist(), [20, -3])

    def test_zero_breaks_otherwise_consistent_sign(self) -> None:
        vectors = pd.DataFrame(
            {"t1": [20, 0], "t2": [10, 10], "t3": [5, 0]},
            index=pd.Index(["a", "b"], name="stock_id"),
        )
        result, details = check_relative_clock_order(vectors, "a", "b")

        # 差值是 20、0、5。0 既不大于 0 也不小于 0，所以不能算同号。
        self.assertIs(result, False)
        zero_row = details.loc[details["difference_a_minus_b"].eq(0)].iloc[0]
        self.assertFalse(zero_row["is_strictly_positive"])
        self.assertFalse(zero_row["is_strictly_negative"])

    def test_no_common_snapshot_returns_insufficient_evidence(self) -> None:
        vectors = pd.DataFrame(
            {"t1": [10, pd.NA], "t2": [pd.NA, 20]},
            index=pd.Index(["a", "b"], name="stock_id"),
            dtype="Int64",
        )
        result, details = check_relative_clock_order(vectors, "a", "b")

        self.assertIsNone(result)
        self.assertTrue(details.empty)

    def test_all_unordered_pairs_are_returned_as_a_dict(self) -> None:
        vectors = pd.DataFrame(
            {
                "t1": [0, 10, 5, pd.NA],
                "t2": [0, 20, -1, pd.NA],
                "t3": [pd.NA, pd.NA, pd.NA, 30],
            },
            index=pd.Index(["a", "b", "c", "d"], name="stock_id"),
            dtype="Int64",
        )

        result = build_pairwise_sign_consistency(vectors)

        # 四只股票共有 4 * 3 / 2 = 6 个无序股票对，每对只出现一次。
        self.assertEqual(
            result,
            {
                "a_b": True,  # a - b 为 -10、-20：全部为负。
                "a_c": False,  # a - c 为 -5、1：出现正负反转。
                "a_d": None,  # a、d 没有共同 snapshot。
                "b_c": True,  # b - c 为 5、21：全部为正。
                "b_d": None,
                "c_d": None,
            },
        )

    def test_cli_without_stock_ids_prints_pairwise_dict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            vectors_csv = Path(temporary_directory) / "vectors.csv"
            make_vectors().to_csv(vectors_csv)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main([str(vectors_csv)])

        pair_results = ast.literal_eval(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertIs(pair_results["000001_000002"], True)
        self.assertIs(pair_results["000001_600000"], True)
        self.assertEqual(len(pair_results), 6)

    def test_cli_prints_direction_counts_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            vectors_csv = Path(temporary_directory) / "vectors.csv"
            make_vectors().to_csv(vectors_csv)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main([str(vectors_csv), "000001", "000002"])

        self.assertEqual(exit_code, 0)
        self.assertIn("比较方向：000001 - 000002", output.getvalue())
        self.assertIn("共同 snapshot 数：2", output.getvalue())
        self.assertIn("符号一致为负", output.getvalue())


if __name__ == "__main__":
    unittest.main()
