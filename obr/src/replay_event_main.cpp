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
  std::string order_path;
  std::string trade_path;
  std::string output_path;
};

void print_usage(const char* program) {
  std::cout << "用法: " << program
            << " --order <order.csv> --trade <trade.csv> [--output <book.csv>]\n";
}

CommandLineOptions parse_command_line(int argc, char* argv[]) {
  CommandLineOptions options;
  options.output_path = "book.csv";

  // argv[0] 是程序自身，从 argv[1] 开始才是用户输入的参数。
  // C++ 直接接收两份原始 CSV，不再读取 Python 生成的 event.csv。
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--order") {
      ++index;
      options.order_path = argv[index];
    } else if (argument == "--trade") {
      ++index;
      options.trade_path = argv[index];
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

obr::Event parse_event(const std::vector<std::string>& columns, bool is_order) {
  // 两份原始表的公共列位置相同：0 clockAtArrival、1 sequenceNo、5 TransactTime、
  // 6 ChannelNo、7 ApplSeqNum。只读取算法需要的列，不猜测其他供应商字段的含义。
  // {} 让无关数字字段从 0 开始，字符从 '\0' 开始，不需要写一长串占位参数。
  obr::Event event = {};
  event.caa = columns[0];
  event.sequence_no = std::stoll(columns[1]);
  event.transaction_time = columns[5];
  event.channel_no = std::stoll(columns[6]);

  if (is_order) {
    // order 独有列：11 Side、12 OrderType、14 Price、15 OrderQty。
    // 市价原始 Price 可以为空或为 0；这里保存原值含义，不用成交价替填。
    event.type = obr::EventType::Order;
    event.side = columns[11][0];
    event.order_type = columns[12][0];
    event.price = columns[14].empty() ? 0 : parse_price(columns[14]);
    event.quantity = std::stoll(columns[15]);
    event.order_appl_seq_num = std::stoll(columns[7]);
  } else {
    // trade 独有列：11 ExecType、14 TradePrice、15 TradeQty、
    // 17 BidApplSeqNum、18 OfferApplSeqNum。F 和 4 都进入事件流，不再过滤 F。
    event.quantity = std::stoll(columns[15]);
    event.bid_appl_seq_num = std::stoll(columns[17]);
    event.offer_appl_seq_num = std::stoll(columns[18]);
    if (columns[11] == "4") {
      event.type = obr::EventType::Cancel;
      // 合法撤单恰好一侧引用非零；trade 自己的 ApplSeqNum 不是被撤订单的编号。
      event.order_appl_seq_num =
          event.bid_appl_seq_num != 0 ? event.bid_appl_seq_num : event.offer_appl_seq_num;
    } else {
      event.type = obr::EventType::Trade;
      event.price = parse_price(columns[14]);
    }
  }
  return event;
}

bool earlier_sequence(const obr::Event& left, const obr::Event& right) {
  // 比较整数，而不是字符串：sequenceNo=2 必须排在 sequenceNo=10 前。
  return left.sequence_no < right.sequence_no;
}

void append_events(const std::string& path, bool is_order, std::vector<obr::Event>& events) {
  std::ifstream input(path.c_str());
  if (!input) {
    std::cerr << "无法打开输入 CSV: " << path << '\n';
    std::exit(EXIT_FAILURE);
  }

  std::string line;
  std::getline(input, line); // 固定表头已知，第一版直接跳过第一行。

  while (std::getline(input, line)) {
    const std::vector<std::string> columns = split_csv_line(line);
    events.push_back(parse_event(columns, is_order));
  }
}

std::vector<obr::Event> read_events(const CommandLineOptions& options) {
  std::vector<obr::Event> events;
  append_events(options.order_path, true, events);
  append_events(options.trade_path, false, events);

  // 先合并全部行，再按 sequenceNo 排序，不按 caa 排序，也不合并相同 caa 的订单。
  // stable_sort 在 sequenceNo 相同时保留装入顺序：各表原始行序，order 在 trade 前。
  std::stable_sort(events.begin(), events.end(), earlier_sequence);
  return events;
}

obr::TradingSession trading_session(const std::string& transaction_time) {
  // TransactTime 左补零到 9 位后是 HHMMSSmmm。
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
  if (options.order_path.empty() || options.trade_path.empty()) {
    print_usage(argv[0]);
    return EXIT_FAILURE;
  }

  const std::vector<obr::Event> events = read_events(options);
  std::vector<obr::TradingSession> sessions;
  sessions.reserve(events.size());

  std::vector<obr::Event>::const_iterator event = events.begin();
  for (; event != events.end(); ++event) {
    sessions.push_back(trading_session(event->transaction_time));
  }

  obr::OrderBook order_book;
  std::vector<obr::Snapshot> snapshots;
  snapshots.reserve(events.size());

  // pending_index 指向尚未输出快照的 order/cancel。events.size() 表示还没有区间。
  // 这里只记起点，不提前复制盘口：后面到达的真实成交还要更新这条快照的状态。
  std::size_t pending_index = events.size();
  obr::Price auction_price = 0;
  for (std::size_t index = 0; index < events.size(); ++index) {
    if (events[index].type != obr::EventType::Trade) {
      // 新区间左边界到达时，先输出上一区间，再处理当前 order/cancel。
      // 这样当前订单和它后面的成交不会被错误地计入上一条 snapshot。
      if (pending_index != events.size()) {
        snapshots.push_back(order_book.make_snapshot(events[pending_index]));
      }
      pending_index = index;
    }

    order_book.apply(events[index], sessions[index]);

    // 集合竞价保留原算法：积累申报，在阶段末统一定价、扣量。
    // 真实集合 F 提供并列时使用的实际成交价，但 apply 不再对它单独扣量。
    const bool is_call_auction = sessions[index] == obr::TradingSession::OpeningAuction ||
                                 sessions[index] == obr::TradingSession::ClosingAuction;
    if (is_call_auction && events[index].type == obr::EventType::Trade) {
      auction_price = events[index].price;
    }
    const bool is_last_event_in_session =
        index + 1U == events.size() || sessions[index + 1U] != sessions[index];
    if (is_call_auction && is_last_event_in_session) {
      order_book.finish_call_auction(auction_price);
      auction_price = 0; // 开盘价不能作为收盘集合竞价的实际价提示。
    }
  }
  // EOF 后没有下一条 order/cancel 帮我们收尾，最后一条必须在此补出。
  if (pending_index != events.size()) {
    snapshots.push_back(order_book.make_snapshot(events[pending_index]));
  }

  write_book(options.output_path, snapshots);
  std::cout << "已重放 " << events.size() << " 条事件，输出 " << snapshots.size()
            << " 条快照，累计成交量 " << order_book.cumulative_trade_quantity() << "，累计成交额 "
            << format_fixed_point(order_book.cumulative_turnover()) << "，输出 "
            << options.output_path << '\n';
  return EXIT_SUCCESS;
}
