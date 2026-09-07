#include "obr/order_book.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace {

void expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << "validation failed: " << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

obr::Event make_order(const char* caa, const char* transaction_time, char side, char order_type,
                      obr::Price price, obr::Quantity quantity, std::int64_t order_seq) {
  const obr::Event event = {
      caa, transaction_time, obr::EventType::Order, side, order_type, price, quantity, 1, order_seq,
      0};
  return event;
}

obr::Event make_cancel(const char* caa, const char* transaction_time, const obr::Event& order,
                       obr::Quantity quantity) {
  // 撤单保留原订单价格（1/U 可以是 0），但必须携带该订单的真实引用与方向。
  const obr::Event event = {
      caa,      transaction_time, obr::EventType::Cancel,   order.side, '\0', order.price,
      quantity, order.channel_no, order.order_appl_seq_num, 0};
  return event;
}

void validate_full_day() {
  obr::OrderBook book;

  // 开盘集合竞价：最大成交量 250，统一成交价 10.0000。
  const obr::Event opening_bid_1 = make_order("09:15", "91500790", '1', '2', 101000, 100, 1);
  const obr::Event opening_bid_2 = make_order("09:16", "91600000", '1', '2', 100000, 200, 2);
  const obr::Event opening_ask_1 = make_order("09:17", "91700000", '2', '2', 99000, 150, 3);
  const obr::Event opening_ask_2 = make_order("09:18", "91800000", '2', '2', 100000, 100, 4);

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
  const obr::Event continuous_ask = make_order("09:30", "93000000", '2', '2', 99500, 20, 5);
  const obr::Event continuous_bid = make_order("10:04", "100407190", '1', '2', 102000, 70, 6);
  const obr::Event continuous_ask_2 = make_order("10:05", "100500000", '2', '2', 101000, 30, 7);
  book.apply(continuous_ask, obr::TradingSession::ContinuousAuction);
  book.apply(continuous_bid, obr::TradingSession::ContinuousAuction);
  book.apply(continuous_ask_2, obr::TradingSession::ContinuousAuction);

  // 收盘集合竞价：新增买卖盘统一在 10.1000 成交 100。
  const obr::Event closing_bid = make_order("14:57", "145700000", '1', '2', 101000, 60, 8);
  const obr::Event closing_ask_1 = make_order("14:58", "145800000", '2', '2', 100000, 50, 9);
  const obr::Event closing_ask_2 = make_order("14:59", "145959000", '2', '2', 101000, 50, 10);
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
  const obr::Event bid = make_order("09:15", "91500000", '1', '2', 101000, 100, 1);
  const obr::Event cancel = make_cancel("09:19", "91900000", bid, 20);
  const obr::Event ask = make_order("09:24", "92400000", '2', '2', 99000, 100, 3);

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
  const obr::Event bid = make_order("09:15", "91500000", '1', '2', 100000, 100, 1);
  const obr::Event ask = make_order("09:16", "91600000", '2', '2', 100000, 80, 2);
  const obr::Event cancel_ask = make_cancel("09:17", "91700000", ask, 30);
  const obr::Event cancel_bid = make_cancel("09:18", "91800000", bid, 20);

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
  const obr::Event ask_1 = make_order("10:00", "100000000", '2', '2', 100000, 30, 1);
  const obr::Event ask_2 = make_order("10:01", "100100000", '2', '2', 101000, 40, 2);
  const obr::Event bid = make_order("10:02", "100200000", '1', '2', 102000, 100, 3);
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

void validate_market_order_sweeps_levels(char side) {
  obr::OrderBook book;

  // 买单：卖一 10.00×100、卖二 10.01×200，市价买 150 后应留下 10.01×150。
  // 卖单：买一 10.00×100、买二 9.99×200，市价卖 150 后应留下 9.99×150。
  const char opponent_side = side == '1' ? '2' : '1';
  const obr::Price second_price = side == '1' ? 100100 : 99900;
  const obr::Event first = make_order("10:00", "100000000", opponent_side, '2', 100000, 100, 1);
  const obr::Event second =
      make_order("10:01", "100100000", opponent_side, '2', second_price, 200, 2);
  const obr::Event market = make_order("10:02", "100200000", side, '1', 0, 150, 3);
  book.apply(first, obr::TradingSession::ContinuousAuction);
  book.apply(second, obr::TradingSession::ContinuousAuction);
  book.apply(market, obr::TradingSession::ContinuousAuction);

  const obr::Snapshot snapshot = book.make_snapshot(market);
  const std::vector<obr::PriceLevel>& opposite = side == '1' ? snapshot.asks : snapshot.bids;
  const std::vector<obr::PriceLevel>& own = side == '1' ? snapshot.bids : snapshot.asks;
  expect(own.empty(), "market order must not leave a resting order");
  expect(opposite.size() == 1U, "market order should consume the first level");
  expect(opposite[0].price == second_price && opposite[0].quantity == 150,
         "market order should continue trading 50 at the second level");
  expect(book.cumulative_trade_quantity() == 150, "market order should trade 150");
  expect(book.cumulative_turnover() == (side == '1' ? 15005000 : 14995000),
         "each market fill should use its opposing level price");
}

void validate_market_order_cancels_remainder(char side) {
  obr::OrderBook book;

  // 对手方两档合计只有 70，市价单 100 成交后，剩余 30 应直接撤销。
  const char opponent_side = side == '1' ? '2' : '1';
  const obr::Price own_price = side == '1' ? 99000 : 101000;
  const obr::Price second_price = side == '1' ? 100100 : 99900;
  const obr::Event own_limit = make_order("10:00", "100000000", side, '2', own_price, 70, 1);
  const obr::Event first = make_order("10:01", "100100000", opponent_side, '2', 100000, 30, 2);
  const obr::Event second =
      make_order("10:02", "100200000", opponent_side, '2', second_price, 40, 3);
  const obr::Event market = make_order("10:03", "100300000", side, '1', 0, 100, 4);
  book.apply(own_limit, obr::TradingSession::ContinuousAuction);
  book.apply(first, obr::TradingSession::ContinuousAuction);
  book.apply(second, obr::TradingSession::ContinuousAuction);
  book.apply(market, obr::TradingSession::ContinuousAuction);

  const obr::Snapshot snapshot = book.make_snapshot(market);
  const std::vector<obr::PriceLevel>& opposite = side == '1' ? snapshot.asks : snapshot.bids;
  const std::vector<obr::PriceLevel>& own = side == '1' ? snapshot.bids : snapshot.asks;
  expect(opposite.empty(), "market order should consume all available opposite quantity");
  expect(own.size() == 1U && own[0].price == own_price && own[0].quantity == 70,
         "market remainder must not change the own-side book");

  // 随后另一张订单挂在最后成交价。原市价单的撤单通知不能误扣这张新订单。
  const obr::Event later = make_order("10:04", "100400000", side, '2', second_price, 60, 5);
  const obr::Event cancel = make_cancel("10:05", "100500000", market, 30);
  book.apply(later, obr::TradingSession::ContinuousAuction);
  book.apply(cancel, obr::TradingSession::ContinuousAuction);
  const obr::Snapshot after_cancel = book.make_snapshot(cancel);
  const std::vector<obr::PriceLevel>& remaining =
      side == '1' ? after_cancel.bids : after_cancel.asks;
  expect(remaining.size() == 2U && remaining[0].price == second_price &&
             remaining[0].quantity == 60 && remaining[1].price == own_price &&
             remaining[1].quantity == 70,
         "IOC cancel notification must not reduce other resting orders");
  expect(book.cumulative_trade_quantity() == 70, "IOC remainder cancel must not add trades");
  expect(book.cumulative_turnover() == (side == '1' ? 7004000 : 6996000),
         "IOC remainder cancel must not change turnover");
}

void validate_market_order_beyond_five_levels(char side) {
  obr::OrderBook book;

  // 五档只是输出深度。放入七档、每档 10 股，市价单 65 必须成交到第七档。
  const char opponent_side = side == '1' ? '2' : '1';
  const obr::Price price_step = side == '1' ? 100 : -100;
  for (int level = 0; level < 7; ++level) {
    const obr::Event order = make_order("10:00", "100000000", opponent_side, '2',
                                        100000 + level * price_step, 10, level + 1);
    book.apply(order, obr::TradingSession::ContinuousAuction);
  }
  const obr::Event market = make_order("10:01", "100100000", side, '1', 0, 65, 8);
  book.apply(market, obr::TradingSession::ContinuousAuction);
  const obr::Snapshot snapshot = book.make_snapshot(market);
  const std::vector<obr::PriceLevel>& opposite = side == '1' ? snapshot.asks : snapshot.bids;
  expect(opposite.size() == 1U && opposite[0].price == 100000 + 6 * price_step &&
             opposite[0].quantity == 5,
         "market order should reach the seventh level and leave 5");
  expect(book.cumulative_trade_quantity() == 65, "market matching must not stop at five levels");
  expect(book.cumulative_turnover() == (side == '1' ? 6518000 : 6482000),
         "deep market fills should use every consumed price");
}

void validate_own_best_order_and_cancel(char side) {
  obr::OrderBook book;

  // U 的 Price=0，实际加入 10.00。之后本方最优价变化，撤单仍应扣原来的 10.00。
  const obr::Event limit = make_order("10:00", "100000000", side, '2', 100000, 40, 1);
  const obr::Event own_best = make_order("10:01", "100100000", side, 'U', 0, 15, 2);
  const obr::Price better_price = side == '1' ? 100100 : 99900;
  const obr::Event better = make_order("10:02", "100200000", side, '2', better_price, 20, 3);
  book.apply(limit, obr::TradingSession::ContinuousAuction);
  book.apply(own_best, obr::TradingSession::ContinuousAuction);
  book.apply(better, obr::TradingSession::ContinuousAuction);

  const obr::Snapshot before_cancel = book.make_snapshot(better);
  const std::vector<obr::PriceLevel>& before =
      side == '1' ? before_cancel.bids : before_cancel.asks;
  expect(before.size() == 2U && before[1].price == 100000 && before[1].quantity == 55,
         "U order should join the best price at its arrival");
  const obr::Event cancel = make_cancel("10:03", "100300000", own_best, 15);
  book.apply(cancel, obr::TradingSession::ContinuousAuction);
  const obr::Snapshot after_cancel = book.make_snapshot(cancel);
  const std::vector<obr::PriceLevel>& after = side == '1' ? after_cancel.bids : after_cancel.asks;
  expect(after.size() == 2U && after[0].price == better_price && after[0].quantity == 20 &&
             after[1].price == 100000 && after[1].quantity == 40,
         "U cancel should use its original assigned price, not the new best price");
  expect(book.cumulative_trade_quantity() == 0 && book.cumulative_turnover() == 0,
         "own-best additions and cancellations must not generate trades");
}

void validate_market_and_own_best_with_empty_book() {
  obr::OrderBook book;

  // 市价单没有对手盘时全部撤销；U 没有本方最优价时也自动撤销。
  const obr::Event market_buy = make_order("10:00", "100000000", '1', '1', 0, 10, 1);
  const obr::Event own_best_buy = make_order("10:01", "100100000", '1', 'U', 0, 10, 2);
  const obr::Event market_sell = make_order("10:02", "100200000", '2', '1', 0, 10, 3);
  const obr::Event own_best_sell = make_order("10:03", "100300000", '2', 'U', 0, 10, 4);
  book.apply(market_buy, obr::TradingSession::ContinuousAuction);
  book.apply(own_best_buy, obr::TradingSession::ContinuousAuction);
  book.apply(market_sell, obr::TradingSession::ContinuousAuction);
  book.apply(own_best_sell, obr::TradingSession::ContinuousAuction);

  // 自动撤销的新增事件没有入簿，后续对应撤单消息也不应访问价格 0 的盘口。
  book.apply(make_cancel("10:04", "100400000", market_buy, 10),
             obr::TradingSession::ContinuousAuction);
  book.apply(make_cancel("10:05", "100500000", own_best_buy, 10),
             obr::TradingSession::ContinuousAuction);
  book.apply(make_cancel("10:06", "100600000", market_sell, 10),
             obr::TradingSession::ContinuousAuction);
  book.apply(make_cancel("10:07", "100700000", own_best_sell, 10),
             obr::TradingSession::ContinuousAuction);

  const obr::Snapshot snapshot = book.make_snapshot(own_best_sell);
  expect(snapshot.bids.empty(), "empty-book market and U orders should leave no bids");
  expect(snapshot.asks.empty(), "empty-book market and U orders should leave no asks");
  expect(book.cumulative_trade_quantity() == 0,
         "empty-book market and U orders should produce no trades");
}

void validate_call_auction_inclusive_difference() {
  obr::OrderBook book;

  // 10.00 与 10.01 都能成交 100，但含等价申报的买卖量之差分别为 0 与 100。
  // 因此唯一成交价应为 10.00，不能用严格价优量之差错误地选出 10.01。
  const obr::Event bid = make_order("09:15", "91500000", '1', '2', 100200, 100, 1);
  const obr::Event ask_1 = make_order("09:16", "91600000", '2', '2', 100000, 100, 2);
  const obr::Event ask_2 = make_order("09:17", "91700000", '2', '2', 100100, 100, 3);
  book.apply(bid, obr::TradingSession::OpeningAuction);
  book.apply(ask_1, obr::TradingSession::OpeningAuction);
  book.apply(ask_2, obr::TradingSession::OpeningAuction);
  book.finish_call_auction();

  const obr::Snapshot snapshot = book.make_snapshot(ask_2);
  expect(snapshot.bids.empty(), "inclusive difference example should consume the bid");
  expect(snapshot.asks.size() == 1U && snapshot.asks[0].price == 100100 &&
             snapshot.asks[0].quantity == 100,
         "inclusive difference example should leave the 10.01 ask");
  expect(book.cumulative_trade_quantity() == 100, "inclusive difference trade should be 100");
  expect(book.cumulative_turnover() == 10000000,
         "inclusive difference should select 10.00 and turnover 1000.0000");
}

void validate_call_auction_actual_price(obr::Price bid_price, obr::Price actual_price) {
  obr::OrderBook book;

  // 买卖量相等且价格交叉时，区间内的候选价可能完全并列。
  // 用实际 trade 价格消除歧义，验证价格可以是申报价，也可以位于申报价之间。
  const obr::Event bid = make_order("09:15", "91500000", '1', '2', bid_price, 100, 1);
  const obr::Event ask = make_order("09:16", "91600000", '2', '2', 100000, 100, 2);
  book.apply(bid, obr::TradingSession::OpeningAuction);
  book.apply(ask, obr::TradingSession::OpeningAuction);
  book.finish_call_auction(actual_price);

  const obr::Snapshot snapshot = book.make_snapshot(ask);
  expect(snapshot.bids.empty() && snapshot.asks.empty(),
         "balanced auction should consume both sides at the actual price");
  expect(book.cumulative_trade_quantity() == 100, "balanced auction should trade 100 only once");
  expect(book.cumulative_turnover() == actual_price * 100,
         "auction turnover should use the actual trade price");
}

} // namespace

int main() {
  validate_full_day();
  validate_cancel();
  validate_cancel_side_with_crossed_price();
  validate_multi_level_continuous_trade();
  validate_market_order_sweeps_levels('1');
  validate_market_order_sweeps_levels('2');
  validate_market_order_cancels_remainder('1');
  validate_market_order_cancels_remainder('2');
  validate_market_order_beyond_five_levels('1');
  validate_market_order_beyond_five_levels('2');
  validate_own_best_order_and_cancel('1');
  validate_own_best_order_and_cancel('2');
  validate_market_and_own_best_with_empty_book();
  validate_call_auction_inclusive_difference();
  validate_call_auction_actual_price(100100, 100000);
  validate_call_auction_actual_price(100100, 100100);
  validate_call_auction_actual_price(100200, 100100);
  std::cout << "simple reconstruction validation passed\n";
  return EXIT_SUCCESS;
}
