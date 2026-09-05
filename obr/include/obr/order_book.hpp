#pragma once

#include "obr/domain.hpp"

#include <functional>
#include <map>
#include <utility>

namespace obr {

// 第一版 OrderBook 按价格档撮合；订单引用只用于查回撤单价格，不维护同价订单队列。
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
  // 最终候选并列时，采用该阶段真实 trade 的成交价；唯一候选不需要额外提示。
  void finish_call_auction(Price actual_price = 0);

  // 从内部全深度 map 中截取买卖各五档。
  Snapshot make_snapshot(const Event& event) const;

  Quantity cumulative_trade_quantity() const;
  Turnover cumulative_turnover() const;

private:
  typedef std::map<Price, Quantity, std::greater<Price>> BidLevels;
  typedef std::map<Price, Quantity> AskLevels;
  typedef std::pair<std::int64_t, std::int64_t> OrderKey;

  void add_order(const Event& event);
  void apply_opponent_best_order(const Event& event);
  void apply_own_best_order(const Event& event);
  void apply_limit_order(const Event& event, Price limit_price);
  void apply_cancel(const Event& event);
  void record_trade(Price price, Quantity quantity);

  // 筛选集合竞价成交价，最终并列时用真实成交价定位；没有可成交数量则返回 false。
  bool find_call_auction_result(Price actual_price, Price& auction_price,
                                Quantity& trade_quantity) const;

  BidLevels bids_;
  AskLevels asks_;
  // 单证券、单交易日内以频道和原订单 ASN 为键。只记定价，不跟踪每张订单的成交量。
  // 0 表示 1/U 因缺少最优价格自动撤销，之后的撤单消息无需再次扣减盘口。
  std::map<OrderKey, Price> order_prices_;
  Quantity cumulative_trade_quantity_;
  Turnover cumulative_turnover_;
};

} // namespace obr
