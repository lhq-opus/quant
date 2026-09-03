#include "obr/order_book.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace {

void require(bool condition, const std::string& message) {
  if (!condition) {
    std::cerr << "study check failed: " << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

void require_applied(const obr::ApplyResult& result, const std::string& operation) {
  if (!result.applied) {
    std::cerr << operation << " failed: " << result.message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

void print_levels(const char* name, const std::vector<obr::PriceLevel>& levels) {
  std::cout << name << '\n';
  for (std::vector<obr::PriceLevel>::const_iterator level = levels.begin(); level != levels.end();
       ++level) {
    std::cout << "  price=" << level->price.value
              << ", quantity=" << level->aggregate_quantity.value << '\n';
  }
}

} // namespace

int main() {
  obr::OrderBook book;

  const std::uint32_t trading_day = 20260903U;
  const std::uint32_t channel = 2010U;

  const obr::OrderId bid_order_1(trading_day, channel, 1U);
  const obr::OrderId bid_order_2(trading_day, channel, 2U);
  const obr::OrderId ask_order_1(trading_day, channel, 3U);

  // 这里直接使用 domain.hpp 中的真实事件结构，不再定义教学替身。
  const obr::AddOrderEvent add_bid_1 = {
      obr::EventId(trading_day, channel, 1U),
      bid_order_1,
      obr::Side::Buy,
      obr::OrderType::Limit,
      obr::Price(100000),
      obr::Quantity(100U),
  };
  const obr::AddOrderEvent add_bid_2 = {
      obr::EventId(trading_day, channel, 2U),
      bid_order_2,
      obr::Side::Buy,
      obr::OrderType::Limit,
      obr::Price(100000),
      obr::Quantity(50U),
  };
  const obr::AddOrderEvent add_ask_1 = {
      obr::EventId(trading_day, channel, 3U),
      ask_order_1,
      obr::Side::Sell,
      obr::OrderType::Limit,
      obr::Price(100100),
      obr::Quantity(80U),
  };

  require_applied(book.apply_add(add_bid_1), "add bid 1");
  require_applied(book.apply_add(add_bid_2), "add bid 2");
  require_applied(book.apply_add(add_ask_1), "add ask 1");

  // 两个同价买单在价位表中聚合成 150，但订单表仍分别保存 100 和 50。
  obr::Quantity bid_level_quantity(0U);
  require(book.get_level_quantity(obr::Side::Buy, obr::Price(100000), &bid_level_quantity),
          "aggregated bid level should exist");
  require(bid_level_quantity.value == 150U, "two bid orders should aggregate to 150");

  const obr::TradeEvent trade = {
      obr::EventId(trading_day, channel, 4U),
      bid_order_1,
      ask_order_1,
      obr::Price(100050),
      obr::Quantity(30U),
  };
  require_applied(book.apply_trade(trade), "trade");

  const obr::CancelOrderEvent cancel = {
      obr::EventId(trading_day, channel, 5U),
      bid_order_2,
      obr::Side::Buy,
      obr::Quantity(20U),
  };
  require_applied(book.apply_cancel(cancel), "cancel bid 2");

  // 相同事件再次到达会被 processed_events_ 拒绝，状态不会重复扣减。
  const obr::ApplyResult duplicate_cancel = book.apply_cancel(cancel);
  require(!duplicate_cancel.applied, "duplicate event must fail");
  require(duplicate_cancel.code == obr::ApplyErrorCode::DuplicateEvent,
          "duplicate event should have the expected error code");

  obr::Quantity bid_1_remaining(0U);
  obr::Quantity bid_2_remaining(0U);
  obr::Quantity ask_1_remaining(0U);
  require(book.get_remaining_quantity(bid_order_1, &bid_1_remaining), "bid 1 should remain live");
  require(book.get_remaining_quantity(bid_order_2, &bid_2_remaining), "bid 2 should remain live");
  require(book.get_remaining_quantity(ask_order_1, &ask_1_remaining), "ask 1 should remain live");

  std::cout << "bid order 1 remaining: " << bid_1_remaining.value << '\n';
  std::cout << "bid order 2 remaining: " << bid_2_remaining.value << '\n';
  std::cout << "ask order 1 remaining: " << ask_1_remaining.value << '\n';
  std::cout << "duplicate message: " << duplicate_cancel.message << '\n';
  print_levels("bid levels:", book.bid_levels());
  print_levels("ask levels:", book.ask_levels());

  const obr::ValidationResult validation = book.validate_invariants();
  require(validation.valid, validation.message);
  std::cout << "invariants valid: yes\n";

  // 小练习：把成交量从 30 改成 90。先判断哪条校验失败，以及三个订单是否会被修改。
  return EXIT_SUCCESS;
}
