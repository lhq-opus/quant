# C++ 订单簿：从编译到执行

当前程序使用 C++11。C++ 可执行文件读取 `event.csv`，输出简化五档 `book.csv`；
如果手里只有原始 `order.csv`、`trade.csv`，先用 Python 上游脚本生成 event。
Python 只负责这一步准备工作，不是 C++ 程序的运行依赖。

第一次使用，按第 1～3 节先编译并运行验证器，不需要准备任何行情数据。随后第 4 节
生成 event，第 5 节执行重放；已有最新 event 的话，可以跳过第 4 节。

## 1. 进入目录，检查工具

本文所有命令都在 **quant 仓库根目录**、同一个终端窗口中执行，不是在工作区根目录，
也不是在 `quant/obr/src` 里执行。当前电脑上的路径是：

```bash
cd /Users/hanqingliu/Desktop/obr/quant
pwd
ls ./obr/CMakeLists.txt
```

换电脑或移动项目后，只需把 `cd` 后的路径换成自己的 quant 目录。后续的 `./obr`
都是相对于这里的路径，不要再写成 `./quant/obr`。

本指南采用 macOS/Linux 终端和 Makefile 构建方式，需要以下工具：

- 支持 C++11 的编译器，例如 Apple Clang、Clang 或 GCC；
- CMake 3.20 或更高版本；
- Make。macOS 的 Command Line Tools 包含编译器和 Make。

```bash
c++ --version
cmake --version
make --version
```

这三条命令都应能显示版本。macOS 缺少编译工具时，可运行 `xcode-select --install`
并完成安装；若已安装 Homebrew 而缺少 CMake，可运行 `brew install cmake`。
这不是要求重新安装已有工具。C++ 部分仅依赖标准库，无需安装额外 C++ 库。

## 2. 编译 Debug 版本

先创建本次操作专用的临时目录，再配置和编译：

```bash
OBR_RUN_DIR="$(mktemp -d /tmp/obr-run.XXXXXX)"
echo "$OBR_RUN_DIR"

cmake -S ./obr -B "$OBR_RUN_DIR/build-debug" \
  -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Debug
cmake --build "$OBR_RUN_DIR/build-debug" --parallel 4
```

逐条理解：

- `mktemp -d` 创建一个新的独立目录，例如 `/tmp/obr-run.ABC123`，避免混入旧构建缓存。
  `OBR_RUN_DIR` 是保存该路径的终端变量，`"$OBR_RUN_DIR"` 表示取出它的值；
- `cmake -S ./obr` 指定源码目录，其中有 `CMakeLists.txt`，不是只编译某个 `.cpp`；
- `-B .../build-debug` 指定构建目录，保存中间文件、库和最后的可执行文件；
- `-G "Unix Makefiles"` 让 CMake 生成供 Make 使用的构建规则，保证本文的程序路径一致；
- `-DCMAKE_BUILD_TYPE=Debug` 选择便于学习和调试的配置；
- 第一条 CMake 命令是“配置”，第二条 `cmake --build` 才真正调用编译器编译、链接；
- `--parallel 4` 最多同时执行四个构建任务。代码的 C++11 标准由项目配置指定，无需再传。

多行命令末尾的 `\` 表示下一行仍属于同一条命令，后面不要再加空格。
每一步成功后再继续；出现错误时先处理错误，不要直接运行后续命令。

编译成功会生成两个可执行文件：

- `"$OBR_RUN_DIR/build-debug/obr_replay_event"`：读取 CSV 并重放订单簿；
- `"$OBR_RUN_DIR/build-debug/obr_validate_reconstruction_core"`：运行内置业务验证。

它们已经是程序，直接输入路径就能执行，不要用 `python3` 去运行它们。

`OBR_RUN_DIR` 只保存在当前终端。新开终端时，需要重新进入 quant，并将它设回前面
打印的真实路径，或者重新执行本节创建和编译。`/tmp` 可能被系统清理，正式需要保留的
重建结果请放到自己的数据目录；这里的临时路径用于演示，不是持久化方案。

## 3. 不用 CSV，先确认程序能运行

```bash
"$OBR_RUN_DIR/build-debug/obr_replay_event" --help
"$OBR_RUN_DIR/build-debug/obr_validate_reconstruction_core"
```

第一条打印如下命令格式，其中程序路径会随临时目录变化：

```text
用法: .../obr_replay_event --event <event.csv> [--output <book.csv>]
```

第二条验证成功时打印：

```text
simple reconstruction validation passed
```

验证器在内存中构造场景，不需要真实数据，也不会生成 book 文件。它覆盖集合竞价、
连续逐档成交、三类订单、动态挂价撤单、同价双边撤单、空盘口和累计成交统计。
它是业务验证程序，不是要用来处理你自己的 CSV 的入口。

## 4. 只有 order/trade：先生成 event.csv

这一节需要 Python 3 和 pandas。使用独立虚拟环境安装依赖，不修改系统 Python：

```bash
python3 --version
python3 -m venv "$OBR_RUN_DIR/venv"
"$OBR_RUN_DIR/venv/bin/python" -m pip install -r ./obr/requirements.txt
```

后续直接调用虚拟环境中的 Python，无需执行 `source .../activate`。依赖范围写在
`requirements.txt` 中。已有合规 event 时，整个第 4 节都不需要执行。

把下面两条赋值中的路径换成自己的原始文件路径，保留双引号以支持路径中的空格：

```bash
OBR_ORDER_CSV="/替换为你的数据目录/order.csv"
OBR_TRADE_CSV="/替换为你的数据目录/trade.csv"

