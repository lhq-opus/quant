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

// 两份原始 CSV 合并后保留三类事件。成交会改簿，但不会单独产生快照行。
enum class EventType {
  Order,
  Trade,
  Cancel,
};

// 原始 TransactTime 决定当前事件属于哪个交易阶段。
enum class TradingSession {
  OpeningAuction,
  ContinuousAuction,
  ClosingAuction,
};

// CSV 的列位置只在读取代码中出现，订单簿只接收归一化后的 Event。
// order 的 price/quantity 来自 Price/OrderQty；成交来自 TradePrice/TradeQty。
// 撤单只需 TradeQty 与原订单引用，不需要 Python 预先补全 Side 或 TradePrice。
// 对当前事件无意义的数字和字符字段保持零值，输入保证业务引用合法。
struct Event {
  std::string caa;
  std::string transaction_time;
  std::int64_t sequence_no; // sequenceNo：合并后的事件排序键，不用于定位原订单。
  EventType type;
  char side;
  char order_type;
  Price price;
  Quantity quantity;
  std::int64_t channel_no;
  std::int64_t order_appl_seq_num; // order 自己的 ASN，或 cancel 引用的原订单 ASN。
  std::int64_t bid_appl_seq_num;   // 成交引用的买单 ASN，不是成交消息自己的 ASN。
  std::int64_t offer_appl_seq_num; // 成交引用的卖单 ASN，与买方引用处于同一频道。
};

// 一个 PriceLevel 就是一档“价格 + 聚合数量”。
struct PriceLevel {
  Price price;
  Quantity quantity;
};

// order/cancel 开启一个快照区间。区间内的成交处理完毕后，才提取五档。
// caa 和 event_type 始终来自区间起点，不能被后续 Trade 的元数据覆盖。
struct Snapshot {
  std::string caa;
  EventType event_type;
  std::vector<PriceLevel> bids;
  std::vector<PriceLevel> asks;
};

} // namespace obr
