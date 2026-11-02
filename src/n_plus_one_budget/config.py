"""Scenario configuration, validated on construction."""

from __future__ import annotations

import os
from dataclasses import dataclass

from n_plus_one_budget.theory import STRATEGIES

MIN_PARENTS = 10

DEFAULT_DSN = os.environ.get(
    "NPLUSONE_DSN", "postgresql://postgres:postgres@127.0.0.1:5433/postgres")


class ConfigError(ValueError):
    """Raised when a scenario cannot show the effect it claims to measure."""


@dataclass(frozen=True)
class LoadConfig:
    """One page load: a strategy, a fixture, and how far away the database is."""

    strategy: str = "n_plus_one"
    parents: int = 100
    children_each: int = 4
    bio_width: int = 200
    round_trip_ms: float = 0.0
    budget: int = 0
    repeats: int = 5
    dsn: str = DEFAULT_DSN

    def __post_init__(self) -> None:
        if self.strategy not in STRATEGIES:
            raise ConfigError(
                f"strategy must be one of {STRATEGIES}, got {self.strategy!r}")
        if self.parents < MIN_PARENTS:
            raise ConfigError(
                f"parents={self.parents} is below {MIN_PARENTS}. The effect is counted "
                "in round trips, and a handful of them is under the noise of a single "
                "connection setup."
            )
        if self.children_each < 1:
            raise ConfigError(
                "children_each must be at least one. A parent with no children is never "
                "asked a follow-up question, so there is no N+1 to find."
            )
        if self.bio_width < 1:
            raise ConfigError("bio_width must be at least one character")
        if self.round_trip_ms < 0:
            raise ConfigError("round_trip_ms cannot be negative")
        if self.budget < 0:
            raise ConfigError("budget cannot be negative")
        if self.repeats < 1:
            raise ConfigError("repeats must be at least one")

    @property
    def round_trip_seconds(self) -> float:
        return self.round_trip_ms / 1000.0

    @property
    def total_children(self) -> int:
        return self.parents * self.children_each

    def as_dict(self) -> dict:
        return {
            "strategy": self.strategy, "parents": self.parents,
            "children_each": self.children_each, "bio_width": self.bio_width,
            "round_trip_ms": self.round_trip_ms, "budget": self.budget,
            "repeats": self.repeats,
        }
