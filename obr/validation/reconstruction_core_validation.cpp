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

obr::Event make_order(const char* caa, const char* transaction_time, char side, char order_type,
                      obr::Price price, obr::Quantity quantity) {
  const obr::Event event = {caa,   transaction_time, obr::EventType::Order, side, order_type,
                            price, quantity};
  return event;
}

obr::Event make_cancel(const char* caa, const char* transaction_time, char side, obr::Price price,
                       obr::Quantity quantity) {
  const obr::Event event = {caa,   transaction_time, obr::EventType::Cancel, side, '\0',
                            price, quantity};
  return event;
}

void validate_full_day() {
  obr::OrderBook book;

  // 开盘集合竞价：最大成交量 250，统一成交价 10.0000。
  const obr::Event opening_bid_1 = make_order("09:15", "91500790", '1', '2', 101000, 100);
  const obr::Event opening_bid_2 = make_order("09:16", "91600000", '1', '2', 100000, 200);
  const obr::Event opening_ask_1 = make_order("09:17", "91700000", '2', '2', 99000, 150);
  const obr::Event opening_ask_2 = make_order("09:18", "91800000", '2', '2', 100000, 100);

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
  const obr::Event continuous_ask = make_order("09:30", "93000000", '2', '2', 99500, 20);
  const obr::Event continuous_bid = make_order("10:04", "100407190", '1', '2', 102000, 70);
  const obr::Event continuous_ask_2 = make_order("10:05", "100500000", '2', '2', 101000, 30);
  book.apply(continuous_ask, obr::TradingSession::ContinuousAuction);
  book.apply(continuous_bid, obr::TradingSession::ContinuousAuction);
  book.apply(continuous_ask_2, obr::TradingSession::ContinuousAuction);

  // 收盘集合竞价：新增买卖盘统一在 10.1000 成交 100。
  const obr::Event closing_bid = make_order("14:57", "145700000", '1', '2', 101000, 60);
  const obr::Event closing_ask_1 = make_order("14:58", "145800000", '2', '2', 100000, 50);
  const obr::Event closing_ask_2 = make_order("14:59", "145959000", '2', '2', 101000, 50);
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
  const obr::Event bid = make_order("09:15", "91500000", '1', '2', 101000, 100);
  const obr::Event cancel = make_cancel("09:19", "91900000", '1', 101000, 20);
  const obr::Event ask = make_order("09:24", "92400000", '2', '2', 99000, 100);

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

void validate_cancel_side_with_crossed_price() {
  obr::OrderBook book;

  // 集合竞价尚未统一撮合时，买卖双方可以在同一个价格上同时有数量。
  const obr::Event bid = make_order("09:15", "91500000", '1', '2', 100000, 100);
  const obr::Event ask = make_order("09:16", "91600000", '2', '2', 100000, 80);
  const obr::Event cancel_ask = make_cancel("09:17", "91700000", '2', 100000, 30);
  const obr::Event cancel_bid = make_cancel("09:18", "91800000", '1', 100000, 20);

  book.apply(bid, obr::TradingSession::OpeningAuction);
  book.apply(ask, obr::TradingSession::OpeningAuction);
  book.apply(cancel_ask, obr::TradingSession::OpeningAuction);

  obr::Snapshot snapshot = book.make_snapshot(cancel_ask);
  expect(snapshot.bids[0].quantity == 100, "sell cancel must not reduce same-price bid");
  expect(snapshot.asks[0].quantity == 50, "sell cancel should reduce same-price ask");

  book.apply(cancel_bid, obr::TradingSession::OpeningAuction);
  snapshot = book.make_snapshot(cancel_bid);
  expect(snapshot.bids[0].quantity == 80, "buy cancel should reduce same-price bid");
  expect(snapshot.asks[0].quantity == 50, "buy cancel must not reduce same-price ask");
}

void validate_multi_level_continuous_trade() {
  obr::OrderBook book;

  // 两个卖价先进入空盘口，随后一张更高限价的买单依次吃掉卖一、卖二。
  const obr::Event ask_1 = make_order("10:00", "100000000", '2', '2', 100000, 30);
  const obr::Event ask_2 = make_order("10:01", "100100000", '2', '2', 101000, 40);
  const obr::Event bid = make_order("10:02", "100200000", '1', '2', 102000, 100);
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

void validate_buy_opponent_and_own_best_orders() {
  obr::OrderBook book;

  // 先放入 10.1000 的卖一。随后类型 1 买单的 CSV Price 故意填 0，证明实际限价
  // 来自到达时的对手方最优价，而不是原始 Price。
  const obr::Event ask = make_order("10:00", "100000000", '2', '2', 101000, 30);
  const obr::Event opponent_best_buy = make_order("10:01", "100100000", '1', '1', 0, 50);
  book.apply(ask, obr::TradingSession::ContinuousAuction);
  book.apply(opponent_best_buy, obr::TradingSession::ContinuousAuction);

  obr::Snapshot snapshot = book.make_snapshot(opponent_best_buy);
  expect(snapshot.asks.empty(), "type 1 buy should consume the opponent best ask");
  expect(snapshot.bids.size() == 1U, "type 1 buy remainder should enter the bid book");
  expect(snapshot.bids[0].price == 101000,
         "type 1 buy remainder should use the former best ask price");
  expect(snapshot.bids[0].quantity == 20, "type 1 buy remainder should be 20");

  // U 买单同样故意填 Price=0；它不主动成交，只加入当前买一 10.1000。
  const obr::Event own_best_buy = make_order("10:02", "100200000", '1', 'U', 0, 15);
  book.apply(own_best_buy, obr::TradingSession::ContinuousAuction);
  snapshot = book.make_snapshot(own_best_buy);
  expect(snapshot.bids[0].price == 101000, "U buy should use the current best bid price");
  expect(snapshot.bids[0].quantity == 35, "U buy should join the current best bid level");
  expect(book.cumulative_trade_quantity() == 30, "type 1 buy should trade 30");
  expect(book.cumulative_turnover() == 3030000, "type 1 buy turnover should be 303.0000");
}

void validate_sell_opponent_and_own_best_orders() {
  obr::OrderBook book;

  // 卖方逻辑与买方对称：类型 1 卖单使用到达时的买一 10.0000，只成交该档，
  // 剩余 10 股转成 10.0000 的卖单。
  const obr::Event bid = make_order("10:00", "100000000", '1', '2', 100000, 40);
  const obr::Event opponent_best_sell = make_order("10:01", "100100000", '2', '1', 0, 50);
  book.apply(bid, obr::TradingSession::ContinuousAuction);
  book.apply(opponent_best_sell, obr::TradingSession::ContinuousAuction);

  obr::Snapshot snapshot = book.make_snapshot(opponent_best_sell);
  expect(snapshot.bids.empty(), "type 1 sell should consume the opponent best bid");
  expect(snapshot.asks.size() == 1U, "type 1 sell remainder should enter the ask book");
  expect(snapshot.asks[0].price == 100000,
         "type 1 sell remainder should use the former best bid price");
  expect(snapshot.asks[0].quantity == 10, "type 1 sell remainder should be 10");

  const obr::Event own_best_sell = make_order("10:02", "100200000", '2', 'U', 0, 15);
  book.apply(own_best_sell, obr::TradingSession::ContinuousAuction);
  snapshot = book.make_snapshot(own_best_sell);
  expect(snapshot.asks[0].price == 100000, "U sell should use the current best ask price");
  expect(snapshot.asks[0].quantity == 25, "U sell should join the current best ask level");
  expect(book.cumulative_trade_quantity() == 40, "type 1 sell should trade 40");
  expect(book.cumulative_turnover() == 4000000, "type 1 sell turnover should be 400.0000");
}

void validate_best_price_orders_with_empty_book() {
  obr::OrderBook book;

  // 对手方最优没有对手盘、本方最优没有本方盘口时，都没有可采用的价格，申报自动撤销。
  const obr::Event opponent_best_buy = make_order("10:00", "100000000", '1', '1', 0, 10);
  const obr::Event own_best_buy = make_order("10:01", "100100000", '1', 'U', 0, 10);
  const obr::Event opponent_best_sell = make_order("10:02", "100200000", '2', '1', 0, 10);
  const obr::Event own_best_sell = make_order("10:03", "100300000", '2', 'U', 0, 10);
  book.apply(opponent_best_buy, obr::TradingSession::ContinuousAuction);
  book.apply(own_best_buy, obr::TradingSession::ContinuousAuction);
  book.apply(opponent_best_sell, obr::TradingSession::ContinuousAuction);
  book.apply(own_best_sell, obr::TradingSession::ContinuousAuction);

  const obr::Snapshot snapshot = book.make_snapshot(own_best_sell);
  expect(snapshot.bids.empty(), "empty-book best-price orders should leave no bids");
  expect(snapshot.asks.empty(), "empty-book best-price orders should leave no asks");
  expect(book.cumulative_trade_quantity() == 0,
         "empty-book best-price orders should produce no trades");
}

} // namespace

int main() {
  validate_full_day();
  validate_cancel();
  validate_cancel_side_with_crossed_price();
  validate_multi_level_continuous_trade();
  validate_buy_opponent_and_own_best_orders();
  validate_sell_opponent_and_own_best_orders();
  validate_best_price_orders_with_empty_book();
  std::cout << "simple reconstruction validation passed\n";
  return EXIT_SUCCESS;
}
