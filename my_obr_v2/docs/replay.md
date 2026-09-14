# my_obr_v2 回放说明

本轮以用户提交 `234c0b8` 的 v2 为基础，补齐流式输入输出、快照确认与尚未接通的
订单处理。使用 C++11，假定输入合法、引用成立、数值运算可表示，不做格式猜测或非法字段回退。

## 构建与运行

从 quant 仓库根目录执行：

```bash
clang++ -std=c++11 -pedantic-errors -Wall -Wextra -Wconversion -Wsign-conversion -Wshadow -Werror \
  -Imy_obr_v2/include my_obr_v2/src/*.cpp -o /tmp/my_obr_v2
/tmp/my_obr_v2 --order /path/order.csv --trade /path/trade.csv --output /path/book.csv
```

省略 `--output` 时写当前目录的 `book.csv`。每个实例处理一个证券、一个交易日、一个通道。

## v2 格式与顺序

按用户 v2 的固定位置读取无引号转义 CSV，跳过一次表头。

委托 20 列：

```text
clockAtArrival,sequenceNo,exchId,securityType,__isRepeated,TransactTime,ChannelNo,ApplSeqNum,SecurityID,secid,mdSource,Side,OrderType,__origTickSeq,Price,OrderQty,OrderIndex,BizIndex,PacketID,IsLastMsg
```

成交 22 列：

```text
clockAtArrival,sequenceNo,exchId,securityType,__isRepeated,TransactTime,ChannelNo,ApplSeqNum,SecurityID,secid,mdSource,ExecType,TradeBSFlag,__origTickSeq,TradePrice,TradeQty,TradeMoney,BidApplSeqNum,OfferApplSeqNum,BizIndex,PacketID,IsLastMsg
```

- `Price/TradePrice` 已为 1/10000 元整数，数量为整数；累计金额按价格乘数量计算。
- `SecurityID` 位于下标 8，沿用用户代码中数值大于等于 300000 的创业板判断；
  输出证券标识取下标 9 的 `secid`。
- `TransactTime` 为 HHMMSSmmm 数字文本，保留原文输出。阶段判断沿用 v2：
  09:15:00—09:25:00 为开盘竞价，09:30:00—11:30:00、13:00:00—14:57:00 前为连续竞价，
  其他记录归到收盘竞价。
- 两个文件分别按数值 CAA 非降序，流式归并时同 CAA 委托优先，各文件保持物理行序。
  此规则来自既有约定，本轮不改用 `sequenceNo` 调度。

事件组沿用 v2 的处理模型：一张委托及其相关 F，或一条撤单及其触发的后续 F，
在下一张委托/撤单前处理完。**CAA 归并也必须保留该组顺序**。例如同 CAA 下，
后来的委托被“委托优先”移到前一委托的 F 之前，就不符合当前模型；该排序问题
此前已被用户排除在本轮范围外。当前实现不支持这种跨组延迟 F，也没有新增输入检查。
这里明确的是算法前提，不把到达时间当成交易所业务序号。

输出固定 30 列，保持 v2 的 `bp4`：

```text
caa,secid,sno,asn,tst,nts,cvl,cto,lpr,opx,bp5,bp4,bp3,bp2,bp1,ap1,ap2,ap3,ap4,ap5,bs5,bs4,bs3,bs2,bs1,as1,as2,as3,as4,as5
```

价格与金额保留两位小数，使用整数四舍五入，避免大额转 double 丢失低位；
恰好半分时向远离零方向舍入。这一点将原浮点格式化的半分结果明确为确定规则。
空档价格为 `0.00`，数量为 `0`；买档从第五档输出到第一档，卖档从第一档到第五档。
只输出连续竞价委托/撤单的确定快照，普通 F 不单独生成一行。

## 核心职责

- `add_resting_order`：建立可见订单、档位总量和 `OrderInfo::position`；
  暂存单激活时按原始到达次序恢复同价队列。
- `consume_order`：按原单扣量。可见订单直接使用 position；
  市价等待余量、创业板暂存余量分别扣自己的状态。全部耗尽时删订单，
  可见档位没有订单时删档，同时清理活动索引。
- `execute_trade`：对一条真实 F 的买卖原单各扣一次。
  某侧没有展示在盘口时，扣的是其独立余量，因此不一定同时改变 asks 和 bids。
