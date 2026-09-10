#include "price_levels.hpp"

#include "checked_math.hpp"

#include <algorithm>
#include <utility>

PriceLevels::PriceLevels(char side) : side_(side) {}

bool PriceLevels::empty() const { return levels_.empty(); }

PriceLevel PriceLevels::best() const {
  if (side_ == '1') {
    // rbegin() 指向最大价格，即买一。
    LevelMap::const_reverse_iterator level = levels_.rbegin();
    return PriceLevel{level->first, level->second};
  }
  // begin() 指向最小价格，即卖一。
  LevelMap::const_iterator level = levels_.begin();
  return PriceLevel{level->first, level->second};
}

int64_t PriceLevels::quantity_at(int64_t price) const {
  LevelMap::const_iterator level = levels_.find(price);
  return level == levels_.end() ? 0 : level->second;
}

void PriceLevels::add(int64_t price, int64_t quantity) {
  // 先计算再写入，既不会覆盖已有量，也不会因加法失败留下新建的零量档。
  const int64_t next_quantity = checked_add(quantity_at(price), quantity);
  levels_[price] = next_quantity;
}

void PriceLevels::reduce(int64_t price, int64_t quantity) {
  LevelMap::iterator level = levels_.find(price);
  level->second -= quantity;
  if (level->second == 0) {
    levels_.erase(level);
  }
}

std::vector<PriceLevel> PriceLevels::read_top(std::size_t count) const {
  std::vector<PriceLevel> result;
  result.reserve(std::min(count, levels_.size()));
  if (side_ == '1') {
    LevelMap::const_reverse_iterator level = levels_.rbegin();
    for (; level != levels_.rend() && result.size() < count; ++level) {
      result.push_back(PriceLevel{level->first, level->second});
    }
  } else {
    LevelMap::const_iterator level = levels_.begin();
    for (; level != levels_.end() && result.size() < count; ++level) {
      result.push_back(PriceLevel{level->first, level->second});
    }
  }
  return result;
}

std::vector<PriceLevel> PriceLevels::read_all() const { return read_top(levels_.size()); }

void PriceLevels::swap(PriceLevels& other) {
  std::swap(side_, other.side_);
  levels_.swap(other.levels_);
}
