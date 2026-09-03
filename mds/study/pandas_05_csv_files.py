"""第五课：创建、合并和分批写入 CSV 文件。

运行方式（先进入 ``quant/`` 目录）：

    python -m mds.study.pandas_05_csv_files

本课会创建真实文件以演示文件级操作，但所有文件都位于系统临时目录，脚本
结束后自动删除。示例只使用派生数据需要的三列，不会产生或提交 mock CSV。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from .pandas_01_io_selection import REQUIRED_COLUMNS

CSV_DTYPES = {
    "clock": "int64",
    "stock_id": "string",
    "time": "string",
}

MORNING_RECORDS: list[dict[str, object]] = [
    {"clock": 1_000_000, "stock_id": "000001", "time": "09:30:00"},
    {"clock": 1_000_020, "stock_id": "600000", "time": "09:30:00"},
]

AFTERNOON_RECORDS: list[dict[str, object]] = [
    {"clock": 2_000_000, "stock_id": "000001", "time": "13:00:00"},
    {"clock": 2_000_030, "stock_id": "000002", "time": "13:00:00"},
]


def build_market_frame(records: list[dict[str, object]]) -> pd.DataFrame:
    """从 Python 记录创建列顺序和 dtype 明确的 DataFrame。"""

    # from_records 很适合“若干条字典记录 -> 表”的场景。columns 不只决定
    # 顺序；当 records 为空时，它仍能创建三列，而不是一个完全没有列的表。
    data = pd.DataFrame.from_records(records, columns=REQUIRED_COLUMNS)

    # CSV 是文本格式，不保存 pandas dtype。这里先把内存表规范化；每次重新
    # read_csv 时仍然要再次传 dtype，不能期待 CSV 帮我们记住类型。
    return data.astype(CSV_DTYPES)


def write_market_csv(data: pd.DataFrame, output_csv: Path | str) -> None:
    """创建一个带表头和数据行的 CSV。"""

    data.to_csv(
        output_csv,
        columns=REQUIRED_COLUMNS,
        index=False,
        encoding="utf-8",
    )

    # to_csv 默认 mode="w"：目标已存在时会覆盖。若业务要求“文件存在就报错”，
    # 可以显式传 mode="x"。生产代码应先确认目标路径，避免覆盖重要结果。


def create_header_only_csv(output_csv: Path | str) -> None:
    """创建只有 ``clock,stock_id,time`` 表头、没有数据行的 CSV。"""

    empty_data = build_market_frame([])
    write_market_csv(empty_data, output_csv)


def read_derived_market_csv(input_csv: Path | str) -> pd.DataFrame:
    """读取本课的三列派生 CSV，并检查表头是否完全一致。"""

    data = pd.read_csv(input_csv, dtype=CSV_DTYPES, encoding="utf-8")

    # 这里检查“完全相同”，因为本课合并的是同 schema 的派生文件。真实原始
    # market data 还含很多行情列，应像第一课那样用 usecols 读取所需三列。
    if data.columns.tolist() != REQUIRED_COLUMNS:
        raise ValueError(
            f"CSV columns must be {REQUIRED_COLUMNS}, got {data.columns.tolist()}"
        )
    return data


def concatenate_csv_rows(input_csvs: Iterable[Path | str]) -> pd.DataFrame:
    """把多个相同表头的 CSV 纵向拼接为一张表。"""

    # 这是便于入门的小文件写法：列表会让所有 DataFrame 同时留在内存中。
    # 对数百万行或很多文件，应结合第四课的 chunksize 分批读取和写出。
    frames = [read_derived_market_csv(path) for path in input_csvs]
    if not frames:
        return build_market_frame([])

    # concat(axis=0) 表示按行向下堆叠：先保留第一个文件的全部行，再放第二个。
    # ignore_index=True 重新生成 0..N-1 索引，避免不同文件各自的 0..M-1 重复。
    # concat 不会自动去重；只有业务明确确认重复无意义时才能 drop_duplicates。
    return pd.concat(frames, axis=0, ignore_index=True)


def merge_market_and_group_csv(
    market_csv: Path | str,
    group_csv: Path | str,
) -> pd.DataFrame:
    """按 stock_id 把分组 CSV 的列连接到 market data 行。"""

    market = read_derived_market_csv(market_csv)
    groups = pd.read_csv(
        group_csv,
        dtype={"stock_id": "string", "group_id": "Int64"},
        encoding="utf-8",
    )
    expected_group_columns = ["stock_id", "group_id"]
    if groups.columns.tolist() != expected_group_columns:
        raise ValueError(
            f"group CSV columns must be {expected_group_columns}, "
            f"got {groups.columns.tolist()}"
        )

    # merge 不是把行简单堆起来，而是像 SQL JOIN 一样按 stock_id 补充列。
    # many_to_one 检查右边映射表每只股票至多一行；indicator 则显示是否匹配。
    return market.merge(
        groups,
        on="stock_id",
        how="left",
        validate="many_to_one",
        indicator="group_match",
    )


def write_csv_batches(
    batches: Iterable[pd.DataFrame],
    output_csv: Path | str,
) -> None:
    """依次追加多个 DataFrame，同时保证表头只写一次。"""

    wrote_any_batch = False

    for batch in batches:
        if batch.empty:
            continue

        batch.to_csv(
            output_csv,
            columns=REQUIRED_COLUMNS,
            index=False,
            encoding="utf-8",
            # 第一批创建/覆盖文件，后续批次追加到文件末尾。
            mode="a" if wrote_any_batch else "w",
            # 只有第一批写列名。若追加时仍用 header=True，表头会混进数据中间。
            header=not wrote_any_batch,
        )
        wrote_any_batch = True

    # 即使没有任何数据，也创建一个有明确表头的空 CSV，便于下游正常读取。
    if not wrote_any_batch:
        create_header_only_csv(output_csv)

    # 分批追加可能在中途失败并留下半成品。重要生产结果可先写同目录临时文件，
    # 全部成功后再原子重命名；本课先聚焦 pandas 的 mode/header 基础语义。


def main() -> int:
    """在临时目录中演示五种 CSV 文件操作。"""

    morning = build_market_frame(MORNING_RECORDS)
    afternoon = build_market_frame(AFTERNOON_RECORDS)

    with TemporaryDirectory() as temporary_directory:
        directory = Path(temporary_directory)
        header_only_csv = directory / "header_only.csv"
        morning_csv = directory / "morning.csv"
        afternoon_csv = directory / "afternoon.csv"
        combined_csv = directory / "combined.csv"
        group_csv = directory / "groups.csv"
        batches_csv = directory / "batches.csv"

        create_header_only_csv(header_only_csv)
        write_market_csv(morning, morning_csv)
        write_market_csv(afternoon, afternoon_csv)

        # 场景一：两份表头相同的行情记录按行合并。
        combined = concatenate_csv_rows([morning_csv, afternoon_csv])
        write_market_csv(combined, combined_csv)

        # 场景二：行情表和 stock_id -> group_id 映射按键补充列。
        pd.DataFrame(
            {
                "stock_id": pd.Series(["000001", "600000"], dtype="string"),
                "group_id": pd.Series([1, 1], dtype="int64"),
            }
        ).to_csv(group_csv, index=False, encoding="utf-8")
        merged = merge_market_and_group_csv(combined_csv, group_csv)

        # 把同一结果拆成三批写回；最终文件仍只应有一个表头。
        write_csv_batches(
            [combined.iloc[:1], combined.iloc[1:3], combined.iloc[3:]],
            batches_csv,
        )
        batch_text = batches_csv.read_text(encoding="utf-8")

        print("\n[1] 创建只有表头的 CSV")
        print(header_only_csv.read_text(encoding="utf-8").rstrip())

        print("\n[2] 从记录创建并写出 CSV")
        print(morning_csv.read_text(encoding="utf-8").rstrip())

        print("\n[3] 相同 schema 的两个 CSV 按行 concat")
        print(combined.to_string(index=False))

        print("\n[4] 不同 schema 的两个 CSV 按 stock_id merge")
        print(merged.to_string(index=False))

        print("\n[5] 分批追加：表头出现次数")
        print(batch_text.count("clock,stock_id,time"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
