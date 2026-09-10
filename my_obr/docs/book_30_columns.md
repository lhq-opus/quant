# my_obr 的 30 列 book 输出

本次将原 21 列扩展为约定的 30 列，补齐事件元数据和源成交统计。
使用 C++11，保留现有函数划分、模拟撮合、市价类型推断以及快照输出时机。

表头严格为：

```text
caa,secid,sno,asn,tst,nts,cvl,cto,lpr,opx,bp5,bo4,bp3,bp2,bp1,ap1,ap2,ap3,ap4,ap5,bs5,bs4,bs3,bs2,bs1,as1,as2,as3,as4,as5
```

`bo4` 按外部契约原样输出，内容是买四价；原实验表头中的 `bp4` 改为 `bo4`。

## 字段和统计口径

| 列 | 来源或计算方式 |
| --- | --- |
| `caa` | 触发快照事件的 `clockAtArrival`，原样保留 |
| `secid` | 该事件的 `secid`，保留字符串及前导零 |
| `sno` | 该事件的 `sequenceNo`，整数输出 |
| `asn` | 该事件本身的 `ApplSeqNum`，整数输出 |
| `tst` | 该事件的 `TransactTime`，保留原文本 |
| `nts` | 已成功处理的 `ExecType=F` 记录数，每条加 1 |
| `cvl` | 上述 F 的 `TradeQty` 之和，每笔只计一次 |
| `cto` | 上述 F 的 `TradePrice × TradeQty` 之和，每笔只计一次 |
| `lpr` | 最近一条已成功处理的 F 的 `TradePrice` |
| `opx` | 全日第一条已成功处理的 F 的 `TradePrice`，设定后不变 |
| `bp5,bo4,bp3,bp2,bp1` | 买五至买一价格 |
| `ap1..ap5` | 卖一至卖五价格 |
| `bs5..bs1` | 与买五至买一对应的数量 |
| `as1..as5` | 与卖一至卖五对应的数量 |

例如撤单事件自身 `ApplSeqNum=900`，引用买单 `BidApplSeqNum=100`，则 book 的 `asn`
输出 `900`，实际扣减的仍是原订单 `100`。为避免混用，`Event` 新增 `appl_seq_num`，
原来的 `order_appl_seq_num` 继续负责原单引用。

数量、笔数和序号使用整数。价格和成交额使用整数计算、四位小数输出，延续输入价格
已放大 10000 倍且数量为整数单位的实验契约。例如 `TradePrice=123456, TradeQty=3`，
该笔成交额输出 `37.0368`。不使用供应商含义尚未确认的 `TradyMoney` 替代计算。

尚无成交时，`nts/cvl` 为 `0`，`cto/lpr/opx` 为 `0.0000`。盘口不足五档时延续原补零规则：
价格 `0.0000`，数量 `0`。没有输入事件时仍写完整表头，不产生数据行。

## 源成交与模拟撮合

五个输出统计字段只在 `OrderBook::apply()` 成功处理源 F 时改变。它们不在预读全日
历史的 `build_trade_map()` 中累计，也不在模拟撮合的 `record_trade()` 中累计。

一笔 F 引用买卖两张订单，但笔数、成交量、成交额各只计一次。反过来，一次价格档
模拟撮合可能对应多条 F：例如同一价位先后成交 4 和 6，`nts=2, cvl=10`，不能把一次
聚合档扣量当成一笔真实成交。撤单和订单事件均不增加这五项统计。

原 `cumulative_trade_quantity_num/cumulative_turnover_num` 保留为模拟撮合的内部结果；
新 `source_trade_count/source_trade_quantity/source_turnover` 用于输出源成交统计。
本轮没有改变价格档由订单模拟撮合更新的实验架构。

处理 F 时先检查原单引用、双方剩余量以及笔数/数量/金额的全部运算范围，再一起更新
两张订单登记和五项统计。溢出或其他校验失败不会留下只扣一侧或只更新部分统计的状态。

## 快照时机与开盘价

快照时机沿用原实现：事件处理后，仅在 `generate_snapshot` 为真时保存快照；writer
只写连续竞价阶段。市价分支原先关闭快照的行为保留，F 不单独生成一行，开收盘阶段也
不因为新增统计而额外输出行。`caa/secid/sno/asn/tst` 始终取触发这张快照的事件。

例如按重放顺序出现：

1. 卖单 A 挂量 10；
2. 买单 B 到达并模拟吃完 A；
3. F 成交 4；
4. F 成交 6；
5. 新订单 C 到达。

B 的快照包含模拟撮合后的盘口，真实统计仍为零；C 的快照才包含 `nts=2, cvl=10`。
不把后面的 F 提前计入 B，也不回写已经保存的快照。若文件以 F 结束而后面没有可输出
事件，最后一行 book 不一定包含全文件最终统计。这是原快照时机的结果，本轮保留。

`opx` 依赖完整单日输入：有开盘竞价 F 时取其首条价格，没有开盘成交时取后续首笔 F。
`lpr` 随每条 F 更新，包括竞价 F；模拟竞价结算不会再增加源成交统计。输入若从日中
开始，不能用截取片段的第一笔价格保证恢复真正的开盘价，当前程序仍要求完整单日输入。

## 修改位置

- [model.hpp](../include/model.hpp)：保存事件自身 ASN，扩展 Snapshot 的九个新增字段。
- [order_book.hpp](../include/order_book.hpp)：保存源成交统计和首笔/最新成交价。
- [order_book.cpp](../src/order_book.cpp)：初始化统计，在已验证 F 分支累计，拍快照时复制。
- [main.cpp](../src/main.cpp)：保留本事件 ASN，按固定 30 列写表头及数据。

两份输入表头和可选 events 导出的 12 列格式保持不变。现有命令行用法不变：
价格档读写现已独立封装，编译时也需要链接 `price_levels.cpp`，接口说明见
[价格档读写封装](price_levels.md)。

```bash
clang++ -std=c++11 -pedantic-errors -Wall -Wextra -Wconversion \
  -Wsign-conversion -Wshadow -Werror -O2 \
  -I quant/my_obr/include \
  quant/my_obr/src/main.cpp quant/my_obr/src/order_book.cpp \
  quant/my_obr/src/price_levels.cpp \
  -o /tmp/my_obr_30

/tmp/my_obr_30 --order /path/to/order.csv --trade /path/to/trade.csv \
  --output /path/to/book.csv --events-output /path/to/events.csv
```

## 验证

验收覆盖严格表头/列序、九个新增字段、撤单自身 ASN、同价多笔成交、跨价成交、成交统计
不重复、首笔/最新价、竞价统计带入、零值与五档精度，以及统计失败的状态原子性。
使用临时合成输入和独立期望值；验证结果与实际命令记录在工作区 `my_obr_30_validation.txt`。
临时验证驱动、CSV 和二进制在提交前删除，不新增提交的单元测试套件。

| 验证 | 结果 |
| --- | --- |
| C++11 严格告警 Debug / Release / ASan+UBSan 构建 | 通过，`-Werror` 零告警 |
| ClangFormat、头文件独立/重复包含 | 通过 |
| 30 列逐字段独立期望值及失败路径 | 15 场景 × 3 构建，共 45 次通过 |
| 与扩展前版本对比 | 13 个合法场景的 21 列盘口投影及 events 输出一致 |
| 核心统计边界和原子性 | 30 场景通过，ASan/UBSan 无发现 |

验收环境为 Apple Clang 21.0.0、arm64 macOS；未启用该环境不支持的 LeakSanitizer。
这些结果来自合成场景，不代表用户真实行情或市价推断实验已经验证完整。
