#include "order_book.hpp"

#include <cstdint>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

// 两个输入文件各保留一条前瞻记录。文件内部已经按整数 CAA 非降序排列，
// 因而每次取较早的一条就能完成归并，不需要把全天事件读入内存再排序。
static std::ifstream order_input;
static std::ifstream trade_input;
static std::string order_line;
static std::string trade_line;
static int64_t order_caa = 0;
static int64_t trade_caa = 0;
static bool has_order = false;
static bool has_trade = false;

// 按已约定的合法 CSV 格式读取一行；到达 EOF 是正常的流式结束条件。
// 此处只提取第一列供归并使用，其余字段等到该记录被选中后再解析。
bool read_next_line(std::ifstream& input, std::string& line, int64_t& caa) {
  if (!std::getline(input, line)) {
    return false;
  }
  caa = std::stoll(line.substr(0, line.find(',')));
  return true;
}

// 返回当前 CAA 较小的记录，并只推进被选中的输入流。
// CAA 相等时沿用既定的委托优先规则；当前模型要求归并后仍保持相关 F
// 在下一张委托/撤单之前，具体顺序边界见 docs/replay.md。
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

// 每次打开都完整重置流状态，因此同一进程也可以从头回放另一组输入。
// 表头属于固定外部格式，只跳过一次，不增加表头猜测或字段合法性检查。
void open_inputs(const std::string& order_path, const std::string& trade_path) {
  if (order_input.is_open()) {
    order_input.close();
  }
  if (trade_input.is_open()) {
    trade_input.close();
  }
  order_input.clear();
  trade_input.clear();
  order_input.open(order_path.c_str());
  trade_input.open(trade_path.c_str());

  order_line.clear();
  trade_line.clear();
  order_caa = 0;
  trade_caa = 0;
  has_order = false;
  has_trade = false;

  std::string header;
  std::getline(order_input, header);
  std::getline(trade_input, header);
  has_order = read_next_line(order_input, order_line, order_caa);
  has_trade = read_next_line(trade_input, trade_line, trade_caa);
}

// 命令行使用 --order <路径> --trade <路径> [--output <路径>]。
// 参数按名称读取；省略输出参数时写入当前目录下的 book.csv。
struct CommandLineOptions {
  std::string order_path;
  std::string trade_path;
  std::string output_path;
};

CommandLineOptions parse_command_line(int argc, char* argv[]) {
  CommandLineOptions options;
  options.output_path = "book.csv";
  for (int index = 1; index < argc; index += 2) {
    const std::string option = argv[index];
    if (option == "--order") {
      options.order_path = argv[index + 1];
    } else if (option == "--trade") {
      options.trade_path = argv[index + 1];
    } else if (option == "--output") {
      options.output_path = argv[index + 1];
    }
  }
  return options;
}

