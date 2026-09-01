#include "obr/order_book.hpp"

#include <limits>
#include <utility>

namespace obr {
namespace {

bool is_valid_side(Side side) { return side == Side::Buy || side == Side::Sell; }

bool is_same_scope(const EventId& event_id, const OrderId& order_id) {
  return event_id.trading_day == order_id.trading_day && event_id.channel == order_id.channel;
}

} // namespace

ApplyResult ApplyResult::success() { return ApplyResult(true, ApplyErrorCode::None, ""); }

ApplyResult ApplyResult::failure(ApplyErrorCode code, const std::string& message) {
  return ApplyResult(false, code, message);
}

ApplyResult OrderBook::apply_add(const AddOrderEvent& event) {
  ApplyResult result = validate_new_event(event.event_id);
  if (!result.applied) {
    return result;
  }

  result = validate_order_scope(event.event_id, event.order_id);
  if (!result.applied) {
    return result;
  }
  if (orders_.find(event.order_id) != orders_.end()) {
    return ApplyResult::failure(ApplyErrorCode::DuplicateOrder, "order id is already live");
  }
  if (event.event_id.application_sequence != event.order_id.application_sequence) {
    return ApplyResult::failure(ApplyErrorCode::ScopeMismatch,
                                "add event sequence must equal its original order sequence");
  }
  if (!is_valid_side(event.side)) {
    return ApplyResult::failure(ApplyErrorCode::InvalidSide, "add order side is invalid");
  }
  if (event.order_type != OrderType::Limit) {
    return ApplyResult::failure(ApplyErrorCode::UnsupportedOrderType,
                                "first reconstruction core supports limit orders only");
  }
  if (event.price.value <= 0) {
    return ApplyResult::failure(ApplyErrorCode::InvalidPrice, "limit order price must be positive");
  }
  if (event.quantity.value == 0U) {
    return ApplyResult::failure(ApplyErrorCode::InvalidQuantity,
                                "add order quantity must be positive");
  }

  Quantity current_quantity(0U);
  get_level_quantity(event.side, event.price, &current_quantity);
  if (event.quantity.value > std::numeric_limits<std::uint64_t>::max() - current_quantity.value) {
    return ApplyResult::failure(ApplyErrorCode::LevelQuantityOverflow,
                                "adding the order would overflow its price-level quantity");
  }

  OrderState state(event.side, event.order_type, event.price, event.quantity);
  orders_.insert(std::make_pair(event.order_id, state));
  add_to_level(event.side, event.price, event.quantity);
  processed_events_.insert(event.event_id);
  return ApplyResult::success();
}

ApplyResult OrderBook::apply_cancel(const CancelOrderEvent& event) {
  ApplyResult result = validate_new_event(event.event_id);
  if (!result.applied) {
    return result;
  }

  result = validate_order_scope(event.event_id, event.order_id);
  if (!result.applied) {
    return result;
  }
  if (!is_valid_side(event.side)) {
    return ApplyResult::failure(ApplyErrorCode::InvalidSide, "cancel side is invalid");
  }

  OrderRegistry::iterator order = orders_.find(event.order_id);
  if (order == orders_.end()) {
    return ApplyResult::failure(ApplyErrorCode::UnknownOrder,
                                "cancel references an unknown live order");
  }

  result = validate_reduction(order, event.side, event.quantity);
  if (!result.applied) {
    return result;
  }

  reduce_order(order, event.quantity);
  processed_events_.insert(event.event_id);
  return ApplyResult::success();
}

ApplyResult OrderBook::apply_trade(const TradeEvent& event) {
  ApplyResult result = validate_new_event(event.event_id);
  if (!result.applied) {
    return result;
  }
  if (event.bid_order_id == event.ask_order_id) {
    return ApplyResult::failure(ApplyErrorCode::InvalidTradeReferences,
                                "trade must reference two distinct orders");
  }

  result = validate_order_scope(event.event_id, event.bid_order_id);
  if (!result.applied) {
    return result;
  }
  result = validate_order_scope(event.event_id, event.ask_order_id);
  if (!result.applied) {
    return result;
  }
  if (event.trade_price.value <= 0) {
    return ApplyResult::failure(ApplyErrorCode::InvalidPrice, "trade price must be positive");
  }

  OrderRegistry::iterator bid_order = orders_.find(event.bid_order_id);
  OrderRegistry::iterator ask_order = orders_.find(event.ask_order_id);
  if (bid_order == orders_.end() || ask_order == orders_.end()) {
    return ApplyResult::failure(ApplyErrorCode::UnknownOrder,
                                "trade references an unknown buy or sell order");
  }

  // Both sides are checked before either side is changed. This is the key atomicity rule.
  result = validate_reduction(bid_order, Side::Buy, event.quantity);
  if (!result.applied) {
    return result;
  }
  result = validate_reduction(ask_order, Side::Sell, event.quantity);
  if (!result.applied) {
    return result;
  }

  reduce_order(bid_order, event.quantity);
  reduce_order(ask_order, event.quantity);
  processed_events_.insert(event.event_id);
  return ApplyResult::success();
}

std::size_t OrderBook::order_count() const { return orders_.size(); }

std::size_t OrderBook::processed_event_count() const { return processed_events_.size(); }

bool OrderBook::get_remaining_quantity(const OrderId& order_id, Quantity* quantity) const {
  OrderRegistry::const_iterator order = orders_.find(order_id);
  if (order == orders_.end()) {
    return false;
  }
  if (quantity != NULL) {
    *quantity = order->second.remaining_quantity;
  }
  return true;
}

bool OrderBook::get_level_quantity(Side side, Price price, Quantity* quantity) const {
  if (side == Side::Buy) {
    BidLevels::const_iterator level = bid_levels_.find(price);
    if (level == bid_levels_.end()) {
      return false;
    }
    if (quantity != NULL) {
      *quantity = level->second;
    }
    return true;
  }
  if (side == Side::Sell) {
    AskLevels::const_iterator level = ask_levels_.find(price);
    if (level == ask_levels_.end()) {
      return false;
    }
    if (quantity != NULL) {
      *quantity = level->second;
    }
    return true;
  }
  return false;
}

std::vector<PriceLevel> OrderBook::bid_levels() const {
  std::vector<PriceLevel> levels;
  levels.reserve(bid_levels_.size());
  BidLevels::const_iterator it = bid_levels_.begin();
  for (; it != bid_levels_.end(); ++it) {
    levels.push_back(PriceLevel(it->first, it->second));
  }
  return levels;
}

std::vector<PriceLevel> OrderBook::ask_levels() const {
  std::vector<PriceLevel> levels;
  levels.reserve(ask_levels_.size());
  AskLevels::const_iterator it = ask_levels_.begin();
  for (; it != ask_levels_.end(); ++it) {
    levels.push_back(PriceLevel(it->first, it->second));
  }
  return levels;
}

ValidationResult OrderBook::validate_invariants() const {
  BidLevels expected_bids;
  AskLevels expected_asks;

  OrderRegistry::const_iterator order = orders_.begin();
  for (; order != orders_.end(); ++order) {
    const OrderId& order_id = order->first;
    const OrderState& state = order->second;

    if (order_id.trading_day == 0U || order_id.channel == 0U ||
        order_id.application_sequence == 0U) {
      return ValidationResult(false, "live order has an invalid scoped id");
    }
    if (!is_valid_side(state.side)) {
      return ValidationResult(false, "live order has an invalid side");
    }
    if (state.order_type != OrderType::Limit) {
      return ValidationResult(false, "live order has an unsupported order type");
    }
    if (state.price.value <= 0 || state.remaining_quantity.value == 0U) {
      return ValidationResult(false, "live order has an invalid price or quantity");
    }

    if (state.side == Side::Buy) {
      BidLevels::iterator level = expected_bids.find(state.price);
      std::uint64_t current = level == expected_bids.end() ? 0U : level->second.value;
      if (state.remaining_quantity.value > std::numeric_limits<std::uint64_t>::max() - current) {
        return ValidationResult(false, "recomputed bid aggregate overflowed");
      }
      Quantity total(current + state.remaining_quantity.value);
      if (level == expected_bids.end()) {
        expected_bids.insert(std::make_pair(state.price, total));
      } else {
        level->second = total;
      }
    } else {
      AskLevels::iterator level = expected_asks.find(state.price);
      std::uint64_t current = level == expected_asks.end() ? 0U : level->second.value;
      if (state.remaining_quantity.value > std::numeric_limits<std::uint64_t>::max() - current) {
        return ValidationResult(false, "recomputed ask aggregate overflowed");
      }
      Quantity total(current + state.remaining_quantity.value);
      if (level == expected_asks.end()) {
        expected_asks.insert(std::make_pair(state.price, total));
      } else {
        level->second = total;
      }
    }
  }

  if (expected_bids != bid_levels_) {
    return ValidationResult(false, "bid levels do not equal the sum of live buy orders");
  }
  if (expected_asks != ask_levels_) {
    return ValidationResult(false, "ask levels do not equal the sum of live sell orders");
  }
  return ValidationResult(true, "");
}

ApplyResult OrderBook::validate_new_event(const EventId& event_id) const {
  if (event_id.trading_day == 0U || event_id.channel == 0U || event_id.application_sequence == 0U) {
    return ApplyResult::failure(ApplyErrorCode::InvalidEventId,
                                "event id requires non-zero trading day, channel, and sequence");
  }
  if (processed_events_.find(event_id) != processed_events_.end()) {
    return ApplyResult::failure(ApplyErrorCode::DuplicateEvent, "event id was already applied");
  }
  return ApplyResult::success();
}

ApplyResult OrderBook::validate_order_scope(const EventId& event_id,
                                            const OrderId& order_id) const {
  if (order_id.trading_day == 0U || order_id.channel == 0U || order_id.application_sequence == 0U) {
    return ApplyResult::failure(ApplyErrorCode::ScopeMismatch,
                                "referenced order id has an invalid scope");
  }
  if (!is_same_scope(event_id, order_id)) {
    return ApplyResult::failure(ApplyErrorCode::ScopeMismatch,
                                "event and referenced order must share trading day and channel");
  }
  return ApplyResult::success();
}

ApplyResult OrderBook::validate_reduction(OrderRegistry::const_iterator order, Side expected_side,
                                          Quantity quantity) const {
  if (quantity.value == 0U) {
    return ApplyResult::failure(ApplyErrorCode::InvalidQuantity,
                                "reduction quantity must be positive");
  }
  if (order->second.side != expected_side) {
    return ApplyResult::failure(ApplyErrorCode::SideMismatch,
                                "referenced order side does not match the event role");
  }
  if (quantity.value > order->second.remaining_quantity.value) {
    return ApplyResult::failure(ApplyErrorCode::OverReduce,
                                "event quantity exceeds referenced order remaining quantity");
  }

  Quantity aggregate(0U);
  if (!get_level_quantity(order->second.side, order->second.price, &aggregate) ||
      aggregate.value < quantity.value) {
    return ApplyResult::failure(ApplyErrorCode::InternalInvariantViolation,
                                "price level cannot satisfy a validated order reduction");
  }
  return ApplyResult::success();
}

void OrderBook::add_to_level(Side side, Price price, Quantity quantity) {
  if (side == Side::Buy) {
    BidLevels::iterator level = bid_levels_.find(price);
    if (level == bid_levels_.end()) {
      bid_levels_.insert(std::make_pair(price, quantity));
    } else {
      level->second = Quantity(level->second.value + quantity.value);
    }
  } else {
    AskLevels::iterator level = ask_levels_.find(price);
    if (level == ask_levels_.end()) {
      ask_levels_.insert(std::make_pair(price, quantity));
    } else {
      level->second = Quantity(level->second.value + quantity.value);
    }
  }
}

void OrderBook::reduce_order(OrderRegistry::iterator order, Quantity quantity) {
  Side side = order->second.side;
  Price price = order->second.price;
  Quantity new_remaining(order->second.remaining_quantity.value - quantity.value);

  if (side == Side::Buy) {
    BidLevels::iterator level = bid_levels_.find(price);
    Quantity new_aggregate(level->second.value - quantity.value);
    if (new_aggregate.value == 0U) {
      bid_levels_.erase(level);
    } else {
      level->second = new_aggregate;
    }
  } else {
    AskLevels::iterator level = ask_levels_.find(price);
    Quantity new_aggregate(level->second.value - quantity.value);
    if (new_aggregate.value == 0U) {
      ask_levels_.erase(level);
    } else {
      level->second = new_aggregate;
    }
  }

  if (new_remaining.value == 0U) {
    orders_.erase(order);
  } else {
    order->second.remaining_quantity = new_remaining;
  }
}

} // namespace obr
