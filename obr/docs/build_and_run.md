# C++ 订单簿：编译与执行

当前程序使用 C++11，直接读取原始 `order.csv`、`trade.csv`，输出简化五档
`book.csv`。不需要 Python 预处理，不接收 `--event`。

## 1. 进入 quant，检查工具

以下命令都在 **quant 仓库根目录**执行：

```bash
cd /Users/hanqingliu/Desktop/obr/quant
c++ --version
cmake --version
make --version
```

换电脑后替换cd路径。需要支持C++11的编译器、CMake 3.20或更高版本，以及Make。
macOS可使用Command Line Tools提供的Apple Clang，Linux可使用Clang或GCC。
C++只依赖标准库，无需安装pandas或第三方C++库。

## 2. 编译 Debug

```bash
OBR_RUN_DIR="$(mktemp -d /tmp/obr-run.XXXXXX)"
echo "$OBR_RUN_DIR"
cmake -S ./obr -B "$OBR_RUN_DIR/build-debug" \
  -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Debug
cmake --build "$OBR_RUN_DIR/build-debug" --parallel 4
```

`-S` 指源码目录，`-B` 指构建目录。第一条cmake配置工程，第二条才编译和链接。
CMakeLists.txt已指定C++11和严格警告，不需要在命令里再次选择标准。
多行命令结尾的反斜杠表示下一行仍属于同一条命令，反斜杠后不要加空格。

成功后会得到 `obr_replay_event` 和 `obr_validate_reconstruction_core`。
可执行文件名称不变，但输入已换成两份原始CSV，不提供旧参数兼容模式。

`OBR_RUN_DIR` 只在当前终端有效。新开终端时重新设置为打印出的目录，
或者重新创建、编译；需要长期保留的结果不要只放在/tmp中。

## 3. 先运行帮助和核心验证

```bash
"$OBR_RUN_DIR/build-debug/obr_replay_event" --help
"$OBR_RUN_DIR/build-debug/obr_validate_reconstruction_core"
```

帮助格式：

```text
用法: .../obr_replay_event --order <order.csv> --trade <trade.csv> [--output <book.csv>]
```

验证成功时打印 `simple reconstruction validation passed`。
验证器在内存中构造场景，不需要CSV；它不是处理实际行情的入口。

## 4. 直接重放原始两表

把下方两条输入路径换成自己的路径：

```bash
OBR_ORDER_CSV="/替换为你的数据目录/order.csv"
OBR_TRADE_CSV="/替换为你的数据目录/trade.csv"
mkdir -p "$OBR_RUN_DIR/output"

"$OBR_RUN_DIR/build-debug/obr_replay_event" \
  --order "$OBR_ORDER_CSV" \
  --trade "$OBR_TRADE_CSV" \
  --output "$OBR_RUN_DIR/output/book.csv"
```

两个输入参数都必填。保留全部正常成交和撤单，不要先把trade过滤成只有ExecType=4。
程序读取两表后按数字sequenceNo排序，不要求文件已经有序。

原始输入固定使用下列表头与列顺序，不重命名、不增加兼容别名：

order.csv：

```text
clockAtArrival,sequenceNo,exchld,securityType,__isRepeadted,TransactTime,ChannelNo,ApplSeqNum,SecurityID,secid,mdSource,Side,OrderType,__origTickSeq,Price,OrderQty,OrderIndex,BizIndex,PacketID,IsLastMsg
```

trade.csv：

```text
clockAtArrival,sequenceNo,exchld,securityType,__isRepeadted,TransactTime,ChannelNo,ApplSeqNum,SecurityID,secid,mdSource,ExecType,TradeBSFlag,__origTickSeq,TradePrice,TradeQty,TradyMoney,BidApplSeqNum,OfferApplSeqNum,BizIndex,PacketID,IsLastMsg
```

仍限定同一证券、同一交易日的完整合法数据，字段中没有逗号或引号。
TransactTime为HHMMSSmmm数字，例如91500790、100407190。
两侧成交引用和撤单引用使用ChannelNo与原订单ApplSeqNum。

文件行为保持简单：

