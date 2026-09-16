# MDS Project Report

## Subtask 1: Recovering Four Fixed Stock Groups

### Approach

#### Initial focus on clock differences

At the beginning, I did not recognize that the key to this subtask was the relative order of stocks. Instead, I focused on differences in `clock`, assuming that stocks from the same upstream group would arrive close together, while records from different groups would be separated by larger gaps. This led to several attempts to recover fixed groups from timing information.

In these experiments, `time` identified a snapshot, while `clock` measured the arrival time of each record in microseconds. The objective was to recover a persistent stock-to-group mapping across snapshots. A cluster of nearby arrivals within one snapshot was only an intermediate observation: different groups could arrive close together, and some stocks could be absent from a snapshot.

#### Searching for a threshold in adjacent clock gaps

The first step was to calculate the `clock` difference between adjacent records belonging to the same snapshot. In [clock_delta.py](../clock_delta.py), the first record and records at a change in `time` receive a zero boundary marker. Positive gaps are sorted to inspect their distribution; boundary markers and nonpositive gaps are excluded from threshold estimation.

The initial detector looked for an abrupt increase in the sorted gaps. It calculated the differences between successive sorted values, estimated their typical positive size using the median and median absolute deviation (MAD), and selected the first jump exceeding both a statistical threshold and a multiple of the median. The gap immediately after that jump became the proposed separation threshold.

The difficulty was that the distribution was strongly skewed, with many repeated small gaps and a much smaller population of large gaps. Ignoring zero increments when estimating the background slope reduced the influence of those repetitions. A conspicuous jump in the sorted values therefore did not necessarily identify the boundary between within-group and between-group arrivals.

I also tried a histogram-based Triangle method during the threshold exploration. It used a logarithmic representation and several histogram resolutions to locate a bend after the dominant peak. This tended to identify where the dense population of very small gaps ended. However, the intended threshold was farther into the tail: intermediate gaps could still belong to the same group. That version was subsequently replaced.

The approach retained in [skewed_delta_threshold.py](../skewed_delta_threshold.py) searches for a local change in the upper tail. It preserves repeated observations, samples the sorted distribution between the 90th and 99.95th percentiles, and applies `log(1 + gap)` to reduce the influence of extreme values. Candidate thresholds leave between 0.5% and 5% of observations above them. At each candidate, the algorithm fits local slopes on either side, using a window covering 0.2% of the observations per side, and selects the largest right-to-left slope ratio. Earlier versions compared multiple window sizes and checked their agreement; the final exploratory version uses a single window for simplicity.

These methods produced candidate thresholds under assumptions about the shape and size of the tail. They did not establish that a particular gap was a true group boundary. In particular, the simplified upper-tail detector selects a candidate even when the distribution has no convincing separation.

#### Combining local timing clusters across snapshots

In [baseline_grouping.py](../baseline_grouping.py), I separated the problem into two stages. Within each snapshot, records were sorted by `clock`, and a new local cluster began whenever the adjacent gap reached or exceeded a threshold. Across snapshots, any pair of stocks that had appeared in different local clusters was permanently prohibited from sharing a final group. Stocks were then assigned greedily to the first group containing no conflicting member.

This rule attempted to use repeated snapshots to resolve occasional proximity between different groups. Its weakness was the permanence of a local decision: one incorrect split could prevent two stocks from ever being grouped together. Conversely, never observing a separation was not the same as having repeated evidence that two stocks belonged together. The quality of the final partition remained strongly dependent on the local threshold.

#### Comparing relative clock vectors

To examine timing relationships across many snapshots, I represented each stock as a vector. For stock `i` in snapshot `t`, its relative clock was defined as:

```text
relative_clock(i, t) = clock(i, t) - first_clock(t)
```

This produced a stock-by-snapshot table. Missing observations remained missing, rather than being filled with zero, because zero already represented a stock arriving at the snapshot's starting clock. Subtracting the common origin aligned snapshots for inspection; it did not change the clock difference between two stocks within a snapshot.

In [relative_clock_grouping.py](../relative_clock_grouping.py), a stock pair received one match whenever both stocks appeared in a snapshot and their clock difference was within a chosen tolerance. I recorded both the number of matches and the match rate:

```text
match_rate(i, j) = matching snapshots / snapshots in which both stocks appeared
```

Requiring both a minimum count and a minimum rate distinguished repeated proximity from a small number of coincidences, while avoiding penalizing a stock simply for being absent. The script's defaults—1,000 microseconds, at least two matches, and a match rate of at least 0.5—were adjustable experimental settings, not established business rules. These pairwise criteria were separate from the automated adjacent-gap threshold estimators.

