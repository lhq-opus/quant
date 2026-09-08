#include "obr/order_book.hpp"

#include <iostream>
#include <vector>

namespace {

void print_levels(const char* name, const std::vector<obr::PriceLevel>& levels) {
  std::cout << name << '\n';
  std::vector<obr::PriceLevel>::const_iterator level = levels.begin();
  for (; level != levels.end(); ++level) {
    std::cout << "  internal_price=" << level->price << ", quantity=" << level->quantity << '\n';
  }
}

void print_snapshot(const obr::Snapshot& snapshot) {
  std::cout << "snapshot caa=" << snapshot.caa << '\n';
  print_levels("bid levels:", snapshot.bids);
  print_levels("ask levels:", snapshot.asks);
}

} // namespace

int main() {
  obr::OrderBook book;

  // 这里直接构造正式代码使用的 Event。
  // 价格 101000 的单位是 0.0001 元，所以它表示 10.1000 元。
  // {} 把没有显式赋值的数字字段初始化为 0；逐字段赋值比长串位置参数更容易阅读。
  obr::Event bid_1 = {};
  bid_1.caa = "09:15";
  bid_1.transaction_time = "91500790";
  bid_1.type = obr::EventType::Order;
  bid_1.side = '1';
  bid_1.order_type = '2';
  bid_1.price = 101000;
  bid_1.quantity = 100;
  bid_1.channel_no = 1;
  bid_1.order_appl_seq_num = 1;

  // 复制 struct 得到另一个独立对象；修改 bid_2 不会改变 bid_1。
  obr::Event bid_2 = bid_1;
  bid_2.caa = "09:16";
  bid_2.transaction_time = "91600000";
  bid_2.price = 100000;
  bid_2.order_appl_seq_num = 2;

  obr::Event ask = bid_1;
  ask.caa = "09:17";
  ask.transaction_time = "91700000";
  ask.side = '2';
  ask.price = 99000;
  ask.order_appl_seq_num = 3;

  // 集合竞价期间 apply 只累加价格档。直到显式调用 finish_call_auction，
  // 三个交叉的价格档才会按照集合竞价规则统一成交。
  book.apply(bid_1, obr::TradingSession::OpeningAuction);
  book.apply(bid_2, obr::TradingSession::OpeningAuction);
  book.apply(ask, obr::TradingSession::OpeningAuction);
  book.finish_call_auction();
  print_snapshot(book.make_snapshot(ask));

  // 撤单只要带原订单引用。方向和价格由核心从订单索引取，不需要上游补全。
  // 当前盘口只剩 10.0000 买量 100，这里引用频道 1、ASN 2 的原买单，撤掉其中 20。
  obr::Event cancel = {};
  cancel.caa = "09:30";
  cancel.transaction_time = "93000000";
  cancel.type = obr::EventType::Cancel;
  cancel.quantity = 20;
  cancel.channel_no = 1;
  cancel.order_appl_seq_num = 2;
  book.apply(cancel, obr::TradingSession::ContinuousAuction);
  print_snapshot(book.make_snapshot(cancel));

  // 连续卖单的价格虽然低于买一，order 到达也不自行撮合。先登记卖量 30。
  obr::Event continuous_ask = ask;
  continuous_ask.caa = "10:04";
  continuous_ask.transaction_time = "100407190";
  continuous_ask.quantity = 30;
  continuous_ask.order_appl_seq_num = 5;
  book.apply(continuous_ask, obr::TradingSession::ContinuousAuction);

  // 真实成交明确引用买单 2 和卖单 5，各扣 30；金额采用 TradePrice=10.0000。
  obr::Event trade = {};
  trade.type = obr::EventType::Trade;
  trade.channel_no = 1;
  trade.bid_appl_seq_num = 2;
  trade.offer_appl_seq_num = 5;
  trade.price = 100000;
  trade.quantity = 30;
  book.apply(trade, obr::TradingSession::ContinuousAuction);

  // 这两步共同构成卖单的快照区间。即使最后处理的是 trade，caa 仍取卖单的 10:04。
  print_snapshot(book.make_snapshot(continuous_ask));

  std::cout << "cumulative trade quantity: " << book.cumulative_trade_quantity() << '\n';
  std::cout << "cumulative turnover in 0.0001 units: " << book.cumulative_turnover() << '\n';

  // 小练习：只把 trade.quantity 从 30 改成 20，预测两侧剩余量与快照的 caa。
  return 0;
}
