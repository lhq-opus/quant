# my_obr 的 30 列 book 输出

当前使用约定的30列，包含事件元数据、源成交统计和五档盘口。
2026-09-10起改为[真实成交驱动](trade_driven.md)：订单只入簿，F扣双方，4扣单方；
快照按order/4起点到下一个起点前的F区间保存，继续使用C++11。

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

## 源成交与盘口

五个输出统计字段只在 `OrderBook::apply_trade()` 成功处理源F时改变。
预读全日历史的 `build_trade_map()` 仅用于沿用市价挂价实验，不扣量、不累计统计。

一笔F引用买卖两张订单，但笔数、成交量、成交额各只计一次。例如同一价位先后有
两条F成交4和6，`nts=2, cvl=10`，不能把一个价格档当成一笔成交。
撤单和订单事件均不增加这五项统计。

原模拟撮合及其内部统计已删除，只保留 `source_trade_count`、`source_trade_quantity`、
`source_turnover` 这一套真实成交统计。F同时减少双方原单余量和已挂档数量，按每张
原单保存的挂价扣量，不把两边都定位到TradePrice。

处理 F 时先检查原单引用、双方剩余量以及笔数/数量/金额的全部运算范围，再一起更新
两张订单登记、对应价格档和五项统计。溢出或其他校验失败不会留下只扣一侧或只更新
部分统计的状态。

## 快照时机与开盘价

每条连续阶段的order/4都作为快照起点，市价单也一样。处理完它后面的全部F、在下一条
order/4入簿前保存快照。`caa/secid/sno/asn/tst` 始终取起点事件，盘口与统计反映区间末
已重放的状态。F不单独出行；开收盘仍不导出行，但真实F会正常改变盘口及统计。

例如按重放顺序出现：

1. 卖单 A 挂量 10；
2. 买单 B 到达，只登记并挂本方档；
3. F 成交 4；
4. F 成交 6；
5. 新订单 C 到达。

B的快照在两条F处理完、C入簿之前保存，因此包含实际扣量后的盘口和 `nts=2, cvl=10`。
不是在B到达时提前执行未来成交，而是延后拍照。文件以F结束时，也会补保存最后一张
order/4对应的快照。相同CAA不合并事件，实际区间顺序始终由sequenceNo决定。

时段切换先结束上一阶段的待输出行，不把收盘F算进最后一张连续阶段快照；因此只导出
连续阶段的book，其最后一行仍不代表收盘后的全日最终统计。

`opx` 依赖完整单日输入：有开盘竞价 F 时取其首条价格，没有开盘成交时取后续首笔 F。
`lpr` 随每条F更新，包括竞价F；不再额外执行模拟竞价结算。输入若从日中
开始，不能用截取片段的第一笔价格保证恢复真正的开盘价，当前程序仍要求完整单日输入。

## 修改位置

- [model.hpp](../include/model.hpp)：保存事件自身 ASN，扩展 Snapshot 的九个新增字段。
- [order_book.hpp](../include/order_book.hpp)：保存源成交统计和首笔/最新成交价。
- [order_book.cpp](../src/order_book.cpp)：order挂单、F扣双方、4撤单及真实成交统计。
- [main.cpp](../src/main.cpp)：按CAA起点区间延后拍照，按固定30列写表头及数据。

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

## 历史验证：2026-09-09扩展30列

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
这些历史结果来自合成场景，不代表用户真实行情或市价推断实验已经验证完整。
2026-09-10的F驱动验证结果见[真实成交驱动](trade_driven.md)，不沿用旧模拟撮合结果作答案。
