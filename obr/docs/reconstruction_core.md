# C++ 订单簿：真实成交驱动的重放

当前 C++ 直接读取 `order.csv` 和 `trade.csv`，不需要 Python 生成 event。
使用 C++11、标准库、定点整数和三个直接的 map，不实现输入兼容层或错误恢复框架。

## 1. 从哪里开始读

- `include/obr/domain.hpp`：价格、数量、三种 Event、Snapshot。
- `src/replay_event_main.cpp`：命令行、CSV、事件合并排序、交易阶段、快照区间、输出。
- `include/obr/order_book.hpp`、`src/order_book.cpp`：订单索引、价格档与状态变化。

建议先看 `parse_event()`，再看 `OrderBook::apply()`，最后看 main 的
`pending_index` 循环。详细运行命令见 [编译执行指南](build_and_run.md)。

## 2. 两份 CSV 怎样合并

输入使用项目约定的原始表头和列顺序。共同读取：

| 原始列 | Event 字段 | 用途 |
| --- | --- | --- |
| clockAtArrival | caa | 原样保留，作为 order/cancel 快照标签 |
| sequenceNo | sequence_no | 转为64位整数，作为事件排序键 |
| TransactTime | transaction_time | HHMMSSmmm，判断交易阶段 |
| ChannelNo | channel_no | 原订单引用的频道作用域 |

order 转成 `EventType::Order`，读取 `Side,OrderType,Price,OrderQty,ApplSeqNum`。
trade 中 `ExecType=F` 转成 `Trade`，`ExecType=4` 转成 `Cancel`，两者都保留。

成交读取 `TradePrice,TradeQty,BidApplSeqNum,OfferApplSeqNum`。撤单使用
`TradeQty` 和两个引用中非零的那个，不用预先补全方向和撤单价格。trade 自己的
`ApplSeqNum` 不是被成交或被撤订单的编号。

两份表先装进同一个 `vector<Event>`，再用 `stable_sort` 按整数 `sequenceNo`
排序。不会按 CAA 排序，不会按同一个 CAA 合并，不会过滤正常成交。
相同 sequenceNo 保留装入顺序：各表原始行序，order 在 trade 前。这个并列规则是
本次离线程序的确定性约定，不代表交易所额外提供了优先级信息。

## 3. 三个 map 就够了

```text
orders_: (ChannelNo, 原订单 ApplSeqNum) -> {方向, 实际挂价}
bids_:   价格从高到低 -> 聚合买量
asks_:   价格从低到高 -> 聚合卖量
```

订单索引负责“找到在哪一侧、哪一档”，价格档负责“这一档现在有多少”。
价格以0.0001元为单位保存在64位整数中。例如10.10元存成101000，写出10.1000。

这一版不另存每张订单的剩余量，不建立 FIFO。真实 trade 已经给出成交双方，
合法输入也保证不会超量；我们只需要把对应价格档的聚合量更新正确。

## 4. 连续阶段：order 不再产生推导成交

### order

- `OrderType=2`：以原始 Price 增加本方完整 OrderQty。
- `OrderType=U`：在到达时取本方最优价，记住该价并增加数量；本方为空时不挂档。
- `OrderType=1`：本次暂时沿用“只登记引用、不挂入本方价格档”的约定。
  非零 Price 是否代表供应商给出的有效挂价尚未确认，不能凭是否填价猜测市价子类型。

order 不修改对手盘，也不自行增加成交量。即使买价高于卖价，也先保留临时交叉状态，
由后续真实成交修正。类型1不会自行推断成交档数、成交量或自动撤单。

### 正常成交 F

`apply_trade()` 做三步：

1. 用 `(ChannelNo, BidApplSeqNum)` 找买单，以它原来的挂价扣除 TradeQty。
2. 用 `(ChannelNo, OfferApplSeqNum)` 找卖单，以它原来的挂价扣除 TradeQty。
3. 成交量累计一次 TradeQty，成交额累计一次 TradePrice × TradeQty。

例如买单挂10.20元、卖单挂10.00元，真实成交50股、成交价10.00元：
买盘10.20档减50，卖盘10.00档减50，成交额加500元。不能把买盘也从10.00档扣量。

