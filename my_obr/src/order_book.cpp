#include "order_book.hpp"

#include <algorithm>
#include <iostream>
#include <vector>

OrderBook::OrderBook()
    : cumulative_trade_quantity_num(0), cumulative_turnover_num(0), trade_number(0), last_price(0),
      opening_price(0) {}

void OrderBook::build_trade_map(Event& event) {
  // typedef std::map<int64_t,std::vector<TradeInfo>> OrderTradeMap;

  if (event.type == EventType::Order) {
    return;
  }

  TradeInfo trade_info{};
  if (event.type == EventType::Cancel) {
    trade_info.trade_type = TradeType::Cancel;
    trade_info.price = event.price;
    trade_info.quantity = event.quantity;
  } else {
    trade_info.trade_type = TradeType::Normal;
    trade_info.price = event.price;
    trade_info.quantity = event.quantity;
  }

  if (event.bid_appl_seq_num != 0) {

    order_trade_map[event.bid_appl_seq_num].push_back(trade_info);
  }

  if (event.offer_appl_seq_num != 0) {
    order_trade_map[event.offer_appl_seq_num].push_back(trade_info);
  }
}

void OrderBook::apply(Event& event, TradingSession session) {

  // filter normal trade
  if (!event.need_handle) {
    return;
  }

  // cancel trade
  if (event.type == EventType::Cancel) {
    apply_cancel(event);
    return;
  }

  // order

  // auction
  if (session == TradingSession::OpeningAution || session == TradingSession::ClosingAuction) {
    apply_order_in_acution(event);

    return;
  }

  if (session == TradingSession::ContinuousTrade) {

    // limit order

    if (event.order_type == '2') {
      apply_limit_order(event);
      return;
    }

    // best
    if (event.order_type == 'U') {
      apply_BBO_order(event);
      return;
    }

    // market order
    if (event.order_type == '1') {
      apply_market_order(event);
      return;
    }

    return;
  }
}

