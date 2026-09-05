# 从原始 order/trade 生成重放事件表

`build_cancel_event_csv.py` 是一个独立运行的上游脚本。它读取固定表头的深交所
`order.csv`、`trade.csv`，生成可以直接交给 Python 或 C++ replay 的 `event.csv`。
order 和 `ExecType=4` 的撤单各生成一条事件；`ExecType=F` 只为集合竞价提供实际
成交价，不生成额外事件。

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

## 固定输入与处理逻辑

原始 order/trade 表头继续沿用项目已有约定。到达时间固定读取 `clockAtArrival`，
交易时间固定读取 `TransactTime`，不兼容其他列名或猜测日期格式。
用户已确认 `TransactTime` 是 `HHMMSSmmm` 数字：例如 `91500790` 左补零后成为
`091500790`，表示 09:15:00.790。上游把补足九位的结果写入 `TransactionTime`。

对于每条 `ExecType=4` 的 trade：

1. 合法输入中 `BidApplSeqNum` 和 `OfferApplSeqNum` 恰好一个为 `0`；
2. 取另一列的非零 ASN；
3. 使用 `ChannelNo + ASN` 在 order 的 `ChannelNo + ApplSeqNum` 中查找订单；
4. 用该 order 的原始 `Side` 和 `Price` 补全撤单事件，同时保留频道和被撤订单 ASN。

加入 `ChannelNo` 是为了避免不同频道出现相同 ASN 时查错。脚本不添加 `type` 列；
order 行和撤单行可以通过各自非空的业务字段区分。事件按 `caa` 稳定排序；当前 demo
假定不存在相同 `caa` 导致的事件顺序问题，不增加其他业务排序规则。

脚本另外从原始 trade 的 `ExecType=F` 行取得开盘、收盘集合竞价各自的实际成交价，
分别复制到对应阶段事件的 `AuctionPrice`。同一场集合竞价使用一个统一成交价；连续
竞价事件，以及没有实际成交的集合阶段，这一列为空。F 行的成交数量不交给 replay
扣减，避免和 replay 自己推导的成交重复计算。

`AuctionPrice` 是读取完整文件后取得的离线信息，不代表盘前或收盘集合事件发生时已知
该价格。阶段末行上的结算后快照沿用 demo 输出口径，不能直接当作当时可见的实时盘口。

## event.csv 列

```text
caa,TransactionTime,Side,OrderType,Price,OrderQty,ExecType,TradeQty,TradePrice,ChannelNo,OrderApplSeqNum,AuctionPrice
```

- 每行都保留 `caa,TransactionTime,Side,ChannelNo,OrderApplSeqNum`；
- order 行填写 `OrderType,Price,OrderQty`，`OrderApplSeqNum` 是自己的 `ApplSeqNum`；
- 撤单行填写 `ExecType,TradeQty,TradePrice`，`OrderApplSeqNum` 是引用的原订单 ASN，
  不是这条撤单自身的 `ApplSeqNum`；`Side` 和 `TradePrice` 来自被撤原订单；
- `AuctionPrice` 的含义是该集合阶段的实际成交价，填写规则见上文；
- 对当前行不适用的业务列为空。所有 CSV 都通过 pandas 读写，字段先按字符串保留。

`TradePrice` 在撤单行中仍保存原订单的原始价格。对于 `OrderType=1/U`，这个价格可能
为 0，也不一定是订单真正挂入盘口的价格。replay 会在处理 order 时记录
`(ChannelNo, OrderApplSeqNum) -> 实际挂单价格`，后续撤单按该引用查价；上游无需自己
再做一次盘口重放。

当前输入范围是单证券、单交易日、完整且合法的数据，订单索引的唯一性由这个约定保证。
脚本不做表头推测、未知枚举恢复或通用异常包装。输出覆盖保护仍然保留，以免误覆盖输入。

生成 event 后可以直接运行：

```bash
python3 ./quant/obr/script/replay_event_order_book.py \
  --event /path/to/event.csv \
  --output /path/to/book.csv
```

也可以用编译好的 `obr_replay_event` 读取同一份 event，不需要手工补充任何列。
