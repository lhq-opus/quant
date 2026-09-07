# MDS pandas 与 Bokeh 可执行教程

这组教程围绕本项目真实出现过或下一步很可能使用的 pandas 与 Bokeh 操作编写。
每个 Python 文件既有中文注释，也有可直接运行的小例子；mock 数据只存在于
内存，不会读写真实行情文件。

从 `quant/` 目录运行全部课程：

```bash
python -m pip install -r mds/requirements.txt
python -m mds.study.run_all
```

也可以按顺序单独运行：

```bash
python -m mds.study.pandas_01_io_selection
python -m mds.study.pandas_02_snapshot_groupby
python -m mds.study.pandas_03_aggregate_merge
python -m mds.study.pandas_04_time_large_data
python -m mds.study.pandas_05_csv_files
python -m mds.study.bokeh_06_mds_visualization
```

第六课默认生成 ``mds/study/mds_bokeh_visualization.html``。它是可以直接用
浏览器打开的交互式页面，并已由同目录的 ``.gitignore`` 排除；也可以传入其他
目标路径：

```bash
python -m mds.study.bokeh_06_mds_visualization /tmp/mds_bokeh.html
```

要把 mock 换成已有 MDS 输出，可以直接复用第六课中的读取和保存函数：

```python
import pandas as pd

from mds.study.bokeh_06_mds_visualization import (
    load_market_data_csv,
    load_relationship_matrix_csv,
    save_mds_dashboard,
)

market = load_market_data_csv("market.csv")
matrix = load_relationship_matrix_csv("groups_match_rates.csv")
groups = pd.read_csv("groups.csv", dtype={"stock_id": "string"})
group_mapping = groups.astype({"group_id": "string"}).set_index("stock_id")[
    "group_id"
].to_dict()

save_mds_dashboard(
    "mds_result.html",
    data=market,
    relationship_matrix=matrix,
    group_mapping=group_mapping,
    snapshot_time="09:30:00",
)
```

V2 时只需把矩阵文件换成 ``groups_cosine_similarity.csv``。全市场二维矩阵会有
平方级单元格，浏览器不适合一次画完；应先选择一个候选分量、少量 group 或
抽样股票，再调用热图函数。

## 学习路线

| 课程 | 当前/未来用途 | 主要 API |
|---|---|---|
| 01 CSV、类型与筛选 | 正确保留股票前导零，只读取三列，检查输入 | `read_csv`、`dtype`、`loc`、`iloc`、`isna`、`duplicated`、`concat`、`to_numeric` |
| 02 snapshot 操作 | 在每个 `time` 内排序和计算 `delta_clock` | `sort_values`、`groupby`、`diff`、`transform`、`cumcount`、`cumsum`、`agg` |
| 03 聚合与连接 | 汇总活跃度、构造候选股票对、连接最终映射 | 命名聚合、self-merge、`validate`、`indicator`、`crosstab` |
| 04 时间与大数据 | 上午/下午稳定性检查，处理数百万行 CSV | `to_timedelta`、`between`、`pivot`、`chunksize`、索引对齐、`memory_usage`、`category` |
| 05 CSV 文件操作 | 创建带表头/仅表头文件，合并 CSV，分批追加 | `DataFrame.from_records`、`to_csv`、`concat`、`merge`、`mode`、`header` |
| 06 Bokeh 可交互图 | snapshot 到达间隔、相对 clock 向量、匹配率/余弦相似度矩阵 | `figure`、`ColumnDataSource`、`line`、`scatter`、`rect`、`HoverTool`、`LinearColorMapper`、`ColorBar`、`gridplot`、`save` |

## 五个贯穿原则

1. `time` 用于标识 3 秒 snapshot；真正比较到达先后的是微秒 `clock`，不要混用。
2. snapshot 内按 clock 得到的 `local_group_id` 只是记录级候选时间簇，不等于
   隐藏 `push_id`，更不等于全天固定 `group_id`。
3. pandas 的宽表、自连接和全局排序都可能制造很大的中间数据。先写清统计
   含义，再测量内存和复杂度；不能只因为一行 pandas 代码能运行就用于全市场。
4. “合并 CSV”要先问清方向：相同列按行堆叠用 `concat`；不同信息按键补列
   用 `merge`。两者的数据含义和行数风险完全不同。
5. 热图中的缺失维度要和真实的相对 `clock = 0` 区分开。本课用灰色表示缺失；
   同时只把单个 snapshot 的近时簇称为候选时间簇，不把图形外观当成永久分组真值。

## 延伸阅读

- [CSV 与文本 I/O](https://pandas.pydata.org/docs/user_guide/io.html)
- [GroupBy：split-apply-combine](https://pandas.pydata.org/docs/user_guide/groupby.html)
- [Merge、join 与 concat](https://pandas.pydata.org/docs/user_guide/merging.html)
- [Copy-on-Write 与链式赋值](https://pandas.pydata.org/docs/user_guide/copy_on_write.html)
- [大数据集的内存与分块建议](https://pandas.pydata.org/docs/user_guide/scale.html)
- [Bokeh：ColumnDataSource](https://docs.bokeh.org/en/latest/docs/user_guide/basic/data.html)
- [Bokeh：图形工具与 HoverTool](https://docs.bokeh.org/en/latest/docs/reference/models/tools.html)
- [Bokeh：分类轴热图示例](https://docs.bokeh.org/en/latest/docs/examples/topics/categorical/heatmap_unemployment.html)
- [Bokeh：生成独立 HTML](https://docs.bokeh.org/en/latest/docs/first_steps/first_steps_7.html)
