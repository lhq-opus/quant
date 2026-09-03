#include <cstdint>
#include <iostream>

namespace {

// 这个函数按值接收 quantity：函数得到一份副本，外面的原变量不会被修改。
std::uint64_t preview_reduction(std::uint64_t quantity, std::uint64_t reduction) {
  if (reduction > quantity) {
    return quantity;
  }
  quantity -= reduction;
  return quantity;
}

// `std::uint64_t&` 是非常量引用，它是调用者变量的另一个名字。
// 修改 quantity，就是修改 main 中传进来的 remaining_quantity。
bool reduce_in_place(std::uint64_t& quantity, std::uint64_t reduction) {
  // 先校验再修改，失败路径不会留下“扣了一半”的状态。
  if (reduction == 0U || reduction > quantity) {
    return false;
  }

  quantity -= reduction;
  return true;
}

// `const std::uint64_t&` 表示只读引用：不复制，也不允许在函数内修改它。
void print_quantity(const char* label, const std::uint64_t& quantity) {
  std::cout << label << quantity << '\n';
}

// 指针参数可以为空，因此它适合表达“有值就写给我，没有就返回 false”的接口。
// 正式核心的 get_remaining_quantity 就采用这种基础写法。
bool copy_to_output(const std::uint64_t& quantity, std::uint64_t* output) {
  // nullptr 是 C++11 的空指针字面量，比数字 0 的含义更明确。
  if (output == nullptr) {
    return false;
  }

  // `*output` 表示访问指针指向的那个变量。
  *output = quantity;
  return true;
}

} // namespace

int main() {
  // 固定宽度整数让我们明确知道字段能表达的范围。
  const std::int64_t price_ticks = 100250;
  const std::uint64_t original_quantity = 1000U;
  std::uint64_t remaining_quantity = original_quantity;

  // 价格在订单簿内部保存为整数刻度，不用 double 做键，避免二进制浮点误差。
  // 这里没有擅自规定一个 tick 对应多少钱；缩放属于将来的 CSV 适配层契约。
  std::cout << "price ticks: " << price_ticks << '\n';

  const std::uint64_t preview = preview_reduction(remaining_quantity, 300U);
  print_quantity("preview after reducing 300: ", preview);
  print_quantity("original is still: ", remaining_quantity);

  const bool applied = reduce_in_place(remaining_quantity, 300U);
  std::cout << "reduction applied: " << (applied ? "yes" : "no") << '\n';
  print_quantity("real remaining: ", remaining_quantity);

  std::uint64_t observed_quantity = 0U;
  // `&observed_quantity` 取得变量地址，把它交给输出指针参数。
  const bool found = copy_to_output(remaining_quantity, &observed_quantity);
  std::cout << "output written: " << (found ? "yes" : "no") << '\n';
  print_quantity("observed quantity: ", observed_quantity);

  const bool null_output_accepted = copy_to_output(remaining_quantity, nullptr);
  std::cout << "null output accepted: " << (null_output_accepted ? "yes" : "no") << '\n';

  // 小练习：把第二次扣减改成 800，先猜 reduce_in_place 的返回值和剩余数量。
  return 0;
}