mkdir -p "$OBR_RUN_DIR/output"
"$OBR_RUN_DIR/venv/bin/python" ./obr/script/build_cancel_event_csv.py \
  --order "$OBR_ORDER_CSV" \
  --trade "$OBR_TRADE_CSV" \
  --output "$OBR_RUN_DIR/output/event.csv"
```

`--order`、`--trade` 指定两份原始输入，`--output` 指定生成的事件文件。重新生成同一个
event 时，可以在这条 Python 命令最后加 `--overwrite`；脚本默认拒绝覆盖已有输出。

生成的是以下固定 12 列，列名和列顺序都不要改：

```text
caa,TransactionTime,Side,OrderType,Price,OrderQty,ExecType,TradeQty,TradePrice,ChannelNo,OrderApplSeqNum,AuctionPrice
```

几个与运行直接相关的约定：

- 原始 `TransactTime` 是 `HHMMSSmmm` 数字；上游补成九位 `TransactionTime`，例如
  `91500790` 变成 `091500790`。不要传旧课程的 ISO 时间字符串；
- `ChannelNo,OrderApplSeqNum` 标识原订单，供 C++ 撤单时查回实际挂单价；
- 原始 trade 要保留 `ExecType=F` 的集合竞价成交，上游据此填入 `AuctionPrice`，
  用于最终并列定价；F 不会额外生成重放事件，避免成交重复扣量；
- 原始两表都只包含同一个证券、同一个交易日的完整合法数据，不要混合多证券运行。

更完整的字段与转换解释见 [event 生成说明](cancel_event_csv.md)。

## 5. 用 C++ 重放 event.csv

如果刚执行了第 4 节，直接使用生成的路径：

```bash
OBR_EVENT_CSV="$OBR_RUN_DIR/output/event.csv"
```

如果已经有一份最新 12 列 event，则用下面这条赋值替代上面那条，并换成真实路径：

```bash
OBR_EVENT_CSV="/替换为你的数据目录/event.csv"
```

两种方式选一种。随后执行：

```bash
mkdir -p "$OBR_RUN_DIR/output"
"$OBR_RUN_DIR/build-debug/obr_replay_event" \
  --event "$OBR_EVENT_CSV" \
  --output "$OBR_RUN_DIR/output/book.csv"
```

`--event` 必填，C++ 不能直接接收 `--order`、`--trade`；`--output` 指定结果文件。
正常结束会打印已重放事件数、推导成交量、推导成交额和输出路径，具体数值取决于输入。

注意当前 C++ 的文件行为：

- 输出会直接覆盖已有同名文件，C++ 没有 `--overwrite` 参数；
- 输出路径必须与 event 和原始输入路径不同，程序不会替你检查同路径覆盖；
- 输出父目录必须先存在，因此命令中先执行 `mkdir -p`；
- 不传 `--output` 会写到当前目录的 `book.csv`。本文始终显式指定它，避免在 quant
  根目录生成文件。需要永久保存结果时，把输出改成你已有数据目录里的新文件路径。

## 6. 查看结果

```bash
head -n 5 "$OBR_RUN_DIR/output/book.csv"
wc -l "$OBR_EVENT_CSV" "$OBR_RUN_DIR/output/book.csv"
```

`head` 显示表头和前四条记录。对本上游生成的文件，event 与 book 的 `wc -l` 结果应
相同，且都包含一行表头。每条 order/撤单事件对应一条快照，而不是每条原始 trade 都
输出。`wc -l` 实际统计换行符，外部 event 的末行若没有换行，会少计一行，不代表少了事件。

当前输出表头固定为简化的 22 列：

```text
caa,event_type,bp1,bs1,bp2,bs2,bp3,bs3,bp4,bs4,bp5,bs5,ap1,as1,ap2,as2,ap3,as3,ap4,as4,ap5,as5
```

`bp/bs` 是买价和买量，`ap/as` 是卖价和卖量，数字 1～5 是档位。价格保留四位小数，
空档的价格和数量都为空。它还不是最初约定含 `cto/lpr/opx` 的完整 30 列 book；
累计成交量、成交额目前打印在终端，不是这份简化 CSV 的列。

## 7. 修改代码后的编译，以及可选构建方式

### 重新编译

修改 `.cpp` 或 `.hpp` 后，执行增量构建并重新验证，再按第 5 节运行：

```bash
cmake --build "$OBR_RUN_DIR/build-debug" --parallel 4
"$OBR_RUN_DIR/build-debug/obr_validate_reconstruction_core"
```

已编译好的程序不会随源码编辑自动更新。修改 `CMakeLists.txt` 后，可重跑第 2 节的
两条 CMake 命令，但无需重新创建 `OBR_RUN_DIR`。

### Release：用于运行较大的文件

Release 开启优化，但不改变业务规则。使用另一个构建目录，避免覆盖 Debug 版本：

```bash
cmake -S ./obr -B "$OBR_RUN_DIR/build-release" \
  -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build "$OBR_RUN_DIR/build-release" --parallel 4
