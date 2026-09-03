# MDS pandas 可执行教程

这组教程围绕本项目真实出现过或下一步很可能使用的 pandas 操作编写。每个
Python 文件既有中文注释，也有可直接运行的小例子；mock 数据只存在于内存，
不会读写真实行情文件。

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
```

## 学习路线

| 课程 | 当前/未来用途 | 主要 pandas API |
|---|---|---|
| 01 CSV、类型与筛选 | 正确保留股票前导零，只读取三列，检查输入 | `read_csv`、`dtype`、`loc`、`iloc`、`isna`、`duplicated`、`concat`、`to_numeric` |
| 02 snapshot 操作 | 在每个 `time` 内排序和计算 `delta_clock` | `sort_values`、`groupby`、`diff`、`transform`、`cumcount`、`cumsum`、`agg` |
| 03 聚合与连接 | 汇总活跃度、构造候选股票对、连接最终映射 | 命名聚合、self-merge、`validate`、`indicator`、`crosstab` |
| 04 时间与大数据 | 上午/下午稳定性检查，处理数百万行 CSV | `to_timedelta`、`between`、`pivot`、`chunksize`、索引对齐、`memory_usage`、`category` |

## 三个贯穿原则

1. `time` 用于标识 3 秒 snapshot；真正比较到达先后的是微秒 `clock`，不要混用。
2. snapshot 内按 clock 得到的 `local_group_id` 只是记录级候选时间簇，不等于
   隐藏 `push_id`，更不等于全天固定 `group_id`。
3. pandas 的宽表、自连接和全局排序都可能制造很大的中间数据。先写清统计
   含义，再测量内存和复杂度；不能只因为一行 pandas 代码能运行就用于全市场。

## 延伸阅读

- [CSV 与文本 I/O](https://pandas.pydata.org/docs/user_guide/io.html)
- [GroupBy：split-apply-combine](https://pandas.pydata.org/docs/user_guide/groupby.html)
- [Merge、join 与 concat](https://pandas.pydata.org/docs/user_guide/merging.html)
- [Copy-on-Write 与链式赋值](https://pandas.pydata.org/docs/user_guide/copy_on_write.html)
- [大数据集的内存与分块建议](https://pandas.pydata.org/docs/user_guide/scale.html)
