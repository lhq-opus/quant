#include "order_book.hpp"

#include <algorithm>
#include <iostream>
#include <vector>

OrderBook::OrderBook()
    : cumulative_trade_quantity_num(0), cumulative_turnover_num(0), trade_number(0), last_price(0),
      opening_price(0) {}

void OrderBook::build_trade_map(const Trade& trade) {
  // typedef std::map<int64_t,std::vector<TradeInfo>> OrderTradeMap;

  TradeInfo trade_info{};
  trade_info.trade_type = trade.trade_type;
  trade_info.price = trade.price;
  trade_info.quantity = trade.quantity;

  if (trade.bid_appl_seq_num != 0) {
    order_trade_map[trade.bid_appl_seq_num].push_back(trade_info);
  }

  if (trade.offer_appl_seq_num != 0) {
    order_trade_map[trade.offer_appl_seq_num].push_back(trade_info);
  }
}

void OrderBook::apply(Order& order) {
  // auction
  if (order.trading_session == TradingSession::OpeningAution ||
      order.trading_session == TradingSession::ClosingAuction) {
    apply_order_in_acution(order);
    return;
  }

  if (order.trading_session == TradingSession::ContinuousTrade) {
    // limit order
    if (order.order_type == '2') {
      apply_limit_order(order);
      return;
    }

    // best
    if (order.order_type == 'U') {
      apply_BBO_order(order);
      return;
    }

    // market order
    if (order.order_type == '1') {
      apply_market_order(order);
      return;
    }

    return;
  }
}

void OrderBook::apply(const Trade& trade) {
  // Normal trades have already been simulated while applying orders.
  if (trade.trade_type == TradeType::Normal) {
    return;
  }

  apply_cancel(trade);
}

