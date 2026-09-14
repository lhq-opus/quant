# my_obr_v2 崩溃与逻辑审查

审查基准：`main` 的 `cc093587247641b15bec018fb00478bd3d912ff6`（提交说明 `tmp`）。
以下文件行号均对应这个提交。本轮只写报告，没有改动生产源码、架构、方法名或新增方法。

**最贴近你描述的原因已经复现：创业板暂存单部分撤销时被整条移出暂存表，
但仍保留没有绑定链表节点的 position；第二次撤销剩余数量时，在
order_book.cpp:263（买单）或 :281（卖单）崩溃。**

这能解释同一行的崩溃，但没有你的实际 core 堆栈和触发原单序号，不能断定你的那次
崩溃一定是这条路径。下面把已复现、已确认状态错误和条件性风险分开记录。

你已经修好的三处不再作为当前缺陷：

- `order_book.cpp:192`：买单撮合后已经减去 `remaining_quantity`。
- `order_book_market_order.cpp:90、112`：市价回放删除节点时已经同步删除索引。
- `order_book_market_order.cpp:117`：市价卖单消耗买盘后已经正确调用 `bids.erase(bid)`。
- 同类索引/删容器问题仍存在于 **CYB 回放**，具体见 A2、A4。

## A. 可能导致 coredump 的问题

### A1. [P1，已复现] 暂存单部分撤销后，第二次撤销解引用从未绑定的 position

**位置：**

- `src/order_book.cpp:151、168`：创建只含 price/side 的 `OrderInfo`。
- `src/order_book.cpp:159–162、172–175`：笼子外订单进入暂存区并直接返回，没有入链表。
- `src/order_book.cpp:91–95`：撤销暂存卖单，直接删除整个暂存项。
- `src/order_book.cpp:247–250`：另一个撤单入口同样直接删除暂存项。
- `src/order_book.cpp:263、281`：随后普通撤单分支解引用 position。

现在的暂存单索引可以用于记录 price/side，但其默认构造的 position **没有对应的
RestingOrder 节点**。首次撤单不扣暂存余量，而是直接 erase；原索引又没有同步删除。
因此“暂存表找不到、索引表找得到”的订单，下一次会被当成已经入簿的普通订单。

以原整数价格刻度构造的最小序列：

| 顺序 | 暂存买单场景 | 暂存卖单场景 |
| --- | --- | --- |
| 1 | 卖单 #1：100000 × 10 | 买单 #1：100000 × 10 |
| 2 | 创业板买单 #2：103000 × 100，超过 102%，暂存 | 创业板卖单 #2：97000 × 100，低于 98%，暂存 |
| 3 | 撤 #2 的 40，合法余量应为 60 | 撤 #2 的 40，合法余量应为 60 |
| 4 | 再撤 #2 的 60 | 再撤 #2 的 60 |

第 3 步实际状态均为 `pending=0, index=1`；第 4 步的 UBSan 栈分别为：

```text
std::__list_iterator<RestingOrder>::operator->
OrderBook::apply_cancel(Trade&) order_book.cpp:263  // 买
OrderBook::apply(Trade&)        order_book.cpp:98

std::__list_iterator<RestingOrder>::operator->
OrderBook::apply_cancel(Trade&) order_book.cpp:281  // 卖
OrderBook::apply(Trade&)        order_book.cpp:98
```

诊断为 `member call on null pointer of type std::__list_node_base`，两个进程均退出 134。

**保持现有方法的修正方向：** 在上述已有撤单分支内扣减暂存单 quantity；
余量为零时才删除暂存项与对应索引。仍在暂存区的订单继续走暂存逻辑，不解引用 position。
这里应修正业务状态，不能只靠 position 判空后 return，否则会继续漏撤数量。

### A2. [P1，已复现] CYB 回放仍把 bids 的迭代器传给 asks.erase

**位置：** `src/order_book_cyb.cpp:124–138`，特别是第 138 行：

```cpp
BidLevels::iterator bid = bids.find(bid_info->second.price);
// ...
if (bid->second.total_quantity == 0) {
    asks.erase(bid);
}
```

这是错误容器的迭代器操作。它可能先破坏树结构，稍后才在 snapshot 或 position
访问处暴露，不一定当场在 erase 这一行崩溃。

按你当前 98% 暂存口径复现：

