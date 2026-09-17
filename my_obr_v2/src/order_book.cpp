#include "order_book.hpp"

#include <algorithm>
#include <vector>

// 输入引用和数值合法，但业务阶段必须显式初始化，首条订单才能安全判断边界。
OrderBook::OrderBook()
    : trading_session(TradingSession::OpeningAution), cumulative_trade_quantity(0),
      cumulative_turnover(0) {}

void OrderBook::apply(Order& order) {
  // 保留原有顺序：结算上一段竞价，回放上一张市价单，再回放创业板事件组。
  // 旧快照必须在处理新来单之前完成，不能混入新来单的盘口或元信息。
  finish_call_auction();
  handle_pending_market_order(order);
  handle_pending_CYB_limit_order(order);
  pending_cyb_group = false;
  update_previous_snapshot();

  trading_session = order.trading_session;
  if (trading_session != TradingSession::ContinuousTrade) {
    // 收盘竞价不沿用连续竞价价格笼子，把仍暂存的余量恢复到竞价簿。
    replay_CYB_trades(std::vector<Trade>());
  }
  order_arrival_rank[order.order_appl_seq_num] = next_arrival_rank++;

  if (trading_session != TradingSession::ContinuousTrade) {
    apply_order_in_acution(order);
    return;
  }

  // 新限价与它解冻的同向单都直接撮合，量额/最新价立即更新。
  // 真实 F 的笔数在下一 Order/Cancel 前收齐，沿用组标志保持当前快照待完成。
  pending_cyb_group = true;
  if (order.order_type == OrderType::Limit) {
    apply_limit_order(order);
  } else if (order.order_type == OrderType::BBO) {
    apply_BBO_order(order);
  } else {
    apply_market_order(order);
  }
  // 限价入口已完成当前单及连续解冻单的撮合，这里直接记录整组快照。
  make_snapshot(order);
}

void OrderBook::apply(Trade& trade) {
  if (trade.trading_session != trading_session) {
    // 阶段变化也可能由 Trade 触发，不能只在 Order 入口收尾。
    finish();
    trading_session = trade.trading_session;
    replay_CYB_trades(std::vector<Trade>());
  }

  if (trade.trade_type == TradeType::Cancel) {
    finish_call_auction();
    const bool market_cancel = pending_market_order_appl_seq != 0 &&
                               (trade.bid_appl_seq_num == pending_market_order_appl_seq ||
                                trade.offer_appl_seq_num == pending_market_order_appl_seq);

    // 市价相关撤单已在它自己的回放中扣量，外层不能再扣第二次。
    // CYB 缓存可能包含由当前撤单触发、却先收到的 F；回放时区分其快照归属。
    handle_pending_market_order(trade);
    handle_pending_CYB_limit_order(trade);
    pending_cyb_group = false;
    if (!replay_caused_by_cancel) {
      update_previous_snapshot();
    }
    if (!market_cancel) {
      apply_cancel(trade);
    }

    // 撤单触发的 F 已在撤单之前收到；扣完撤量、恢复余量后即可完成该行。
    replay_CYB_trades(std::vector<Trade>());
    if (replay_caused_by_cancel) {
      // 普通 F 的输出标记为 false，这里沿用撤单的输出开关，元信息取首笔 F。
      // 这一行包含整组成交及撤单后的盘口，不再另外生成一条 cancel 行。
      cyb_first_trade.generate_snapshot = trade.generate_snapshot;
      make_snapshot(cyb_first_trade);
    } else {
      make_snapshot(trade);
    }
    replay_caused_by_cancel = false;
    return;
  }

  if (trading_session != TradingSession::ContinuousTrade) {
    // 竞价价量来自本阶段真实 F；统计立即累计，盘口在原竞价结算方法中扣一次。
    auction_trade_quantity += trade.quantity;
    auction_trade_price = trade.price;
    if (trading_session == TradingSession::OpeningAution) {
      opening_price = trade.price;
    }
    record_trade(trade.price, trade.quantity);
    return;
  }

  // 市价之后出现不相关 F 时，先结束市价自己的成交段，使其有价余量可被后续引用。
  // 此时也完成由市价解冻的旧单撮合；随后这些旧单的真实 F 只需补笔数。
  if (pending_market_order_appl_seq != 0 &&
      trade.bid_appl_seq_num != pending_market_order_appl_seq &&
      trade.offer_appl_seq_num != pending_market_order_appl_seq) {
    replay_pending_market_order(pending_market_order_trades);
  }

  const bool market_trade = pending_market_order_appl_seq != 0 &&
                            (trade.bid_appl_seq_num == pending_market_order_appl_seq ||
                             trade.offer_appl_seq_num == pending_market_order_appl_seq);
  if (market_trade) {
    // 市价仍按真实 F 定价和统计，相关 F 只进入市价缓存。
    record_trade(trade.price, trade.quantity);
    handle_pending_market_order(trade);
  } else if (trade.is_CYB) {
    // 已提前撮合的限价 F 只补笔数，仍暂存的原单则需要按真实 F 扣量。
    // CYB 缓存保留到组边界，以便把撤单触发的特殊组分给首笔 F 的快照。
    handle_pending_CYB_limit_order(trade);
  } else {
    // 非创业板限价已在来单时完成扣盘和量额统计，不能再次访问已全成的原单。
    ++trade_count;
  }
  update_previous_snapshot();
}

