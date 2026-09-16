# method_5：用户扫描脚本的最小修改

保留用户原来的逐行 `iloc`、字典、列表及合并逻辑。算法仅增加两处：

1. 从开头全量股票记录，按相邻 `clock` 差大于 `100000` 建立初始扫描片段映射。
2. 原 `delta_clock <= 100` 合并条件追加“初始扫描片段不同”。

另补独立运行所需的 pandas CSV 读取和结果保存；没有更换合并算法。该筛选条件是 method1 的启发式假设，不代表一次接近必然属于同一真实业务组。

在 `quant` 目录运行：

```sh
python mds/v2_grouping/method_5/script/group_by_scan.py
```

输入固定为 `mds/data_v2.csv`，输出本目录 `stock_groups.csv`。组号保留原脚本产生的编号，可以不连续；实际组数看 `len(group)`。

实际全量运行得到 1451 股、6 组，成员与 method1 一致（允许组号不同）。未新增或运行单元测试。
