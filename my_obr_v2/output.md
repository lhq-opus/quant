# my_obr_v2 崩溃与逻辑审查

## 本次修复：ce51d92 漏扣仍暂存原单的真实成交

对照 `5205be9 → ce51d92` 找到一处可复现的回归：
`replay_CYB_trades` 把非撤单特性组的 F 一律改成 `++trade_count`，
但 F 引用的订单可能仍在 `pending_limit_order_alive`，此前没有提前撮合。
这时必须按真实引用扣量；只加笔数会留下已经成交的幽灵挂单。

### 崩溃路径与前后版本对照

以下买向临时输入中，数量均为 100，CAA 严格递增，F 在下一张委托前到达：

| 顺序 | 事件 | 正确状态 |
| --- | --- | --- |
| 1 | 卖 A，10.25 | 卖一 A 100 |
| 2 | 买 B，10.46 | 等待本组真实 F |
| 3 | F：B 与 A 成交 100，价格 10.25 | A、B 全成并清理 |
| 4 | 卖 C，10.50 | 卖一 C 100 |
| 5 | 买 D，10.25 | D 不成交，挂买一 100 |
| 6 | 撤 D 100 | 删除 D |
| 7 | 新卖单 E，10.60 | 正常继续处理 |

该边界例按[2020 年创业板特别规定第 2.3 条](https://docs.static.szse.cn/www/disclosure/notice/general/W020200612831351578076.pdf)
的最小报价单位舍入构造：10.25 × 102% = 10.455，按分舍入为 10.46。
两份源码的简化比较都没有该舍入，所以内部暂存 B；旧版仍能通过真实 F 扣清 A、B。
这不是用户真实行情，也不表示本次已经扩展了 v2 的价格笼子规则。

`ce51d92` 漏掉第 3 步扣量，D 到达后会吃掉幽灵 A，D 被误判全成并删除索引。
第 6 步的合法撤单因此查到 `order_info_map.end()`，随后访问无效 `OrderInfo/position`。
卖向镜像使用买一 10.26、限价卖单 10.05，同样复现。

旧版两例的完整 30 列输出均符合独立预期；未添加断言的 `ce51d92` 在两例中都被
ASan 报出 `apply_cancel` 第 250 行的无效内存访问。临时断言副本进一步确认，
首次错误是撤单引用的 D 已被误删，而不是输入缺少原单。
本地平台是 Apple Clang/libc++；用户栈来自 Linux/GCC 13，停在后续 rank 插入。
已经确认近期变更存在崩溃回归，但尚未用用户原始输入证明它就是该 rank 栈的同一条路径。

### 最小修复

- 原 F 分支增加判断：任意一侧仍在暂存表时，调用现有 `execute_trade` 与 `record_trade`；
  已提前撮合的 F 仍只补笔数，撤单特性组继续按真实引用执行。
- 将 Cancel 判组循环中“每笔 F 之前”的空回放，移到确定普通前缀结束的位置。
  空回放昨晚已从只入簿变为直接撮合；若插在一张原单的多笔 F 之间，另一张同向暂存单
  可能抢先消耗后续 F 的对手量，使成交归错原单、后续合法撤单再次查不到索引。
- 确定撤单特性组起点后，先恢复普通前缀留下的合格余量再完成旧行；
  保留整组回放末尾的激活，以及特殊组首笔 F 的 CAA 和统计归属。

没有新增状态、业务方法或输入检查；27 个方法签名及头文件保持不变。
业务改动仅在 `order_book_cyb.cpp`，`order_book.cpp` 只同步两处注释。

验证通过 50 个针对场景和 16 条固定种子的混合事件流，共 32767 条事件、
23479 行、704370 个完整输出字段。覆盖买卖镜像、拆分成交、余量归属、
Order/Cancel/EOF 边界、普通前缀及撤单特性组、前缀余量入簿和连续解冻。
50 个针对场景同时通过旧版与修复版；修复版生产 CLI 的 C++11 强告警构建及
ASan/UBSan 回放通过。完整命令和证据保存在工作区根的
`cyb_recent_fix_validation.txt`、`cyb_recent_original_crash.txt`、`learning_plan.md`；
临时驱动、输入和二进制不提交。

## 上一增量：解冻单直接撮合，删除限价等待状态

按用户确认的顺序，`Order A → F(A1) → F(A2) → F(B1) → Order C`，
由 A 解冻的同向 B 的全部成交，会在下一 Order/Cancel 前收到。
本次在原方法中完成以下调整，原 27 个业务方法名、签名和文件分工保持不变：

- 删除 `pending_limit_order_appl_seq`、`pending_limit_trade_quantity`，
  以及 `held_trade/predicted_trade` 分流和待确认数量归零的判断。
- A 先完成自身撮合，原 CYB 激活循环再调用 `apply_limit_order` 直接撮合 B。
  多张同侧解冻单按价格、原到达次序处理；每张完成后重新检查新解冻的单。
  先移除冻结占位索引，再由原方法完成全成清理或余量入簿，避免留下无效 position。
- `execute_order_at_price` 的单侧撮合当场累计量额和 last price；真实 F 只补笔数，
  不重复扣盘或累计。双侧竞价结算保持只扣盘口，市价仍按真实 F 定价并完整统计。
- 沿用 `pending_cyb_group` 等待连续竞价委托组，在下一 Order/Cancel 或 EOF 完成
  snapshot；不再需要保存限价待确认数量。A 与 B 的量额、笔数和最新价都归 A 的行。
- 非市价 CYB F 仍由原缓存保留接收顺序，以识别 `F1 → F2 → Cancel` 特性组。
  普通前缀只补笔数；识别撤单触发组后，先完成旧行，再执行其真实 F，
  这部分成交仍归首笔 F 元信息的 snapshot，包含后到 Cancel 处理后的盘口。

未新增状态或业务方法；输入输出列、CAA 归并、市价行保留策略均未改动。
全部连续竞价委托行（包括无成交的委托）统一等到组边界完成，这是删除等待数量后的输出时机。
继续使用 C++11 和中文注释，不增加输入格式防御逻辑。

验证通过 68 个合法场景：497 行、14910 个完整 CSV 字段与独立预期一致，
34445 项即时统计、原单余量、position、FIFO、档位汇总及快照状态检查通过。
覆盖买卖镜像、部分/全部成交、F 拆分笔数、同侧多价/同价/连续解冻、
Order/Cancel/EOF 边界、撤单特性组及普通前缀、市价余量/待撤、U 单和开收盘竞价。
严格 C++11、强告警 `-Werror`、ASan/UBSan、方法签名和格式检查通过。

实际命令（工作区根；临时驱动、CSV 及二进制在提交前删除）：

```bash
python3 quant/obr/.cyb_cleanup_probe/run.py corrected
clang++ -std=c++11 -pedantic-errors -Wall -Wextra -Wconversion -Wsign-conversion -Wshadow -Werror -Iquant/my_obr_v2/include -fsyntax-only quant/my_obr_v2/src/*.cpp
git -C quant diff --check
```

完整命令与结果在工作区根 `cyb_cleanup_validation.txt`、`cyb_cleanup_structure_validation.txt`。
以下保留各历史增量当时的行为记录，当前处理时机以文首修复说明和 `docs/replay.md` 为准。

## 上一增量：创业板新限价先完成自身撮合

用户确认：买单只解冻同向买单，解冻单不会改变当前买单自己的撮合结果；
解冻单的成交及 last price 同样归入当前买单 snapshot。卖单处理对称。
此前以“解冻单可能抢走新单的成交量”为由，让存在暂存单的整组都停止预测，
不符合这个业务前提；本次撤掉该限制，保留现有方法及文件结构。

- apply_limit_order 删除 pending_cyb_group 下全量入簿并返回的分支，
  合格新单继续用原 while 完成自身撮合，暂存价格范围判断保持原样。
- apply(Trade) 优先用新单原单序号和待确认量识别已经预测的 F，
  只累计真实成交并确认数量，不再扣盘口；全成时已删除的原单不会再次被解引用。
- 已预测 F 不进入 CYB 缓存，解冻单 F 沿用原回放；pending_cyb_group
  继续等待当前整组快照，使解冻成交的量额、笔数、last price 都归当前新单行。
- 撤单触发但 F 先到的 firstF 快照归属保持，普通 Order 解冻与 Cancel 解冻仍分别处理。

本次没有新增状态字段或业务方法，也没有增加输入格式检查。

独立验证：隔离的旧版源码在这 44 个场景的最终 CSV 均正确，但其中 34 个场景
未通过新单到达后立即撮合的检查，表现为预计成交量为零、对手未扣量、新单全量入簿。
调整后，44 个场景的即时及最终状态均符合预期：360 行、10800 个完整 CSV 字段
与独立黄金一致，22544 项预计量、position、原单余量、档位及快照断言通过。
另有 4 个独立 CLI 镜像场景，10 行、300 个字段通过手算比对。
覆盖跨档全成、部分成交、暂存单未解冻、解冻无成交、多单解冻，以及
“预测 F → 正常解冻 F → 撤单触发 F”的快照分组。严格 C++11、ASan/UBSan 通过，
原 27 个方法签名不变。详细命令与结果在工作区根 `cyb_limit_validation.txt`、
`cyb_limit_io_validation.txt` 和 `cyb_limit_structure_validation.txt`；临时验证产物不提交。

## 上一增量：创业板撤单触发成交的快照归属

按用户补充的输入特性：撤掉买一/卖一触发暂存单时，接收顺序是
`trade1 → trade2 → Cancel`。用户的 `234c0b` 已有 `replay_caused_by_cancel`
及跳过旧快照更新的分支。后续实现把 CYB F 无条件统计到上一行，并且统一生成
Cancel 元信息的行，丢失了这个特性。

本次在既有方法中增加状态及条件分支，保留全部 27 个业务方法名、签名和调用分工：

- CYB F 延迟到原回放循环中扣量、统计；其他 F 保持原统计时机。
- 每回放一笔前，基于已处理普通前缀后的最优档，判断后到 Cancel 是否会删掉
  该档，以及暂存单是否已经成交到更深的对手档；因此普通前缀仍属于上一行。
- 第一笔撤单触发 F 之前完成旧行，随后按原框架回放成交、执行撤单和激活余量。
- 这组只生成首笔 F 元信息的快照，包含本组所有 F 的统计和撤单后的五档；
  不再另外输出 Cancel 行。普通撤单、仅激活无 F、Order/EOF 收尾保持原逻辑。

修复前，30 个真实 CLI 场景中的 20 个特性场景复现旧行被污染及新行 CAA 错误，
10 个对照场景通过。复查另外补齐普通/市价前缀已激活其他暂存单的盘口归属，
新增买卖四个镜像场景也从失败变为通过。最终 34 个场景通过，272 行、8160 个数据字段
与独立黄金结果一致；逐事件及末态检查通过 18700 项 position、FIFO、档位汇总和索引断言。
覆盖买卖镜像、非零历史统计、多笔同价成交、普通成交前缀、连续两次触发、激活余量的
后续成交/撤单、前缀成交激活其他暂存单，以及普通 Order/Cancel 对照。
C++11 强告警与 ASan/UBSan 通过，27 个原方法签名及格式/diff 检查通过。
详细命令及修复前后结果见工作区根 `cyb_cancel_validation.txt`；临时验证工具不提交。

这次修复的是用户明确指出的快照归属错误；不据此断言已经定位用户实际 core 的唯一原因。
下文保留之前逐步定位 coredump 的记录，“不检查创业板”仅指对应历史增量。

## 上一增量的定位前提与调整

按用户最新要求，先假设：市价单的成交组结束时如果仍没有成交价，剩余数量之后只会撤销，
绝不会再成交。新市价单刚到达、正在等待本组首次 F 的正常流程不受这个前提影响。
同时沿用“F 的 CAA 严格晚于触发订单、没有相同 CAA”，本轮不检查创业板、不调整排序。

本次缩小到以下一步：

- 保留已独立复现并修复的空本方 U 单撤单问题，具体原因见下方第 1 项。
- 撤掉为旧未定价市价后续成交引入的集合、组标志、限价延迟和快照延迟。
- 删除旧未定价余量恢复到市价 F 缓存及在 execute_trade 中重新定价的分支。
- 无成交价余量仍保留 unpriced_quantity，后续部分/全部撤销正常扣量并清理索引。
  新限价单不会因这些只待撤订单而停止提前撮合或延迟输出。

目前仍未拿到用户实际 core 堆栈，不能把合成复现当成唯一实际根因。
下一步集中核对崩溃原单的状态及其首次被删除的事件，不扩展已被前提排除的行情路径。
本步定点验证：买卖各 10 个、共 20 个场景及 2200 项断言通过，覆盖当前市价、无价待撤、
有价余量、普通限价和空 U 的撤单状态，以及新限价的及时输出、无快照市价事件的行归属。
严格 C++11、强告警全部视为错误、ASan/UBSan 通过；生产 CLI 完整编译通过，原有 27 个
业务方法签名不变，格式/diff 检查通过。未检查创业板或改动排序。
准确命令与结果在工作区根 cancel_only_validation.txt、cancel_only_structure_validation.txt。

## 第二轮历史检查：非创业板路径

审查基准为 `bb37942940be07628fe6c7c84f5dfcf0e90571aa`。本轮不检查创业板业务，
不修改 `order_book_cyb.cpp`；仍保留原有业务方法名称、签名和文件分工。
以下修复前行号均对应 bb37942。第 1 项仍是有效业务缺陷；第 2 项随用户收窄前提被排除。

### 1. 已修复：空本方盘口的 U 单收到撤单后访问无效 position

**原因位置：** `order_book.cpp:163–170` 的 `apply_BBO_order`。
本方为空时，原代码直接删除到达顺序并返回，没有保留该订单的索引和待撤数量。
随后对应的撤单进入 `apply_cancel`，`:263` 的 `find` 返回 `end`，
继续读取不存在的 `OrderInfo`，最终在 `:279` 的 `position->remaining_quantity` 崩溃。
这里最先出错的是原单状态被过早丢弃，不能只在解引用处加空判断并跳过撤单。

最小序列：连续竞价，本方为空；新增 `U` 买单 #1、数量 100；收到撤 #1 的 100。
卖单方向完全对称。两侧均实际复现 UBSan 的空链表节点访问并异常退出。
这个例子不涉及创业板，也不需要打乱 Order/F 的事件组顺序。

本方无报价的 U 申报会自动撤销，依据为深交所规则第 3.3.6 条。
[深交所交易规则（2023 年修订）](https://docs.static.szse.cn/www/lawrules/rule/trade/W020230217564423808793.pdf)
已有主线 `obr` 的说明和验证也包含该业务。本例检查的是输入存在对应撤单时的状态处理，
不据此假设供应商会输出未通过前端校验的所有拒单。

**本次处理：** 在原 `apply_BBO_order` 中保留 `DROP_SIGNAL`、默认 position 和
`unpriced_quantity`，复用原 `apply_cancel` 的未入簿扣量分支，撤完再删除索引。
订单不加入任何价格档位；之后即使本方出现报价，也不会把这张待撤 U 单重新入簿。

### 2. 已按新前提排除：旧未定价市价单后来成交

先前构造的“旧市价单没有成交价，新限价到达后它再参与 F”场景，在旧实验模型下确实
能够复现提前误撮合、负余量和无效 position，但违反用户本轮采用的“之后只撤销”前提。
因此撤回将其作为当前输入故障候选的判断，不把它列为此次真实数据的缺陷。

321d8fc 曾为这个场景加入 unpriced_market_orders、pending_unpriced_group 及相关等待。
本次已移除这些状态和后续 F 恢复逻辑，保持普通限价提前撮合与及时快照。
原始实验过程仍保留在历史提交及 noncyb_market_audit.txt 中，仅作为旧模型的记录。

### 3. 已按用户保证排除：同 CAA 的复现不适用于本次输入

用户在本轮补充两项保证：订单产生的 Trade，其 CAA 严格晚于该订单；不会出现相同 CAA。
因此审查期间构造的“当前 F 与下一张委托同 CAA，委托优先导致错序”例子不适用于用户输入，
不再列为本次实际故障的候选原因。原始合成复现仍保留在工作区日志中，不能将它们解释成
用户数据违反了顺序约定。不同 CAA 的跨组交错也没有用户数据证据，本轮不据此归因。

排序保持原样；代码仍沿用既有事件组处理模型，未扩展多个交错组的处理。
第 1 项空本方 U 单撤单问题不依赖相同 CAA。第 2 项已经按最新前提排除，
不能将下面历史验证中的旧未定价后续成交场景当成当前有效输入。

### 历史验证记录（321d8fc）

原始失败及最小序列在工作区根 `noncyb_market_audit.txt`、`noncyb_io_audit.txt`；
IO 审查使用 `git show bb37942` 的隔离源码，避免把进行中的修复混入基线结果。
以下验证属于 321d8fc 及其当时的模型，本次收窄后的验证另见文首日志：

- 独立参考模型生成 20 个固定种子、每种 10000 组，共 20 万组普通限价、U、市价和撤单。
  逐组收尾验证 35297481 项断言，核对每张原单的价格/余量/position、索引、档位汇总、
  统计及五档；相同序列再仅靠自然 Order/Cancel 边界和 EOF 回放，2973880 项断言通过。
  两种执行合计 40 万组回放，不把它们称为 40 万组不同输入。
- 14 个新增双向状态场景分别运行状态核对和自然流式核对，共 28 次、2600 项断言通过。
  覆盖旧未定价单全成/部分、多价 F、普通 F 与市价 F 不同先后、多个旧未定价原单。
- 10 个集合/标志定点场景、106 项断言通过，检查空 U 排除、未定价集合增删、
  无 F 组分别在 Order/Cancel/EOF 释放，以及最后未定价余量移除后恢复及时输出。
- 16 组真实 CLI 的 38 行、1140 个数据字段和所有表头字段与独立手算预期一致。
  检查完整 30 列、各事件元信息、量额/最新价、EOF，以及空 U 与无关成交混合。
- 独立公开 apply 驱动另覆盖 16 个空 U、旧未定价与可见单竞争、下一 Order/Cancel/EOF
  收尾场景。全部 ASan/UBSan 通过。普通无未定价余量场景仍保留原来的及时输出行为。
- 所有编译使用严格 C++11、强告警及 `-Werror`；sanitizer 构建启用
  `-g -O0 -fsanitize=address,undefined -fno-omit-frame-pointer`。
  原有 27 个业务方法签名逐项比对、格式、diff 检查均通过。

实际命令（工作区根，临时验证工具交付前删除）：

```bash
python3 quant/obr/.noncyb_state_probe/run.py
python3 quant/obr/.noncyb_state_probe/run.py --stream
python3 quant/obr/.noncyb_state_probe/mixed.py
python3 quant/obr/.noncyb_io_probe/fix_run.py
clang++ -std=c++11 -pedantic-errors -Wall -Wextra -Wconversion -Wsign-conversion -Wshadow -Werror -Iquant/my_obr_v2/include -fsyntax-only quant/my_obr_v2/src/*.cpp
git -C quant diff --check
```

完整记录分别在 `noncyb_state_validation.txt`、`noncyb_state_stream_validation.txt`、
`noncyb_state_mixed_validation.txt`、`noncyb_io_fix_validation.txt` 及
`noncyb_structure_validation.txt`；严格晚于触发订单的 CAA 复现在
`noncyb_io_strict_after_audit.txt`。随机验证覆盖的是上述明确业务模型，不能证明所有
供应商时序都被支持；CAA 错序失败不计入修复后通过的场景。
所有临时驱动、输入及二进制仅用于本轮验证，不进入提交。

## 历史修复更新（bb37942）：保留当前方法结构

已在用户当前实现基础上修复下列问题。保留全部原有业务方法名、签名、文件分工、
market/CYB 缓存及 handle/replay 流程；execute_trade、get_snapshots 仅补全原来已有的声明。
没有引入 consume_order、add_resting_order 等新方法。仅显式禁止原本不安全的隐式复制，
不新增可调用业务方法。C++11、合法输入和中文注释要求继续适用。

| 原报告项 | 本次处理 |
| --- | --- |
| A1、A4：无效/悬空 position | apply_cancel 先分市价、未定价、暂存、可见状态；部分保留余量，全成/全撤同步清索引，只有可见原单才访问 position |
| A2：CYB 错容器删除 | 回放调用已有 execute_trade，再复用 apply_cancel 按原单 side 清理正确档位 |
| A3、B6：市价余量价格错误 | 回放只由真实 F 更新最后价格，余量通过已有入簿方法统一档位 key 与索引 price |
| A5：阶段未初始化 | 原构造函数显式初始化 trading_session |
| A6：特殊路由/空簿/复制风险 | 同 F 只入一份缓存，双方独立按实际状态扣量；CYB 不再无条件读取两边 begin；空 BBO 不虚构档位；禁用默认复制 |
| B1：没有 Ready | update_previous_snapshot 在所有等待状态结束后设 Ready；普通未成交单立即完成，普通 limit 的 F 确认齐后立即完成 |
| B2：竞价未扣盘 | F 累计本阶段独立价量，保留原 finish_call_auction/execute_auction_trade 结算，阶段切换和 EOF 均覆盖，统计不再重复 |
| B3：nts 双计 | record_trade 只在 apply 处理真实 F 时调用，推演和回放不再累计 |
| B4：EOF 遗留缓存 | 原 finish 回放市价、CYB 并结算竞价，随后完成旧快照 |
| B5：暂存余量/激活/旧快照 | 回放扣清暂存原单，按原到达 FIFO 恢复合格余量，在新事件前更新并完成旧快照 |
| B7：丢弃整段 F | 外层完成互斥路由，replay_CYB_trades 逐条执行，不再 return 后 clear 未处理的尾部 |
| B8：非 C++11 初始化 | 原位置改为 C++11 聚合初始化，严格 C++11 强告警检查通过 |

另补齐没有任何 F 的市价单分次撤销：未定价余量保存在原索引的 unpriced_quantity，
不会丢失或进入可见档位；后续收到真实 F 时复用原市价缓存，按该组最后一笔 F 定价。
新增等待字段只记录确认量、阶段量和当前组状态，未更换原有方法结构。

普通 limit 提前撮合与 CYB 回放不能竞争同一份对手量，因此有暂存参与的整组关闭提前撮合，
统一按真实 F 扣引用并在组末输出。仍沿用用户的 102%/98% 暂存口径、CAA 同值 Order 优先，
普通推演对应 F 必须在下一事件组之前完整到齐；不扩展现行交易所规则或跨组延迟 F 模型。

**最终验证：32 个核心/状态组合场景、2770 项断言通过；5 组完整 CLI 回放，
11 行输出的 330 个字段与独立预期一致。严格 C++11、全部告警视为错误和 ASan/UBSan
均通过。** 其中双暂存、市价对暂存的 3 项为内部状态组合夹具，不声称完整交易所行情。

头文件逐项比对确认原有 27 个业务方法的声明/签名均保持不变；未定价余量多次撤单、
后续多价 F 按最后价格入簿、其他事件快照保留，以及禁止复制/赋值均已验证。
格式与 diff 检查通过，临时 CSV、驱动和二进制不进入提交。

实际验证使用的命令（工作区根）：

```bash
python3 quant/obr/.v2_fix_validation/run.py
clang++ -std=c++11 -pedantic-errors -Wall -Wextra -Wconversion -Wsign-conversion -Wshadow -Werror -Iquant/my_obr_v2/include -fsyntax-only quant/my_obr_v2/src/*.cpp
/opt/homebrew/bin/clang-format --style=file:quant/obr/.clang-format --dry-run --Werror quant/my_obr_v2/include/order_book.hpp quant/my_obr_v2/src/*.cpp
git -C quant diff --check
```

临时验证脚本分别以 -g -O0 -fsanitize=address,undefined -fno-omit-frame-pointer
构建核心驱动和 CLI；追加组合/多价验证后，对原 26 场景和 5 组 CLI 再跑一次回归。
完整结果与准确命令在工作区根 my_obr_v2_fix_validation.txt，
方法签名/格式核对在 my_obr_v2_fix_structure_validation.txt。
下面保留原报告，行号固定于修复前的 cc09358，不能把历史崩溃结果理解为修复后的结果。

## 修复前审查记录

审查基准：`main` 的 `cc093587247641b15bec018fb00478bd3d912ff6`（提交说明 `tmp`）。
以下文件行号均对应这个提交。该次审查只写报告，没有改动生产源码；后续修复情况见上节。

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
