# C++ 版本：编译与执行指南

这份文档只说明当前第一版 C++11 demo 怎样编译和运行。它读取 `event.csv`，重放开盘
集合、连续和收盘集合竞价，然后输出简化的五档 `book.csv`。

## 1. 进入工作区根目录

下面所有命令都从包含 `quant` 目录的工作区根目录执行。在当前电脑上是：

```bash
cd /Users/hanqingliu/Desktop/obr
```

如果以后移动了项目，只需要把这里换成新的工作区路径，后续相对路径不变。

## 2. 检查编译工具

项目需要：

- 支持 C++11 的 C++ 编译器；
- CMake 3.20 或更高版本。

先查看当前环境：

```bash
c++ --version
cmake --version
```

C++ 程序只依赖标准库，不需要 pandas，也没有第三方 C++ 依赖。

## 3. 编译

```bash
cmake -S ./quant/obr -B /tmp/obr-build -DCMAKE_BUILD_TYPE=Debug
cmake --build /tmp/obr-build --parallel
```

两条命令的含义：

- `-S ./quant/obr`：源码和 `CMakeLists.txt` 在这里；
- `-B /tmp/obr-build`：把编译中间文件放到 `/tmp`，不污染 Git 仓库；
- `CMAKE_BUILD_TYPE=Debug`：当前学习阶段保留便于调试的信息；
- `--parallel`：允许编译器并行编译不同源文件。

编译成功后会生成两个程序：

```text
/tmp/obr-build/obr_replay_event
/tmp/obr-build/obr_validate_reconstruction_core
```

其中 `obr_replay_event` 是真正读取 CSV 的程序，另一个是正常流程验证程序。

可以先查看 replay 的命令行格式：

```bash
/tmp/obr-build/obr_replay_event --help
```

预期输出：

```text
用法: /tmp/obr-build/obr_replay_event --event <event.csv> [--output <book.csv>]
```

## 4. 准备 event.csv

输入必须是当前约定的 9 列：

```text
caa,TransactionTime,Side,OrderType,Price,OrderQty,ExecType,TradeQty,TradePrice
```

- order 行填写 `caa,TransactionTime,Side,OrderType,Price,OrderQty`；
- 撤单行填写 `caa,TransactionTime,ExecType,TradeQty,TradePrice`；
- `ExecType=4` 表示撤单；
- `TransactionTime` 用于区分开盘集合、连续和收盘集合竞价；
- 程序会按 `caa` 稳定排序，不要求 CSV 当前已经排好顺序。

第一版假设 CSV 内容合法，并且字段中没有需要引号保护的逗号。

## 5. 执行订单簿重放

把下面两个路径换成自己的真实路径：

```bash
/tmp/obr-build/obr_replay_event \
  --event /绝对路径/event.csv \
  --output /绝对路径/book.csv
```

例如，假设输入文件就在当前工作区根目录：

```bash
/tmp/obr-build/obr_replay_event \
  --event ./event.csv \
  --output ./book.csv
```

正常结束时会看到类似输出：

```text
已重放 10 条事件，推导成交量 400，推导成交额 4016.0000，输出 ./book.csv
```

`--output` 可以省略：

```bash
/tmp/obr-build/obr_replay_event --event ./event.csv
```

此时程序会在当前命令所在目录写入 `book.csv`。

注意：当前 demo 会直接覆盖已经存在的输出文件，没有 `--overwrite` 参数；输出文件的
父目录也必须事先存在。

## 6. 查看结果

查看表头和前几行：

```bash
head -n 5 ./book.csv
```

查看总行数：

```bash
wc -l ./book.csv
```

输出是一条输入 Event 对应一条快照，因此：

```text
book.csv 总行数 = event.csv 数据行数 + 1 行表头
```

## 7. 运行项目自带的正常流程验证

```bash
/tmp/obr-build/obr_validate_reconstruction_core
```

预期输出：

```text
simple reconstruction validation passed
```

这个验证覆盖合法输入下的开盘集合竞价、连续多档成交、撤单、收盘集合竞价、剩余数量
入簿以及累计成交量和成交额；它不是畸形输入测试框架。

## 8. 修改代码后重新编译

修改 `.cpp` 或 `.hpp` 后，一般只需要再次运行：

```bash
cmake --build /tmp/obr-build --parallel
```

CMake 会只重新编译发生变化的文件。如果修改了 `CMakeLists.txt`，可以重新执行第 3 节
的两条完整命令。

## 9. 可选：使用 Sanitizer 编译

想检查明显的内存越界或未定义行为时，可以使用另一个构建目录：

```bash
cmake -S ./quant/obr -B /tmp/obr-build-sanitized \
  -DCMAKE_BUILD_TYPE=Debug \
  -DOBR_ENABLE_SANITIZERS=ON
cmake --build /tmp/obr-build-sanitized --parallel

/tmp/obr-build-sanitized/obr_validate_reconstruction_core
/tmp/obr-build-sanitized/obr_replay_event \
  --event ./event.csv \
  --output ./book-sanitized.csv
```

## 10. 当前 demo 常见问题

### 找不到 event.csv

优先使用绝对路径，或先用下面的命令确认文件实际位置：

```bash
pwd
ls -l ./event.csv
```

### 无法写入 book.csv

先确认输出父目录存在且当前用户有写权限。第一版不会自动创建目录。

### 集合竞价唯一候选价断言失败

当前 demo 不使用 reference price，约定集合竞价规则筛选后只有一个候选价。如果输入
出现最终并列，需要在后续版本补充正式并列规则，而不是在第一版中随意选择高价或低价。
