#include "order_book.hpp"

#include <algorithm>

// 所有计数和等待状态从空簿开始；竞价不推演撮合，直接接受其真实成交。
OrderBook::OrderBook()
    : trading_session(TradingSession::OpeningAution), next_arrival_rank(0),
      cumulative_trade_quantity(0), cumulative_turnover(0), trade_count(0), last_trade_price(0),
      opening_price(0), pending_limit_order_appl_seq(0), pending_limit_trade_quantity(0),
      pending_cyb_event_group(false), pending_market_order(), pending_market_order_appl_seq(0),
      pending_market_order_quantity(0), pending_market_last_price(0) {}

// 同一来单的相关 F 紧随来单，下一张委托/撤单是事件组边界。
// 先完成旧组，防止旧组的成交统计或市价余量污染新事件的快照元信息。
void OrderBook::apply(Order& order) {
  finish_event_group();
  trading_session = order.trading_session;
  activate_cyb_orders();
  order_arrival_rank[order.order_appl_seq_num] = next_arrival_rank++;
  if (order.order_type == OrderType::Market) {
    market_order_ids.insert(std::make_pair(order.channel_no, order.order_appl_seq_num));
  }

  if (trading_session != TradingSession::ContinuousTrade) {
    apply_order_in_acution(order);
    return;
  }

  // 存在暂存委托时，盘口变化还可能触发这些委托的成交。该组统一使用真实
  // F 的订单引用扣量，不将限价推演与暂存单激活混用。
  pending_cyb_event_group = !pending_limit_order_alive.empty();
  if (order.order_type == OrderType::Limit) {
    apply_limit_order(order);
  } else if (order.order_type == OrderType::BBO) {
    apply_BBO_order(order);
  } else {
    apply_market_order(order);
  }
  activate_cyb_orders();
  make_snapshot(order);

  // 普通未撮合限价单已经有确定结果，可以直接写出；撮合限价等真实 F
  // 确认预计成交量，市价和涉及创业板暂存单的组另有收尾时机。
  if (pending_market_order_appl_seq == 0 && pending_limit_trade_quantity == 0 &&
      !pending_cyb_event_group) {
    complete_previous_snapshot();
  }
}

void OrderBook::apply(Trade& trade) {
  if (trade.trading_session != trading_session) {
    finish_event_group();
    trading_session = trade.trading_session;
    activate_cyb_orders();
  }

  if (trade.trade_type == TradeType::Cancel) {
    const bool cyb_affected = !pending_limit_order_alive.empty();
    if (is_pending_market_trade(trade)) {
      // 撤销量先从未展示市价余量扣除，再结束市价组。撤单价格不参与
      // 市价余量定价，避免零撤单价覆盖最后一次真实成交价格。
      apply_cancel(trade);
      finish_pending_market_order(true);
      finish_event_group();
    } else {
      finish_event_group();
      apply_cancel(trade);
    }
    pending_cyb_event_group = cyb_affected || !pending_limit_order_alive.empty();
    activate_cyb_orders();
    make_snapshot(trade);
    if (!pending_cyb_event_group) {
      complete_previous_snapshot();
    }
    return;
  }

  if (trading_session != TradingSession::ContinuousTrade) {
    // 开盘和收盘竞价均直接按每条 F 的双方原单引用扣量。阶段结束时
    // 无需再按全日累计成交量扣盘，EOF 也不需要额外推算竞价成交价。
    execute_trade(trade);
    record_trade(trade);
    return;
  }

  // 市价尚有余量却遇到不相关 F，说明它自己的成交段已经结束；
  // 先把余量按该市价单最后成交价入簿，供后续真实 F 引用。
  if (pending_market_order_appl_seq != 0 && pending_market_order_quantity > 0 &&
      !is_pending_market_trade(trade)) {
    finish_pending_market_order();
  }

  const bool market_trade = is_pending_market_trade(trade);
  const bool simulated_limit_trade = pending_limit_trade_quantity > 0 &&
                                     (trade.bid_appl_seq_num == pending_limit_order_appl_seq ||
                                      trade.offer_appl_seq_num == pending_limit_order_appl_seq);

  if (simulated_limit_trade) {
    // 限价来单已提前扣完盘口，F 在这里仅确认数量，不重复执行。
    // 来单余量由 apply_limit_order 计算并入簿，确认余量单独保存在成员中。
    pending_limit_trade_quantity -= trade.quantity;
  } else {
    execute_trade(trade);
  }

  record_trade(trade);
  if (market_trade) {
    pending_market_last_price = trade.price;
  }
  activate_cyb_orders();
  update_previous_snapshot();

  if (market_trade && pending_market_order_quantity == 0 && !pending_cyb_event_group) {
    finish_pending_market_order();
  } else if (simulated_limit_trade && pending_limit_trade_quantity == 0 &&
             !pending_cyb_event_group) {
    // 完成量确认即可输出，不必再等下一条委托或文件结束。
    complete_previous_snapshot();
    pending_limit_order_appl_seq = 0;
  }
}

