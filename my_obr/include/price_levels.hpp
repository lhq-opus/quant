#ifndef MY_OBR_PRICE_LEVELS_HPP
#define MY_OBR_PRICE_LEVELS_HPP

#include "model.hpp"

#include <cstddef>
#include <map>
#include <vector>

// 一侧盘口的价格档，不管理订单引用，也不决定撮合价格或成交数量。
// 所有档位数量为正；减到零时立即删档。同价加量保留该档已有数量。
// 对外始终按最优到最差读取：买盘从高到低，卖盘从低到高。
class PriceLevels {
public:
  // 沿用原始方向：'1' 是买盘，'2' 是卖盘。
  explicit PriceLevels(char side);

  bool empty() const;
  // 调用者先确认非空；返回副本，不让外部持有可能因删档失效的迭代器。
  PriceLevel best() const;
  // 该价位不存在时返回 0，查询不会偷偷创建一个空档。
  int64_t quantity_at(int64_t price) const;

  // 调用者保证价格、数量合法。加量沿用现有的溢出检查。
  void add(int64_t price, int64_t quantity);
  // 调用者保证该档存在，且 0 < quantity <= 该档数量；减空时统一删档。
  void reduce(int64_t price, int64_t quantity);

  // 读取独立的值副本。read_top 只读所需档数，不足时由快照层补零。
  std::vector<PriceLevel> read_top(std::size_t count) const;
  std::vector<PriceLevel> read_all() const;

  // 交换两份盘口数据，方向也一起交换；默认值拷贝可独立保存一份盘口。
  void swap(PriceLevels& other);

private:
  // 内部统一升序，买盘用反向遍历，卖盘用正向遍历。
  typedef std::map<int64_t, int64_t> LevelMap;
  char side_;
  LevelMap levels_;
};

#endif
