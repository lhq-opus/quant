"""第一课：DataFrame / Series、CSV 读取、筛选和数据质量检查。

运行方式（先进入 ``quant/`` 目录）：

    python -m mds.study.pandas_01_io_selection

这份脚本使用内存字符串模拟 CSV，因此可以放心反复运行。示例的字段和 MDS
一致，但数据只是为了教学，不表示真实股票组或真实时间分布。
"""

from __future__ import annotations

from io import StringIO

import pandas as pd

REQUIRED_COLUMNS = ["clock", "stock_id", "time"]

# 故意保留 exchange 和 last_price 两个额外行情列，用来演示 usecols 如何只读
# MDS 算法真正允许使用的 clock、stock_id、time。
# 同一个 time 的行连续出现，但 snapshot 内的 clock 顺序被故意打乱。
EXAMPLE_MARKET_CSV = """clock,stock_id,exchange,time,last_price
1000035,600000,SH,09:30:00,10.10
1010000,600001,SH,09:30:00,11.20
1000000,000001,SZ,09:30:00,8.30
1000020,000002,SZ,09:30:00,7.40
2000000,000002,SZ,09:30:03,7.50
2010000,600001,SH,09:30:03,11.30
2000025,000001,SZ,09:30:03,8.40
3000030,000001,SZ,13:00:00,8.50
3010000,600001,SH,13:00:00,11.40
3000000,600000,SH,13:00:00,10.20
4000000,000003,SZ,13:00:03,6.00
4000020,000001,SZ,13:00:03,8.60
"""


def load_example_market_data() -> pd.DataFrame:
    """读取教学 CSV，并显式控制列和 dtype。"""

    # StringIO 把字符串包装成一个“像文件一样”的对象。真实项目里把第一个
    # 参数换成 Path 或 CSV 文件名即可，其他参数不需要改变。
    data = pd.read_csv(
        StringIO(EXAMPLE_MARKET_CSV),
        # usecols 不只节省内存，也把“算法只依赖三列”写进代码。
        usecols=REQUIRED_COLUMNS,
        dtype={
            # clock 是整数微秒时间戳。数据保证无缺失时用 int64 最紧凑。
            "clock": "int64",
            # 股票 ID 不是用来运算的数字。读成 string 才会保留 000001 的前导零。
            "stock_id": "string",
            # time 是交易所 snapshot 标识，此处先保留原始文本，第四课再解析。
            "time": "string",
        },
    )
    return data


