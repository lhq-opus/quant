# 逐单盘口、独立输入类型与模拟成交统计

`bids/asks` 的价格档内容为逐单 FIFO 队列。限价单和本方最优 U 单处理完成后，
即可读取包含模拟成交笔数、最新成交价等信息的 `Snapshot`，不必等待后续 F。
市价单沿用当前根据关联成交/撤单历史推断的实验分支。

代码仍使用 C++11，保留原有函数划分，`apply_market_order` 没有拆分。按用户指定，
不新增数据溢出、空盘口、输入校验或异常恢复框架；输入完整、合法、引用正确且运算可表示
是本轮前提。已有六项局部修复继续保留。

## Order 和 Trade 分开处理

输入现在有两个独立类型，解析后保持各自类型直至进入盘口：

| 类型 | 来源与专属字段 |
| --- | --- |
| `Order` | order.csv；`side`、`order_type`、`order_appl_seq_num` |
| `Trade` | trade.csv；`trade_type`、`trade_appl_seq_num`、`bid_appl_seq_num`、`offer_appl_seq_num` |

两者各自保存 CAA、时间、通道、`sequence_no`、价格、数量和快照开关。
`TradeType::Normal` 对应 F，`TradeType::Cancel` 对应撤单 4；撤单也属于 `Trade` 输入。
`trade_appl_seq_num` 标识成交/撤单记录本身，撤单定位使用非零的买方或卖方原订单引用。

`OrderBook` 提供以下重载，由 C++ 根据实参类型选择：

```cpp
void apply(Order& order);
void apply(const Trade& trade);
Snapshot make_snapshot(const Order& order);
Snapshot make_snapshot(const Trade& trade);
```

`apply(Order&)` 直接读取委托自身的 `trading_session`，调用原限价/U/市价/竞价函数。
`apply(const Trade&)` 对撤单调用 `apply_cancel`；普通 F 继续跳过，以免重复应用模拟成交。
原 `need_handle` 标志已移除。`EventType` 只保留为快照及 CSV 的来源标签，不再有统一的
`Event` 输入对象、基类或中间转换。

main 通过 `CsvReplayStream::read_line` 每次取得一条原始记录，在循环内调用
`parse_order` 或 `parse_trade`，然后调用对应的 `apply` 重载。

阶段切换使用前一条已处理记录的阶段和当前阶段判断：离开开盘竞价时，先结算再应用当前
记录；文件结束时若仍在开盘竞价则结算。原来的下一元素 `index + 1` 读取已移除。
此次不调整市价推断规则。

## 按 CAA 模拟逐行推送

两份输入文件必须各自已经按**数值 CAA 非降序**排列。`CsvReplayStream` 打开两份文件、
跳过表头，在每路保存一条待处理原文及其 CAA。每次 `read_line`：

1. 比较两条待处理记录的 CAA，返回较小的那条原文和来源标记。
2. CAA 相同时先取 Order，同一文件内保持物理行序。
3. 只补读刚取出记录的那一路；一路结束后继续另一条流，两路结束时返回 `false`。

CAA 通过整数比较，因此 `9` 排在 `10` 前面；原始字符串原样保留用于输出。
`sequence_no` 仍被解析和导出，但不参与调度，也不再全量排序。这是用户指定的到达顺序
模拟规则，不是新增的交易所业务排序规则。程序不检查输入是否有序。

主循环的读取、转换和应用过程如下，实际代码还保留阶段结算和逐条输出：

```cpp
for (;;) {
  if (!input.read_line(line, is_order)) {
    break;
  }
  const std::vector<std::string> columns = split_csv_line(line);
  if (is_order) {
    Order order = parse_order(columns);
    order_book.apply(order);
  } else {
    const Trade trade = parse_trade(columns);
    order_book.apply(trade);
  }
}
```

读取层的 `line` 和 `is_order` 只表示原文及来源，不是统一的业务 Event。每轮循环只向
盘口推送一个 `Order` 或 `Trade`；另一条待处理记录留到后续循环。

`build_trade_map_from_csv(order_path, trade_path, order_book)` 是独立的预处理方法，
在主循环前完整扫描两份 CSV。订单行只推进扫描，成交/撤单行解析成 `Trade` 后调用
原 `OrderBook::build_trade_map`。关联历史按 trade 文件中的行序保存，不再按
`sequence_no` 重排。预处理不调用 `apply`，不增加盘口订单或成交统计。
预处理结束后，main 创建新的 `CsvReplayStream`，从两份文件开头重新模拟推送。

book 和 events 输出流各打开一次并写一次表头。每次解析后先写当前 events 行，再
`apply`；需要快照时立即生成一个 `Snapshot` 并写入 book 输出流。程序不再保存
完整的 Order、Trade 或 Snapshot 数组，也不强制逐行 flush。输入缓存规模不随记录数
增长；历史 map 和盘口仍保存各自所需的状态。

## 盘口现在保存什么

