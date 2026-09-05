#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace obr {

// 第一版不用复杂的价格类。Price 就是一个 64 位整数，单位是 0.0001 元。
// 例如 CSV 中的 10.10 会保存成 101000，写回 CSV 时再恢复成 10.1000。
// 这样仍然能避免 double 带来的小数误差，同时语法很基础。
typedef std::int64_t Price;

// 数量和成交额也直接使用 64 位整数。
// Turnover 的单位是“价格的 0.0001 单位 × 数量”。
typedef std::int64_t Quantity;
typedef std::int64_t Turnover;

// event.csv 里只有两类需要 replay 的事件：order 和 ExecType=4 的撤单。
enum class EventType {
  Order,
  Cancel,
};

// TransactionTime 决定当前事件属于哪个交易阶段。
enum class TradingSession {
  OpeningAuction,
  ContinuousAuction,
  ClosingAuction,
};

// CSV 的 order 行和 cancel 行最终都转换成这个简单 Event。
//
// order：
//   side       <- Side
//   order_type <- OrderType（1=市价、2=限价、U=本方最优）
//   price      <- Price（只有类型 2 直接把它当成限价使用）
//   quantity   <- OrderQty
//
// cancel：
//   type       <- ExecType=4
//   side       <- Side
//   price      <- TradePrice
//   quantity   <- TradeQty
//
// cancel 的 Side 由上游从原订单补全；order_type 对撤单无意义，填成 '\0'。
// 两类事件都保存 ChannelNo 与原订单的 ASN，用于撤单时查回实际挂单价。
// cancel.price 仍保留原始 TradePrice，但类型 1/U 可能动态定价，不能用它定位盘口。
// auction_price 来自当前集合阶段真实成交的 TradePrice；连续阶段或无成交时为 0。
struct Event {
  std::string caa;
  std::string transaction_time;
  EventType type;
  char side;
  char order_type;
  Price price;
  Quantity quantity;
  std::int64_t channel_no;
  std::int64_t order_appl_seq_num;
  Price auction_price;
};

// 一个 PriceLevel 就是一档“价格 + 聚合数量”。
struct PriceLevel {
  Price price;
  Quantity quantity;
};

// 每处理完一条 Event，就从全深度订单簿中截取买卖各五档形成 Snapshot。
struct Snapshot {
  std::string caa;
  EventType event_type;
  std::vector<PriceLevel> bids;
  std::vector<PriceLevel> asks;
};

} // namespace obr