1. 买盘 #1：100000 × 10；买盘 #2：99000 × 20。
2. 创业板卖单 #3：97500 × 20，暂存。
3. 卖单 #4：100000 × 10 吃完 #1，随后对应 F 到达。
4. 买一变成 99000；97500 已不低于 99000 的 98%，真实 F 为 #2 与 #3 成交 20。
5. 下一张委托触发 `replay_CYB_trades`。

ASan 报告：

```text
heap-use-after-free
释放位置：OrderBook::replay_CYB_trades  order_book_cyb.cpp:138
读取位置：OrderBook::fill_snapshot_levels order_book_snapshot.cpp:13
```

**修正方向：** 在原方法中改为 `bids.erase(bid)`。市价文件里的这一处你已经修了，
CYB 文件中的这一处还没有。

### A3. [P1，已确认状态错误及无效访问路径] 市价余量实际挂在 -1 档，但索引记录真实成交价

**位置：**

- `src/order_book.cpp:111`：市价单索引 price 初始为 `DROP_SIGNAL=-1`。
- `src/order_book_market_order.cpp:59`：把该索引复制到局部 `order`。
- `src/order_book_market_order.cpp:127、135`：余量放入 `bids[order.price]` / `asks[order.price]`。
- 同文件 `:131、139`：索引却写成 `trade_price`。

实际观测：市价买单 100，成交 50 @ 100000，下一张委托触发回放后：

```text
index.price = 100000
余量实际所在档位 = -1
bids.count(100000) = 0
```

随后撤销该余量：

- `order_book.cpp:261` 用 100000 查找档位，得到 end。
- `:263` 的 position 此时可能仍有效，因为它指向 -1 档的节点。
- `:264` 却解引用 end 来扣档位量。
- 若碰巧存在 100000 档，则会扣错档位量；全撤时还可能用该档的链表删除另一链表的节点。

所以这一处不一定崩在 position 行，也可能在后一行或 erase 时崩溃。
本机该最小场景 **没有触发 ASan 报错**；报告依据是已观测的档位/索引不一致及源码路径，
不把它写成已复现 coredump。

**修正方向：** 原回放方法里，余量入簿的 key 与写入索引的 price 必须使用同一个
最后实际成交价格；不能继续用市价单最初的 -1。

### A4. [P1，已确认悬空索引] CYB 回放删除 list 节点后没有删除索引

**位置：** `src/order_book_cyb.cpp:110–113、131–134`。

这两处只调用 `orders.erase(position)`，没有删除 `ask_info` / `bid_info` 对应的
`order_info_map` 项。position 指向的节点已销毁，索引中保存的迭代器随之失效。

已实际验证：暂存买单 20 股通过真实 F 全部成交后，被消耗的可见卖单索引仍然存在。
这确认了悬空索引；该独立场景没有再合法引用已全成原单，因此没有把它冒称为第二次
解引用已经崩溃。若后续内部回放重复处理或错误分派到这个索引，map 的存在判断无法保护 position。

**修正方向：** 在原有两个删节点分支同步删除对应索引。
`order_book_market_order.cpp:90、112` 已经是你做好的同类修正。

还应注意 `apply_limit_order` 在第 151 行预先登记索引：来单全部撮合时没有进入
余量入簿分支，也没有清除这个未绑定 position 的索引。这是另一种“存在索引但没有节点”，
不能与“已经删过节点的悬空 position”混为一谈。

### A5. [P1，静态确认] 第一条订单读取未初始化的 trading_session

**位置：** `include/order_book.hpp:62`、`src/order_book.cpp:7、13`。

成员没有初始值，构造函数只初始化累计量额，首次 `apply(Order&)` 却立刻读取阶段，
可能错误判断是否需要 `finish_call_auction`。这是独立的未定义行为，不涉及非法输入。

**修正方向：** 在现有构造函数初始化阶段。上述崩溃驱动为隔离此问题，只在驱动中
把初始阶段显式设为 ContinuousTrade，生产代码保持原样。

### A6. [条件性风险，未认定为这次 core 根因] 其他未入簿/空簿访问

- `order_book_cyb.cpp:29–36`：两个独立 if；若一条 F 的买卖两侧都仍在暂存表，
  同一 F 被加入缓存两次。随后 `:99–107` 只区分买侧是否暂存，仍把暂存卖侧当作
  有有效 position 的可见卖单。该条件成立时既可能重复处理，也可能直接访问未绑定迭代器。
  本轮未用完整、独立的行情事件序列复现这一组合，故作为条件性风险列出。
