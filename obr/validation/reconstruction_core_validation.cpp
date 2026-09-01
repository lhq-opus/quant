#include "obr/order_book.hpp"

#include <cstdlib>
#include <iostream>
#include <limits>
#include <vector>

namespace {

const std::uint32_t kTradingDay = 20260901U;
const std::uint32_t kChannel = 1U;

void fail(const char* message) {
  std::cerr << "validation failed: " << message << '\n';
  std::exit(EXIT_FAILURE);
}

void expect(bool condition, const char* message) {
  if (!condition) {
    fail(message);
  }
}

obr::OrderId make_order_id(std::uint64_t sequence) {
  return obr::OrderId(kTradingDay, kChannel, sequence);
}

obr::EventId make_event_id(std::uint64_t sequence) {
  return obr::EventId(kTradingDay, kChannel, sequence);
}

obr::AddOrderEvent make_add(std::uint64_t sequence, obr::Side side, std::int64_t price,
                            std::uint64_t quantity, obr::OrderType order_type) {
  obr::AddOrderEvent event = {make_event_id(sequence), make_order_id(sequence), side, order_type,
                              obr::Price(price),       obr::Quantity(quantity)};
  return event;
}

obr::AddOrderEvent make_limit_add(std::uint64_t sequence, obr::Side side, std::int64_t price,
                                  std::uint64_t quantity) {
  return make_add(sequence, side, price, quantity, obr::OrderType::Limit);
}

obr::CancelOrderEvent make_cancel(std::uint64_t event_sequence, std::uint64_t order_sequence,
                                  obr::Side side, std::uint64_t quantity) {
  obr::CancelOrderEvent event = {make_event_id(event_sequence), make_order_id(order_sequence), side,
                                 obr::Quantity(quantity)};
  return event;
}

obr::TradeEvent make_trade(std::uint64_t event_sequence, std::uint64_t bid_sequence,
                           std::uint64_t ask_sequence, std::int64_t price, std::uint64_t quantity) {
  obr::TradeEvent event = {make_event_id(event_sequence), make_order_id(bid_sequence),
                           make_order_id(ask_sequence), obr::Price(price), obr::Quantity(quantity)};
  return event;
}

struct ObservableState {
  std::size_t order_count;
  std::size_t event_count;
  std::vector<obr::PriceLevel> bids;
  std::vector<obr::PriceLevel> asks;
};

ObservableState observe(const obr::OrderBook& book) {
  ObservableState state = {book.order_count(), book.processed_event_count(), book.bid_levels(),
                           book.ask_levels()};
  return state;
}

bool same_state(const ObservableState& left, const ObservableState& right) {
  return left.order_count == right.order_count && left.event_count == right.event_count &&
         left.bids == right.bids && left.asks == right.asks;
}

void expect_invariants(const obr::OrderBook& book) {
  obr::ValidationResult result = book.validate_invariants();
  if (!result.valid) {
    std::cerr << "invariant audit failed: " << result.message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

void expect_success(obr::OrderBook& book, const obr::ApplyResult& result) {
  if (!result.applied) {
    std::cerr << "expected success, got: " << result.message << '\n';
    std::exit(EXIT_FAILURE);
  }
  expect_invariants(book);
}

void expect_failure_unchanged(obr::OrderBook& book, const ObservableState& before,
                              const obr::ApplyResult& result, obr::ApplyErrorCode expected_code) {
  expect(!result.applied, "expected event rejection");
  if (result.code != expected_code) {
    std::cerr << "unexpected rejection code: " << result.message << '\n';
    std::exit(EXIT_FAILURE);
  }
  expect(same_state(observe(book), before), "rejected event changed the book");
  expect_invariants(book);
}

void check_remaining(const obr::OrderBook& book, std::uint64_t order_sequence,
                     std::uint64_t expected_quantity) {
  obr::Quantity actual(0U);
  expect(book.get_remaining_quantity(make_order_id(order_sequence), &actual),
         "expected live order was not found");
  expect(actual.value == expected_quantity, "unexpected remaining order quantity");
}

void check_level(const obr::OrderBook& book, obr::Side side, std::int64_t price,
                 std::uint64_t expected_quantity) {
  obr::Quantity actual(0U);
  expect(book.get_level_quantity(side, obr::Price(price), &actual),
         "expected price level was not found");
  expect(actual.value == expected_quantity, "unexpected aggregate level quantity");
}

void validate_normal_flow() {
  obr::OrderBook book;

  expect_success(book, book.apply_add(make_limit_add(1U, obr::Side::Buy, 10000, 1000U)));
  expect_success(book, book.apply_add(make_limit_add(2U, obr::Side::Buy, 10000, 500U)));
  expect_success(book, book.apply_add(make_limit_add(3U, obr::Side::Buy, 9900, 700U)));
  expect_success(book, book.apply_add(make_limit_add(4U, obr::Side::Buy, 9800, 600U)));
  expect_success(book, book.apply_add(make_limit_add(5U, obr::Side::Buy, 9700, 500U)));
  expect_success(book, book.apply_add(make_limit_add(6U, obr::Side::Buy, 9600, 400U)));
  expect_success(book, book.apply_add(make_limit_add(7U, obr::Side::Buy, 9500, 300U)));
  expect_success(book, book.apply_add(make_limit_add(8U, obr::Side::Buy, 9400, 200U)));
  expect_success(book, book.apply_add(make_limit_add(9U, obr::Side::Sell, 10100, 800U)));
  expect_success(book, book.apply_add(make_limit_add(10U, obr::Side::Sell, 10200, 900U)));

  expect(book.bid_levels().size() == 7U, "book did not retain levels beyond top five");
  check_level(book, obr::Side::Buy, 10000, 1500U);

  expect_success(book, book.apply_trade(make_trade(11U, 1U, 9U, 10100, 300U)));
  check_remaining(book, 1U, 700U);
  check_remaining(book, 9U, 500U);

  expect_success(book, book.apply_cancel(make_cancel(12U, 2U, obr::Side::Buy, 500U)));
  expect(!book.get_remaining_quantity(make_order_id(2U), NULL),
         "full cancel did not remove the order");
  check_level(book, obr::Side::Buy, 10000, 700U);

  expect_success(book, book.apply_trade(make_trade(13U, 1U, 9U, 10100, 500U)));
  expect(!book.get_remaining_quantity(make_order_id(9U), NULL),
         "full fill did not remove the sell order");
  check_remaining(book, 1U, 200U);

  expect_success(book, book.apply_cancel(make_cancel(14U, 1U, obr::Side::Buy, 200U)));
  expect(book.bid_levels()[0].price == obr::Price(9900),
         "removing best bid did not promote the next full-depth level");

  ObservableState before = observe(book);
  expect_failure_unchanged(book, before,
                           book.apply_cancel(make_cancel(14U, 1U, obr::Side::Buy, 200U)),
                           obr::ApplyErrorCode::DuplicateEvent);

  before = observe(book);
  obr::AddOrderEvent duplicate_order = {make_event_id(15U), make_order_id(3U),
                                        obr::Side::Buy,     obr::OrderType::Limit,
                                        obr::Price(9900),   obr::Quantity(1U)};
  expect_failure_unchanged(book, before, book.apply_add(duplicate_order),
                           obr::ApplyErrorCode::DuplicateOrder);

  before = observe(book);
  expect_failure_unchanged(book, before,
                           book.apply_cancel(make_cancel(16U, 999U, obr::Side::Buy, 1U)),
                           obr::ApplyErrorCode::UnknownOrder);

  before = observe(book);
  expect_failure_unchanged(book, before,
                           book.apply_cancel(make_cancel(17U, 3U, obr::Side::Sell, 1U)),
                           obr::ApplyErrorCode::SideMismatch);

  before = observe(book);
  expect_failure_unchanged(book, before,
                           book.apply_cancel(make_cancel(18U, 3U, obr::Side::Buy, 701U)),
                           obr::ApplyErrorCode::OverReduce);

  before = observe(book);
  expect_failure_unchanged(book, before, book.apply_trade(make_trade(19U, 3U, 10U, 10000, 701U)),
                           obr::ApplyErrorCode::OverReduce);
  check_remaining(book, 10U, 900U);

  before = observe(book);
  expect_failure_unchanged(book, before, book.apply_trade(make_trade(20U, 3U, 999U, 10000, 1U)),
                           obr::ApplyErrorCode::UnknownOrder);

  before = observe(book);
  expect_failure_unchanged(book, before,
                           book.apply_cancel(make_cancel(21U, 3U, obr::Side::Buy, 0U)),
                           obr::ApplyErrorCode::InvalidQuantity);

  before = observe(book);
  expect_failure_unchanged(book, before, book.apply_add(make_limit_add(22U, obr::Side::Buy, 0, 1U)),
                           obr::ApplyErrorCode::InvalidPrice);

  before = observe(book);
  expect_failure_unchanged(
      book, before, book.apply_add(make_add(23U, obr::Side::Buy, 9000, 1U, obr::OrderType::Market)),
      obr::ApplyErrorCode::UnsupportedOrderType);

  before = observe(book);
  obr::CancelOrderEvent wrong_scope = {make_event_id(24U), obr::OrderId(kTradingDay, 2U, 3U),
                                       obr::Side::Buy, obr::Quantity(1U)};
  expect_failure_unchanged(book, before, book.apply_cancel(wrong_scope),
                           obr::ApplyErrorCode::ScopeMismatch);

  before = observe(book);
  obr::CancelOrderEvent invalid_event = {obr::EventId(0U, kChannel, 25U), make_order_id(3U),
                                         obr::Side::Buy, obr::Quantity(1U)};
  expect_failure_unchanged(book, before, book.apply_cancel(invalid_event),
                           obr::ApplyErrorCode::InvalidEventId);
}

void validate_aggregate_overflow() {
  obr::OrderBook book;
  expect_success(book, book.apply_add(make_limit_add(1U, obr::Side::Buy, 10000,
                                                     std::numeric_limits<std::uint64_t>::max())));

  ObservableState before = observe(book);
  expect_failure_unchanged(book, before,
                           book.apply_add(make_limit_add(2U, obr::Side::Buy, 10000, 1U)),
                           obr::ApplyErrorCode::LevelQuantityOverflow);
}

} // namespace

int main() {
  validate_normal_flow();
  validate_aggregate_overflow();
  std::cout << "reconstruction core validation passed\n";
  return EXIT_SUCCESS;
}
