"""第六课：用 Bokeh 观察 MDS 的 clock、向量和股票关系矩阵。

从 ``quant/`` 目录运行：

    python -m mds.study.bokeh_06_mds_visualization

默认会生成 ``mds/study/mds_bokeh_visualization.html``。也可以指定路径：

    python -m mds.study.bokeh_06_mds_visualization /tmp/mds_bokeh.html

Bokeh 生成的 HTML 可以直接用浏览器打开。图中的缩放、平移、悬停提示、图例
隐藏等交互都在浏览器内完成，不需要启动 Python Web 服务。

本课从一个极小的折线/散点图开始，然后覆盖 MDS 最常见的三种观察场景：

1. 单个 ``time``（snapshot）内，各股票按 ``clock`` 到达的先后和间隔；
2. 每只股票跨多个 snapshot 的相对 ``clock`` 向量；
3. V1 匹配率或 V2 余弦相似度这类 ``stock_id × stock_id`` 关系矩阵。

所有 market data 都在内存中生成，只使用 ``clock``、``stock_id``、``time``。
示例分组标签只用于把热图的行排在一起，绝不会作为待测分组算法的输入。
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from bokeh.io import output_file, save
from bokeh.layouts import column, gridplot
from bokeh.models import ColorBar, ColumnDataSource, Div, LinearColorMapper
from bokeh.palettes import Category10, Viridis256
from bokeh.plotting import figure
from bokeh.transform import factor_cmap

REQUIRED_COLUMNS = ["clock", "stock_id", "time"]
# 教程命令约定从 quant/ 运行。默认 HTML 放在允许写入且已忽略的 mds/study/
# 目录，而不是写到仓库根目录。
DEFAULT_OUTPUT_HTML = Path("mds/study/mds_bokeh_visualization.html")

# 这份 mock 刻意包含三种现象：
#
# - 同一组股票通常只相差几十微秒；
# - 不同组通常相差约 10,000 微秒；
# - 在 09:30:09，示例组 A 和 B 偶然几乎同时推送，形成一次跨组近时碰撞；
# - 若股票在某个 snapshot 没有更新，那一维就缺失，而不是 0。
#
# 每个 snapshot 内的 clock 已按升序排列，符合当前相对 clock 向量脚本的前提。
EXAMPLE_MDS_RECORDS = [
    (1_000_000, "000001", "09:30:00"),
    (1_000_025, "000002", "09:30:00"),
    (1_010_000, "600000", "09:30:00"),
    (1_010_030, "600001", "09:30:00"),
    (1_022_000, "300001", "09:30:00"),
    (2_000_010, "000001", "09:30:03"),
    (2_000_035, "000002", "09:30:03"),
    (2_010_010, "600000", "09:30:03"),
    (2_010_045, "600001", "09:30:03"),
    (3_000_000, "000001", "09:30:06"),
    (3_010_000, "600000", "09:30:06"),
    (3_010_025, "600001", "09:30:06"),
    (3_021_000, "300001", "09:30:06"),
    (4_000_000, "000001", "09:30:09"),
    (4_000_020, "000002", "09:30:09"),
    (4_000_055, "600000", "09:30:09"),
    (4_000_080, "600001", "09:30:09"),
    (5_000_005, "000001", "09:30:12"),
    (5_000_035, "000002", "09:30:12"),
    (5_010_020, "600000", "09:30:12"),
    (5_022_000, "300001", "09:30:12"),
    (6_000_000, "000002", "09:30:15"),
    (6_010_000, "600000", "09:30:15"),
    (6_010_020, "600001", "09:30:15"),
    (6_023_000, "300001", "09:30:15"),
]

# 这里只是 mock 数据的已知标签，用于把同组股票排到相邻行，让热图更容易读。
# 真正处理未知 market data 时，不应为了“让图更像聚簇”而虚构这个映射；可以
# 按 stock_id 排序，或传入算法已经推断出的 group_id 排序。
EXAMPLE_VISUAL_GROUPS = {
    "000001": "示例组 A",
    "000002": "示例组 A",
    "600000": "示例组 B",
    "600001": "示例组 B",
    "300001": "低活跃单例",
}


def load_example_mds_data() -> pd.DataFrame:
    """创建本课的内存 mock，并显式设置三个字段的类型。"""

    data = pd.DataFrame.from_records(EXAMPLE_MDS_RECORDS, columns=REQUIRED_COLUMNS)
    return data.astype(
        {
            "clock": "int64",
            # 股票 ID 必须是字符串，否则 000001 会变成整数 1。
            "stock_id": "string",
            "time": "string",
        }
    )


def load_market_data_csv(input_csv: Path | str) -> pd.DataFrame:
    """读取真实 MDS CSV 中本课需要的三列。

    真实行情 CSV 还有很多盘口字段，但可视化和分组逻辑都不应该悄悄依赖它们。
    因此这里用 ``usecols`` 把输入边界写清楚。输入格式由项目约定保证正确，
    本教学函数不额外编写格式猜测和清洗分支。
    """

    return pd.read_csv(
        input_csv,
        usecols=REQUIRED_COLUMNS,
        dtype={"clock": "int64", "stock_id": "string", "time": "string"},
    )


def build_basic_plot() -> Any:
    """用最小例子认识 figure、ColumnDataSource、line 和 scatter。

    Bokeh 的常用思路是：

    1. 数据放进 ``ColumnDataSource``；
    2. glyph（图形标记）通过列名引用数据，例如 x="snapshot_number"；
    3. HoverTool 中用 ``@列名`` 读取鼠标所在点的字段。

    数据和画图配置分开后，同一份 source 可以同时供折线和散点使用，也便于
    后续增加筛选器或交互回调。
    """

    source = ColumnDataSource(
        data={
            "snapshot_number": [1, 2, 3, 4, 5, 6],
            "active_stock_count": [5, 4, 4, 4, 4, 4],
        }
    )

    plot = figure(
        title="Bokeh 基础：每个 snapshot 的股票数",
        width=590,
        height=320,
        x_axis_label="snapshot 序号",
        y_axis_label="出现的股票数",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        active_scroll="wheel_zoom",
        tooltips=[
            ("snapshot", "@snapshot_number"),
            ("股票数", "@active_stock_count"),
        ],
    )

    # line 展示总体变化趋势；scatter 把每个真实观测点明确画出来。
    # 两层 glyph 共用 source，因此 x/y 都直接写列名，不必重复传数组。
    plot.line(
        x="snapshot_number",
        y="active_stock_count",
        source=source,
        line_width=2,
        color="#4C78A8",
        legend_label="活跃股票数",
    )
    plot.scatter(
        x="snapshot_number",
        y="active_stock_count",
        source=source,
        size=10,
        color="#F58518",
        legend_label="实际观测",
    )
    plot.legend.location = "bottom_left"
    plot.legend.click_policy = "hide"
    return plot


def prepare_snapshot_arrivals(
    data: pd.DataFrame,
    snapshot_time: str,
    *,
    gap_threshold_us: int = 1_000,
) -> pd.DataFrame:
    """准备单个 snapshot 的到达顺序，并切出记录级候选时间簇。

    本函数只为画图准备数据：相邻 ``clock`` gap 大于等于阈值时，候选簇编号
    加一。这个 ``candidate_group_id`` 不是隐藏 ``push_id``，更不是全天固定
    ``group_id``。不同真实组偶尔会近时碰撞，所以单张图只能提供弱证据。
    """

    snapshot = (
        data.loc[data["time"].eq(snapshot_time), REQUIRED_COLUMNS]
        .sort_values("clock", kind="stable")
        .reset_index(drop=True)
        .copy()
    )

    # 本课示例保证 snapshot_time 存在，因此可以直接取第一行作为零点。
    snapshot_start = int(snapshot.loc[0, "clock"])
    snapshot["relative_clock_us"] = snapshot["clock"] - snapshot_start

    # 第一行没有前驱，把它的 gap 设成 0；后续每次遇到大 gap 就令 cumsum +1。
    snapshot["previous_gap_us"] = snapshot["clock"].diff().fillna(0).astype("int64")
    starts_new_candidate = snapshot["previous_gap_us"].ge(gap_threshold_us)
    snapshot["candidate_group_id"] = starts_new_candidate.cumsum().astype("int64")
    snapshot["candidate_group"] = "候选时间簇 " + snapshot["candidate_group_id"].astype(
        "string"
    )
    return snapshot


def build_snapshot_arrival_plot(
    arrivals: pd.DataFrame,
    *,
    gap_threshold_us: int = 1_000,
) -> Any:
    """画一个 snapshot 内的相对 clock 散点图。

    横轴越靠右表示该记录到达得越晚；同色只表示被当前 gap 阈值切进同一个
    记录级候选簇。悬停时可以检查原始 clock、相对 clock 和前一条 gap。
    """

    candidate_factors = arrivals["candidate_group"].drop_duplicates().tolist()
    source = ColumnDataSource(arrivals)

    plot = figure(
        title=f"单个 snapshot 的到达间隔：{arrivals.loc[0, 'time']}",
        width=590,
        height=320,
        x_axis_label="相对 snapshot 首条记录的 clock（微秒）",
        y_axis_label="stock_id",
        # Bokeh 分类轴的第一项默认在下方，反转后可让 clock 最早的股票在上方。
        y_range=list(reversed(arrivals["stock_id"].astype(str).tolist())),
        tools="pan,wheel_zoom,box_zoom,reset,save",
        active_scroll="wheel_zoom",
        tooltips=[
            ("time", "@time"),
            ("stock_id", "@stock_id"),
            ("原始 clock", "@clock"),
            ("相对 clock", "@relative_clock_us μs"),
            ("前一条 gap", "@previous_gap_us μs"),
            ("候选簇", "@candidate_group"),
        ],
    )
    plot.scatter(
        x="relative_clock_us",
        y="stock_id",
        source=source,
        size=14,
        color=factor_cmap(
            "candidate_group",
            palette=Category10[10],
            factors=candidate_factors,
        ),
        legend_field="candidate_group",
    )
    plot.legend.location = "bottom_right"
    plot.legend.click_policy = "hide"
    plot.ygrid.grid_line_color = None

    # Span 适合画固定参考线，但这里的阈值针对的是“相邻点差”，不是绝对 x 位置，
    # 所以不画一条误导性的 x=threshold 竖线，而是把阈值写进副标题。
    plot.title.text = f"{plot.title.text}（相邻 gap 阈值 {gap_threshold_us} μs）"
    return plot


def prepare_relative_clock_heatmap_data(
    data: pd.DataFrame,
    *,
    group_mapping: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """把 market data 转成长表，供相对 clock 向量热图使用。

    返回三项：

    - 每行一个 ``stock_id × time`` 单元格的长表；
    - 热图从左到右的 snapshot 顺序；
    - 热图从上到下的股票顺序。

    缺失组合仍保留一行，值为 ``NaN``。这一点很重要：0 表示该股票真实地是
    snapshot 第一条记录，``NaN`` 才表示该 snapshot 没有出现这只股票。
    """

    ordered = data.sort_values(["time", "clock"], kind="stable").copy()
    snapshot_order = ordered["time"].drop_duplicates().astype(str).tolist()

    # transform("first") 把每个 snapshot 的首 clock 广播到组内每一行。
    snapshot_start = ordered.groupby("time", sort=False)["clock"].transform("first")
    ordered["relative_clock_us"] = ordered["clock"] - snapshot_start

    vectors = ordered.pivot(
        index="stock_id",
        columns="time",
        values="relative_clock_us",
    ).reindex(columns=snapshot_order)
    vectors.index = vectors.index.astype(str)

    if group_mapping is None:
        # 没有分组结果时按股票 ID 排序，绝不从图形外观反推一个假标签。
        stock_order = sorted(vectors.index.tolist())
    else:
        # 如果已经有推断结果，可以先按 group_id、再按 stock_id 排序。同组连续
        # 排列更容易看出色带；排序仅影响显示，不改变任何数值。
        group_order = {
            group_label: position
            for position, group_label in enumerate(
                dict.fromkeys(group_mapping.values())
            )
        }
        stock_order = sorted(
            vectors.index.tolist(),
            key=lambda stock_id: (
                group_order.get(
                    group_mapping.get(stock_id, "未分组"), len(group_order)
                ),
                stock_id,
            ),
        )
    vectors = vectors.reindex(index=stock_order)

    # 宽向量表适合算法计算；Bokeh 的每一个 rect 对应一行数据，所以 melt 把它
    # 转成长表。melt 会保留 NaN，于是缺失维度也能画成一个灰色格子。
    heatmap_data = (
        vectors.rename_axis(index="stock_id", columns="time")
        .reset_index()
        .melt(
            id_vars="stock_id",
            var_name="time",
            value_name="relative_clock_us",
        )
    )
    heatmap_data["stock_id"] = heatmap_data["stock_id"].astype("string")
    heatmap_data["time"] = heatmap_data["time"].astype("string")
    heatmap_data["group_label"] = (
        heatmap_data["stock_id"].map(group_mapping or {}).fillna("未提供分组")
    )
    heatmap_data["relative_clock_text"] = heatmap_data["relative_clock_us"].map(
        lambda value: "该 snapshot 未出现" if pd.isna(value) else f"{int(value):,} μs"
    )
    return heatmap_data, snapshot_order, stock_order


def build_relative_clock_heatmap(
    heatmap_data: pd.DataFrame,
    snapshot_order: list[str],
    stock_order: list[str],
) -> Any:
    """画相对 clock 向量热图；缺失维度使用灰色。"""

    observed = heatmap_data["relative_clock_us"].dropna()
    high = max(float(observed.max()), 1.0)
    color_mapper = LinearColorMapper(
        palette=Viridis256,
        low=0,
        high=high,
        # nan_color 专门表示缺失。不要先 fillna(0)，否则缺失会和真实零点同色。
        nan_color="#D9D9D9",
    )
    source = ColumnDataSource(heatmap_data)

    plot = figure(
        title="跨 snapshot 的相对 clock 向量热图",
        width=590,
        height=340,
        x_range=snapshot_order,
        y_range=list(reversed(stock_order)),
        x_axis_label="time（向量维度）",
        y_axis_label="stock_id",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        active_scroll="wheel_zoom",
        tooltips=[
            ("stock_id", "@stock_id"),
            ("time", "@time"),
            ("相对 clock", "@relative_clock_text"),
            ("显示排序标签", "@group_label"),
        ],
    )
    plot.rect(
        x="time",
        y="stock_id",
        width=0.94,
        height=0.88,
        source=source,
        line_color="white",
        fill_color={"field": "relative_clock_us", "transform": color_mapper},
    )
    plot.add_layout(
        ColorBar(color_mapper=color_mapper, title="相对 clock（μs）"),
        "right",
    )
    plot.xaxis.major_label_orientation = 0.8
    plot.grid.grid_line_color = None
    return plot


def make_example_relationship_matrix() -> pd.DataFrame:
    """创建一个示意匹配率矩阵，用来学习矩阵热图。

    A 组与 B 组各自在对角线附近形成高值块；跨组值较低。低活跃的 300001
    与部分股票没有足够共同 snapshot，因此用 NaN 表示“证据不足”，而不是 0。
    这些数值只为教学构造，不是本课运行分组算法得到的结果。
    """

    stock_ids = ["000001", "000002", "600000", "600001", "300001"]
    values = [
        [1.00, 0.97, 0.08, 0.06, 0.12],
        [0.97, 1.00, 0.09, 0.07, float("nan")],
        [0.08, 0.09, 1.00, 0.95, 0.10],
        [0.06, 0.07, 0.95, 1.00, float("nan")],
        [0.12, float("nan"), 0.10, float("nan"), 1.00],
    ]
    labels = pd.Index(stock_ids, name="stock_id")
    return pd.DataFrame(values, index=labels, columns=stock_ids, dtype="float64")


def load_relationship_matrix_csv(input_csv: Path | str) -> pd.DataFrame:
    """读取 V1/V2 输出的 ``stock_id × stock_id`` 数值矩阵 CSV。

    当前 V1/V2 会把行股票 ID 写在第一列 ``stock_id``，列名也是股票 ID。
    读取时第一列必须显式使用字符串 dtype，才能保留 000001 的前导零。空单元格
    会自然读成 NaN，继续表示余弦相似度等指标的共同维度证据不足。
    """

    matrix = pd.read_csv(input_csv, dtype={"stock_id": "string"}).set_index("stock_id")
    matrix.index = matrix.index.astype(str)
    matrix.columns = matrix.columns.astype(str)
    return matrix.apply(pd.to_numeric)


def relationship_matrix_to_long_form(matrix: pd.DataFrame) -> pd.DataFrame:
    """把二维关系矩阵变成 Bokeh 每个 rect 一行的长表。"""

    ordered = matrix.copy()
    ordered.index = ordered.index.astype(str)
    ordered.columns = ordered.columns.astype(str)
    stock_order = ordered.index.tolist()

    # 用普通双循环展开矩阵，便于初学者直接看出每个单元格对应哪一对股票。
    # 对全市场矩阵，这里会产生 N² 行，只适合抽样、单个候选分量或调试视图；
    # 不应把数千只股票的完整关系矩阵一次画进浏览器。
    cells: list[dict[str, object]] = []
    for stock_a in stock_order:
        for stock_b in ordered.columns:
            value = ordered.loc[stock_a, stock_b]
            cells.append(
                {
                    "stock_a": stock_a,
                    "stock_b": stock_b,
                    "value": value,
                    "value_text": "证据不足"
                    if pd.isna(value)
                    else f"{float(value):.3f}",
                }
            )
    return pd.DataFrame.from_records(cells)


def build_relationship_matrix_heatmap(
    matrix: pd.DataFrame,
    *,
    title: str = "股票两两匹配率矩阵",
    color_label: str = "匹配率",
) -> Any:
    """把匹配率或余弦相似度矩阵画成可悬停检查的热图。"""

    heatmap_data = relationship_matrix_to_long_form(matrix)
    stock_order = matrix.index.astype(str).tolist()
    observed = heatmap_data["value"].dropna()
    high = max(float(observed.max()), 1.0)
    color_mapper = LinearColorMapper(
        palette=Viridis256,
        low=0,
        high=high,
        nan_color="#D9D9D9",
    )

    plot = figure(
        title=title,
        width=590,
        height=340,
        x_range=stock_order,
        y_range=list(reversed(stock_order)),
        x_axis_label="stock_b",
        y_axis_label="stock_a",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        active_scroll="wheel_zoom",
        tooltips=[
            ("stock_a", "@stock_a"),
            ("stock_b", "@stock_b"),
            (color_label, "@value_text"),
        ],
    )
    plot.rect(
        x="stock_b",
        y="stock_a",
        width=0.94,
        height=0.94,
        source=ColumnDataSource(heatmap_data),
        line_color="white",
        fill_color={"field": "value", "transform": color_mapper},
    )
    plot.add_layout(ColorBar(color_mapper=color_mapper, title=color_label), "right")
    plot.xaxis.major_label_orientation = 0.8
    plot.grid.grid_line_color = None
    return plot


def build_mds_dashboard(
    data: pd.DataFrame | None = None,
    relationship_matrix: pd.DataFrame | None = None,
    *,
    group_mapping: dict[str, str] | None = None,
    snapshot_time: str = "09:30:00",
    gap_threshold_us: int = 1_000,
) -> Any:
    """组合四张独立图，返回一个可保存的 Bokeh 页面布局。

    每个 ``build_*`` 函数只负责一张图，所以后续调整 MDS 观察重点时可以单独
    替换，不需要改保存逻辑。实际使用时，把 ``data`` 换成
    ``load_market_data_csv`` 的结果，把 ``relationship_matrix`` 换成
    ``load_relationship_matrix_csv`` 的结果即可。
    """

    uses_example_data = data is None
    if uses_example_data:
        data = load_example_mds_data()
        # 只有使用本课 mock 时才自动套用 mock 真值排序。传入真实行情后，默认
        # 不使用这些恰好与真实股票重名的示例标签。
        if group_mapping is None:
            group_mapping = EXAMPLE_VISUAL_GROUPS
    if relationship_matrix is None:
        relationship_matrix = make_example_relationship_matrix()

    arrivals = prepare_snapshot_arrivals(
        data,
        snapshot_time,
        gap_threshold_us=gap_threshold_us,
    )
    vector_cells, snapshot_order, stock_order = prepare_relative_clock_heatmap_data(
        data,
        group_mapping=group_mapping,
    )

    introduction = Div(
        text="""
        <h1>MDS Bokeh 可交互可视化</h1>
        <p>把鼠标停在点或方格上可查看原始字段；滚轮缩放，工具栏可复位或保存图像。</p>
        <p><b>解释边界：</b>单个 snapshot 的近时簇只是记录级候选；关系矩阵中的
        重复高值块才是全天固定分组的统计线索，灰色表示缺失或证据不足。</p>
        """,
        sizing_mode="stretch_width",
    )
    plots = gridplot(
        [
            [
                build_basic_plot(),
                build_snapshot_arrival_plot(
                    arrivals,
                    gap_threshold_us=gap_threshold_us,
                ),
            ],
            [
                build_relative_clock_heatmap(
                    vector_cells,
                    snapshot_order,
                    stock_order,
                ),
                build_relationship_matrix_heatmap(relationship_matrix),
            ],
        ],
        merge_tools=False,
    )
    return column(introduction, plots)


def save_mds_dashboard(
    output_html: Path | str,
    data: pd.DataFrame | None = None,
    relationship_matrix: pd.DataFrame | None = None,
    *,
    group_mapping: dict[str, str] | None = None,
    snapshot_time: str = "09:30:00",
    gap_threshold_us: int = 1_000,
) -> Path:
    """把完整课程页面保存为不需要 Python 服务的独立 HTML。

    不传数据时生成完整 mock 教程。传入真实数据时，也可同时传入 V1/V2 关系
    矩阵和已经推断出的分组标签；这些参数只决定画什么，不参与分组计算。
    """

    output_path = Path(output_html)
    output_file(
        filename=output_path,
        title="MDS Bokeh 可交互可视化",
        # inline 会把 BokehJS 资源直接嵌入 HTML，复制文件后也能离线打开。
        mode="inline",
    )
    save(
        build_mds_dashboard(
            data,
            relationship_matrix,
            group_mapping=group_mapping,
            snapshot_time=snapshot_time,
            gap_threshold_us=gap_threshold_us,
        )
    )
    return output_path


def run_temporary_example() -> int:
    """供 run_all 使用：验证 HTML 能生成，但不在仓库留下教学产物。"""

    with tempfile.TemporaryDirectory() as temporary_directory:
        output_path = Path(temporary_directory) / DEFAULT_OUTPUT_HTML.name
        save_mds_dashboard(output_path)
        print("\n[Bokeh] 已在系统临时目录生成独立 HTML")
        print("包含：基础图、snapshot 到达图、相对 clock 向量、关系矩阵")
        print("HTML 大小：", output_path.stat().st_size, "bytes")
    return 0


def main(output_html: Path | str = DEFAULT_OUTPUT_HTML) -> int:
    """生成可长期保留并用浏览器打开的课程 HTML。"""

    output_path = save_mds_dashboard(output_html)
    print(f"已生成 Bokeh 教程：{output_path.resolve()}")
    print("用浏览器打开该 HTML，即可缩放、悬停查看数据并隐藏图例项。")
    return 0


def parse_arguments() -> argparse.Namespace:
    """解析一个可选输出路径，保持命令行示例简单。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_html",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT_HTML,
        help="输出 HTML 路径（默认：mds/study/mds_bokeh_visualization.html）",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    raise SystemExit(main(arguments.output_html))