void OrderBook::apply_market_order(Event& event) {
  int64_t remaining_quantity = event.quantity;

  int64_t best_price = 0;
  int64_t quantity_at_best = 0;

  if (event.side == '1') {
    best_price = asks.begin()->first;
    quantity_at_best = asks.begin()->second.total_quantity;
  } else {
    best_price = bids.begin()->first;
    quantity_at_best = bids.begin()->second.total_quantity;
  }

  // trade as normal
  if (quantity_at_best >= remaining_quantity) {
    if (event.side == '1') {
      AskLevels::iterator best_ask = asks.begin();
      BookLevel& level = best_ask->second;

      while (remaining_quantity > 0) {
        RestingOrder& resting_order = level.orders.front();
        int64_t traded_quantity = std::min(remaining_quantity, resting_order.remaining_quantity);
        record_trade(best_price, traded_quantity);
        remaining_quantity -= traded_quantity;
        resting_order.remaining_quantity -= traded_quantity;
        level.total_quantity -= traded_quantity;

        if (resting_order.remaining_quantity == 0) {
          order_price.erase(resting_order.order_appl_seq_num);
          level.orders.pop_front();
        }
      }

      if (level.total_quantity == 0) {
        asks.erase(best_ask);
      }
    } else {
      BidLevels::iterator best_bid = bids.begin();
      BookLevel& level = best_bid->second;

      while (remaining_quantity > 0) {
        RestingOrder& resting_order = level.orders.front();
        int64_t traded_quantity = std::min(remaining_quantity, resting_order.remaining_quantity);
        record_trade(best_price, traded_quantity);
        remaining_quantity -= traded_quantity;
        resting_order.remaining_quantity -= traded_quantity;
        level.total_quantity -= traded_quantity;

        if (resting_order.remaining_quantity == 0) {
          order_price.erase(resting_order.order_appl_seq_num);
          level.orders.pop_front();
        }
      }

      if (level.total_quantity == 0) {
        bids.erase(best_bid);
      }
    }
    return;
  }

  // quantity_at_best is not enough
  MarketOrderType market_order_type;
  std::vector<TradeInfo> trades = order_trade_map[event.order_appl_seq_num];

  // add to order book at best and wait for cancel
  if (trades.size() == 1 && trades[0].trade_type == TradeType::Cancel) {

    // if (event.caa == "1629942086088510"){
    //     std::cout <<"?" << std::endl;
    //     std::cout << order_trade_map[5901368].size() << std::endl;
    //      std::cout <<trades.size() << std::endl;

    //      if (trades[0].trade_type == TradeType::Cancel){
    //         std::cout <<"*" << std::endl;
    //      }
    // }

    if (event.caa == "1629942086088510") {
      std::cout << "?" << std::endl;
    }

    event.generate_snapshot = false;

    if (event.side == '1') {
      int64_t price = bids.begin()->first;
      BookLevel& level = bids[price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{event.order_appl_seq_num, event.quantity});
      level.total_quantity += event.quantity;
      order_price[event.order_appl_seq_num] = OrderInfo{price, event.side, position};
    } else {
      int64_t price = asks.begin()->first;
      BookLevel& level = asks[price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{event.order_appl_seq_num, event.quantity});
      level.total_quantity += event.quantity;
      order_price[event.order_appl_seq_num] = OrderInfo{price, event.side, position};
    }
    return;
  }

  market_order_type = MarketOrderType::TradeAtBest;

  if (trades.size() > 1 && trades.back().trade_type == TradeType::Cancel) {
    market_order_type = MarketOrderType::CancelAfterFiveLevel;
  } else {
    for (std::size_t index = 0; index < trades.size(); ++index) {
      if (trades[index].price != best_price) {
        market_order_type = MarketOrderType::TradeWithSlippage;
        break;
      }
    }
  }

  // trade after five levels
  if (market_order_type == MarketOrderType::CancelAfterFiveLevel) {
    event.generate_snapshot = false;

    if (event.side == '1') {
      int64_t level_cnt = 0;
      while (remaining_quantity > 0 && !asks.empty() && level_cnt < 5) {
        AskLevels::iterator best_ask = asks.begin();
        int64_t price = best_ask->first;
        BookLevel& level = best_ask->second;

        while (remaining_quantity > 0 && level.total_quantity > 0) {
          RestingOrder& resting_order = level.orders.front();
          int64_t traded_quantity = std::min(remaining_quantity, resting_order.remaining_quantity);
          record_trade(price, traded_quantity);
          remaining_quantity -= traded_quantity;
          resting_order.remaining_quantity -= traded_quantity;
          level.total_quantity -= traded_quantity;

          if (resting_order.remaining_quantity == 0) {
            order_price.erase(resting_order.order_appl_seq_num);
            level.orders.pop_front();
          }
        }

        if (level.total_quantity == 0) {
          asks.erase(best_ask);
        }
        level_cnt++;
      }
    } else {
      int64_t level_cnt = 0;
      while (remaining_quantity > 0 && !bids.empty() && level_cnt < 5) {
        BidLevels::iterator best_bid = bids.begin();
        int64_t price = best_bid->first;
        BookLevel& level = best_bid->second;
        int64_t traded_at_level = 0;

        while (remaining_quantity > 0 && level.total_quantity > 0) {
          RestingOrder& resting_order = level.orders.front();
          int64_t traded_quantity = std::min(remaining_quantity, resting_order.remaining_quantity);
          record_trade(price, traded_quantity);
          remaining_quantity -= traded_quantity;
          resting_order.remaining_quantity -= traded_quantity;
          level.total_quantity -= traded_quantity;
          traded_at_level += traded_quantity;

          if (resting_order.remaining_quantity == 0) {
            order_price.erase(resting_order.order_appl_seq_num);
            level.orders.pop_front();
          }
        }

        if (event.caa == "1629943945030354") {
          std::cout << price << "," << traded_at_level << std::endl;
        }

        if (level.total_quantity == 0) {
          bids.erase(best_bid);
        }
        level_cnt++;
      }

      if (event.caa == "1629943945030354") {
        std::cout << remaining_quantity << std::endl;
      }
    }

    // Keep the pending-cancel marker outside the price levels.
    order_price[event.order_appl_seq_num] = OrderInfo{-1, event.side, OrderQueue::iterator()};
    return;
  }

  // trade at fixed price
  if (market_order_type == MarketOrderType::TradeAtBest) {
    event.generate_snapshot = false;

    if (event.side == '1') {
      AskLevels::iterator best_ask = asks.begin();
      BookLevel& opposite_level = best_ask->second;
      while (opposite_level.total_quantity > 0) {
        RestingOrder& resting_order = opposite_level.orders.front();
        int64_t traded_quantity = resting_order.remaining_quantity;
        record_trade(best_price, traded_quantity);
        remaining_quantity -= traded_quantity;
        opposite_level.total_quantity -= traded_quantity;
        order_price.erase(resting_order.order_appl_seq_num);
        opposite_level.orders.pop_front();
      }
      asks.erase(best_ask);

      BookLevel& level = bids[best_price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{event.order_appl_seq_num, remaining_quantity});
      level.total_quantity += remaining_quantity;
      order_price[event.order_appl_seq_num] = OrderInfo{best_price, event.side, position};
    } else {
      BidLevels::iterator best_bid = bids.begin();
      BookLevel& opposite_level = best_bid->second;
      while (opposite_level.total_quantity > 0) {
        RestingOrder& resting_order = opposite_level.orders.front();
        int64_t traded_quantity = resting_order.remaining_quantity;
        record_trade(best_price, traded_quantity);
        remaining_quantity -= traded_quantity;
        opposite_level.total_quantity -= traded_quantity;
        order_price.erase(resting_order.order_appl_seq_num);
        opposite_level.orders.pop_front();
      }
      bids.erase(best_bid);

      BookLevel& level = asks[best_price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{event.order_appl_seq_num, remaining_quantity});
      level.total_quantity += remaining_quantity;
      order_price[event.order_appl_seq_num] = OrderInfo{best_price, event.side, position};
    }

    return;
  }

  // trade at slippage price
  if (event.side == '1') {
    while (remaining_quantity > 0 && !asks.empty()) {
      AskLevels::iterator best_ask = asks.begin();
      BookLevel& level = best_ask->second;

      while (remaining_quantity > 0 && level.total_quantity > 0) {
        RestingOrder& resting_order = level.orders.front();
        int64_t traded_quantity = std::min(remaining_quantity, resting_order.remaining_quantity);
        record_trade(best_ask->first, traded_quantity);
        remaining_quantity -= traded_quantity;
        resting_order.remaining_quantity -= traded_quantity;
        level.total_quantity -= traded_quantity;

        if (resting_order.remaining_quantity == 0) {
          order_price.erase(resting_order.order_appl_seq_num);
          level.orders.pop_front();
        }
      }

      if (level.total_quantity == 0) {
        asks.erase(best_ask);
      }
    }

    return;
  }

  while (remaining_quantity > 0 && !bids.empty()) {
    BidLevels::iterator best_bid = bids.begin();
    BookLevel& level = best_bid->second;

    while (remaining_quantity > 0 && level.total_quantity > 0) {
      RestingOrder& resting_order = level.orders.front();
      int64_t traded_quantity = std::min(remaining_quantity, resting_order.remaining_quantity);
      record_trade(best_bid->first, traded_quantity);
      remaining_quantity -= traded_quantity;
      resting_order.remaining_quantity -= traded_quantity;
      level.total_quantity -= traded_quantity;

      if (resting_order.remaining_quantity == 0) {
        order_price.erase(resting_order.order_appl_seq_num);
        level.orders.pop_front();
      }
    }

    if (level.total_quantity == 0) {
      bids.erase(best_bid);
    }
  }
}

