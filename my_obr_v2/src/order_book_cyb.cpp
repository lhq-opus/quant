#include "order_book.hpp"

#include <vector>

void OrderBook::handle_pending_CYB_limit_order(Order&) {
  // 下一张委托是旧事件组边界：整组先回放再清缓存。真实 F 的统计已经在 apply
  // 中累计，旧快照的完成由外层在处理新委托之前统一决定。
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
  // 当前撤单之前的 F 属于上一组；先还原旧盘口。不要无条件读取两侧 begin，
  // 单边没有可见订单同样是合法的业务状态。
  replay_CYB_trades(pending_CYB_trades);
  pending_CYB_trades.clear();
  update_previous_snapshot();
}

void OrderBook::replay_CYB_trades(std::vector<Trade> trades) {
  // 统一按两侧原单扣量：暂存原单自身也要扣，订单全成时同步删除其状态与索引。
  // 不再因一条 F 属于市价/暂存就 return 丢弃整个尾部，也不另外累计成交统计。
  for (std::size_t index = 0; index < trades.size(); ++index) {
    execute_trade(trades[index]);
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
