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

// These are the implementation's inferred categories, not raw exchange codes.
enum class MarketOrderType { TradeAtBest, CancelAfterFiveLevel, TradeWithSlippage };

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
  bool need_handle;
  bool generate_snapshot;
};

struct TradeInfo {
  TradeType trade_type;
  int64_t price;
  int64_t quantity;
};

// The existing implementation uses this field order for aggregate initialization.
struct OrderInfo {
  int64_t price;
  char side;
  // Original quantity minus source F/4 events, not simulated level fills.
  int64_t remaining_quantity;
  // Simulated unpriced remainder awaiting a source cancellation; never a level.
  int64_t pending_cancel_quantity;
};

struct PriceLevel {
  int64_t price;
  int64_t quantity;
};

struct AuctionCandidate {
  int64_t price;
  int64_t trade_quantity;
  int64_t remain_quantity_at_price;
  char side;
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