void OrderBook::apply_market_order(Order& order) {
  pending_market_order_appl_seq = order.order_appl_seq_num;
  pending_market_order_quantity = order.quantity;
  pending_market_trade_quantity = 0;
  pending_market_last_price = 0;
  pending_market_has_cancel = false;
  pending_market_has_snapshot = order.generate_snapshot;
  pending_market_order_trades.clear();
  // 未定价市价单不进入链表；按等待状态分流后才能决定扣独立余量还是 position。
  order_info_map[order.order_appl_seq_num] =
      OrderInfo{DROP_SIGNAL, order.side, OrderQueue::iterator(), 0};
}

void OrderBook::apply_BBO_order(Order& order) {
  // 本方为空时无法确定本方最优价，订单不会进入盘口，但后续仍会收到自动撤单。
  // 保留未入簿原单及待撤数量，让 apply_cancel 消耗这一业务状态；提前丢掉索引
  // 会使合法撤单查到 end，随后把无效 position 当成链表节点访问。
  // 当前事件仍可输出未改变的盘口；有本方档位时沿用原来的转限价处理。
  if ((order.side == EventSide::Buy && bids.empty()) ||
      (order.side == EventSide::Sell && asks.empty())) {
    order_info_map[order.order_appl_seq_num] =
        OrderInfo{DROP_SIGNAL, order.side, OrderQueue::iterator(), order.quantity};
    return;
  }
  Order limit_order = order;
  limit_order.price = order.side == EventSide::Buy ? bids.begin()->first : asks.begin()->first;
  apply_limit_order(limit_order);
}

void OrderBook::apply_order_in_acution(Order& order) {
  // 保留原方法名和“只入簿、不撮合”的职责；市价余量和 CYB 恢复也复用它，
  // 确保档位 key、索引 price 和 position 指向的链表始终一致。
  BookLevel& level = order.side == EventSide::Buy ? bids[order.price] : asks[order.price];
  OrderQueue::iterator position = level.orders.end();
  const int64_t rank = order_arrival_rank.find(order.order_appl_seq_num)->second;
  // 普通新单直接追加；较早暂存单恢复时，从队尾回退到原始同价 FIFO 位置。
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
  order_info_map[order.order_appl_seq_num] = OrderInfo{order.price, order.side, position, 0};
}

