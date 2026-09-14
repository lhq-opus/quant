#ifndef MY_OBR_ORDER_BOOK_HPP
#define MY_OBR_ORDER_BOOK_HPP

#include "model.hpp"

#include <functional>
#include <map>
#include <set>
#include <utility>
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

  // 只覆盖 snapshot 的买卖五档：价格由优到劣，数量为档位总量，缺档补零。
  // 不改变快照的元信息、成交统计或盘口；同一 snapshot 可以反复填充。
  void fill_snapshot_levels(Snapshot& snapshot) const;

  // 分别判断 Trade 的买方、卖方原单是否为已处理过的市价委托，覆盖两个输出值。
  // 适用于普通成交和撤单引用；这两个值表示原单类型，不表示要扣哪一侧盘口。
  void get_market_trade_sides(const Trade& trade, bool& is_bid, bool& is_ask) const;

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
  // 保存本盘口实例已收到的市价原单身份：(通道，原委托序号)。实例按单交易日使用。
  // 全部成交或撤单后也保留，后续 Trade 仍可查询，不依赖活动订单是否还在簿内。
  std::set<std::pair<int64_t, int64_t>> market_order_ids;
  int64_t cumulative_trade_quantity_num;
  int64_t cumulative_turnover_num;
  int64_t trade_number;
  int64_t last_price;
  int64_t opening_price;
};

#endif
