# asks / bids 的读写封装

`OrderBook` 负责按order/F/4更新指定订单；`PriceLevels` 只负责保存和读写某一侧价格档。
它不读取CSV、不推断市价单类型、不模拟撮合，也不更新成交统计。

实现分为 [price_levels.hpp](../include/price_levels.hpp) 和
[price_levels.cpp](../src/price_levels.cpp)，使用 C++11，没有自定义模板或虚函数。
`OrderBook` 构造时用 `bids('1')`、`asks('2')` 指定方向。

## 接口

- `empty()`：该侧是否没有档位。
- `best()`：返回最优档的价格和数量；调用前先确认非空。
- `quantity_at(price)`：查询某个价位的数量，不存在返回0，不创建档位。
- `add(price, quantity)`：同价累加，新价建档，沿用原有加法溢出检查。
- `reduce(price, quantity)`：扣减该档数量，减到0就删档。
- `read_top(count)`：读取前count档，买盘降序、卖盘升序，不足时只返回已有档。
- `read_all()`：按同样顺序读取全部档位。
- `swap(other)`：交换价格档和方向，与默认值拷贝配合可保存或恢复一份盘口。

内部 `map` 是私有成员，调用处拿不到它的可写引用或迭代器。
`best`、`read_top`、`read_all` 都返回值副本；修改这些副本不会改变真实盘口。

`add` 的调用前提是正价格、正数量；`reduce` 的调用前提是价位存在且扣量不超过该档。
原有业务函数仍负责其既有校验，没有在这里添加另一套重复检查或错误恢复框架。

## 真实F的卖方档位扣量怎样写

```cpp
// ask是通过OfferApplSeqNum找到的原卖单；此前已检查双方余量和统计运算。
if (ask.price != 0) {
  asks.reduce(ask.price, event.quantity);
}
```

业务函数不用再修改 `second`、判断零量、`erase()`，也不会持有删档后失效的迭代器。
买方同理，从买单自己的挂价扣量，而不是强制扣最优档或TradePrice价档。

快照用 `read_top(5)` 读取五档，再由快照层补零，不复制全部深度。
当前成交驱动核心不再使用全量竞价筛选或新单全盘备份；`read_all/swap` 保留为价格档
类已有接口。按价格扣量需要一次 `map::find`，这里优先保持接口简单。

## 与成交驱动版本的关系

最初封装提交3da2f8b没有改变撮合规则；后续按用户要求改为[真实成交驱动](trade_driven.md)。
本类的读写接口仍不变，业务变化发生在OrderBook和主重放循环。
`Snapshot::bids/asks` 仍是独立的五档结果，不是可修改真实盘口的入口。

当前仍是用户的市价推断实验版本；封装和回归验证不表示这些市场规则已经得到确认。

## 历史验证：价格档封装提交3da2f8b

使用临时合成数据，以封装前的 `97c2fb4` 为基线：42 组合法场景的 30 列盘口和
12 列 events 导出逐字节一致，14 组既有失败场景的退出状态和诊断也保持一致。
其中 20 组随机事件流共 2000 行快照，还通过了独立计算的逐字段核对。

档位顺序、同价加量、减空删除、副本隔离、复制交换及失败回滚的 68 项断言通过。
以上检查覆盖 Debug、Release 和 ASan/UBSan 构建，严格使用 C++11，零编译告警；
未使用真实行情，临时验证程序与 CSV 不进入提交。

## 编译与执行

在工作区根目录执行，需要编译三个 `.cpp`：

```bash
clang++ -std=c++11 -pedantic-errors -Wall -Wextra -Wconversion \
  -Wsign-conversion -Wshadow -Werror -O2 \
  -I quant/my_obr/include \
  quant/my_obr/src/main.cpp quant/my_obr/src/order_book.cpp \
  quant/my_obr/src/price_levels.cpp \
  -o /tmp/my_obr

/tmp/my_obr --order /path/to/order.csv --trade /path/to/trade.csv \
  --output /path/to/book.csv --events-output /path/to/events.csv
```