void OrderBook::apply_market_order(Order& order) {
  int64_t remaining_quantity = order.quantity;

  int64_t best_price = 0;
  int64_t quantity_at_best = 0;

  if (order.side == '1') {
    best_price = asks.begin()->first;
    quantity_at_best = asks.begin()->second.total_quantity;
  } else {
    best_price = bids.begin()->first;
    quantity_at_best = bids.begin()->second.total_quantity;
  }

  // trade as normal
  if (quantity_at_best >= remaining_quantity) {
    if (order.side == '1') {
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
  std::vector<TradeInfo> trades = order_trade_map[order.order_appl_seq_num];

  // add to order book at best and wait for cancel
  if (trades.size() == 1 && trades[0].trade_type == TradeType::Cancel) {

    // if (order.caa == "1629942086088510"){
    //     std::cout <<"?" << std::endl;
    //     std::cout << order_trade_map[5901368].size() << std::endl;
    //      std::cout <<trades.size() << std::endl;

    //      if (trades[0].trade_type == TradeType::Cancel){
    //         std::cout <<"*" << std::endl;
    //      }
    // }

    if (order.caa == "1629942086088510") {
      std::cout << "?" << std::endl;
    }

    order.generate_snapshot = false;

    if (order.side == '1') {
      int64_t price = bids.begin()->first;
      BookLevel& level = bids[price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{order.order_appl_seq_num, order.quantity});
      level.total_quantity += order.quantity;
      order_price[order.order_appl_seq_num] = OrderInfo{price, order.side, position};
    } else {
      int64_t price = asks.begin()->first;
      BookLevel& level = asks[price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{order.order_appl_seq_num, order.quantity});
      level.total_quantity += order.quantity;
      order_price[order.order_appl_seq_num] = OrderInfo{price, order.side, position};
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
    order.generate_snapshot = false;

    if (order.side == '1') {
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

        if (order.caa == "1629943945030354") {
          std::cout << price << "," << traded_at_level << std::endl;
        }

        if (level.total_quantity == 0) {
          bids.erase(best_bid);
        }
        level_cnt++;
      }

      if (order.caa == "1629943945030354") {
        std::cout << remaining_quantity << std::endl;
      }
    }

    // Keep the pending-cancel marker outside the price levels.
    order_price[order.order_appl_seq_num] = OrderInfo{-1, order.side, OrderQueue::iterator()};
    return;
  }

  // trade at fixed price
  if (market_order_type == MarketOrderType::TradeAtBest) {
    order.generate_snapshot = false;

    if (order.side == '1') {
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
          level.orders.end(), RestingOrder{order.order_appl_seq_num, remaining_quantity});
      level.total_quantity += remaining_quantity;
      order_price[order.order_appl_seq_num] = OrderInfo{best_price, order.side, position};
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
          level.orders.end(), RestingOrder{order.order_appl_seq_num, remaining_quantity});
      level.total_quantity += remaining_quantity;
      order_price[order.order_appl_seq_num] = OrderInfo{best_price, order.side, position};
    }

    return;
  }

  // trade at slippage price
  if (order.side == '1') {
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

void OrderBook::apply_BBO_order(Order& order) {
  Order limit_order = order;
  if (order.side == '1') {
    limit_order.price = bids.begin()->first;
  } else {
    limit_order.price = asks.begin()->first;
  }
  apply_limit_order(limit_order);
}

void OrderBook::apply_order_in_acution(Order& order) {
  if (order.side == '1') {
    BookLevel& level = bids[order.price];
    OrderQueue::iterator position = level.orders.insert(
        level.orders.end(), RestingOrder{order.order_appl_seq_num, order.quantity});
    level.total_quantity += order.quantity;
    order_price[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
  } else {
    BookLevel& level = asks[order.price];
    OrderQueue::iterator position = level.orders.insert(
        level.orders.end(), RestingOrder{order.order_appl_seq_num, order.quantity});
    level.total_quantity += order.quantity;
    order_price[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
  }
}

void OrderBook::apply_limit_order(Order& order) {
  int64_t remaining_quantity = order.quantity;

  // buy
  if (order.side == '1') {
    while (remaining_quantity > 0 && !asks.empty()) {
      AskLevels::iterator best_ask = asks.begin();
      if (best_ask->first > order.price) {
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
      BookLevel& level = bids[order.price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{order.order_appl_seq_num, remaining_quantity});
      level.total_quantity += remaining_quantity;
      order_price[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
    }

    return;
  }

  // sell
  while (remaining_quantity > 0 && !bids.empty()) {
    BidLevels::iterator best_bid = bids.begin();
    if (best_bid->first < order.price) {
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
    BookLevel& level = asks[order.price];
    OrderQueue::iterator position = level.orders.insert(
        level.orders.end(), RestingOrder{order.order_appl_seq_num, remaining_quantity});
    level.total_quantity += remaining_quantity;
    order_price[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
  }
}

void OrderBook::apply_cancel(const Trade& trade) {

  int64_t order_appl_seq_num =
      trade.bid_appl_seq_num != 0 ? trade.bid_appl_seq_num : trade.offer_appl_seq_num;
  OrderPriceMap::const_iterator order_info = order_price.find(order_appl_seq_num);
  if (order_info == order_price.end()) {
    return;
  }
  int64_t price = order_info->second.price;
  if (price == -1) {
    return;
  }
  char side = order_info->second.side;

  if (side == '1') {
    BidLevels::iterator bid = bids.find(price);
    if (bid == bids.end()) {
      return;
    }
    OrderQueue::iterator position = order_info->second.position;
    position->remaining_quantity -= trade.quantity;
    bid->second.total_quantity -= trade.quantity;
    if (position->remaining_quantity == 0) {
      bid->second.orders.erase(position);
      order_price.erase(order_info);
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
  OrderQueue::iterator position = order_info->second.position;
  position->remaining_quantity -= trade.quantity;
  ask->second.total_quantity -= trade.quantity;
  if (position->remaining_quantity == 0) {
    ask->second.orders.erase(position);
    order_price.erase(order_info);
  }

  if (ask->second.total_quantity == 0) {
    asks.erase(ask);
  }

  //   if (trade.caa == "1629943945030657") {
  //     std::cout << "?3" << std::endl;
  //     std::cout << trade.caa << "," << price << "," << side << "," << trade.quantity <<
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

Snapshot OrderBook::make_snapshot(const Order& order) {
  return make_snapshot(order.caa, EventType::Order, order.trading_session);
}

Snapshot OrderBook::make_snapshot(const Trade& trade) {
  EventType event_type =
      trade.trade_type == TradeType::Cancel ? EventType::Cancel : EventType::Trade;
  return make_snapshot(trade.caa, event_type, trade.trading_session);
}

Snapshot OrderBook::make_snapshot(const std::string& caa, EventType event_type,
                                  TradingSession session) {
  Snapshot snapshot;
  snapshot.caa = caa;
  snapshot.trade_number = trade_number;
  snapshot.last_price = last_price;
  snapshot.opening_price = opening_price;
  snapshot.cumulative_trade_quantity = cumulative_trade_quantity_num;
  snapshot.cumulative_turnover = cumulative_turnover_num;
  snapshot.event_type = event_type;

  // if (caa !=""){
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

  snapshot.trading_session = session;

  return snapshot;
}
