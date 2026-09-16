"""用 pandas + Matplotlib 展示 snapshot 中交错的股票顺序。

输入 CSV 只读取 stock_id、time；相同 time 属于同一 snapshot，组内保留
CSV 原始行序。stock_id 为整数。图片不读取 group_id，也不预设分组数。

从 quant 目录运行：
    python mds/report/script/plot_snapshot_order.py INPUT.csv OUTPUT.png
    python mds/report/script/plot_snapshot_order.py INPUT.csv OUTPUT.png \
        --snapshots 1 1000 2000 --zoom-stocks 200

snapshot 编号从 1 开始，按 time 在文件中首次出现的顺序计数。
上排展示完整 snapshot；下排放大 ID 最小的若干只股票。
纵轴用全文件股票按 ID 升序的名次，消除代码数值间的大空隙。
多条交错的递增轨迹可提示多个组，但局部轨迹数量不是固定组数的证明。
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd


def plot_snapshot_order(
    input_csv: Path,
    output_image: Path,
    snapshot_numbers: list[int] | None = None,
    zoom_stocks: int = 200,
):
    data = pd.read_csv(
        input_csv,
        usecols=["stock_id", "time"],
        dtype={"stock_id": "int64", "time": "string"},
    )
    # sort=True 只排序股票字典，不改变记录顺序；相同股票始终使用同一名次。
    data["stock_rank"], stock_ids = pd.factorize(data["stock_id"], sort=True)
    data["stock_rank"] += 1
    snapshots = data.groupby("time", sort=False)
    sizes = snapshots.size()
    if data.empty:
        raise ValueError("The input CSV contains no records.")
    if snapshot_numbers is None:
        snapshot_numbers = list(range(1, min(3, len(sizes)) + 1))
    if not snapshot_numbers or any(n < 1 or n > len(sizes) for n in snapshot_numbers):
        raise ValueError(f"Snapshot numbers must be between 1 and {len(sizes)}.")
    if zoom_stocks < 1:
        raise ValueError("zoom_stocks must be positive.")

    zoom_limit = min(zoom_stocks, len(stock_ids))
    fig, axes = plt.subplots(
        2, len(snapshot_numbers),
        figsize=(5 * len(snapshot_numbers), 8.5),
        squeeze=False,
    )
    fig.suptitle("Stock arrival order within snapshots", fontsize=17, y=0.98)
    fig.text(
        0.5, 0.935,
        f"{len(sizes):,} snapshots | {len(data):,} records | "
        f"{len(stock_ids):,} stocks | One dot per record; no group labels",
        ha="center", fontsize=10, color="#475569",
    )

    for column, number in enumerate(snapshot_numbers):
        time_value = sizes.index[number - 1]
        part = snapshots.get_group(time_value).reset_index(drop=True)
        # 横轴是本轮原始到达位置，不按股票排序，避免人为生成递增轨迹。
        part["position"] = part.index + 1
        zoom = part.loc[part["stock_rank"] <= zoom_limit]
        for row, points in enumerate([part, zoom]):
            ax = axes[row, column]
            ax.scatter(
                points["position"], points["stock_rank"],
                s=5 if row == 0 else 13,
                color="#25618B", alpha=0.85, linewidths=0, rasterized=True,
            )
            ax.set_xlabel("Arrival position within snapshot")
            ax.set_ylabel("Stock rank (ascending stock_id)")
            ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
            ax.grid(alpha=0.2, linewidth=0.6)
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)

        axes[0, column].set_title(
            f"Snapshot {number:,} | {len(part):,} records\ntime = {time_value}",
            fontsize=11, pad=10,
        )
        axes[0, column].set_xlim(0, len(part) + 1)
        axes[0, column].set_ylim(0, len(stock_ids) + 1)
        axes[1, column].set_title(
            f"Detail: the {zoom_limit:,} lowest-ID stocks", fontsize=11, pad=10,
        )
        axes[1, column].set_ylim(0, zoom_limit + 1)
        if zoom.empty:
            axes[1, column].text(
                0.5, 0.5, "No selected stocks in this snapshot",
                transform=axes[1, column].transAxes, ha="center", va="center",
            )
        else:
            axes[1, column].set_xlim(0, int(zoom["position"].max()) + 3)

    fig.text(
        0.5, 0.025,
        "Separate rising tracks suggest interleaved ordered streams. "
        "Visual patterns alone do not establish the number of fixed groups.",
        ha="center", fontsize=9, color="#475569", wrap=True,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.905), h_pad=2.2, w_pad=2.2)
    output_image.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_image, dpi=240, facecolor="white")
    plt.close(fig)
    print(f"Read {len(data):,} records in {len(sizes):,} snapshots.")
    print(f"Plotted snapshots: {snapshot_numbers}")
    print(f"Saved: {output_image.resolve()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_image", type=Path)
    parser.add_argument(
        "--snapshots", type=int, nargs="+",
        help="1-based snapshot numbers in first-appearance order (default: first 3).",
    )
    parser.add_argument("--zoom-stocks", type=int, default=200)
    args = parser.parse_args()
    plot_snapshot_order(
        args.input_csv, args.output_image, args.snapshots, args.zoom_stocks,
    )


if __name__ == "__main__":
    main()
