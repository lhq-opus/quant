"""A deliberately simple snapshot-based stock grouping baseline.

This module turns each distinct ``time`` value into one snapshot, sorts that
snapshot by ``clock``, and cuts a new local group whenever the adjacent clock
gap is greater than or equal to a detected threshold. It then combines local
groups into one fixed ``stock_id -> group_id`` mapping.

The baseline intentionally gives absolute priority to the user's first rule:
if two stocks are separated in any snapshot where both appear, they can never
belong to the same final group. A missing stock contributes no evidence in that
snapshot.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from numbers import Integral
from pathlib import Path
from typing import Sequence

import pandas as pd
from pandas.api.types import is_integer_dtype, is_unsigned_integer_dtype

from .clock_delta import (
    DEFAULT_MIN_SEGMENT_SIZE,
    DEFAULT_MIN_SLOPE_MULTIPLIER,
    DEFAULT_ROBUST_Z_THRESHOLD,
    MAX_INT64,
    find_abrupt_increase,
)


REQUIRED_COLUMNS = ("clock", "stock_id", "time")
OUTPUT_COLUMNS = ("stock_id", "group_id")
Pair = tuple[str, str]
MembershipHistory = dict[str, dict[str, int]]


@dataclass(frozen=True)
class BaselineGroupingResult:
    """Grouping output plus diagnostics that explain the baseline run."""

    mapping: pd.DataFrame
    threshold: int
    threshold_source: str
    snapshot_count: int
    local_group_count: int
    positive_pair_count: int
    blocked_merge_count: int

    @property
    def final_group_count(self) -> int:
        """Return the number of final fixed groups."""

        if self.mapping.empty:
            return 0
        return int(self.mapping["group_id"].nunique())


class _UnionFind:
    """Maintain final components while exposing their member sets."""

    def __init__(self, stock_ids: Sequence[str]) -> None:
        self._parent = {stock_id: stock_id for stock_id in stock_ids}
        self._members = {stock_id: {stock_id} for stock_id in stock_ids}

    def find(self, stock_id: str) -> str:
        """Return the component root and compress the lookup path."""

        parent = self._parent[stock_id]
        if parent != stock_id:
            self._parent[stock_id] = self.find(parent)
        return self._parent[stock_id]

    def members(self, root: str) -> set[str]:
        """Return members of a root component."""

        return self._members[root]

    def union(self, first_root: str, second_root: str) -> str:
        """Merge two roots deterministically and return the surviving root."""

        # Roots are always the lexicographically smallest stock in a component.
        # Keeping that invariant makes group construction reproducible.
        surviving_root, absorbed_root = sorted((first_root, second_root))
        self._parent[absorbed_root] = surviving_root
        self._members[surviving_root].update(self._members.pop(absorbed_root))
        return surviving_root

    def components(self) -> list[set[str]]:
        """Return all current member sets."""

        return list(self._members.values())


def _ordered_pair(stock_a: str, stock_b: str) -> Pair:
    """Return a stable key for an unordered stock pair."""

    if stock_a <= stock_b:
        return stock_a, stock_b
    return stock_b, stock_a


def _normalize_market_data(data: pd.DataFrame) -> pd.DataFrame:
    """Validate the baseline assumptions and normalize the three used columns."""

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"missing required CSV column(s): {missing}")

    if data.empty:
        raise ValueError("cannot group an empty market data table")
    if data["stock_id"].isna().any():
        raise ValueError("stock_id contains missing values")
    if data["time"].isna().any():
        raise ValueError("time contains missing values")
    if data["clock"].isna().any():
        raise ValueError("clock contains missing values")

    try:
        clock = pd.to_numeric(data["clock"], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError("clock must contain integer microsecond timestamps") from error

    if not is_integer_dtype(clock.dtype):
        raise ValueError("clock must contain integer microsecond timestamps")
    if is_unsigned_integer_dtype(clock.dtype) and clock.max() > MAX_INT64:
        raise ValueError("clock contains a value outside the signed 64-bit range")

    normalized = pd.DataFrame(
        {
            "clock": clock.astype("int64"),
            "stock_id": data["stock_id"].astype("string"),
            "time": data["time"].astype("string"),
            "_row_order": range(len(data)),
        }
    )

    # Whether one stock may have multiple records in one three-second snapshot
    # remains a business question. This first baseline assumes at most one and
    # rejects ambiguous input instead of silently inventing semantics.
    duplicated = normalized.duplicated(subset=["time", "stock_id"], keep=False)
    if duplicated.any():
        example = normalized.loc[duplicated, ["time", "stock_id"]].iloc[0]
        raise ValueError(
            "baseline requires at most one row per stock_id within each time; "
            f"found duplicate stock_id={example['stock_id']!r}, "
            f"time={example['time']!r}"
        )

    return normalized


def _sort_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Sort one snapshot by clock and preserve input order for clock ties."""

    return snapshot.sort_values(
        ["clock", "_row_order"], kind="stable", ignore_index=True
    )


