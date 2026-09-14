#pragma once
#include "model.hpp"
#include <map>
#include <queue>

class OrderBook
{
public:
    OrderBook();

    void build_trade_map(Event &event);

    void apply(Order &order);
    void apply(Trade &trade);
    bool pop_snapshot(Snapshot& snapshot);

    std::vector<Snapshot> get_snapshots();

    void finish();

private:
    const int64_t BID_COEFFICIENT = 102;
    const int64_t ASK_COEFFICIENT = 98;
    const int64_t DROP_SIGNAL = -1;

    struct OrderInfo
    {
        int64_t price;
        EventSide side;
        OrderQueue::iterator position;
    };

    typedef std::map<int64_t, BookLevel, std::greater<int64_t>> BidLevels;
    typedef std::map<int64_t, BookLevel> AskLevels;

    void finish_call_auction();
    void apply_order_in_acution(Order &order);
    void apply_BBO_order(Order &order);
    void apply_limit_order(Order &order);
    void apply_market_order(Order &order);
    void apply_cancel(Trade& trade);
    void record_trade(int64_t price, int64_t quantity);
    void execute_order_at_price(int64_t price, int64_t quantity, bool reduce_bids, bool reduce_asks);
    void execute_trade(Trade &trade);
    void execute_auction_trade(int64_t price, int64_t quantity);

    void handle_pending_market_order(Order &order);
    void handle_pending_market_order(Trade &trade);
    void replay_pending_market_order(std::vector<Trade> trades);

    void make_snapshot(Order &order);
    void make_snapshot(Trade &trade);
    void update_previous_snapshot();
    void fill_snapshot_levels(Snapshot& snapshot);
    void fill_snapshot_statistics(Snapshot& snapshot);


    void handle_pending_CYB_limit_order(Order &order);
    void handle_pending_CYB_limit_order(Trade &trade);
    void replay_CYB_trades(std::vector<Trade> trades);

    TradingSession trading_session;

    BidLevels bids;
    AskLevels asks;

    // ApplSeqNum -> price
    std::map<int64_t, OrderInfo> order_info_map;

    // stats

    int64_t cumulative_trade_quantity = 0;
    int64_t cumulative_turnover = 0;
    int64_t trade_count = 0;
    int64_t last_trade_price = 0;
    int64_t opening_price = 0;

    std::deque<Snapshot> snapshots;

    // market order replay

    int64_t pending_market_order_appl_seq = 0;
    int64_t pending_market_order_quantity = 0;
    std::vector<Trade> pending_market_order_trades;

    // cyb logic

    std::vector<Trade> pending_CYB_trades;

    struct BidCompare
    {
        bool operator()(const Event &a, const Event &b) const
        {
            if (a.price == b.price)
            {
                return a.caa > b.caa;
            }
            return a.price > b.price; // 小顶
        }
    };

    struct AskCompare
    {
        bool operator()(const Event &a, const Event &b) const
        {
            if (a.price == b.price)
            {
                return a.caa > b.caa;
            }

            return a.price < b.price;
        }
    };

    std::priority_queue<Event, std::vector<Event>, BidCompare> pending_bid_limit_order;

    std::priority_queue<Event, std::vector<Event>, AskCompare> pending_ask_limit_order;

    // ApplSeqNum -> bool
    std::map<int64_t, Order> pending_limit_order_alive;
};
