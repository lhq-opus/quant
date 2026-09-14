#include "order_book.hpp"

// 从全深度盘口投影五档：买价由高到低，卖价由低到高，每档数量取缓存
// 的订单总余量。先清空旧投影再补零，允许同一个 Pending 快照反复更新。
void OrderBook::fill_snapshot_levels(Snapshot& snapshot) const {
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

// 所有统计字段一起复制，避免快照的成交笔数、量额和成交价来自不同进度。
// 开盘价由竞价真实成交建立；投影函数本身不修改订单簿和累计统计。
void OrderBook::fill_snapshot_statistics(Snapshot& snapshot) const {
  snapshot.trade_count = trade_count;
  snapshot.last_price = last_trade_price;
  snapshot.cumulative_trade_quantity = cumulative_trade_quantity;
  snapshot.cumulative_turnover = cumulative_turnover;
  snapshot.opening_price = opening_price;
}

// 委托的元信息属于触发事件，后续相关成交只更新五档和统计，不替换这些
// 字段。Pending 状态保证关联成交处理结束之前，流式输出不能提前取走。
void OrderBook::make_snapshot(const Order& order) {
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
  fill_snapshot_levels(snapshot);
  fill_snapshot_statistics(snapshot);
  snapshots.push_back(snapshot);
}

// 撤单快照使用撤单自己的元信息；是否需要输出仍由事件的开关和时段决定。
// 普通成交通常不创建新行，而是确认并更新前一个委托或撤单快照。
void OrderBook::make_snapshot(const Trade& trade) {
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
  fill_snapshot_levels(snapshot);
  fill_snapshot_statistics(snapshot);
  snapshots.push_back(snapshot);
}

// 仅最后一个尚未确认的快照可以改变。Ready 快照可能已写入文件，必须
// 保持不可变；Deleted 快照也不能被后续事件重新激活或改成其他事件的行。
void OrderBook::update_previous_snapshot() {
  if (snapshots.empty() || snapshots.back().status != SnapshotStatus::Pending) {
    return;
  }
  fill_snapshot_levels(snapshots.back());
  fill_snapshot_statistics(snapshots.back());
}

// 事件组结束时先取最终盘口和统计，再标记为可输出或删除；不会修改
// 触发快照的原始元信息，也不会重复完成已经确认过的快照。
void OrderBook::complete_previous_snapshot(SnapshotStatus status) {
  if (snapshots.empty() || snapshots.back().status != SnapshotStatus::Pending) {
    return;
  }
  update_previous_snapshot();
  snapshots.back().status = status;
}

// 每次只交付一个已确认快照，并从内存移除。Deleted 行直接跳过，队首
// Pending 行则等待后续成交确认，不能越过它输出后面的事件。
bool OrderBook::pop_snapshot(Snapshot& snapshot) {
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
