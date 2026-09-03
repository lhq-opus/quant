# C++11 第一版 event.csv 重放

## 这一版解决什么问题

这一版把 Python `replay_event_order_book.py` 的主要数据流用基础 C++11 重写一遍：

```text
命令行
  -> 读取固定 9 列 event.csv
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

输入固定为以下 9 列：

```text
caa,TransactionTime,Side,OrderType,Price,OrderQty,ExecType,TradeQty,TradePrice
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

其中 `Side` 和 `TradePrice` 已由上游从原订单补全。这一步把两种 CSV 行归一成同一个
简单 `Event`，所以 `OrderBook` 不需要知道原始列位置；集合竞价出现买卖同价时，也能
按 `Side` 撤销正确一侧。

## 为什么价格仍使用整数

代码没有复杂的强类型，但也没有使用 `double`。`Price` 是普通 `std::int64_t`，单位为
0.0001 元：

```text
CSV 10.10  <->  内部 101000  <->  输出 10.1000
```

`parse_price()` 在输入边界拆开整数和小数部分，`format_fixed_point()` 在输出边界恢复四位小数。
成交额内部同样保留四位小数单位。

## OrderBook 的直接逻辑

内部只有两个主要状态：

```text
bids_: 价格从高到低 -> 聚合买量
asks_: 价格从低到高 -> 聚合卖量
```

- 集合竞价 order：只加入本方 map；阶段结束时统一筛选成交价并扣减双方数量；
- 连续竞价 order：从对方 `map.begin()` 开始逐档成交，剩余量再进入本方 map；
- cancel：用上游补好的 `TradePrice` 查找价格档并扣除 `TradeQty`；
- snapshot：直接从两个已经排好序的 map 各取前五个元素。

集合竞价与 Python demo 相同：按最大成交量、较优价格全部成交、成交价一侧全部成交、
严格高买量与严格低卖量差最小依次筛选。本 demo 不使用 reference price，约定筛选后只剩
一个候选价。

## 有意不做的事情

这一版假设输入是单交易日、单标的、完整且合法的数据，因此没有实现：

- 订单 ID、同价 FIFO 或真实成交双方恢复；
- 表头兼容、带引号 CSV、非法数字和未知枚举诊断；
- 重复事件、序列缺口、未知撤单、超量扣减或整数溢出策略；
- 输出覆盖保护、恢复模式、多标的调度或性能优化。

这些不是被遗忘，而是按当前学习目标推迟。后续工业化迭代可以在已经理解状态变化之后，
逐项恢复明确的输入契约和错误策略。

## 验证

```bash
/tmp/obr-build/obr_validate_reconstruction_core
```

验证程序只覆盖合法正常流程：开盘集合竞价、连续逐档成交、盘前撤单、收盘集合竞价、
未成交数量结转以及累计成交量和成交额。端到端验证还会让 C++ 和 Python 读取同一份临时
`event.csv`，并逐字节比较两份 `book.csv`。
