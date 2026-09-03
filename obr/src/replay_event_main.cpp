#include "obr/order_book.hpp"

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

const obr::Price kFixedPointScale = 10000;

struct CommandLineOptions {
  std::string event_path;
  std::string output_path;
};

void print_usage(const char* program) {
  std::cout << "用法: " << program << " --event <event.csv> [--output <book.csv>]\n";
}

CommandLineOptions parse_command_line(int argc, char* argv[]) {
  CommandLineOptions options;
  options.output_path = "book.csv";

  // argv[0] 是程序自身，从 argv[1] 开始才是用户输入的参数。
  // 这里保留和 Python replay 相似的 --event、--output 写法，但不引入命令行库。
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--event") {
      ++index;
      options.event_path = argv[index];
    } else if (argument == "--output") {
      ++index;
      options.output_path = argv[index];
    }
  }
  return options;
}

std::vector<std::string> split_csv_line(const std::string& line) {
  std::vector<std::string> columns;
  std::string current_column;

  // 第一版输入保证字段里没有逗号和引号，所以逐字符遇到逗号就切一列即可。
  // 循环故意走到 index == line.size()，这样行尾空字段也能被保存。
  for (std::size_t index = 0; index <= line.size(); ++index) {
    if (index == line.size() || line[index] == ',') {
      columns.push_back(current_column);
      current_column.clear();
    } else {
      current_column += line[index];
    }
  }
  return columns;
}

obr::Price parse_price(const std::string& text) {
  // 把十进制价格手工转成万分之一单位，避免使用 double。
  // 例："10.10" -> whole="10"、fraction="10" -> 101000。
  const std::size_t point = text.find('.');
  const std::string whole = text.substr(0, point);
  std::string fraction;
  if (point != std::string::npos) {
    fraction = text.substr(point + 1);
  }

  while (fraction.size() < 4U) {
    fraction += '0';
  }
  if (fraction.size() > 4U) {
    fraction = fraction.substr(0, 4U);
  }

  const obr::Price whole_value = static_cast<obr::Price>(std::stoll(whole));
  const obr::Price fraction_value =
      fraction.empty() ? 0 : static_cast<obr::Price>(std::stoll(fraction));
  return whole_value * kFixedPointScale + fraction_value;
}

obr::Event parse_event(const std::vector<std::string>& columns) {
  // 固定列位置如下。输入表头已经约定好，所以第一版不再建立“列名 -> 下标”的 map：
  // 0 caa, 1 TransactionTime, 2 Side, 3 OrderType, 4 Price,
  // 5 OrderQty, 6 ExecType, 7 TradeQty, 8 TradePrice。
  obr::Event event;
  event.caa = columns[0];
  event.transaction_time = columns[1];

  if (columns[6] == "4") {
    // 撤单行：TradePrice 已由上游根据原订单引用补全。
    event.type = obr::EventType::Cancel;
    event.side = '\0';
    event.order_type = '\0';
    event.price = parse_price(columns[8]);
    event.quantity = static_cast<obr::Quantity>(std::stoll(columns[7]));
  } else {
    // order 行：直接读取 Side、OrderType、Price 和 OrderQty。
    // 当前 demo 的合法输入都是限价单，所以 order_type 只保存，不做分支判断。
    event.type = obr::EventType::Order;
    event.side = columns[2][0];
    event.order_type = columns[3][0];
    event.price = parse_price(columns[4]);
    event.quantity = static_cast<obr::Quantity>(std::stoll(columns[5]));
  }
  return event;
}

bool earlier_caa(const obr::Event& left, const obr::Event& right) { return left.caa < right.caa; }

std::vector<obr::Event> read_events(const std::string& path) {
  std::ifstream input(path.c_str());
  if (!input) {
    std::cerr << "无法打开 event.csv: " << path << '\n';
    std::exit(EXIT_FAILURE);
  }

  std::string line;
  std::getline(input, line); // 固定表头已知，第一版直接跳过第一行。

  std::vector<obr::Event> events;
  while (std::getline(input, line)) {
    const std::vector<std::string> columns = split_csv_line(line);
    events.push_back(parse_event(columns));
  }

  // stable_sort 与 pandas 的 stable 排序对应：caa 相同时保留 CSV 原有先后顺序。
  std::stable_sort(events.begin(), events.end(), earlier_caa);
  return events;
}

