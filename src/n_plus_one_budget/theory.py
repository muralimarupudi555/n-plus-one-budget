"""What a loading strategy costs, derived before anything was measured.

Loading `n` parent rows and their children can be done three ways, and they differ in one
number that no latency graph shows: how many times the application asks the database
anything.

    N+1        1 + n queries
    batched    2 queries, whatever n is
    join       1 query, whatever n is

The time that costs is not the time the database spends. Each query is a round trip, so

    wall time = queries * (round_trip + server_time) + transfer

and on a developer's machine the round trip is tens of microseconds. That is the whole
reason this defect survives review: at a loopback round trip the difference between one
query and a hundred and one is a couple of milliseconds, which is indistinguishable from
noise and invisible to any test that asserts on elapsed time. Across a network at two
milliseconds the same code path is two hundred milliseconds slower, and nothing about the
code changed.

The ratio between the strategies is therefore a property of the round trip rather than of
the query. As the round trip grows it tends to `(1 + n) / 2`; as it shrinks to nothing it
tends to the ratio of the server times, which is near one. A benchmark run locally measures
the second limit and reports it as though it were the first.

The fixes are not free either, and the two are not equivalent. A join returns one row per
child and repeats every parent column on each of them, so it transfers rows the batched
pair does not. The batched pair sends each parent once and pays an extra round trip for the
privilege. Which is cheaper depends on the round trip and the width of the parent row, and
E3 measures both rather than asserting either.
"""

from __future__ import annotations

STRATEGIES = ("n_plus_one", "batched", "join")

# A page stops feeling instant somewhere around here, so it is the threshold used to ask
# whether a given number of extra round trips would be noticed at all.
NOTICEABLE_SECONDS = 0.05


def query_count(strategy: str, parents: int) -> int:
    """Queries issued to load `parents` parents and all their children."""
    if strategy == "n_plus_one":
        return 1 + parents
    if strategy == "batched":
        return 2
    if strategy == "join":
        return 1
    raise ValueError(f"unknown strategy {strategy!r}")


def predicted_seconds(strategy: str, parents: int, round_trip_seconds: float,
                      server_seconds: float = 0.0) -> float:
    """Round trips dominate, so the prediction is built from them."""
    return query_count(strategy, parents) * (round_trip_seconds + server_seconds)


def extra_round_trips(parents: int) -> int:
    """Round trips N+1 spends that the batched pair does not."""
    return query_count("n_plus_one", parents) - query_count("batched", parents)


def slowdown(parents: int, round_trip_seconds: float,
             server_seconds: float = 0.0) -> float:
    """How much slower N+1 is than the batched pair at this round trip.

    With no per-query cost at all the strategies are indistinguishable, which is the
    degenerate case a local benchmark approaches.
    """
    cost = round_trip_seconds + server_seconds
    if cost <= 0:
        return 1.0
    return query_count("n_plus_one", parents) / query_count("batched", parents)


def rows_returned(strategy: str, parents: int, children_each: int) -> int:
    """Rows crossing the wire, which is where a join pays for its single query."""
    total_children = parents * children_each
    if strategy == "join":
        return total_children
    return parents + total_children


def duplicated_parent_rows(parents: int, children_each: int) -> int:
    """Parent rows a join repeats: one per child beyond the first."""
    return parents * max(0, children_each - 1)


def bytes_returned(strategy: str, parents: int, children_each: int,
                   parent_width: int, child_width: int) -> int:
    """Payload size, which is where a join pays and a row count cannot see it.

    Rows are the obvious unit and the wrong one. A join returns fewer rows than the
    batched pair - one per child rather than parents plus children - while repeating every
    parent column on each of them, so counting rows makes it look like the cheaper option.
    """
    total_children = parents * children_each
    if strategy == "join":
        return total_children * (parent_width + child_width)
    return parents * parent_width + total_children * child_width


def duplicated_bytes(parents: int, children_each: int, parent_width: int) -> int:
    """Payload a join spends sending parent rows somebody already has."""
    return duplicated_parent_rows(parents, children_each) * parent_width


def invisible_below(parents: int, round_trip_seconds: float,
                    threshold_seconds: float = NOTICEABLE_SECONDS) -> bool:
    """Whether the extra round trips stay under a threshold a human would notice.

    A code path costing a hundred extra queries is comfortably under it on a loopback
    connection and comfortably over it across a network. That is the entire problem
    stated as one function.
    """
    return extra_round_trips(parents) * round_trip_seconds < threshold_seconds
