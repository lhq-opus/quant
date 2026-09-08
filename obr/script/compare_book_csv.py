#!/usr/bin/env python3
"""逐行对比 OBR 输出和答案的 caa、买卖五档价量，使用 pandas 读写 CSV。"""

import argparse
from decimal import Decimal, InvalidOperation
from itertools import zip_longest
from pathlib import Path

import pandas as pd

# 按答案的盘口顺序列出要比较的字段，不比较 event_type、secid 和累计成交统计。
# 两份输入的列顺序可以不同，读取后都按这份列表排列。
COMPARE_COLUMNS = [
    "caa",
    "bp5",
    "bp4",
    "bp3",
    "bp2",
    "bp1",
    "ap1",
    "ap2",
    "ap3",
    "ap4",
    "ap5",
    "bs5",
    "bs4",
    "bs3",
    "bs2",
    "bs1",
    "as1",
    "as2",
    "as3",
    "as4",
    "as5",
]
DIFF_COLUMNS = [
    "data_row",
    "field",
    "actual_caa",
    "expected_caa",
    "actual_value",
    "expected_value",
]


def parse_args():
    """actual 是自己的输出，expected 是答案，output 是单独的差异文件。"""
    parser = argparse.ArgumentParser(description="逐行精确比较 caa 和买卖五档价量。")
    parser.add_argument(
        "--actual", required=True, type=Path, help="自己的 OBR 输出 CSV"
    )
    parser.add_argument("--expected", required=True, type=Path, help="答案 book CSV")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("book_diff.csv"),
        help="差异 CSV 路径，默认 book_diff.csv",
    )
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有差异文件")
    return parser.parse_args()


def read_book(path):
    """原样保留 CAA 和数值文本，不让 pandas 转成浮点数或把空档变成 NaN。"""
    frame = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        skip_blank_lines=False,
        encoding="utf-8-sig",
    )

    # 旧答案用 bo4 表示买四价，当前 replay 用 bp4。只在读取视图中兼容这个已有约定，
    # 并明确提示用户；不修改原始文件。已经存在 bp4 时，直接使用 bp4。
    if "bp4" not in frame.columns and "bo4" in frame.columns:
        print("%s：按项目约定将 bo4 作为 bp4 比较。" % path)
        frame = frame.rename(columns={"bo4": "bp4"})

    missing = [column for column in COMPARE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("%s 缺少必需列：%s" % (path, ", ".join(missing)))
    return frame.loc[:, COMPARE_COLUMNS]


def values_equal(field, actual, expected):
    """CAA 比原始字符串；盘口价量比精确数值，空字段只与空字段相等。"""
    if field == "caa" or actual == "" or expected == "":
        return actual == expected

    # Decimal 直接读取字符串：10、10.0、10.0000 等值，不舍入，也不使用浮点容差。
    actual_number = Decimal(actual)
    expected_number = Decimal(expected)
    return (
        actual_number.is_finite()
        and expected_number.is_finite()
        and actual_number == expected_number
    )


def compare_books(actual, expected):
    """外层逐行、内层逐字段；每个不相等的字段生成一条差异记录。"""
    differences = []
    actual_rows = actual.itertuples(index=False, name=None)
    expected_rows = expected.itertuples(index=False, name=None)

    # zip_longest 同时取两边的一行；短的一边读完后用 None 补齐。
    # 不能用普通 zip，否则较长文件的尾部会被漏掉，导致错误地报告一致。
    for data_row, (left, right) in enumerate(
        zip_longest(actual_rows, expected_rows), 1
    ):
        actual_caa = left[0] if left is not None else ""
        expected_caa = right[0] if right is not None else ""
        if left is None or right is None:
            differences.append(
                [
                    data_row,
                    "__row__",
                    actual_caa,
                    expected_caa,
                    "缺少整行" if left is None else "存在整行",
                    "缺少整行" if right is None else "存在整行",
                ]
            )
            continue

        # 不按 CAA join、不排序。即使两行 CAA 不同，也列出这一行的所有字段差异。
        for field, actual_value, expected_value in zip(COMPARE_COLUMNS, left, right):
            try:
                same = values_equal(field, actual_value, expected_value)
            except InvalidOperation as error:
                raise ValueError(
                    "数据行 %d，字段 %s 不是合法数值：actual=%r，expected=%r"
                    % (data_row, field, actual_value, expected_value)
                ) from error
            if not same:
                differences.append(
                    [
                        data_row,
                        field,
                        actual_caa,
                        expected_caa,
                        actual_value,
                        expected_value,
                    ]
                )

    # 即使没有差异，也返回固定表头，输出文件只有表头。
    return pd.DataFrame(differences, columns=DIFF_COLUMNS)


def main():
    """读取、比较、输出差异；完全一致返回 0，有差异返回 1。"""
    args = parse_args()
    output = args.output.resolve()
    for input_path in (args.actual, args.expected):
        if output == input_path.resolve() or (
            output.exists() and output.samefile(input_path)
        ):
            raise ValueError("差异输出路径不能覆盖输入文件")
    if output.exists() and not args.overwrite:
        raise FileExistsError("差异文件已存在；如需覆盖，请使用 --overwrite")

    actual = read_book(args.actual)
    expected = read_book(args.expected)
    differences = compare_books(actual, expected)

    output.parent.mkdir(parents=True, exist_ok=True)
    differences.to_csv(
        output, index=False, encoding="utf-8", mode="w" if args.overwrite else "x"
    )
    print("实际输出 %d 行，答案 %d 行。" % (len(actual), len(expected)))
    print("差异明细：%s（data_row 从 1 开始，不含表头）" % output)
    if differences.empty:
        print("对比一致：caa 和20个五档价量字段全部相等。")
        return 0

    print(
        "对比不一致：%d 行，%d 处差异。"
        % (differences["data_row"].nunique(), len(differences))
    )
    print("前10处差异：")
    print(differences.head(10).to_string(index=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