def _collect_snapshot_gaps(data: pd.DataFrame) -> pd.Series:
    """Collect adjacent clock gaps after sorting inside each snapshot."""

    gap_parts: list[pd.Series] = []
    for _, snapshot in data.groupby("time", sort=False):
        ordered_snapshot = _sort_snapshot(snapshot)
        # The first row has no predecessor in its snapshot and therefore does
        # not contribute a gap to threshold detection.
        gap_parts.append(ordered_snapshot["clock"].diff().dropna().astype("int64"))

    if not gap_parts:
        return pd.Series(dtype="int64")
    return pd.concat(gap_parts, ignore_index=True)


def _resolve_threshold(
    data: pd.DataFrame,
    threshold: int | None,
    *,
    robust_z_threshold: float,
    min_slope_multiplier: float,
    min_segment_size: int,
) -> tuple[int, str]:
    """Use a manual threshold or detect one from all within-snapshot gaps."""

    if threshold is not None:
        if isinstance(threshold, bool) or not isinstance(threshold, Integral):
            raise ValueError("threshold must be a positive integer number of microseconds")
        resolved_threshold = int(threshold)
        if resolved_threshold <= 0:
            raise ValueError("threshold must be a positive integer number of microseconds")
        return resolved_threshold, "manual"

    gaps = _collect_snapshot_gaps(data)
    abrupt_increase = find_abrupt_increase(
        pd.DataFrame({"delta_clock": gaps}),
        robust_z_threshold=robust_z_threshold,
        min_slope_multiplier=min_slope_multiplier,
        min_segment_size=min_segment_size,
    )
    if abrupt_increase is None:
        raise ValueError(
            "could not detect an abrupt snapshot clock-gap threshold; "
            "provide --threshold explicitly"
        )
    return abrupt_increase.delta_clock, "automatic"


def _collect_local_evidence(
    data: pd.DataFrame, threshold: int
) -> tuple[MembershipHistory, Counter[Pair], int, int]:
    """Cut every snapshot and collect same-local-group evidence.

    A gap equal to the threshold starts a new local group. This is intentional:
    ``find_abrupt_increase`` returns the first value on the large-gap side, so
    that value should be treated as a separator rather than a within-group gap.
    """

    histories: MembershipHistory = {
        stock_id: {} for stock_id in data["stock_id"].unique().tolist()
    }
    positive_evidence: Counter[Pair] = Counter()
    snapshot_count = 0
    local_group_count = 0

    for time_value, snapshot in data.groupby("time", sort=False):
        snapshot_count += 1
        ordered_snapshot = _sort_snapshot(snapshot)
        gaps = ordered_snapshot["clock"].diff()

        starts_new_group = gaps.ge(threshold)
        starts_new_group.iloc[0] = True
        local_group_ids = starts_new_group.cumsum().sub(1).astype("int64")
        ordered_snapshot = ordered_snapshot.assign(local_group_id=local_group_ids)

        snapshot_group_count = int(local_group_ids.nunique())
        local_group_count += snapshot_group_count

        for stock_id, local_group_id in zip(
            ordered_snapshot["stock_id"],
            ordered_snapshot["local_group_id"],
            strict=True,
        ):
            histories[str(stock_id)][str(time_value)] = int(local_group_id)

        # Every pair in one local candidate group receives one unit of positive
        # evidence. This is deliberately simple and can be expensive for very
        # large local groups; it is part of the baseline, not the final design.
        for _, local_group in ordered_snapshot.groupby("local_group_id", sort=False):
            stock_ids = local_group["stock_id"].astype(str).tolist()
            for stock_a, stock_b in combinations(stock_ids, 2):
                positive_evidence[_ordered_pair(stock_a, stock_b)] += 1

    return histories, positive_evidence, snapshot_count, local_group_count