// 入簿统一维护链表、档位汇总与 position 索引。暂存单恢复时使用原始
// 到达次序插入同价链表，不能简单放到后来同价委托的队尾。
void OrderBook::add_resting_order(const Order& order) {
  BookLevel& level = order.side == EventSide::Buy ? bids[order.price] : asks[order.price];
  OrderQueue::iterator position = level.orders.end();
  const int64_t rank = order_arrival_rank.find(order.order_appl_seq_num)->second;
  // 从队尾向前查找：普通新单直接追加，只有较早的暂存单恢复时才需回退。
  while (position != level.orders.begin()) {
    OrderQueue::iterator previous = position;
    --previous;
    if (order_arrival_rank.find(previous->order_appl_seq_num)->second < rank) {
      break;
    }
    position = previous;
  }
  position = level.orders.insert(position, RestingOrder{order.order_appl_seq_num, order.quantity});
  level.total_quantity += order.quantity;
  order_info_map[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position};
}

void OrderBook::apply_order_in_acution(Order& order) { add_resting_order(order); }

// 本方最优委托以当前本方最优价转为限价处理；合法输入中的这类委托
// 已有可引用的本方档位，沿用 v2 的价格确定方式。
void OrderBook::apply_BBO_order(Order& order) {
  Order limit_order = order;
  limit_order.price = order.side == EventSide::Buy ? bids.begin()->first : asks.begin()->first;
  apply_limit_order(limit_order);
}

void OrderBook::apply_limit_order(Order& order) {
  if (is_outside_cyb_range(order)) {
    pending_limit_order_alive[order.order_appl_seq_num] = order;
    pending_cyb_event_group = true;
    return;
  }

  if (pending_cyb_event_group) {
    // 暂存单参与时按真实 F 逐单执行；来单全量先登记，不能提前消耗
    // 对手订单，否则后续暂存单触发的 F 会再次扣掉同一份数量。
    add_resting_order(order);
    return;
  }

  int64_t remaining_quantity = order.quantity;
  if (order.side == EventSide::Buy) {
    while (remaining_quantity > 0 && !asks.empty() && asks.begin()->first <= order.price) {
      const int64_t quantity = std::min(remaining_quantity, asks.begin()->second.total_quantity);
      execute_order_at_price(quantity, false, true);
      remaining_quantity -= quantity;
    }
  } else {
    while (remaining_quantity > 0 && !bids.empty() && bids.begin()->first >= order.price) {
      const int64_t quantity = std::min(remaining_quantity, bids.begin()->second.total_quantity);
      execute_order_at_price(quantity, true, false);
      remaining_quantity -= quantity;
    }
  }

  pending_limit_order_appl_seq = order.order_appl_seq_num;
  pending_limit_trade_quantity = order.quantity - remaining_quantity;
  if (remaining_quantity > 0) {
    Order remaining_order = order;
    remaining_order.quantity = remaining_quantity;
    add_resting_order(remaining_order);
  } else {
    order_arrival_rank.erase(order.order_appl_seq_num);
  }
}

// 撤单合法地只有一侧引用；委托余量、档位删除与索引清理由统一扣量函数完成。
void OrderBook::apply_cancel(const Trade& trade) {
  const int64_t order_id =
      trade.bid_appl_seq_num != 0 ? trade.bid_appl_seq_num : trade.offer_appl_seq_num;
  consume_order(order_id, trade.quantity);
}

