#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "order_book.hpp"

static std::ifstream order_input;
static std::ifstream trade_input;
static std::string order_line;
static std::string trade_line;
static int64_t order_caa = 0;
static int64_t trade_caa = 0;
static bool has_order = false;
static bool has_trade = false;

bool read_next_line(std::ifstream &input, std::string &line, int64_t &caa)
{
    if (!std::getline(input, line))
    {
        return false;
    }
    caa = std::stoll(line.substr(0, line.find(',')));
    return true;
}

bool read_line(std::string &line, bool &is_order)
{
    if (!has_order && !has_trade)
    {
        return false;
    }
    is_order = !has_trade || (has_order && order_caa <= trade_caa);
    if (is_order)
    {
        line = order_line;
        has_order = read_next_line(order_input, order_line, order_caa);
    }
    else
    {
        line = trade_line;
        has_trade = read_next_line(trade_input, trade_line, trade_caa);
    }
    return true;
}

void open_inputs(const std::string &order_path, const std::string &trade_path)
{

    order_input.open(order_path.c_str());
    trade_input.open(trade_path.c_str());

    order_caa = 0;
    trade_caa = 0;

    std::string header;
    std::getline(order_input, header);
    std::getline(trade_input, header);
    has_order = read_next_line(order_input, order_line, order_caa);
    has_trade = read_next_line(trade_input, trade_line, trade_caa);
}

struct CommandLineOptions
{
    std::string order_path;
    std::string trade_path;
    std::string output_path;
    std::string events_output_path;
};

CommandLineOptions parse_command_line(int argc, char *argv[])
{
    CommandLineOptions options;
    options.output_path = "book.csv";

    options.order_path = argv[2];
    options.trade_path = argv[4];
    options.output_path = argv[6];
    return options;
}

std::vector<std::string> split_csv_line(std::string line)
{
    std::vector<std::string> columns;
    std::string current_column;

    for (std::size_t index = 0; index <= line.size(); ++index)
    {
        if (index == line.size() || line[index] == ',')
        {
            columns.push_back(current_column);
            current_column.clear();
        }
        else
        {
            current_column += line[index];
        }
    }
    return columns;
}

TradingSession get_trading_session(const std::string transaction_time)
{
    std::string padded = transaction_time;
    if (padded.size() < 9)
    {
        padded = std::string(9 - padded.size(), '0') + padded;
    }
    const int hhmmss = std::atoi(padded.substr(0, 6).c_str());

    if (hhmmss >= 91500 && hhmmss <= 92500)
    {
        return TradingSession::OpeningAution;
    }
    if ((hhmmss >= 93000 && hhmmss <= 113000) || (hhmmss >= 130000 && hhmmss < 145700))
    {
        return TradingSession::ContinuousTrade;
    }
    return TradingSession::ClosingAuction;
}

Order parse_order(const std::vector<std::string> &columns)
{
    Order order = {};
    /*
     order:
      0: clockAtArrival, 1: sequenceNo, 2: exchId
      3: securityType, 4: __isRepeated, 5: TransactTime
      6: ChannelNo,7: ApplSeqNum,8: SecurityID, 9: secid
      10: mdSource, 11: Side,12: OrderType, 13: __origTickSeq
      14: Price, 15: OrderQty, 16: OrderIndex
      17: BizIndex, 18: PacketID, 19: IsLastMsg
     */
    order.caa = columns[0];
    order.sequence_no = std::stoll(columns[1]);
    order.transaction_time = columns[5];
    order.channel_no = std::stoll(columns[6]);
    order.trading_session = get_trading_session(order.transaction_time);
    order.security_id = columns[9];
    order.apply_seq_no = columns[7];

    order.is_CYB = static_cast<int64_t>(std::stoll(columns[8])) >= 300000;

    if (order.trading_session == TradingSession::ContinuousTrade)
    {
        order.generate_snapshot = true;
    }

    order.side = columns[11][0] == '1' ? EventSide::Buy : EventSide::Sell;

    if (columns[12][0] == '1')
    {
        order.order_type = OrderType::Market;
    }
    else if (columns[12][0] == '2')
    {
        order.order_type = OrderType::Limit;
    }
    else
    {
        order.order_type = OrderType::BBO;
    }

    order.price = static_cast<int64_t>(std::stoll(columns[14]));
    order.quantity = std::stoll(columns[15]);
    order.order_appl_seq_num = std::stoll(columns[7]);

    return order;
}