def example_series_and_dataframe(data: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """演示单中括号和双中括号返回不同类型。"""

    # 单中括号选择一列，返回一维 Series。Series 有自己的 index、name 和 dtype。
    stock_series = data["stock_id"]

    # 双中括号接收“列名列表”，哪怕只选一列也返回二维 DataFrame。
    stock_frame = data[["stock_id"]]

    # 经验法则：准备继续做字符串/数值运算时常用 Series；需要把结果交给要求
    # 表结构的函数，或需要保留二维形状时用 DataFrame。
    return stock_series, stock_frame


def example_select_rows(data: pd.DataFrame) -> pd.DataFrame:
    """用布尔条件和 loc 选择一个 snapshot 中的部分列。"""

    is_first_snapshot = data["time"].eq("09:30:00")
    is_shenzhen_stock = data["stock_id"].str.startswith("0")

    # 多个条件要分别放进括号，再用 &（且）或 |（或）连接。不能写 Python 的
    # ``and`` / ``or``，因为这里比较的是一整列，而不是单个 True/False。
    selected = data.loc[
        is_first_snapshot & is_shenzhen_stock,
        ["time", "stock_id", "clock"],
    ].copy()

    # .loc 按“行标签/条件、列标签”选取；.iloc 则按整数位置选取。
    # selected.iloc[0] 是第一行，selected.iloc[:2, :2] 是前两行前两列。
    return selected


def example_safe_assignment(data: pd.DataFrame) -> pd.DataFrame:
    """演示 copy、assign 和 loc 赋值，避免链式赋值。"""

    # 筛选后准备修改时主动 copy，意思很明确：下面修改的是独立结果，不希望
    # 影响原 DataFrame。pandas 3 的 Copy-on-Write 下尤其不应依赖链式赋值。
    annotated = data.copy()

    # assign 很适合根据已有列创建新列，并返回新的 DataFrame。
    annotated = annotated.assign(clock_ms=annotated["clock"] / 1_000)

    # 修改部分行时，把行条件和列名一次性交给 loc。
    # 不要写 annotated["snapshot_label"][mask] = ...；那是链式赋值。
    annotated["snapshot_label"] = "other"
    first_snapshot = annotated["time"].eq("09:30:00")
    annotated.loc[first_snapshot, "snapshot_label"] = "opening_example"
    return annotated


def example_data_quality_report(
    data: pd.DataFrame,
) -> tuple[pd.Series, pd.DataFrame]:
    """构造坏数据，演示 isna 和 duplicated 如何定位问题。"""

    # pandas 的 ``Int64``（首字母大写）是“可空整数”；普通 ``int64`` 不能
    # 表示 pd.NA。这里仅为演示主动构造一条 clock 缺失记录。
    dirty = data.astype({"clock": "Int64"}).copy()
    dirty.loc[1, "clock"] = pd.NA

    # concat 用来沿行方向拼接。ignore_index=True 会生成连续的新索引。
    dirty = pd.concat([dirty, dirty.iloc[[0]]], ignore_index=True)

    # isna() 先逐单元格产生布尔值，再按列 sum()；True 会按 1 计数。
    missing_counts = dirty[REQUIRED_COLUMNS].isna().sum()

    # keep=False 会把一组重复记录中的每一行都标出来，方便一起检查。
    # 是否允许同一 time + stock_id 多行目前仍是业务未决问题，所以这里只检查
    # 三个输入字段完全相同的记录，不擅自把可能合法的多次更新删除。
    duplicate_mask = dirty.duplicated(subset=REQUIRED_COLUMNS, keep=False)
    duplicate_rows = dirty.loc[duplicate_mask, REQUIRED_COLUMNS]

    # 生产代码通常应先报告或抛错，再由业务规则决定 dropna/drop_duplicates；
    # 不要为了“让代码跑通”而静默删除无法解释的 market data。
    return missing_counts, duplicate_rows


def example_numeric_conversion() -> pd.Series:
    """演示 to_numeric 对外部文本数据做严格数值转换。"""

    raw_clock = pd.Series(["1000000", "1000020", "1010000"], dtype="string")

    # errors="raise" 遇到 "not-a-number" 会直接报错，适合 clock 这种必须为
    # 数值的字段；errors="coerce" 会改成缺失值，可能掩盖输入错误。
    return pd.to_numeric(raw_clock, errors="raise").astype("int64")


def example_write_csv(data: pd.DataFrame) -> str:
    """把结果写入内存 CSV，演示 index=False 和 columns。"""

    output = StringIO()
    data.to_csv(
        output,
        # DataFrame 的行索引通常只是 pandas 内部编号，不属于业务字段。
        # index=False 可避免输出一列无名的 0,1,2...。
        index=False,
        # columns 同时限制并固定输出列顺序。
        columns=REQUIRED_COLUMNS,
    )
    return output.getvalue()


def main() -> int:
    """顺序运行本课所有例子，并把关键结果打印出来。"""

    data = load_example_market_data()
    stock_series, stock_frame = example_series_and_dataframe(data)
    selected = example_select_rows(data)
    annotated = example_safe_assignment(data)
    missing_counts, duplicate_rows = example_data_quality_report(data)
    parsed_clock = example_numeric_conversion()
    output_csv = example_write_csv(data.head(2))

    print("\n[1] 读取后的形状、列名和 dtype")
    print("shape:", data.shape)
    print("columns:", data.columns.tolist())
    print(data.dtypes)

    print("\n[2] Series 与 DataFrame 的维度")
    print("Series ndim/shape:", stock_series.ndim, stock_series.shape)
    print("DataFrame ndim/shape:", stock_frame.ndim, stock_frame.shape)

    print("\n[3] loc 条件筛选结果")
    print(selected.to_string(index=False))

    print("\n[4] assign + loc 创建的教学标签")
    print(annotated.head(4).to_string(index=False))

    print("\n[5] 缺失计数与完全重复行")
    print(missing_counts.to_string())
    print(duplicate_rows.to_string(index=False))

    print("\n[6] 严格转换后的 clock")
    print(parsed_clock.to_list())

    print("\n[7] to_csv(index=False) 的前两条记录")
    print(output_csv.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
