#pragma once

#include <cstdint>

namespace obr {

// Price stores an integer number of price units. The CSV adapter will define the scale later.
struct Price {
  explicit Price(std::int64_t initial_value) : value(initial_value) {}

  std::int64_t value;
};

inline bool operator==(const Price& left, const Price& right) { return left.value == right.value; }

inline bool operator!=(const Price& left, const Price& right) { return !(left == right); }

inline bool operator<(const Price& left, const Price& right) { return left.value < right.value; }

inline bool operator>(const Price& left, const Price& right) { return right < left; }

struct Quantity {
  explicit Quantity(std::uint64_t initial_value) : value(initial_value) {}

  std::uint64_t value;
};

inline bool operator==(const Quantity& left, const Quantity& right) {
  return left.value == right.value;
}

inline bool operator!=(const Quantity& left, const Quantity& right) { return !(left == right); }

enum class EventType {
  AddOrder,
  CancelOrder,
  Trade,
};

enum class Side {
  Buy,
  Sell,
};

// These are normalized meanings. A future CSV adapter will translate raw SZSE codes.
enum class OrderType {
  Market,
  Limit,
  OwnSideBest,
};

struct OrderId {
  OrderId(std::uint32_t day, std::uint32_t channel_number, std::uint64_t sequence)
      : trading_day(day), channel(channel_number), application_sequence(sequence) {}

  std::uint32_t trading_day;
  std::uint32_t channel;
  std::uint64_t application_sequence;
};

inline bool operator==(const OrderId& left, const OrderId& right) {
  return left.trading_day == right.trading_day && left.channel == right.channel &&
         left.application_sequence == right.application_sequence;
}

inline bool operator!=(const OrderId& left, const OrderId& right) { return !(left == right); }

inline bool operator<(const OrderId& left, const OrderId& right) {
  if (left.trading_day != right.trading_day) {
    return left.trading_day < right.trading_day;
  }
  if (left.channel != right.channel) {
    return left.channel < right.channel;
  }
  return left.application_sequence < right.application_sequence;
}

struct EventId {
  EventId(std::uint32_t day, std::uint32_t channel_number, std::uint64_t sequence)
      : trading_day(day), channel(channel_number), application_sequence(sequence) {}

  std::uint32_t trading_day;
  std::uint32_t channel;
  std::uint64_t application_sequence;
};

inline bool operator==(const EventId& left, const EventId& right) {
  return left.trading_day == right.trading_day && left.channel == right.channel &&
         left.application_sequence == right.application_sequence;
}

inline bool operator<(const EventId& left, const EventId& right) {
  if (left.trading_day != right.trading_day) {
    return left.trading_day < right.trading_day;
  }
  if (left.channel != right.channel) {
    return left.channel < right.channel;
  }
  return left.application_sequence < right.application_sequence;
}

// Three concrete event structures keep the first version readable without std::variant.
struct AddOrderEvent {
  EventId event_id;
  OrderId order_id;
  Side side;
  OrderType order_type;
  Price price;
  Quantity quantity;

  EventType event_type() const { return EventType::AddOrder; }
};

struct CancelOrderEvent {
  EventId event_id;
  OrderId order_id;
  Side side;
  Quantity quantity;

  EventType event_type() const { return EventType::CancelOrder; }
};

struct TradeEvent {
  EventId event_id;
  OrderId bid_order_id;
  OrderId ask_order_id;
  Price trade_price;
  Quantity quantity;

  EventType event_type() const { return EventType::Trade; }
};

} // namespace obr
