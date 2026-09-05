# Python 订单簿重建 demo

`reconstruct_book_demo.py` 用一个 Python 文件展示从 `order.csv` 和 `trade.csv`
重建 `book.csv` 的完整状态转换。它的目标是学习和手工验证，不是取代 C++ 生产核心。

脚本使用 pandas 读写 CSV。首次运行前安装项目依赖：

```bash
python3 -m venv /tmp/obr-python-env
source /tmp/obr-python-env/bin/activate
python -m pip install -r ./quant/obr/requirements.txt
```

输入列全部按字符串读取，订单簿计算时才显式把价格转为 `Decimal`、数量转为整数。

## 运行

```bash
python3 ./quant/obr/script/reconstruct_book_demo.py \
  --order ./data/examples/order.csv \
  --trade ./data/examples/trade.csv \
  --output /tmp/reconstructed-book.csv
```

默认不覆盖已存在的输出。需要替换之前的 demo 结果时可以加 `--overwrite`，
但输出路径与 order 或 trade 输入相同时始终会被拒绝。

## demo 支持范围

- 单交易日、单证券、单频道；
- `OrderType=2` 限价委托；
- `ExecType=F` 成交和 `ExecType=4` 撤单；
- 从足以建立完整活动订单的起点开始重放；
- 每个合并事件后输出一行五档快照。

它不支持市价单、本方最优、多频道合并、多证券、盘中初始快照、缺口恢复或
任何宽容模式。未知值和不一致数据直接报错。

## 核心数据结构

```text
orders
  (trading_day, channel, original_asn)
    -> side, limit_price, remaining_quantity

bid_levels / ask_levels
  price -> aggregate_remaining_quantity
```

`orders` 保留每张活动订单，因为成交和撤单通过原始 ASN 指向具体订单。
`bid_levels` 和 `ask_levels` 是按价格聚合的全深度状态。五档只在输出时投影，
第六档及更深价格不会从内部删除。

## 三种状态转换

### 新增

1. 确认订单 ID 当前不存在；
2. 把方向、价格和原始数量写入 `orders`；
3. 给对应买卖方向和价格档加上数量。

### 撤单

1. 根据非零的 `BidApplSeqNum` 或 `OfferApplSeqNum` 定位订单；
2. 确认订单存在、方向正确且剩余量不小于本次 `TradeQty`；
3. 同时减少订单剩余量和价格档聚合量；
4. 数量变为零时删除订单或空价格档。

### 成交

1. 用 `BidApplSeqNum` 和 `OfferApplSeqNum` 定位买卖两张订单；
2. **在修改任何状态前**，同时确认两张订单存在、方向正确且数量足够；
3. 对两张订单及它们的价格档扣减相同的 `TradeQty`；
4. 仅在真实成交中更新 `nts`、`cvl`、`cto`、`lpr`、`opx`。

## 输出规则

- 按 `ChannelNo + ApplSeqNum` 合并两个文件；`clockAtArrival` 只是输出元数据；
- ASN 属于整个频道，单证券数据中的 ASN 不要求逐条加一；重复 ASN 仍然报错，
  但不能仅凭单证券文件跳号判断频道丢包；
- 买价从高到低、卖价从低到高选取前五档；
- 价格和成交额固定四位小数，不足五档的位置写空字符串；
- `bo4` 保留外部表头拼写，内部仍按“买四价”理解；
- `cto` 由 `TradePrice × TradeQty` 独立计算，不直接信任 `TradyMoney`。

脚本在每个事件后从活动订单重算买卖聚合档位并检查不变量。这是 O(N) 教学检查，
不是对正式热路径的性能建议。
