"""The counter and the budget, which are the mechanism this repository is named for."""

from __future__ import annotations

import pytest

from n_plus_one_budget.counting import BudgetExceeded, QueryCounter, connect


def test_a_fresh_counter_has_seen_nothing():
    assert QueryCounter().count == 0


def test_it_counts_what_the_cursor_runs(conn):
    conn.execute("SELECT 1").fetchall()
    conn.execute("SELECT 2").fetchall()
    assert conn.query_counter.count == 2


def test_an_n_plus_one_is_visible_as_a_count(conn):
    conn.execute("SELECT id FROM npo_author").fetchall()
    for author_id in range(1, 6):
        conn.execute("SELECT id FROM npo_book WHERE author_id = %s",
                     (author_id,)).fetchall()
    assert conn.query_counter.count == 6


def test_reset_clears_the_count_and_the_log(conn):
    conn.execute("SELECT 1").fetchall()
    conn.query_counter.reset()
    assert conn.query_counter.count == 0
    assert conn.query_counter.queries == []


class TestBudget:
    def test_a_path_within_budget_passes(self, conn):
        with conn.query_counter.budget(2):
            conn.execute("SELECT 1").fetchall()
            conn.execute("SELECT 2").fetchall()

    def test_one_query_too_many_fails(self, conn):
        with pytest.raises(BudgetExceeded), conn.query_counter.budget(2):
            for _ in range(3):
                conn.execute("SELECT 1").fetchall()

    def test_it_fails_on_the_offending_query_not_at_the_end(self, conn):
        """So the traceback points at the line somebody has to change."""
        reached = []
        with pytest.raises(BudgetExceeded), conn.query_counter.budget(1):
            conn.execute("SELECT 1").fetchall()
            conn.execute("SELECT 2").fetchall()
            reached.append("after")
        assert reached == []

    def test_the_message_counts_only_this_block(self, conn):
        conn.execute("SELECT 1").fetchall()
        conn.execute("SELECT 2").fetchall()
        with pytest.raises(BudgetExceeded) as caught, conn.query_counter.budget(1):
            conn.execute("SELECT 3").fetchall()
            conn.execute("SELECT 4").fetchall()
        assert "issued 2 queries against a budget of 1" in str(caught.value)

    def test_the_message_names_the_block(self, conn):
        with pytest.raises(BudgetExceeded) as caught, \
                conn.query_counter.budget(1, label="the author list page"):
            conn.execute("SELECT 1").fetchall()
            conn.execute("SELECT 2").fetchall()
        assert "the author list page" in str(caught.value)

    def test_the_message_shows_the_shapes_not_every_statement(self, conn):
        """An N+1 prints the same statement a hundred times; the shape is the signal."""
        with pytest.raises(BudgetExceeded) as caught, conn.query_counter.budget(3):
            conn.execute("SELECT id FROM npo_author").fetchall()
            for author_id in range(1, 8):
                conn.execute("SELECT id FROM npo_book WHERE author_id = %s",
                             (author_id,)).fetchall()
        message = str(caught.value)
        assert "x SELECT id FROM npo_book WHERE author_id" in message
        assert message.count("npo_book") <= 3

    def test_the_budget_is_lifted_when_the_block_ends(self, conn):
        with pytest.raises(BudgetExceeded), conn.query_counter.budget(1):
            conn.execute("SELECT 1").fetchall()
            conn.execute("SELECT 2").fetchall()
        for _ in range(5):
            conn.execute("SELECT 1").fetchall()

    def test_budgets_nest_and_the_outer_one_is_restored(self, conn):
        with conn.query_counter.budget(10, label="outer"):
            with pytest.raises(BudgetExceeded), conn.query_counter.budget(1, "inner"):
                conn.execute("SELECT 1").fetchall()
                conn.execute("SELECT 2").fetchall()
            conn.execute("SELECT 3").fetchall()
        assert conn.query_counter.count == 3


def test_the_simulated_round_trip_slows_every_query(fixture_db):
    import time

    with connect(fixture_db, round_trip_seconds=0.01) as conn:
        started = time.perf_counter()
        for _ in range(5):
            conn.execute("SELECT 1").fetchall()
        elapsed = time.perf_counter() - started
    assert elapsed >= 0.05


def test_no_round_trip_means_no_added_delay(fixture_db):
    import time

    with connect(fixture_db) as conn:
        started = time.perf_counter()
        for _ in range(5):
            conn.execute("SELECT 1").fetchall()
        elapsed = time.perf_counter() - started
    assert elapsed < 0.05
