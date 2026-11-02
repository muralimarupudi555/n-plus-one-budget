"""Re-derive the query counts and the payload ratios, and check the recorded runs.

The timings belong to this machine and the round trip is simulated. The query counts do
not belong to anything: loading `n` parents one child-query at a time is `1 + n` queries
on every machine that has ever existed. So the counts are what gets re-checked on every
verify, together with the payload relationships, which follow from the shape of a join
rather than from this box.

It was run against tampered results before being trusted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from n_plus_one_budget import theory  # noqa: E402

EXPERIMENTS = ROOT / "docs" / "experiments"


def load(name: str) -> dict:
    path = EXPERIMENTS / name
    if not path.exists():
        raise SystemExit(f"missing {path.relative_to(ROOT)}, run `make bench` first")
    return json.loads(path.read_text())


def check_e1(problems: list[str]) -> None:
    data = load("e1.json")
    for row in data["rows"]:
        expected = theory.query_count(row["strategy"], row["parents"])
        if row["queries"] != expected:
            problems.append(
                f"E1 {row['strategy']} at {row['parents']} parents: {row['queries']} "
                f"queries, the definition says {expected}"
            )
        if not row["matches_reference"]:
            problems.append(
                f"E1 {row['strategy']} at {row['parents']} parents: did not return the "
                "reference result, so its cost is not comparable to anything"
            )
    if not data["every_count_matches"]:
        problems.append("E1: the run itself recorded a count that missed its definition")
    if data["worst_local_difference_noticeable"]:
        problems.append(
            "E1: the local difference was large enough to notice, which would mean the "
            "premise of this repository does not hold on this machine; check the fixture "
            "size before believing the rest"
        )


def check_e2(problems: list[str]) -> None:
    data = load("e2.json")
    slowdowns = [row["slowdown"] for row in data["rows"]]
    if slowdowns != sorted(slowdowns):
        problems.append(
            "E2: the slowdown must grow with the round trip; the extra queries are "
            "paid for in trips"
        )
    if not data["slope_is_one"]:
        problems.append(
            f"E2: cost per extra round trip rose {data['cost_per_trip_slope']}x per "
            "millisecond of round trip rather than one for one, so the sweep is "
            "measuring something other than round trips"
        )
    first, last = data["rows"][0], data["rows"][-1]
    if first["would_be_noticed"]:
        problems.append(
            "E2: the local run was noticeable, which contradicts E1 and the premise"
        )
    if not last["would_be_noticed"]:
        problems.append(
            "E2: the most distant run was not noticeable, so the sweep never reached "
            "the regime it exists to show"
        )
    for row in data["rows"]:
        if row["round_trip_ms"] > 0 and \
                row["effective_round_trip_ms"] < row["round_trip_ms"]:
            problems.append(
                f"E2 round trip {row['round_trip_ms']}: the measured sleep "
                f"({row['effective_round_trip_ms']}ms) was shorter than requested, which "
                "a sleep cannot be"
            )


def check_e3(problems: list[str]) -> None:
    data = load("e3.json")
    for row in data["rows"]:
        measured, derived = row["bytes_ratio"], row["predicted_bytes_ratio"]
        if abs(measured - derived) / derived >= 0.1:
            problems.append(
                f"E3 parent width {row['bio_width']}: the join sent {measured}x the "
                f"bytes, the derivation says {derived}x"
            )
        if row["join_rows"] >= row["batched_rows"]:
            problems.append(
                f"E3 parent width {row['bio_width']}: a join returns one row per child, "
                "so it must return fewer rows than parents plus children"
            )
    ratios = [row["bytes_ratio"] for row in data["rows"]]
    if ratios != sorted(ratios):
        problems.append(
            "E3: a wider parent is repeated more, so the payload ratio must grow with it"
        )
    if not data["rows_always_favour_the_join"]:
        problems.append(
            "E3: the row count favouring the join at every width is the trap this "
            "experiment exists to show; losing it means the fixture changed"
        )
    if data["local_crossover_width"] is None:
        problems.append(
            "E3: the join won at every width locally, so the sweep never reached the "
            "point where its payload outweighs its single round trip"
        )


def main() -> int:
    problems: list[str] = []
    check_e1(problems)
    check_e2(problems)
    check_e3(problems)

    if problems:
        print("law check failed:\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            f"\n{len(problems)} problem(s). A recorded measurement no longer matches the "
            "arithmetic it was derived from. Re-run `make bench`, and if the problem "
            "survives, the mechanism changed and the prose needs to change with it.",
            file=sys.stderr,
        )
        return 1

    print("law check passed: every recorded run still matches the query arithmetic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
