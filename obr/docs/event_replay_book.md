# order 与撤单事件的订单簿重放

`replay_event_order_book.py` 读取 `build_cancel_event_csv.py` 生成的 `event.csv`，
在价格档层面处理可成交数量、更新买卖盘，并在每条事件之后输出一行五档订单簿。

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
订单级 FIFO。内部保留全部价格档，生成快照时才各取买卖前五档。

## order 的价格档级撮合

买单处理流程：

1. 读取当前卖一；
2. 如果卖一价格高于买入限价，停止成交；
3. 否则成交量取“买单剩余量”和“卖一聚合量”的较小值；
4. 从买单和卖一分别扣除这部分数量，卖一为 0 时删除该价格档；
5. 买单仍有剩余时继续查看新的卖一，全部可成交档位处理完后，剩余量才进入买盘。

卖单处理与之对称：从买一开始，只要买一价格不低于卖出限价，就依次消耗买一、
买二等价格档；最后未成交的剩余量进入卖盘。

这个过程仍然是在推导成交，但只处理“价格档总量”，不会判断买单具体与同价位中的
哪一张卖单成交，也不会保存订单 FIFO。

深交所连续竞价规则规定，买入申报高于当前最低卖价时，以当前最低卖价成交；卖出
申报低于当前最高买价时，以当前最高买价成交。脚本据此使用被消耗的卖一或买一价格
计算成交额。参见[《深圳证券交易所交易规则（2026年修订）》](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)第 3.4.4 条。

## 成交量和成交额

每次消耗一个价格档时：

```text
该档成交额 = 该档成交价格 × 该档成交数量
```

同一 order 连续消耗卖一、卖二时，各档分别计算再相加。脚本保存：

- `event_trade_quantity`：当前 order 推导出的成交量；
- `event_turnover`：当前 order 推导出的成交额；
- `cumulative_trade_quantity`：累计推导成交量；
- `cumulative_turnover`：累计推导成交额。

例如卖一为 `100.2000 × 600`、卖二为 `100.3000 × 400`，随后到达
`100.3000 × 700` 的买单：

```text
先成交 600 × 100.2000 = 60120.0000
再成交 100 × 100.3000 = 10030.0000
累计成交量 = 700
累计成交额 = 70150.0000
```

价格档模型不能确定同一价格内涉及多少张具体订单，因此不能可靠推导交易所成交消息
笔数 `nts`。当前简化 book 表头不输出成交统计；命令结束时会打印累计推导成交量和
成交额，后续完整 book writer 可使用累计量和累计额生成 `cvl`、`cto`。

## 撤单 trade 的处理

当前 `event.csv` 只保留 `ExecType=4` 的撤单 trade。
`build_cancel_event_csv.py` 已根据原始订单引用，把撤单订单的价格写入
`TradePrice`。

重放时：

1. 根据 `TradePrice` 找到买盘或卖盘的对应价格档；
2. 从该价格档减去 `TradeQty`；
3. 如果聚合数量变成 0，删除整个价格档。

第一版输入保证数据合法且撤单价格可以定位到正确的一侧，因此这里不再进行订单级
FIFO 扣减、超量检查或兼容处理。

## caa 与快照的对应关系

每一条 order 或撤单 trade 都恰好生成一行订单簿：

```text
输入事件 caa -> 应用该事件 -> 输出相同 caa 的 book 行
```

输出不会合并或跳过事件。事件先按 `caa` 稳定排序；两个事件的 `caa` 相同时，保持
它们在 `event.csv` 中的原始顺序。

由 order 推导出的全部价格档成交都归属于这条 order，因此订单簿使用该 order 的
`caa`；撤单后的订单簿使用对应撤单 trade 的 `caa`。原始 `ExecType=F` trade 不在
当前 `event.csv` 中，也不会额外产生 book 行。

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
