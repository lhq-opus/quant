#include "order_book.hpp"

#include <algorithm>
#include <vector>
#include <iostream>

OrderBook::OrderBook() : cumulative_trade_quantity(0), cumulative_turnover(0) {}

void OrderBook::apply(Order &order)
{

    // finish auction
    if (trading_session == TradingSession::OpeningAution && order.trading_session == TradingSession::ContinuousTrade)
    {
        finish_call_auction();
    }

    handle_pending_market_order(order);

    handle_pending_CYB_limit_order(order);

    trading_session = order.trading_session;

    // order

    // auction
    if (order.trading_session == TradingSession::OpeningAution || order.trading_session == TradingSession::ClosingAuction)
    {
        apply_order_in_acution(order);
        return;
    }

    if (order.trading_session == TradingSession::ContinuousTrade)
    {
        // limit order
        if (order.order_type == OrderType::Limit)
        {
            apply_limit_order(order);
            make_snapshot(order);
            return;
        }
        // best
        if (order.order_type == OrderType::BBO)
        {
            apply_BBO_order(order);
            make_snapshot(order);
            return;
        }
        // market order
        if (order.order_type == OrderType::Market)
        {
            apply_market_order(order);
            make_snapshot(order);
            return;
        }
        return;
    }
}

void OrderBook::apply(Trade &trade)
{
    handle_pending_market_order(trade);

    handle_pending_CYB_limit_order(trade);

    trading_session = trade.trading_session;

    if (trade.trade_type == TradeType::Normal)
    {
        if (trade.trading_session == TradingSession::OpeningAution)
        {
            opening_price = trade.price;
        }

        trade_count += 1;
        last_trade_price = trade.price;

        if (pending_limit_order_alive.find(trade.bid_appl_seq_num) == pending_limit_order_alive.end() && pending_limit_order_alive.find(trade.offer_appl_seq_num) == pending_limit_order_alive.end())
        {

            update_previous_snapshot();
        }

        return;
    }

    // cancel trade
    if (trade.trade_type == TradeType::Cancel)
    {

        if (trade.is_CYB && pending_limit_order_alive.find(trade.offer_appl_seq_num) != pending_limit_order_alive.end())
        {
            pending_limit_order_alive.erase(trade.offer_appl_seq_num);
            make_snapshot(trade);
            return;
        }

        apply_cancel(trade);
        make_snapshot(trade);

        return;
    }
}

void OrderBook::apply_market_order(Order &order)
{

    pending_market_order_appl_seq = order.order_appl_seq_num;
    pending_market_order_quantity = order.quantity;

    order_info_map[order.order_appl_seq_num] = OrderInfo{price : DROP_SIGNAL, side : order.side};
}

void OrderBook::apply_BBO_order(Order &order)
{
    Order limit_order = order;
    if (order.side == EventSide::Buy)
    {
        limit_order.price = bids.begin()->first;
    }
    else
    {
        limit_order.price = asks.begin()->first;
    }
    apply_limit_order(limit_order);
}

