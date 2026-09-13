#include "order_book.hpp"

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

Order parse_order(const std::vector<std::string>& columns) {
  Order order = {};
  /*
   * order:
   * 0: clockAtArrival, 1: sequenceNo, 2: exchld
   * 3: securityType, 4: __isRepeadted, 5: TransactTime
   * 6: ChannelNo, 7: ApplSeqNum, 8: SecurityID, 9: secid
   * 10: mdSource, 11: Side, 12: OrderType, 13: __origTickSeq
   * 14: Price, 15: OrderQty, 16: OrderIndex
   * 17: BizIndex, 18: PacketID, 19: IsLastMsg
   */
  order.caa = columns[0];
  order.sequence_no = std::stoll(columns[1]);
  order.transaction_time = columns[5];
  order.channel_no = std::stoll(columns[6]);
  order.trading_session = get_trading_session(order.transaction_time);
  order.generate_snapshot = order.trading_session == TradingSession::ContinuousTrade;
  order.side = columns[11][0];
  order.order_type = columns[12][0];
  order.price = static_cast<int64_t>(std::stoll(columns[14]));
  order.quantity = std::stoll(columns[15]);
  order.order_appl_seq_num = std::stoll(columns[7]);
  return order;
}

Trade parse_trade(const std::vector<std::string>& columns) {
  Trade trade = {};
  /*
   * trade:
   * 0: clockAtArrival, 1: sequenceNo, 2: exchld
   * 3: securityType, 4: __isRepeadted, 5: TransactTime
   * 6: ChannelNo, 7: ApplSeqNum, 8: SecurityID, 9: secid
   * 10: mdSource, 11: ExecType, 12: TradeBSFlag, 13: __origTickSeq
   * 14: TradePrice, 15: TradeQty, 16: TradyMoney
   * 17: BidApplSeqNum, 18: OfferApplSeqNum, 19: BizIndex
   * 20: PacketID, 21: IsLastMsg
   */
  trade.caa = columns[0];
  trade.sequence_no = std::stoll(columns[1]);
  trade.transaction_time = columns[5];
  trade.channel_no = std::stoll(columns[6]);
  trade.trading_session = get_trading_session(trade.transaction_time);
  trade.trade_appl_seq_num = std::stoll(columns[7]);
  trade.quantity = std::stoll(columns[15]);
  trade.bid_appl_seq_num = std::stoll(columns[17]);
  trade.offer_appl_seq_num = std::stoll(columns[18]);
  if (columns[11] == "4") {
    trade.trade_type = TradeType::Cancel;
    trade.generate_snapshot = trade.trading_session == TradingSession::ContinuousTrade;
  } else {
    trade.trade_type = TradeType::Normal;
    trade.price = static_cast<int64_t>(std::stoll(columns[14]));
  }
  return trade;
}

// Each input is already ordered by numeric CAA. Keep one pending line per input.
class CsvReplayStream {
public:
  CsvReplayStream(const std::string& order_path, const std::string& trade_path)
      : order_input(order_path.c_str()), trade_input(trade_path.c_str()), order_caa(0),
        trade_caa(0), has_order(false), has_trade(false) {
    std::string header;
    std::getline(order_input, header);
    std::getline(trade_input, header);
    has_order = read_next_line(order_input, order_line, order_caa);
    has_trade = read_next_line(trade_input, trade_line, trade_caa);
  }

  bool read_line(std::string& line, bool& is_order) {
    if (!has_order && !has_trade) {
      return false;
    }
    is_order = !has_trade || (has_order && order_caa <= trade_caa);
    if (is_order) {
      line = order_line;
      has_order = read_next_line(order_input, order_line, order_caa);
    } else {
      line = trade_line;
      has_trade = read_next_line(trade_input, trade_line, trade_caa);
    }
    return true;
  }

private:
  bool read_next_line(std::ifstream& input, std::string& line, int64_t& caa) {
    if (!std::getline(input, line)) {
      return false;
    }
    caa = std::stoll(line.substr(0, line.find(',')));
    return true;
  }

  std::ifstream order_input;
  std::ifstream trade_input;
  std::string order_line;
  std::string trade_line;
  int64_t order_caa;
  int64_t trade_caa;
  bool has_order;
  bool has_trade;
};

