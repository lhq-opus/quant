#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <list>



enum class TradeType{
    Cancel,
    Normal,
};

enum class TradingSession{
    OpeningAution,
    ContinuousTrade,
    ClosingAuction,
};

enum class SnapshotStatus{
    Pending,
    Ready,
    Deleted,
};

enum class EventSide{
    Buy,
    Sell,
};

enum class OrderType{
    Market,
    Limit,
    BBO,
};

struct RestingOrder {
  int64_t order_appl_seq_num;
  int64_t remaining_quantity;
};

typedef std::list<RestingOrder> OrderQueue;
struct BookLevel {
  BookLevel() : total_quantity(0) {}

  int64_t total_quantity;
  OrderQueue orders;
};

struct Order {
  std::string caa;
  std::string transaction_time;
  std::string security_id;
  std::string apply_seq_no;
  int64_t sequence_no;
  int64_t channel_no;
  EventSide side;
  OrderType order_type;
  int64_t price;
  int64_t quantity;
  int64_t order_appl_seq_num;
  bool generate_snapshot;
  TradingSession trading_session;
  bool is_CYB;
};

struct Trade {
  std::string caa;
  std::string transaction_time;
  std::string security_id;
  std::string apply_seq_no;
  int64_t sequence_no;
  int64_t channel_no;
  TradeType trade_type;
  int64_t price;
  int64_t quantity;
  int64_t trade_appl_seq_num;
  int64_t bid_appl_seq_num;
  int64_t offer_appl_seq_num;
  bool generate_snapshot;
  TradingSession trading_session;
  bool is_CYB;
};

struct Event {
  std::string caa;
  std::string transaction_time;
  std::string security_id;
  std::string apply_seq_no;
  int64_t sequence_no;
  TradeType type;
  EventSide side;
  OrderType order_type;
  int64_t price;
  int64_t quantity;
  int64_t channel_no;
  int64_t order_appl_seq_num;
  int64_t bid_appl_seq_num;  
  int64_t offer_appl_seq_num;
  TradingSession trading_session;
  bool need_handle;
  bool generate_snapshot;
  bool is_CYB;
};


struct PriceLevel {
    std::int64_t price;
    std::int64_t quantity;
};

struct Snapshot{
    std::string caa;
    TradingSession trading_session;
    std::vector<PriceLevel> bids;
    std::vector<PriceLevel> asks;
    int64_t trade_count;
    int64_t last_price;
    int64_t cumulative_trade_quantity;
    int64_t cumulative_turnover;
    std::string transaction_time;
    std::string security_id;
    std::string apply_seq_no;
    int64_t sequence_no;
    int64_t opening_price;
    SnapshotStatus status;
};

struct AuctionCandidate{
    std::int64_t price;
    std::int64_t trade_quantity;
    std::int64_t remain_quantity_at_price;
};