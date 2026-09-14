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

  void build_trade_map(const Trade& trade);
  void apply(Order& order);
  void apply(const Trade& trade);
  void finish_call_auction();
  Snapshot make_snapshot(const Order& order);
  Snapshot make_snapshot(const Trade& trade);

private:
  // begin() selects the highest bid and lowest ask respectively.
  typedef std::map<int64_t, BookLevel, std::greater<int64_t>> BidLevels;
  typedef std::map<int64_t, BookLevel> AskLevels;
  typedef std::map<int64_t, OrderInfo> OrderPriceMap;
  typedef std::map<int64_t, std::vector<TradeInfo>> OrderTradeMap;

  void apply_market_order(Order& order);
  void apply_BBO_order(Order& order);
  void apply_order_in_acution(Order& order);
  void apply_limit_order(Order& order);
  void apply_cancel(const Trade& trade);
  Snapshot make_snapshot(const std::string& caa, EventType event_type, TradingSession session);
  // 执行已确定价格、数量的成交，并统一维护订单、档位和成交统计。
  // reduce_bids/reduce_asks 指定扣减侧：连续撮合只扣对手侧，集合竞价同时扣两侧。
  // 从所选侧最优档的 FIFO 队首扣量；price 是成交价，竞价时可不同于订单挂价。
  // 调用方保证可成交量充足；连续撮合每次只传当前一个价档的成交量。
  void execute_trade(int64_t price, int64_t quantity, bool reduce_bids, bool reduce_asks);
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