原实现已经保存所有价格档，只是在快照和五档市价分支中限制为五档。缺少的信息是同一
价格内有哪些订单、各剩多少量、谁先进入队列。

现在的数据关系为：

```text
bids / asks
  price -> BookLevel
             total_quantity: 该档全部订单剩余量之和
             orders: 同价 FIFO 链表
                       RestingOrder { order_appl_seq_num, remaining_quantity }

order_price
  原订单 ASN -> OrderInfo { price, side, position }
                                     position 指向该订单的链表节点
```

同价订单按当前重放顺序插入队尾，撮合从队首开始。当前重放顺序按上述数值 CAA 归并，
同一输入文件内保持行序；没有新增数据完整性检查。

价格档缓存 `total_quantity`。撮合和撤单同时维护订单剩余量与档位总量，因此生成五档
快照只读取每侧前五档的缓存总量，不需要再扫描全簿或这些档位内的所有订单。

节点完全成交或全撤后，从链表和订单索引删除；整档没有剩余量时才删除价格档。
撤单通过原订单索引中的迭代器直接定位节点，不会把同价的其他订单当成被撤单。
因为这些迭代器属于当前盘口实例，`OrderBook` 禁止拷贝，避免复制后仍指向原实例的节点。

## 限价单和 U 单

`apply_limit_order` 保留原来的买卖方向分支和价格判断，在每个可成交价格档内逐单配对。
每次配对数量取来单未成交量与对手队首订单剩余量的较小值；来单还有余量时继续下一单，
当前档成交完后才进入下一价格档。来单最终未成交量排入自身限价档的队尾。

例如卖一 `10.0000` 有两张订单，先到 A 剩余 3，后到 B 剩余 4。一张限价买单买入 5：

| 配对 | 成交量 | 剩余状态 |
| --- | --- | --- |
| 来单与 A | 3 | A 移除，来单剩 2 |
| 来单与 B | 2 | B 剩 2，来单完成 |

在处理这张买单时，模拟成交笔数立即增加 2、累计量增加 5、最后成交价为 `10.0000`。
虽然只消费一个价格档，也不能只算成一笔。之后收到的源 F 继续沿用原跳过逻辑，不重复
扣量或重复更新统计。

`apply_BBO_order` 仍把 U 解释为**本方最优**。先锁定到达时本方最优价，再用 `Order` 副本
按这个限价调用限价处理，原委托的 `price` 不被改写。正常未交叉盘口下，U 只是排入
本方最优档队尾，不会产生新成交，此时笔数和最新价保持原值，也可以立即生成快照。

## 市价单如何适配

市价单原先的分支顺序、历史推断条件和 `generate_snapshot` 开关继续保留：

- 最优档总量足够时直接处理；这里比较的仍是**整档总量**，不是第一张订单的数量。
- 历史只有一条撤单时，仍按原实验规则挂本方最优，加入同价队尾。
- 末条记录是撤单时仍走五档分支，五档指五个不同价格，每档可以成交多张订单。
- 固定最优价分支吃完一个对手价档后，把来单余量追加到本方同价队尾，保留原有订单。
- 跨价分支按价格顺序继续扫盘，各档内部也按 FIFO 配对。
- 历史为空时仍走此前保留的默认 `TradeAtBest`。

所有市价分支都同步维护队列与档位总量，正量订单配对也更新模拟统计。五档分支处理完
立即返回；`order_price = -1` 仍只作不入簿的待撤标记，后续撤单读取该标记直接返回。
本轮没有重新确定市价申报子类型，也没有用新的盘口容器替换这些实验判断。

## 集合竞价与统计

竞价选价继续使用原框架，只把价格档数量读取改为 `total_quantity`。结算时在原
`finish_call_auction` 内，按买卖两侧的价格顺序和同价 FIFO 队首成对扣量，每次配对
使用选定的竞价价格记一笔。两侧各扣一次数量，成交统计只累计一次。

例如同一竞价价格下，买队列数量为 `[3, 4]`，卖队列为 `[2, 5]`，依次配对成交
`2、1、4`，模拟成交 3 笔、总量 7；不会把整场竞价记成 1 笔，也不会因同时扣买卖两侧
把成交量算成 14。原竞价选价规则仍然保留，流式输入改造没有扩展收盘竞价处理。

`Snapshot` 保存的模拟统计如下：

| 字段 | 含义 |
| --- | --- |
| `trade_number` | 累计模拟订单配对笔数 |
| `last_price` | 最近一次模拟配对成交价 |
| `opening_price` | 第一次模拟配对成交价，之后保持不变 |
| `cumulative_trade_quantity` | 累计模拟成交量，每次配对计一次 |
| `cumulative_turnover` | 累计模拟成交额，按配对价格乘数量计算 |

未成交时这些统计初值为 0，价格和金额沿用原内部整数单位。每张快照保存当时统计的
值副本，后来的订单不会改写之前的快照。