- `order_book_market_order.cpp:80–84、102–106`：市价回放默认对手单一定在可见簿中；
  若对手仍是本实现尚未激活的创业板暂存单，其索引虽存在，position 仍不可解引用。
  这里同样需要在现有回放分支内明确暂存单的处理职责。
- `order_book_cyb.cpp:44–52`：有缓存 F 的撤单分支无条件读取两侧 begin。
  例如暂存买单的 F 只消耗卖侧，买侧可能根本没有可见档位，此时仍读取 `bids.begin()->first`。
  单边空簿是正常状态；不能把它当作非法 CSV。
- `order_book.cpp:119、123`：BBO 直接读取本方 begin。若调用时本方无档位，同样无效；
  是否接受这种 BBO 事件取决于当前数据业务前提，不能仅凭这两行认定实际出现过。
- `OrderBook` 默认可复制，但 `OrderInfo::position` 不会因为 list 被复制而自动改指向副本。
  当前 main 没有复制 OrderBook，因此这不是现有调用链的实证原因；应避免在外层按值复制。
  Snapshot 的 vector 值复制没有发现这一问题。

## B. 已确认的实现问题

### B1. [P1，CLI 已复现] 快照从未变为 Ready，输出只有表头

**位置：** `order_book_snapshot.cpp:53、72、79–84、89–97`；`order_book.cpp:419–422`。

两个 make_snapshot 都设 Pending，整个 src 没有任何把状态设为 Ready 的语句。
update_previous_snapshot 仅填字段，finish 也只是调用它。
pop_snapshot 遇到队首 Pending 就返回 false。

完整 CLI 输入两条不成交的连续竞价限价买单，成交文件只有表头：

- 预期：一行表头、两行委托快照。
- 实际：进程退出 0，book.csv 只有一行表头。

同时，每张新委托/撤单继续 push_back，前面的 Pending 阻止弹出，快照内存会持续增长。

**修正方向：** 在现有 apply、回放、update/finish 等方法中补齐明确的事件完成与 Ready 转换。
普通未撮合单可以直接完成；需要真实 F 确认的单必须等该组处理完。
不能简单让任意第一条 F 到来就 Ready，否则多笔成交只输出了一部分。

### B2. [P1，已复现] 集合竞价成交没有累计量额，也没有实际扣盘

**位置：** `order_book.cpp:68–84、301–306、309–355、419–422`。

竞价 F 在 apply 中只更新 opening_price、trade_count、last_trade_price，
没有累计本阶段成交数量、金额，也没有扣双方订单。

开盘转连续时，finish_call_auction 使用的是 `cumulative_trade_quantity`。
当天只有竞价 F 时它仍是 0，因此 execute_auction_trade 执行零次。
收盘又没有对应的收尾调用；EOF 也不会处理竞价。

独立场景：竞价买卖各 100 股，真实成交 100 @ 100000：

| 阶段 | 预期 | 实际 |
| --- | --- | --- |
| 开盘 F 后转连续 | 两个原档位删除，cvl=100，cto=10000000 | 两档各残留100，cvl=0，cto=0 |
| 收盘 F 后 EOF | 两档删除，cvl=100，cto=10000000 | 两档各残留100，cvl=0，cto=0 |

**修正方向：** 仍使用你的竞价方法，确保价格和 quantity 来自对应竞价阶段的 F，
在阶段切换及 EOF 把本阶段成交实际扣盘一次。不能把全日累计量当成这次竞价量。
如果先在 F 时累计量额，还要避免 execute_auction_trade 再把同一成交统计一次。
同样需要覆盖阶段切换由 Trade 而非 Order 触发的入口。

### B3. [P1，已复现] 普通限价单成交笔数计了两次

**位置：** `order_book.cpp:411–414` 与 `:75–76`。

execute_order_at_price 推演时递增 trade_count，随后真实 F 又递增一次。

实际场景：卖单 100，买限价 40，真实 F 一条、成交 40：

```text
预期：ask=60, cvl=40, nts=1
实际：ask=60, cvl=40, nts=2
```

这里准确的问题是 **笔数双计**；当前普通限价路径的量额没有在 apply(F) 再加一次，
不能笼统说这条路径的所有统计都双计。成交最新价也分别被推演与真实 F 写入。

