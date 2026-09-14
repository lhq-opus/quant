#include "order_book.hpp"

#include <algorithm>
#include <vector>
#include <iostream>

void OrderBook::handle_pending_CYB_limit_order(Order &order)
{
    if (!order.is_CYB)
    {
        return;
    }

    replay_CYB_trades(pending_CYB_trades);

    pending_CYB_trades.clear();
}

void OrderBook::handle_pending_CYB_limit_order(Trade &trade)
{
    if (!trade.is_CYB)
    {
        return;
    }

    if (trade.trade_type == TradeType::Normal)
    {

        if (pending_limit_order_alive.find(trade.bid_appl_seq_num) != pending_limit_order_alive.end())
        {
            pending_CYB_trades.push_back(trade);
        }

        if (pending_limit_order_alive.find(trade.offer_appl_seq_num) != pending_limit_order_alive.end())
        {
            pending_CYB_trades.push_back(trade);
        }

        return;
    }

    bool replay_caused_by_cancel = false;

    if (trade.trade_type == TradeType::Cancel && pending_CYB_trades.size() != 0)
    {
        Trade trade = pending_CYB_trades[0];

        int64_t bid_price = order_info_map[trade.bid_appl_seq_num].price;
        int64_t ask_price = order_info_map[trade.offer_appl_seq_num].price;

        int64_t best_bids = bids.begin()->first;
        int64_t best_asks = asks.begin()->first;

        if (pending_limit_order_alive.find(trade.bid_appl_seq_num) != pending_limit_order_alive.end())
        {

            replay_caused_by_cancel = best_asks != ask_price;
        }

        if (pending_limit_order_alive.find(trade.offer_appl_seq_num) != pending_limit_order_alive.end())
        {
            replay_caused_by_cancel = best_bids != bid_price;
        }
    }

    replay_CYB_trades(pending_CYB_trades);

    if (!replay_caused_by_cancel)
    {
        update_previous_snapshot();
    }

    pending_CYB_trades.clear();
}

void OrderBook::replay_CYB_trades(std::vector<Trade> trades)
{

    for (int64_t i = 0; i < trades.size(); i++)
    {

        Trade trade = trades[i];

        int64_t quantity = trade.quantity;

        if (order_info_map.find(trade.bid_appl_seq_num) == order_info_map.end() || order_info_map.find(trade.offer_appl_seq_num) == order_info_map.end())
        {
            return;
        }

        int64_t bid_price = order_info_map[trade.bid_appl_seq_num].price;
        int64_t ask_price = order_info_map[trade.offer_appl_seq_num].price;

        if (bid_price == DROP_SIGNAL || ask_price == DROP_SIGNAL)
        {
            return;
        }

        if (pending_limit_order_alive.find(trade.bid_appl_seq_num) != pending_limit_order_alive.end())
        {
            // bid: pendind; ask normal
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
            // bid: normal; ask pending
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
        record_trade(trade.price, trade.quantity);
    }
}