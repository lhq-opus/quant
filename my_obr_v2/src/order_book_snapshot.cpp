#include "order_book.hpp"

#include <algorithm>
#include <vector>
#include <iostream>

void OrderBook::make_snapshot(Order &order){}

void OrderBook::make_snapshot(Trade &trade){}

void OrderBook::make_snapshot(Event &event)
{

    if (!event.generate_snapshot)
    {
        return;
    }

    Snapshot snapshot{};

    snapshot.caa = event.caa;
    snapshot.event_type = event.type;

    BidLevels::iterator bid = bids.begin();

    for (; bid != bids.end() && snapshot.bids.size() < 5; ++bid)
    {
        PriceLevel level = {bid->first, bid->second};

        snapshot.bids.push_back(level);
    }

    while (snapshot.bids.size() < 5)
    {
        PriceLevel level = {0, 0};
        snapshot.bids.push_back(level);
    }

    AskLevels::iterator ask = asks.begin();
    for (; ask != asks.end() && snapshot.asks.size() < 5; ++ask)
    {
        PriceLevel level = {ask->first, ask->second};
        snapshot.asks.push_back(level);
    }

    while (snapshot.asks.size() < 5)
    {
        PriceLevel level = {0, 0};
        snapshot.asks.push_back(level);
    }

    snapshot.trading_session = event.trading_session;
    snapshot.trade_count = trade_count;
    snapshot.last_price = last_trade_price;
    snapshot.cumulative_trade_quantity = cumulative_trade_quantity;
    snapshot.cumulative_turnover = cumulative_turnover;
    snapshot.security_id = event.security_id;
    snapshot.sequence_no = event.sequence_no;
    snapshot.apply_seq_no = event.apply_seq_no;
    snapshot.transaction_time = event.transaction_time;
    snapshot.opening_price = opening_price;

    snapshot.status = SnapshotStatus::Pending;

    snapshots.push_back(snapshot);

    return;
}

void OrderBook::update_previous_snapshot()
{
    if (snapshots.size() == 0)
    {
        return;
    }

    snapshots[snapshots.size() - 1].last_price = last_trade_price;
    snapshots[snapshots.size() - 1].trade_count = trade_count;

    snapshots[snapshots.size() - 1].bids.clear();
    snapshots[snapshots.size() - 1].asks.clear();

    BidLevels::iterator bid = bids.begin();

    for (; bid != bids.end() && snapshots[snapshots.size() - 1].bids.size() < 5; ++bid)
    {
        PriceLevel level = {bid->first, bid->second};

        snapshots[snapshots.size() - 1].bids.push_back(level);
    }

    while (snapshots[snapshots.size() - 1].bids.size() < 5)
    {
        PriceLevel level = {0, 0};
        snapshots[snapshots.size() - 1].bids.push_back(level);
    }

    AskLevels::iterator ask = asks.begin();
    for (; ask != asks.end() && snapshots[snapshots.size() - 1].asks.size() < 5; ++ask)
    {
        PriceLevel level = {ask->first, ask->second};
        snapshots[snapshots.size() - 1].asks.push_back(level);
    }

    while (snapshots[snapshots.size() - 1].asks.size() < 5)
    {
        PriceLevel level = {0, 0};
        snapshots[snapshots.size() - 1].asks.push_back(level);
    }

    snapshots[snapshots.size() - 1].cumulative_trade_quantity = cumulative_trade_quantity;
    snapshots[snapshots.size() - 1].cumulative_turnover = cumulative_turnover;
}

std::vector<Snapshot> OrderBook::get_snapshots()
{
    return snapshots;
}