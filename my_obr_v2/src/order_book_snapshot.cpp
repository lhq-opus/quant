#include "order_book.hpp"

#include <vector>

void OrderBook::fill_snapshot_levels(Snapshot& snapshot) {
  // 每次重新投影全部五档，保证旧快照复用后不会残留已经删除的价格或数量。
  // 内部统一按最优到第五档存储，导出时再转换为 v2 的列顺序。
  snapshot.bids.clear();
  snapshot.asks.clear();

  for (BidLevels::const_iterator bid = bids.begin(); bid != bids.end() && snapshot.bids.size() < 5;
       ++bid) {
    const PriceLevel level = {bid->first, bid->second.total_quantity};
    snapshot.bids.push_back(level);
  }
  while (snapshot.bids.size() < 5) {
    const PriceLevel level = {0, 0};
    snapshot.bids.push_back(level);
  }

  for (AskLevels::const_iterator ask = asks.begin(); ask != asks.end() && snapshot.asks.size() < 5;
       ++ask) {
    const PriceLevel level = {ask->first, ask->second.total_quantity};
    snapshot.asks.push_back(level);
  }
  while (snapshot.asks.size() < 5) {
    const PriceLevel level = {0, 0};
    snapshot.asks.push_back(level);
  }
}

void OrderBook::fill_snapshot_statistics(Snapshot& snapshot) {
  // 统计值只来自真实 F；限价撮合推演和市价/CYB 回放不会再次累计。
  snapshot.trade_count = trade_count;
  snapshot.last_price = last_trade_price;
  snapshot.cumulative_trade_quantity = cumulative_trade_quantity;
  snapshot.cumulative_turnover = cumulative_turnover;
  snapshot.opening_price = opening_price;
}

void OrderBook::make_snapshot(Order& order) {
  // 继续沿用 v2 的输出范围：只有连续竞价且要求输出的事件创建快照。
  if (!order.generate_snapshot || order.trading_session != TradingSession::ContinuousTrade) {
    return;
  }

  Snapshot snapshot = {};
  snapshot.caa = order.caa;
  snapshot.trading_session = order.trading_session;
  snapshot.security_id = order.security_id;
  snapshot.sequence_no = order.sequence_no;
  snapshot.apply_seq_no = order.apply_seq_no;
  snapshot.transaction_time = order.transaction_time;
  snapshot.status = SnapshotStatus::Pending;
  snapshots.push_back(snapshot);
  // 无待确认成交时可立即输出；否则保留委托原始元信息，等待真实 F 补齐状态。
  update_previous_snapshot();
}

void OrderBook::make_snapshot(Trade& trade) {
  if (!trade.generate_snapshot || trade.trading_session != TradingSession::ContinuousTrade) {
    return;
  }

  Snapshot snapshot = {};
  snapshot.caa = trade.caa;
  snapshot.trading_session = trade.trading_session;
  snapshot.security_id = trade.security_id;
  snapshot.sequence_no = trade.sequence_no;
  snapshot.apply_seq_no = trade.apply_seq_no;
  snapshot.transaction_time = trade.transaction_time;
  snapshot.status = SnapshotStatus::Pending;
  snapshots.push_back(snapshot);
  // 撤单生成自己的快照，成交本身仍由外层更新对应委托的待确认快照。
  update_previous_snapshot();
}

void OrderBook::update_previous_snapshot() {
  if (snapshots.empty() || snapshots.back().status != SnapshotStatus::Pending) {
    return;
  }

  fill_snapshot_levels(snapshots.back());
  fill_snapshot_statistics(snapshots.back());

  // 三类未完成状态全部结束后才释放快照：市价回放、限价推演的真实成交
  // 确认，以及创业板暂存单相关成交组。Ready 后不再被后续事件覆盖。
  if (pending_market_order_appl_seq == 0 && pending_limit_trade_quantity == 0 &&
      !pending_cyb_group) {
    snapshots.back().status = SnapshotStatus::Ready;
  }
}

bool OrderBook::pop_snapshot(Snapshot& snapshot) {
  // 删除行直接跳过；Pending 行阻止后续行越过它，保持事件输出顺序。
  while (!snapshots.empty() && snapshots.front().status == SnapshotStatus::Deleted) {
    snapshots.pop_front();
  }
  if (snapshots.empty() || snapshots.front().status != SnapshotStatus::Ready) {
    return false;
  }
  snapshot = snapshots.front();
  snapshots.pop_front();
  return true;
}

std::vector<Snapshot> OrderBook::get_snapshots() {
  // 保留原有查询接口；返回当前缓存的副本，不改变流式输出队列和快照状态。
  return std::vector<Snapshot>(snapshots.begin(), snapshots.end());
}