**修正方向：** 在现有方法里明确推演和真实 F 各负责什么；真实成交笔数只保留一个
计数入口。某张真实 F 与推演循环次数不能天然视为两次不同成交。

### B4. [P1，市价已复现，CYB 静态确认] EOF 没有回放待处理市价/CYB 成交

**位置：** `order_book.cpp:419–422`；`order_book_market_order.cpp:30–36`；
`order_book_cyb.cpp:26–39`。

两种特殊成交先缓存，通常等后面的 Order/Cancel 才回放；finish 却只更新快照。

实际场景：卖单 100，市价买单 40，F 成交 40，立刻 EOF：

```text
预期：ask=60, cvl=40, pending_market_order_trades=0
实际：ask=100, cvl=0, pending_market_order_trades=1
```

**修正方向：** 在现有 finish 中处理尚未回放的特殊成交和尾部快照。
调用顺序须保证同一 F 不被市价与 CYB 路径重复消耗；单纯 update 快照不能完成结算。

### B5. [P1，已确认状态错误] CYB 原单余量、激活与快照更新未闭合

**位置：** `order_book_cyb.cpp:99–141、7–16`；`order_book.cpp:159–175`。

- replay_CYB_trades 只扣可见对手单，不扣暂存单自身 quantity，也不在全成时删除暂存项。
  实际一张暂存买单已成交完 20，回放后仍为 `alive=1, quantity=20`。
- 进入暂存区后，没有重新检查范围并把合格余量入簿的执行路径。
  两个 priority_queue 成员也没有参与这项处理。即使行情 F 告诉你暂存单已经被激活成交，
  部分成交后的剩余量仍不会恢复到五档。
- 由下一条 Order 触发 CYB 回放时，handle_pending_CYB_limit_order(Order&) 只回放、clear，
  没有更新上一张快照。此前相关 F 因至少一侧有暂存原单而跳过了
  `order_book.cpp:78–81` 的快照更新，因此旧事件快照会保留回放前的盘口。
  这是独立于“当前没有 Ready”的时点问题，补上 Ready 后仍需处理。

**修正方向：** 在现有 CYB 回放及处理方法中扣清暂存原单数量，完成时清理状态；
按你已采用的范围规则把合格余量放入正确档位并记录真实 position。
旧事件相关 F 的回放和快照更新应在下一张事件生成自己的快照之前完成。

### B6. [P2，静态确认] 市价撤单把最后实际成交价覆盖为撤单价

**位置：** `order_book_market_order.cpp:64–72、122`。

循环在判断 Cancel 之前就执行 `trade_price = trade.price`。
该输入解析器将撤单 price 保持为 0，因此“先有 F、后有撤单”会把实际成交价覆盖为 0。

例如市价 100，成交 40，撤销 20，仍有 40 需要按原规则处理；
此时 remaining_quantity=40、trade_price=0，余量入簿条件不成立，这 40 被漏掉。

**修正方向：** 在原循环中只用 Normal F 更新最后成交价；撤单只更新撤销量和撤单标志。
这与 A3 是两个独立问题：A3 是档位 key 不一致，这里是定价变量先被覆盖。

### B7. [P2，条件性数据丢失] 一条缓存事件不能处理时，整批后续 F 被丢弃

**位置：** `order_book_cyb.cpp:86–96`，以及调用方 `:14–16、66–73`。

replay_CYB_trades 一旦碰到引用不存在或任一侧是 DROP_SIGNAL，就 return 整个函数；
外层接着 clear 整个 vector。这样本条以及它后面的其他 F 都被移除，即便后面的订单可以处理。

输入合法也不能排除它：市价与暂存单的路由、提前模拟消耗、先前错误的状态清理都会使
内部状态不符合这里的假设。不能把 return 当成业务结算成功。

**修正方向：** 在原方法中明确哪些 F 已由其他路径处理、哪些仍需保留或执行；
既不无条件丢弃整个尾部，也不只把 return 换成 continue 后忽略本条成交。

### B8. [P2，严格编译已验证失败] 仍有不属于 C++11 的初始化写法

**位置：** `order_book.cpp:111、151、168`；
`order_book_market_order.cpp:131、139`。

例如：

```cpp
OrderInfo{price : trade_price, side : EventSide::Buy, position}
```

