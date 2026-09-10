#include "order_book.hpp"

#include "checked_math.hpp"

#include <algorithm>
#include <stdexcept>
#include <vector>

OrderBook::OrderBook()
    : bids('1'), asks('2'), cumulative_trade_quantity_num(0), cumulative_turnover_num(0),
      source_trade_count(0), source_trade_quantity(0), source_turnover(0), last_trade_price(0),
      opening_price(0) {}

void OrderBook::build_trade_map(Event& event) {
  if (event.type == EventType::Order) {
    return;
  }
  if (event.quantity <= 0 || event.channel_no < 0 || event.bid_appl_seq_num < 0 ||
      event.offer_appl_seq_num < 0) {
    throw std::invalid_argument("invalid execution quantity or reference");
  }
  if ((event.type == EventType::Cancel &&
       ((event.bid_appl_seq_num == 0) == (event.offer_appl_seq_num == 0))) ||
      (event.type == EventType::Trade &&
       (event.bid_appl_seq_num == 0 || event.offer_appl_seq_num == 0 ||
        event.bid_appl_seq_num == event.offer_appl_seq_num || event.price <= 0)) ||
      (event.type != EventType::Trade && event.type != EventType::Cancel)) {
    throw std::invalid_argument("invalid execution type or side references");
  }

  TradeInfo trade_info = {};
  trade_info.trade_type = event.type == EventType::Cancel ? TradeType::Cancel : TradeType::Normal;
  trade_info.price = event.price;
  trade_info.quantity = event.quantity;
  const OrderKey bid_key(event.channel_no, event.bid_appl_seq_num);
  const OrderKey ask_key(event.channel_no, event.offer_appl_seq_num);
  bool bid_created = false;
  bool ask_created = false;
  bool bid_appended = false;
  try {
    if (event.bid_appl_seq_num != 0) {
      const std::pair<OrderTradeMap::iterator, bool> entry =
          order_trade_map.emplace(bid_key, std::vector<TradeInfo>());
      bid_created = entry.second;
      entry.first->second.push_back(trade_info);
      bid_appended = true;
    }
    if (event.offer_appl_seq_num != 0) {
      const std::pair<OrderTradeMap::iterator, bool> entry =
          order_trade_map.emplace(ask_key, std::vector<TradeInfo>());
      ask_created = entry.second;
      entry.first->second.push_back(trade_info);
    }
  } catch (...) {
    if (bid_appended) {
      order_trade_map.find(bid_key)->second.pop_back();
    }
    if (bid_created) {
      order_trade_map.erase(bid_key);
    }
    if (ask_created) {
      order_trade_map.erase(ask_key);
    }
    throw;
  }
}

