#include "order_book.hpp"

// 市价来单暂不进入可见盘口。后续真实成交通过原单引用扣减对手盘，
// 并同步扣减这里保存的余量；本文件只负责市价组的建立和收尾。
void OrderBook::apply_market_order(Order& order) {
  pending_market_order = order;
  pending_market_order_appl_seq = order.order_appl_seq_num;
  pending_market_order_quantity = order.quantity;
  pending_market_last_price = 0;
}

// 以通道和原单序号确认成交或撤单是否属于当前等待中的市价委托。
// 零序号表示没有待处理市价单，不能与撤单中缺失的一侧引用匹配。
bool OrderBook::is_pending_market_trade(const Trade& trade) const {
  return pending_market_order_appl_seq != 0 &&
         trade.channel_no == pending_market_order.channel_no &&
         (trade.bid_appl_seq_num == pending_market_order_appl_seq ||
          trade.offer_appl_seq_num == pending_market_order_appl_seq);
}

// 查询原始委托类型，而不是当前是否仍有挂单。市价委托完全成交、撤销，
// 或按最后成交价转为挂单后，原始身份仍然保留，两侧标志独立返回。
void OrderBook::get_market_trade_sides(const Trade& trade, bool& is_bid, bool& is_ask) const {
  is_bid = market_order_ids.count(std::make_pair(trade.channel_no, trade.bid_appl_seq_num)) != 0;
  is_ask = market_order_ids.count(std::make_pair(trade.channel_no, trade.offer_appl_seq_num)) != 0;
}

// 成交量、撤销量已经由 consume_order 扣除，成交统计也已按真实 F 更新。
// 收尾只处理余量和快照状态，不能再次回放成交或累计成交量、金额。
void OrderBook::finish_pending_market_order(bool canceled) {
  if (pending_market_order_appl_seq == 0) {
    return;
  }

  if (pending_market_order_quantity > 0 && pending_market_last_price > 0) {
    // 沿用 v2 的余量规则：存在实际成交价时，剩余委托以最后成交价入簿。
    // 复制原单保留身份和到达次序，盘口档位与订单索引使用同一实际价格。
    Order remaining_order = pending_market_order;
    remaining_order.price = pending_market_last_price;
    remaining_order.quantity = pending_market_order_quantity;
    add_resting_order(remaining_order);
  } else {
    // 已耗尽的订单不再需要 FIFO 次序；从未成交的市价单没有可用挂单价，
    // 按 v2 规则结束该组，也不把它伪装成价格为零或负数的盘口订单。
    order_arrival_rank.erase(pending_market_order_appl_seq);
  }

  // 全部由成交消耗时保留原市价委托快照。发生撤单或存在余量时，沿用
  // v2 删除原市价快照的策略；随后撤单/订单自己的快照反映最终盘口。
  const SnapshotStatus status = pending_market_order_quantity == 0 && !canceled
                                    ? SnapshotStatus::Ready
                                    : SnapshotStatus::Deleted;
  complete_previous_snapshot(status);

  // 已入簿余量的 position 和到达次序由活动索引继续持有；这里只清理
  // 本次市价组的等待状态，原始市价身份集合仍然用于后续成交查询。
  pending_market_order = Order();
  pending_market_order_appl_seq = 0;
  pending_market_order_quantity = 0;
  pending_market_last_price = 0;
}
