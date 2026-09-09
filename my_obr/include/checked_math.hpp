#ifndef MY_OBR_CHECKED_MATH_HPP
#define MY_OBR_CHECKED_MATH_HPP

#include <limits>
#include <stdexcept>
#include <stdint.h>

// Quantities and turnover are nonnegative. Check before performing arithmetic.
inline int64_t checked_add(int64_t left, int64_t right) {
  if (left < 0 || right < 0 || right > std::numeric_limits<int64_t>::max() - left) {
    throw std::overflow_error("nonnegative integer addition exceeds int64 range");
  }
  return left + right;
}

inline int64_t checked_multiply(int64_t left, int64_t right) {
  if (left < 0 || right < 0 || (left != 0 && right > std::numeric_limits<int64_t>::max() / left)) {
    throw std::overflow_error("nonnegative integer product exceeds int64 range");
  }
  return left * right;
}

#endif