这是 GNU 旧式指定成员初始化，还混用了指定/非指定初始化。
本机 `clang++ -std=c++11 -pedantic-errors` 对这些位置报告 15 个错误。
不加 pedantic-errors 时 Clang 以扩展接受，所以“能编出运行程序”和“符合 C++11”是两件事。

**修正方向：** 在原方法的初始化位置使用成员声明顺序的 C++11 聚合初始化；
未入簿的 position 仍需要配合 A1/A4 的状态处理，改语法本身不能修复崩溃。

## C. 本轮没有归咎于输入格式的事项

- 仍以合法输入为前提，不建议新增表头、列数、格式猜测、解析回退等检查。
- 同 CAA 委托优先来自既定排序约定；若它打断相关 F 与来单的组顺序，依然存在
  提前回放/快照归属风险。此前用户排除过排序调整，本报告不把它当作新发现的唯一根因。
- fill_snapshot_levels 会补齐双侧五档，writer 的五档索引没有发现独立越界原因。
- std::list 插入其他节点、std::map 插入其他档位，本身不会让现有活动节点的 position
  失效。这里重点是从未绑定、节点已删除、容器被错误删除和索引价格不一致。
- docs/replay.md 是上一版说明，仍描述当前已不存在的方法和 Ready 确认流程。
  本次结论以 cc09358 的源码和复现为准，不能沿用该文档的“已通过”结论。

## D. 验证证据与范围

运行环境：macOS arm64，Apple Clang 21。生产 7 个源/头文件均未修改。
临时驱动、输入 CSV、输出 CSV 和二进制不提交。

严格语法检查（工作区根执行），结果 exit 1：

```bash
clang++ -std=c++11 -pedantic-errors -Wall -Wextra \
  -Iquant/my_obr_v2/include -fsyntax-only quant/my_obr_v2/src/*.cpp
```

为执行原源码的运行时审查，崩溃驱动允许其现存编译器扩展（quant 根执行）：

```bash
clang++ -std=gnu++11 -g -O0 -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I my_obr_v2/include obr/.v2_crash_market_audit/driver.cpp \
  my_obr_v2/src/order_book.cpp my_obr_v2/src/order_book_market_order.cpp \
  my_obr_v2/src/order_book_cyb.cpp my_obr_v2/src/order_book_snapshot.cpp \
  -o obr/.v2_crash_market_audit/driver
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  obr/.v2_crash_market_audit/driver held_buy_cancel
```

`held_sell_cancel`、`cyb_wrong_container` 使用同一驱动分别运行；三者均确认运行时错误。
驱动显式指定初始交易阶段，只为了隔离 A5；没有在生产方法中补检查或改变执行逻辑。
完整 CLI 的 Pending 问题则直接使用原 main，未对 OrderBook 做这种初始化干预。

| 检查 | 结果 |
| --- | --- |
| 暂存买单、卖单分两次撤销 | 两个 position 空节点访问，分别定位 :263、:281 |
| CYB 错容器删除 | ASan use-after-free，释放源 :138，读取点 snapshot :13 |
| 市价余量价格 | 实际档位 -1、索引价 100000，确认状态不一致；本机未报 sanitizer 错误 |
| CYB 全成 | 对手索引残留；暂存原单仍保留原数量 |
| 开盘/收盘竞价 | 真实 F 后量额为零、已成交订单仍在簿 |
| 普通限价一条 F | nts 实际 2，应为 1 |
| 市价 F 后 EOF | 对手未扣，缓存仍有 F |
| 两条普通限价的完整 CLI | book.csv 实际只有 1 行，应为 3 行 |
| 严格 C++11 | GNU 指定成员初始化导致检查失败 |

详细日志保存在工作区根：

- `my_obr_v2_crash_market_validation.txt`：崩溃栈及 5 个事件序列。
- `my_obr_v2_audit_core_probe.txt`：竞价、成交笔数和 EOF 的预期/实际值。
- `my_obr_v2_audit_pipeline_validation.txt`：完整 CLI 的表头-only 输出。
- `my_obr_v2_audit_strict_build.txt`、`my_obr_v2_audit_extension_build.txt`：两种编译模式结果。

未获得真实 core 文件及崩溃时原单引用，故本报告提供已验证候选根因和代码问题，
没有声称已经定位你那一次实际崩溃的唯一事件。
