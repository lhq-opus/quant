#include "order_book.hpp"

#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <sys/stat.h>

struct CommandLineOptions {
  std::string order_path;
  std::string trade_path;
  std::string output_path;
  std::string events_output_path;
};

CommandLineOptions parse_command_line(int argc, char* argv[]) {
  CommandLineOptions options;
  options.output_path = "book.csv";
  bool has_output = false;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument != "--order" && argument != "--trade" && argument != "--output" &&
        argument != "--events-output") {
      throw std::invalid_argument("unknown option: " + argument);
    }
    if (index + 1 >= argc || std::string(argv[index + 1]).empty() ||
        std::string(argv[index + 1]).compare(0, 2, "--") == 0) {
      throw std::invalid_argument("missing path after " + argument);
    }
    const std::string path = argv[++index];
    if (argument == "--order") {
      if (!options.order_path.empty()) {
        throw std::invalid_argument("duplicate option: " + argument);
      }
      options.order_path = path;
    } else if (argument == "--trade") {
      if (!options.trade_path.empty()) {
        throw std::invalid_argument("duplicate option: " + argument);
      }
      options.trade_path = path;
    } else if (argument == "--output") {
      if (has_output) {
        throw std::invalid_argument("duplicate option: " + argument);
      }
      options.output_path = path;
      has_output = true;
    } else {
      if (!options.events_output_path.empty()) {
        throw std::invalid_argument("duplicate option: " + argument);
      }
      options.events_output_path = path;
    }
  }
  if (options.order_path.empty() || options.trade_path.empty()) {
    throw std::invalid_argument("both --order and --trade are required; use --help for usage");
  }

  // Resolve existing symlinks and compare inode identities before opening any
  // output.
  std::vector<std::string> paths;
  paths.push_back(options.order_path);
  paths.push_back(options.trade_path);
  paths.push_back(options.output_path);
  if (!options.events_output_path.empty()) {
    paths.push_back(options.events_output_path);
  }
  std::vector<std::string> resolved_paths;
  std::vector<struct stat> path_stats(paths.size());
  std::vector<bool> path_exists(paths.size(), false);
  for (std::size_t index = 0; index < paths.size(); ++index) {
    const std::string& path = paths[index];
    errno = 0;
    std::unique_ptr<char, void (*)(void*)> resolved(::realpath(path.c_str(), NULL), std::free);
    std::string normalized;
    if (resolved) {
      normalized = resolved.get();
    } else {
      const int error = errno;
      if (error != ENOENT || index < 2) {
        throw std::runtime_error("cannot resolve path " + path + ": " + std::strerror(error));
      }
      struct stat link_status = {};
      if (::lstat(path.c_str(), &link_status) == 0 && S_ISLNK(link_status.st_mode)) {
        throw std::runtime_error("cannot resolve dangling output symlink: " + path);
      }
      const std::size_t separator = path.find_last_of('/');
      const std::string directory =
          separator == std::string::npos ? "." : (separator == 0 ? "/" : path.substr(0, separator));
      const std::string filename =
          separator == std::string::npos ? path : path.substr(separator + 1);
      resolved.reset(::realpath(directory.c_str(), NULL));
      if (!resolved) {
        throw std::runtime_error("cannot resolve output directory " + directory + ": " +
                                 std::strerror(errno));
      }
      normalized = resolved.get();
      normalized += "/" + filename;
    }
    path_exists[index] = ::stat(path.c_str(), &path_stats[index]) == 0;
    if (path_exists[index] && !S_ISREG(path_stats[index].st_mode)) {
      throw std::runtime_error("path is not a regular file: " + path);
    }
    for (std::size_t previous = 0; previous < index; ++previous) {
      if (normalized == resolved_paths[previous] ||
          (path_exists[index] && path_exists[previous] &&
           path_stats[index].st_dev == path_stats[previous].st_dev &&
           path_stats[index].st_ino == path_stats[previous].st_ino)) {
        throw std::invalid_argument("input/output paths must be distinct: " + path + " and " +
                                    paths[previous]);
      }
    }
    resolved_paths.push_back(normalized);
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
  // The experimental input contract is HHMMSSmmm, optionally omitting leading
  // zeros.
  if (transaction_time.empty() || transaction_time.size() > 9 ||
      transaction_time.find_first_not_of("0123456789") != std::string::npos) {
    throw std::invalid_argument("TransactTime must be an integer HHMMSSmmm value: " +
                                transaction_time);
  }
  const std::string padded = std::string(9 - transaction_time.size(), '0') + transaction_time;
  const int hour = std::atoi(padded.substr(0, 2).c_str());
  const int minute = std::atoi(padded.substr(2, 2).c_str());
  const int second = std::atoi(padded.substr(4, 2).c_str());
  if (hour > 23 || minute > 59 || second > 59) {
    throw std::invalid_argument("invalid clock time in TransactTime: " + transaction_time);
  }
  const int hhmmss = std::atoi(padded.substr(0, 6).c_str());
  if (hhmmss >= 91500 && hhmmss <= 92500) {
    return TradingSession::OpeningAution;
  }
  if ((hhmmss >= 93000 && hhmmss <= 113000) || (hhmmss >= 130000 && hhmmss < 145700)) {
    return TradingSession::ContinuousTrade;
  }
  if (hhmmss >= 145700 && hhmmss <= 150000) {
    return TradingSession::ClosingAuction;
  }
  throw std::invalid_argument("TransactTime is outside the supported trading sessions: " +
                              transaction_time);
}