void OrderBook::apply_BBO_order(Event& event) {
  Event limit_event = event;
  if (event.side == '1') {
    limit_event.price = bids.begin()->first;
  } else {
    limit_event.price = asks.begin()->first;
  }
  apply_limit_order(limit_event);
}

void OrderBook::apply_order_in_acution(Event& event) {
  if (event.side == '1') {
    BookLevel& level = bids[event.price];
    OrderQueue::iterator position = level.orders.insert(
        level.orders.end(), RestingOrder{event.order_appl_seq_num, event.quantity});
    level.total_quantity += event.quantity;
    order_price[event.order_appl_seq_num] = OrderInfo{event.price, event.side, position};
  } else {
    BookLevel& level = asks[event.price];
    OrderQueue::iterator position = level.orders.insert(
        level.orders.end(), RestingOrder{event.order_appl_seq_num, event.quantity});
    level.total_quantity += event.quantity;
    order_price[event.order_appl_seq_num] = OrderInfo{event.price, event.side, position};
  }
}

void OrderBook::apply_limit_order(Event& event) {
  int64_t remaining_quantity = event.quantity;

  // buy
  if (event.side == '1') {
    while (remaining_quantity > 0 && !asks.empty()) {
      AskLevels::iterator best_ask = asks.begin();
      if (best_ask->first > event.price) {
        break;
      }
      BookLevel& level = best_ask->second;

      while (remaining_quantity > 0 && level.total_quantity > 0) {
        RestingOrder& resting_order = level.orders.front();
        int64_t traded_quantity = std::min(remaining_quantity, resting_order.remaining_quantity);
        record_trade(best_ask->first, traded_quantity);
        remaining_quantity -= traded_quantity;
        resting_order.remaining_quantity -= traded_quantity;
        level.total_quantity -= traded_quantity;

        if (resting_order.remaining_quantity == 0) {
          order_price.erase(resting_order.order_appl_seq_num);
          level.orders.pop_front();
        }
      }

      if (level.total_quantity == 0) {
        asks.erase(best_ask);
      }
    }

    if (remaining_quantity > 0) {
      BookLevel& level = bids[event.price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{event.order_appl_seq_num, remaining_quantity});
      level.total_quantity += remaining_quantity;
      order_price[event.order_appl_seq_num] = OrderInfo{event.price, event.side, position};
    }

    return;
  }

  // sell
  while (remaining_quantity > 0 && !bids.empty()) {
    BidLevels::iterator best_bid = bids.begin();
    if (best_bid->first < event.price) {
      break;
    }
    BookLevel& level = best_bid->second;

    while (remaining_quantity > 0 && level.total_quantity > 0) {
      RestingOrder& resting_order = level.orders.front();
      int64_t traded_quantity = std::min(remaining_quantity, resting_order.remaining_quantity);
      record_trade(best_bid->first, traded_quantity);
      remaining_quantity -= traded_quantity;
      resting_order.remaining_quantity -= traded_quantity;
      level.total_quantity -= traded_quantity;

      if (resting_order.remaining_quantity == 0) {
        order_price.erase(resting_order.order_appl_seq_num);
        level.orders.pop_front();
      }
    }

    if (level.total_quantity == 0) {
      bids.erase(best_bid);
    }
  }

  if (remaining_quantity > 0) {
    BookLevel& level = asks[event.price];
    OrderQueue::iterator position = level.orders.insert(
        level.orders.end(), RestingOrder{event.order_appl_seq_num, remaining_quantity});
    level.total_quantity += remaining_quantity;
    order_price[event.order_appl_seq_num] = OrderInfo{event.price, event.side, position};
  }
}