- 命令行参数、输入文件可读、输出位置可写均由使用者保证，程序不检查或处理失败。
- 输出父目录必须已经存在。
- 输出不得与任一输入同路径，程序不做路径冲突检查。
- 输出会覆盖同名文件，没有 `--overwrite` 参数。
- 省略 `--output` 时写到当前目录的book.csv。建议始终明确指定输出路径，
  避免在quant根目录生成文件。

## 5. 查看输出与快照含义

```bash
head -n 5 "$OBR_RUN_DIR/output/book.csv"
```

输出保持原来的22列：

```text
caa,event_type,bp1,bs1,bp2,bs2,bp3,bs3,bp4,bs4,bp5,bs5,ap1,as1,ap2,as2,ap3,as3,ap4,as4,ap5,as5
```

价格保留四位小数，空档价量都为空。累计成交量和成交额打印在终端，
本轮不扩展为完整30列book。

每条order/撤单各输出一行，正常成交不单独输出。因此book数据行数等于
order数据行数加trade中的撤单行数，不等于两份输入的总行数。

例如 `order A → trade → trade → order B`：
A的快照包含中间两笔成交，CAA仍是A的clockAtArrival。
处理B之前才写出A；B和后面的成交进入下一条快照。最后一条在EOF补出。
同CAA的order/cancel也各自保留一行，程序不会按CAA合并或重新排序。

集合竞价沿用阶段末统一定价、扣量，真实集合成交不再重复扣量。
市价Price非零时的供应商挂价语义尚未确认，当前仍保留类型1不挂本方价档的约定。
细节和逐步示例见 [C++核心说明](reconstruction_core.md)。

## 6. 修改代码后重新编译

```bash
cmake --build "$OBR_RUN_DIR/build-debug" --parallel 4
"$OBR_RUN_DIR/build-debug/obr_validate_reconstruction_core"
```

可执行文件不会随源码自动更新。修改CMakeLists.txt后可重新执行配置命令。

## 7. Release 和 Sanitizer

Release使用独立目录，开启优化但不改变业务规则：

```bash
cmake -S ./obr -B "$OBR_RUN_DIR/build-release" \
  -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build "$OBR_RUN_DIR/build-release" --parallel 4
"$OBR_RUN_DIR/build-release/obr_validate_reconstruction_core"
"$OBR_RUN_DIR/build-release/obr_replay_event" \
  --order "$OBR_ORDER_CSV" --trade "$OBR_TRADE_CSV" \
  --output "$OBR_RUN_DIR/output/book-release.csv"
```

ASan/UBSan用于检查实际执行到的内存错误和未定义行为，不代表对所有输入的证明：

```bash
cmake -S ./obr -B "$OBR_RUN_DIR/build-sanitized" \
  -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Debug -DOBR_ENABLE_SANITIZERS=ON
cmake --build "$OBR_RUN_DIR/build-sanitized" --parallel 4
"$OBR_RUN_DIR/build-sanitized/obr_validate_reconstruction_core"
"$OBR_RUN_DIR/build-sanitized/obr_replay_event" \
  --order "$OBR_ORDER_CSV" --trade "$OBR_TRADE_CSV" \
  --output "$OBR_RUN_DIR/output/book-sanitized.csv"
```

三种构建读取同一份两表后，应输出相同结果：

```bash
cmp "$OBR_RUN_DIR/output/book.csv" "$OBR_RUN_DIR/output/book-release.csv"
cmp "$OBR_RUN_DIR/output/book.csv" "$OBR_RUN_DIR/output/book-sanitized.csv"
```

cmp没有输出且退出0表示逐字节一致。代码已在macOS上验证，不声称实跑Linux。

## 8. 常见问题

- 找不到CMakeLists.txt：检查当前目录是quant，不是在obr/src里执行。
- 找不到程序：先确认编译成功，以及OBR_RUN_DIR仍指向实际构建目录。
- 运行前准备好可读的order/trade和可写的输出目录；程序不提供文件打开失败提示。
- 集合竞价候选价并列：需要完整trade提供该阶段实际成交价，不手工猜最高或最低价。
- 所有CLI参数都要完整拼写，并带合法路径值；本版不做缺参、错误参数或非法CSV检查。
