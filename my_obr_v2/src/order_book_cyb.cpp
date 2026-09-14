#include "order_book.hpp"

#include <vector>

// 保留用户 v2 采用的创业板范围：买价不高于卖一的 102%，卖价不低于
// 买一的 98%；只对连续竞价限价委托使用。对手侧为空时沿用 v2 的
// 不暂存处理，不引入输入中没有提供的昨收价或其他规则版本。
bool OrderBook::is_outside_cyb_range(const Order& order) const {
  if (!order.is_CYB || order.trading_session != TradingSession::ContinuousTrade) {
    return false;
  }
  if (order.side == EventSide::Buy) {
    return !asks.empty() && order.price * 100 > asks.begin()->first * 102;
  }
  return !bids.empty() && order.price * 100 < bids.begin()->first * 98;
}

// 盘口改变后，原先笼子外的委托可能恢复展示。每轮先基于同一盘口收集
// 符合条件的委托，再统一入簿；新增档位可能使其他暂存单也符合条件，
// 所以持续处理到没有新激活的订单。每个订单最多从暂存区移出一次。
void OrderBook::activate_cyb_orders() {
  if (trading_session != TradingSession::ContinuousTrade) {
    // 收盘竞价不使用连续竞价价格笼子，暂存余量全部进入竞价簿。
    for (std::map<int64_t, Order>::const_iterator held = pending_limit_order_alive.begin();
         held != pending_limit_order_alive.end(); ++held) {
      add_resting_order(held->second);
    }
    pending_limit_order_alive.clear();
    return;
  }

  while (!pending_limit_order_alive.empty()) {
    std::vector<int64_t> activated_ids;
    for (std::map<int64_t, Order>::const_iterator held = pending_limit_order_alive.begin();
         held != pending_limit_order_alive.end(); ++held) {
      if (!is_outside_cyb_range(held->second)) {
        activated_ids.push_back(held->first);
      }
    }
    if (activated_ids.empty()) {
      return;
    }
    for (std::vector<int64_t>::const_iterator id = activated_ids.begin(); id != activated_ids.end();
         ++id) {
      std::map<int64_t, Order>::iterator held = pending_limit_order_alive.find(*id);
      add_resting_order(held->second);
      pending_limit_order_alive.erase(held);
    }
  }
}