void OrderBook::apply_cancel(Event& event) {

  OrderPriceMap::const_iterator order = order_price.find(event.order_appl_seq_num);
  if (order == order_price.end()) {
    return;
  }
  int64_t price = order->second.price;
  if (price == -1) {
    return;
  }
  char side = order->second.side;

  if (side == '1') {
    BidLevels::iterator bid = bids.find(price);
    if (bid == bids.end()) {
      return;
    }
    OrderQueue::iterator position = order->second.position;
    position->remaining_quantity -= event.quantity;
    bid->second.total_quantity -= event.quantity;
    if (position->remaining_quantity == 0) {
      bid->second.orders.erase(position);
      order_price.erase(order);
    }

    if (bid->second.total_quantity == 0) {
      bids.erase(bid);
    }

    return;
  }

  AskLevels::iterator ask = asks.find(price);
  if (ask == asks.end()) {
    return;
  }
  OrderQueue::iterator position = order->second.position;
  position->remaining_quantity -= event.quantity;
  ask->second.total_quantity -= event.quantity;
  if (position->remaining_quantity == 0) {
    ask->second.orders.erase(position);
    order_price.erase(order);
  }

  if (ask->second.total_quantity == 0) {
    asks.erase(ask);
  }

  //   if (event.caa == "1629943945030657") {
  //     std::cout << "?3" << std::endl;
  //     std::cout << event.caa << "," << price << "," << side << "," << event.quantity <<
  //     ask->first
  //               << std::endl;

  //     BidLevels::iterator bid = bids.begin();
  //     std::cout << "?3" << bid->first << std::endl;
  //   }

  return;
}

void OrderBook::record_trade(int64_t price, int64_t quantity) {
  if (trade_number == 0) {
    opening_price = price;
  }
  ++trade_number;
  last_price = price;
  cumulative_trade_quantity_num += quantity;
  cumulative_turnover_num += price * quantity;
}