void OrderBook::apply(Event& event, TradingSession session) {
  if (event.quantity <= 0 || event.channel_no < 0) {
    throw std::invalid_argument("quantity must be positive and channel must be nonnegative");
  }

  // Source F events validate remainders and update the exported statistics.
  // Experimental matching has already changed levels and its separate totals.
  if (event.type == EventType::Trade) {
    if (event.bid_appl_seq_num <= 0 || event.offer_appl_seq_num <= 0 || event.price <= 0) {
      throw std::invalid_argument("trade requires two positive order references and a price");
    }
    OrderPriceMap::iterator bid_order =
        order_price.find(OrderKey(event.channel_no, event.bid_appl_seq_num));
    OrderPriceMap::iterator ask_order =
        order_price.find(OrderKey(event.channel_no, event.offer_appl_seq_num));
    if (bid_order == order_price.end() || ask_order == order_price.end()) {
      throw std::runtime_error("trade references an unknown order");
    }
    if (bid_order->second.side != '1' || ask_order->second.side != '2') {
      throw std::runtime_error("trade reference side does not match the original order");
    }
    if (event.quantity > bid_order->second.remaining_quantity ||
        event.quantity > ask_order->second.remaining_quantity) {
      throw std::runtime_error("trade exceeds a referenced order's remaining quantity");
    }
    if (event.quantity >
            bid_order->second.remaining_quantity - bid_order->second.pending_cancel_quantity ||
        event.quantity >
            ask_order->second.remaining_quantity - ask_order->second.pending_cancel_quantity) {
      throw std::runtime_error("trade would consume quantity reserved for a pending cancellation");
    }
    const int64_t next_count = checked_add(source_trade_count, 1);
    const int64_t next_quantity = checked_add(source_trade_quantity, event.quantity);
    const int64_t trade_amount = checked_multiply(event.price, event.quantity);
    const int64_t next_turnover = checked_add(source_turnover, trade_amount);
    // Validate all arithmetic before changing either order or any statistic.
    bid_order->second.remaining_quantity -= event.quantity;
    ask_order->second.remaining_quantity -= event.quantity;
    source_trade_count = next_count;
    source_trade_quantity = next_quantity;
    source_turnover = next_turnover;
    last_trade_price = event.price;
    if (opening_price == 0) {
      opening_price = event.price;
    }
    return;
  }
  if (!event.need_handle) {
    return;
  }

  if (event.type == EventType::Cancel) {
    apply_cancel(event);
    return;
  }
  if (event.type != EventType::Order || event.order_appl_seq_num <= 0 ||
      (event.side != '1' && event.side != '2') ||
      (event.order_type != '1' && event.order_type != '2' && event.order_type != 'U')) {
    throw std::invalid_argument("invalid order type, side or reference");
  }
  if (event.price < 0 || (event.order_type == '2' && event.price == 0)) {
    throw std::invalid_argument("limit price must be positive; market price must be nonnegative");
  }
  if (session != TradingSession::OpeningAution && session != TradingSession::ClosingAuction &&
      session != TradingSession::ContinuousTrade) {
    throw std::invalid_argument("unsupported trading session");
  }
  if (session != TradingSession::ContinuousTrade && event.order_type != '2') {
    throw std::invalid_argument("auction order must be a limit order");
  }
  const OrderKey key(event.channel_no, event.order_appl_seq_num);
  if (order_price.find(key) != order_price.end()) {
    throw std::runtime_error("duplicate order reference");
  }

  // Keep the current function structure. Only levels are copied, not the entire
  // order registry or execution history; a failed new order can erase its key.
  PriceLevels previous_bids = bids;
  PriceLevels previous_asks = asks;
  const int64_t previous_quantity = cumulative_trade_quantity_num;
  const int64_t previous_turnover = cumulative_turnover_num;
  const bool previous_snapshot_flag = event.generate_snapshot;
  order_price.emplace(key, OrderInfo{event.price, event.side, event.quantity, 0});
  try {
    if (session == TradingSession::OpeningAution || session == TradingSession::ClosingAuction) {
      apply_order_in_acution(event);
      return;
    }
    if (session == TradingSession::ContinuousTrade) {
      if (event.order_type == '2') {
        apply_limit_order(event);
        return;
      }
      if (event.order_type == 'U') {
        apply_BBO_order(event);
        return;
      }
      if (event.order_type == '1') {
        apply_market_order(event);
        return;
      }
    }
  } catch (...) {
    bids.swap(previous_bids);
    asks.swap(previous_asks);
    order_price.erase(key);
    cumulative_trade_quantity_num = previous_quantity;
    cumulative_turnover_num = previous_turnover;
    event.generate_snapshot = previous_snapshot_flag;
    throw;
  }
}

