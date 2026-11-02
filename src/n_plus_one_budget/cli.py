"""Command line entry point.

Exit code 4 is the one worth having, and it is deliberately not about time. It says this
code path issued more queries than it was allowed to, which is true on the machine that
wrote it as well as the one that will run it - unlike a latency assertion, which passes on
a loopback connection and fails in production.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from n_plus_one_budget.config import ConfigError, LoadConfig
from n_plus_one_budget.report import Report, build_report
from n_plus_one_budget.theory import STRATEGIES

EXIT_WITHIN_BUDGET = 0
EXIT_BAD_CONFIG = 2
EXIT_INTERNAL_ERROR = 3
EXIT_OVER_BUDGET = 4
EXIT_MEASUREMENT_INVALID = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="n-plus-one-budget",
        description="Count the queries a page load issues, and hold it to a budget.",
    )
    parser.add_argument("--strategy", choices=STRATEGIES, default="n_plus_one")
    parser.add_argument("--parents", type=int, default=100)
    parser.add_argument("--children-each", type=int, default=4)
    parser.add_argument("--bio-width", type=int, default=200)
    parser.add_argument("--round-trip-ms", type=float, default=0.0)
    parser.add_argument("--budget", type=int, default=2,
                        help="queries this page may issue; 0 disables the check")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def classify(report: Report) -> int:
    if not report.measurement_valid:
        return EXIT_MEASUREMENT_INVALID
    if report.over_budget:
        return EXIT_OVER_BUDGET
    return EXIT_WITHIN_BUDGET


def render(report: Report) -> str:
    config, result = report.config, report.result
    lines = [
        f"{config.strategy}, {config.parents} parents with {config.children_each} "
        f"children each, simulated round trip {config.round_trip_ms:g}ms",
        "",
        f"{'reading':<34}{'measured':>12}{'derived':>10}",
        "-" * 56,
        f"{'queries issued':<34}{result.queries:>12}{result.predicted_queries:>10}",
        f"{'rows returned':<34}{result.rows_returned:>12}",
        f"{'payload characters':<34}{result.bytes_returned:>12}",
        f"{'median wall time':<34}{result.ms:>10.2f} ms",
        f"{'run to run spread':<34}{result.seconds_spread:>11.2f}x",
    ]
    if report.budget:
        lines.append(f"{'budget':<34}{report.budget:>12}")

    if report.over_budget:
        costs = report.extra_ms_at
        lines += [
            "",
            f"this page issued {result.queries} queries against a budget of "
            f"{report.budget}: {report.extra_round_trips} more round trips than it needs.",
            "What those extra trips cost depends entirely on how far away the database is:",
        ]
        lines += [f"  at {rtt:>4} ms round trip   {cost:9.2f} ms added"
                  for rtt, cost in costs.items()]
        lines.append(
            "The first of those is a developer machine. The last is another region."
        )
    if config.strategy == "join" and report.duplicated_bytes:
        lines += [
            "",
            f"one query, but {report.duplicated_bytes} characters of it are parent rows "
            "sent again: a join repeats every parent column on every child.",
            "A query counter cannot see that, which is worth knowing about query counters.",
        ]
    if not report.measurement_valid:
        lines.append("")
        if not result.matches_reference:
            lines.append(
                "this strategy did not return what the reference loader returns, so its "
                "cost is not comparable to anything"
            )
        else:
            lines.append(
                f"issued {result.queries} queries where its definition says "
                f"{result.predicted_queries}: something is adding queries that this "
                "measurement does not know about"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fields = dict(strategy=args.strategy, parents=args.parents,
                      children_each=args.children_each, bio_width=args.bio_width,
                      round_trip_ms=args.round_trip_ms, budget=args.budget,
                      repeats=args.repeats)
        if args.dsn:
            fields["dsn"] = args.dsn
        config = LoadConfig(**fields)
    except ConfigError as exc:
        print(f"invalid scenario: {exc}", file=sys.stderr)
        return EXIT_BAD_CONFIG

    try:
        report = build_report(config)
    except Exception as exc:  # noqa: BLE001
        print(f"load failed to complete: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    print(json.dumps(report.as_dict(), indent=2) if args.json else render(report))
    return classify(report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
