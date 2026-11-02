"""The three loaders, against a real schema, checked for agreement first."""

from __future__ import annotations

import pytest

from n_plus_one_budget import theory
from n_plus_one_budget.counting import connect
from n_plus_one_budget.database import ensure_schema
from n_plus_one_budget.loaders import load, payload_bytes

STRATEGIES = ["n_plus_one", "batched", "join"]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_returns_the_same_result(conn, strategy, parents):
    """The precondition for every other number here."""
    reference = load("batched", conn, parents).shape()
    assert load(strategy, conn, parents).shape() == reference


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_query_counts_match_the_derivation(fixture_db, strategy, parents):
    with connect(fixture_db) as conn:
        load(strategy, conn, parents)
        assert conn.query_counter.count == theory.query_count(strategy, parents)


def test_an_unknown_strategy_is_refused(conn, parents):
    with pytest.raises(ValueError, match="unknown strategy"):
        load("optimistic", conn, parents)


def test_n_plus_one_grows_its_query_count_with_the_page(fixture_db, parents):
    counts = []
    for page in (5, 10, parents):
        with connect(fixture_db) as conn:
            load("n_plus_one", conn, page)
            counts.append(conn.query_counter.count)
    assert counts == [6, 11, parents + 1]


@pytest.mark.parametrize("strategy", ["batched", "join"])
def test_the_fixes_do_not_grow_with_the_page(fixture_db, strategy, parents):
    counts = []
    for page in (5, 10, parents):
        with connect(fixture_db) as conn:
            load(strategy, conn, page)
            counts.append(conn.query_counter.count)
    assert len(set(counts)) == 1


def test_every_parent_gets_all_its_children(conn, parents, children):
    loaded = load("batched", conn, parents)
    assert len(loaded.authors) == parents
    assert all(len(books) == children for _, books in loaded.authors)


def test_a_join_returns_fewer_rows_but_more_payload(conn, parents):
    joined = load("join", conn, parents)
    batched = load("batched", conn, parents)
    assert joined.rows_returned < batched.rows_returned
    assert joined.bytes_returned > batched.bytes_returned


def test_the_joins_extra_payload_is_the_repeated_parent(fixture_db, parents, children):
    """The excess should be the duplicated parent rows, not something else."""
    width = 500
    ensure_schema(fixture_db, parents, children, bio_width=width)
    with connect(fixture_db) as conn:
        excess = load("join", conn, parents).bytes_returned - \
            load("batched", conn, parents).bytes_returned
    predicted = theory.duplicated_bytes(parents, children, width)
    assert excess == pytest.approx(predicted, rel=0.1)


def test_a_wider_parent_widens_the_gap(fixture_db, parents, children):
    def gap(width: int) -> float:
        ensure_schema(fixture_db, parents, children, bio_width=width)
        with connect(fixture_db) as conn:
            return (load("join", conn, parents).bytes_returned
                    / load("batched", conn, parents).bytes_returned)

    assert gap(1000) > gap(100)


def test_payload_bytes_counts_every_field():
    assert payload_bytes([("ab", "c"), ("d", "")]) == 4


def test_payload_bytes_of_nothing_is_nothing():
    assert payload_bytes([]) == 0
