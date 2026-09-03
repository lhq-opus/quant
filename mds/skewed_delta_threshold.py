#!/usr/bin/env python3
"""从排序后的 ``delta_clock`` 长尾中寻找一个简单候选阈值。"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


DELTA_COLUMN = "delta_clock"

# 用户提供的数据分布中，组间 gap 只占最后一小部分。
# 因此只在“尾部占 0.5% 到 5%”的区域寻找折点，不扫描整条曲线。
MIN_TAIL_FRACTION = 0.005
MAX_TAIL_FRACTION = 0.05

# 从 90% 分位开始观察，可以跳过前面大量小于 20 微秒的密集值。
# 最顶部 0.05% 不参与拟合，避免极少数超大值把斜率拉得过高。
ANALYSIS_START_QUANTILE = 0.90
ANALYSIS_END_QUANTILE = 0.9995
QUANTILE_POINT_COUNT = 4096

# 对每个候选点，分别使用左边和右边 0.2% 的数据估计局部斜率。
LOCAL_WINDOW_FRACTION = 0.002


def _linear_slope(x: np.ndarray, y: np.ndarray) -> float:
    """计算一组点的最小二乘直线斜率。"""

    centered_x = x - x.mean()
    centered_y = y - y.mean()
    return float((centered_x @ centered_y) / (centered_x @ centered_x))


def estimate_skewed_threshold(data: pd.DataFrame) -> int:
    """寻找排序曲线进入最后一小段快速长尾的位置。

    这版 baseline 只做五件事：

    1. 取出正 ``delta_clock`` 并排序；0 是 snapshot 边界，不参与分析；
    2. 在排序位置 90% 到 99.95% 之间等距取样；
    3. 对数化纵轴，降低最大几个 gap 对斜率的支配；
    4. 在尾部占 0.5% 到 5% 的范围内，比较候选点左右局部斜率；
    5. 返回“右斜率 / 左斜率”最大位置对应的 ``delta_clock``。

    返回值只是适合第一版实验的候选阈值，不代表已经证明了真实组间边界。
    """

    # clock_delta.py 会在每个新 time 的第一行产生 0；这些值不是股票间
    # 的真实到达间隔，因此只保留正值。输入格式固定，不再重复做类型、
    # 缺失值和整数范围等防御性检查。
    sorted_values = np.sort(
        data.loc[data[DELTA_COLUMN] > 0, DELTA_COLUMN].to_numpy(dtype="int64")
    )

    # 用排序位置而不是 unique 值取样，才能保留“小 gap 出现很多次”这一
    # 频数信息。rank_indices 指向原始排序数组中的实际观测值。
    quantiles = np.linspace(
        ANALYSIS_START_QUANTILE,
        ANALYSIS_END_QUANTILE,
        QUANTILE_POINT_COUNT,
    )
    rank_indices = (quantiles * (len(sorted_values) - 1)).astype("int64")
    curve = np.log1p(sorted_values[rank_indices])

    quantile_step = quantiles[1] - quantiles[0]
    window_points = int(LOCAL_WINDOW_FRACTION / quantile_step)

    # 候选折点 q 的右侧比例 1-q 就是尾部占比。这里只检查用户认为合理的
    # 小尾部范围，并为左右局部窗口各留出足够位置。
    first_candidate = np.searchsorted(
        quantiles,
        1 - MAX_TAIL_FRACTION,
    )
    last_candidate = np.searchsorted(
        quantiles,
        1 - MIN_TAIL_FRACTION,
    )
    first_candidate = max(first_candidate, window_points)
    last_candidate = min(last_candidate, len(quantiles) - window_points)

    best_index = first_candidate
    best_slope_ratio = -1.0

    for index in range(first_candidate, last_candidate):
        left_slice = slice(index - window_points, index)
        right_slice = slice(index, index + window_points)

        left_slope = _linear_slope(
            quantiles[left_slice],
            curve[left_slice],
        )
        right_slope = _linear_slope(
            quantiles[right_slice],
            curve[right_slice],
        )

        # 1e-12 只用于避免左侧曲线完全水平时除以 0。
        slope_ratio = right_slope / (left_slope + 1e-12)
        if slope_ratio > best_slope_ratio:
            best_slope_ratio = slope_ratio
            best_index = index

    return int(sorted_values[rank_indices[best_index]])


def process_csv(input_csv: Path | str, output_csv: Path | str) -> int:
    """读取 ``delta_clock``，估计阈值，并写出一行 CSV。"""

    # 上游 clock_delta.py 的输出格式固定，这里只读取所需列。
    data = pd.read_csv(
        input_csv,
        usecols=[DELTA_COLUMN],
        dtype={DELTA_COLUMN: "int64"},
    )
    threshold = estimate_skewed_threshold(data)
    pd.DataFrame({"threshold": [threshold]}).to_csv(output_csv, index=False)
    return threshold


def build_argument_parser() -> argparse.ArgumentParser:
    """创建最小化的命令行参数。"""

    parser = argparse.ArgumentParser(
        description="寻找 delta_clock 排序曲线进入最后一小段长尾的位置。"
    )
    parser.add_argument("input_csv", type=Path, help="包含 delta_clock 的输入 CSV")
    parser.add_argument("output_csv", type=Path, help="保存 threshold 的输出 CSV")
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行命令行程序并打印候选阈值。"""

    arguments = build_argument_parser().parse_args(argv)
    threshold = process_csv(arguments.input_csv, arguments.output_csv)
    print(f"检测到的 delta_clock 候选阈值：{threshold} 微秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