Event parse_event(std::vector<std::string> columns, bool is_order) {
  const std::size_t expected_columns = is_order ? 20 : 22;
  if (columns.size() != expected_columns) {
    throw std::invalid_argument("expected " + std::to_string(expected_columns) +
                                " CSV columns, got " + std::to_string(columns.size()));
  }
  const auto parse_integer = [&columns](std::size_t index, const char* name,
                                        int64_t minimum) -> int64_t {
    const std::string& raw = columns[index];
    if (raw.empty() || raw.find_first_not_of("0123456789") != std::string::npos) {
      throw std::invalid_argument(std::string(name) + " must contain only decimal digits: " + raw);
    }
    int64_t value = 0;
    try {
      std::size_t consumed = 0;
      value = std::stoll(raw, &consumed, 10);
      if (consumed != raw.size()) {
        throw std::invalid_argument("trailing characters");
      }
    } catch (const std::exception&) {
      throw std::invalid_argument(std::string(name) +
                                  " is outside the signed 64-bit range: " + raw);
    }
    if (value < minimum) {
      throw std::invalid_argument(std::string(name) + " must be >= " + std::to_string(minimum) +
                                  ": " + raw);
    }
    return value;
  };

  Event event = {};
  // Preserve vendor spelling at the CSV boundary; only fields used here get
  // semantics.
  if (columns[0].empty()) {
    throw std::invalid_argument("clockAtArrival must be nonempty");
  }
  if (columns[8].empty() || columns[9].empty()) {
    throw std::invalid_argument("SecurityID and secid must both be nonempty");
  }
  event.caa = columns[0];
  event.sequence_no = parse_integer(1, "sequenceNo", 0);
  event.transaction_time = columns[5];
  event.channel_no = parse_integer(6, "ChannelNo", 0);
  const int64_t application_sequence = parse_integer(7, "ApplSeqNum", 1);
  event.security_id = columns[8];
  event.secid = columns[9];
  event.trading_session = get_trading_session(event.transaction_time);
  event.generate_snapshot = event.trading_session == TradingSession::ContinuousTrade;
  event.quantity = parse_integer(15, is_order ? "OrderQty" : "TradeQty", 1);
  if (is_order) {
    if (columns[11] != "1" && columns[11] != "2") {
      throw std::invalid_argument("unsupported Side: " + columns[11]);
    }
    if (columns[12] != "1" && columns[12] != "2" && columns[12] != "U") {
      throw std::invalid_argument("unsupported OrderType: " + columns[12]);
    }
    event.type = EventType::Order;
    event.side = columns[11][0];
    event.order_type = columns[12][0];
    // Prices remain integer multiples of 0.0001, as in the existing experiment.
    event.price = parse_integer(14, "Price", event.order_type == '2' ? 1 : 0);
    event.order_appl_seq_num = application_sequence;
    event.need_handle = true;
  } else {
    if (columns[11] != "4" && columns[11] != "F") {
      throw std::invalid_argument("unsupported ExecType: " + columns[11]);
    }
    event.bid_appl_seq_num = parse_integer(17, "BidApplSeqNum", 0);
    event.offer_appl_seq_num = parse_integer(18, "OfferApplSeqNum", 0);
    if (columns[11] == "4") {
      if ((event.bid_appl_seq_num == 0) == (event.offer_appl_seq_num == 0)) {
        throw std::invalid_argument("cancel requires exactly one nonzero order reference");
      }
      event.type = EventType::Cancel;
      event.order_appl_seq_num =
          event.bid_appl_seq_num != 0 ? event.bid_appl_seq_num : event.offer_appl_seq_num;
      event.need_handle = true;
    } else {
      if (event.bid_appl_seq_num == 0 || event.offer_appl_seq_num == 0 ||
          event.bid_appl_seq_num == event.offer_appl_seq_num) {
        throw std::invalid_argument("trade requires two distinct nonzero order references");
      }
      event.type = EventType::Trade;
      event.price = parse_integer(14, "TradePrice", 1);
      event.need_handle = false;
      event.generate_snapshot = false;
    }
  }
  return event;
}

