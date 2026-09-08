"""检查两只股票的 relative_clock 是否始终保持一致的严格先后顺序。

本脚本读取 ``build_relative_clock_vectors`` 保存的宽表 CSV。CSV 格式示例：

    stock_id,t1,t2,t3
    000001,0,0,
    000002,20,10,30

从 ``quant/`` 目录运行：

    python -m mds.relative_clock_order_check vectors.csv 000002 000001

上面的参数顺序表示检查：

    relative_clock(000002) - relative_clock(000001)

是否在两只股票共同出现的每个 snapshot 中始终同号。

缺失值的处理规则：

- 某个 snapshot 只有一只股票出现时，该维度没有可比较的差值，直接跳过；
- 如果两只股票没有任何共同 snapshot，结果是“证据不足”，不是 True；
- 全部差值严格大于 0，或者全部差值严格小于 0，判断都为 True；
- 如果差值中出现 0，或者正数和负数同时出现，判断为 False。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

FAILED_SNAPSHOT_DISPLAY_LIMIT = 20


def read_relative_clock_vectors(vectors_csv: Path | str) -> pd.DataFrame:
    """读取 ``vectors.to_csv(...)`` 生成的相对 clock 向量表。

    ``build_relative_clock_vectors`` 返回的 DataFrame 以 ``stock_id`` 为索引，
    因此直接调用 ``vectors.to_csv(...)`` 后，CSV 的第一列仍名为
    ``stock_id``。读取时必须把它指定为字符串，避免 ``000001`` 变成整数 1。

    后续 snapshot 列由 pandas 按数值读取。CSV 中的空单元格会保留为 NaN，
    表示该股票在相应 snapshot 没有记录；这里不会把它填成 0。
    """

    return pd.read_csv(
        vectors_csv,
        dtype={"stock_id": "string"},
    ).set_index("stock_id")


def check_relative_clock_order(
    vectors: pd.DataFrame,
    stock_a: str,
    stock_b: str,
) -> tuple[bool | None, pd.DataFrame]:
    """检查 ``stock_a - stock_b`` 在全部共同 snapshot 中是否严格同号。

    返回值由两部分组成：

    1. 判断结果：
       - ``True``：差值全部大于 0，或者全部小于 0；
       - ``False``：差值出现 0，或者正数和负数同时出现；
       - ``None``：没有任何共同 snapshot，无法判断。
    2. 逐 snapshot 明细，只保留两只股票都有值的共同 snapshot。

    单独返回明细是为了便于继续检查失败发生在哪些 snapshot；判断逻辑本身
    保持独立，后续也可以直接在其他 Python 脚本中调用。
    """

    # 先取出两只股票的向量，再转置。转置后每行对应一个 snapshot，两列分别
    # 是 stock_a 和 stock_b 的 relative_clock。
    pair_values = vectors.loc[[stock_a, stock_b]].T
    pair_values.columns = ["relative_clock_a", "relative_clock_b"]
    pair_values.index.name = "snapshot"

    # dropna() 默认要求一行中所有列都有值。因此，只要任一股票在该 snapshot
    # 缺失，这一行就不会进入差值计算。缺失不是 0，也不是顺序被违反。
    common_snapshots = pair_values.dropna().copy()
    common_snapshots["difference_a_minus_b"] = (
        common_snapshots["relative_clock_a"] - common_snapshots["relative_clock_b"]
    )

    # 分别记录每个差值是否严格大于 0、是否严格小于 0。差值等于 0 时，
    # 两个布尔值都会是 False，所以 0 不会被误判为任意一种符号。
    common_snapshots["is_strictly_positive"] = common_snapshots[
        "difference_a_minus_b"
    ].gt(0)
    common_snapshots["is_strictly_negative"] = common_snapshots[
        "difference_a_minus_b"
    ].lt(0)
    details = common_snapshots.reset_index()

    # Python/pandas 对空序列调用 all() 会得到 True，但在业务上，“没有共同
    # snapshot”只能说明没有证据，不能证明先后顺序恒成立，所以显式返回 None。
    if details.empty:
        return None, details

    # 符号一致有且只有两种情况：
    #
    # 1. 每个差值都严格大于 0，即 stock_a 的 relative_clock 始终更大；
    # 2. 每个差值都严格小于 0，即 stock_a 的 relative_clock 始终更小。
    #
    # 这里用 or 连接两个“全部满足”条件。正负号混合时两个 all() 都为
    # False；只要存在 0，对应那一侧的 all() 也会为 False。
    all_positive = bool(details["is_strictly_positive"].all())
    all_negative = bool(details["is_strictly_negative"].all())
    return all_positive or all_negative, details


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数。"""

    parser = argparse.ArgumentParser(
        description=(
            "检查 stock_a - stock_b 的 relative_clock 差值是否在全部共同 "
            "snapshot 中严格同号（全部大于 0 或全部小于 0）。"
        )
    )
    parser.add_argument("vectors_csv", type=Path, help="相对 clock 向量 CSV")
    parser.add_argument("stock_a", help="差值左侧的股票 ID")
    parser.add_argument("stock_b", help="差值右侧的股票 ID")
    return parser