I also explored alternative comparisons of the vectors. An earlier version of [relative_clock_grouping_v2.py](../relative_clock_grouping_v2.py) used Euclidean distance divided by the square root of the number of common snapshots, equivalent to root mean squared error (RMSE). It displayed a distance heatmap and a single-linkage hierarchy before cutting at a threshold. Normalization made distances less dependent on the number of available observations, but large timing deviations could still dominate the result, and single linkage allowed chains of intermediate matches to join distant stocks.

The current V2 instead calculates cosine similarity over snapshots where both stocks are present. It requires sufficient common observations before applying a similarity threshold, whose default is 0.99. This compares the direction of the timing vectors while ignoring their scale. That also creates a limitation: vectors such as `[1, 2]` and `[100, 200]` have cosine similarity 1 despite their different timing magnitudes. Insufficient shared evidence is retained as an unknown similarity rather than treated as a measured mismatch.

#### Turning pairwise relationships into fixed groups

The experiments also changed how pairwise compatibility was converted into groups. An early version used connected components, allowing indirect relationships to join stocks. I then required every pair within a group to satisfy the compatibility criteria. If `A–B` and `B–C` passed but `A–C` failed, the three stocks could no longer be merged into one group. This reduced chain-based merging, but could also fragment a true group when some pairs lacked sufficient observations.

Two grouping strategies were implemented under this all-pairs constraint. The `minimize` strategy sought the smallest number of compatible groups by treating incompatible pairs as graph-coloring conflicts. It combined a greedy solution, lower bounds, and bounded exact search, and reported whether the minimum had actually been proved. The alternative strategies, `rate_greedy` and `cosine_greedy`, processed the strongest relationships first and merged two existing groups only when all cross-group pairs were compatible. These greedy choices were not reversed, so they did not guarantee the fewest groups.

The scripts exported the underlying relationship matrices, and V1 also visualized relative clock vectors, making it possible to inspect the evidence behind a proposed partition. Nevertheless, finding an optimal partition for a chosen compatibility matrix did not validate the timing criterion used to construct that matrix.

#### Similarity gradients and subgroup structure

When inspecting the pairwise match rates, I noticed a pronounced gradient in similarity. Here, similarity meant the proportion of jointly observed snapshots in which the two stocks' clock difference was below the chosen threshold. For a given stock, approximately 10–15 other stocks had similarity above 80%, while each successive 10-percentage-point band below that level also contained roughly 10–15 stocks. The relationships extended across several similarity levels rather than separating cleanly into one highly similar set and unrelated stocks.

I interpreted this pattern as evidence of subgroup structure within larger stock groups. Stocks within a subgroup could remain close in clock, while different subgroups belonging to the same larger group could have substantial clock differences. This suggested that a strict timing-similarity criterion could identify smaller subgroups while splitting the larger groups I ultimately wanted to recover.

Using these timing relationships, I divided the stocks into nearly 300 subgroups. Inspecting their members revealed the observation that changed my approach: within each subgroup, the stocks maintained a strictly consistent relative order across all snapshots in which they appeared together. Missing stocks did not change the relative order of the members that were present.

#### Moving from timing magnitude toward relative order

The consistent ordering within these subgroups made me recognize relative stock order as an important grouping clue. I then examined this property explicitly with [relative_clock_order_check.py](../relative_clock_order_check.py), which checked whether the difference between two stocks' relative clocks retained the same strict sign across all snapshots where both appeared. Consistently positive or consistently negative differences indicated a stable ordering; a sign reversal or a tie failed the strict check. Pairs with no common observations were left undetermined.

The timing-based exploration had exposed smaller structures whose members preserved their order even as clock differences varied. This observation motivated the subsequent approach based on relative stock order. It did not yet determine how the nearly 300 subgroups should be combined into the four larger groups.

#### Merging subgroups using order consistency

I next attempted to merge the subgroups. My hypothesis was that if stocks within a subgroup maintained a strict relative order, the same property might extend to all stocks within a larger group. I therefore treated two subgroups as eligible for merging when every stock pair in their combined membership maintained a consistent strict order across the snapshots in which both stocks appeared. Checking only the existing order within each subgroup was insufficient; the ordering relationships between members of the two subgroups also had to remain consistent.

The order in which subgroups were merged affected the final partition. For Subtask 1, I used subgroup similarity to prioritize merges. The similarity between two subgroups was the average of the previously defined timing-based stock-pair similarities over all pairs with one stock in each subgroup:

```text
similarity(A, B) = sum(similarity(i, j) for i in A for j in B) / (|A| * |B|)
```

