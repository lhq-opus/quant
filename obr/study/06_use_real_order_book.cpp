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
  const obr::Event bid_1 = {"09:15", "91500790", obr::EventType::Order, '1', '2', 101000, 100};
  const obr::Event bid_2 = {"09:16", "91600000", obr::EventType::Order, '1', '2', 100000, 100};
  const obr::Event ask = {"09:17", "91700000", obr::EventType::Order, '2', '2', 99000, 100};

  // 集合竞价期间 apply 只累加价格档。直到显式调用 finish_call_auction，
  // 三个交叉的价格档才会按照集合竞价规则统一成交。
  book.apply(bid_1, obr::TradingSession::OpeningAuction);
  book.apply(bid_2, obr::TradingSession::OpeningAuction);
  book.apply(ask, obr::TradingSession::OpeningAuction);
  book.finish_call_auction();
  print_snapshot(book.make_snapshot(ask));

  // 简化 Event 已经把撤单的 TradePrice/TradeQty 归一成 price/quantity。
  // 当前盘口只剩 10.0000 买量 100，这里撤掉其中 20。
  const obr::Event cancel = {"09:19", "91900000", obr::EventType::Cancel, '\0', '\0', 100000, 20};
  book.apply(cancel, obr::TradingSession::OpeningAuction);
  print_snapshot(book.make_snapshot(cancel));

  // 连续竞价卖单 9.9000 低于当前买一 10.0000，所以立即以买一价格成交 30。
  const obr::Event continuous_ask = {"10:04", "100407190", obr::EventType::Order, '2', '2',
                                     99000,   30};
  book.apply(continuous_ask, obr::TradingSession::ContinuousAuction);
  print_snapshot(book.make_snapshot(continuous_ask));

  std::cout << "cumulative trade quantity: " << book.cumulative_trade_quantity() << '\n';
  std::cout << "cumulative turnover in 0.0001 units: " << book.cumulative_turnover() << '\n';

  // 小练习：把 continuous_ask 的数量从 30 改成 120，预测卖单最终是否会进入卖盘。
  return 0;
}
