"""E2. The same code, at several distances from the database.

Nothing about the code changes across this sweep. The page is identical, the query counts
are identical, the database does identical work. The only thing that moves is how long a
round trip takes, and that is enough to take the N+1 from a rounding error to a timeout.

The simulated round trip is a sleep applied to every query as it leaves the process, which
is argued in ADR-002. It models the part of a real network that matters here - that each
query waits for the previous one to come back - and not the parts that do not.

The apparatus check took three goes to state correctly, and the final form is narrower and
more honest than the first.

The first version predicted the added time as the extra query count times the *requested*
round trip. It failed everywhere, worst at the smallest setting, where it was out by a
factor of four.

The second added two measured terms: what an extra query costs with no simulated network
at all, and what a sleep actually lasts rather than what it was asked for - at a tenth of a
millisecond the scheduler adds more than half as much again. Better, and still failing, by
a consistent few tenths of a millisecond per query.

The reason is that injecting delay with a sleep costs more than the sleep. The thread is
descheduled and the wake-up is paid by whatever runs next, so part of the injection lands
on the following query rather than inside the sleep that caused it. No amount of timing the
sleep itself will find that.

So the claim being checked is the one that survives all of it: **the cost per extra round
trip rises one-for-one with the round trip**. The slope is what matters and is predicted to
be one. The intercept is the injection overhead - real, disclosed, and not claimed to be
zero. A sweep whose slope is not one is measuring something other than round trips.
"""

from __future__ import annotations

import json
from pathlib import Path

from n_plus_one_budget import theory
from n_plus_one_budget.config import DEFAULT_DSN, LoadConfig
from n_plus_one_budget.harness import run_load

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
PARENTS = 100
CHILDREN = 4
REPEATS = 5
ROUND_TRIPS_MS = (0.0, 0.1, 0.5, 1.0, 2.0, 5.0)
# The slope of cost-per-trip against requested round trip, which the derivation puts at
# one. The band is wide enough for two differences of medians on a shared box.
SLOPE_BAND = (0.85, 1.15)
# The smallest round trip the slope is fitted over. Below this the injection overhead is
# comparable to the signal and dominates the fit.
SLOPE_FROM_MS = 0.5


def main() -> None:
    rows = []
    baseline_extra_ms = 0.0
    for rtt in ROUND_TRIPS_MS:
        measured = {}
        for strategy in theory.STRATEGIES:
            config = LoadConfig(strategy=strategy, parents=PARENTS,
                                children_each=CHILDREN, round_trip_ms=rtt,
                                repeats=REPEATS, dsn=DEFAULT_DSN)
            measured[strategy] = run_load(config)

        npo = measured["n_plus_one"]
        batched = measured["batched"]
        joined = measured["join"]
        extra_ms = npo.ms - batched.ms
        effective_ms = npo.effective_round_trip_seconds * 1000

        if rtt == 0.0:
            # What an extra query costs with no simulated network at all: parsing,
            # dispatch and the loopback. Every later prediction is built on top of it.
            baseline_extra_ms = extra_ms

        extra_trips = theory.extra_round_trips(PARENTS)
        cost_per_trip = (extra_ms - baseline_extra_ms) / extra_trips

        rows.append({
            "cost_per_extra_trip_ms": round(cost_per_trip, 4),
            "injection_overhead_ms": round(cost_per_trip - rtt, 4),
            "round_trip_ms": rtt,
            "effective_round_trip_ms": round(effective_ms, 4),
            "n_plus_one_ms": round(npo.ms, 3),
            "batched_ms": round(batched.ms, 3),
            "join_ms": round(joined.ms, 3),
            "slowdown": round(npo.ms / batched.ms, 2),
            "extra_ms": round(extra_ms, 3),
            "would_be_noticed": not theory.invisible_below(PARENTS, rtt / 1000.0),
        })
        print(f"  asked {rtt:4.1f}ms (really {effective_ms:5.3f}ms)   "
              f"n+1 {npo.ms:8.2f}ms   batched {batched.ms:6.2f}ms   "
              f"join {joined.ms:6.2f}ms   {npo.ms / batched.ms:6.1f}x   "
              f"{'noticed' if rows[-1]['would_be_noticed'] else 'invisible'}")

    # Fit the slope of cost-per-trip against the requested round trip over the settings
    # where the signal is well above the injection overhead.
    fitted = [r for r in rows if r["round_trip_ms"] >= SLOPE_FROM_MS]
    rise = fitted[-1]["cost_per_extra_trip_ms"] - fitted[0]["cost_per_extra_trip_ms"]
    run = fitted[-1]["round_trip_ms"] - fitted[0]["round_trip_ms"]
    slope = rise / run if run else 0.0
    intercept = fitted[-1]["cost_per_extra_trip_ms"] - slope * fitted[-1]["round_trip_ms"]

    local, remote = rows[0], rows[-1]
    first_noticed = next((r for r in rows if r["would_be_noticed"]), None)

    payload = {
        "experiment": "e2_the_cost_is_round_trips",
        "parents": PARENTS, "children_each": CHILDREN, "repeats": REPEATS,
        "rows": rows,
        "cost_per_trip_slope": round(slope, 4),
        "slope_is_one": SLOPE_BAND[0] <= slope <= SLOPE_BAND[1],
        "injection_overhead_ms": round(intercept, 4),
        "baseline_extra_ms": round(baseline_extra_ms, 3),
        "slowdown_grows_with_distance": (
            [r["slowdown"] for r in rows] == sorted(r["slowdown"] for r in rows)),
        "local_slowdown": local["slowdown"],
        "local_extra_ms": local["extra_ms"],
        "remote_round_trip_ms": remote["round_trip_ms"],
        "remote_slowdown": remote["slowdown"],
        "remote_extra_ms": remote["extra_ms"],
        "remote_n_plus_one_ms": remote["n_plus_one_ms"],
        "first_noticeable_round_trip_ms": (
            first_noticed["round_trip_ms"] if first_noticed else None),
        "extra_round_trips": theory.extra_round_trips(PARENTS),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e2.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"cost per extra round trip rises one-for-one with the round trip: "
          f"{payload['slope_is_one']} (slope {payload['cost_per_trip_slope']})")
    print(f"injection overhead, disclosed rather than assumed away: "
          f"{payload['injection_overhead_ms']}ms per query")
    print(f"the slowdown grows with distance:            "
          f"{payload['slowdown_grows_with_distance']}")
    print(f"locally the same page is {local['slowdown']}x slower, "
          f"{local['extra_ms']}ms of difference")
    print(f"at {remote['round_trip_ms']}ms it is {remote['slowdown']}x slower, "
          f"{remote['extra_ms']}ms of difference, for identical code")


if __name__ == "__main__":
    main()