void append_events(const std::string& path, bool is_order, std::vector<Event>& events) {
  std::ifstream input(path.c_str());
  if (!input.is_open()) {
    throw std::runtime_error("cannot open input file: " + path);
  }
  const std::string expected_header =
      is_order ? "clockAtArrival,sequenceNo,exchld,securityType,__isRepeadted,"
                 "TransactTime,ChannelNo,"
                 "ApplSeqNum,SecurityID,secid,mdSource,Side,OrderType,__"
                 "origTickSeq,Price,OrderQty,"
                 "OrderIndex,BizIndex,PacketID,IsLastMsg"
               : "clockAtArrival,sequenceNo,exchld,securityType,__isRepeadted,"
                 "TransactTime,ChannelNo,"
                 "ApplSeqNum,SecurityID,secid,mdSource,ExecType,TradeBSFlag,__"
                 "origTickSeq,TradePrice,"
                 "TradeQty,TradyMoney,BidApplSeqNum,OfferApplSeqNum,BizIndex,"
                 "PacketID,IsLastMsg";
  std::string line;
  if (!std::getline(input, line)) {
    throw std::runtime_error(path + ":1: cannot read CSV header");
  }
  if (!line.empty() && line.back() == '\r') {
    line.pop_back();
  }
  if (line != expected_header) {
    throw std::invalid_argument(path + ":1: CSV header does not match the required schema");
  }
  std::size_t line_number = 1;
  while (std::getline(input, line)) {
    ++line_number;
    if (!line.empty() && line.back() == '\r') {
      line.pop_back();
    }
    try {
      if (line.find('"') != std::string::npos) {
        throw std::invalid_argument("quoted CSV fields are not supported");
      }
      const std::vector<std::string> columns = split_csv_line(line);
      Event event = parse_event(columns, is_order);
      event.source_path = path;
      event.source_line = line_number;
      events.push_back(event);
    } catch (const std::exception& error) {
      throw std::runtime_error(path + ":" + std::to_string(line_number) + ": " + error.what());
    }
  }
  if (input.bad() || !input.eof()) {
    throw std::runtime_error(path + ":" + std::to_string(line_number + 1) + ": CSV read failed");
  }
  input.clear();
  input.close();
  if (input.fail()) {
    throw std::runtime_error("cannot close input file: " + path);
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
  for (std::size_t index = 0; index < events.size(); ++index) {
    const Event& event = events[index];
    const std::string context = event.source_path + ":" + std::to_string(event.source_line) +
                                ": caa=" + event.caa +
                                ", sequenceNo=" + std::to_string(event.sequence_no) + ": ";
    if (event.security_id != events.front().security_id || event.secid != events.front().secid ||
        event.channel_no != events.front().channel_no) {
      throw std::invalid_argument(context +
                                  "this experiment accepts only one SecurityID/secid and channel");
    }
    if (index > 0 && event.sequence_no == events[index - 1].sequence_no) {
      throw std::invalid_argument(context + "duplicate sequenceNo; ordering would be ambiguous");
    }
    if (index > 0 && static_cast<int>(event.trading_session) <
                         static_cast<int>(events[index - 1].trading_session)) {
      throw std::invalid_argument(context + "trading session moves backwards in sequenceNo order");
    }
  }
  return events;
}

std::string format_fixed_point(int64_t value) {
  // Avoid floating-point rounding and avoid negating INT64_MIN.
  const uint64_t magnitude =
      value < 0 ? static_cast<uint64_t>(-(value + 1)) + 1 : static_cast<uint64_t>(value);
  std::ostringstream output;
  if (value < 0) {
    output << '-';
  }
  output << magnitude / 10000 << '.' << std::setw(4) << std::setfill('0') << magnitude % 10000;
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
    throw std::runtime_error("cannot open book output: " + path);
  }
  output << "caa,bp5,bp4,bp3,bp2,bp1,ap1,ap2,ap3,ap4,ap5,bs5,bs4,bs3,bs2,bs1,"
            "as1,as2,as3,as4,as5\n";
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
  output.close();
  if (!output) {
    throw std::runtime_error("cannot write/close book output: " + path);
  }
}