void OrderBook::apply_limit_order(Order& order) {
  // 每轮处理一张原单：先完成当前单，再检查它是否解冻了其他单。
  // 用局部副本切换下一张原单，既不改外层生成快照使用的输入事件，也不递归增长调用栈。
  Order current_order = order;
  while (true) {
    // 保留用户 v2 的对手最优价 102%/98% 范围；对手为空时不暂存。
    const bool outside = current_order.is_CYB &&
                         ((current_order.side == EventSide::Buy && !asks.empty() &&
                           current_order.price * 100 > asks.begin()->first * BID_COEFFICIENT) ||
                          (current_order.side == EventSide::Sell && !bids.empty() &&
                           current_order.price * 100 < bids.begin()->first * ASK_COEFFICIENT));
    if (outside) {
      pending_limit_order_alive[current_order.order_appl_seq_num] = current_order;
      order_info_map[current_order.order_appl_seq_num] =
          OrderInfo{current_order.price, current_order.side, OrderQueue::iterator(), 0};
      pending_cyb_group = true;
    } else {
      // 本单必须先完成自身全部撮合及余量入簿，才轮到由它解冻的旧单。
      // 所有轮次的量额和最新价归同一快照，已提前撮合部分的真实 F 只补笔数。
      int64_t remaining_quantity = current_order.quantity;
      if (current_order.side == EventSide::Buy) {
        while (remaining_quantity > 0 && !asks.empty() &&
               asks.begin()->first <= current_order.price) {
          const int64_t quantity =
              std::min(remaining_quantity, asks.begin()->second.total_quantity);
          execute_order_at_price(asks.begin()->first, quantity, false, true);
          remaining_quantity -= quantity;
        }
      } else {
        while (remaining_quantity > 0 && !bids.empty() &&
               bids.begin()->first >= current_order.price) {
          const int64_t quantity =
              std::min(remaining_quantity, bids.begin()->second.total_quantity);
          execute_order_at_price(bids.begin()->first, quantity, true, false);
          remaining_quantity -= quantity;
        }
      }

      if (remaining_quantity > 0) {
        Order remaining_order = current_order;
        remaining_order.quantity = remaining_quantity;
        apply_order_in_acution(remaining_order);
      } else {
        // 全成来单没有链表节点，后续真实 F 不再通过其 position 扣量。
        order_arrival_rank.erase(current_order.order_appl_seq_num);
      }
    }

    // 每轮重新读取最新盘口，收集此刻能够解冻的原单；没有合格单即结束。
    // 这里始终是连续竞价入口，竞价阶段的暂存恢复仍由回放入口只入簿处理。
    std::vector<int64_t> activated;
    for (std::map<int64_t, Order>::const_iterator held = pending_limit_order_alive.begin();
         held != pending_limit_order_alive.end(); ++held) {
      const Order& frozen_order = held->second;
      const bool still_frozen =
          (frozen_order.side == EventSide::Buy && !asks.empty() &&
           frozen_order.price * 100 > asks.begin()->first * BID_COEFFICIENT) ||
          (frozen_order.side == EventSide::Sell && !bids.empty() &&
           frozen_order.price * 100 < bids.begin()->first * ASK_COEFFICIENT);
      if (!still_frozen) {
        activated.push_back(held->first);
      }
    }
    if (activated.empty()) {
      break;
    }
    // 沿用原来的方向、价格及同价到达优先级；本轮只取第一张。
    // 它完成后可能再解冻价格更优的旧单，因此不能一次处理完本轮收集的整批订单。
    std::sort(activated.begin(), activated.end(), [this](int64_t left_id, int64_t right_id) {
      const Order& left = pending_limit_order_alive.find(left_id)->second;
      const Order& right = pending_limit_order_alive.find(right_id)->second;
      if (left.side != right.side) {
        return left.side == EventSide::Buy;
      }
      if (left.price != right.price) {
        return left.side == EventSide::Buy ? left.price > right.price : left.price < right.price;
      }
      return order_arrival_rank.find(left_id)->second < order_arrival_rank.find(right_id)->second;
    });

    std::map<int64_t, Order>::iterator held = pending_limit_order_alive.find(activated.front());
    // 先复制待解冻原单，再删除暂存项及没有节点的占位索引；保留原到达顺序。
    // 下一轮直接复用上面的撮合逻辑，负责全成清理或为剩余量建立有效 position。
    current_order = held->second;
    pending_limit_order_alive.erase(held);
    order_info_map.erase(current_order.order_appl_seq_num);
  }
}

void OrderBook::apply_cancel(Trade& trade) {
  const int64_t order_id =
      trade.bid_appl_seq_num != 0 ? trade.bid_appl_seq_num : trade.offer_appl_seq_num;
  if (order_id == pending_market_order_appl_seq) {
    pending_market_order_quantity -= trade.quantity;
    return;
  }

  std::map<int64_t, Order>::iterator held = pending_limit_order_alive.find(order_id);
  if (held != pending_limit_order_alive.end()) {
    // 暂存单没有链表节点，部分撤单/成交只扣独立余量；撤完才删除暂存和索引。
    held->second.quantity -= trade.quantity;
    if (held->second.quantity == 0) {
      pending_limit_order_alive.erase(held);
      order_info_map.erase(order_id);
      order_arrival_rank.erase(order_id);
    }
    return;
  }

  std::map<int64_t, OrderInfo>::iterator info = order_info_map.find(order_id);
  if (info->second.price == DROP_SIGNAL) {
    // 已结束成交组且无 F 的市价余量，按当前前提后续只会撤销；空本方 U 单也只待撤。
    // 两者都没有链表节点，按记录的未定价数量扣除，不能访问默认 position。
    // 部分撤销保留余量，全部撤销才清理索引；U 单不会因后来出现本方报价而重新入簿。
    info->second.unpriced_quantity -= trade.quantity;
    if (info->second.unpriced_quantity == 0) {
      order_info_map.erase(info);
      order_arrival_rank.erase(order_id);
    }
    return;
  }

  const int64_t price = info->second.price;
  const EventSide side = info->second.side;
  OrderQueue::iterator position = info->second.position;
  BookLevel& level = side == EventSide::Buy ? bids.find(price)->second : asks.find(price)->second;
  position->remaining_quantity -= trade.quantity;
  level.total_quantity -= trade.quantity;
  if (position->remaining_quantity == 0) {
    level.orders.erase(position);
    order_info_map.erase(info);
    order_arrival_rank.erase(order_id);
  }
  if (level.orders.empty()) {
    // side 属于被消耗原单；对手是买单就删 bids，不能把 bids 的迭代器交给 asks。
    if (side == EventSide::Buy) {
      bids.erase(price);
    } else {
      asks.erase(price);
    }
  }
}

