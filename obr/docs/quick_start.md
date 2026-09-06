# Quick Start

Linux 已安装 `g++`，在 `quant` 根目录执行；替换现有 12 列 event 和输出路径。输出目录须存在，输出不能与输入同路径，会覆盖同名文件：

```bash
g++ -std=c++11 -O2 -I ./obr/include ./obr/src/order_book.cpp ./obr/src/replay_event_main.cpp -o /tmp/obr_replay_event && /tmp/obr_replay_event --event "/path/to/event.csv" --output "/path/to/book.csv"
```
