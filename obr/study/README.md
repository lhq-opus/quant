# OBR C++11 代码学习区

这里用 6 个可以独立运行的小程序，拆解订单簿重建代码里已经出现、或下一步很可能
出现的 C++ 用法。学习代码追求“看得见每一步”，正式业务实现仍在 `include/obr` 和
`src`；这里不会维护第二套生产订单簿。

代码中的中文注释是课程正文，英文名称尽量与正式实现一致。全部程序使用 C++11，
因此也满足“C++14 或更早”的要求。这里没有使用结构化绑定、`std::optional`、
`std::variant`、`std::string_view`、`map::contains`、三向比较等 C++17/20 用法。

## 建议顺序

| 课程 | 先理解什么 | 对应正式代码 |
| --- | --- | --- |
| `01_values_references_const.cpp` | 值、函数、值传递、引用、指针输出、`const`、定点价格 | `OrderBook` 的参数和集合竞价输出参数 |
| `02_structs_enums_operators.cpp` | `struct`、构造函数、初始化列表、`explicit`、`enum class`、运算符 | `Event`/`Snapshot` 的基础语法及后续强类型思路 |
| `03_containers_iterators.cpp` | `vector`、`map`、`set`、迭代器、排序规则 | `OrderBook` 的买卖价位表与五档快照 |
| `04_class_result_atomicity.cpp` | `class`、`public/private`、结果对象、先校验后修改、不变量 | 后续工业化版本可能恢复的错误处理思路 |
| `05_price_time_queue.cpp` | 价格优先和同价 FIFO，`deque` 的队首/队尾 | 后续若要显式保存队列优先级时可能使用 |
| `06_use_real_order_book.cpp` | 把前面语法放回真实类型，执行集合竞价、连续竞价和撤单 | 当前简化重建核心 |

第 4、5 节保留了订单 ID、错误结果和同价 FIFO 的学习例子，供后续工业化迭代参考。
当前第一版正式核心更简单：它和 Python replay 一样只维护聚合价格档，不恢复具体订单，
并在价格档层面推导成交。不要把这个教学假设当成完整的交易所逐笔成交模型。

## 编译和运行

在工作区根目录执行：

```bash
cmake -S quant/obr/study -B /tmp/obr-cpp-study-build
cmake --build /tmp/obr-cpp-study-build --parallel
```

然后逐个运行：

```bash
/tmp/obr-cpp-study-build/obr_study_01_values
/tmp/obr-cpp-study-build/obr_study_02_types
/tmp/obr-cpp-study-build/obr_study_03_containers
/tmp/obr-cpp-study-build/obr_study_04_class
/tmp/obr-cpp-study-build/obr_study_05_price_time
/tmp/obr-cpp-study-build/obr_study_06_real_core
```

建议再开一次运行时检查构建：

```bash
cmake -S quant/obr/study -B /tmp/obr-cpp-study-sanitize \
  -DOBR_STUDY_ENABLE_SANITIZERS=ON
cmake --build /tmp/obr-cpp-study-sanitize --parallel
```

如果只想手工编译第一节，可以直接执行：

```bash
c++ -std=c++11 -Wall -Wextra -Wconversion -Werror -Wpedantic -Wshadow \
  quant/obr/study/01_values_references_const.cpp -o /tmp/obr-study-01
/tmp/obr-study-01
```

`CMakeLists.txt` 中的 `CXX_STANDARD 11` 是版本约束，`CXX_EXTENSIONS OFF` 禁止依赖某个
编译器私有扩展；严格警告选项帮助我们尽早发现可疑的隐式转换、变量遮蔽等问题。

## 头文件、源文件和链接

先把第 6 节当作一个具体例子：

1. `#include "obr/order_book.hpp"` 会让编译器看到类型和函数的声明，例如
   `OrderBook::apply` 可以接收什么参数。
2. `06_use_real_order_book.cpp` 和 `src/order_book.cpp` 分别是翻译单元，各自先编译成
   目标文件；前者包含调用，后者包含函数定义。
3. 链接器最后把两份目标文件合成 `obr_study_06_real_core`。如果只编译第 6 节而漏掉
   `order_book.cpp`，通常会得到“未定义符号”，不是语法错误。
4. `#pragma once` 避免一个头文件在同一翻译单元中被重复展开；头文件主要告诉各个
   翻译单元有哪些类型和公开成员函数。
5. `namespace obr` 把正式类型放进项目自己的名字空间；教学文件中的匿名
   `namespace {}` 则让辅助函数只在当前 `.cpp` 内可见。

## 生命周期和所有权

- `main` 中的局部 `OrderBook book` 在进入作用域时构造，离开作用域时自动析构。
- `map`、`vector`、`set` 和 `deque` 拥有其中的元素；容器销毁时元素也自动销毁，
  所以这些例子完全不需要手写 `new`/`delete`。
- 引用和原始指针在这些接口里只是临时借用，不拥有对象。调用期间被引用或被指向的
  对象必须仍然存在。
- 这就是当前代码最直接的 RAII：对象负责自己拥有的资源，生命周期由作用域管理。
  以后只有出现真实的动态所有权需求时，才应引入 `std::unique_ptr` 等智能指针。

## 后续课程按实际代码增加

当前 CSV replay 已经使用 `std::stable_sort`、比较函数、`std::string` 和文件流；可以在
读完第 6 节后继续阅读 `src/replay_event_main.cpp`。模板、移动语义、智能指针和并发不会
为了“展示高级语法”提前塞进教程，等后续实现真正需要时再增加对应的最小例子。

## 怎么学，而不是只把程序跑一遍

每一节可以按这个循环进行：

1. 暂时遮住 `main` 后半段，先猜变量或容器最终是什么状态。
2. 阅读第一次出现的语法旁边的注释。
3. 编译并运行，比较输出和自己的预测。
4. 完成文件末尾注释中的小练习，再重新编译。
5. 最后回到对应正式代码，寻找相同写法。

可以先回答三个检查问题：

- 为什么 `OrderBook::apply` 使用 `const Event&`，而不是复制一份 `Event`？
- 为什么买价 `map` 使用 `std::greater`，卖价却使用默认排序？
- 为什么集合竞价阶段不能在每条订单到来时立即撮合？

这些程序通过只说明示例在当前工具链下可用，不等于你已经掌握。真正的学习证据是你
能解释对象如何变化，或自己完成一个小改动。
