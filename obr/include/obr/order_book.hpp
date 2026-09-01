#pragma once

#include "obr/domain.hpp"

#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace obr {

enum class ApplyErrorCode {
  None,
  InvalidEventId,
  DuplicateEvent,
  ScopeMismatch,
  InvalidSide,
  UnsupportedOrderType,
  InvalidPrice,
  InvalidQuantity,
  DuplicateOrder,
  UnknownOrder,
  SideMismatch,
  InvalidTradeReferences,
  OverReduce,
  LevelQuantityOverflow,
  InternalInvariantViolation,
};

struct ApplyResult {
  ApplyResult(bool was_applied, ApplyErrorCode error_code, const std::string& error_message)
      : applied(was_applied), code(error_code), message(error_message) {}

  static ApplyResult success();
  static ApplyResult failure(ApplyErrorCode code, const std::string& message);

  bool applied;
  ApplyErrorCode code;
  std::string message;
};

struct PriceLevel {
  PriceLevel(Price level_price, Quantity level_quantity)
      : price(level_price), aggregate_quantity(level_quantity) {}

  Price price;
  Quantity aggregate_quantity;
};

inline bool operator==(const PriceLevel& left, const PriceLevel& right) {
  return left.price == right.price && left.aggregate_quantity == right.aggregate_quantity;
}

struct OrderState {
  OrderState(Side order_side, OrderType type, Price order_price, Quantity remaining)
      : side(order_side), order_type(type), price(order_price), remaining_quantity(remaining) {}

  Side side;
  OrderType order_type;
  Price price;
  Quantity remaining_quantity;
};

struct ValidationResult {
  ValidationResult(bool is_valid, const std::string& error_message)
      : valid(is_valid), message(error_message) {}

  bool valid;
  std::string message;
};

// This class owns one instrument's live orders and all of its price levels.
// CSV reading, event ordering, snapshots, and multi-instrument dispatch stay outside it.
class OrderBook {
public:
  ApplyResult apply_add(const AddOrderEvent& event);
  ApplyResult apply_cancel(const CancelOrderEvent& event);
  ApplyResult apply_trade(const TradeEvent& event);

  std::size_t order_count() const;
  std::size_t processed_event_count() const;

  bool get_remaining_quantity(const OrderId& order_id, Quantity* quantity) const;
  bool get_level_quantity(Side side, Price price, Quantity* quantity) const;

  std::vector<PriceLevel> bid_levels() const;
  std::vector<PriceLevel> ask_levels() const;

  // This O(N) audit is intended for validation and diagnostics, not every hot-path event.
  ValidationResult validate_invariants() const;

private:
  typedef std::map<OrderId, OrderState> OrderRegistry;
  typedef std::map<Price, Quantity, std::greater<Price>> BidLevels;
  typedef std::map<Price, Quantity> AskLevels;

  ApplyResult validate_new_event(const EventId& event_id) const;
  ApplyResult validate_order_scope(const EventId& event_id, const OrderId& order_id) const;
  ApplyResult validate_reduction(OrderRegistry::const_iterator order, Side expected_side,
                                 Quantity quantity) const;

  void add_to_level(Side side, Price price, Quantity quantity);
  void reduce_order(OrderRegistry::iterator order, Quantity quantity);

  OrderRegistry orders_;
  BidLevels bid_levels_;
  AskLevels ask_levels_;
  std::set<EventId> processed_events_;
};

} // namespace obr
