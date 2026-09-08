# OBR 订单簿重建

C++11 价格档级订单簿重放：Python 上游从原始 `order.csv`、`trade.csv` 生成固定
12 列 `event.csv`，C++ 读取 event 并输出简化五档 `book.csv`。

## 编译与执行

从 [C++ 编译执行指南](docs/build_and_run.md) 开始。文档包含从 quant 根目录操作的
完整命令、参数解释、无数据验证、原始 CSV 重放，以及 Debug/Release/Sanitizer 构建。
已有 event 时不需要运行 Python 上游。

## 其他说明

- [原始 order/trade 到 event 的转换](docs/cancel_event_csv.md)
- [订单簿重放规则与当前 demo 边界](docs/event_replay_book.md)
- [C++ 核心代码结构](docs/reconstruction_core.md)
- [逐行对比 OBR 输出与答案](docs/compare_book_csv.md)
- [C++ 语法学习程序](study/README.md)

当前限定单证券、单交易日的完整合法输入；输出是简化 22 列，并非最初的完整 30 列
book。实际运行前请阅读指南中的文件覆盖注意事项。