obr::TradingSession trading_session(const std::string& transaction_time) {
  // TransactionTime 左补零到 9 位后是 HHMMSSmmm。
  // 例如 91500790 -> 091500790，阶段判断只读取前六位 091500。
  std::string padded = transaction_time;
  if (padded.size() < 9U) {
    padded = std::string(9U - padded.size(), '0') + padded;
  }
  const int hhmmss = std::atoi(padded.substr(0, 6U).c_str());

  if (hhmmss >= 91500 && hhmmss <= 92500) {
    return obr::TradingSession::OpeningAuction;
  }
  if ((hhmmss >= 93000 && hhmmss <= 113000) || (hhmmss >= 130000 && hhmmss < 145700)) {
    return obr::TradingSession::ContinuousAuction;
  }

  // 输入保证剩余事件位于 14:57 至 15:00，所以直接归为收盘集合竞价。
  return obr::TradingSession::ClosingAuction;
}

const char* event_type_text(obr::EventType type) {
  return type == obr::EventType::Cancel ? "cancel" : "order";
}

std::string format_fixed_point(obr::Price value) {
  // 价格和成交额使用相同的万分之一缩放。
  // 例如内部整数 101000 在输出边界恢复成固定四位小数 10.1000。
  std::ostringstream output;
  output << value / kFixedPointScale << '.' << std::setw(4) << std::setfill('0')
         << value % kFixedPointScale;
  return output.str();
}

void write_level(std::ofstream& output, const std::vector<obr::PriceLevel>& levels,
                 std::size_t index) {
  // 每档总是写两个逗号分隔字段。档位不存在时保持两个空字段。
  output << ',';
  if (index < levels.size()) {
    output << format_fixed_point(levels[index].price);
  }
  output << ',';
  if (index < levels.size()) {
    output << levels[index].quantity;
  }
}

void write_book(const std::string& path, const std::vector<obr::Snapshot>& snapshots) {
  // ofstream 默认覆盖同名文件。这是第一版 demo，不额外实现 overwrite 策略。
  std::ofstream output(path.c_str());
  if (!output) {
    std::cerr << "无法写入 book.csv: " << path << '\n';
    std::exit(EXIT_FAILURE);
  }

  output << "caa,event_type,bp1,bs1,bp2,bs2,bp3,bs3,bp4,bs4,bp5,bs5,"
            "ap1,as1,ap2,as2,ap3,as3,ap4,as4,ap5,as5\n";

  std::vector<obr::Snapshot>::const_iterator snapshot = snapshots.begin();
  for (; snapshot != snapshots.end(); ++snapshot) {
    output << snapshot->caa << ',' << event_type_text(snapshot->event_type);

    for (std::size_t index = 0; index < 5U; ++index) {
      write_level(output, snapshot->bids, index);
    }
    for (std::size_t index = 0; index < 5U; ++index) {
      write_level(output, snapshot->asks, index);
    }
    output << '\n';
  }
}

} // namespace

int main(int argc, char* argv[]) {
  if (argc == 1 || (argc == 2 && std::string(argv[1]) == "--help")) {
    print_usage(argv[0]);
    return argc == 1 ? EXIT_FAILURE : EXIT_SUCCESS;
  }

  const CommandLineOptions options = parse_command_line(argc, argv);
  if (options.event_path.empty()) {
    print_usage(argv[0]);
    return EXIT_FAILURE;
  }

  const std::vector<obr::Event> events = read_events(options.event_path);
  std::vector<obr::TradingSession> sessions;
  sessions.reserve(events.size());

  std::vector<obr::Event>::const_iterator event = events.begin();
  for (; event != events.end(); ++event) {
    sessions.push_back(trading_session(event->transaction_time));
  }

  obr::OrderBook order_book;
  std::vector<obr::Snapshot> snapshots;
  snapshots.reserve(events.size());

  for (std::size_t index = 0; index < events.size(); ++index) {
    order_book.apply(events[index], sessions[index]);

    // 集合竞价最后一条输入完成后统一撮合，然后才生成这一条的快照。
    // 因此输出行数仍然与输入 Event 行数完全相同，不创建虚构的成交 Event。
    const bool is_call_auction = sessions[index] == obr::TradingSession::OpeningAuction ||
                                 sessions[index] == obr::TradingSession::ClosingAuction;
    const bool is_last_event_in_session =
        index + 1U == events.size() || sessions[index + 1U] != sessions[index];
    if (is_call_auction && is_last_event_in_session) {
      order_book.finish_call_auction();
    }

    snapshots.push_back(order_book.make_snapshot(events[index]));
  }

  write_book(options.output_path, snapshots);
  std::cout << "已重放 " << snapshots.size() << " 条事件，推导成交量 "
            << order_book.cumulative_trade_quantity() << "，推导成交额 "
            << format_fixed_point(order_book.cumulative_turnover()) << "，输出 "
            << options.output_path << '\n';
  return EXIT_SUCCESS;
}