// 当前输入是无引号转义的固定列 CSV。保留空列，避免 TradeBSFlag 等空字段
// 改变后续列的位置；这里只拆分当前记录，不保存已经处理的原始行。
std::vector<std::string> split_csv_line(const std::string& line) {
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

// TransactTime 按当前版本约定为 HHMMSSmmm 整数文本，除去毫秒即可判断阶段。
// 保留原实现的阶段划分：开盘集合竞价、连续竞价，其余记录归入收盘集合竞价。
TradingSession get_trading_session(const std::string& transaction_time) {
  const int64_t hhmmss = std::stoll(transaction_time) / 1000;
  if (hhmmss >= 91500 && hhmmss <= 92500) {
    return TradingSession::OpeningAution;
  }
  if ((hhmmss >= 93000 && hhmmss <= 113000) || (hhmmss >= 130000 && hhmmss < 145700)) {
    return TradingSession::ContinuousTrade;
  }
  return TradingSession::ClosingAuction;
}

// 委托按 my_obr_v2 的 20 列位置解析，价格已经是 1e-4 元整数，不再次缩放。
// SecurityID 用于沿用创业板判断；快照中的证券标识沿用第 9 列 secid。
Order parse_order(const std::vector<std::string>& columns) {
  Order order = {};
  /*
   * 0: clockAtArrival, 1: sequenceNo, 2: exchId
   * 3: securityType, 4: __isRepeated, 5: TransactTime
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
  order.security_id = columns[9];
  order.apply_seq_no = columns[7];
  order.is_CYB = std::stoll(columns[8]) >= 300000;
  order.generate_snapshot = order.trading_session == TradingSession::ContinuousTrade;
  order.side = columns[11][0] == '1' ? EventSide::Buy : EventSide::Sell;

  // 原始编码仍为 1=市价、2=限价、U=本方最优；合法输入下直接转换。
  if (columns[12][0] == '1') {
    order.order_type = OrderType::Market;
  } else if (columns[12][0] == '2') {
    order.order_type = OrderType::Limit;
  } else {
    order.order_type = OrderType::BBO;
  }

  order.price = std::stoll(columns[14]);
  order.quantity = std::stoll(columns[15]);
  order.order_appl_seq_num = std::stoll(columns[7]);
  return order;
}

// 成交文件按 my_obr_v2 的 22 列解析，保留 TradeMoney 的外部拼写。
// 重建状态只读取实际依赖的字段，成交金额由核心按成交价与成交量累计。
Trade parse_trade(const std::vector<std::string>& columns) {
  Trade trade = {};
  /*
   * 0: clockAtArrival, 1: sequenceNo, 2: exchId
   * 3: securityType, 4: __isRepeated, 5: TransactTime
   * 6: ChannelNo, 7: ApplSeqNum, 8: SecurityID, 9: secid
   * 10: mdSource, 11: ExecType, 12: TradeBSFlag, 13: __origTickSeq
   * 14: TradePrice, 15: TradeQty, 16: TradeMoney
   * 17: BidApplSeqNum, 18: OfferApplSeqNum, 19: BizIndex
   * 20: PacketID, 21: IsLastMsg
   */
  trade.caa = columns[0];
  trade.sequence_no = std::stoll(columns[1]);
  trade.transaction_time = columns[5];
  trade.channel_no = std::stoll(columns[6]);
  trade.trading_session = get_trading_session(trade.transaction_time);
  trade.security_id = columns[9];
  trade.apply_seq_no = columns[7];
  trade.trade_appl_seq_num = std::stoll(columns[7]);
  trade.is_CYB = std::stoll(columns[8]) >= 300000;
  trade.generate_snapshot = trade.trading_session == TradingSession::ContinuousTrade;
  trade.quantity = std::stoll(columns[15]);
  trade.bid_appl_seq_num = std::stoll(columns[17]);
  trade.offer_appl_seq_num = std::stoll(columns[18]);

  // 撤单独立触发快照；普通成交是否更新已有快照由核心的订单处理流程决定。
  if (columns[11] == "4") {
    trade.trade_type = TradeType::Cancel;
  } else {
    trade.trade_type = TradeType::Normal;
    trade.price = std::stoll(columns[14]);
    trade.generate_snapshot = false;
  }
  return trade;
}

// 状态中的价格和金额均以 1e-4 元为单位，输出统一保留两位小数。
// 先在整数域按四舍五入得到分，避免转换为 double 丢失较大累计金额的低位。
// 负值也采用绝对值四舍五入再恢复符号，且不对最小有符号整数直接取负。
std::string format_fixed_point(int64_t value) {
  const bool negative = value < 0;
  const uint64_t magnitude =
      negative ? static_cast<uint64_t>(-(value + 1)) + 1 : static_cast<uint64_t>(value);
  const uint64_t cents = magnitude / 100 + (magnitude % 100 >= 50 ? 1 : 0);
  std::ostringstream output;
  if (negative) {
    output << '-';
  }
  output << cents / 100 << '.' << std::setfill('0') << std::setw(2) << cents % 100;
  return output.str();
}

// 输出文件只打开一次、表头只写一次；保留当前版本的 bp4 和全部 30 列顺序。
void write_book_header(std::ofstream& output) {
  output << "caa,secid,sno,asn,tst,nts,cvl,cto,lpr,opx,bp5,bp4,bp3,bp2,bp1,ap1,ap2,ap3,ap4,ap5,"
            "bs5,bs4,bs3,bs2,bs1,as1,as2,as3,as4,as5\n";
}

// 每次只序列化一个已确定的连续竞价快照。未确定或已删除的快照没有输出行，
// 集合竞价仍更新盘口与统计，但当前输出约定不包含该阶段的快照。
void write_book_row(std::ofstream& output, const Snapshot& snapshot) {
  if (snapshot.trading_session != TradingSession::ContinuousTrade ||
      snapshot.status != SnapshotStatus::Ready) {
    return;
  }

  output << snapshot.caa << ',' << snapshot.security_id << ',' << snapshot.sequence_no << ','
         << snapshot.apply_seq_no << ',' << snapshot.transaction_time << ',' << snapshot.trade_count
         << ',' << snapshot.cumulative_trade_quantity << ','
         << format_fixed_point(snapshot.cumulative_turnover) << ','
         << format_fixed_point(snapshot.last_price) << ','
         << format_fixed_point(snapshot.opening_price);

  // 核心按最优到第五档保存；CSV 的买档反向输出，卖档保持正向。
  // 核心已为缺档补零，价格输出 0.00，数量输出 0。
  for (std::size_t index = 0; index < 5; ++index) {
    output << ',' << format_fixed_point(snapshot.bids[4 - index].price);
  }
  for (std::size_t index = 0; index < 5; ++index) {
    output << ',' << format_fixed_point(snapshot.asks[index].price);
  }
  for (std::size_t index = 0; index < 5; ++index) {
    output << ',' << snapshot.bids[4 - index].quantity;
  }
  for (std::size_t index = 0; index < 5; ++index) {
    output << ',' << snapshot.asks[index].quantity;
  }
  // 使用换行符保留标准流缓冲，不为每一条行情强制刷新文件。
  output << '\n';
}

// 成交可能一次确定多个待输出快照，因此每次状态推进后都取尽可输出结果。
// pop_snapshot 同时从核心队列移除已交付快照，避免累积全天快照。
void drain_snapshots(OrderBook& order_book, std::ofstream& output) {
  Snapshot snapshot = {};
  while (order_book.pop_snapshot(snapshot)) {
    write_book_row(output, snapshot);
  }
}

// 归并、解析、应用和输出形成单条记录的流水线；两路中的任一路先到 EOF，
// 都继续消费另一路，最后由 finish 收尾尚待确认的订单与快照。
void handle_event_loop(OrderBook& order_book, std::ofstream& output) {
  std::string line;
  bool is_order = false;
  while (read_line(line, is_order)) {
    const std::vector<std::string> columns = split_csv_line(line);
    if (is_order) {
      Order order = parse_order(columns);
      order_book.apply(order);
    } else {
      Trade trade = parse_trade(columns);
      order_book.apply(trade);
    }
    drain_snapshots(order_book, output);
  }
  order_book.finish();
  drain_snapshots(order_book, output);
}

// 一个回放实例对应一个证券、一个交易日，输入输出资源随 main 退出自动关闭。
int main(int argc, char* argv[]) {
  const CommandLineOptions options = parse_command_line(argc, argv);
  open_inputs(options.order_path, options.trade_path);
  std::ofstream output(options.output_path.c_str());
  write_book_header(output);

  OrderBook order_book;
  handle_event_loop(order_book, output);
  return 0;
}