Here, `similarity(i, j)` was the fraction of jointly observed snapshots in which the stocks' clock difference was below the threshold. Higher average similarity gave a subgroup pair higher merge priority, while strict order consistency determined whether the merge was allowed.

This was a greedy heuristic: a merge could satisfy the order condition locally while restricting the combinations available later. The similarity ranking therefore influenced the result, without guaranteeing the desired final partition. In Subtask 1, where the number of groups was relatively small, the method happened to recover the four groups successfully. Its success in this case did not make the merge-priority rule generally reliable. The limitations of this approach become apparent in Subtask 2 and will be discussed there.

```text
Stock-pair similarities
          |
          | Apply a similarity threshold
          v
      Subgroups
          |
          | Merge higher-similarity subgroup pairs first
          | Similarity: mean of all cross-subgroup stock-pair similarities
          | Merge only if strict relative order is preserved
          v
    Final groups
  (4 in Subtask 1)
```

## Subtask 2: Recovering Eight Fixed Stock Groups

### Observation

The approach that succeeded in Subtask 1 did not transfer successfully to Subtask 2. I could not identify any distinguishing feature in the second dataset that explained why the same strategy should fail. I spent two to three days adjusting the order of subgroup merges, but none of these adjustments produced a stable partition. This exposed how strongly the earlier algorithm depended on its merge sequence: its success in Subtask 1 had not established a reliable way to recover larger groups.

### Approach

#### Establishing a lower bound with conflicting stocks

After receiving a hint, I realized that repeatedly merging subgroups from the bottom up was both unstable and unnecessary. I could instead start by identifying stocks that must belong to different groups, use them as initial group representatives, and then place subgroups into those groups as their assignments became determined.

I defined two stocks as conflicting if their relative order reversed across snapshots: one stock appeared before the other in one snapshot, but after it in another. Only snapshots containing both stocks were comparable. Under the assumption that all members of a group preserve a consistent relative order, conflicting stocks cannot belong to the same group.

To obtain initial representatives, I maintained a set of anchor stocks that were **pairwise conflicting**:

1. Choose any stock `a` as the first anchor and initialize `A = {a}`.
2. Find a stock that conflicts with **every stock already in `A`**. Add it as a new anchor. For example, adding `b` requires a conflict with `a`; adding `c` requires conflicts with both `a` and `b`.
3. Repeat until no remaining stock conflicts with every selected anchor.

If this process selects `k` anchors, each must belong to a different group, so the data require **at least `k` groups**. I initialize one group per anchor, each containing its representative stock. The condition is conflict with every selected representative, not merely a conflict with one member of the anchor set.

This construction finds a set of mutually conflicting stocks that cannot be extended by adding another stock. It does not necessarily find the largest such set: the initial stock and subsequent choices can affect the bound obtained. Therefore, `k` is a justified lower bound, not automatically the exact minimum or the true business group count.

#### Assigning subgroups only when their destination is unique

For each unassigned subgroup, I examined its compatibility with every current group. A group was a possible destination only if **no stock in the subgroup conflicted with any stock already in that group**. This required checking all cross-pairs, rather than comparing only a subgroup representative with the group's anchor.

```text
Candidates(S) = {G : no stock in subgroup S conflicts with any stock in group G}
```

If a subgroup had exactly one candidate group, I assigned it to that group. If it had multiple candidates, I left it pending instead of choosing one by similarity. As other subgroups were assigned, the groups acquired additional members and therefore additional conflict constraints. A previously ambiguous subgroup could then become incompatible with some of its candidate groups, leaving a single possible destination.

I repeated this process while new assignments were possible. If a full pass produced no new assignments, the remaining subgroups stayed unresolved. A subgroup with no compatible group required review of the current grouping assumptions or the number of initialized groups; adding more members to existing groups could not remove an already observed conflict.

The uniqueness of an assignment was conditional on the initialized groups being the complete set of destinations and on the subgroups being valid units. If all stocks could be assigned to `k` groups without internal conflicts, that partition would provide an upper bound of `k`, matching the lower bound from the anchors. Together, these would establish the minimum group count under the observed order constraints. The anchor-selection procedure alone did not establish this result.

#### Algorithm outline: order-conflict grouping