void OrderBook::apply_market_order(Event& event) {
  int64_t remaining_quantity = event.quantity;

  int64_t best_price = 0;
  int64_t quantity_at_best = 0;

  if ((event.side == '1' && asks.empty()) || (event.side == '2' && bids.empty())) {
    throw std::runtime_error("market order has no opposite level; empty-book policy is unresolved");
  }
  if (event.side == '1') {
    const PriceLevel level = asks.best();
    best_price = level.price;
    quantity_at_best = level.quantity;
  } else {
    const PriceLevel level = bids.best();
    best_price = level.price;
    quantity_at_best = level.quantity;
  }

  // trade as normal
  if (quantity_at_best >= remaining_quantity) {
    if (event.side == '1') {

      const PriceLevel best_ask = asks.best();

      record_trade(best_price, remaining_quantity);

      asks.reduce(best_ask.price, remaining_quantity);

    } else {
      const PriceLevel best_bid = bids.best();

      record_trade(best_price, remaining_quantity);

      bids.reduce(best_bid.price, remaining_quantity);
    }
    return;
  }

  // quantity_at_best is not enough

  MarketOrderType market_order_type;

  const OrderTradeMap::const_iterator history =
      order_trade_map.find(OrderKey(event.channel_no, event.order_appl_seq_num));
  if (history == order_trade_map.end() || history->second.empty()) {
    throw std::runtime_error(
        "market order needs execution history when the best level is insufficient");
  }
  const std::vector<TradeInfo>& trades = history->second;

  // add to order book at best and wait for cancel
  if (trades.size() == 1 && trades[0].trade_type == TradeType::Cancel) {
    if ((event.side == '1' && bids.empty()) || (event.side == '2' && asks.empty())) {
      throw std::runtime_error("cancel-only market inference requires an own-side price");
    }
    event.generate_snapshot = false;

    if (event.side == '1') {

      int64_t price = bids.best().price;
      bids.add(price, event.quantity);
      order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = price;
    } else {
      int64_t price = asks.best().price;
      asks.add(price, event.quantity);
      order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = price;
    }
    return;
  }

  market_order_type = MarketOrderType::TradeAtBest;

  if (trades.size() != 1 && trades.back().trade_type == TradeType::Cancel) {
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
        const PriceLevel best_ask = asks.best();

        int64_t traded_quantity = std::min(remaining_quantity, best_ask.quantity);

        int64_t price = best_ask.price;
        record_trade(price, traded_quantity);

        remaining_quantity -= traded_quantity;

        asks.reduce(best_ask.price, traded_quantity);

        level_cnt++;
      }

      if (remaining_quantity > 0) {
        order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num))
            .pending_cancel_quantity = remaining_quantity;
      }
    } else {

      int64_t level_cnt = 0;
      while (remaining_quantity > 0 && !bids.empty() && level_cnt < 5) {
        const PriceLevel best_bid = bids.best();

        int64_t traded_quantity = std::min(remaining_quantity, best_bid.quantity);

        int64_t price = best_bid.price;

        record_trade(price, traded_quantity);

        remaining_quantity -= traded_quantity;

        bids.reduce(best_bid.price, traded_quantity);

        level_cnt++;
      }

      if (remaining_quantity > 0) {
        order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num))
            .pending_cancel_quantity = remaining_quantity;
      }
    }

    order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = 0;
    return;
  }

  // trade at fixed price
  if (market_order_type == MarketOrderType::TradeAtBest) {

    event.generate_snapshot = false;
    order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = best_price;

    remaining_quantity -= quantity_at_best;

    if (event.side == '1') {
      asks.reduce(best_price, quantity_at_best);
      bids.add(best_price, remaining_quantity);

      record_trade(best_price, quantity_at_best);
    } else {

      bids.reduce(best_price, quantity_at_best);
      asks.add(best_price, remaining_quantity);
      record_trade(best_price, quantity_at_best);
    }

    return;
  }

  // trade at slippage price

  if (event.side == '1') {
    while (remaining_quantity > 0 && !asks.empty()) {
      const PriceLevel best_ask = asks.best();

      int64_t traded_quantity = std::min(remaining_quantity, best_ask.quantity);

      record_trade(best_ask.price, traded_quantity);

      remaining_quantity -= traded_quantity;

      asks.reduce(best_ask.price, traded_quantity);
    }

    order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).pending_cancel_quantity =
        remaining_quantity;
    order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = 0;
    return;
  }

  while (remaining_quantity > 0 && !bids.empty()) {
    const PriceLevel best_bid = bids.best();

    int64_t traded_quantity = std::min(remaining_quantity, best_bid.quantity);

    record_trade(best_bid.price, traded_quantity);

    remaining_quantity -= traded_quantity;

    bids.reduce(best_bid.price, traded_quantity);
  }
  order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).pending_cancel_quantity =
      remaining_quantity;
  order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = 0;
}

void OrderBook::apply_BBO_order(Event& event) {
  if ((event.side == '1' && bids.empty()) || (event.side == '2' && asks.empty())) {
    throw std::runtime_error(
        "own-side-best order has no own-side level; cancellation policy is unresolved");
  }
  if (event.side == '1') {
    int64_t price = bids.best().price;
    bids.add(price, event.quantity);
    order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = price;
  } else {
    int64_t price = asks.best().price;
    asks.add(price, event.quantity);
    order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = price;
  }
}

void OrderBook::apply_order_in_acution(Event& event) {
  if (event.side == '1') {
    bids.add(event.price, event.quantity);

  } else {
    asks.add(event.price, event.quantity);
  }

  order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = event.price;
}

