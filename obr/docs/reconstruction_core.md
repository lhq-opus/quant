# C++11 第一版 event.csv 重放

## 这一版解决什么问题

这一版把 Python `replay_event_order_book.py` 的主要数据流用基础 C++11 重写一遍：

```text
命令行
  -> 读取固定 12 列 event.csv
  -> 每行转换成 Event
  -> 按 caa 稳定排序
  -> 重放开盘集合、连续和收盘集合竞价
  -> 每条 Event 生成一条五档 Snapshot
  -> 写 book.csv
```

目标是让初学者可以顺着代码看到 CSV 字符串怎样一步步变成订单簿，而不是第一版就搭建
完整的生产框架。代码只使用 C++11 及更早的基础语法和标准库。

## 三个文件的职责

- `include/obr/domain.hpp`：定义基础整数别名、`Event`、`TradingSession`、
  `PriceLevel` 和 `Snapshot`；
- `include/obr/order_book.hpp` 与 `src/order_book.cpp`：用两个 `std::map` 保存买卖
  聚合价格档，实现集合竞价、连续竞价、撤单和五档快照；
- `src/replay_event_main.cpp`：解析命令行、拆分 CSV、转换 Event、判断交易阶段、排序，
  最后写出 CSV。

这三层只是为了不把文件读写和订单簿状态混在同一个函数里，不是抽象框架。

## 构建和运行

在 `quant/obr` 目录执行：

```bash
cmake -S . -B /tmp/obr-build -DCMAKE_BUILD_TYPE=Debug
cmake --build /tmp/obr-build --parallel

/tmp/obr-build/obr_replay_event \
  --event /path/to/event.csv \
  --output /path/to/book.csv
```

`--output` 可以省略，默认覆盖当前目录下的 `book.csv`。第一版没有 `--overwrite`、路径
冲突检查或自动创建父目录。

## CSV 怎样变成 Event

输入由 `build_cancel_event_csv.py` 直接生成，固定为以下 12 列：

```text
caa,TransactionTime,Side,OrderType,Price,OrderQty,ExecType,TradeQty,TradePrice,ChannelNo,OrderApplSeqNum,AuctionPrice
```

`replay_event_main.cpp` 先跳过表头，然后用一个简单循环按逗号拆分每一行。输入约定合法，
字段中没有逗号和引号，因此这里不引入第三方 CSV 库，也不实现 RFC CSV 转义规则。

order 行转换为：

```text
EventType::Order
side       = Side
order_type = OrderType
price      = Price
quantity   = OrderQty
```

`ExecType=4` 的撤单行转换为：

```text
EventType::Cancel
side     = Side
price    = TradePrice
quantity = TradeQty
```

其中 `Side` 和 `TradePrice` 已由上游从原订单补全，后者仍是原始价格。两类事件还共用
`ChannelNo,OrderApplSeqNum`：order 填自己的 ASN，cancel 填引用的原订单 ASN。
`OrderBook` 通过这个引用查到实际挂单价，cancel 的 `price` 不再负责定位档位；集合
竞价出现买卖同价时，再按 `Side` 选择正确一侧。

`TransactionTime` 由上游把原始 `TransactTime` 按固定的 `HHMMSSmmm` 数字格式左补
九位得到，不需要用户手工添加。`AuctionPrice` 是该开盘或收盘集合阶段的实际成交价；
连续阶段以及集合阶段没有实际成交时为空。两种 CSV 行都归一成简单的 `Event`，所以
`OrderBook` 不需要知道原始列位置。

`order_type` 在连续竞价中决定 `OrderBook` 怎样取得实际限价：

- `2` 直接使用 `event.price`；
- `1` 按当前 demo 约定使用对手方最优价，剩余量也挂在该价；
- `U` 忽略 `event.price`，直接加入本方最优档。

