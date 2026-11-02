"""A cursor that counts the queries it runs, and a budget that fails when there are too many.

Counting at the cursor is deliberate. An application does not decide how many queries it
issues; its ORM does, two layers down, in response to an attribute access that looks free.
A counter that lives where the queries actually leave the process sees every one of them,
including the ones nobody wrote.

This is also where the simulated round trip is injected. A query's cost is dominated by the
trip rather than the work, so the trip is the thing worth being able to vary, and varying it
here applies it to every query however it was issued.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import psycopg


class BudgetExceeded(AssertionError):
    """Raised when a code path issues more queries than it was allowed.

    An AssertionError rather than a bespoke exception, so that a budget reads like any
    other assertion in a test and fails the same way.
    """


@dataclass
class QueryCounter:
    """Counts queries, remembers them, and can pretend the database is far away."""

    round_trip_seconds: float = 0.0
    count: int = 0
    queries: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _budget: int | None = None
    _budget_label: str = ""
    _budget_started: int = 0

    def record(self, query: str) -> None:
        with self._lock:
            self.count += 1
            self.queries.append(query)
            budget, label = self._budget, self._budget_label
            started = self._budget_started
            count = self.count
        if budget is not None and count > budget:
            # Counts are reported relative to the block, not to the connection. A budget
            # is a statement about one code path, so a message that mixes in whatever
            # ran before it sends the reader looking in the wrong place.
            inside = count - started
            raise BudgetExceeded(
                f"{label or 'this code path'} issued {inside} queries against a budget "
                f"of {budget - started}.\n"
                f"The query that broke it: {_summarise(query)}\n"
                f"Queries in this block:\n{self.summary(since=started)}"
            )
        if self.round_trip_seconds > 0:
            time.sleep(self.round_trip_seconds)

    def reset(self) -> None:
        with self._lock:
            self.count = 0
            self.queries.clear()

    def summary(self, limit: int = 6, since: int = 0) -> str:
        """The distinct shapes issued, with how many times each ran.

        Shapes rather than full text, because the output of an N+1 is the same statement a
        hundred times and printing it a hundred times buries the one line that matters.
        """
        shapes: dict[str, int] = {}
        for query in self.queries[since:]:
            shape = _summarise(query)
            shapes[shape] = shapes.get(shape, 0) + 1
        lines = [f"  {count:5} x {shape}" for shape, count in
                 sorted(shapes.items(), key=lambda item: -item[1])[:limit]]
        if len(shapes) > limit:
            lines.append(f"  ... and {len(shapes) - limit} more shapes")
        return "\n".join(lines)

    @contextmanager
    def budget(self, limit: int, label: str = ""):
        """Fail immediately if more than `limit` queries are issued inside the block.

        Immediately, rather than at the end: the traceback then points at the line that
        issued the query that broke the budget, which is the line somebody has to change.
        A check at the end of the block names only the block.
        """
        with self._lock:
            previous = (self._budget, self._budget_label, self._budget_started)
            started = self.count
            self._budget = started + limit
            self._budget_label = label
            self._budget_started = started
        try:
            yield self
        finally:
            with self._lock:
                (self._budget, self._budget_label,
                 self._budget_started) = previous

    def as_dict(self) -> dict:
        return {"queries": self.count, "round_trip_seconds": self.round_trip_seconds}


def _summarise(query: str) -> str:
    text = " ".join(str(query).split())
    return text if len(text) <= 90 else text[:87] + "..."


class CountingCursor(psycopg.Cursor):
    """A cursor that tells the connection's counter about every statement it runs."""

    def execute(self, query, params=None, **kwargs):  # type: ignore[override]
        counter = getattr(self.connection, "query_counter", None)
        if counter is not None:
            counter.record(query)
        return super().execute(query, params, **kwargs)


def connect(dsn: str, round_trip_seconds: float = 0.0) -> psycopg.Connection:
    """Open a connection whose queries are counted and optionally slowed."""
    conn = psycopg.connect(dsn, autocommit=True, cursor_factory=CountingCursor)
    conn.query_counter = QueryCounter(round_trip_seconds=round_trip_seconds)
    return conn