Trade parse_trade(const std::vector<std::string> &columns)
{
    Trade trade = {};

    /*
    trade:
    0: clockAtArrival, 1: sequenceNo, 2: exchId
    3: securityType, 4: __isRepeated, 5: TransactTime
    6: ChannelNo, 7: ApplSeqNum, 8: SecurityID, 9: secid
    10: mdSource, 11: ExecType, 12: TradeBSFlag, 13: __origTickSeq
    14: TradePrice, 15: TradeQty,16: TradeMoney
    17: BidApplSeqNum, 18: OfferApplSeqNum, 19: BizIndex
    20: PacketID, 21: IsLastMsg
    */

    trade.caa = columns[0];
    trade.sequence_no = std::stoll(columns[1]);
    trade.transaction_time = columns[5];
    trade.channel_no = std::stoll(columns[6]);
    trade.trading_session = get_trading_session(trade.transaction_time);
    trade.security_id = columns[9];
    trade.apply_seq_no = columns[7];

    trade.is_CYB = static_cast<int64_t>(std::stoll(columns[8])) >= 300000;

    if (trade.trading_session == TradingSession::ContinuousTrade)
    {
        trade.generate_snapshot = true;
    }

    trade.quantity = std::stoll(columns[15]);
    trade.bid_appl_seq_num = std::stoll(columns[17]);
    trade.offer_appl_seq_num = std::stoll(columns[18]);

    if (columns[11] == "4")
    {
        trade.trade_type = TradeType::Cancel;
    }
    else
    {
        trade.trade_type = TradeType::Normal;
        trade.price = static_cast<int64_t>(std::stoll(columns[14]));
        trade.generate_snapshot = false;
    }

    return trade;
}

Event parse_event(std::vector<std::string> columns, bool is_order)
{
    Event event = {};
    /*

    order:
    0: clockAtArrival, 1: sequenceNo, 2: exchId
    3: securityType, 4: __isRepeated, 5: TransactTime
    6: ChannelNo,7: ApplSeqNum,8: SecurityID, 9: secid
    10: mdSource, 11: Side,12: OrderType, 13: __origTickSeq
    14: Price, 15: OrderQty, 16: OrderIndex
    17: BizIndex, 18: PacketID, 19: IsLastMsg


    trade:
    0: clockAtArrival, 1: sequenceNo, 2: exchId
    3: securityType, 4: __isRepeated, 5: TransactTime
    6: ChannelNo, 7: ApplSeqNum, 8: SecurityID, 9: secid
    10: mdSource, 11: ExecType, 12: TradeBSFlag, 13: __origTickSeq
    14: TradePrice, 15: TradeQty,16: TradeMoney
    17: BidApplSeqNum, 18: OfferApplSeqNum, 19: BizIndex
    20: PacketID, 21: IsLastMsg

    */
    event.caa = columns[0];
    event.sequence_no = std::stoll(columns[1]);
    event.transaction_time = columns[5];
    event.channel_no = std::stoll(columns[6]);
    event.trading_session = get_trading_session(event.transaction_time);
    event.security_id = columns[9];
    event.apply_seq_no = columns[7];

    event.is_CYB = static_cast<int64_t>(std::stoll(columns[8])) >= 300000;

    if (event.trading_session == TradingSession::ContinuousTrade)
    {
        event.generate_snapshot = true;
    }

    if (is_order)
    {
        event.type = EventType::Order;
        event.side = columns[11][0] == '1' ? EventSide::Buy : EventSide::Sell;

        if (columns[12][0] == '1')
        {
            event.order_type = OrderType::Market;
        }
        else if (columns[12][0] == '2')
        {
            event.order_type = OrderType::Limit;
        }
        else
        {
            event.order_type = OrderType::BBO;
        }

        event.price = static_cast<int64_t>(std::stoll(columns[14]));
        event.quantity = std::stoll(columns[15]);
        event.order_appl_seq_num = std::stoll(columns[7]);
        event.need_handle = true;
    }
    else
    {
        event.quantity = std::stoll(columns[15]);
        event.bid_appl_seq_num = std::stoll(columns[17]);
        event.offer_appl_seq_num = std::stoll(columns[18]);

        if (columns[11] == "4")
        {
            event.type = EventType::Cancel;
            event.order_appl_seq_num = event.bid_appl_seq_num != 0 ? event.bid_appl_seq_num : event.offer_appl_seq_num;
            event.need_handle = true;
        }
        else
        {
            event.type = EventType::Trade;
            event.price = static_cast<int64_t>(std::stoll(columns[14]));
            event.need_handle = false;
            event.generate_snapshot = false;
        }
    }

    return event;
}

