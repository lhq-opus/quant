#pragma once

#include <cstdint>
#include <list>
#include <string>
#include <vector>

// 输入保证合法，解析层把原始代码转换为以下内部枚举。
enum class TradeType { Cancel, Normal };
enum class TradingSession { OpeningAution, ContinuousTrade, ClosingAuction };
enum class SnapshotStatus { Pending, Ready, Deleted };
enum class EventSide { Buy, Sell };
enum class OrderType { Market, Limit, BBO };

struct RestingOrder {
  int64_t order_appl_seq_num;
  int64_t remaining_quantity;
};

typedef std::list<RestingOrder> OrderQueue;

// 每档缓存总量，orders 按原始到达次序保存活动订单。
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
  TradingSession trading_session;
  EventSide side;
  OrderType order_type;
  int64_t price;
  int64_t quantity;
  int64_t order_appl_seq_num;
  bool generate_snapshot;
  bool is_CYB;
};

struct Trade {
  std::string caa;
  std::string transaction_time;
  std::string security_id;
  std::string apply_seq_no;
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
  bool is_CYB;
};

struct PriceLevel {
  int64_t price;
  int64_t quantity;
};

// 元信息取触发订单/撤单，价量与统计取该事件相关成交处理完成时的状态。
// 两侧各固定五档，缺失价量为零；只向外输出 Ready 状态。
struct Snapshot {
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
