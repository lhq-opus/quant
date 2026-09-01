# 第一版订单簿重建核心（C++11 基础语法）

## 范围

这一版只实现单标的、已标准化事件的核心状态机。它不读取 CSV，也不负责跨文件排序、
序列缺口、五档输出或累计成交统计。这样可以先独立证明最关键的状态转换，再让后续适配层
复用同一个核心。

按用户的学习目标，本版固定为 C++11，不使用 `std::variant`、`std::visit`、
`std::optional`、结构化绑定或三向比较。新增、撤单和成交是三个普通 `struct`，
分别传入 `apply_add`、`apply_cancel`和 `apply_trade`，便于直接跟踪逻辑。
活动订单和已处理事件分别使用 `std::map` 和 `std::set`；它们不是本项目的最终
性能选型，但第一版没有自定义哈希逻辑，更容易学习和检查。

当前核心只接受限价订单。深交所 `OrderType=1`（市价）和 `U`（本方最优）的行为会受
交易阶段和上游编码契约影响；在这些规则被确认和单独设计以前，核心返回
`UnsupportedOrderType`，不会猜测价格或静默入簿。

## 状态与事件

`OrderId` 由交易日、频道和原委托 `ApplSeqNum` 组成。`EventId` 使用相同三段作用域，
但表示当前事件自身的应用序号。这两个类型刻意分开，避免把成交/撤单事件序号误当作
被引用的原委托序号。

每个活动订单保存方向、类型、价格和剩余数量。买卖两侧分别维护全深度价格映射：
买价从高到低，卖价从低到高。每档数量必须等于该方向、该价格所有活动订单剩余量之和。

核心接收三种标准化事件：

- `AddOrderEvent`：增加一个唯一活动订单，并增加对应价格档；
- `CancelOrderEvent`：验证订单、方向和可撤数量后，减少一个订单；
- `TradeEvent`：先同时验证买卖两个引用和双方可成交数量，再同时减少两个订单。

剩余量或价位聚合变成零时立即删除。成功应用的 `EventId` 会被记录；重复事件返回
`DuplicateEvent`，不会二次改变状态。

## 原子性和错误

所有预期业务错误都在修改前完成校验。特别是成交事件只有在买卖双方同时有效时才开始
更新，因此未知订单、方向错误或任一方数量不足都不会留下“只扣了一边”的中间状态。
错误通过 `ApplyResult` 返回，不依赖异常表达正常数据质量问题。

本版没有实现恢复模式。零价格、零数量、重复订单、跨交易日/频道引用、未知订单、超量
成交或撤单、价位数量溢出等都会严格拒绝。`validate_invariants()` 会从活动订单重新计算
全量聚合，用于验证和诊断；它是 O(N) 审计，不应放进生产热路径的每个事件。

## 构建与验证

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
./build/obr_validate_reconstruction_core

cmake -S . -B build-sanitized -DCMAKE_BUILD_TYPE=Debug -DOBR_ENABLE_SANITIZERS=ON
cmake --build build-sanitized --parallel
./build-sanitized/obr_validate_reconstruction_core
```

验证程序使用运行时构造的事件，不依赖或提交 mock CSV。它覆盖同价聚合、七档深度、
部分/全部成交与撤单、深档晋升、重复事件、重复订单、未知引用、方向错误、跨作用域、
超量扣减、零值、不支持的订单类型和聚合溢出，并检查每个失败事件前后状态完全一致。
