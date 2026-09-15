#include "order_book.hpp"

#include <vector>

void OrderBook::handle_pending_CYB_limit_order(Order&) {
  // 下一张委托是旧事件组边界：整组先回放并统计，再清缓存。
  // 本入口没有触发撤单，旧快照的完成由外层在处理新委托之前统一决定。
  cyb_replay_has_cancel = false;
  replay_caused_by_cancel = false;
  replay_CYB_trades(pending_CYB_trades);
  pending_CYB_trades.clear();
  update_previous_snapshot();
}

void OrderBook::handle_pending_CYB_limit_order(Trade& trade) {
  if (trade.trade_type == TradeType::Normal) {
    // 外层已经将市价关联 F 分给市价缓存。这里无论一侧还是两侧暂存，只存一次，
    // 也保存暂存参与事件组中普通可见订单的 F，保持该组真实成交的先后次序。
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
  // 统一按两侧原单扣量：暂存原单自身也要扣，订单全成时同步删除其状态与索引。
  // CYB F 到达时尚未统计；在回放中按先后顺序扣盘并且只累计一次。
  for (std::size_t index = 0; index < trades.size(); ++index) {
    if (cyb_replay_has_cancel && !replay_caused_by_cancel) {
      // 普通成交前缀可能已经让其他暂存单恢复展示；此前市价回放也可能改变最优档。
      // 先复用现有激活逻辑，保证分组判断和旧快照都基于前缀处理后的完整盘口。
      // 空 vector 不进入本 for，只执行下方激活循环，因此不会继续递归。
      replay_CYB_trades(std::vector<Trade>());
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
        // 在第一笔撤单触发 F 扣盘和统计之前完成旧行，保留它应有的普通前缀。
        // 外层仍按原框架执行真正的撤单；这里只保存新行的起点，后续 F 同归新行。
        pending_cyb_group = false;
        update_previous_snapshot();
        pending_cyb_group = true;
        replay_caused_by_cancel = true;
        cyb_first_trade = current;
      }
    }
    execute_trade(trades[index]);
    record_trade(trades[index].price, trades[index].quantity);
  }

  // 每轮基于同一盘口收集能够恢复展示的余量，再统一入簿；恢复后的新最优价
  // 可能影响其他暂存单，因此重复直到没有新增合格订单。空缓存也执行这一段，
  // 以覆盖只有撤单/档位变化而没有 F 的激活。竞价阶段则解除连续竞价笼子。
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
    for (std::size_t index = 0; index < activated.size(); ++index) {
      std::map<int64_t, Order>::iterator held = pending_limit_order_alive.find(activated[index]);
      // 复用现有只入簿方法，按原到达次序恢复 FIFO；不调用 limit 再推演成交。
      apply_order_in_acution(held->second);
      pending_limit_order_alive.erase(held);
    }
  }
}
