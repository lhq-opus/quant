# event.csv 价格—时间优先重放 demo

`replay_event_order_book.py` 读取 `build_cancel_event_csv.py` 生成的 `event.csv`，
用简化的连续撮合规则重放限价单，并在每个事件后输出一行五档快照。

## 运行

```bash
python3 ./quant/obr/script/replay_event_order_book.py \
  --event /path/to/event.csv \
  --output /path/to/book.csv
```

`--output` 省略时默认写到当前目录的 `book.csv`。默认不覆盖已有输出；需要重新
生成时添加 `--overwrite`，但输出不能覆盖输入 `event.csv`。

## 价格优先、时间优先

每个价格对应一个 FIFO 队列，队首是该价格最早到达的剩余订单：

```text
价格 -> [最早订单剩余量, 第二早订单剩余量, ...]
```

- 新买单先与最低卖价成交；买入限价低于最低卖价时停止成交；
- 新卖单先与最高买价成交；卖出限价高于最高买价时停止成交；
- 同一价格有多张订单时，总是先扣队首订单；
- incoming order 全部成交就不入簿，存在余量才加入本方价格队列末尾；
- 内部保存全部价格档，五档只在写快照时截取。

这套规则描述的是本项目的连续撮合验证模型，不适用于集合竞价，也不替代交易所
正式规则或逐笔成交消息。

## 撤单限制

当前 `event.csv` 的撤单行只有 `TradePrice` 和 `TradeQty`，已经没有原始订单 ID
与方向。因此 demo 采用以下严格规则：

1. `TradePrice` 必须恰好出现在买簿或卖簿的一侧；
2. 该价格的聚合剩余量必须不小于 `TradeQty`；
3. 验证全部通过后，再从该价格 FIFO 队首开始扣减。

这能重建聚合价位数量，但不能证明被撤销的是哪张真实订单。如果价格在两侧、两侧
都没有，或撤单量过大，脚本直接报错，且该事件不修改订单簿。

## 输入与输出

输入表头必须严格为：

```text
caa,Side,OrderType,Price,OrderQty,ExecType,TradeQty,TradePrice
```

目前只支持 `Side=1/2`、`OrderType=2` 和 `ExecType=4`。一行必须完整表示 order
或 cancel，不能把两类字段混在同一行。

输出表头为：

```text
caa,event_type,bp1,bs1,bp2,bs2,bp3,bs3,bp4,bs4,bp5,bs5,
ap1,as1,ap2,as2,ap3,as3,ap4,as4,ap5,as5
```

`event_type` 为 `order` 或 `cancel`；价格固定四位小数，空档输出空字符串。事件先
按 ISO 8601 `caa` 稳定排序；时间完全相同时保留 `event.csv` 中的原始顺序。

所有 CSV 通过 pandas 读写，依赖安装方式见 `quant/obr/requirements.txt`。
