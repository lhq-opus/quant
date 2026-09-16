#include "order_book.hpp"

#include <vector>

void OrderBook::handle_pending_market_order(Order&) {
  // 下一条委托到来时，上一张市价单的成交组已经结束；先还原它的最终盘口，
  // 再让外层处理新委托，避免新委托读取尚未扣减的对手盘。
  if (pending_market_order_appl_seq != 0) {
    replay_pending_market_order(pending_market_order_trades);
  }
}

void OrderBook::handle_pending_market_order(Trade& trade) {
  if (pending_market_order_appl_seq == 0) {
    return;
  }

  const bool is_pending_event = trade.bid_appl_seq_num == pending_market_order_appl_seq ||
                                trade.offer_appl_seq_num == pending_market_order_appl_seq;

  if (trade.trade_type == TradeType::Normal) {
    if (is_pending_event) {
      // 缓存期间尚未扣量，因此用独立的累计成交量判断是否已经收到全部成交。
      // pending_market_order_quantity 留给回放逐笔扣减，不能在这里提前修改。
      pending_market_order_trades.push_back(trade);
      pending_market_trade_quantity += trade.quantity;
      if (pending_market_trade_quantity == pending_market_order_quantity) {
        replay_pending_market_order(pending_market_order_trades);
      }
    }
    return;
  }

  // 相关撤单必须与此前成交按原顺序一起回放；无关撤单只负责结束上一组成交，
  // 其自身仍由外层 apply 处理，不能在这里重复扣减。
  if (is_pending_event) {
    pending_market_order_trades.push_back(trade);
  }
  replay_pending_market_order(pending_market_order_trades);
}

void OrderBook::replay_pending_market_order(std::vector<Trade> trades) {
  const int64_t order_appl_seq = pending_market_order_appl_seq;
  const EventSide side = order_info_map.find(order_appl_seq)->second.side;

  // 参数按值保存本组成交；函数末尾清空成员缓存不会影响当前遍历。
  // 真实 F 的统计已由 apply 统一累计，这里仅按两侧订单引用还原数量。
  for (std::size_t index = 0; index < trades.size(); ++index) {
    Trade& trade = trades[index];
    if (trade.trade_type == TradeType::Normal) {
      execute_trade(trade);
      pending_market_last_price = trade.price;
    } else {
      apply_cancel(trade);
      pending_market_has_cancel = true;
    }
  }

  const int64_t remaining_quantity = pending_market_order_quantity;
  if (remaining_quantity > 0 && pending_market_last_price > 0) {
    // v2 将市价单未成交余量按最后一笔真实成交价入簿。撤单价格可能为零，
    // 因此只能由 F 更新 pending_market_last_price，不能用最后一条消息的价格。
    // 复用现有入簿方法同步创建队列节点和 position，消除价格与档位不一致。
    Order remaining_order = {};
    remaining_order.order_appl_seq_num = order_appl_seq;
    remaining_order.side = side;
    remaining_order.price = pending_market_last_price;
    remaining_order.quantity = remaining_quantity;
    apply_order_in_acution(remaining_order);
  } else if (remaining_quantity > 0) {
    // 当前前提：本组成交结束仍没有成交价的市价余量，之后只会撤销，不再成交。
    // 保存未定价数量供后续单次或分次撤单按 DROP_SIGNAL 分支扣减，
    // 不能把尚存余量的占位索引提前删除；这条待撤记录没有可以解引用的 position。
    order_info_map.find(order_appl_seq)->second.unpriced_quantity = remaining_quantity;
  } else {
    // 全部成交或撤完后，数量归零的市价占位索引和原始到达次序一起删除。
    order_info_map.erase(order_appl_seq);
    order_arrival_rank.erase(order_appl_seq);
  }

  // 保留 v2 的输出口径：只有未带撤单且全部成交的市价委托才保留原快照。
  // 无快照的业务阶段不会创建快照，也无需访问 snapshots.back()。
  // 是否生成了当前市价委托行由原事件标志确定。
  if (pending_market_has_snapshot && (pending_market_has_cancel || remaining_quantity > 0) &&
      !snapshots.empty() && snapshots.back().status == SnapshotStatus::Pending) {
    snapshots.back().status = SnapshotStatus::Deleted;
  }

  pending_market_order_appl_seq = 0;
  pending_market_order_quantity = 0;
  pending_market_trade_quantity = 0;
  pending_market_last_price = 0;
  pending_market_has_cancel = false;
  pending_market_has_snapshot = false;
  pending_market_order_trades.clear();

  // 市价自身先按真实 F 回放，再直接撮合因此解冻的同向旧单。
  // 本组快照仍等下一事件边界，解冻单随后到达的真实 F 只补笔数。
  replay_CYB_trades(std::vector<Trade>());
  update_previous_snapshot();
}
