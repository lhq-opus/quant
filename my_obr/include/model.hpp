#ifndef MY_OBR_MODEL_HPP
#define MY_OBR_MODEL_HPP

#include <cstddef>
#include <stdint.h>
#include <string>
#include <vector>

enum class EventType { Order, Trade, Cancel };

// Keep the existing source spellings until a separate naming change is requested.
enum class TradingSession { OpeningAution, ContinuousTrade, ClosingAuction };

enum class TradeType { Normal, Cancel };

// Value-initialize with {} before assigning parsed fields. Side and order_type
// retain raw CSV characters; fields unrelated to an event remain zero/empty.
struct Event {
  std::string caa;
  std::string transaction_time;
  std::string security_id;
  std::string secid;
  std::string source_path;
  std::size_t source_line;
  int64_t sequence_no;
  // This message's ApplSeqNum, distinct from a referenced original order.
  int64_t appl_seq_num;
  int64_t channel_no;
  EventType type;
  TradingSession trading_session;
  char side;
  char order_type;
  int64_t price;
  int64_t quantity;
  int64_t order_appl_seq_num;
  int64_t bid_appl_seq_num;
  int64_t offer_appl_seq_num;
  // 连续阶段的order/4作为快照起点；后续F处理完才真正拍照。
  bool generate_snapshot;
};

struct TradeInfo {
  TradeType trade_type;
  int64_t price;
};

// 原订单登记。price为实际采用的挂价，0表示本实验中不计入可见价格档。
struct OrderInfo {
  int64_t price;
  char side;
  // 原委托量减去已经重放到的F/4数量，绝不提前扣未来成交或推算待撤量。
  int64_t remaining_quantity;
};

struct PriceLevel {
  int64_t price;
  int64_t quantity;
};

// make_snapshot supplies five levels on each side, padding missing levels with 0.
struct Snapshot {
  std::string caa;
  std::string secid;
  int64_t sequence_no;
  int64_t appl_seq_num;
  std::string transaction_time;
  // Source F statistics through this snapshot's replay position.
  int64_t trade_count;
  int64_t cumulative_trade_quantity;
  int64_t cumulative_turnover;
  int64_t last_trade_price;
  int64_t opening_price;
  EventType event_type;
  TradingSession trading_session;
  std::vector<PriceLevel> bids;
  std::vector<PriceLevel> asks;
};

#endif
