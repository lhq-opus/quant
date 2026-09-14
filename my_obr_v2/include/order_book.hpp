#pragma once
#include "model.hpp"
#include <deque>
#include <map>
#include <queue>

class OrderBook {
public:
  OrderBook();
  // position 属于本实例的链表；禁止原有隐式复制，防止副本仍指向原簿节点。
  OrderBook(const OrderBook&) = delete;
  OrderBook& operator=(const OrderBook&) = delete;

  void build_trade_map(Event& event);

  void apply(Order& order);
  void apply(Trade& trade);
  bool pop_snapshot(Snapshot& snapshot);

  std::vector<Snapshot> get_snapshots();

  void finish();

private:
  const int64_t BID_COEFFICIENT = 102;
  const int64_t ASK_COEFFICIENT = 98;
  const int64_t DROP_SIGNAL = -1;

  struct OrderInfo {
    int64_t price;
    EventSide side;
    // 暂存/市价等待态使用默认迭代器，必须先分流；仅已入簿订单可解引用。
    OrderQueue::iterator position;
    // 无成交价的市价余量，以及本方为空的 U 单待撤数量；两者都不在可见链表中。
    int64_t unpriced_quantity;
  };

  typedef std::map<int64_t, BookLevel, std::greater<int64_t>> BidLevels;
  typedef std::map<int64_t, BookLevel> AskLevels;

  void finish_call_auction();
  void apply_order_in_acution(Order& order);
  void apply_BBO_order(Order& order);
  void apply_limit_order(Order& order);
  void apply_market_order(Order& order);
  void apply_cancel(Trade& trade);
  void record_trade(int64_t price, int64_t quantity);
  void execute_order_at_price(int64_t price, int64_t quantity, bool reduce_bids, bool reduce_asks);
  void execute_trade(Trade& trade);
  void execute_auction_trade(int64_t price, int64_t quantity);

  void handle_pending_market_order(Order& order);
  void handle_pending_market_order(Trade& trade);
  void replay_pending_market_order(std::vector<Trade> trades);

  void make_snapshot(Order& order);
  void make_snapshot(Trade& trade);
  void update_previous_snapshot();
  void fill_snapshot_levels(Snapshot& snapshot);
  void fill_snapshot_statistics(Snapshot& snapshot);

  void handle_pending_CYB_limit_order(Order& order);
  void handle_pending_CYB_limit_order(Trade& trade);
  void replay_CYB_trades(std::vector<Trade> trades);

  TradingSession trading_session;

  BidLevels bids;
  AskLevels asks;

  // 原单序号对应其价格、方向和位置；未展示状态先分流，不直接使用 position。
  std::map<int64_t, OrderInfo> order_info_map;
  // 暂存单恢复入簿仍保留原始到达次序，同价队列不能按恢复时刻重新排队。
  std::map<int64_t, int64_t> order_arrival_rank;
  int64_t next_arrival_rank = 0;

  // 仅由真实 F 累计的全日成交统计。

  int64_t cumulative_trade_quantity = 0;
  int64_t cumulative_turnover = 0;
  int64_t trade_count = 0;
  int64_t last_trade_price = 0;
  int64_t opening_price = 0;

  std::deque<Snapshot> snapshots;
  // 普通限价只提前扣盘口，相关真实 F 确认完这一份量后才允许输出快照。
  int64_t pending_limit_order_appl_seq = 0;
  int64_t pending_limit_trade_quantity = 0;
  // 有暂存单参与的组统一按真实引用回放，避免与限价推演争用同一份对手量。
  bool pending_cyb_group = false;
  // 每段竞价的成交量独立于全日累计量；结算只扣盘，不重复统计真实 F。
  int64_t auction_trade_quantity = 0;
  int64_t auction_trade_price = 0;

  // 当前市价单及其待回放成交，沿用原有 vector 缓存结构。

  int64_t pending_market_order_appl_seq = 0;
  int64_t pending_market_order_quantity = 0;
  std::vector<Trade> pending_market_order_trades;
  // 已缓存的成交量用于判断市价是否全成；待回放余量在 execute_trade 时才扣。
  int64_t pending_market_trade_quantity = 0;
  int64_t pending_market_last_price = 0;
  bool pending_market_has_cancel = false;
  // 当前市价委托是否请求了快照；没有生成该行时不删除其他事件的快照。
  bool pending_market_has_snapshot = false;

  // 创业板当前事件组的真实 F；外层保证每条成交只进入一份缓存。

  std::vector<Trade> pending_CYB_trades;

  struct BidCompare {
    bool operator()(const Event& a, const Event& b) const {
      if (a.price == b.price) {
        return a.caa > b.caa;
      }
      return a.price > b.price; // 小顶
    }
  };

  struct AskCompare {
    bool operator()(const Event& a, const Event& b) const {
      if (a.price == b.price) {
        return a.caa > b.caa;
      }

      return a.price < b.price;
    }
  };

  std::priority_queue<Event, std::vector<Event>, BidCompare> pending_bid_limit_order;

  std::priority_queue<Event, std::vector<Event>, AskCompare> pending_ask_limit_order;

  // 原单序号对应暂存委托，quantity 保存尚未成交/撤销的余量。
  std::map<int64_t, Order> pending_limit_order_alive;
};
