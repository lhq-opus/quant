#include "order_book.hpp"

#include <algorithm>
#include <vector>

void OrderBook::handle_pending_CYB_limit_order(Order&) {
  // 下一张委托是旧事件组边界：补齐本组真实成交笔数，再清缓存。
  // 本入口没有触发撤单，旧快照的完成由外层在处理新委托之前统一决定。
  cyb_replay_has_cancel = false;
  replay_caused_by_cancel = false;
  replay_CYB_trades(pending_CYB_trades);
  pending_CYB_trades.clear();
  update_previous_snapshot();
}

void OrderBook::handle_pending_CYB_limit_order(Trade& trade) {
  if (trade.trade_type == TradeType::Normal) {
    // 市价关联 F 已由外层分流。其余 CYB F 按原顺序缓存，组末补笔数，
    // 并在 Cancel 边界识别尚未提前撮合的撤单触发成交。
    pending_CYB_trades.push_back(trade);
    return;
  }
  // 创业板可能先收到暂存单的 F，再收到使最优档消失的触发撤单。
  // 保留撤单信息供逐笔回放判断；普通前缀仍属于上一张快照，不能整组挪走。
  cyb_cancel_trade = trade;
  cyb_replay_has_cancel = trade.is_CYB && trading_session == TradingSession::ContinuousTrade;
  replay_caused_by_cancel = false;
  replay_CYB_trades(pending_CYB_trades);
  pending_CYB_trades.clear();
  cyb_replay_has_cancel = false;
  if (!replay_caused_by_cancel) {
    update_previous_snapshot();
  }
}

void OrderBook::replay_CYB_trades(std::vector<Trade> trades) {
  // 已提前撮合的普通限价及解冻单只补真实笔数。若真实 F 引用的原单仍在暂存表，
  // 则该单尚未撮合，必须按真实引用扣量，不能把未执行的 F 也当成确认消息。
  // 后到撤单触发的特殊组此前同样没有扣盘，识别组起点后按双方引用执行并统计。
  for (std::size_t index = 0; index < trades.size(); ++index) {
    if (cyb_replay_has_cancel && !replay_caused_by_cancel) {
      // 按已经处理的真实 F 前缀判断分组，中途不能再调用空回放提前撮合。
      // 首笔 F 改变最优档后，若抢先撮合另一张暂存单，会消耗后续 F 的对手量，
      // 使原单余量和真实引用错位；等普通前缀结束或整组回放结束后再激活余量。
      const Trade& current = trades[index];
      const bool held_bid = pending_limit_order_alive.count(current.bid_appl_seq_num) != 0;
      const bool held_ask = pending_limit_order_alive.count(current.offer_appl_seq_num) != 0;
      bool cancel_removes_best = false;
      // 以已回放普通前缀后的盘口判断：暂存买单成交到了更深的卖档，而后到撤单
      // 恰好会删掉当前卖一，说明这笔 F 属于撤单触发的新组。部分撤单、同档仍有
      // 其他订单时不能这样分组；卖单使用完全对称的买一判断。
      // 两侧都暂存时没有可见对手档，不能拿默认 position 或空盘口判断最优价。
      if (held_bid && !held_ask && !asks.empty() && cyb_cancel_trade.offer_appl_seq_num != 0) {
        const OrderInfo& opposite = order_info_map.find(current.offer_appl_seq_num)->second;
        const OrderInfo& canceled =
            order_info_map.find(cyb_cancel_trade.offer_appl_seq_num)->second;
        cancel_removes_best = opposite.price != asks.begin()->first &&
                              canceled.price == asks.begin()->first &&
                              cyb_cancel_trade.quantity == asks.begin()->second.total_quantity;
      } else if (held_ask && !held_bid && !bids.empty() && cyb_cancel_trade.bid_appl_seq_num != 0) {
        const OrderInfo& opposite = order_info_map.find(current.bid_appl_seq_num)->second;
        const OrderInfo& canceled = order_info_map.find(cyb_cancel_trade.bid_appl_seq_num)->second;
        cancel_removes_best = opposite.price != bids.begin()->first &&
                              canceled.price == bids.begin()->first &&
                              cyb_cancel_trade.quantity == bids.begin()->second.total_quantity;
      }
      if (cancel_removes_best) {
        // 已确定普通前缀到此结束，先把它留下的合格余量恢复入簿，补齐旧行。
        // 当前撤单尚未扣量，其触发单仍被旧最优价限制，不会在这里抢先撮合。
        replay_CYB_trades(std::vector<Trade>());
        // 在第一笔撤单触发 F 扣盘和统计之前完成旧行，保留它应有的普通前缀。
        // 外层仍按原框架执行真正的撤单；这里只保存新行的起点，后续 F 同归新行。
        pending_cyb_group = false;
        update_previous_snapshot();
        pending_cyb_group = true;
        replay_caused_by_cancel = true;
        cyb_first_trade = current;
      }
    }
    if (replay_caused_by_cancel ||
        pending_limit_order_alive.count(trades[index].bid_appl_seq_num) != 0 ||
        pending_limit_order_alive.count(trades[index].offer_appl_seq_num) != 0) {
      execute_trade(trades[index]);
      record_trade(trades[index].price, trades[index].quantity);
    } else {
      ++trade_count;
    }
  }

  // 每轮基于同一盘口收集合格暂存单，再按价优/原到达顺序直接撮合，余量入簿。
  // 撮合后的最优价可能继续解冻其他订单，因此重复直到没有新增合格订单。
  // 空缓存也执行这一段；竞价阶段则解除连续竞价笼子，只入簿、不提前撮合。
  while (!pending_limit_order_alive.empty()) {
    std::vector<int64_t> activated;
    for (std::map<int64_t, Order>::const_iterator held = pending_limit_order_alive.begin();
         held != pending_limit_order_alive.end(); ++held) {
      const Order& order = held->second;
      bool outside = false;
      if (trading_session == TradingSession::ContinuousTrade) {
        outside = (order.side == EventSide::Buy && !asks.empty() &&
                   order.price * 100 > asks.begin()->first * BID_COEFFICIENT) ||
                  (order.side == EventSide::Sell && !bids.empty() &&
                   order.price * 100 < bids.begin()->first * ASK_COEFFICIENT);
      }
      if (!outside) {
        activated.push_back(held->first);
      }
    }
    if (activated.empty()) {
      break;
    }
    // 同轮解冻的同侧订单按价格优先，同价沿用原到达次序；不能按 map 中的
    // 订单号先后撮合，否则较低优先级的暂存单会先消耗对手量。
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
    for (std::size_t index = 0; index < activated.size(); ++index) {
      std::map<int64_t, Order>::iterator held = pending_limit_order_alive.find(activated[index]);
      // 先移除冻结态及没有节点的占位索引，再让原方法负责全成清理或余量入簿。
      // 拷贝保存原单，避免 erase 后继续引用已失效的 map 元素。
      Order order = held->second;
      pending_limit_order_alive.erase(held);
      order_info_map.erase(order.order_appl_seq_num);
      if (trading_session == TradingSession::ContinuousTrade) {
        apply_limit_order(order);
        // 本单完成后可能又解冻价格更优的旧单，重新收集，不能先把原批次撮合完。
        break;
      } else {
        apply_order_in_acution(order);
      }
    }
  }
}
