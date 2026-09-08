#pragma once

#include "obr/domain.hpp"

#include <functional>
#include <map>
#include <utility>

namespace obr {

// 第一版 OrderBook 用价格档保存数量，用订单引用定位成交和撤单，不模拟连续撮合。
//
// 买盘 map 使用 std::greater<Price>，所以 begin() 永远是最高买价；
// 卖盘 map 使用默认升序，所以 begin() 永远是最低卖价。
// 因此 begin() 可用于 U 单定价、集合竞价和提取五档。
class OrderBook {
public:
  OrderBook();

  // 应用一条已经从 CSV 转换好的 Event。
  // order 只增加本方数量；连续成交按原订单引用扣两侧；撤单扣一侧。
  // 集合竞价的 F 不在这里扣量，阶段末仍由 finish_call_auction 统一处理。
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

  // 我们只重建聚合盘口，因此索引只需方向和挂价，不另建订单级 FIFO 队列。
  // 数量保存在 bids_/asks_；输入保证成交和撤单不会超过对应原订单的剩余量。
  struct OrderInfo {
    char side;
    Price price; // 0 表示没有挂入可见价格档，不代表一个价格为 0 的档位。
  };

  void add_order(const Event& event);
  void apply_trade(const Event& event);
  void reduce_order(const OrderKey& key, Quantity quantity);
  void record_trade(Price price, Quantity quantity);

  // 筛选集合竞价成交价，最终并列时用真实成交价定位；没有可成交数量则返回 false。
  bool find_call_auction_result(Price actual_price, Price& auction_price,
                                Quantity& trade_quantity) const;

  BidLevels bids_;
  AskLevels asks_;
  // 单证券、单交易日内，以 ChannelNo + 原订单 ApplSeqNum 定位。
  // 即使某档暂时吃空，索引仍保留原挂价；后续事件不重新用当前最优价定价。
  std::map<OrderKey, OrderInfo> orders_;
  Quantity cumulative_trade_quantity_;
  Turnover cumulative_turnover_;
};

} // namespace obr
