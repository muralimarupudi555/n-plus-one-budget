"""Turn a load into a verdict, and check the instruments while doing it.

Two things have to hold before a query count means anything. The strategy must have
returned what the reference loader returns, because a cheaper strategy that drops rows is
not cheaper. And the measured count must match the derivation, because these are exact
integers rather than samples - a strategy that issues a different number of queries than
its definition says is not the strategy under test, and the usual cause is an ORM quietly
adding one.
"""

from __future__ import annotations

from dataclasses import dataclass

from n_plus_one_budget import theory
from n_plus_one_budget.config import LoadConfig
from n_plus_one_budget.harness import LoadResult, run_load


@dataclass(frozen=True)
class Report:
    result: LoadResult

    @property
    def config(self) -> LoadConfig:
        return self.result.config

    @property
    def budget(self) -> int:
        return self.config.budget

    @property
    def over_budget(self) -> bool:
        return self.budget > 0 and self.result.queries > self.budget

    @property
    def measurement_valid(self) -> bool:
        return self.result.matches_reference and self.result.queries_agree

    @property
    def extra_round_trips(self) -> int:
        return self.result.queries - theory.query_count("batched", self.config.parents)

    @property
    def extra_ms_at(self) -> dict:
        """What those extra round trips would cost at several realistic distances.

        The point of showing more than one is that the figure measured on the machine the
        code was written on is the least interesting of them.
        """
        return {
            f"{rtt_ms:g}": round(self.extra_round_trips * rtt_ms, 2)
            for rtt_ms in (0.05, 0.5, 1.0, 2.0, 5.0)
        }

    @property
    def would_be_noticed(self) -> bool:
        return not theory.invisible_below(
            self.config.parents, self.config.round_trip_seconds)

    @property
    def duplicated_bytes(self) -> int:
        if self.config.strategy != "join":
            return 0
        return theory.duplicated_bytes(
            self.config.parents, self.config.children_each, self.config.bio_width)

    def as_dict(self) -> dict:
        return {
            **self.result.as_dict(),
            "budget": self.budget,
            "over_budget": self.over_budget,
            "extra_round_trips": self.extra_round_trips,
            "extra_ms_at_round_trip": self.extra_ms_at,
            "would_be_noticed_here": self.would_be_noticed,
            "duplicated_bytes": self.duplicated_bytes,
            "measurement_valid": self.measurement_valid,
        }


def build_report(config: LoadConfig) -> Report:
    return Report(result=run_load(config))