const char* event_type_text(EventType type) {
  if (type == EventType::Order) {
    return "order";
  }
  return type == EventType::Trade ? "trade" : "cancel";
}

void write_events(const std::string& path, const std::vector<Event>& events) {
  // This diagnostic export preserves the parsed replay order without changing
  // events.
  std::ofstream output(path.c_str());
  if (!output) {
    throw std::runtime_error("cannot open events output: " + path);
  }
  output << "caa,transaction_time,sequence_no,event_type,side,order_type,price,"
            "quantity,"
            "channel_no,order_appl_seq_num,bid_appl_seq_num,offer_appl_seq_num\n";
  std::vector<Event>::const_iterator event = events.begin();
  for (; event != events.end(); ++event) {
    output << event->caa << ',' << event->transaction_time << ',' << event->sequence_no << ','
           << event_type_text(event->type) << ',';
    // Execution events have no Side/OrderType; write empty fields instead of
    // NUL bytes.
    if (event->side != '\0') {
      output << event->side;
    }
    output << ',';
    if (event->order_type != '\0') {
      output << event->order_type;
    }
    // Export original event values, without substituting resolved resting-order
    // prices.
    output << ',' << format_fixed_point(event->price) << ',' << event->quantity << ','
           << event->channel_no << ',' << event->order_appl_seq_num << ','
           << event->bid_appl_seq_num << ',' << event->offer_appl_seq_num << '\n';
  }
  output.close();
  if (!output) {
    throw std::runtime_error("cannot write/close events output: " + path);
  }
}

int main(int argc, char* argv[]) {
  try {
    if (argc == 2 && std::string(argv[1]) == "--help") {
      std::cout << "Usage: my_obr --order ORDER.csv --trade TRADE.csv "
                   "[--output BOOK.csv] "
                   "[--events-output EVENTS.csv]\n"
                   "Prices are integer multiples of 0.0001; TransactTime uses "
                   "HHMMSSmmm.\n"
                   "Input must contain one instrument/channel and one trading "
                   "day's events.\n";
      if (!std::cout) {
        throw std::runtime_error("cannot write usage output");
      }
      return EXIT_SUCCESS;
    }
    const CommandLineOptions options = parse_command_line(argc, argv);
    std::vector<Event> events = read_events(options);
    if (!options.events_output_path.empty()) {
      write_events(options.events_output_path, events);
    }
    OrderBook order_book = {};
    for (std::size_t index = 0; index < events.size(); ++index) {
      try {
        order_book.build_trade_map(events[index]);
      } catch (const std::exception& error) {
        throw std::runtime_error(
            events[index].source_path + ":" + std::to_string(events[index].source_line) + ": caa=" +
            events[index].caa + ", sequenceNo=" + std::to_string(events[index].sequence_no) +
            ", order_id=" + std::to_string(events[index].order_appl_seq_num) + ": " + error.what());
      }
    }
    std::vector<Snapshot> snapshots;
    snapshots.reserve(events.size());
    for (std::size_t index = 0; index < events.size(); ++index) {
      try {
        order_book.apply(events[index], events[index].trading_session);
        const bool is_last_event_in_session =
            index + 1 == events.size() ||
            events[index + 1].trading_session != events[index].trading_session;
        const bool is_call_auction =
            events[index].trading_session == TradingSession::OpeningAution ||
            events[index].trading_session == TradingSession::ClosingAuction;
        if (is_call_auction && is_last_event_in_session) {
          order_book.finish_call_auction();
        }
        if (events[index].generate_snapshot) {
          snapshots.push_back(order_book.make_snapshot(events[index]));
        }
      } catch (const std::exception& error) {
        throw std::runtime_error(
            events[index].source_path + ":" + std::to_string(events[index].source_line) + ": caa=" +
            events[index].caa + ", sequenceNo=" + std::to_string(events[index].sequence_no) +
            ", order_id=" + std::to_string(events[index].order_appl_seq_num) + ": " + error.what());
      }
    }
    write_book(options.output_path, snapshots);
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << "my_obr: " << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
