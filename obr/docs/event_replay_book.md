# order 与撤单事件的订单簿重放

`replay_event_order_book.py` 读取 `build_cancel_event_csv.py` 生成的 `event.csv`，
依次更新买卖盘，并在每条事件之后输出一行五档订单簿。

## 运行方式

```bash
python3 ./quant/obr/script/replay_event_order_book.py \
  --event /path/to/event.csv \
  --output /path/to/book.csv
```

`--output` 省略时，默认写到当前目录的 `book.csv`。如果输出文件已经存在，需要添加
`--overwrite`。输出路径不能与输入 `event.csv` 相同。

## 核心数据结构

脚本分别保存完整买盘和卖盘：

```text
bids：买方价格 -> 该价格的聚合数量
asks：卖方价格 -> 该价格的聚合数量
```

订单簿输出只关心每个价格档的总数量，所以第一版不保存同价订单队列，也不实现
FIFO。内部保留全部价格档，生成快照时才各取买卖前五档。

## order 的处理

- `Side=1`：把 `OrderQty` 累加到 `bids[Price]`；
- `Side=2`：把 `OrderQty` 累加到 `asks[Price]`。

order 只修改自己的买方或卖方价格档。即使新买价高于卖一，或新卖价低于买一，
脚本也不会主动撮合，因为重放器不能自行创造交易所没有发布的成交事件。

## 撤单 trade 的处理

当前 `event.csv` 只保留 `ExecType=4` 的撤单 trade。
`build_cancel_event_csv.py` 已根据原始订单引用，把撤单订单的价格写入
`TradePrice`。

重放时：

1. 根据 `TradePrice` 找到买盘或卖盘的对应价格档；
2. 从该价格档减去 `TradeQty`；
3. 如果聚合数量变成 0，删除整个价格档。

第一版输入保证数据合法且撤单价格可以定位到正确的一侧，因此这里不再进行订单级
FIFO 扣减、撮合、超量检查或兼容处理。

## caa 与快照的对应关系

每一条 order 或撤单 trade 都恰好生成一行订单簿：

```text
输入事件 caa -> 应用该事件 -> 输出相同 caa 的 book 行
```

输出不会合并或跳过事件。事件先按 `caa` 稳定排序；两个事件的 `caa` 相同时，保持
它们在 `event.csv` 中的原始顺序。

## 固定输入结构

脚本只读取以下固定表头，不猜测其他字段名，也不提供兼容表头：

```text
caa,Side,OrderType,Price,OrderQty,ExecType,TradeQty,TradePrice
```

- order 行使用 `caa,Side,OrderType,Price,OrderQty`；
- 撤单行使用 `caa,ExecType,TradeQty,TradePrice`；
- 当前必要枚举是 `Side=1/2`、`OrderType=2`、`ExecType=4`；
- 输入已经保证格式和内容合法，脚本直接按上述字段执行。

## 输出结构

```text
caa,event_type,bp1,bs1,bp2,bs2,bp3,bs3,bp4,bs4,bp5,bs5,
ap1,as1,ap2,as2,ap3,as3,ap4,as4,ap5,as5
```

- `event_type` 为 `order` 或 `cancel`；
- 买盘按价格从高到低输出，卖盘按价格从低到高输出；
- 价格固定输出四位小数；
- 不足五档的位置输出空字符串。

所有 CSV 使用 pandas 读写，依赖安装方式见 `quant/obr/requirements.txt`。