void build_trade_map_from_csv(const std::string& order_path, const std::string& trade_path,
                              OrderBook& order_book) {
  CsvReplayStream input(order_path, trade_path);
  std::string line;
  bool is_order = false;
  while (input.read_line(line, is_order)) {
    // Order rows are scanned too; only trades contribute to the existing history map.
    if (!is_order) {
      const Trade trade = parse_trade(split_csv_line(line));
      order_book.build_trade_map(trade);
    }
  }
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

void write_book(std::ofstream& output, const Snapshot& snapshot) {
  if (snapshot.trading_session != TradingSession::ContinuousTrade) {
    return;
  }
  output << snapshot.caa;
  for (std::size_t index = 0; index < 5; ++index) {
    write_price(output, snapshot.bids, 4 - index);
  }
  for (std::size_t index = 0; index < 5; ++index) {
    write_price(output, snapshot.asks, index);
  }
  for (std::size_t index = 0; index < 5; ++index) {
    write_quantity(output, snapshot.bids, 4 - index);
  }
  for (std::size_t index = 0; index < 5; ++index) {
    write_quantity(output, snapshot.asks, index);
  }
  output << '\n';
}

const char* event_type_text(EventType type) {
  if (type == EventType::Order) {
    return "order";
  }
  return type == EventType::Trade ? "trade" : "cancel";
}

void write_event(std::ofstream& output, const Order& order) {
  output << order.caa << ',' << order.transaction_time << ',' << order.sequence_no << ','
         << event_type_text(EventType::Order) << ',';
  if (order.side != '\0') {
    output << order.side;
  }
  output << ',';
  if (order.order_type != '\0') {
    output << order.order_type;
  }
  output << ',' << format_fixed_point(order.price) << ',' << order.quantity << ','
         << order.channel_no << ',' << order.order_appl_seq_num << ",0,0\n";
}

void write_event(std::ofstream& output, const Trade& trade) {
  const bool is_cancel = trade.trade_type == TradeType::Cancel;
  const int64_t order_appl_seq_num =
      is_cancel ? (trade.bid_appl_seq_num != 0 ? trade.bid_appl_seq_num : trade.offer_appl_seq_num)
                : 0;
  // Preserve the existing CSV columns: side/type empty, original order ID for cancels only.
  output << trade.caa << ',' << trade.transaction_time << ',' << trade.sequence_no << ','
         << event_type_text(is_cancel ? EventType::Cancel : EventType::Trade) << ",,,"
         << format_fixed_point(trade.price) << ',' << trade.quantity << ',' << trade.channel_no
         << ',' << order_appl_seq_num << ',' << trade.bid_appl_seq_num << ','
         << trade.offer_appl_seq_num << '\n';
}

int main(int argc, char* argv[]) {
  const CommandLineOptions options = parse_command_line(argc, argv);
  OrderBook order_book = {};
  build_trade_map_from_csv(options.order_path, options.trade_path, order_book);

  CsvReplayStream input(options.order_path, options.trade_path);
  std::ofstream output(options.output_path.c_str());
  if (!output) {
    std::cerr << "无法写入 book.csv: " << options.output_path << '\n';
    std::exit(EXIT_FAILURE);
  }
  output << "caa,bp5,bp4,bp3,bp2,bp1,ap1,ap2,ap3,ap4,ap5,bs5,bs4,bs3,bs2,bs1,as1,as2,as3,as4,as5\n";
  std::ofstream events_output(options.events_output_path.c_str());
  events_output << "caa,transaction_time,sequence_no,event_type,side,order_type,price,quantity,"
                   "channel_no,order_appl_seq_num,bid_appl_seq_num,offer_appl_seq_num\n";

  std::string line;
  bool is_order = false;
  TradingSession previous_session = TradingSession::ContinuousTrade;
  for (;;) {
    // Read one raw record, convert it to its own type, then apply it.
    if (!input.read_line(line, is_order)) {
      break;
    }
    const std::vector<std::string> columns = split_csv_line(line);
    if (is_order) {
      Order order = parse_order(columns);
      if (previous_session == TradingSession::OpeningAution &&
          order.trading_session != previous_session) {
        order_book.finish_call_auction();
      }
      write_event(events_output, order);
      order_book.apply(order);
      if (order.generate_snapshot) {
        write_book(output, order_book.make_snapshot(order));
      }
      previous_session = order.trading_session;
    } else {
      const Trade trade = parse_trade(columns);
      if (previous_session == TradingSession::OpeningAution &&
          trade.trading_session != previous_session) {
        order_book.finish_call_auction();
      }
      write_event(events_output, trade);
      order_book.apply(trade);
      if (trade.generate_snapshot) {
        write_book(output, order_book.make_snapshot(trade));
      }
      previous_session = trade.trading_session;
    }
  }
  if (previous_session == TradingSession::OpeningAution) {
    order_book.finish_call_auction();
  }
}
