#ifndef MY_OBR_MODEL_HPP
#define MY_OBR_MODEL_HPP

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
  int64_t sequence_no;
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
  EventType event_type;
  TradingSession trading_session;
  std::vector<PriceLevel> bids;
  std::vector<PriceLevel> asks;
};

#endif
