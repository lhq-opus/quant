#include "order_book.hpp"

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

struct CommandLineOptions {
  std::string order_path;
  std::string trade_path;
  std::string output_path;
  std::string events_output_path;
};

CommandLineOptions parse_command_line(int argc, char* argv[]) {
  CommandLineOptions options;
  options.output_path = "book.csv";
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
    } else if (argument == "--events-output") {
      ++index;
      options.events_output_path = argv[index];
    }
  }
  return options;
}

std::vector<std::string> split_csv_line(std::string line) {
  std::vector<std::string> columns;
  std::string current_column;
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

TradingSession get_trading_session(const std::string transaction_time) {
  std::string padded = transaction_time;
  if (padded.size() < 9) {
    padded = std::string(9 - padded.size(), '0') + padded;
  }
  const int hhmmss = std::atoi(padded.substr(0, 6).c_str());
  if (hhmmss >= 91500 && hhmmss <= 92500) {
    return TradingSession::OpeningAution;
  }
  if ((hhmmss >= 93000 && hhmmss <= 113000) || (hhmmss >= 130000 && hhmmss < 145700)) {
    return TradingSession::ContinuousTrade;
  }
  return TradingSession::ClosingAuction;
}

Event parse_event(std::vector<std::string> columns, bool is_order) {
  Event event = {};
  /*
   * order:
   * 0: clockAtArrival, 1: sequenceNo, 2: exchId
   * 3: securityType, 4: __isRepeated, 5: TransactTime
   * 6: ChannelNo, 7: ApplSeqNum, 8: SecurityID, 9: secid
   * 10: mdSource, 11: Side, 12: OrderType, 13: __origTickSeq
   * 14: Price, 15: OrderQty, 16: OrderIndex
   * 17: BizIndex, 18: PacketID, 19: IsLastMsg
   *
   * trade:
   * 0: clockAtArrival, 1: sequenceNo, 2: exchId
   * 3: securityType, 4: __isRepeated, 5: TransactTime
   * 6: ChannelNo, 7: ApplSeqNum, 8: SecurityID, 9: secid
   * 10: mdSource, 11: ExecType, 12: TradeBSFlag, 13: __origTickSeq
   * 14: TradePrice, 15: TradeQty, 16: TradeMoney
   * 17: BidApplSeqNum, 18: OfferApplSeqNum, 19: BizIndex
   * 20: PacketID, 21: IsLastMsg
   */
  event.caa = columns[0];
  event.sequence_no = std::stoll(columns[1]);
  event.transaction_time = columns[5];
  event.channel_no = std::stoll(columns[6]);
  event.trading_session = get_trading_session(event.transaction_time);
  if (event.trading_session == TradingSession::ContinuousTrade) {
    event.generate_snapshot = true;
  }
  if (is_order) {
    event.type = EventType::Order;
    event.side = columns[11][0];
    event.order_type = columns[12][0];
    event.price = static_cast<int64_t>(std::stoll(columns[14]));
    event.quantity = std::stoll(columns[15]);
    event.order_appl_seq_num = std::stoll(columns[7]);
    event.need_handle = true;
  } else {
    event.quantity = std::stoll(columns[15]);
    event.bid_appl_seq_num = std::stoll(columns[17]);
    event.offer_appl_seq_num = std::stoll(columns[18]);
    if (columns[11] == "4") {
      event.type = EventType::Cancel;
      event.order_appl_seq_num =
          event.bid_appl_seq_num != 0 ? event.bid_appl_seq_num : event.offer_appl_seq_num;
      event.need_handle = true;
    } else {
      event.type = EventType::Trade;
      event.price = static_cast<int64_t>(std::stoll(columns[14]));
      event.need_handle = false;
      event.generate_snapshot = false;
    }
  }
  return event;
}

void append_events(const std::string& path, bool is_order, std::vector<Event>& events) {
  std::ifstream input(path.c_str());
  std::string line;
  std::getline(input, line);
  while (std::getline(input, line)) {
    const std::vector<std::string> columns = split_csv_line(line);
    events.push_back(parse_event(columns, is_order));
  }
}

bool cmp_events(const Event& left, const Event& right) {
  return left.sequence_no < right.sequence_no;
}

std::vector<Event> read_events(const CommandLineOptions& options) {
  std::vector<Event> events;
  append_events(options.order_path, true, events);
  append_events(options.trade_path, false, events);
  std::sort(events.begin(), events.end(), cmp_events);
  return events;
}

std::string format_fixed_point(int64_t value) {
  std::ostringstream output;
  output << std::fixed << std::setprecision(2) << value / 10000.0;
  return output.str();
}

void write_level(std::ofstream& output, const std::vector<PriceLevel>& levels, std::size_t index) {
  output << ',';
  if (index < levels.size()) {
    output << format_fixed_point(levels[index].price);
  }
  output << ',';
  if (index < levels.size()) {
    output << levels[index].quantity;
  }
}

void write_price(std::ofstream& output, const std::vector<PriceLevel>& levels, std::size_t index) {
  output << ',';
  if (index < levels.size()) {
    output << format_fixed_point(levels[index].price);
  }
}

void write_quantity(std::ofstream& output, const std::vector<PriceLevel>& levels,
                    std::size_t index) {
  output << ',';
  if (index < levels.size()) {
    output << levels[index].quantity;
  }
}

void write_book(const std::string& path, const std::vector<Snapshot>& snapshots) {
  std::ofstream output(path.c_str());
  if (!output) {
    std::cerr << "无法写入 book.csv: " << path << '\n';
    std::exit(EXIT_FAILURE);
  }
  output << "caa,bp5,bp4,bp3,bp2,bp1,ap1,ap2,ap3,ap4,ap5,bs5,bs4,bs3,bs2,bs1,as1,as2,as3,as4,as5\n";
  std::vector<Snapshot>::const_iterator snapshot = snapshots.begin();
  for (; snapshot != snapshots.end(); ++snapshot) {
    if (snapshot->trading_session != TradingSession::ContinuousTrade) {
      continue;
    }
    output << snapshot->caa;
    for (std::size_t index = 0; index < 5; ++index) {
      write_price(output, snapshot->bids, 4 - index);
    }
    for (std::size_t index = 0; index < 5; ++index) {
      write_price(output, snapshot->asks, index);
    }
    for (std::size_t index = 0; index < 5; ++index) {
      write_quantity(output, snapshot->bids, 4 - index);
    }
    for (std::size_t index = 0; index < 5; ++index) {
      write_quantity(output, snapshot->asks, index);
    }
    output << '\n';
  }
}

const char* event_type_text(EventType type) {
  if (type == EventType::Order) {
    return "order";
  }
  return type == EventType::Trade ? "trade" : "cancel";
}

void write_events(const std::string& path, const std::vector<Event>& events) {
  // 验证旁路只读取已经解析、合并和排序的 events，不修改事件，也不接触订单簿。
  // 输出包括真实成交，行序与随后重放完全相同；它不是旧版 Python event.csv 的结构。
  std::ofstream output(path.c_str());
  output << "caa,transaction_time,sequence_no,event_type,side,order_type,price,quantity,"
            "channel_no,order_appl_seq_num,bid_appl_seq_num,offer_appl_seq_num\n";
  std::vector<Event>::const_iterator event = events.begin();
  for (; event != events.end(); ++event) {
    output << event->caa << ',' << event->transaction_time << ',' << event->sequence_no << ','
           << event_type_text(event->type) << ',';
    // 成交和撤单没有解析 Side/OrderType，内部保留 '\0'；CSV 写空字段，不写 NUL 字节。
    if (event->side != '\0') {
      output << event->side;
    }
    output << ',';
    if (event->order_type != '\0') {
      output << event->order_type;
    }
    // 价格恢复为四位小数；无关数字字段的 0 如实保留。这里不会把 U 单实际挂价、
    // 原订单方向或价格反填进事件，因此可以直接核对解析结果，而不是重放后的状态。
    output << ',' << format_fixed_point(event->price) << ',' << event->quantity << ','
           << event->channel_no << ',' << event->order_appl_seq_num << ','
           << event->bid_appl_seq_num << ',' << event->offer_appl_seq_num << '\n';
  }
}

int main(int argc, char* argv[]) {
  const CommandLineOptions options = parse_command_line(argc, argv);
  std::vector<Event> events = read_events(options);
  write_events(options.events_output_path, events);
  OrderBook order_book = {};
  for (std::size_t index = 0; index < events.size(); ++index) {
    order_book.build_trade_map(events[index]);
  }
  std::vector<Snapshot> snapshots;
  snapshots.reserve(events.size());
  for (std::size_t index = 0; index < events.size(); ++index) {
    order_book.apply(events[index], events[index].trading_session);
    const bool is_last_event_in_session =
        events[index + 1].trading_session != events[index].trading_session;
    const bool is_call_auction = events[index].trading_session == TradingSession::OpeningAution;
    if (is_call_auction && is_last_event_in_session) {
      order_book.finish_call_auction();
    }
    if (events[index].generate_snapshot) {
      snapshots.push_back(order_book.make_snapshot(events[index]));
    }
  }
  write_book(options.output_path, snapshots);
}