def _were_ever_separated(
    stock_a: str,
    stock_b: str,
    histories: MembershipHistory,
    cache: dict[Pair, bool],
) -> bool:
    """Return whether a pair was split in any snapshot where both appeared."""

    pair = _ordered_pair(stock_a, stock_b)
    cached = cache.get(pair)
    if cached is not None:
        return cached

    history_a = histories[stock_a]
    history_b = histories[stock_b]

    # Iterate over the shorter history to reduce dictionary lookups. If one
    # stock is absent from a snapshot, that time is simply not found in the
    # other history and contributes no negative evidence.
    if len(history_a) > len(history_b):
        history_a, history_b = history_b, history_a

    separated = any(
        time_value in history_b and history_b[time_value] != local_group_id
        for time_value, local_group_id in history_a.items()
    )
    cache[pair] = separated
    return separated


def _components_can_merge(
    first_members: set[str],
    second_members: set[str],
    histories: MembershipHistory,
    separation_cache: dict[Pair, bool],
) -> bool:
    """Require every cross-component pair to respect permanent separation."""

    return not any(
        _were_ever_separated(
            stock_a,
            stock_b,
            histories,
            separation_cache,
        )
        for stock_a in first_members
        for stock_b in second_members
    )


def _merge_with_permanent_separation(
    stock_ids: Sequence[str],
    histories: MembershipHistory,
    positive_evidence: Counter[Pair],
) -> tuple[list[set[str]], int]:
    """Greedily merge strong positive pairs without violating hard constraints."""

    union_find = _UnionFind(stock_ids)
    separation_cache: dict[Pair, bool] = {}
    blocked_merge_count = 0

    # Stronger repeated same-group evidence is considered first. Pair order is
    # the deterministic tie-breaker. Hard separation always wins regardless of
    # how large the positive count is.
    ordered_evidence = sorted(
        positive_evidence.items(),
        key=lambda item: (-item[1], item[0]),
    )
    for (stock_a, stock_b), _same_group_count in ordered_evidence:
        first_root = union_find.find(stock_a)
        second_root = union_find.find(stock_b)
        if first_root == second_root:
            continue

        if not _components_can_merge(
            union_find.members(first_root),
            union_find.members(second_root),
            histories,
            separation_cache,
        ):
            blocked_merge_count += 1
            continue

        union_find.union(first_root, second_root)

    return union_find.components(), blocked_merge_count


def _build_mapping(components: list[set[str]]) -> pd.DataFrame:
    """Assign deterministic zero-based group IDs and sort by stock ID."""

    ordered_components = sorted(
        (sorted(component) for component in components),
        key=lambda component: component[0],
    )
    rows = [
        (stock_id, group_id)
        for group_id, component in enumerate(ordered_components)
        for stock_id in component
    ]
    return (
        pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))
        .sort_values("stock_id", kind="stable", ignore_index=True)
        .astype({"stock_id": "string", "group_id": "int64"})
    )