```text
Relative stock order across snapshots
                  |
                  v
Build stock-pair conflicts from order reversals
                  |
                  v
Choose one anchor stock
                  |
                  v
Repeatedly add a stock conflicting with EVERY existing anchor
Stop when no further stock can be added
                  |
                  v
k pairwise-conflicting anchors => at least k groups
Initialize one group per anchor
                  |
                  v
Find compatible groups for each pending subgroup
(no conflicts between any subgroup member and any group member)
                  |
       +----------+--------------+----------------+
       |                         |                |
       v                         v                v
Exactly one candidate     Multiple candidates   No candidates
       |                         |                |
       v                         v                v
Assign to that group       Keep pending       Flag for review
       |                         |
       +------------+------------+
                    |
                    v
Recheck pending subgroups after groups gain new members
                    |
                    v
Stop when no new assignments are possible
Report assigned groups and any unresolved subgroups
```

#### Finding additional boundaries from successor distributions

For the Subtask 2 dataset, the order-conflict algorithm produced only four groups. The relative-order constraints therefore did not expose the additional divisions needed to recover the eight groups.

Following a suggestion from Joyo, I examined which stock appeared immediately after each stock. I traversed the dataset in its original row order and counted every consecutive stock pair. For each stock `a`, I converted these counts into a distribution over its immediate successors:

```text
P(next stock = b | current stock = a)
    = count(a followed immediately by b) / sum_c count(a followed immediately by c)
```

For ordinary stocks, the successor distribution was strongly concentrated: a single stock typically accounted for approximately 50–90% of the following records. The terminal stocks of the four existing groups behaved differently. Their successor distributions were much more dispersed, with even the most frequent successor accounting for less than 10% of observations.

This contrast suggested a way to identify boundaries that order consistency alone had not revealed. I searched within each of the four groups for another stock with a similarly dispersed successor distribution. In each group, I found one such internal stock and used its position in the group's established order as a dividing point. Splitting each of the four groups into two yielded the eight-group partition.

The two stages used different aspects of the sequence: order conflicts established four broader groups, while the concentration of immediate-successor probabilities revealed an additional boundary inside each one. The observed 50–90% and below-10% ranges described the pattern that guided this analysis, rather than a universal threshold assumed in advance.

```text
Four groups from order-conflict analysis
                    |
                    v
Count immediate successors in the original dataset row order
                    |
                    v
Compare successor distributions
Ordinary stocks: one successor accounts for about 50–90%
Group-ending stocks: even the top successor accounts for less than 10%
                    |
                    v
Find one additional stock with a dispersed distribution inside each group
                    |
                    v
Use its position as an internal boundary
                    |
                    v
Split each of the four groups into two => eight groups
```

## Subtask 3: Recovering Six Groups from Clock Proximity

### Observation

Although the task description presented Subtask 3 as the most difficult, I found it relatively straightforward. Much of the logic I had developed earlier for grouping stocks by clock differences could be reused almost directly in this task.

An important complication was the coexistence of two update modes: a full update every 30 seconds and a group-based update every 3 seconds. The two modes used different stock partitions, so their interleaved records introduced relationships that did not all describe the same grouping structure. I did not recognize these two modes at the beginning. Instead, I carried over the group-and-subgroup model from the first two subtasks and immediately began designing a grouping rule.

### Approach

#### Interpreting the pre-market segments

I initially assumed that stocks were still organized into groups containing smaller subgroups. During the pre-market period, I used clock gaps between adjacent records to divide the initial stock sequence into 30 segments. I then interpreted each segment as potentially containing several subgroups drawn from different groups.

That interpretation was incorrect. Nevertheless, it led me to introduce a restriction that unexpectedly helped recover an almost correct partition: I distinguished close arrivals within the same pre-market segment from close arrivals across different segments.

#### Explaining close arrivals under the initial hypothesis

For adjacent records observed after the market opened, I considered three possible explanations for a very small clock gap, around 100 microseconds or less:

1. The two stocks belonged to the same subgroup.
2. They belonged to different subgroups within the same larger group.
3. They belonged to different subgroups whose update times happened to be extremely close, potentially even across different groups.

Under my interpretation of the pre-market segments, two stocks sharing a segment were not necessarily members of the same subgroup. Their temporal proximity therefore did not provide an unambiguous relationship. I instead treated a short clock gap between stocks from different segments as a likely connection between subgroups of the same larger group.

This was a heuristic inference. In particular, the possibility of coincident update times was not eliminated by the different-segment condition.

#### Connecting stocks across segments

I represented stocks as vertices in an undirected graph. An edge was added when two records were adjacent, their stocks belonged to different pre-market segments, and their clock gap was at most 100 microseconds. This is the central rule implemented in [method1](../v2_grouping/method1/script/rule_adjacent.py).

