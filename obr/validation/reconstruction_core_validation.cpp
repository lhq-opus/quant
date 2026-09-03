#include "obr/order_book.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

namespace {

void expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << "validation failed: " << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

obr::Event make_order(const char* caa, const char* transaction_time, char side, obr::Price price,
                      obr::Quantity quantity) {
  const obr::Event event = {caa,   transaction_time, obr::EventType::Order, side, '2',
                            price, quantity};
  return event;
}

obr::Event make_cancel(const char* caa, const char* transaction_time, obr::Price price,
                       obr::Quantity quantity) {
  const obr::Event event = {caa,   transaction_time, obr::EventType::Cancel, '\0', '\0',
                            price, quantity};
  return event;
}

void validate_full_day() {
  obr::OrderBook book;

  // 开盘集合竞价：最大成交量 250，统一成交价 10.0000。
  const obr::Event opening_bid_1 = make_order("09:15", "91500790", '1', 101000, 100);
  const obr::Event opening_bid_2 = make_order("09:16", "91600000", '1', 100000, 200);
  const obr::Event opening_ask_1 = make_order("09:17", "91700000", '2', 99000, 150);
  const obr::Event opening_ask_2 = make_order("09:18", "91800000", '2', 100000, 100);

  book.apply(opening_bid_1, obr::TradingSession::OpeningAuction);
  book.apply(opening_bid_2, obr::TradingSession::OpeningAuction);
  book.apply(opening_ask_1, obr::TradingSession::OpeningAuction);
  book.apply(opening_ask_2, obr::TradingSession::OpeningAuction);
  book.finish_call_auction();

  obr::Snapshot snapshot = book.make_snapshot(opening_ask_2);
  expect(snapshot.bids.size() == 1U, "opening should leave one bid level");
  expect(snapshot.bids[0].price == 100000, "opening remaining bid price should be 10.0000");
  expect(snapshot.bids[0].quantity == 50, "opening remaining bid quantity should be 50");
  expect(snapshot.asks.empty(), "opening should consume all eligible asks");

  // 连续竞价：卖单先消耗 10.0000 买盘，随后另一个卖单消耗 10.2000 买盘。
  const obr::Event continuous_ask = make_order("09:30", "93000000", '2', 99500, 20);
  const obr::Event continuous_bid = make_order("10:04", "100407190", '1', 102000, 70);
  const obr::Event continuous_ask_2 = make_order("10:05", "100500000", '2', 101000, 30);
  book.apply(continuous_ask, obr::TradingSession::ContinuousAuction);
  book.apply(continuous_bid, obr::TradingSession::ContinuousAuction);
  book.apply(continuous_ask_2, obr::TradingSession::ContinuousAuction);

  // 收盘集合竞价：新增买卖盘统一在 10.1000 成交 100。
  const obr::Event closing_bid = make_order("14:57", "145700000", '1', 101000, 60);
  const obr::Event closing_ask_1 = make_order("14:58", "145800000", '2', 100000, 50);
  const obr::Event closing_ask_2 = make_order("14:59", "145959000", '2', 101000, 50);
  book.apply(closing_bid, obr::TradingSession::ClosingAuction);
  book.apply(closing_ask_1, obr::TradingSession::ClosingAuction);
  book.apply(closing_ask_2, obr::TradingSession::ClosingAuction);
  book.finish_call_auction();

  snapshot = book.make_snapshot(closing_ask_2);
  expect(snapshot.bids.size() == 1U, "closing should leave one bid level");
  expect(snapshot.bids[0].price == 100000, "final bid price should be 10.0000");
  expect(snapshot.bids[0].quantity == 30, "final bid quantity should be 30");
  expect(snapshot.asks.empty(), "closing should consume all asks");
  expect(book.cumulative_trade_quantity() == 400, "full day cumulative quantity should be 400");
  expect(book.cumulative_turnover() == 40160000,
         "full day cumulative turnover should be 4016.0000");
}

void validate_cancel() {
  obr::OrderBook book;
  const obr::Event bid = make_order("09:15", "91500000", '1', 101000, 100);
  const obr::Event cancel = make_cancel("09:19", "91900000", 101000, 20);
  const obr::Event ask = make_order("09:24", "92400000", '2', 99000, 100);

  book.apply(bid, obr::TradingSession::OpeningAuction);
  book.apply(cancel, obr::TradingSession::OpeningAuction);
  book.apply(ask, obr::TradingSession::OpeningAuction);
  book.finish_call_auction();

  const obr::Snapshot snapshot = book.make_snapshot(ask);
  expect(snapshot.bids.empty(), "cancel example should consume the remaining bid");
  expect(snapshot.asks.size() == 1U, "cancel example should leave one ask level");
  expect(snapshot.asks[0].price == 99000, "cancel example ask should stay at 9.9000");
  expect(snapshot.asks[0].quantity == 20, "cancel example should leave ask quantity 20");
  expect(book.cumulative_trade_quantity() == 80, "cancel example trade quantity should be 80");
  expect(book.cumulative_turnover() == 7920000, "cancel example turnover should be 792.0000");
}

void validate_multi_level_continuous_trade() {
  obr::OrderBook book;

  // 两个卖价先进入空盘口，随后一张更高限价的买单依次吃掉卖一、卖二。
  const obr::Event ask_1 = make_order("10:00", "100000000", '2', 100000, 30);
  const obr::Event ask_2 = make_order("10:01", "100100000", '2', 101000, 40);
  const obr::Event bid = make_order("10:02", "100200000", '1', 102000, 100);
  book.apply(ask_1, obr::TradingSession::ContinuousAuction);
  book.apply(ask_2, obr::TradingSession::ContinuousAuction);
  book.apply(bid, obr::TradingSession::ContinuousAuction);

  const obr::Snapshot snapshot = book.make_snapshot(bid);
  expect(snapshot.asks.empty(), "multi-level trade should consume both ask levels");
  expect(snapshot.bids.size() == 1U, "buy remainder should enter one bid level");
  expect(snapshot.bids[0].price == 102000, "buy remainder should use its limit price");
  expect(snapshot.bids[0].quantity == 30, "buy remainder should be 30");
  expect(book.cumulative_trade_quantity() == 70, "multi-level cumulative quantity should be 70");
  expect(book.cumulative_turnover() == 7040000,
         "multi-level cumulative turnover should be 704.0000");
}

} // namespace

int main() {
  validate_full_day();
  validate_cancel();
  validate_multi_level_continuous_trade();
  std::cout << "simple reconstruction validation passed\n";
  return EXIT_SUCCESS;
}
