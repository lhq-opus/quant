#include "order_book.hpp"

#include "checked_math.hpp"

#include <stdexcept>
#include <vector>

OrderBook::OrderBook()
    : bids('1'), asks('2'), source_trade_count(0), source_trade_quantity(0), source_turnover(0),
      last_trade_price(0), opening_price(0) {}

void OrderBook::build_trade_map(const Event& event) {
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

  // 这里仅保存关联记录的类型和价格。即使看到了后续F，也不在这里提前扣量。
  TradeInfo trade_info = {};
  trade_info.trade_type = event.type == EventType::Cancel ? TradeType::Cancel : TradeType::Normal;
  trade_info.price = event.price;
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

void OrderBook::apply(const Event& event, TradingSession session) {
  if (event.quantity <= 0 || event.channel_no < 0) {
    throw std::invalid_argument("quantity must be positive and channel must be nonnegative");
  }

  // 开盘、连续交易、收盘使用同一条F扣量路径。
  // 集合竞价不再自行计算成交或在阶段末补扣一次，真实TradePrice就是该笔成交价。
  if (event.type == EventType::Trade) {
    apply_trade(event);
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
  if (order_price.find(OrderKey(event.channel_no, event.order_appl_seq_num)) != order_price.end()) {
    throw std::runtime_error("duplicate order reference");
  }
  add_order(event);
}

void OrderBook::add_order(const Event& event) {
  // 登记数量始终是完整原始量；挂价另行确定，不提前计算成交量或待撤量。
  OrderInfo info = {event.price, event.side, event.quantity};
  if (event.order_type == '1') {
    info.price = find_market_order_price(event);
  } else if (event.order_type == 'U') {
    if ((event.side == '1' && bids.empty()) || (event.side == '2' && asks.empty())) {
      throw std::runtime_error(
          "own-side-best order has no own-side level; cancellation policy is unresolved");
    }
    // U只在到达时取一次本方最优价。后来成交/撤单都按这个已保存的价格扣量。
    info.price = event.side == '1' ? bids.best().price : asks.best().price;
  }

  const OrderKey key(event.channel_no, event.order_appl_seq_num);
  order_price.emplace(key, info);
  try {
    if (info.price == 0) {
      // 不挂档不等于没有订单。后续F/4仍然按引用扣这张订单的剩余量。
      return;
    }
    if (info.side == '1') {
      bids.add(info.price, info.remaining_quantity);
    } else {
      asks.add(info.price, info.remaining_quantity);
    }
  } catch (...) {
    // add先完成加法检查才写单档；失败时仅移除新登记，不需要复制整个盘口。
    order_price.erase(key);
    throw;
  }
}

int64_t OrderBook::find_market_order_price(const Event& event) const {
  // 以下只保留原my_obr的挂价实验，不是从行情字段唯一确定的交易所市价子类型。
  // 原来的扫一档/五档/跨档循环全部删除；真实成交数量和档数只能由后续F决定。
  if ((event.side == '1' && asks.empty()) || (event.side == '2' && bids.empty())) {
    throw std::runtime_error("market order has no opposite level; empty-book policy is unresolved");
  }
  const PriceLevel opposite = event.side == '1' ? asks.best() : bids.best();
  if (opposite.quantity >= event.quantity) {
    // 原实验在这个分支不留下可见挂单；现在只登记原始量，等待真实F或4。
    return 0;
  }

  const OrderTradeMap::const_iterator history =
      order_trade_map.find(OrderKey(event.channel_no, event.order_appl_seq_num));
  if (history == order_trade_map.end() || history->second.empty()) {
    throw std::runtime_error(
        "market order needs execution history when the best level is insufficient");
  }
  const std::vector<TradeInfo>& trades = history->second;
  if (trades.size() == 1 && trades[0].trade_type == TradeType::Cancel) {
    if ((event.side == '1' && bids.empty()) || (event.side == '2' && asks.empty())) {
      throw std::runtime_error("cancel-only market inference requires an own-side price");
    }
    // 原“只有一条撤单”实验分支：暂挂到本方最优价，等真实4扣掉。
    return event.side == '1' ? bids.best().price : asks.best().price;
  }
  if (trades.size() > 1 && trades.back().trade_type == TradeType::Cancel) {
    // 原“最后是撤单”的实验分支不挂价。这里不推算余量，也不限制F最多成交五档。
    return 0;
  }
  for (std::size_t index = 0; index < trades.size(); ++index) {
    if (trades[index].price != opposite.price) {
      // 原跨价实验分支不挂本方档；对手盘口只能在处理相应F时扣减。
      return 0;
    }
  }
  // 原“同一最优价成交、余量留在该价”分支：先以该价登记完整量。
  // 此时不吃对手档；后续真实F扣掉已成交部分，剩余量自然留在本方档上。
  return opposite.price;
}

void OrderBook::apply_trade(const Event& event) {
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
  OrderInfo& bid = bid_order->second;
  OrderInfo& ask = ask_order->second;
  if (bid.side != '1' || ask.side != '2') {
    throw std::runtime_error("trade reference side does not match the original order");
  }
  if (event.quantity > bid.remaining_quantity || event.quantity > ask.remaining_quantity) {
    throw std::runtime_error("trade exceeds a referenced order's remaining quantity");
  }

  // 先检查两侧再扣量，不能先扣买方，检查卖方失败后留下半笔成交。
  if (bid.price != 0 && bids.quantity_at(bid.price) < event.quantity) {
    throw std::runtime_error("trade buy level is missing or has insufficient quantity");
  }
  if (ask.price != 0 && asks.quantity_at(ask.price) < event.quantity) {
    throw std::runtime_error("trade sell level is missing or has insufficient quantity");
  }
  const int64_t next_count = checked_add(source_trade_count, 1);
  const int64_t next_quantity = checked_add(source_trade_quantity, event.quantity);
  const int64_t trade_amount = checked_multiply(event.price, event.quantity);
  const int64_t next_turnover = checked_add(source_turnover, trade_amount);

  // 买卖原单可能挂在不同价格；从各自挂价扣量，绝不是统一从TradePrice这档扣。
  // price为0时没有可见档可扣，但下面的订单余量仍必须减少。
  if (bid.price != 0) {
    bids.reduce(bid.price, event.quantity);
  }
  if (ask.price != 0) {
    asks.reduce(ask.price, event.quantity);
  }
  bid.remaining_quantity -= event.quantity;
  ask.remaining_quantity -= event.quantity;

  // 同一笔F虽然扣双方，但成交笔数、成交量和金额都只累计一次。
  source_trade_count = next_count;
  source_trade_quantity = next_quantity;
  source_turnover = next_turnover;
  last_trade_price = event.price;
  if (opening_price == 0) {
    opening_price = event.price;
  }
}

void OrderBook::apply_cancel(const Event& event) {
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
  if (event.quantity > info.remaining_quantity) {
    throw std::runtime_error("cancel exceeds order remaining quantity");
  }

  // 撤单沿用已保存的挂价；不挂档的订单仅减少登记量，不能误扣其他订单的档位。
  if (info.price != 0) {
    if (info.side == '1') {
      if (bids.quantity_at(info.price) < event.quantity) {
        throw std::runtime_error("cancel buy level is missing or has insufficient quantity");
      }
      bids.reduce(info.price, event.quantity);
    } else {
      if (asks.quantity_at(info.price) < event.quantity) {
        throw std::runtime_error("cancel sell level is missing or has insufficient quantity");
      }
      asks.reduce(info.price, event.quantity);
    }
  }
  info.remaining_quantity -= event.quantity;
}

Snapshot OrderBook::make_snapshot(const Event& event) const {
  Snapshot snapshot = {};
  // 元数据使用区间起点order/4，盘口和统计使用拍照时已经重放完成的状态。
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

  // PriceLevels负责最优到最差的顺序；快照层按原输出约定补足五档。
  snapshot.bids = bids.read_top(5);
  snapshot.asks = asks.read_top(5);
  const PriceLevel empty_level = {0, 0};
  snapshot.bids.resize(5, empty_level);
  snapshot.asks.resize(5, empty_level);
  snapshot.trading_session = event.trading_session;
  return snapshot;
}