For example, suppose the pre-market segments contained `{a, b, c}` and `{d, e}`. If `a` and `c` appeared consecutively with a tiny clock gap, I did not add an edge: under the original segment interpretation, I could not determine whether they belonged to the same subgroup. If `a` and `d` appeared consecutively with a tiny gap, their different segment memberships allowed an edge. I interpreted this as evidence that they likely belonged to the same larger group, even if they came from different subgroups.

If another observation also supported an edge between `b` and `d`, the three stocks `a`, `b`, and `d` became connected. No direct edge between `a` and `b` was required.

```text
Pre-market segments:
    Segment 1: {a, b, c}       Segment 2: {d, e}

Adjacent arrivals with a tiny clock gap:
    a, c  -> same segment      -> no edge added by this rule
    a, d  -> different segments -> add edge a--d
    b, d  -> different segments -> add edge b--d

Resulting connected component:
    a ----- d ----- b
```

Applying this rule across the records produced six disconnected components, which I used as the six stock groups. The number six emerged from the connections rather than being imposed on the graph. The resulting partition was almost correct, despite the incorrect assumptions that had motivated the rule. This outcome did not validate my original interpretation of the segments as mixtures of subgroups; it showed that a useful grouping rule could arise from an incomplete understanding of the update mechanism.

#### Recognizing the two update modes

Further inspection revealed that, after the market opened, the same stock could be updated twice within less than one second. This led me to recognize two separate update mechanisms: full updates every 30 seconds, organized into 30 groups, and ordinary updates every 3 seconds, whose grouping was still to be inferred. The two stock partitions had no direct relationship. Ordinary updates were conditional on a stock's state changing, whereas the full-update stream also included stocks with no state changes.

This explained why the earlier rule had worked surprisingly well. By considering edges only between stocks from different pre-market segments, I had unintentionally excluded almost all of the influence of the 30-second full updates. Most short-gap adjacencies within a full-update segment could not create edges under that rule.

However, a small number of full-update records and ordinary-update records could happen to be adjacent and have extremely close clocks. Those mixed-stream adjacencies could still create unwanted edges, accidentally connecting otherwise separate components or attaching individual stocks to the wrong component. The appearance of six disconnected components was therefore encouraging, but did not by itself resolve the remaining contamination.

#### Filtering full updates before constructing the graph

I revised the workflow to filter full updates first and then construct stock relationships from the remaining records. I considered two filtering strategies:

1. **Match the pre-market segment sequences.** After the market opened, search for the same stock sequences observed in the pre-market segments and remove the matching records. The matches would be subsequences rather than necessarily contiguous blocks, allowing ordinary updates to be interleaved. The difficulty was identifying which occurrence of a stock belonged to the full update. A match could consume an ordinary-update record while leaving the corresponding full-update record behind.
2. **Remove closely spaced updates of the same stock.** For each stock, look for successive updates separated by less than a threshold, such as 2.5 seconds. Under the assumed three-second ordinary-update cadence, I treated such a pair as containing at least one full update. Removing both records avoided having to decide which one it was. This could also delete an ordinary update, and it could miss a full update when the stock had no state change and therefore no nearby ordinary update.

Both strategies could remove ordinary-update records and leave some full-update records behind. I chose the second because it was simpler to implement. The ordinary-update stream contained roughly five to ten times as many records as the full-update stream, so I expected sufficient statistical evidence to remain even after losing some ordinary updates.

Residual full updates required a separate safeguard in graph construction. Adjacency and a small clock gap alone could no longer be treated as sufficient evidence for an edge.

#### Selecting edges through frequent successors

After filtering, I examined each stock's successor distribution and ranked its successor candidates by how frequently they appeared. I used the top `n` successors of each stock to select graph edges, bringing the frequency of a relationship into the decision instead of relying only on an individual close arrival.

I varied `n` from 1 to 20. Every tested value produced six connected stock groups and five isolated stocks. The five isolated stocks had no state changes and appeared only in the full-update stream, so they supplied no ordinary-update evidence for assigning them to one of the six groups. I retained them as isolated stocks rather than interpreting them as five additional ordinary-update groups.

The six-group result therefore persisted across the tested range of successor counts. This was a more useful result than the initial partition alone: it followed explicit handling of the two update modes and a frequency-based selection of relationships, while leaving the stocks without ordinary-update evidence separate.

```text
Mixed full updates and ordinary updates
                  |
                  v
Find closely spaced updates of the same stock
(for example, less than 2.5 seconds apart)
                  |
                  v
Remove both records in each qualifying pair
                  |
                  v
Rank each stock's successor candidates by frequency
                  |
                  v
Select edges using the top n successors per stock
                  |
                  v
Find connected components
                  |
                  v
n = 1, 2, ..., 20: six groups + five isolated stocks
```