void OrderBook::apply_limit_order(Event& event) {
  int64_t remaining_quantity = event.quantity;

  order_price.at(OrderKey(event.channel_no, event.order_appl_seq_num)).price = event.price;

  // buy
  if (event.side == '1') {
    while (remaining_quantity > 0 && !asks.empty()) {
      const PriceLevel best_ask = asks.best();
      if (best_ask.price > event.price) {
        break;
      }

      int64_t traded_quantity = std::min(remaining_quantity, best_ask.quantity);

      record_trade(best_ask.price, traded_quantity);

      remaining_quantity -= traded_quantity;

      asks.reduce(best_ask.price, traded_quantity);
    }

    if (remaining_quantity > 0) {
      bids.add(event.price, remaining_quantity);
    }

    return;
  }

  // sell

  while (remaining_quantity > 0 && !bids.empty()) {

    const PriceLevel best_bid = bids.best();
    if (best_bid.price < event.price) {
      break;
    }

    int64_t traded_quantity = std::min(remaining_quantity, best_bid.quantity);

    record_trade(best_bid.price, traded_quantity);

    remaining_quantity -= traded_quantity;

    bids.reduce(best_bid.price, traded_quantity);
  }

  if (remaining_quantity > 0) {
    asks.add(event.price, remaining_quantity);
  }
}

void OrderBook::apply_cancel(Event& event) {
  if (event.order_appl_seq_num <= 0 || event.bid_appl_seq_num < 0 || event.offer_appl_seq_num < 0 ||
      ((event.bid_appl_seq_num == 0) == (event.offer_appl_seq_num == 0))) {
    throw std::invalid_argument("cancel requires exactly one positive side reference");
  }
  const int64_t referenced_id =
      event.bid_appl_seq_num != 0 ? event.bid_appl_seq_num : event.offer_appl_seq_num;
  if (referenced_id != event.order_appl_seq_num) {
    throw std::invalid_argument("cancel order id disagrees with its side reference");
  }
  OrderPriceMap::iterator order = order_price.find(OrderKey(event.channel_no, referenced_id));
  if (order == order_price.end()) {
    throw std::runtime_error("cancel references an unknown order");
  }
  OrderInfo& info = order->second;
  if ((event.bid_appl_seq_num != 0 && info.side != '1') ||
      (event.offer_appl_seq_num != 0 && info.side != '2')) {
    throw std::runtime_error("cancel reference side disagrees with original order");
  }
  if (event.quantity <= 0 || event.quantity > info.remaining_quantity) {
    throw std::runtime_error("cancel exceeds order remaining quantity or is not positive");
  }
  if (info.pending_cancel_quantity > 0) {
    if (event.quantity > info.pending_cancel_quantity) {
      throw std::runtime_error("cancel exceeds simulated pending remainder");
    }
    info.pending_cancel_quantity -= event.quantity;
    info.remaining_quantity -= event.quantity;
    return;
  }

  const int64_t price = info.price;
  if (info.side == '1') {
    if (bids.quantity_at(price) < event.quantity) {
      throw std::runtime_error("cancel buy level is missing or has insufficient quantity");
    }
    bids.reduce(price, event.quantity);
    info.remaining_quantity -= event.quantity;
    return;
  }

  if (asks.quantity_at(price) < event.quantity) {
    throw std::runtime_error("cancel sell level is missing or has insufficient quantity");
  }
  asks.reduce(price, event.quantity);
  info.remaining_quantity -= event.quantity;
}

void OrderBook::record_trade(int64_t price, int64_t quantity) {
  const int64_t next_quantity = checked_add(cumulative_trade_quantity_num, quantity);
  const int64_t trade_amount = checked_multiply(price, quantity);
  const int64_t next_turnover = checked_add(cumulative_turnover_num, trade_amount);
  cumulative_trade_quantity_num = next_quantity;
  cumulative_turnover_num = next_turnover;
}