void OrderBook::find_call_action_result(int64_t& auction_price, int64_t& trade_quantity,
                                        int64_t& remaining_quantity_at_price, char& side) {
  std::vector<int64_t> prices;
  BidLevels::iterator bid = bids.begin();

  for (; bid != bids.end(); ++bid) {
    prices.push_back(bid->first);
  }

  AskLevels::iterator ask = asks.begin();
  for (; ask != asks.end(); ++ask) {
    prices.push_back(ask->first);
  }

  std::sort(prices.begin(), prices.end());
  prices.erase(std::unique(prices.begin(), prices.end()), prices.end());

  std::vector<AuctionCandidate> candidates;
  std::vector<int64_t>::iterator price = prices.begin();

  for (; price != prices.end(); ++price) {
    int64_t buy_quantity = 0;
    int64_t sell_quantity = 0;
    AuctionCandidate candidate;

    bid = bids.begin();

    for (; bid != bids.end(); ++bid) {
      if (bid->first >= *price) {
        buy_quantity += bid->second.total_quantity;
      }
    }

    ask = asks.begin();

    for (; ask != asks.end(); ++ask) {
      if (ask->first <= *price) {
        sell_quantity += ask->second.total_quantity;
      }
    }

    int64_t actual_trade = std::min(buy_quantity, sell_quantity);

    candidate.price = *price;
    candidate.trade_quantity = actual_trade;
    candidate.remain_quantity_at_price = std::abs(buy_quantity - sell_quantity);
    if (buy_quantity > sell_quantity) {
      candidate.side = '1';
    } else {
      candidate.side = '2';
    }

    candidates.push_back(candidate);
  }

  std::sort(candidates.begin(), candidates.end(),
            [](const AuctionCandidate& x, const AuctionCandidate& y) {
              if (x.trade_quantity != y.trade_quantity) {
                return x.trade_quantity > y.trade_quantity;
              }
              return x.remain_quantity_at_price < y.remain_quantity_at_price;
            });

  auction_price = candidates[0].price;
  trade_quantity = candidates[0].trade_quantity;
  remaining_quantity_at_price = candidates[0].remain_quantity_at_price;
  side = candidates[0].side;

  return;
}

void OrderBook::finish_call_auction() {
  int64_t auction_price = 0;
  int64_t trade_quantity = 0;
  int64_t remaining_quantity_at_price = 0;
  char side = '1';

  find_call_action_result(auction_price, trade_quantity, remaining_quantity_at_price, side);

  int64_t remaining_quantity = trade_quantity;
  while (remaining_quantity > 0) {
    BidLevels::iterator bid = bids.begin();
    AskLevels::iterator ask = asks.begin();
    RestingOrder& buy_order = bid->second.orders.front();
    RestingOrder& sell_order = ask->second.orders.front();
    int64_t traded_quantity = std::min(
        remaining_quantity, std::min(buy_order.remaining_quantity, sell_order.remaining_quantity));

    record_trade(auction_price, traded_quantity);
    remaining_quantity -= traded_quantity;
    buy_order.remaining_quantity -= traded_quantity;
    sell_order.remaining_quantity -= traded_quantity;
    bid->second.total_quantity -= traded_quantity;
    ask->second.total_quantity -= traded_quantity;

    if (buy_order.remaining_quantity == 0) {
      order_price.erase(buy_order.order_appl_seq_num);
      bid->second.orders.pop_front();
    }
    if (sell_order.remaining_quantity == 0) {
      order_price.erase(sell_order.order_appl_seq_num);
      ask->second.orders.pop_front();
    }
    if (bid->second.total_quantity == 0) {
      bids.erase(bid);
    }
    if (ask->second.total_quantity == 0) {
      asks.erase(ask);
    }
  }
}

Snapshot OrderBook::make_snapshot(Event& event) {
  Snapshot snapshot;
  snapshot.caa = event.caa;
  snapshot.trade_number = trade_number;
  snapshot.last_price = last_price;
  snapshot.opening_price = opening_price;
  snapshot.cumulative_trade_quantity = cumulative_trade_quantity_num;
  snapshot.cumulative_turnover = cumulative_turnover_num;
  snapshot.event_type = event.type;

  // if (event.caa !=""){
  //     std::cout<<"bids:" << std::endl;
  // for (; bid != bids.end(); ++bid) {
  //     std::cout<< bid->first <<" ,"<< bid->second << std::endl;
  // }
  // }

  // while (bid != bids.end() && snapshot.bids.size() < 5) {

  //     PriceLevel level = {bid->first, bid->second.total_quantity};

  //     snapshot.bids.push_back(level);

  //     ++bid;
  // }
  BidLevels::iterator bid = bids.begin();

  for (; bid != bids.end() && snapshot.bids.size() < 5; ++bid) {
    PriceLevel level = {bid->first, bid->second.total_quantity};

    snapshot.bids.push_back(level);
  }

  while (snapshot.bids.size() < 5) {
    PriceLevel level = {0, 0};
    snapshot.bids.push_back(level);
  }

  AskLevels::iterator ask = asks.begin();
  for (; ask != asks.end() && snapshot.asks.size() < 5; ++ask) {
    PriceLevel level = {ask->first, ask->second.total_quantity};
    snapshot.asks.push_back(level);
  }

  while (snapshot.asks.size() < 5) {
    PriceLevel level = {0, 0};
    snapshot.asks.push_back(level);
  }

  snapshot.trading_session = event.trading_session;

  return snapshot;
}
