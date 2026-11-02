"""Run one page load and record both what it cost and what it returned.

Every run checks that the strategy returned exactly what the batched loader returns. Three
strategies that disagree about their results are not three strategies, and a timing
comparison between them would be meaningless. That check runs before any number is
reported, which is the same discipline the sibling repositories in this series apply to
their own instruments.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from n_plus_one_budget import theory
from n_plus_one_budget.config import LoadConfig
from n_plus_one_budget.counting import connect
from n_plus_one_budget.database import ensure_schema
from n_plus_one_budget.loaders import load


@dataclass(frozen=True)
class LoadResult:
    """One strategy, measured."""

    config: LoadConfig
    queries: int
    rows_returned: int
    bytes_returned: int
    seconds: float
    seconds_spread: float
    matches_reference: bool

    @property
    def predicted_queries(self) -> int:
        return theory.query_count(self.config.strategy, self.config.parents)

    @property
    def queries_agree(self) -> bool:
        return self.queries == self.predicted_queries

    @property
    def ms(self) -> float:
        return self.seconds * 1000.0

    def as_dict(self) -> dict:
        return {
            "config": self.config.as_dict(), "queries": self.queries,
            "predicted_queries": self.predicted_queries,
            "queries_agree": self.queries_agree,
            "rows_returned": self.rows_returned,
            "bytes_returned": self.bytes_returned,
            "ms": round(self.ms, 3),
            "seconds_spread": round(self.seconds_spread, 4),
            "matches_reference": self.matches_reference,
        }


def run_load(config: LoadConfig, build_schema: bool = True) -> LoadResult:
    """Load the page `repeats` times and report the median, with a correctness check."""
    if build_schema:
        ensure_schema(config.dsn, config.parents, config.children_each,
                      config.bio_width)

    # The reference result is loaded without any simulated latency, because its only job
    # is to say what the right answer is.
    with connect(config.dsn) as reference_conn:
        reference = load("batched", reference_conn, config.parents).shape()

    timings: list[float] = []
    queries = 0
    rows = 0
    payload = 0
    matches = True

    for _ in range(config.repeats):
        with connect(config.dsn, config.round_trip_seconds) as conn:
            started = time.perf_counter()
            loaded = load(config.strategy, conn, config.parents)
            timings.append(time.perf_counter() - started)
            queries = conn.query_counter.count
            rows = loaded.rows_returned
            payload = loaded.bytes_returned
            matches = matches and loaded.shape() == reference

    low = min(timings)
    return LoadResult(
        config=config, queries=queries, rows_returned=rows, bytes_returned=payload,
        seconds=statistics.median(timings),
        seconds_spread=max(timings) / low if low > 0 else 0.0,
        matches_reference=matches,
    )
