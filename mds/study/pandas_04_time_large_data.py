"""第四课：交易时段切片、大 CSV 分块读取和内存检查。

运行方式（先进入 ``quant/`` 目录）：

    python -m mds.study.pandas_04_time_large_data

MDS 一天可能有数百万行。chunksize 能降低部分任务的峰值内存，但需要全局
排序、全局分位数或完整 snapshot 的算法不能无状态地逐块计算。

本课的 mock 明确假设 ``time`` 编码为零补齐的 ``HH:MM:SS``。真实 CSV 的
具体编码和精度仍待确认；确认后应调整解析格式，不能从列名静默推断。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from io import StringIO

import pandas as pd

from .pandas_01_io_selection import (
    EXAMPLE_MARKET_CSV,
    REQUIRED_COLUMNS,
    load_example_market_data,
)

CSV_DTYPES = {
    "clock": "int64",
    "stock_id": "string",
    "time": "string",
}


def add_trading_session(data: pd.DataFrame) -> pd.DataFrame:
    """把 time 文本解析成日内时长，并标记上午/下午。"""

    result = data.copy()

    # time 只有时分秒而没有日期。to_timedelta 会把 09:30:00 表示成“从午夜
    # 起 9 小时 30 分”，避免 to_datetime 自动补一个与业务无关的日期。
    result["time_offset"] = pd.to_timedelta(result["time"], errors="raise")

    # 先创建可空字符串列，再用 loc 分段赋值。若未来出现集合竞价、午休或
    # 盘后数据，它们不会被误塞进上午/下午，而会暂时保持 <NA> 供检查。
    result["session"] = pd.Series(pd.NA, index=result.index, dtype="string")
    morning = result["time_offset"].between(
        pd.Timedelta("09:15:00"),
        pd.Timedelta("11:30:00"),
        inclusive="both",
    )
    afternoon = result["time_offset"].between(
        pd.Timedelta("13:00:00"),
        pd.Timedelta("15:00:00"),
        inclusive="both",
    )
    result.loc[morning, "session"] = "morning"
    result.loc[afternoon, "session"] = "afternoon"
    return result


def build_session_activity_table(timed: pd.DataFrame) -> pd.DataFrame:
    """先聚合成长表，再 pivot 成上午/下午对照表。"""

    activity_long = (
        timed.dropna(subset=["session"])
        .groupby(["stock_id", "session"], as_index=False, sort=True)
        .size()
        .rename(columns={"size": "record_count"})
    )

    # pivot 要求每个 stock_id + session 只有一个值；所以先 groupby 聚合。
    # 若原表仍有重复组合，可改用 pivot_table 并显式指定 aggfunc。
    activity_wide = activity_long.pivot(
        index="stock_id",
        columns="session",
        values="record_count",
    )
    return activity_wide.fillna(0).astype("int64").reset_index()


def count_updates_with_chunks(chunksize: int = 4) -> pd.Series:
    """逐块累计每只股票的记录数：这是适合 chunksize 的可加统计。"""

    total_counts = pd.Series(dtype="int64", name="record_count")

    # read_csv(..., chunksize=N) 返回 TextFileReader，而不是一个 DataFrame。
    # 每次循环只把最多 N 行载入内存。真实使用时把 StringIO 换成文件路径。
    with pd.read_csv(
        StringIO(EXAMPLE_MARKET_CSV),
        usecols=REQUIRED_COLUMNS,
        dtype=CSV_DTYPES,
        chunksize=chunksize,
    ) as reader:
        for chunk in reader:
            chunk_counts = chunk["stock_id"].value_counts(sort=False)

            # Series.add 会按 index（这里是 stock_id）对齐，而不是按物理位置
            # 相加。fill_value=0 让只在某一块出现的股票也能正确累计。
            total_counts = total_counts.add(chunk_counts, fill_value=0)

    return total_counts.astype("int64").sort_index()


def iter_complete_snapshot_batches(
    chunks: Iterable[pd.DataFrame],
) -> Iterator[pd.DataFrame]:
    """保留块尾的未完成 time，避免一个 snapshot 被拆成两次处理。

    前提：输入 CSV 已按 time 排列，并且相同 time 的行连续。若真实输入不满足
    这个前提，应先采用可扩展的外部排序方案，不能直接使用本函数。
    """

    carry: pd.DataFrame | None = None

    for raw_chunk in chunks:
        if raw_chunk.empty:
            continue

        # 上一块最后一个 time 的行，与当前块开头合并后再判断是否完整。
        combined = (
            raw_chunk
            if carry is None
            else pd.concat([carry, raw_chunk], ignore_index=True)
        )

        final_time = combined["time"].iloc[-1]
        is_final_time = combined["time"].eq(final_time)

        # 当前块最后一个 time 可能还会延续到下一块，因此暂不产出。
        complete = combined.loc[~is_final_time].copy()
        carry = combined.loc[is_final_time].copy()

        if not complete.empty:
            yield complete.reset_index(drop=True)

    # 文件结束后，最后一个 time 也终于完整。
    if carry is not None and not carry.empty:
        yield carry.reset_index(drop=True)


def snapshot_sizes_with_boundary_carry(chunksize: int = 3) -> pd.Series:
    """用块尾 carry 后的完整 snapshot 计算每个 time 的记录数。"""

    total_sizes = pd.Series(dtype="int64", name="record_count")
    with pd.read_csv(
        StringIO(EXAMPLE_MARKET_CSV),
        usecols=REQUIRED_COLUMNS,
        dtype=CSV_DTYPES,
        chunksize=chunksize,
    ) as reader:
        for complete_batch in iter_complete_snapshot_batches(reader):
            batch_sizes = complete_batch.groupby("time", sort=False).size()
            total_sizes = total_sizes.add(batch_sizes, fill_value=0)

    # 只保留按 time 聚合后的短 Series，不把所有 batch 再 concat 回内存；否则
    # 虽然读取时用了 chunksize，峰值内存最终仍会接近整份 CSV。
    return total_sizes.astype("int64").sort_index().rename("record_count")


def compare_memory_usage(data: pd.DataFrame, repeats: int = 1_000) -> pd.Series:
    """用 deep=True 比较重复字符串列与 category 的实际内存。"""

    # 小表的 category 元数据开销可能比节省的字符串还多，所以复制成一个仍然
    # 很小的教学规模再比较。真实项目始终应测量，不要假定 category 必然更省。
    repeated = pd.concat([data] * repeats, ignore_index=True)
    strings_bytes = int(repeated.memory_usage(index=True, deep=True).sum())

    compact = repeated.astype({"stock_id": "category", "time": "category"})
    category_bytes = int(compact.memory_usage(index=True, deep=True).sum())

    # category 只改变存储表示，不应改变业务值。分块读取时每块可能拥有不同
    # categories，跨块 concat/merge 前要额外留意 dtype 是否仍保持一致。
    return pd.Series(
        {
            "string_bytes": strings_bytes,
            "category_bytes": category_bytes,
        },
        dtype="int64",
    )


def main() -> int:
    data = load_example_market_data()
    timed = add_trading_session(data)
    activity_wide = build_session_activity_table(timed)
    chunk_counts = count_updates_with_chunks(chunksize=4)
    snapshot_sizes = snapshot_sizes_with_boundary_carry(chunksize=3)
    memory = compare_memory_usage(data)

    print("\n[1] time 解析和交易时段")
    print(
        timed[["time", "time_offset", "session"]]
        .drop_duplicates()
        .to_string(index=False)
    )

    print("\n[2] 上午/下午活跃度对照")
    print(activity_wide.to_string(index=False))

    print("\n[3] chunksize 分块累计记录数")
    print(chunk_counts.to_string())

    print("\n[4] 跨 chunk 保留完整 snapshot")
    print(snapshot_sizes.to_string())

    print("\n[5] 深度内存统计（字节）")
    print(memory.to_string())

    print(
        "\n边界提醒：value_counts 这类可加统计适合直接分块；"
        "全局排序、分位数和 snapshot 分组需要全局算法或显式维护跨块状态。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
