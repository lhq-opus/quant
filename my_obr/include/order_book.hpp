#ifndef MY_OBR_ORDER_BOOK_HPP
#define MY_OBR_ORDER_BOOK_HPP

#include "model.hpp"
#include "price_levels.hpp"

#include <map>
#include <utility>
#include <vector>

// Price levels still follow the experimental matching rules. Source executions
// validate order remainders and update output statistics without applying the
// same fills to levels again. Output statistics count only processed source F.
// An invalid event throws std::exception and leaves the prior book state intact.
class OrderBook {
public:
  OrderBook();

  void build_trade_map(Event& event);
  void apply(Event& event, TradingSession session);
  void finish_call_auction();
  Snapshot make_snapshot(Event& event);

private:
  // One trading day per instance. Channel scopes every source order reference.
  typedef std::pair<int64_t, int64_t> OrderKey;
  typedef std::map<OrderKey, OrderInfo> OrderPriceMap;
  typedef std::map<OrderKey, std::vector<TradeInfo>> OrderTradeMap;

  void apply_market_order(Event& event);
  void apply_BBO_order(Event& event);
  void apply_order_in_acution(Event& event);
  void apply_limit_order(Event& event);
  void apply_cancel(Event& event);
  void record_trade(int64_t price, int64_t quantity);
  void find_call_action_result(int64_t& auction_price, int64_t& trade_quantity,
                               int64_t& remaining_quantity_at_price, char& side);

  // 两侧价格档只通过 PriceLevels 方法读写，业务函数不再操作底层 map。
  PriceLevels bids;
  PriceLevels asks;
  OrderPriceMap order_price;
  OrderTradeMap order_trade_map;
  // Simulated matching totals retained for the existing experiment.
  int64_t cumulative_trade_quantity_num;
  int64_t cumulative_turnover_num;
  // Independent source F totals exported in book.csv; zero before the first F.
  int64_t source_trade_count;
  int64_t source_trade_quantity;
  int64_t source_turnover;
  int64_t last_trade_price;
  int64_t opening_price;
};

#endif
