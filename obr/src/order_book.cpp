#include "obr/order_book.hpp"

#include <algorithm>
#include <cassert>
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
  // 撤单在三个阶段中的处理方式相同：从已知价格档扣除 TradeQty。
  if (event.type == EventType::Cancel) {
    apply_cancel(event);
    return;
  }

  // 深交所逐笔行情只给出 OrderType=1/2/U，没有给出区分各种市价子类型所需的
  // TimeInForce、MaxPriceLevels 和 MinQty。为了保持当前 demo 简单、结果确定，约定：
  //   1 = 对手方最优，未成交部分按该价格转成限价单；
  //   2 = 普通限价单；
  //   U = 本方最优，直接加入本方当前最优档。
  // 市价申报只用于连续竞价，因此合法的集合竞价 order 仍然都是限价单。
  if (session == TradingSession::ContinuousAuction) {
    if (event.order_type == '1') {
      apply_opponent_best_order(event);
    } else if (event.order_type == 'U') {
      apply_own_best_order(event);
    } else {
      // 输入保证 OrderType 只有 1、2、U，所以最后一个分支就是 2。
      apply_limit_order(event, event.price);
    }
    return;
  }

  // 开盘和收盘集合竞价期间不逐笔撮合，只把订单累加到本方价格档。
  add_order(event);
}

void OrderBook::add_order(const Event& event) {
  if (event.side == '1') {
    // map 的 operator[] 在价格不存在时会先放入一个 0，然后再加数量。
    bids_[event.price] += event.quantity;
  } else {
    asks_[event.price] += event.quantity;
  }
}

void OrderBook::apply_opponent_best_order(const Event& event) {
  if (event.side == '1') {
    // 买单使用到达时的卖一作为限价。没有卖盘时，没有对手方最优价，申报自动撤销。
    if (asks_.empty()) {
      return;
    }
    apply_limit_order(event, asks_.begin()->first);
    return;
  }

  // 卖单与之对称：使用到达时的买一；没有买盘时自动撤销。
  if (bids_.empty()) {
    return;
  }
  apply_limit_order(event, bids_.begin()->first);
}

void OrderBook::apply_own_best_order(const Event& event) {
  if (event.side == '1') {
    // 买方最高价就是买一。若本方盘口为空，则不存在本方最优价，申报自动撤销。
    if (bids_.empty()) {
      return;
    }

    // U 的 CSV Price 在本 demo 中不参与定价，订单直接加入到达时的买一档。
    bids_[bids_.begin()->first] += event.quantity;
    return;
  }

  // 卖方最低价就是卖一，处理方式与买方完全对称。
  if (asks_.empty()) {
    return;
  }
  asks_[asks_.begin()->first] += event.quantity;
}

void OrderBook::apply_limit_order(const Event& event, Price limit_price) {
  Quantity remaining_quantity = event.quantity;

  if (event.side == '1') {
    // asks_ 默认按价格升序，因此 begin() 就是当前卖一。
    // 买单只要还有数量，并且卖一不高于买入限价，就继续逐档成交。
    while (remaining_quantity > 0 && !asks_.empty()) {
      AskLevels::iterator best_ask = asks_.begin();
      if (best_ask->first > limit_price) {
        break;
      }

      const Quantity traded_quantity = std::min(remaining_quantity, best_ask->second);
      record_trade(best_ask->first, traded_quantity);

      remaining_quantity -= traded_quantity;
      best_ask->second -= traded_quantity;
      if (best_ask->second == 0) {
        asks_.erase(best_ask);
      }
    }

    // 对手盘已经不能继续成交时，买单剩余数量进入自己的限价档。
    if (remaining_quantity > 0) {
      bids_[limit_price] += remaining_quantity;
    }
    return;
  }

  // bids_ 使用降序比较器，因此 begin() 就是当前买一。
  // 卖单从最高买价开始，只要买一不低于卖出限价，就继续逐档成交。
  while (remaining_quantity > 0 && !bids_.empty()) {
    BidLevels::iterator best_bid = bids_.begin();
    if (best_bid->first < limit_price) {
      break;
    }

    const Quantity traded_quantity = std::min(remaining_quantity, best_bid->second);
    record_trade(best_bid->first, traded_quantity);

    remaining_quantity -= traded_quantity;
    best_bid->second -= traded_quantity;
    if (best_bid->second == 0) {
      bids_.erase(best_bid);
    }
  }

  // 卖单没有完全成交时，剩余数量进入自己的限价档。
  if (remaining_quantity > 0) {
    asks_[limit_price] += remaining_quantity;
  }
}

void OrderBook::apply_cancel(const Event& event) {
  // 集合竞价期间同一个价格可以同时存在买卖申报，因此不能用价格推断撤单方向。
  // event.csv 已经从原订单补全 Side：'1' 撤买单，'2' 撤卖单。
  if (event.side == '1') {
    BidLevels::iterator bid = bids_.find(event.price);
    bid->second -= event.quantity;
    if (bid->second == 0) {
      bids_.erase(bid);
    }
    return;
  }

  // 第一版输入保证 Side、价格和数量合法，所以卖方分支直接修改对应卖盘价格档。
  AskLevels::iterator ask = asks_.find(event.price);
  ask->second -= event.quantity;
  if (ask->second == 0) {
    asks_.erase(ask);
  }
}

void OrderBook::record_trade(Price price, Quantity quantity) {
  cumulative_trade_quantity_ += quantity;
  cumulative_turnover_ += price * quantity;
}

bool OrderBook::find_call_auction_result(Price& auction_price, Quantity& trade_quantity) const {
  // 候选价格就是当前买卖申报价格的并集。
  std::vector<Price> prices;
  BidLevels::const_iterator bid = bids_.begin();
  for (; bid != bids_.end(); ++bid) {
    prices.push_back(bid->first);
  }
  AskLevels::const_iterator ask = asks_.begin();
  for (; ask != asks_.end(); ++ask) {
    prices.push_back(ask->first);
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
    candidate.quantity_difference = better_buy_quantity >= better_sell_quantity
                                        ? better_buy_quantity - better_sell_quantity
                                        : better_sell_quantity - better_buy_quantity;
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

  // 第二轮：如果最大成交量相同，选择严格高买量与严格低卖量差最小者。
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

  // 当前 demo 不使用 reference price，约定合法输入到这里一定只剩一个价格。
  assert(final_candidates.size() == 1U);
  auction_price = final_candidates[0].price;
  trade_quantity = maximum_trade_quantity;
  return true;
}

void OrderBook::finish_call_auction() {
  Price auction_price = 0;
  Quantity trade_quantity = 0;
  if (!find_call_auction_result(auction_price, trade_quantity)) {
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