void OrderBook::consume_order(int64_t order_id, int64_t quantity) {
  if (order_id == pending_market_order_appl_seq) {
    pending_market_order_quantity -= quantity;
    return;
  }

  std::map<int64_t, Order>::iterator held = pending_limit_order_alive.find(order_id);
  if (held != pending_limit_order_alive.end()) {
    // 暂存单尚无可见档位。部分成交/撤单必须保留未消耗部分。
    held->second.quantity -= quantity;
    if (held->second.quantity == 0) {
      pending_limit_order_alive.erase(held);
      order_arrival_rank.erase(order_id);
    }
    return;
  }

  std::map<int64_t, OrderInfo>::iterator info = order_info_map.find(order_id);
  const int64_t price = info->second.price;
  const EventSide side = info->second.side;
  OrderQueue::iterator position = info->second.position;
  BookLevel& level = side == EventSide::Buy ? bids.find(price)->second : asks.find(price)->second;
  position->remaining_quantity -= quantity;
  level.total_quantity -= quantity;
  if (position->remaining_quantity == 0) {
    level.orders.erase(position);
    order_info_map.erase(info);
    order_arrival_rank.erase(order_id);
  }
  if (level.orders.empty()) {
    // 使用原单的 side 删除对应容器，卖单成交不能误删 bids 的迭代器。
    if (side == EventSide::Buy) {
      bids.erase(price);
    } else {
      asks.erase(price);
    }
  }
}

// 真实 F 总是同时消耗买卖原单，但任一侧可能在市价等待区或创业板暂存区，
// 因而不一定同时改变可见 bids、asks。真实成交只在 apply 中统一计数一次。
void OrderBook::execute_trade(const Trade& trade) {
  consume_order(trade.bid_appl_seq_num, trade.quantity);
  consume_order(trade.offer_appl_seq_num, trade.quantity);
}

// 同一档的 quantity 可能覆盖多个 FIFO 订单，循环用于跨订单扣完这个确定量。
// 调用方已经将 quantity 限制在当前档位总量内，来单余量由调用方直接减去
// quantity；这里没有未成交余量需要返回，也不把推演视作新的真实成交。
void OrderBook::execute_order_at_price(int64_t quantity, bool reduce_bids, bool reduce_asks) {
  int64_t remaining_quantity = quantity;
  while (remaining_quantity > 0) {
    int64_t executed_quantity = remaining_quantity;
    if (reduce_bids) {
      executed_quantity =
          std::min(executed_quantity, bids.begin()->second.orders.front().remaining_quantity);
    }
    if (reduce_asks) {
      executed_quantity =
          std::min(executed_quantity, asks.begin()->second.orders.front().remaining_quantity);
    }
    if (reduce_bids) {
      consume_order(bids.begin()->second.orders.front().order_appl_seq_num, executed_quantity);
    }
    if (reduce_asks) {
      consume_order(asks.begin()->second.orders.front().order_appl_seq_num, executed_quantity);
    }
    remaining_quantity -= executed_quantity;
  }
}

// 真实 F 是成交统计的唯一来源。竞价不额外合成成交，撤单不会到达这里。
// 价格为 1/10000 元整数，金额沿用同一精度乘以成交数量。
void OrderBook::record_trade(const Trade& trade) {
  ++trade_count;
  cumulative_trade_quantity += trade.quantity;
  cumulative_turnover += trade.price * trade.quantity;
  last_trade_price = trade.price;
  if (trade.trading_session == TradingSession::OpeningAution) {
    opening_price = trade.price;
  }
}

void OrderBook::finish_event_group() {
  finish_pending_market_order();
  activate_cyb_orders();
  complete_previous_snapshot();
  pending_limit_order_appl_seq = 0;
  pending_limit_trade_quantity = 0;
  pending_cyb_event_group = false;
}

// EOF 与正常事件组边界使用同一收尾路径，处理尾部市价余量与待确认快照。
void OrderBook::finish() { finish_event_group(); }