void OrderBook::execute_trade(Trade& trade) {
  // 补全原来已有的接口。复用现有 apply_cancel 的按原单扣量职责，每边扣同一成交量，
  // 其中市价、暂存和可见订单各自分流；这里不生成撤单快照，也不改变成交统计。
  const int64_t order_ids[2] = {trade.bid_appl_seq_num, trade.offer_appl_seq_num};
  for (int index = 0; index < 2; ++index) {
    const int64_t order_id = order_ids[index];
    Trade consumed = trade;
    consumed.bid_appl_seq_num = index == 0 ? order_id : 0;
    consumed.offer_appl_seq_num = index == 1 ? order_id : 0;
    apply_cancel(consumed);
  }
}

void OrderBook::record_trade(int64_t price, int64_t quantity) {
  // 仅用于尚未提前统计的真实 F：市价、竞价、仍暂存原单及撤单触发的特殊组。
  // 已提前撮合的限价/解冻单量额已累计，其真实 F 只补笔数，不能重复调用这里。
  ++trade_count;
  last_trade_price = price;
  cumulative_trade_quantity += quantity;
  cumulative_turnover += price * quantity;
}

void OrderBook::finish_call_auction() {
  if (auction_trade_quantity == 0) {
    return;
  }
  execute_auction_trade(auction_trade_price, auction_trade_quantity);
  auction_trade_quantity = 0;
  auction_trade_price = 0;
}

void OrderBook::execute_auction_trade(int64_t price, int64_t quantity) {
  // 输入已给出本段竞价实际成交价量，双方按各自价优/FIFO 消耗确定数量。
  // 统计在 F 到达时已累计，本方法只能扣盘，不能再加一遍全日累计量。
  execute_order_at_price(price, quantity, true, true);
}

void OrderBook::execute_order_at_price(int64_t price, int64_t quantity, bool reduce_bids,
                                       bool reduce_asks) {
  // 单侧扣量用于限价主动撮合，price 是本次被吃档位的实际价格；量额和最新价
  // 随撮合立即更新，笔数仍按真实 F 计算，避免把跨订单次数当成供应商成交条数。
  // 双侧扣量用于竞价结算，其真实 F 已经统计，不能重复累计。
  if (reduce_bids != reduce_asks) {
    cumulative_trade_quantity += quantity;
    cumulative_turnover += price * quantity;
    last_trade_price = price;
  }
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

    Trade consumed = {};
    consumed.quantity = executed_quantity;
    if (reduce_bids) {
      consumed.bid_appl_seq_num = bids.begin()->second.orders.front().order_appl_seq_num;
    }
    if (reduce_asks) {
      consumed.offer_appl_seq_num = asks.begin()->second.orders.front().order_appl_seq_num;
    }
    if (reduce_bids && reduce_asks) {
      execute_trade(consumed);
    } else {
      apply_cancel(consumed);
    }
    // 循环只负责跨同价订单（竞价时还可能跨档），外层来单也要减去本次确定量。
    remaining_quantity -= executed_quantity;
  }
}

void OrderBook::finish() {
  // EOF 与阶段边界都复用原收尾入口：先处理价量，再释放属于旧事件的快照。
  finish_call_auction();
  if (pending_market_order_appl_seq != 0) {
    replay_pending_market_order(pending_market_order_trades);
  }
  // EOF/阶段边界没有后到的触发撤单，缓存仍归属当前事件组。
  cyb_replay_has_cancel = false;
  replay_caused_by_cancel = false;
  replay_CYB_trades(pending_CYB_trades);
  pending_CYB_trades.clear();
  pending_cyb_group = false;
  update_previous_snapshot();
}
