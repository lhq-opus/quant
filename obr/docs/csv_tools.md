# CSV 验证工具

这两个脚本位于 `obr/script`，只使用 Python 标准库，都可以作为独立命令运行。
它们用于构建可复现的小型验证数据，不负责确定最终的交易所事件排序规则。

## 1. 按到达时间截取三个 CSV

```bash
python3 ./quant/obr/script/slice_csv_by_arrival_time.py \
  --order ./data/examples/order.csv \
  --trade ./data/examples/trade.csv \
  --book ./data/examples/book.csv \
  --start-time '2026-08-31T09:30:00.000110+08:00' \
  --end-time '2026-08-31T09:30:00.000118+08:00' \
  --output-dir /tmp/obr-subset
```

输出固定为目标目录中的 `order.csv`、`trade.csv`、`book.csv`。区间是闭区间，
因此时间恰好等于起点或终点的行也会被保留。脚本保留每个输入文件的原表头和
数据字段，不在这一步合并 schema。

时间列自动按以下顺序识别：

1. `clockAtArrivalTime`；
2. `clockAtArrival`；
3. `caa`。

可使用 `--order-time-column`、`--trade-time-column`、`--book-time-column`
显式覆盖。默认按 ISO 8601 解析；对于其他已知格式，传入一个
`datetime.strptime` 格式，例如：

```bash
--time-format '%Y%m%d%H%M%S%f'
```

默认不覆盖已有输出；确认后可加 `--overwrite`。输出路径与任一输入路径相同时
总是拒绝，避免原数据被覆盖。

## 2. 合并 order 和 trade

```bash
python3 ./quant/obr/script/merge_order_trade_csv.py \
  --order ./data/examples/order.csv \
  --trade ./data/examples/trade.csv \
  --output /tmp/obr-merged.csv
```

输出列顺序为：

1. 新增列 `type`，值为 `order` 或 `trade`；
2. order 的全部列，保持原顺序；
3. trade 中尚未出现的独有列，保持它们在 trade 中的原顺序。

某类记录没有的列输出为空字符串。行按到达时间升序稳定排序；如果时间完全相同，
order 文件中的行在 trade 文件中的行之前，每个文件内的原始相对顺序保持不变。
这个规则只为构建验证数据提供确定性；最终重建流仍必须按已确认的频道和应用序号规则
排序，不能把到达时间当作权威业务顺序。

脚本默认不覆盖已有输出；需要时显式传入 `--overwrite`。
