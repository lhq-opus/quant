#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <limits>
#include <map>

namespace {

struct QueuedOrder {
  QueuedOrder(std::uint64_t identifier, std::uint64_t quantity)
      : order_id(identifier), remaining_quantity(quantity) {}

  std::uint64_t order_id;
  std::uint64_t remaining_quantity;
};

typedef std::deque<QueuedOrder> OrderQueue;
typedef std::map<std::int64_t, OrderQueue, std::greater<std::int64_t>> BidBook;
typedef std::map<std::int64_t, OrderQueue> AskBook;

void add_bid(BidBook& bids, std::uint64_t order_id, std::int64_t price, std::uint64_t quantity) {
  // map 的 []：价位不存在时先创建一个空 deque；存在时直接取得原队列。
  // push_back 把新订单放在同价队尾，所以更早到达的订单仍在前面。
  bids[price].push_back(QueuedOrder(order_id, quantity));
}

void add_ask(AskBook& asks, std::uint64_t order_id, std::int64_t price, std::uint64_t quantity) {
  asks[price].push_back(QueuedOrder(order_id, quantity));
}

bool calculate_total_bid_quantity(const BidBook& bids, std::uint64_t* output) {
  if (output == nullptr) {
    return false;
  }

  std::uint64_t total = 0U;
  for (BidBook::const_iterator level = bids.begin(); level != bids.end(); ++level) {
    for (OrderQueue::const_iterator order = level->second.begin(); order != level->second.end();
         ++order) {
      if (order->remaining_quantity > std::numeric_limits<std::uint64_t>::max() - total) {
        return false;
      }
      total += order->remaining_quantity;
    }
  }
  *output = total;
  return true;
}

bool has_at_least(const BidBook& bids, std::uint64_t requested_quantity) {
  // 不先求一个可能溢出的总和，而是从“还需要多少”中逐笔安全地减。
  std::uint64_t quantity_needed = requested_quantity;
  for (BidBook::const_iterator level = bids.begin(); level != bids.end(); ++level) {
    for (OrderQueue::const_iterator order = level->second.begin(); order != level->second.end();
         ++order) {
      if (order->remaining_quantity >= quantity_needed) {
        return true;
      }
      quantity_needed -= order->remaining_quantity;
    }
  }
  return false;
}

bool consume_best_bids(BidBook& bids, std::uint64_t requested_quantity) {
  // 为了演示“失败不改状态”，先验证总量，再进入真正修改阶段。
  if (requested_quantity == 0U || !has_at_least(bids, requested_quantity)) {
    return false;
  }

  std::uint64_t quantity_left = requested_quantity;
  while (quantity_left > 0U) {
    // 买价 map 降序排列，因此 begin() 永远是当前最高价格：价格优先。
    BidBook::iterator best_level = bids.begin();
    OrderQueue& queue = best_level->second;

    // front() 是同价最早进入队列的订单：时间优先。
    QueuedOrder& oldest_order = queue.front();
    if (quantity_left < oldest_order.remaining_quantity) {
      oldest_order.remaining_quantity -= quantity_left;
      quantity_left = 0U;
    } else {
      quantity_left -= oldest_order.remaining_quantity;
      queue.pop_front();
      if (queue.empty()) {
        bids.erase(best_level);
      }
    }
  }
  return true;
}

void print_best_bid_queue(const BidBook& bids) {
  if (bids.empty()) {
    std::cout << "bid book is empty\n";
    return;
  }

  const BidBook::const_iterator best_level = bids.begin();
  std::cout << "best bid price: " << best_level->first << '\n';
  for (OrderQueue::const_iterator order = best_level->second.begin();
       order != best_level->second.end(); ++order) {
    std::cout << "  order " << order->order_id << " remaining " << order->remaining_quantity
              << '\n';
  }
}

} // namespace

int main() {
  BidBook bids;
  AskBook asks;

  add_bid(bids, 1U, 100100, 50U);
  add_bid(bids, 2U, 100200, 40U);
  add_bid(bids, 3U, 100200, 30U);
  add_ask(asks, 4U, 100400, 60U);
  add_ask(asks, 5U, 100300, 20U);

  std::cout << "initial queue:\n";
  print_best_bid_queue(bids);
  std::cout << "best ask price: " << asks.begin()->first << '\n';

  // 先消耗 40：订单 2 全部离队；再消耗 10：订单 3 还剩 20。
  const bool consumed = consume_best_bids(bids, 50U);
  std::cout << "consume 50 succeeded: " << (consumed ? "yes" : "no") << '\n';
  print_best_bid_queue(bids);

  std::uint64_t before_failed_consume = 0U;
  if (!calculate_total_bid_quantity(bids, &before_failed_consume)) {
    std::cerr << "could not calculate bid quantity\n";
    return 1;
  }
  const bool oversized = consume_best_bids(bids, 1000U);
  std::uint64_t after_failed_consume = 0U;
  if (!calculate_total_bid_quantity(bids, &after_failed_consume)) {
    std::cerr << "could not calculate bid quantity\n";
    return 1;
  }
  std::cout << "consume 1000 succeeded: " << (oversized ? "yes" : "no") << '\n';
  std::cout << "failed consume changed state: "
            << (before_failed_consume == after_failed_consume ? "no" : "yes") << '\n';

  // 小练习：再消耗 20，观察最高买价如何从 100200 下降到 100100。
  // 注意：本文件用于理解队列，不代表重建器应该自行撮合订单。
  return 0;
}