void OrderBook::find_call_action_result(int64_t& auction_price, int64_t& trade_quantity,
                                        int64_t& remaining_quantity_at_price, char& side) {
  auction_price = 0;
  trade_quantity = 0;
  remaining_quantity_at_price = 0;
  side = '\0';
  std::vector<int64_t> prices;
  // 集合竞价筛选期间不修改盘口，一次读取两侧全量副本即可反复遍历。
  const std::vector<PriceLevel> bid_levels = bids.read_all();
  const std::vector<PriceLevel> ask_levels = asks.read_all();
  std::vector<PriceLevel>::const_iterator bid = bid_levels.begin();
  for (; bid != bid_levels.end(); ++bid) {
    prices.push_back(bid->price);
  }

  std::vector<PriceLevel>::const_iterator ask = ask_levels.begin();
  for (; ask != ask_levels.end(); ++ask) {
    prices.push_back(ask->price);
  }

  std::sort(prices.begin(), prices.end());
  prices.erase(std::unique(prices.begin(), prices.end()), prices.end());

  std::vector<AuctionCandidate> candidates;
  std::vector<int64_t>::iterator price = prices.begin();

  for (; price != prices.end(); ++price) {
    int64_t buy_quantity = 0;
    int64_t sell_quantity = 0;
    AuctionCandidate candidate;

    bid = bid_levels.begin();

    for (; bid != bid_levels.end(); ++bid) {
      if (bid->price >= *price) {
        buy_quantity = checked_add(buy_quantity, bid->quantity);
      }
    }

    ask = ask_levels.begin();

    for (; ask != ask_levels.end(); ++ask) {
      if (ask->price <= *price) {
        sell_quantity = checked_add(sell_quantity, ask->quantity);
      }
    }

    int64_t actual_trade = std::min(buy_quantity, sell_quantity);
    if (actual_trade == 0) {
      continue;
    }
    int64_t strictly_better_buy = buy_quantity;
    int64_t strictly_better_sell = sell_quantity;
    strictly_better_buy -= bids.quantity_at(*price);
    strictly_better_sell -= asks.quantity_at(*price);
    if (strictly_better_buy > actual_trade || strictly_better_sell > actual_trade) {
      continue;
    }

    candidate.price = *price;
    candidate.trade_quantity = actual_trade;
    candidate.remain_quantity_at_price =
        buy_quantity >= sell_quantity ? buy_quantity - sell_quantity : sell_quantity - buy_quantity;
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

  if (candidates.empty()) {
    return;
  }
  if (candidates.size() > 1 && candidates[0].trade_quantity == candidates[1].trade_quantity &&
      candidates[0].remain_quantity_at_price == candidates[1].remain_quantity_at_price) {
    throw std::runtime_error("auction price is ambiguous; a confirmed reference price is required");
  }
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
  if (trade_quantity == 0) {
    return;
  }
  // 先检查统计运算；之后按原规则扣量，reduce 不分配内存并统一删除空档。
  record_trade(auction_price, trade_quantity);

  int64_t bid_quantity_left = trade_quantity;
  while (!bids.empty() && bid_quantity_left > 0) {
    const PriceLevel bid = bids.best();
    if (bid.price < auction_price) {
      break;
    }
    const int64_t reduced = std::min(bid_quantity_left, bid.quantity);
    bids.reduce(bid.price, reduced);
    bid_quantity_left -= reduced;
  }

  int64_t ask_quantity_left = trade_quantity;
  while (!asks.empty() && ask_quantity_left > 0) {
    const PriceLevel ask = asks.best();
    if (ask.price > auction_price) {
      break;
    }
    const int64_t reduced = std::min(ask_quantity_left, ask.quantity);
    asks.reduce(ask.price, reduced);
    ask_quantity_left -= reduced;
  }
}

Snapshot OrderBook::make_snapshot(Event& event) {
  Snapshot snapshot = {};
  snapshot.caa = event.caa;
  snapshot.secid = event.secid;
  snapshot.sequence_no = event.sequence_no;
  snapshot.appl_seq_num = event.appl_seq_num;
  snapshot.transaction_time = event.transaction_time;
  snapshot.trade_count = source_trade_count;
  snapshot.cumulative_trade_quantity = source_trade_quantity;
  snapshot.cumulative_turnover = source_turnover;
  snapshot.last_trade_price = last_trade_price;
  snapshot.opening_price = opening_price;
  snapshot.event_type = event.type;

  // PriceLevels 负责最优到最差的顺序；快照层仍按原输出约定补足五档。
  snapshot.bids = bids.read_top(5);
  snapshot.asks = asks.read_top(5);
  const PriceLevel empty_level = {0, 0};
  snapshot.bids.resize(5, empty_level);
  snapshot.asks.resize(5, empty_level);

  snapshot.trading_session = event.trading_session;

  return snapshot;
}