- `execute_order_at_price`：限价推演在一个档位扣确定的 quantity，循环用于跨越同价
  FIFO 订单。调用方直接从来单余量减去 quantity，不存在要返回的未成交量。
- `record_trade`：仅对真实 F 调用一次，更新笔数、累计量额、最新价；
  开盘竞价 F 同时确定开盘价。撤单和限价推演不累计成交统计。
- `fill_snapshot_levels`：基于完整 asks/bids 重建双侧五档，缺档补零，可反复覆盖同一快照。
- `get_market_trade_sides`：根据成交的双方原单引用和通道，独立返回 is_bid/is_ask；
  查询的是原始市价身份，全成、撤单或余量入簿后仍可查询。

### 限价及本方最优

普通限价先按对手价优、同价 FIFO 推演扣盘，将未成交部分入簿，并保存预计成交量。
真实 F 到来时仅确认已推演的量并累计真实统计，不重复扣盘。预计量全部确认后，
立刻将原委托快照设为 Ready；未成交限价可在来单时直接 Ready。
本方最优以现有本方最优价转为限价处理。

例如卖一 10 元共 30 股、卖二 10.01 元共 40 股，限价买入 10.01 元 50 股：
来单后卖一删除、卖二剩 20 股；随后真实 F 的 30 股和 20 股只更新统计。
第二条 F 后即可输出该买单快照，累计成交 50 股、2 笔，不等待下一张委托。

### 市价

市价来单暂不展示在盘口。相关 F 立即按双方原单引用扣量，并记录这张市价单自己的
最后真实成交价。市价段结束时，有成交价的未成交余量按该价入簿；
没有发生 F 时不从其他订单的历史成交价猜一个价格。

沿用 v2 的行保留策略：全部由成交消耗的市价单保留其原快照；
有余量或发生撤单的原市价快照删除，后续委托/撤单行反映最终盘口。
撤单先扣撤销量，再处理剩余量；撤单价格不覆盖最后成交价。
下一张委托、撤单、阶段切换及 EOF 均能完成收尾。

### 竞价

开盘和收盘都直接使用本阶段真实 F 的价格、数量及双方订单引用。
每条 F 各扣两侧一次、累计一次；不再在阶段结束时用全日累计量二次扣盘，
也不额外推算一个集合竞价价格。收盘竞价解除连续竞价的暂存限制。
本轮保留 v2 的开盘价来源：没有开盘竞价 F 时，opx 保持 0。

### 创业板

沿用用户 v2 的范围判断：买价超过卖一 102%、卖价低于买一 98% 时暂存；
对手侧为空时沿用原代码的不暂存处理。部分撤单、部分成交保留暂存余量。
盘口变化后重新检查范围，符合条件的暂存单恢复入簿；激活不虚构成交。

有暂存单参与的事件组不使用限价提前扣盘，改为登记来单、按真实 F 精确扣双方引用，
并等事件组末输出快照。这避免了暂存单激活与限价推演竞争同一份对手盘数量。
同一 F 即使两侧都为暂存单，或一侧暂存、一侧市价，也只执行和统计一次。

这个范围判断是用户 v2 的简化口径，不是完整的现行创业板规则。
[2020 年创业板特别规定](https://docs.static.szse.cn/www/disclosure/notice/general/W020200612831351578076.pdf)
包含暂存、恢复参与及基准价回退等规定；
[2023 年交易规则](https://docs.static.szse.cn/www/lawrules/rule/stock/trade/W020230217564424593579.pdf)
的价格范围和超范围处理已有变化。本轮不静默引入新的规则版本、昨收价输入、
最小报价单位舍入或基准价回退；后续适配需先确定数据对应的交易日及规则版本。

## 流式边界与验证

两路各缓存一行；每次 apply 后持续 pop_snapshot 并写出 Ready 行。
Deleted 行跳过，Pending 行等待；已输出快照随即从队列删除。
活动订单和全深度档位按业务状态保留，市价原始身份集合保留到实例结束，
因此整体内存仍随活动订单与当日市价订单数增长。

本轮使用未提交的合法场景驱动和临时 CSV，验证限价买卖、部分/全部成交与撤单、
竞价原单引用、市价余量与 EOF、创业板暂存及激活、position 与档位汇总、
五档补位、流归并及完整 30 列结果。构建采用 C++11 强告警，并运行 ASan/UBSan。
执行记录保存在工作区根的 learning_plan.md 及 my_obr_v2_*_validation.txt，
临时输入、驱动和二进制不进入提交。
