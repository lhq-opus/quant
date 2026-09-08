# Quick Start

Linux 已安装 `g++`，在 `quant` 根目录执行；替换原始 order、trade 和输出路径。
输出目录须存在，输出不能与任一输入同路径，会覆盖同名文件。不需要生成 event.csv：

```bash
g++ -std=c++11 -O2 -I ./obr/include ./obr/src/order_book.cpp ./obr/src/replay_event_main.cpp -o /tmp/obr_replay_event
/tmp/obr_replay_event --order "/path/to/order.csv" --trade "/path/to/trade.csv" --output "/path/to/book.csv"
```