这是**按一次订单配对计一笔**的教学模拟，依赖完整的初始盘口和正确的同价先后顺序，
没有验证它必然等于供应商拆分或汇总后的 F 记录条数。市价历史推断造成的模拟差异也仍然存在。

## 如何读取及修改范围

```cpp
order_book.apply(order);
Snapshot order_snapshot = order_book.make_snapshot(order);

order_book.apply(trade);
Snapshot trade_snapshot = order_book.make_snapshot(trade);
```

以上假设 `order` 和 `trade` 已完成读取；调用后可以直接读取快照的统计字段。两种
快照重载复用同一段五档投影代码，并分别复制原记录的 CAA、阶段和来源标签。
main 仍使用原来的 `generate_snapshot` 条件，普通 F 不产生输出行，市价分支原先关闭
快照的行为保留。

用户已选择只在内存 `Snapshot` 中保存新增统计。流式改造调整了 main 的读取和
写出方式，21 列 book 及 12 列 events 的格式、格式化方法保持原样。events 中 Trade 的
方向/委托类型写空字段，普通 F 的原单列写 0，撤单的原单列写被撤订单引用；撤单价格仍
沿用此前的 0。`trade_appl_seq_num` 暂不增加到导出列。本次没有做性能基准。

本次流式改造只修改 `src/main.cpp` 和本文档；两个头文件及 `src/order_book.cpp` 保持
原样。实际命令与结果记录在工作区 `my_obr_stream_validation.txt`；临时验证驱动、mock
和二进制不提交。

## 逐单盘口阶段的验证记录

- 30 组核心场景分别在 Debug、Release、ASan/UBSan 下运行，共 90 组运行全部通过。
  覆盖双侧 FIFO、指定订单撤量、U 定价、跨档最新价、市价原分支、五价十单、深档晋升、
  竞价配对、F 不重复累计以及快照值独立性；逐事件核对档位总量、队列和索引一致。
- 核心及临时驱动在 C++11、`-pedantic-errors` 和严格告警 `-Werror` 下编译通过；
  ASan/UBSan 无诊断，运行时使用 `ASAN_OPTIONS=detect_leaks=0`。
- 两个头文件独立及重复包含检查、ClangFormat、`git diff --check` 均通过。
- 完整程序编译链接通过，仅有未修改的 `main.cpp` 中原整数转 `double` 精度告警。
  该阶段未运行 main 的完整文件重放，未验证 CSV、非法输入或数值溢出。
  详细记录在工作区 `my_obr_fifo_validation.txt`。

## Order/Trade 拆分的验证记录

以下记录来自此前按 `sequence_no` 排序的类型拆分阶段，不代表当前流式输入接受乱序 CAA。

- 34 组核心场景在 Debug、Release、ASan/UBSan 下全部通过。其中 30 组回归原 FIFO、
  市价和统计行为，4 组检查独立类型、重载、快照元信息及成交自身 ASN 与撤单引用分离。
  核心和驱动使用严格 C++11 与 `-Werror` 编译，无告警。
- 7 组完整程序回放在 Debug、ASan/UBSan 下全部通过，输入包括两表各自乱序、两种类型
  的尾段、F 跳过、开盘转连续及相同序号的调度；输出与手算的 12 列 events、21 列 book
  逐字一致。完整构建保留原价格格式化处整数转 `double` 的一条告警。
- 两个头文件独立及重复包含、ClangFormat、`git diff --check` 均通过。独立差分复核确认
  市价长函数和其他撮合函数只有参数类型与名称适配，算法保持原样。
- ASan/UBSan 运行无代码诊断；当前平台不支持泄漏检测，使用 `detect_leaks=0`，未验证
  内存泄漏。没有增加非法输入或溢出检查，也未据合成数据声明真实行情恢复正确。
  详细记录在工作区 `my_obr_types_validation.txt`。

## 按CAA逐行推送的验证记录

- Debug、Release、ASan/UBSan 下，12 组整程序回放、13 组读取顺序检查和 4 组预处理及
  即时统计检查全部通过。覆盖数值 CAA 的 `9 < 10`、同 CAA Order 优先、与 `sequence_no`
  相反的顺序、两路尾段、单流、开盘阶段切换、F 跳过和撤单。
- 四组市价场景验证预扫描后的盘口和统计仍为空，完整关联历史可用于原跨价、仅撤单、
  同价和五档末撤分支；主循环每条记录及输出都符合手算结果。
- 整程序 book/events 与手算的 21/12 列输出逐字一致；构建只保留原
  `format_fixed_point` 中整数转 `double` 的一条告警。地址/UB 检查无诊断，未启用当前
  平台不支持的泄漏检测，未测试非法输入或数值溢出。
- 格式及差分检查通过；两个头文件和核心 cpp 与前一提交逐字一致。main 中没有全量
  Order、Trade、Snapshot 数组或排序调用。详细命令见 `my_obr_stream_validation.txt`。
