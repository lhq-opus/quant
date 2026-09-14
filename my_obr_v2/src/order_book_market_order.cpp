#include "order_book.hpp"

#include <algorithm>
#include <vector>
#include <iostream>

void OrderBook::handle_pending_market_order(Order &order)
{
    if (pending_market_order_appl_seq == 0)
    {
        return;
    }

    replay_pending_market_order(pending_market_order_trades);

    pending_market_order_appl_seq = 0;
    pending_market_order_quantity = 0;
    pending_market_order_trades.clear();
}

void OrderBook::handle_pending_market_order(Trade &trade)
{
    if (pending_market_order_appl_seq == 0)
    {
        return;
    }

    const bool is_pending_event = trade.bid_appl_seq_num == pending_market_order_appl_seq || trade.offer_appl_seq_num == pending_market_order_appl_seq;

    if (trade.trade_type == TradeType::Normal)
    {
        if (is_pending_event)
        {
            pending_market_order_trades.push_back(trade);
        }
        return;
    }

    if (trade.trade_type == TradeType::Cancel && is_pending_event)
    {
        pending_market_order_trades.push_back(trade);
    }

    replay_pending_market_order(pending_market_order_trades);

    pending_market_order_appl_seq = 0;
    pending_market_order_quantity = 0;
    pending_market_order_trades.clear();
}

void OrderBook::replay_pending_market_order(std::vector<Trade> trades)
{

    int64_t remaining_quantity = pending_market_order_quantity;
    int64_t trade_price = 0;
    int64_t trade_quantity = 0;
    bool has_cancel = false;

    OrderInfo order = order_info_map[pending_market_order_appl_seq];
    EventSide side = order.side;

    for (std::size_t index = 0; index < trades.size(); ++index)
    {
        Trade trade = trades[index];
        trade_price = trade.price;
        trade_quantity = trade.quantity;
        remaining_quantity -= trade_quantity;

        if (trade.trade_type == TradeType::Cancel)
        {
            has_cancel = true;
            break;
        }

        record_trade(trade_price, trade_quantity);

        if (side == EventSide::Buy)
        {
            int64_t ask_order_seq_num = trade.offer_appl_seq_num;
            std::map<int64_t, OrderInfo>::const_iterator ask_info = order_info_map.find(ask_order_seq_num);
            AskLevels::iterator ask = asks.find(ask_info->second.price);

            OrderQueue::iterator position = ask_info->second.position;
            position->remaining_quantity -= trade.quantity;
            ask->second.total_quantity -= trade.quantity;

            if (position->remaining_quantity == 0)
            {
                ask->second.orders.erase(position);
            }

            if (ask->second.total_quantity == 0)
            {
                asks.erase(ask);
            }
        }
        else
        {

            int64_t bid_order_seq_num = trade.bid_appl_seq_num;
            std::map<int64_t, OrderInfo>::const_iterator bid_info = order_info_map.find(bid_order_seq_num);
            BidLevels::iterator bid = bids.find(bid_info->second.price);

            OrderQueue::iterator position = bid_info->second.position;
            position->remaining_quantity -= trade.quantity;
            bid->second.total_quantity -= trade.quantity;

            if (position->remaining_quantity == 0)
            {
                bid->second.orders.erase(position);
            }

            if (bid->second.total_quantity == 0)
            {
                asks.erase(bid);
            }
        }
    }

    if (remaining_quantity != 0 && trade_price != 0)
    {
        int64_t order_appl_seq = pending_market_order_appl_seq;
        if (side == EventSide::Buy)
        {
            BookLevel &level = bids[order.price];
            OrderQueue::iterator position = level.orders.insert(
                level.orders.end(), RestingOrder{order_appl_seq, remaining_quantity});
            level.total_quantity += remaining_quantity;
            order_info_map[pending_market_order_appl_seq] = OrderInfo{price : trade_price, side : EventSide::Buy, position};
        }
        else
        {
            BookLevel &level = asks[order.price];
            OrderQueue::iterator position = level.orders.insert(
                level.orders.end(), RestingOrder{order_appl_seq, remaining_quantity});
            level.total_quantity += remaining_quantity;
            order_info_map[pending_market_order_appl_seq] = OrderInfo{price : trade_price, side : EventSide::Sell, position};
        }
    }

    if (has_cancel || remaining_quantity > 0)
    {
        snapshots[snapshots.size() - 1].status = SnapshotStatus::Deleted;
    }
    else
    {

        update_previous_snapshot();
    }
}