void append_events(const std::string &path, bool is_order, std::vector<Event> &events)
{

    std::ifstream input(path.c_str());

    std::string line;
    std::getline(input, line);

    while (std::getline(input, line))
    {
        const std::vector<std::string> columns = split_csv_line(line);
        events.push_back(parse_event(columns, is_order));
    }
}

bool cmp_events(const Event &left, const Event &right)
{
    return left.sequence_no < right.sequence_no;
}

std::vector<Event> read_events(const CommandLineOptions &options)
{

    std::vector<Event> events;

    append_events(options.order_path, true, events);
    append_events(options.trade_path, false, events);

    std::sort(events.begin(), events.end(), cmp_events);
    return events;
}

std::string format_fixed_point(int64_t value)
{
    std::ostringstream output;

    output << std::fixed << std::setprecision(2) << value / 10000.0;

    return output.str();
}

void write_book_row(std::ofstream &output, bool write_header, const Snapshot &snapshot)
{
    if (write_header)
    {
        output << "caa,secid,sno,asn,tst,nts,cvl,cto,lpr,opx,bp5,bp4,bp3,bp2,bp1,ap1,ap2,ap3,ap4,ap5,bs5,bs4,bs3,bs2,bs1,as1,as2,as3,as4,as5\n";
        return;
    }

    std::vector<Snapshot>::const_iterator snapshot = snapshots.begin();

    for (; snapshot != snapshots.end(); ++snapshot)
    {

        if (snapshot->trading_session != TradingSession::ContinuousTrade)
        {
            continue;
        }

        if (snapshot->status == SnapshotStatus::Deleted)
        {
            continue;
        }

        output << snapshot->caa;
        output << "," << snapshot->security_id;
        output << "," << snapshot->sequence_no;
        output << "," << snapshot->apply_seq_no;
        output << "," << snapshot->transaction_time;
        output << "," << snapshot->trade_count;
        output << "," << snapshot->cumulative_trade_quantity;
        output << "," << format_fixed_point(snapshot->cumulative_turnover);
        output << "," << format_fixed_point(snapshot->last_price);
        output << "," << format_fixed_point(snapshot->opening_price);

        for (std::size_t index = 0; index < 5; ++index)
        {
            output << ',';
            output << format_fixed_point(snapshot->bids[4 - index].price);
        }

        for (std::size_t index = 0; index < 5; ++index)
        {
            output << ',';
            output << format_fixed_point(snapshot->asks[index].price);
        }

        for (std::size_t index = 0; index < 5; ++index)
        {
            output << ',';
            output << snapshot->bids[4 - index].quantity;
        }

        for (std::size_t index = 0; index < 5; ++index)
        {
            output << ',';
            output << snapshot->asks[index].quantity;
        }

        output << '\n';
    }
}

void handle_event_loop(OrderBook& order_book)
{

    std::string line;
    bool is_order = false;

    for (;;)
    {
        if (!read_line(line, is_order))
        {
            break;
        }

        const std::vector<std::string> columns = split_csv_line(line);

        if (is_order)
        {
            Order order = parse_order(columns);
            order_book.apply(order);
        }
    }
}

int main(int argc, char *argv[])
{
    const CommandLineOptions options = parse_command_line(argc, argv);
    std::vector<Event> events = read_events(options);

    OrderBook order_book = {};

    open_inputs(options.order_path, options.trade_path);
    std::ofstream output(options.output_path.c_str());

    write_book_row(output, true, Snapshot{});

    for (std::size_t index = 0; index < events.size(); ++index)
    {
        if (events[index].trading_session == TradingSession::ClosingAuction)
        {
            break;
        }
        order_book.apply(events[index], events[index].trading_session);
    }

    order_book.finish();

    std::vector<Snapshot> snapshots = order_book.get_snapshots();

    write_book(options.output_path, snapshots);
}
