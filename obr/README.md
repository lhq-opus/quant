# OBR 订单簿重建

C++11 订单簿重建：直接读取原始 `order.csv`、`trade.csv`，按 `sequenceNo` 合并排序，
连续阶段由真实成交更新盘口，输出简化五档 `book.csv`，不需要 Python 预处理。

## 编译与执行

从 [C++ 编译执行指南](docs/build_and_run.md) 开始。文档包含从 quant 根目录操作的
完整命令、参数解释、无数据验证、原始 CSV 重放，以及 Debug/Release/Sanitizer 构建。
每条 order/撤单对应一条快照，快照包含下一条 order/撤单之前的成交，CAA 保留起点原值。

## 其他说明

- [C++ 事件处理、快照区间与代码结构](docs/reconstruction_core.md)
- [独立 Python 工具：生成 event](docs/cancel_event_csv.md)
- [独立 Python 工具：order 驱动的重放](docs/event_replay_book.md)
- [逐行对比 OBR 输出与答案](docs/compare_book_csv.md)
- [C++ 语法学习程序](study/README.md)

当前限定单证券、单交易日的完整合法输入；输出是简化 22 列，并非最初的完整 30 列
book。实际运行前请阅读指南中的文件覆盖注意事项。
