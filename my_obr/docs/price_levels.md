# asks / bids 的读写封装

`OrderBook` 继续决定订单怎样撮合、该扣多少数量；新增的 `PriceLevels` 只负责保存和
读写某一侧的价格档。它不读取 CSV，不分析市价单类型，也不更新成交统计。

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
- `read_all()`：按同样顺序读取全部档位，供集合竞价筛选使用。
- `swap(other)`：交换价格档和方向，与值拷贝配合保留原来的失败回滚。

内部 `map` 是私有成员，调用处拿不到它的可写引用或迭代器。
`best`、`read_top`、`read_all` 都返回值副本；修改这些副本不会改变真实盘口。

`add` 的调用前提是正价格、正数量；`reduce` 的调用前提是价位存在且扣量不超过该档。
原有业务函数仍负责其既有校验，没有在这里添加另一套重复检查或错误恢复框架。

## 原来的扣量代码怎样写

```cpp
if (!asks.empty()) {
  const PriceLevel best_ask = asks.best();
  const int64_t quantity = std::min(remaining_quantity, best_ask.quantity);

  record_trade(best_ask.price, quantity);
  asks.reduce(best_ask.price, quantity);
  remaining_quantity -= quantity;
}
```

该段在有正剩余量的撮合循环内使用。业务函数不用再写 `begin()`、修改 `second`、
判断零量、`erase()` 这一组操作，也不会保留一个删档后失效的迭代器。
循环下一次重新调用 `best()`，自然得到更新后的最优档。

快照用 `read_top(5)` 读取五档，再由快照层按原约定补零；此操作不复制全部深度。
竞价筛选只在开始时各读一份全量副本，候选筛选期间反复遍历它们。全量副本有额外
内存开销；按价格扣量需要一次 `map::find`，这里优先保持接口简单，没有优化这部分。

## 本轮没有改变的内容

市价历史推断、各撮合函数的职责、待撤余额、原有校验与失败回滚、开收盘竞价、源F
统计、快照时点、30列表头及12列events旁路都保持原有规则。
`Snapshot::bids/asks` 仍是独立的五档结果，不是可修改真实盘口的入口。

当前仍是用户的市价推断实验版本；封装和回归验证不表示这些市场规则已经得到确认。

## 本轮验证

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
