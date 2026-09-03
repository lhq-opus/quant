#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <string>
#include <utility>

namespace study {

enum class ErrorCode {
  None,
  InvalidValue,
  DuplicateOrder,
  UnknownOrder,
  OverReduce,
  LevelOverflow,
};

// 不抛异常的业务结果对象：调用者必须同时看到成功与失败原因。
struct ApplyResult {
  ApplyResult(bool was_applied, ErrorCode error_code, const std::string& error_message)
      : applied(was_applied), code(error_code), message(error_message) {}

  static ApplyResult success() { return ApplyResult(true, ErrorCode::None, ""); }

  static ApplyResult failure(ErrorCode code, const std::string& message) {
    return ApplyResult(false, code, message);
  }

  bool applied;
  ErrorCode code;
  std::string message;
};

struct OrderState {
  OrderState(std::int64_t order_price, std::uint64_t remaining)
      : price(order_price), remaining_quantity(remaining) {}

  std::int64_t price;
  std::uint64_t remaining_quantity;
};

class SimpleOrderBook {
public:
  ApplyResult apply_add(std::uint64_t order_id, std::int64_t price, std::uint64_t quantity) {
    // 第一段只做校验，不修改任何成员。
    if (order_id == 0U || price <= 0 || quantity == 0U) {
      return ApplyResult::failure(ErrorCode::InvalidValue,
                                  "order id, price and quantity must be positive");
    }
    if (orders_.find(order_id) != orders_.end()) {
      return ApplyResult::failure(ErrorCode::DuplicateOrder, "order id already exists");
    }

    LevelMap::const_iterator current_level = levels_.find(price);
    if (current_level != levels_.end() &&
        quantity > std::numeric_limits<std::uint64_t>::max() - current_level->second) {
      return ApplyResult::failure(ErrorCode::LevelOverflow, "aggregate quantity would overflow");
    }

    // 所有业务条件通过后，第二段才集中修改订单表和价位表。
    orders_.insert(std::make_pair(order_id, OrderState(price, quantity)));
    LevelMap::iterator mutable_level = levels_.find(price);
    if (mutable_level == levels_.end()) {
      levels_.insert(std::make_pair(price, quantity));
    } else {
      mutable_level->second += quantity;
    }
    return ApplyResult::success();
  }

  ApplyResult apply_cancel(std::uint64_t order_id, std::uint64_t quantity) {
    OrderMap::iterator order = orders_.find(order_id);

    // 仍然先完成全部校验。失败时，orders_ 和 levels_ 原样不动。
    if (order == orders_.end()) {
      return ApplyResult::failure(ErrorCode::UnknownOrder, "order id does not exist");
    }
    if (quantity == 0U) {
      return ApplyResult::failure(ErrorCode::InvalidValue, "cancel quantity must be positive");
    }
    if (quantity > order->second.remaining_quantity) {
      return ApplyResult::failure(ErrorCode::OverReduce, "cancel exceeds remaining quantity");
    }

    LevelMap::iterator level = levels_.find(order->second.price);
    if (level == levels_.end() || quantity > level->second) {
      return ApplyResult::failure(ErrorCode::OverReduce, "price level is inconsistent");
    }

    // 校验结束后再修改。数量归零时，同时删除空订单和空价位。
    order->second.remaining_quantity -= quantity;
    level->second -= quantity;
    if (level->second == 0U) {
      levels_.erase(level);
    }
    if (order->second.remaining_quantity == 0U) {
      orders_.erase(order);
    }
    return ApplyResult::success();
  }

  bool get_remaining(std::uint64_t order_id, std::uint64_t* quantity) const {
    if (quantity == nullptr) {
      return false;
    }
    OrderMap::const_iterator order = orders_.find(order_id);
    if (order == orders_.end()) {
      return false;
    }
    *quantity = order->second.remaining_quantity;
    return true;
  }

  bool validate_invariants() const {
    // 从活动订单重新求和，然后与缓存价位比较。这是慢检查，但非常适合验证。
    LevelMap expected_levels;
    for (OrderMap::const_iterator order = orders_.begin(); order != orders_.end(); ++order) {
      if (order->second.remaining_quantity == 0U) {
        return false;
      }

      LevelMap::iterator expected_level = expected_levels.find(order->second.price);
      if (expected_level == expected_levels.end()) {
        expected_levels.insert(
            std::make_pair(order->second.price, order->second.remaining_quantity));
      } else {
        // 即使是诊断代码，也不能让求和悄悄回绕为一个看似正常的小数。
        if (order->second.remaining_quantity >
            std::numeric_limits<std::uint64_t>::max() - expected_level->second) {
          return false;
        }
        expected_level->second += order->second.remaining_quantity;
      }
    }
    return expected_levels == levels_;
  }

private:
  typedef std::map<std::uint64_t, OrderState> OrderMap;
  typedef std::map<std::int64_t, std::uint64_t> LevelMap;

  // private 成员只能由类的方法维护，调用者不能绕过规则直接改内部状态。
  OrderMap orders_;
  LevelMap levels_;
};

} // namespace study

int main() {
  study::SimpleOrderBook book;

  const study::ApplyResult first_add = book.apply_add(1001U, 100250, 500U);
  const study::ApplyResult second_add = book.apply_add(1002U, 100250, 300U);
  std::cout << "two adds applied: " << (first_add.applied && second_add.applied ? "yes" : "no")
            << '\n';

  std::uint64_t before_bad_cancel = 0U;
  book.get_remaining(1001U, &before_bad_cancel);

  const study::ApplyResult bad_cancel = book.apply_cancel(1001U, 600U);
  std::uint64_t after_bad_cancel = 0U;
  book.get_remaining(1001U, &after_bad_cancel);

  std::cout << "oversized cancel applied: " << (bad_cancel.applied ? "yes" : "no") << '\n';
  std::cout << "failure message: " << bad_cancel.message << '\n';
  std::cout << "state unchanged: " << (before_bad_cancel == after_bad_cancel ? "yes" : "no")
            << '\n';

  const study::ApplyResult good_cancel = book.apply_cancel(1001U, 200U);
  std::cout << "valid cancel applied: " << (good_cancel.applied ? "yes" : "no") << '\n';
  std::cout << "invariants valid: " << (book.validate_invariants() ? "yes" : "no") << '\n';

  // 小练习：完全撤掉 1002，再解释订单表和价位表为什么都仍然保留 100250。
  return 0;
}
