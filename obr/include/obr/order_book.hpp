#pragma once

#include "obr/domain.hpp"

#include <functional>
#include <map>

namespace obr {

// 第一版 OrderBook 只维护聚合价格档，不维护订单 ID 或同价订单队列。
//
// 买盘 map 使用 std::greater<Price>，所以 begin() 永远是最高买价；
// 卖盘 map 使用默认升序，所以 begin() 永远是最低卖价。
// 这让连续竞价可以直接从双方的 begin() 开始撮合。
class OrderBook {
public:
  OrderBook();

  // 应用一条已经从 CSV 转换好的 Event。
  // 连续竞价根据 OrderType 分别处理 1、2、U；集合竞价的合法限价单只进入本方价格档。
  void apply(const Event& event, TradingSession session);

  // 一段开盘或收盘集合竞价结束时调用一次，统一确定成交价并扣减数量。
  void finish_call_auction();

  // 从内部全深度 map 中截取买卖各五档。
  Snapshot make_snapshot(const Event& event) const;

  Quantity cumulative_trade_quantity() const;
  Turnover cumulative_turnover() const;

private:
  typedef std::map<Price, Quantity, std::greater<Price>> BidLevels;
  typedef std::map<Price, Quantity> AskLevels;

  void add_order(const Event& event);
  void apply_opponent_best_order(const Event& event);
  void apply_own_best_order(const Event& event);
  void apply_limit_order(const Event& event, Price limit_price);
  void apply_cancel(const Event& event);
  void record_trade(Price price, Quantity quantity);

  // 找到集合竞价唯一成交价。返回 false 表示当前买卖盘没有可成交数量。
  bool find_call_auction_result(Price& auction_price, Quantity& trade_quantity) const;

  BidLevels bids_;
  AskLevels asks_;
  Quantity cumulative_trade_quantity_;
  Turnover cumulative_turnover_;
};

} // namespace obr