"$OBR_RUN_DIR/build-release/obr_validate_reconstruction_core"
"$OBR_RUN_DIR/build-release/obr_replay_event" \
  --event "$OBR_EVENT_CSV" \
  --output "$OBR_RUN_DIR/output/book-release.csv"
```

### Sanitizer：检查内存与未定义行为

Apple Clang、Clang 或 GCC 可以使用项目已有的 ASan/UBSan 开关。它会增加运行开销，
用于检查实际执行到的路径，不代表证明所有输入都正确：

```bash
cmake -S ./obr -B "$OBR_RUN_DIR/build-sanitized" \
  -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Debug -DOBR_ENABLE_SANITIZERS=ON
cmake --build "$OBR_RUN_DIR/build-sanitized" --parallel 4
"$OBR_RUN_DIR/build-sanitized/obr_validate_reconstruction_core"
"$OBR_RUN_DIR/build-sanitized/obr_replay_event" \
  --event "$OBR_EVENT_CSV" \
  --output "$OBR_RUN_DIR/output/book-sanitized.csv"
```

在三种版本都重放了同一份 event 后，可以比较输出：

```bash
cmp "$OBR_RUN_DIR/output/book.csv" "$OBR_RUN_DIR/output/book-release.csv"
cmp "$OBR_RUN_DIR/output/book.csv" "$OBR_RUN_DIR/output/book-sanitized.csv"
```

两条 `cmp` 都不打印内容且退出码为 0，表示逐字节一致。

## 8. 常见问题与范围限制

- 找不到 `CMakeLists.txt`：先执行 `pwd` 和 `ls ./obr/CMakeLists.txt`，确认位于 quant
  根目录；不要在 `src` 下运行本文命令，也不要在源码目录直接执行 `cmake .`；
- 找不到可执行文件：检查编译是否成功，以及 `echo "$OBR_RUN_DIR"` 是否仍是原来的
  构建根路径。临时目录已经被清理的话，需要重新编译；
- `No module named pandas`：第 4 节安装和执行都要用同一个虚拟环境的 Python；
- 找不到 event：用 `ls -l "$OBR_EVENT_CSV"` 检查路径。旧的 8/9 列 event 不能直接
  交给新程序，应从原始两表重新生成，不要靠手工补空列；
- 无法写入 book：检查父目录是否存在、是否有写权限，并确保没有覆盖输入文件；
- 提示集合竞价候选价并列且缺少实际价格：给上游完整原始 trade，让它从开盘/收盘
  `ExecType=F` 取得 `AuctionPrice`，不要手工挑最高价或最低价；
- 参数名按文档完整拼写，每个路径参数后都要有值；当前 CLI 没有全面的误用检查。

本版仍假定 CAA 排序不存在业务顺序问题，`OrderType=1` 采用“即时成交剩余撤销”的
demo 约定：逐档成交、不限五档、余量不入簿，不是全部市价子类型实现。
C++ CSV 读取按固定列位置处理合法数据，
不支持引号内逗号等通用 CSV 格式。集合竞价结算状态写在该阶段最后一条事件上，
`AuctionPrice` 是读取完整文件后得到的离线信息，不能当作当时已知的实时价格。

业务细节见 [重放规则](event_replay_book.md)，代码职责见 [C++ 核心说明](reconstruction_core.md)。
