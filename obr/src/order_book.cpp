#include "obr/order_book.hpp"

#include <algorithm>
#include <vector>

namespace obr {
namespace {

// 集合竞价会先为每个申报价计算三个值，再逐层筛选。
// 这里直接用一个局部 struct 保存结果，比引入通用算法或模板更容易阅读。
struct AuctionCandidate {
  Price price;
  Quantity trade_quantity;
  Quantity quantity_difference;
};

} // namespace

OrderBook::OrderBook() : cumulative_trade_quantity_(0), cumulative_turnover_(0) {}

void OrderBook::apply(const Event& event, TradingSession session) {
  if (event.type == EventType::Order) {
    // 即使限价买单高于卖一，也只加本方数量，等待真实 F 指出成交双方与数量。
    add_order(event);
  } else if (event.type == EventType::Cancel) {
    // 撤单不需要自己携带价格和方向，两者都从原订单索引取得。
    reduce_order(OrderKey(event.channel_no, event.order_appl_seq_num), event.quantity);
  } else if (session == TradingSession::ContinuousAuction) {
    apply_trade(event);
  }
  // 集合竞价 F 不在这里扣量。原有阶段末统一定价/扣量逻辑保持不变，不能扣两遍。
}

void OrderBook::add_order(const Event& event) {
  OrderInfo order = {event.side, event.price};
  if (event.order_type == '1') {
    // 类型 1 暂沿用“不挂本方价档”的约定，但不再自行撮合或推断余量撤销。
    // 非零 Price 的供应商挂价语义尚未确认，不能仅凭是否填价改成限价处理。
    order.price = 0;
  } else if (event.order_type == 'U') {
    // U 只在到达时取一次本方最优价。以后即使最优档变化，成交/撤单仍找这个价格。
    // 本方为空时不存在可用挂价，记为 0；这是业务分支，不是非法输入检查。
    if (event.side == '1') {
      order.price = bids_.empty() ? 0 : bids_.begin()->first;
    } else {
      order.price = asks_.empty() ? 0 : asks_.begin()->first;
    }
  }
  orders_[OrderKey(event.channel_no, event.order_appl_seq_num)] = order;
  if (order.price == 0) {
    return;
  }
  if (event.side == '1') {
    // operator[] 在价格不存在时创建数量为 0 的档，再累加完整 OrderQty。
    bids_[order.price] += event.quantity;
  } else {
    asks_[order.price] += event.quantity;
  }
}

void OrderBook::apply_trade(const Event& event) {
  // 真实 trade 已经告诉我们成交双方，不再猜哪张单先成交、是否继续吃第二档。
  // 两侧原订单可以挂在不同价格；必须各找原挂价，不能都从 TradePrice 这一档扣量。
  reduce_order(OrderKey(event.channel_no, event.bid_appl_seq_num), event.quantity);
  reduce_order(OrderKey(event.channel_no, event.offer_appl_seq_num), event.quantity);

  // 买卖各扣一份数量，但这是同一笔成交，成交量和金额只累计一次。
  record_trade(event.price, event.quantity);
}

void OrderBook::reduce_order(const OrderKey& key, Quantity quantity) {
  const OrderInfo& order = orders_.find(key)->second;
  if (order.price == 0) {
    // 未挂入价格档的订单没有可见数量可扣，但 apply_trade 仍会处理另一侧与成交统计。
    return;
  }

  // 相同价格可能同时存在买卖档，方向来自原订单，而不是看哪一侧恰好存在这个价格。
  if (order.side == '1') {
    BidLevels::iterator bid = bids_.find(order.price);
    bid->second -= quantity;
    if (bid->second == 0) {
      bids_.erase(bid);
    }
    return;
  }

  AskLevels::iterator ask = asks_.find(order.price);
  ask->second -= quantity;
  if (ask->second == 0) {
    asks_.erase(ask);
  }
}

void OrderBook::record_trade(Price price, Quantity quantity) {
  cumulative_trade_quantity_ += quantity;
  cumulative_turnover_ += price * quantity;
}

bool OrderBook::find_call_auction_result(Price actual_price, Price& auction_price,
                                         Quantity& trade_quantity) const {
  // 当前买卖申报价构成候选集。真实集合成交价可能在两个申报价之间，也必须参与筛选。
  std::vector<Price> prices;
  BidLevels::const_iterator bid = bids_.begin();
  for (; bid != bids_.end(); ++bid) {
    prices.push_back(bid->first);
  }
  AskLevels::const_iterator ask = asks_.begin();
  for (; ask != asks_.end(); ++ask) {
    prices.push_back(ask->first);
  }
  if (actual_price > 0) {
    prices.push_back(actual_price);
  }

  std::sort(prices.begin(), prices.end());
  prices.erase(std::unique(prices.begin(), prices.end()), prices.end());

  std::vector<AuctionCandidate> candidates;
  std::vector<Price>::const_iterator price = prices.begin();
  for (; price != prices.end(); ++price) {
    Quantity buy_quantity = 0;
    bid = bids_.begin();
    for (; bid != bids_.end(); ++bid) {
      if (bid->first >= *price) {
        buy_quantity += bid->second;
      }
    }

    Quantity sell_quantity = 0;
    ask = asks_.begin();
    for (; ask != asks_.end(); ++ask) {
      if (ask->first <= *price) {
        sell_quantity += ask->second;
      }
    }

    const Quantity possible_trade = std::min(buy_quantity, sell_quantity);
    if (possible_trade == 0) {
      continue;
    }

    // 严格高于候选价的买单、严格低于候选价的卖单，都必须能够全部成交。
    Quantity better_buy_quantity = 0;
    bid = bids_.begin();
    for (; bid != bids_.end(); ++bid) {
      if (bid->first > *price) {
        better_buy_quantity += bid->second;
      }
    }

    Quantity better_sell_quantity = 0;
    ask = asks_.begin();
    for (; ask != asks_.end(); ++ask) {
      if (ask->first < *price) {
        better_sell_quantity += ask->second;
      }
    }

    if (better_buy_quantity > possible_trade || better_sell_quantity > possible_trade) {
      continue;
    }

    // 候选价上的买方或卖方至少要有一方全部成交。
    Quantity buy_at_price = 0;
    BidLevels::const_iterator same_bid = bids_.find(*price);
    if (same_bid != bids_.end()) {
      buy_at_price = same_bid->second;
    }

    Quantity sell_at_price = 0;
    AskLevels::const_iterator same_ask = asks_.find(*price);
    if (same_ask != asks_.end()) {
      sell_at_price = same_ask->second;
    }

    const bool all_buys_at_price_trade = better_buy_quantity + buy_at_price <= possible_trade;
    const bool all_sells_at_price_trade = better_sell_quantity + sell_at_price <= possible_trade;
    if (!all_buys_at_price_trade && !all_sells_at_price_trade) {
      continue;
    }

    AuctionCandidate candidate;
    candidate.price = *price;
    candidate.trade_quantity = possible_trade;
    // 次级筛选用“买价 >= 候选价”与“卖价 <= 候选价”的累计量之差，包含等价申报。
    // 上面的严格价优量只用于检查能否全部成交，不能代替这里的累计买卖量。
    candidate.quantity_difference =
        buy_quantity >= sell_quantity ? buy_quantity - sell_quantity : sell_quantity - buy_quantity;
    candidates.push_back(candidate);
  }

  if (candidates.empty()) {
    return false;
  }

  // 第一轮：只保留最大可成交量对应的候选价格。
  Quantity maximum_trade_quantity = 0;
  std::vector<AuctionCandidate>::const_iterator candidate = candidates.begin();
  for (; candidate != candidates.end(); ++candidate) {
    if (candidate->trade_quantity > maximum_trade_quantity) {
      maximum_trade_quantity = candidate->trade_quantity;
    }
  }

  std::vector<AuctionCandidate> maximum_candidates;
  candidate = candidates.begin();
  for (; candidate != candidates.end(); ++candidate) {
    if (candidate->trade_quantity == maximum_trade_quantity) {
      maximum_candidates.push_back(*candidate);
    }
  }

  // 第二轮：如果最大成交量相同，选择包含候选价的累计买卖量之差最小者。
  Quantity minimum_difference = maximum_candidates[0].quantity_difference;
  candidate = maximum_candidates.begin();
  for (; candidate != maximum_candidates.end(); ++candidate) {
    if (candidate->quantity_difference < minimum_difference) {
      minimum_difference = candidate->quantity_difference;
    }
  }

  std::vector<AuctionCandidate> final_candidates;
  candidate = maximum_candidates.begin();
  for (; candidate != maximum_candidates.end(); ++candidate) {
    if (candidate->quantity_difference == minimum_difference) {
      final_candidates.push_back(*candidate);
    }
  }

  trade_quantity = maximum_trade_quantity;
  if (final_candidates.size() == 1U) {
    auction_price = final_candidates[0].price;
    return true;
  }

  // 本 demo 不另加前收盘价/最近成交价的参考价格规则，直接用上游真实成交价解开并列。
  // trade 只提供统一价格，不再次扣量，避免与下面的档级撮合重复计算。
  // 输入保证并列时提供的真实成交价有效，无需再查候选列表或处理异常。
  auction_price = actual_price;
  return true;
}

void OrderBook::finish_call_auction(Price actual_price) {
  Price auction_price = 0;
  Quantity trade_quantity = 0;
  if (!find_call_auction_result(actual_price, auction_price, trade_quantity)) {
    return;
  }

  // 买方从最高价向下扣减所有不低于集合竞价成交价的数量。
  Quantity bid_quantity_left = trade_quantity;
  BidLevels::iterator bid = bids_.begin();
  while (bid != bids_.end() && bid_quantity_left > 0 && bid->first >= auction_price) {
    const Quantity reduced = std::min(bid_quantity_left, bid->second);
    bid->second -= reduced;
    bid_quantity_left -= reduced;

    if (bid->second == 0) {
      BidLevels::iterator empty_level = bid;
      ++bid;
      bids_.erase(empty_level);
    } else {
      ++bid;
    }
  }

  // 卖方从最低价向上扣减所有不高于集合竞价成交价的数量。
  Quantity ask_quantity_left = trade_quantity;
  AskLevels::iterator ask = asks_.begin();
  while (ask != asks_.end() && ask_quantity_left > 0 && ask->first <= auction_price) {
    const Quantity reduced = std::min(ask_quantity_left, ask->second);
    ask->second -= reduced;
    ask_quantity_left -= reduced;

    if (ask->second == 0) {
      AskLevels::iterator empty_level = ask;
      ++ask;
      asks_.erase(empty_level);
    } else {
      ++ask;
    }
  }

  // 集合竞价双方成交数量相同，并且全部使用同一个 auction_price 计算成交额。
  record_trade(auction_price, trade_quantity);
}

Snapshot OrderBook::make_snapshot(const Event& event) const {
  Snapshot snapshot;
  snapshot.caa = event.caa;
  snapshot.event_type = event.type;

  // bids_ 本来就是降序，直接取前五个元素就是买一到买五。
  BidLevels::const_iterator bid = bids_.begin();
  for (; bid != bids_.end() && snapshot.bids.size() < 5U; ++bid) {
    PriceLevel level = {bid->first, bid->second};
    snapshot.bids.push_back(level);
  }

  // asks_ 本来就是升序，直接取前五个元素就是卖一到卖五。
  AskLevels::const_iterator ask = asks_.begin();
  for (; ask != asks_.end() && snapshot.asks.size() < 5U; ++ask) {
    PriceLevel level = {ask->first, ask->second};
    snapshot.asks.push_back(level);
  }

  return snapshot;
}

Quantity OrderBook::cumulative_trade_quantity() const { return cumulative_trade_quantity_; }

Turnover OrderBook::cumulative_turnover() const { return cumulative_turnover_; }

} // namespace obr