def main(argv: list[str] | None = None) -> int:
    """读取向量 CSV、执行判断，并打印简洁的诊断信息。"""

    arguments = build_argument_parser().parse_args(argv)
    vectors = read_relative_clock_vectors(arguments.vectors_csv)
    result, details = check_relative_clock_order(
        vectors,
        arguments.stock_a,
        arguments.stock_b,
    )

    total_snapshot_count = vectors.shape[1]
    common_snapshot_count = len(details)
    skipped_snapshot_count = total_snapshot_count - common_snapshot_count

    print(f"比较方向：{arguments.stock_a} - {arguments.stock_b}")
    print(f"全部 snapshot 数：{total_snapshot_count}")
    print(f"共同 snapshot 数：{common_snapshot_count}")
    print(f"因任一股票缺失而跳过：{skipped_snapshot_count}")

    if result is None:
        print("判断结果：证据不足；两只股票没有共同 snapshot。")
        return 0

    minimum_difference = details["difference_a_minus_b"].min()
    maximum_difference = details["difference_a_minus_b"].max()
    positive_count = int(details["is_strictly_positive"].sum())
    negative_count = int(details["is_strictly_negative"].sum())
    zero_count = common_snapshot_count - positive_count - negative_count
    print(f"共同 snapshot 中的最小差值：{minimum_difference:g}")
    print(f"共同 snapshot 中的最大差值：{maximum_difference:g}")
    print(
        f"差值符号计数：正数 {positive_count}，负数 {negative_count}，零 {zero_count}"
    )

    if result:
        if positive_count == common_snapshot_count:
            print("判断结果：是；全部共同 snapshot 的差值都大于 0，符号一致为正。")
        else:
            print("判断结果：是；全部共同 snapshot 的差值都小于 0，符号一致为负。")
        return 0

    displayed_details = details.loc[
        :,
        [
            "snapshot",
            "relative_clock_a",
            "relative_clock_b",
            "difference_a_minus_b",
        ],
    ]
    print("判断结果：否；差值出现 0，或者正数和负数同时出现。")
    print(
        f"前 {min(len(displayed_details), FAILED_SNAPSHOT_DISPLAY_LIMIT)} 条共同 "
        "snapshot 明细："
    )
    print(displayed_details.head(FAILED_SNAPSHOT_DISPLAY_LIMIT).to_string(index=False))
    if len(displayed_details) > FAILED_SNAPSHOT_DISPLAY_LIMIT:
        print(
            f"其余 {len(displayed_details) - FAILED_SNAPSHOT_DISPLAY_LIMIT} 条"
            "未在终端展开。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
