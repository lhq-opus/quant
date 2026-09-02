# 撤单价格验证事件表

`build_cancel_event_csv.py` 是一个独立运行的验证脚本。它保留全部 order，只保留
`ExecType=4` 的 trade，并把撤单引用的原订单价格写入撤单行的 `TradePrice`，最后
按到达时间生成 `event.csv`。

## 运行

先按照 `quant/obr/requirements.txt` 安装 pandas，然后执行：

```bash
python3 ./quant/obr/script/build_cancel_event_csv.py \
  --order /path/to/order.csv \
  --trade /path/to/trade.csv \
  --output /path/to/event.csv
```

`--output` 省略时默认写到当前目录的 `event.csv`。默认不覆盖已有文件；需要重新
生成时添加 `--overwrite`。输出路径与两个输入之一相同时始终拒绝。

## 处理逻辑

对于每条 `ExecType=4` 的 trade：

1. `BidApplSeqNum` 和 `OfferApplSeqNum` 必须恰好一个为 `0`；
2. 取另一列的非零 ASN；
3. 使用 `ChannelNo + ASN` 在 order 的 `ChannelNo + ApplSeqNum` 中查找订单；
4. 用该 order 的原始 `Price` 创建或覆盖 trade 的 `TradePrice`。

加入 `ChannelNo` 是为了避免不同频道出现相同 ASN 时查错。脚本不添加 `type` 列；
order 行和 trade 行可以通过各自非空的业务字段区分。同一 `caa` 下使用稳定排序，
order 行位于 trade 行之前。

## event.csv 列

```text
caa,Side,OrderType,Price,OrderQty,ExecType,TradeQty,TradePrice
```

- order 行保留 `caa,Side,OrderType,Price,OrderQty`，trade 专有列为空；
- 撤单 trade 行保留 `caa,ExecType,TradeQty,TradePrice`，order 专有列为空；
- 输入到达时间可命名为 `clockAtArrivalTime`、`clockAtArrival` 或 `caa`，输出统一为
  `caa`；
- 所有 CSV 都通过 pandas 读写，原始字段先按字符串保留。

这个脚本按 `ChannelNo + ApplSeqNum` 建立唯一订单索引。如果输入跨交易日后该键重复，
脚本会拒绝；当前验证数据应先截取为单交易日。它只用于检查撤单引用和事件顺序，
不是完整订单簿重建器。
