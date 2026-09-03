#include <cstdint>
#include <iostream>

namespace study {

// struct 默认公开成员，适合表达一组简单、有名字的数据。
struct Price {
  // explicit 禁止把整数悄悄当成 Price，例如不能直接写 Price price = 100250。
  // 冒号后面是成员初始化列表：成员在进入构造函数体之前已经初始化完成。
  explicit Price(std::int64_t initial_value) : value(initial_value) {}

  std::int64_t value;
};

// map 需要比较键。定义 operator< 后，Price 就能作为默认 map 的键。
bool operator<(const Price& left, const Price& right) { return left.value < right.value; }

bool operator==(const Price& left, const Price& right) { return left.value == right.value; }

struct Quantity {
  explicit Quantity(std::uint64_t initial_value) : value(initial_value) {}

  std::uint64_t value;
};

// enum class 的名字不会泄漏到外围作用域，而且不同枚举之间不能随意混用。
enum class Side {
  Buy,
  Sell,
};

enum class EventType {
  AddOrder,
  CancelOrder,
  Trade,
};

struct OrderId {
  OrderId(std::uint32_t day, std::uint32_t channel_number, std::uint64_t sequence)
      : trading_day(day), channel(channel_number), application_sequence(sequence) {}

  std::uint32_t trading_day;
  std::uint32_t channel;
  std::uint64_t application_sequence;
};

// 复合键按交易日、频道、应用序号逐层比较，形成稳定的字典序。
bool operator<(const OrderId& left, const OrderId& right) {
  if (left.trading_day != right.trading_day) {
    return left.trading_day < right.trading_day;
  }
  if (left.channel != right.channel) {
    return left.channel < right.channel;
  }
  return left.application_sequence < right.application_sequence;
}

struct AddOrderEvent {
  OrderId order_id;
  Side side;
  Price price;
  Quantity quantity;

  // 末尾的 const 表示调用这个成员函数不会修改当前事件对象。
  EventType event_type() const { return EventType::AddOrder; }
};

const char* side_name(Side side) {
  switch (side) {
  case Side::Buy:
    return "buy";
  case Side::Sell:
    return "sell";
  }
  return "unknown";
}

} // namespace study

int main() {
  // 花括号按成员声明顺序构造 AddOrderEvent；每个强类型都显式构造。
  const study::AddOrderEvent event = {
      study::OrderId(20260903U, 2010U, 1001U),
      study::Side::Buy,
      study::Price(100250),
      study::Quantity(800U),
  };

  std::cout << "side: " << study::side_name(event.side) << '\n';
  std::cout << "price ticks: " << event.price.value << '\n';
  std::cout << "quantity: " << event.quantity.value << '\n';
  std::cout << "is add event: " << (event.event_type() == study::EventType::AddOrder ? "yes" : "no")
            << '\n';

  const study::OrderId earlier(20260903U, 2010U, 1000U);
  std::cout << "earlier id sorts first: " << (earlier < event.order_id ? "yes" : "no") << '\n';

  const study::Price same_price(100250);
  std::cout << "strong prices equal: " << (same_price == event.price ? "yes" : "no") << '\n';

  // 小练习：增加一个 Sell 事件，并通过 side_name 打印；不要把 Side 写成整数 1/2。
  return 0;
}
