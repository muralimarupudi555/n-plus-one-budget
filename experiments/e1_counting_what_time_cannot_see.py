"""E1. The query count is exact and the local clock is useless.

Load the same page three ways at several sizes. Two things should come out.

The query counts should match their definitions exactly - `1 + n`, `2`, `1` - because these
are integers rather than samples. A strategy that issues a different number than its
definition says is not the strategy under test, and the usual cause is an ORM quietly
adding one.

The wall times, measured here on a loopback connection, should show a difference small
enough that nobody would act on it. That is the finding, not a disappointment: the point of
counting queries is that the clock on the machine where the code was written is the wrong
instrument, and E1 is where that is established before E2 shows what the same code costs
somewhere else.
"""

from __future__ import annotations

import json
from pathlib import Path

from n_plus_one_budget import theory
from n_plus_one_budget.config import DEFAULT_DSN, LoadConfig
from n_plus_one_budget.harness import run_load

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
SIZES = (25, 50, 100, 200)
CHILDREN = 4
REPEATS = 7


def main() -> None:
    rows = []
    for parents in SIZES:
        measured = {}
        for strategy in theory.STRATEGIES:
            config = LoadConfig(strategy=strategy, parents=parents,
                                children_each=CHILDREN, repeats=REPEATS,
                                dsn=DEFAULT_DSN)
            result = run_load(config)
            measured[strategy] = result
            rows.append({
                "parents": parents, "strategy": strategy,
                "queries": result.queries,
                "predicted_queries": result.predicted_queries,
                "queries_agree": result.queries_agree,
                "ms": round(result.ms, 3),
                "rows_returned": result.rows_returned,
                "bytes_returned": result.bytes_returned,
                "matches_reference": result.matches_reference,
                "spread": round(result.seconds_spread, 3),
            })
        npo, batched = measured["n_plus_one"], measured["batched"]
        print(f"  {parents:4} parents   n+1 {npo.queries:4} queries "
              f"{npo.ms:7.2f}ms   batched {batched.queries} queries "
              f"{batched.ms:6.2f}ms   difference "
              f"{(npo.ms - batched.ms):6.2f}ms")

    worst = max(
        next(r for r in rows if r["parents"] == p and r["strategy"] == "n_plus_one")["ms"]
        - next(r for r in rows if r["parents"] == p and r["strategy"] == "batched")["ms"]
        for p in SIZES
    )
    payload = {
        "experiment": "e1_counting_what_time_cannot_see",
        "children_each": CHILDREN, "repeats": REPEATS, "sizes": list(SIZES),
        "rows": rows,
        "every_count_matches": all(r["queries_agree"] for r in rows),
        "every_result_matches": all(r["matches_reference"] for r in rows),
        "worst_local_difference_ms": round(worst, 3),
        "worst_local_difference_noticeable": worst >= theory.NOTICEABLE_SECONDS * 1000,
        "largest_page": SIZES[-1],
        "largest_page_queries": theory.query_count("n_plus_one", SIZES[-1]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e1.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"every query count matched its definition exactly: "
          f"{payload['every_count_matches']}")
    print(f"every strategy returned the same result:          "
          f"{payload['every_result_matches']}")
    print(f"worst local difference was {payload['worst_local_difference_ms']}ms, "
          f"which a developer would notice: "
          f"{payload['worst_local_difference_noticeable']}")


if __name__ == "__main__":
    main()