深交所行情里的 `OrderType=1` 只说明它属于市价订单。正式申报还需要
`TimeInForce / MaxPriceLevels / MinQty` 才能区分不同市价子类型，而当前 event 没有
这些字段。因此这里的 `1=对手方最优、剩余转限价` 是为现有输入选择的教学约定，不是
完整交易所枚举映射。两份官方字段定义可分别查看
[Binary 行情接口](https://www.szse.cn/marketServices/technicalservice/interface/P020250328368568358456.pdf)
和 [STEP 交易接口](https://investor.szse.cn/marketServices/technicalservice/interface/P020250328368240326574.pdf)。

## 为什么价格仍使用整数

代码没有复杂的强类型，但也没有使用 `double`。`Price` 是普通 `std::int64_t`，单位为
0.0001 元：

```text
CSV 10.10  <->  内部 101000  <->  输出 10.1000
```

`parse_price()` 在输入边界拆开整数和小数部分，`format_fixed_point()` 在输出边界恢复四位小数。
成交额内部同样保留四位小数单位。

## OrderBook 的直接逻辑

盘口仍用两个有序 map，另加一个用于撤单定位的小索引：

```text
bids_: 价格从高到低 -> 聚合买量
asks_: 价格从低到高 -> 聚合卖量
原订单价格索引: (频道, 原订单 ASN) -> 实际挂单价格或未挂入盘口
```

- 集合竞价 order：只加入本方 map；阶段结束时统一筛选成交价并扣减双方数量；
- 连续竞价类型 `2`：从对方 `map.begin()` 开始逐档成交，剩余量以 CSV 限价进入本方；
- 连续竞价类型 `1`：先取对方 `map.begin()` 的价格作为限价，只成交该最优档，剩余
  数量以这个价格进入本方；对手盘为空时自动撤销；
- 连续竞价类型 `U`：直接加入本方 `map.begin()` 对应的最优档，本方为空时自动撤销；
- cancel：按原订单引用取得实际挂单价，用 `Side` 选择买卖盘，然后扣除 `TradeQty`。
  类型 `1/U` 因空盘口自动撤销时没有挂单价，后续该单的撤单事件不再扣簿；
- snapshot：直接从两个已经排好序的 map 各取前五个元素。

原订单价格索引在处理 order、确定实际限价时填写，因此原始 `Price=0` 的 `1/U` 也能
正确撤单。索引不维护每张订单剩余量，不建立 FIFO，成交仍然只扣聚合价格档。

集合竞价与 Python demo 相同：计算最大成交量，并满足严格较优价格全部成交、成交价
一侧全部成交的条件；再按包含候选价的 `abs(buy_quantity - sell_quantity)` 最小筛选。
如果仍有多个候选，使用原始 trade 给出的 `AuctionPrice`；实际成交价也会加入候选集合，
允许该价没有原始挂单。这里不用 reference price，也不再假定候选一定唯一。

原始 `ExecType=F` 只给集合竞价提供价格，不进入 event 重复扣量。所有集合成交按一个
统一价格累计成交额，买卖两侧各扣一次成交数量。该阶段最后一条 order/cancel 的快照
显示结算后状态，每条 event 仍与一条相同 `caa` 的 book 对应。

## 有意不做的事情

这一版假设输入是单交易日、单标的、完整且合法的数据，因此没有实现：

- 同价 FIFO、每张订单剩余量或真实成交双方恢复；
- 表头兼容、带引号 CSV、非法数字和未知枚举诊断；
- 重复事件、序列缺口、未知撤单、超量扣减或整数溢出策略；
- 输出覆盖保护、恢复模式、多标的调度或性能优化。

输入也假定不存在 CAA 事件顺序问题，因此继续按 `caa` 稳定排序，不在本轮添加 ASN
业务排序。后续工业化迭代可以在已经理解状态变化之后，逐项恢复明确的输入契约和错误策略。

## 验证

```bash
/tmp/obr-build/obr_validate_reconstruction_core
```

验证程序只覆盖合法正常流程：开盘集合竞价、连续逐档成交、三种 `OrderType` 的买卖
方向、最优价为空时自动撤销及其撤单、动态挂单价撤单、盘前同价双边撤单、收盘集合
竞价、集合竞价数量差筛选与实际成交价并列处理、未成交数量结转以及累计成交量和成交额。
端到端验证还会从临时原始 order/trade 生成 event，让 C++ 和 Python 读取同一份
`event.csv`，并逐字节比较两份 `book.csv`。临时 mock CSV 不纳入提交。