void OrderBook::apply_order_in_acution(Order &order)
{
    if (order.side == EventSide::Buy)
    {
        BookLevel &level = bids[order.price];
        OrderQueue::iterator position = level.orders.insert(
            level.orders.end(), RestingOrder{order.order_appl_seq_num, order.quantity});
        level.total_quantity += order.quantity;
        order_info_map[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
    }
    else
    {
        BookLevel &level = asks[order.price];
        OrderQueue::iterator position = level.orders.insert(
            level.orders.end(), RestingOrder{order.order_appl_seq_num, order.quantity});
        level.total_quantity += order.quantity;
        order_info_map[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
    }
}

void OrderBook::apply_limit_order(Order &order)
{
    int64_t remaining_quantity = order.quantity;
    order_info_map[order.order_appl_seq_num] = OrderInfo{price : order.price, side : order.side};

    // limit order rules for CYB
    if (order.is_CYB && order.side == EventSide::Buy && !asks.empty())
    {
        AskLevels::iterator best_ask = asks.begin();
        int64_t best_ask_price = best_ask->first;

        if (order.price * 100 > best_ask_price * BID_COEFFICIENT)
        {
            pending_limit_order_alive[order.order_appl_seq_num] = order;
            return;
        }
    }

    if (order.is_CYB && order.side == EventSide::Sell && !bids.empty())
    {
        order_info_map[order.order_appl_seq_num] = OrderInfo{price : order.price, side : order.side};
        BidLevels::iterator best_bid = bids.begin();
        int64_t best_bid_price = best_bid->first;

        if (order.price * 100 < best_bid_price * ASK_COEFFICIENT)
        {
            pending_limit_order_alive[order.order_appl_seq_num] = order;
            return;
        }
    }

    if (order.side == EventSide::Buy)
    {
        while (remaining_quantity > 0 && !asks.empty())
        {
            AskLevels::iterator best_ask = asks.begin();
            if (best_ask->first > order.price)
            {
                break;
            }

            int64_t traded_quantity = std::min(remaining_quantity, best_ask->second.total_quantity);

            execute_order_at_price(best_ask->first, traded_quantity, false, true);
        }

        if (remaining_quantity > 0)
        {
            BookLevel &level = bids[order.price];
            OrderQueue::iterator position = level.orders.insert(
                level.orders.end(), RestingOrder{order.order_appl_seq_num, remaining_quantity});
            level.total_quantity += remaining_quantity;
            order_info_map[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
        }

        return;
    }

    while (remaining_quantity > 0 && !bids.empty())
    {

        BidLevels::iterator best_bid = bids.begin();
        if (best_bid->first < order.price)
        {
            break;
        }

        int64_t traded_quantity = std::min(remaining_quantity, best_bid->second.total_quantity);

        execute_order_at_price(best_bid->first, traded_quantity, true, false);
        remaining_quantity -= traded_quantity;
    }

    if (remaining_quantity > 0)
    {
        BookLevel &level = asks[order.price];
        OrderQueue::iterator position = level.orders.insert(
            level.orders.end(), RestingOrder{order.order_appl_seq_num, remaining_quantity});
        level.total_quantity += remaining_quantity;
        order_info_map[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
    }
}

void OrderBook::apply_cancel(Trade &trade)
{

    int64_t order_appl_seq_num = trade.bid_appl_seq_num != 0 ? trade.bid_appl_seq_num : trade.offer_appl_seq_num;

    std::map<int64_t, OrderInfo>::const_iterator order_info = order_info_map.find(order_appl_seq_num);
    if (order_info == order_info_map.end())
    {
        return;
    }
    int64_t price = order_info->second.price;
    EventSide side = order_info_map[order_appl_seq_num].side;

    // CYB rules
    if (pending_limit_order_alive.find(order_appl_seq_num) != pending_limit_order_alive.end())
    {
        pending_limit_order_alive.erase(order_appl_seq_num);
        return;
    }
    // end

    if (price == DROP_SIGNAL)
    {
        return;
    }

    if (side == EventSide::Buy)
    {
        BidLevels::iterator bid = bids.find(price);
        OrderQueue::iterator position = order_info->second.position;
        position->remaining_quantity -= trade.quantity;
        bid->second.total_quantity -= trade.quantity;
        if (position->remaining_quantity == 0)
        {
            bid->second.orders.erase(position);
            order_info_map.erase(order_info);
        }

        if (bid->second.total_quantity == 0)
        {
            bids.erase(bid);
        }

        return;
    }

    AskLevels::iterator ask = asks.find(price);
    OrderQueue::iterator position = order_info->second.position;
    position->remaining_quantity -= trade.quantity;
    ask->second.total_quantity -= trade.quantity;
    if (position->remaining_quantity == 0)
    {
        ask->second.orders.erase(position);
        order_info_map.erase(order_info);
    }

    if (ask->second.total_quantity == 0)
    {
        asks.erase(ask);
    }
}

void OrderBook::record_trade(int64_t price, int64_t quantity)
{
    cumulative_trade_quantity += quantity;
    cumulative_turnover += price * quantity;
}

void OrderBook::finish_call_auction()
{
    int64_t auction_price = opening_price;
    int64_t trade_quantity = cumulative_trade_quantity;

    execute_auction_trade(auction_price, trade_quantity);
}

void OrderBook::execute_auction_trade(int64_t price, int64_t quantity)
{
    int64_t remaining_quantity = quantity;
    while (remaining_quantity > 0)
    {
        int64_t traded_quantity = remaining_quantity;

        traded_quantity =
            std::min(traded_quantity, bids.begin()->second.orders.front().remaining_quantity);

        traded_quantity =
            std::min(traded_quantity, asks.begin()->second.orders.front().remaining_quantity);

        BidLevels::iterator bid = bids.begin();
        BookLevel &level = bid->second;
        RestingOrder &order = level.orders.front();
        order.remaining_quantity -= traded_quantity;
        level.total_quantity -= traded_quantity;
        if (order.remaining_quantity == 0)
        {
            order_info_map.erase(order.order_appl_seq_num);
            level.orders.pop_front();
        }
        if (level.orders.empty())
        {
            bids.erase(bid);
        }

        AskLevels::iterator ask = asks.begin();
        BookLevel &level = ask->second;
        RestingOrder &order = level.orders.front();
        order.remaining_quantity -= traded_quantity;
        level.total_quantity -= traded_quantity;
        if (order.remaining_quantity == 0)
        {
            order_info_map.erase(order.order_appl_seq_num);
            level.orders.pop_front();
        }
        if (level.orders.empty())
        {
            asks.erase(ask);
        }

        cumulative_trade_quantity += traded_quantity;
        cumulative_turnover += price * traded_quantity;
        remaining_quantity -= traded_quantity;
    }
}

void OrderBook::execute_order_at_price(int64_t price, int64_t quantity, bool reduce_bids, bool reduce_asks)
{
    int64_t remaining_quantity = quantity;
    while (remaining_quantity > 0)
    {
        int64_t traded_quantity = remaining_quantity;
        if (reduce_bids)
        {
            traded_quantity =
                std::min(traded_quantity, bids.begin()->second.orders.front().remaining_quantity);
        }
        if (reduce_asks)
        {
            traded_quantity =
                std::min(traded_quantity, asks.begin()->second.orders.front().remaining_quantity);
        }

        if (reduce_bids)
        {
            BidLevels::iterator bid = bids.begin();
            BookLevel &level = bid->second;
            RestingOrder &order = level.orders.front();
            order.remaining_quantity -= traded_quantity;
            level.total_quantity -= traded_quantity;
            if (order.remaining_quantity == 0)
            {
                order_info_map.erase(order.order_appl_seq_num);
                level.orders.pop_front();
            }
            if (level.orders.empty())
            {
                bids.erase(bid);
            }
        }

        if (reduce_asks)
        {
            AskLevels::iterator ask = asks.begin();
            BookLevel &level = ask->second;
            RestingOrder &order = level.orders.front();
            order.remaining_quantity -= traded_quantity;
            level.total_quantity -= traded_quantity;
            if (order.remaining_quantity == 0)
            {
                order_info_map.erase(order.order_appl_seq_num);
                level.orders.pop_front();
            }
            if (level.orders.empty())
            {
                asks.erase(ask);
            }
        }

        ++trade_count;
        last_trade_price = price;
        cumulative_trade_quantity += traded_quantity;
        cumulative_turnover += price * traded_quantity;
        remaining_quantity -= traded_quantity;
    }
}

void OrderBook::finish()
{
    update_previous_snapshot();
}