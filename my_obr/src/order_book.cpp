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
  // 在撮合前记录原始市价身份：市价单可能立即全部成交，不会留在活动订单索引中。
  // 只根据原委托的类型判断；本方最优 U 和限价单都不属于这里的市价单。
  if (order.order_type == '1') {
    market_order_ids.insert(std::make_pair(order.channel_no, order.order_appl_seq_num));
  }

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

void OrderBook::get_market_trade_sides(const Trade& trade, bool& is_bid, bool& is_ask) const {
  // 使用 Trade 引用的原委托序号，而不是该 Trade 自身的序号；通道也是查询键的一部分。
  // 两侧独立查询，所以结果可同时为 true；零引用自然不在合法市价原单集合中。
  is_bid = market_order_ids.count(std::make_pair(trade.channel_no, trade.bid_appl_seq_num)) != 0;
  is_ask = market_order_ids.count(std::make_pair(trade.channel_no, trade.offer_appl_seq_num)) != 0;
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

  // 对手最优档足够时，一次传入本单全部成交量，由公共方法按同价 FIFO 扣量。
  if (quantity_at_best >= remaining_quantity) {
    // 卖单扣 bids，买单扣 asks；来单尚未入簿，无需从本方档位再扣一次。
    execute_trade(best_price, remaining_quantity, order.side == '2', order.side == '1');
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

  // 五档分支按价格档计数，同一个档位内成交多张订单仍只算经过一档。
  if (market_order_type == MarketOrderType::CancelAfterFiveLevel) {
    order.generate_snapshot = false;

    if (order.side == '1') {
      int64_t level_cnt = 0;
      while (remaining_quantity > 0 && !asks.empty() && level_cnt < 5) {
        AskLevels::iterator best_ask = asks.begin();
        int64_t price = best_ask->first;
        int64_t traded_quantity = std::min(remaining_quantity, best_ask->second.total_quantity);
        // 买单只扣当前卖档；方法可能删除该档，调用后不再访问 best_ask。
        execute_trade(price, traded_quantity, false, true);
        remaining_quantity -= traded_quantity;
        level_cnt++;
      }
    } else {
      int64_t level_cnt = 0;
      while (remaining_quantity > 0 && !bids.empty() && level_cnt < 5) {
        BidLevels::iterator best_bid = bids.begin();
        int64_t price = best_bid->first;
        int64_t traded_at_level = std::min(remaining_quantity, best_bid->second.total_quantity);
        // 卖单只扣当前买档，下一轮重新取得扣量后的最优档。
        execute_trade(price, traded_at_level, true, false);
        remaining_quantity -= traded_at_level;

        if (order.caa == "1629943945030354") {
          std::cout << price << "," << traded_at_level << std::endl;
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

  // 固定最优价分支只吃完原对手最优档，未成交余量随后挂在本方同价档。
  if (market_order_type == MarketOrderType::TradeAtBest) {
    order.generate_snapshot = false;
    execute_trade(best_price, quantity_at_best, order.side == '2', order.side == '1');
    remaining_quantity -= quantity_at_best;

    if (order.side == '1') {
      BookLevel& level = bids[best_price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{order.order_appl_seq_num, remaining_quantity});
      level.total_quantity += remaining_quantity;
      order_price[order.order_appl_seq_num] = OrderInfo{best_price, order.side, position};
    } else {
      BookLevel& level = asks[best_price];
      OrderQueue::iterator position = level.orders.insert(
          level.orders.end(), RestingOrder{order.order_appl_seq_num, remaining_quantity});
      level.total_quantity += remaining_quantity;
      order_price[order.order_appl_seq_num] = OrderInfo{best_price, order.side, position};
    }

    return;
  }

  // 跨价分支逐档决定成交价，避免把后续档位的成交也记在第一档价格上。
  if (order.side == '1') {
    while (remaining_quantity > 0 && !asks.empty()) {
      AskLevels::iterator best_ask = asks.begin();
      int64_t traded_quantity = std::min(remaining_quantity, best_ask->second.total_quantity);
      execute_trade(best_ask->first, traded_quantity, false, true);
      remaining_quantity -= traded_quantity;
    }

    return;
  }

  while (remaining_quantity > 0 && !bids.empty()) {
    BidLevels::iterator best_bid = bids.begin();
    int64_t traded_quantity = std::min(remaining_quantity, best_bid->second.total_quantity);
    execute_trade(best_bid->first, traded_quantity, true, false);
    remaining_quantity -= traded_quantity;
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

  // 买单依次吃卖档；本函数只决定可成交价格和数量，逐单扣量交给公共方法。
  if (order.side == '1') {
    while (remaining_quantity > 0 && !asks.empty()) {
      AskLevels::iterator best_ask = asks.begin();
      if (best_ask->first > order.price) {
        break;
      }
      int64_t traded_quantity = std::min(remaining_quantity, best_ask->second.total_quantity);
      execute_trade(best_ask->first, traded_quantity, false, true);
      remaining_quantity -= traded_quantity;
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

  // 卖单执行镜像流程：每次只消耗当前买档，下一轮重新取得最优买价。
  while (remaining_quantity > 0 && !bids.empty()) {
    BidLevels::iterator best_bid = bids.begin();
    if (best_bid->first < order.price) {
      break;
    }
    int64_t traded_quantity = std::min(remaining_quantity, best_bid->second.total_quantity);
    execute_trade(best_bid->first, traded_quantity, true, false);
    remaining_quantity -= traded_quantity;
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

void OrderBook::execute_trade(int64_t price, int64_t quantity, bool reduce_bids, bool reduce_asks) {
  // quantity 是调用方已经确定的成交量。一次调用可能涉及同价多单，
  // 集合竞价还可能跨过不同挂价，因此循环按 FIFO 队首拆成逐单配对。
  int64_t remaining_quantity = quantity;
  while (remaining_quantity > 0) {
    int64_t traded_quantity = remaining_quantity;
    if (reduce_bids) {
      traded_quantity =
          std::min(traded_quantity, bids.begin()->second.orders.front().remaining_quantity);
    }
    if (reduce_asks) {
      traded_quantity =
          std::min(traded_quantity, asks.begin()->second.orders.front().remaining_quantity);
    }

    // 先确定这一对订单能成交多少，再用同一数量扣减所选侧。
    // 连续撮合只选对手侧；集合竞价选两侧，但仍表示同一笔成交。
    if (reduce_bids) {
      BidLevels::iterator bid = bids.begin();
      BookLevel& level = bid->second;
      RestingOrder& order = level.orders.front();
      order.remaining_quantity -= traded_quantity;
      level.total_quantity -= traded_quantity;
      if (order.remaining_quantity == 0) {
        // 先删索引再删节点；节点删除后，order 引用和索引中的迭代器都不能再使用。
        order_price.erase(order.order_appl_seq_num);
        level.orders.pop_front();
      }
      if (level.orders.empty()) {
        bids.erase(bid);
      }
    }

    if (reduce_asks) {
      AskLevels::iterator ask = asks.begin();
      BookLevel& level = ask->second;
      RestingOrder& order = level.orders.front();
      order.remaining_quantity -= traded_quantity;
      level.total_quantity -= traded_quantity;
      if (order.remaining_quantity == 0) {
        order_price.erase(order.order_appl_seq_num);
        level.orders.pop_front();
      }
      if (level.orders.empty()) {
        asks.erase(ask);
      }
    }

    // 统计放在两侧扣量之后，每次配对只累计一次，避免竞价成交量被算成两倍。
    // price 始终是实际模拟成交价；竞价时不能用被扣订单的挂价代替它。
    if (trade_number == 0) {
      opening_price = price;
    }
    ++trade_number;
    last_price = price;
    cumulative_trade_quantity_num += traded_quantity;
    cumulative_turnover_num += price * traded_quantity;
    remaining_quantity -= traded_quantity;
  }
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

  // 竞价总成交量已由选价过程算出；公共方法同时扣双方最优订单，统一按竞价价格记账。
  execute_trade(auction_price, trade_quantity, true, true);
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
  snapshot.trading_session = session;

  // 元信息与统计在这里填写，五档价格和数量统一由盘口投影方法生成。
  fill_snapshot_levels(snapshot);
  return snapshot;
}

void OrderBook::fill_snapshot_levels(Snapshot& snapshot) const {
  // 每次重建恰好五个零档，随后覆盖当前存在的档位；复用快照时不会残留旧数据。
  snapshot.bids.assign(5, PriceLevel{0, 0});
  snapshot.asks.assign(5, PriceLevel{0, 0});

  // bids 已按价格降序排列：下标 0 是买一，price/quantity 分别对应 bp1/bs1。
  std::size_t index = 0;
  for (BidLevels::const_iterator bid = bids.begin(); bid != bids.end() && index < 5;
       ++bid, ++index) {
    snapshot.bids[index] = PriceLevel{bid->first, bid->second.total_quantity};
  }

  // asks 已按价格升序排列：下标 0 是卖一，price/quantity 分别对应 ap1/as1。
  index = 0;
  for (AskLevels::const_iterator ask = asks.begin(); ask != asks.end() && index < 5;
       ++ask, ++index) {
    snapshot.asks[index] = PriceLevel{ask->first, ask->second.total_quantity};
  }
}
