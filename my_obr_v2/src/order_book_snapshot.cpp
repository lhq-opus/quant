#include "order_book.hpp"

#include <algorithm>
#include <vector>
#include <iostream>

void OrderBook::fill_snapshot_levels(Snapshot& snapshot) {
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


void OrderBook::fill_snapshot_statistics(Snapshot& snapshot)  {
  snapshot.trade_count = trade_count;
  snapshot.last_price = last_trade_price;
  snapshot.cumulative_trade_quantity = cumulative_trade_quantity;
  snapshot.cumulative_turnover = cumulative_turnover;
  snapshot.opening_price = opening_price;
}

void OrderBook::make_snapshot(Order& order) {
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
  fill_snapshot_levels(snapshot);
  fill_snapshot_statistics(snapshot);
  snapshots.push_back(snapshot);
}


void OrderBook::update_previous_snapshot() {
  if (snapshots.empty() || snapshots.back().status != SnapshotStatus::Pending) {
    return;
  }
  fill_snapshot_levels(snapshots.back());
  fill_snapshot_statistics(snapshots.back());
}



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
