#include <cstdint>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <utility>
#include <vector>

namespace {

struct OrderState {
  OrderState(std::int64_t order_price, std::uint64_t remaining)
      : price(order_price), remaining_quantity(remaining) {}

  std::int64_t price;
  std::uint64_t remaining_quantity;
};

struct PriceLevel {
  PriceLevel(std::int64_t level_price, std::uint64_t quantity)
      : price(level_price), aggregate_quantity(quantity) {}

  std::int64_t price;
  std::uint64_t aggregate_quantity;
};

// typedef 给较长的容器类型起一个业务名称；正式核心也采用这种 C++11 写法。
typedef std::map<std::uint64_t, OrderState> OrderRegistry;
typedef std::map<std::int64_t, std::uint64_t, std::greater<std::int64_t>> BidLevels;
typedef std::map<std::int64_t, std::uint64_t> AskLevels;
typedef std::set<std::uint64_t> ProcessedEvents;

void print_snapshot(const std::vector<PriceLevel>& levels) {
  // const_iterator 只允许读取，不能通过迭代器修改 vector 中的元素。
  for (std::vector<PriceLevel>::const_iterator level = levels.begin(); level != levels.end();
       ++level) {
    // `level->price` 等价于 `(*level).price`。
    std::cout << "price=" << level->price << ", quantity=" << level->aggregate_quantity << '\n';
  }
}

} // namespace

int main() {
  OrderRegistry orders;

  // insert 返回 pair<iterator, bool>；second 表示这次是否真的插入。
  const std::pair<OrderRegistry::iterator, bool> first_order =
      orders.insert(std::make_pair(1001U, OrderState(100250, 300U)));
  std::cout << "first order inserted: " << (first_order.second ? "yes" : "no") << '\n';

  const std::pair<OrderRegistry::iterator, bool> duplicate_order =
      orders.insert(std::make_pair(1001U, OrderState(100300, 999U)));
  std::cout << "duplicate inserted: " << (duplicate_order.second ? "yes" : "no") << '\n';

  // find 不会创建元素；找不到时返回 end() 这个“尾后”迭代器。
  OrderRegistry::iterator order = orders.find(1001U);
  if (order == orders.end()) {
    std::cerr << "expected order 1001 was not found\n";
    return 1;
  }
  order->second.remaining_quantity -= 50U;
  std::cout << "order 1001 remaining: " << order->second.remaining_quantity << '\n';

  // 买价使用 greater，所以 begin() 是最高价；卖价默认升序，所以 begin() 是最低价。
  BidLevels bid_levels;
  bid_levels.insert(std::make_pair(100100, 200U));
  bid_levels.insert(std::make_pair(100300, 100U));
  bid_levels.insert(std::make_pair(100200, 400U));

  AskLevels ask_levels;
  ask_levels.insert(std::make_pair(100500, 300U));
  ask_levels.insert(std::make_pair(100400, 250U));

  std::cout << "best bid: " << bid_levels.begin()->first << '\n';
  std::cout << "best ask: " << ask_levels.begin()->first << '\n';

  std::vector<PriceLevel> bid_snapshot;
  // reserve 只预留容量，不产生元素；随后 push_back 才真正追加元素。
  bid_snapshot.reserve(bid_levels.size());
  for (BidLevels::const_iterator level = bid_levels.begin(); level != bid_levels.end(); ++level) {
    bid_snapshot.push_back(PriceLevel(level->first, level->second));
  }

  std::cout << "bid snapshot (high to low):\n";
  print_snapshot(bid_snapshot);

  // set 只保存唯一键，适合记录已经处理过的事件 ID。
  ProcessedEvents processed_events;
  processed_events.insert(5001U);
  processed_events.insert(5001U);
  std::cout << "processed event count: " << processed_events.size() << '\n';

  bid_levels.erase(100200);
  std::cout << "bid level count after erase: " << bid_levels.size() << '\n';

  // 小练习：再插入一个 100300 的买单数量。思考 insert 为什么不会自动聚合旧价位。
  return 0;
}