def infer_fixed_groups(
    data: pd.DataFrame,
    *,
    threshold: int | None = None,
    robust_z_threshold: float = DEFAULT_ROBUST_Z_THRESHOLD,
    min_slope_multiplier: float = DEFAULT_MIN_SLOPE_MULTIPLIER,
    min_segment_size: int = DEFAULT_MIN_SEGMENT_SIZE,
) -> BaselineGroupingResult:
    """Infer a fixed stock grouping with the coarse snapshot baseline.

    Complexity is intentionally not optimized: positive pair collection costs
    ``O(sum(local_group_size ** 2))`` and constrained component checks can also
    become expensive. This implementation is suitable as a correctness and
    failure-mode baseline, not yet as the final full-market algorithm.
    """

    normalized = _normalize_market_data(data)
    resolved_threshold, threshold_source = _resolve_threshold(
        normalized,
        threshold,
        robust_z_threshold=robust_z_threshold,
        min_slope_multiplier=min_slope_multiplier,
        min_segment_size=min_segment_size,
    )
    histories, positive_evidence, snapshot_count, local_group_count = (
        _collect_local_evidence(normalized, resolved_threshold)
    )
    stock_ids = sorted(histories)
    components, blocked_merge_count = _merge_with_permanent_separation(
        stock_ids,
        histories,
        positive_evidence,
    )
    mapping = _build_mapping(components)

    return BaselineGroupingResult(
        mapping=mapping,
        threshold=resolved_threshold,
        threshold_source=threshold_source,
        snapshot_count=snapshot_count,
        local_group_count=local_group_count,
        positive_pair_count=len(positive_evidence),
        blocked_merge_count=blocked_merge_count,
    )


def process_csv(
    input_csv: Path | str,
    output_csv: Path | str,
    *,
    threshold: int | None = None,
    robust_z_threshold: float = DEFAULT_ROBUST_Z_THRESHOLD,
    min_slope_multiplier: float = DEFAULT_MIN_SLOPE_MULTIPLIER,
    min_segment_size: int = DEFAULT_MIN_SEGMENT_SIZE,
) -> BaselineGroupingResult:
    """Read market data, run the baseline, and write ``stock_id,group_id``."""

    data = pd.read_csv(
        input_csv,
        usecols=list(REQUIRED_COLUMNS),
        dtype={"clock": "string", "stock_id": "string", "time": "string"},
    )
    result = infer_fixed_groups(
        data,
        threshold=threshold,
        robust_z_threshold=robust_z_threshold,
        min_slope_multiplier=min_slope_multiplier,
        min_segment_size=min_segment_size,
    )
    result.mapping.to_csv(output_csv, columns=list(OUTPUT_COLUMNS), index=False)
    return result


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Infer a coarse fixed stock grouping from time snapshots and clock "
            "gaps. Any pair separated once is permanently separated."
        )
    )
    parser.add_argument("input_csv", type=Path, help="source market data CSV")
    parser.add_argument("output_csv", type=Path, help="destination group mapping CSV")
    parser.add_argument(
        "--threshold",
        type=int,
        help="manual clock-gap threshold in microseconds; default: auto-detect",
    )
    parser.add_argument(
        "--robust-z-threshold",
        type=float,
        default=DEFAULT_ROBUST_Z_THRESHOLD,
        help="automatic detector MAD threshold (default: %(default)s)",
    )
    parser.add_argument(
        "--min-slope-multiplier",
        type=float,
        default=DEFAULT_MIN_SLOPE_MULTIPLIER,
        help="automatic detector minimum slope multiplier (default: %(default)s)",
    )
    parser.add_argument(
        "--min-segment-size",
        type=int,
        default=DEFAULT_MIN_SEGMENT_SIZE,
        help="automatic detector minimum samples per side (default: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the baseline CLI."""

    parser = build_argument_parser()
    arguments = parser.parse_args(argv)

    try:
        result = process_csv(
            arguments.input_csv,
            arguments.output_csv,
            threshold=arguments.threshold,
            robust_z_threshold=arguments.robust_z_threshold,
            min_slope_multiplier=arguments.min_slope_multiplier,
            min_segment_size=arguments.min_segment_size,
        )
    except (OSError, ValueError) as error:
        parser.exit(status=1, message=f"error: {error}\n")

    print(
        f"threshold={result.threshold} ({result.threshold_source}), "
        f"snapshots={result.snapshot_count}, "
        f"local_groups={result.local_group_count}, "
        f"final_groups={result.final_group_count}, "
        f"blocked_merges={result.blocked_merge_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
