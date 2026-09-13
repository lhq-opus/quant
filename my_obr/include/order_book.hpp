#ifndef MY_OBR_ORDER_BOOK_HPP
#define MY_OBR_ORDER_BOOK_HPP

#include "model.hpp"

#include <functional>
#include <map>
#include <vector>

// Teaching experiment: complete, valid input and representable arithmetic are
// assumed. Equal-price orders follow replay arrival order; source F is not reapplied.
class OrderBook {
public:
  OrderBook();

  // Registry iterators refer to this instance's queues.
  OrderBook(const OrderBook&) = delete;
  OrderBook& operator=(const OrderBook&) = delete;

  void build_trade_map(Event& event);
  void apply(Event& event, TradingSession session);
  void finish_call_auction();
  Snapshot make_snapshot(Event& event);

private:
  // begin() selects the highest bid and lowest ask respectively.
  typedef std::map<int64_t, BookLevel, std::greater<int64_t>> BidLevels;
  typedef std::map<int64_t, BookLevel> AskLevels;
  typedef std::map<int64_t, OrderInfo> OrderPriceMap;
  typedef std::map<int64_t, std::vector<TradeInfo>> OrderTradeMap;

  void apply_market_order(Event& event);
  void apply_BBO_order(Event& event);
  void apply_order_in_acution(Event& event);
  void apply_limit_order(Event& event);
  void apply_cancel(Event& event);
  void record_trade(int64_t price, int64_t quantity);
  void find_call_action_result(int64_t& auction_price, int64_t& trade_quantity,
                               int64_t& remaining_quantity_at_price, char& side);

  BidLevels bids;
  AskLevels asks;
  OrderPriceMap order_price;
  OrderTradeMap order_trade_map;
  int64_t cumulative_trade_quantity_num;
  int64_t cumulative_turnover_num;
  int64_t trade_number;
  int64_t last_price;
  int64_t opening_price;
};

#endif