未挂价的市价单在本方没有价格档可扣，但仍要扣对手单并记录成交。
代码不会把成交价反填为该市价单的挂价，因为成交价不等于剩余量的申报价。

### 撤单 4

用非零引用查原订单的方向和挂价，再扣除 TradeQty。撤单只改一侧，不增加成交统计。
U 单即使到撤单时本方最优价已经变化，仍扣到它到达时记住的原挂价。

以上扣量共用 `reduce_order()`，档位数量变为0就删除。输出只取五档，但内部维护全深度。

## 5. 快照为什么要晚一点输出

这里区分“内部状态变化”和“新增一行 snapshot”：F 会改变内部簿，但只有
order/cancel 开启新快照。CAA 来自起点事件，不来自区间里最后一笔成交。

```text
sequenceNo:    10          11        12          13          14
事件:         order A     trade     trade       cancel B    trade
快照区间:     [ A 的区间                       )[ B 的区间直到 EOF ]
输出 caa:      A.caa                             B.caa
```

处理到 cancel B 之前才输出 A，所以 A 的状态包含11、12两笔成交，但不包含B的撤量。
处理完B和14的成交，EOF 时输出B。没有成交的区间也输出一行，不能把相邻order合并掉。

`pending_index` 保存当前起点在 events 中的下标。每遇到下一条 order/cancel，
先从当前簿提取上一条快照，再应用当前事件。文件结尾补出尚未输出的最后一条。
无需缓存每笔成交或反复修改已经输出的快照。

区间严格按 sequenceNo 排好的事件顺序划分，CAA只是标签。即使两个起点CAA相同，
仍有两行；CAA与sequenceNo不一致时也不回到按CAA排序。
这是一种离线的“区间完成状态”，不是起点CAA那一瞬间的实时盘口。

输出行数 = order行数 + ExecType=4的trade行数。
每行使用原有22列、四位小数价格、空档留空，不新增成交行或虚构CAA。

## 6. 集合竞价保持原逻辑

开盘仍先累计order、应用撤单，阶段结束时统一筛选价格并扣量：

1. 最大可成交量，同时满足更优价全部成交、成交价至少一侧全部成交；
2. 同量候选按包含等价申报的买卖累计量差最小筛选；
3. 仍并列时采用该阶段真实成交价；真实价也加入候选集，可位于两个申报价之间。

不新增 reference_price。真实集合竞价F只提供实际成交价，不额外扣一次数量。
输入保证并列时的真实成交价有效，代码直接采用该价，不做有效性复查或抛异常。
该阶段最后一条order/cancel的快照仍显示统一结算后的盘口，保持原先的盘前结果。
收盘沿用同一套集合逻辑，开盘和收盘的实际价提示分别重置。

连续阶段的真实F与集合阶段的统一成交各自只累计一次，不能双计。

## 7. 当前边界与验证

仍限定单证券、单交易日、完整合法输入。引用订单应在按sequenceNo回放时已经出现。
TransactTime采用HHMMSSmmm数字，字段内不含逗号或引号；不添加其他CSV格式兼容。
价格最多四位小数、整数不溢出，输出目录由使用者准备，输出不得与输入同路径。

不做重复/缺口检测、非法输入恢复、每单余量校验、多标的调度、生产级保护。
也不做缺参检查、文件打开失败处理、超长小数截断或异常捕获。参数与文件可读写由
调用者保证；数字直接用标准库转换，非法输入不属于本 demo 的处理范围。
空盘口、市价空价格、扣完删除空档、不足五档和无集合成交仍是正常业务情况，保留分支。
市价非零Price和余量挂价语义仍需数据源说明，不能声称覆盖全部市价子类型。
Python工具本轮未修改算法，不再与C++保持相同的连续成交模型。

运行现有 `obr_validate_reconstruction_core` 验证核心；端到端验收用临时pandas数据
核对乱序合并、双边扣量、延迟成交、CAA区间、首尾、深档晋升和集合竞价回归。
验证器中的结果断言仅用于开发时核对算法，不是正式重放程序的输入校验。
不提交mock CSV，也不新增单元测试框架。
