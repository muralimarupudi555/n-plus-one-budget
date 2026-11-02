"""Whole page loads, where the count has to match the derivation."""

from __future__ import annotations

import pytest

from n_plus_one_budget import theory
from n_plus_one_budget.config import LoadConfig
from n_plus_one_budget.harness import run_load

PARENTS = 20


def scenario(**overrides) -> LoadConfig:
    fields = dict(parents=PARENTS, children_each=3, repeats=2)
    fields.update(overrides)
    return LoadConfig(**fields)


@pytest.mark.parametrize("strategy", ["n_plus_one", "batched", "join"])
def test_every_strategy_returns_the_reference_result(dsn, strategy):
    result = run_load(scenario(strategy=strategy, dsn=dsn))
    assert result.matches_reference


@pytest.mark.parametrize("strategy", ["n_plus_one", "batched", "join"])
def test_every_strategy_issues_what_its_definition_says(dsn, strategy):
    result = run_load(scenario(strategy=strategy, dsn=dsn))
    assert result.queries == theory.query_count(strategy, PARENTS)
    assert result.queries_agree


def test_a_simulated_round_trip_shows_up_in_the_time(dsn):
    quick = run_load(scenario(strategy="n_plus_one", dsn=dsn))
    slow = run_load(scenario(strategy="n_plus_one", round_trip_ms=2.0, dsn=dsn))
    assert slow.seconds > quick.seconds


def test_the_round_trip_barely_touches_the_batched_loader(dsn):
    """Two queries pay two round trips; twenty-one pay twenty-one."""
    quick = run_load(scenario(strategy="batched", dsn=dsn))
    slow = run_load(scenario(strategy="batched", round_trip_ms=2.0, dsn=dsn))
    added = slow.seconds - quick.seconds
    assert added < 0.02


def test_the_round_trip_hits_n_plus_one_far_harder(dsn):
    batched_added = (run_load(scenario(strategy="batched", round_trip_ms=2.0, dsn=dsn))
                     .seconds
                     - run_load(scenario(strategy="batched", dsn=dsn)).seconds)
    npo_added = (run_load(scenario(strategy="n_plus_one", round_trip_ms=2.0, dsn=dsn))
                 .seconds
                 - run_load(scenario(strategy="n_plus_one", dsn=dsn)).seconds)
    assert npo_added > 5 * batched_added


def test_the_added_time_tracks_the_extra_round_trips(dsn):
    rtt = 0.002
    quick = run_load(scenario(strategy="n_plus_one", dsn=dsn))
    slow = run_load(scenario(strategy="n_plus_one", round_trip_ms=2.0, dsn=dsn))
    predicted = theory.query_count("n_plus_one", PARENTS) * rtt
    assert slow.seconds - quick.seconds == pytest.approx(predicted, rel=0.5)


def test_a_run_reports_its_spread(dsn):
    assert run_load(scenario(repeats=3, dsn=dsn)).seconds_spread >= 1.0
