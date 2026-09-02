"""Calculate and inspect adjacent clock differences in market data CSV files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Sequence

import pandas as pd
from pandas.api.types import is_integer_dtype, is_unsigned_integer_dtype


REQUIRED_COLUMNS = ("clock", "stock_id", "time")
OUTPUT_COLUMNS = ("stock_id", "delta_clock")
MAX_INT64 = 2**63 - 1
DEFAULT_ROBUST_Z_THRESHOLD = 6.0
DEFAULT_MIN_SLOPE_MULTIPLIER = 5.0
DEFAULT_MIN_SEGMENT_SIZE = 2
MIN_BASELINE_SLOPES = 3
MAD_TO_STANDARD_DEVIATION = 1.4826


@dataclass(frozen=True)
class AbruptIncrease:
    """保存一个异常跃升候选点及其解释信息。

    例如排序值为 ``20, 30, 35, 10000, 11000`` 时：

    - ``delta_clock`` 是跃升后的值 ``10000``，也就是用户关心的候选点；
    - ``previous_delta_clock`` 是跃升前的值 ``35``；
    - ``slope`` 是两者之差 ``10000 - 35 = 9965``；
    - 其余字段描述这条斜率为什么被算法认为异常。
    """

    delta_clock: int
    previous_delta_clock: int
    slope: int
    slope_threshold: float
    robust_z_score: float
    slope_multiplier: float
    lower_count: int
    upper_count: int


def calculate_clock_deltas(data: pd.DataFrame) -> pd.DataFrame:
    """Return ``stock_id`` and the adjacent ``clock`` difference.

    Input row order is preserved. The first delta is zero. Every later delta is
    also zero when its ``time`` differs from the preceding row; otherwise it is
    the current ``clock`` minus the preceding row's ``clock``.
    """

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"missing required CSV column(s): {missing}")

    if data["stock_id"].isna().any():
        raise ValueError("stock_id contains missing values")
    if data["time"].isna().any():
        raise ValueError("time contains missing values")
    if data["clock"].isna().any():
        raise ValueError("clock contains missing values")

    if data.empty:
        return pd.DataFrame(
            {
                "stock_id": data["stock_id"].copy(),
                "delta_clock": pd.Series(index=data.index, dtype="int64"),
            }
        )

    try:
        clock = pd.to_numeric(data["clock"], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError("clock must contain integer microsecond timestamps") from error

    if not is_integer_dtype(clock.dtype):
        raise ValueError("clock must contain integer microsecond timestamps")
    if is_unsigned_integer_dtype(clock.dtype) and clock.max() > MAX_INT64:
        raise ValueError("clock contains a value outside the signed 64-bit range")

    clock = clock.astype("int64")
    previous_clock = clock.shift(1, fill_value=clock.iloc[0])
    same_time_as_previous = data["time"].eq(data["time"].shift(1)).fillna(False)
    delta_clock = (
        clock.sub(previous_clock)
        .where(same_time_as_previous, other=0)
        .astype("int64")
    )

    return pd.DataFrame(
        {
            "stock_id": data["stock_id"].copy(),
            "delta_clock": delta_clock,
        }
    )


def sort_clock_deltas(data: pd.DataFrame) -> pd.DataFrame:
    """Return rows stably sorted by ``delta_clock`` in ascending order."""

    if "delta_clock" not in data:
        raise ValueError("missing required column: delta_clock")

    return data.sort_values("delta_clock", kind="stable", ignore_index=True)


def find_abrupt_increase(
    data: pd.DataFrame,
    *,
    robust_z_threshold: float = DEFAULT_ROBUST_Z_THRESHOLD,
    min_slope_multiplier: float = DEFAULT_MIN_SLOPE_MULTIPLIER,
    min_segment_size: int = DEFAULT_MIN_SEGMENT_SIZE,
) -> AbruptIncrease | None:
    """在排序后的正 ``delta_clock`` 中寻找第一个异常跃升点。

    可以把排序值画成一条曲线：横轴是排序位置，纵轴是
    ``delta_clock``。相邻两个纵轴值的差就是这里所说的“斜率”。如果
    大部分斜率很小、某一条斜率突然非常大，该斜率右侧的值就是候选点。

    例如 ``20, 30, 35, 10000, 11000`` 的斜率依次是
    ``10, 5, 9965, 1000``。``9965`` 明显偏大，所以返回它右侧的
    ``10000``，而不是返回斜率本身或左侧的 ``35``。

    检测分为四步：

    1. 只保留正值并排序；
    2. 计算相邻排序值之间的正斜率；
    3. 用 median（中位数）和 MAD（中位绝对偏差）估计正常斜率范围；
    4. 返回第一个同时超过统计门槛和倍率门槛、且两侧样本充足的点。

    返回值只是探索数据分布的候选点，不代表已经证明这里是真实组间边界。
    """

    # 先检查参数，避免 NaN、无穷大或没有实际意义的门槛悄悄进入计算。
    # robust_z_threshold 可以为 0，但不能为负；倍率必须大于 1，否则
    # “异常斜率”甚至可能不需要大于普通斜率。
    if not isfinite(robust_z_threshold) or robust_z_threshold < 0:
        raise ValueError("robust_z_threshold must be finite and non-negative")
    if not isfinite(min_slope_multiplier) or min_slope_multiplier <= 1:
        raise ValueError("min_slope_multiplier must be finite and greater than 1")
    if min_segment_size < 1:
        raise ValueError("min_segment_size must be at least 1")
    if "delta_clock" not in data:
        raise ValueError("missing required column: delta_clock")

    # 即使调用者传入的是字符串列，也先尝试转换成数值。这里要求整数，
    # 因为 clock 和 delta_clock 的业务单位都是整数微秒。
    try:
        delta_clock = pd.to_numeric(data["delta_clock"], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError("delta_clock must contain integer values") from error

    if delta_clock.isna().any() or not is_integer_dtype(delta_clock.dtype):
        raise ValueError("delta_clock must contain integer values")
    if is_unsigned_integer_dtype(delta_clock.dtype) and delta_clock.max() > MAX_INT64:
        raise ValueError("delta_clock contains a value outside the signed 64-bit range")

    # 只用正值判断分布拐点：
    #
    # - 0 是 calculate_clock_deltas 在首行和 time 切换处写入的边界标记，
    #   并不表示两条真实记录之间存在 0 微秒间隔；
    # - 负值表示 CSV 物理行中的 clock 向后跳了，它可以保留在输出中供
    #   排查输入顺序，但不能拿来估计“正时间间隔突然增大”的位置。
    #
    # find_abrupt_increase 自己执行排序，因此调用者不必预先排序 DataFrame。
    positive_deltas = (
        delta_clock.loc[delta_clock.gt(0)]
        .astype("int64")
        .sort_values(kind="stable")
        .reset_index(drop=True)
    )

    # 一个候选点会把数据切成“候选点左侧”和“候选点及其右侧”两部分。
    # 两部分都至少要有 min_segment_size 个样本，否则一个孤立的最大值
    # 就可能被误当成稳定的新数据区间。默认值 2 会拒绝只有一个尾部值的
    # 情形，但仍能处理用户给出的 3 个小值 + 2 个大值示例。
    if len(positive_deltas) < 2 * min_segment_size:
        return None

    # diff() 计算“当前排序值 - 前一个排序值”。第一个值没有前驱，所以
    # 第一条 slope 是 NaN。仍以示例为例：
    #
    # delta_clock: 20, 30, 35, 10000, 11000
    # slope:       NaN, 10,  5,  9965,  1000
    slopes = positive_deltas.diff()

    # 重复的 delta_clock 会产生 slope=0。零斜率只说明出现了重复取值，
    # 不能描述“正常的正向增长幅度”，所以计算背景水平时只使用正斜率。
    positive_slopes = slopes.loc[slopes.gt(0)]

    # 至少需要若干条正斜率才能谈“普通水平”和“异常值”。样本太少时返回
    # None 比根据一两个差值强行猜测更诚实。
    if len(positive_slopes) < MIN_BASELINE_SLOPES:
        return None

    # median_slope 是所有正斜率从小到大排列后的中间水平。这里不用平均数，
    # 是因为一个极大的候选斜率会明显拉高平均数，却不容易拉偏中位数。
    #
    # MAD 的全称是 Median Absolute Deviation：
    #   1. 先计算每条斜率与 median_slope 相差多少；
    #   2. 再取这些绝对差的中位数。
    #
    # 因而 MAD 可以直观理解为“普通斜率通常离中间水平有多远”，同样不
    # 容易被少数极端斜率带偏。
    median_slope = float(positive_slopes.median())
    median_absolute_deviation = float(
        positive_slopes.sub(median_slope).abs().median()
    )

    # 1.4826 是常见的换算系数：当普通斜率近似正态分布时，
    # 1.4826 * MAD 与标准差处在相近尺度。无需把它理解成业务常数；它只
    # 是为了让 robust_z_threshold=6 大致表达“偏离普通水平很多倍”。
    robust_scale = MAD_TO_STANDARD_DEVIATION * median_absolute_deviation

    # 统计门槛：普通中间水平 + 指定倍数的稳健波动尺度。
    robust_threshold = median_slope + robust_z_threshold * robust_scale

    # 倍率门槛：候选斜率还必须至少达到普通正斜率中位数的指定倍数。
    # 这一层尤其用于 MAD=0 的情况。例如大量普通斜率都等于 10 时，
    # MAD 会是 0；单靠上面的统计门槛会让任何大于 10 的值都通过，而
    # 默认的 5 倍门槛会要求它至少大于 50。
    multiplier_threshold = median_slope * min_slope_multiplier

    # 取两个门槛中更严格的一个，等价于要求候选同时通过两项检查。
    slope_threshold = max(robust_threshold, multiplier_threshold)

    # position 是候选“右侧值”在 positive_deltas 中的位置，也是它左侧
    # 的样本数。例如 10000 位于示例中的位置 3，因此左侧有 3 个样本；
    # 总共 5 个样本，所以从 10000 开始的右侧有 5 - 3 = 2 个样本。
    positions = pd.Series(range(len(positive_deltas)), index=positive_deltas.index)
    eligible = (
        # 条件一：当前斜率确实超过上面得到的最终门槛。
        slopes.gt(slope_threshold)
        # 条件二、三：切分点左右都有足够样本，不信任孤立的两端值。
        & positions.ge(min_segment_size)
        & positions.le(len(positive_deltas) - min_segment_size)
    )
    candidate_positions = positions.loc[eligible]
    if candidate_positions.empty:
        return None

    # positions 按 delta_clock 从小到大排列，因此取第一个候选，得到的就是
    # “第一个突然增大的点”。这与简单取全局最大斜率不同：如果后面还有
    # 更大的第二次跃升，我们仍优先返回更早出现的尺度变化。
    position = int(candidate_positions.iloc[0])
    slope = int(slopes.iloc[position])

    # robust_z_score 只用于解释候选有多突出。当 MAD=0 时，稳健波动尺度
    # 也是 0，普通除法没有定义；用 inf 表示候选相对零波动背景无限突出。
    # 这不是计算错误，最终是否入选仍已经受到倍率门槛约束。
    if robust_scale == 0:
        robust_z_score = float("inf")
    else:
        robust_z_score = (slope - median_slope) / robust_scale

    # 返回跃升后的 delta_clock，同时带回跃升前值、斜率、门槛和两侧样本
    # 数，方便 CLI 或后续代码解释“为什么选中了这个点”。
    return AbruptIncrease(
        delta_clock=int(positive_deltas.iloc[position]),
        previous_delta_clock=int(positive_deltas.iloc[position - 1]),
        slope=slope,
        slope_threshold=slope_threshold,
        robust_z_score=robust_z_score,
        slope_multiplier=slope / median_slope,
        lower_count=position,
        upper_count=len(positive_deltas) - position,
    )


def process_csv(
    input_csv: Path | str,
    output_csv: Path | str,
    *,
    robust_z_threshold: float = DEFAULT_ROBUST_Z_THRESHOLD,
    min_slope_multiplier: float = DEFAULT_MIN_SLOPE_MULTIPLIER,
    min_segment_size: int = DEFAULT_MIN_SEGMENT_SIZE,
) -> AbruptIncrease | None:
    """Calculate deltas, sort the output, detect a jump, and write the CSV."""

    data = pd.read_csv(
        input_csv,
        usecols=list(REQUIRED_COLUMNS),
        dtype={"clock": "string", "stock_id": "string", "time": "string"},
    )
    result = sort_clock_deltas(calculate_clock_deltas(data))
    abrupt_increase = find_abrupt_increase(
        result,
        robust_z_threshold=robust_z_threshold,
        min_slope_multiplier=min_slope_multiplier,
        min_segment_size=min_segment_size,
    )
    result.to_csv(output_csv, columns=list(OUTPUT_COLUMNS), index=False)
    return abrupt_increase


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate each row's clock difference from the preceding input row. "
            "Sort the output by delta_clock and report the first anomalous "
            "increase. The delta is zero for the first row and whenever time "
            "changes."
        )
    )
    parser.add_argument("input_csv", type=Path, help="source market data CSV")
    parser.add_argument("output_csv", type=Path, help="destination CSV")
    parser.add_argument(
        "--robust-z-threshold",
        type=float,
        default=DEFAULT_ROBUST_Z_THRESHOLD,
        help="MAD-based slope anomaly threshold (default: %(default)s)",
    )
    parser.add_argument(
        "--min-slope-multiplier",
        type=float,
        default=DEFAULT_MIN_SLOPE_MULTIPLIER,
        help="minimum slope divided by the median positive slope (default: %(default)s)",
    )
    parser.add_argument(
        "--min-segment-size",
        type=int,
        default=DEFAULT_MIN_SEGMENT_SIZE,
        help="minimum positive delta count on each side (default: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)

    try:
        abrupt_increase = process_csv(
            arguments.input_csv,
            arguments.output_csv,
            robust_z_threshold=arguments.robust_z_threshold,
            min_slope_multiplier=arguments.min_slope_multiplier,
            min_segment_size=arguments.min_segment_size,
        )
    except (OSError, ValueError) as error:
        parser.exit(status=1, message=f"error: {error}\n")

    if abrupt_increase is None:
        print("No abrupt delta_clock increase detected.")
    else:
        print(
            "Detected abrupt delta_clock increase: "
            f"value={abrupt_increase.delta_clock}, "
            f"previous={abrupt_increase.previous_delta_clock}, "
            f"slope={abrupt_increase.slope}, "
            f"robust_z={abrupt_increase.robust_z_score:.2f}, "
            f"slope_multiplier={abrupt_increase.slope_multiplier:.2f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
