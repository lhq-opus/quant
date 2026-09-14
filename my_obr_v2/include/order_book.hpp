#pragma once

#include "model.hpp"

#include <deque>
#include <functional>
#include <map>
#include <set>
#include <utility>

// 单证券、单交易日、单通道的 v2 重放实例。输入和引用合法，数值运算可表示。
// 活动订单索引中的迭代器属于本实例，不允许复制订单簿。
class OrderBook {
public:
  OrderBook();
  OrderBook(const OrderBook&) = delete;
  OrderBook& operator=(const OrderBook&) = delete;

  void apply(Order& order);
  void apply(Trade& trade);
  // 每次 apply 后持续取出 Ready 快照；Pending 等相关成交，Deleted 直接丢弃。
  bool pop_snapshot(Snapshot& snapshot);
  void finish();
  void fill_snapshot_levels(Snapshot& snapshot) const;
  void get_market_trade_sides(const Trade& trade, bool& is_bid, bool& is_ask) const;

private:
  struct OrderInfo {
    int64_t price;
    EventSide side;
    OrderQueue::iterator position;
  };
  typedef std::map<int64_t, BookLevel, std::greater<int64_t>> BidLevels;
  typedef std::map<int64_t, BookLevel> AskLevels;

  void add_resting_order(const Order& order);
  void apply_order_in_acution(Order& order);
  void apply_BBO_order(Order& order);
  void apply_limit_order(Order& order);
  void apply_market_order(Order& order);
  void apply_cancel(const Trade& trade);
  // 已知原单时直接用 position 扣量；未展示的市价/创业板委托只扣独立余量。
  void consume_order(int64_t order_appl_seq_num, int64_t quantity);
  void execute_trade(const Trade& trade);
  // 限价推演仅修改对手盘口，实际 F 负责所有成交统计。
  void execute_order_at_price(int64_t quantity, bool reduce_bids, bool reduce_asks);
  void record_trade(const Trade& trade);

  void finish_pending_market_order(bool canceled = false);
  bool is_pending_market_trade(const Trade& trade) const;
  bool is_outside_cyb_range(const Order& order) const;
  void activate_cyb_orders();

  void make_snapshot(const Order& order);
  void make_snapshot(const Trade& trade);
  void fill_snapshot_statistics(Snapshot& snapshot) const;
  void update_previous_snapshot();
  void complete_previous_snapshot(SnapshotStatus status = SnapshotStatus::Ready);
  void finish_event_group();

  TradingSession trading_session;
  BidLevels bids;
  AskLevels asks;
  std::map<int64_t, OrderInfo> order_info_map;
  // 原始到达次序用于暂存订单恢复入簿后的同价 FIFO；订单耗尽时清理。
  std::map<int64_t, int64_t> order_arrival_rank;
  int64_t next_arrival_rank;
  std::set<std::pair<int64_t, int64_t>> market_order_ids;

  int64_t cumulative_trade_quantity;
  int64_t cumulative_turnover;
  int64_t trade_count;
  int64_t last_trade_price;
  int64_t opening_price;
  std::deque<Snapshot> snapshots;

  // 当前限价推演的成交量，只用于等待真实 F 确认，不充当累计成交统计。
  int64_t pending_limit_order_appl_seq;
  int64_t pending_limit_trade_quantity;
  // 暂存单可能被盘口变化激活；该事件组按真实引用执行，等组末确定快照。
  bool pending_cyb_event_group;

  // 市价来单先不展示，关联 F 到达即扣量；组末按最后成交价处理余量。
  Order pending_market_order;
  int64_t pending_market_order_appl_seq;
  int64_t pending_market_order_quantity;
  int64_t pending_market_last_price;

  // 笼子外限价暂存在这里，不伪造订单链表迭代器。
  std::map<int64_t, Order> pending_limit_order_alive;
};
