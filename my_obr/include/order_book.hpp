#ifndef MY_OBR_ORDER_BOOK_HPP
#define MY_OBR_ORDER_BOOK_HPP

#include "model.hpp"
#include "price_levels.hpp"

#include <map>
#include <utility>
#include <vector>

// 新单只登记并增加本方档位；真实F扣双方，真实4扣被撤一方。
// 有挂价的价格档数量等于该侧、该价所有订单的remaining_quantity之和。
// 市价单是否挂档仍沿用项目的实验推断，不宣称从现有字段可唯一确定交易所类型。
// 成交统计仅累计已成功处理的F；既有校验失败时不改变此前状态。
class OrderBook {
public:
  OrderBook();

  // 预读历史仅供市价挂价推断，不改变订单量、盘口量和成交统计。
  void build_trade_map(const Event& event);
  void apply(const Event& event, TradingSession session);
  Snapshot make_snapshot(const Event& event) const;

private:
  // One trading day per instance. Channel scopes every source order reference.
  typedef std::pair<int64_t, int64_t> OrderKey;
  typedef std::map<OrderKey, OrderInfo> OrderPriceMap;
  typedef std::map<OrderKey, std::vector<TradeInfo>> OrderTradeMap;

  void add_order(const Event& event);
  int64_t find_market_order_price(const Event& event) const;
  void apply_trade(const Event& event);
  void apply_cancel(const Event& event);

  // 两侧价格档只通过 PriceLevels 方法读写，业务函数不再操作底层 map。
  PriceLevels bids;
  PriceLevels asks;
  OrderPriceMap order_price;
  OrderTradeMap order_trade_map;
  // 唯一一套成交统计，全部由真实F更新，首笔F之前为零。
  int64_t source_trade_count;
  int64_t source_trade_quantity;
  int64_t source_turnover;
  int64_t last_trade_price;
  int64_t opening_price;
};

#endif
