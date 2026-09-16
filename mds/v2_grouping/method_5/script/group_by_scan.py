from pathlib import Path

import pandas as pd


METHOD = Path(__file__).resolve().parents[1]
data = pd.read_csv(METHOD.parents[1] / "data_v2.csv")

# 首轮全量数据按大间隔切段，保存每只股票所属的初始扫描片段。
initial = data.iloc[:data["stock_id"].nunique()].copy()
initial["scan_segment"] = initial["clock"].diff().gt(100_000).cumsum() + 1
stock_to_scan_segment = initial.set_index("stock_id")["scan_segment"].to_dict()

first_stock = data.iloc[0]["stock_id"]

group_index = 1
# str -> int
stock_to_group_map = {first_stock:1}

# int -> list[str]
group = {1:[first_stock]}

threshold = 100

for i in range(1,len(data)):
    current_row = data.iloc[i]
    previous_row = data.iloc[i -1]

    current_stock = current_row["stock_id"]
    previous_stock = previous_row["stock_id"]

    delta_clock = int(current_row["clock"]) - int(previous_row["clock"])

    # 保留原合并逻辑，只增加“初始扫描片段不同”的条件。
    if (
        delta_clock <= threshold
        and stock_to_scan_segment[current_stock] != stock_to_scan_segment[previous_stock]
    ):
        previous_stock_group_index = stock_to_group_map[previous_stock]

        current_stock_group_index = stock_to_group_map.get(current_stock,0)

        if current_stock_group_index == previous_stock_group_index:
            continue

        previous_stock_group = group[previous_stock_group_index]

        if current_stock_group_index == 0:
            stock_to_group_map[current_stock] = previous_stock_group_index
            previous_stock_group.append(current_stock)

            continue

        # merge

        current_stock_group = group[current_stock_group_index]

        for stock in current_stock_group:
            stock_to_group_map[stock] = previous_stock_group_index
            previous_stock_group.append(stock)

        del group[current_stock_group_index]

    else:

        previous_stock_group_index = stock_to_group_map[previous_stock]

        current_stock_group_index = stock_to_group_map.get(current_stock,0)

        if current_stock_group_index == previous_stock_group_index:
            continue

        if current_stock_group_index != 0:
            continue

        group_index +=1
        stock_to_group_map[current_stock] = group_index
        group[group_index] = [current_stock]

pd.Series(stock_to_group_map, name="group_id").rename_axis("stock_id").to_csv(
    METHOD / "stock_groups.csv"
)
print("分组数:", len(group))
