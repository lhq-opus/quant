#ifndef MY_OBR_MODEL_HPP
#define MY_OBR_MODEL_HPP

#include <list>
#include <stdint.h>
#include <string>
#include <vector>

// Snapshot/output source labels; input records use separate Order and Trade types.
enum class EventType { Order, Trade, Cancel };

// Keep the existing source spellings until a separate naming change is requested.
enum class TradingSession { OpeningAution, ContinuousTrade, ClosingAuction };

enum class TradeType { Normal, Cancel };

// These are the implementation's inferred categories, not raw exchange codes.
enum class MarketOrderType { TradeAtBest, CancelAfterFiveLevel, TradeWithSlippage };

// Value-initialize parsed records with {}. Side and order_type retain raw codes.
struct Order {
  std::string caa;
  std::string transaction_time;
  int64_t sequence_no;
  int64_t channel_no;
  TradingSession trading_session;
  char side;
  char order_type;
  int64_t price;
  int64_t quantity;
  int64_t order_appl_seq_num;
  bool generate_snapshot;
};

// A trade.csv record is either a normal execution or a cancellation.
// Its own sequence identifies this record; bid/offer sequences reference orders.
struct Trade {
  std::string caa;
  std::string transaction_time;
  int64_t sequence_no;
  int64_t channel_no;
  TradingSession trading_session;
  TradeType trade_type;
  int64_t price;
  int64_t quantity;
  int64_t trade_appl_seq_num;
  int64_t bid_appl_seq_num;
  int64_t offer_appl_seq_num;
  bool generate_snapshot;
};

struct TradeInfo {
  TradeType trade_type;
  int64_t price;
  int64_t quantity;
};

struct RestingOrder {
  int64_t order_appl_seq_num;
  int64_t remaining_quantity;
};

typedef std::list<RestingOrder> OrderQueue;

// Orders enter at the back and match at the front; the cached total feeds snapshots.
struct BookLevel {
  BookLevel() : total_quantity(0) {}

  int64_t total_quantity;
  OrderQueue orders;
};

// position belongs to the queue at price. A price of -1 has no queued order.
struct OrderInfo {
  int64_t price;
  char side;
  OrderQueue::iterator position;
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
  // Simulated order-pair statistics, available immediately after apply().
  int64_t trade_number;
  int64_t last_price;
  int64_t opening_price;
  int64_t cumulative_trade_quantity;
  int64_t cumulative_turnover;
  EventType event_type;
  TradingSession trading_session;
  std::vector<PriceLevel> bids;
  std::vector<PriceLevel> asks;
};

#endif
