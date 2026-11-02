"""The cost model, tested as properties rather than restated as formulas."""

from __future__ import annotations

import pytest

from n_plus_one_budget import theory


def test_n_plus_one_is_one_per_parent_plus_one():
    assert theory.query_count("n_plus_one", 100) == 101


def test_batching_is_two_whatever_the_size():
    assert theory.query_count("batched", 10) == theory.query_count("batched", 10_000) == 2


def test_a_join_is_one():
    assert theory.query_count("join", 10_000) == 1


def test_an_unknown_strategy_is_refused():
    with pytest.raises(ValueError, match="unknown strategy"):
        theory.query_count("lazy_maybe", 10)


def test_extra_round_trips_grow_with_the_parents():
    counts = [theory.extra_round_trips(n) for n in (10, 100, 1000)]
    assert counts == sorted(counts)
    assert theory.extra_round_trips(100) == 99


def test_predicted_time_is_trips_times_the_trip():
    assert theory.predicted_seconds("n_plus_one", 99, 0.001) == pytest.approx(0.1)


def test_with_no_per_query_cost_the_strategies_are_indistinguishable():
    """The degenerate case a local benchmark approaches, and reports as a result."""
    assert theory.slowdown(100, 0.0, 0.0) == 1.0


def test_the_slowdown_is_the_query_ratio_once_trips_cost_anything():
    assert theory.slowdown(100, 0.002) == pytest.approx(101 / 2)


def test_a_hundred_extra_trips_are_invisible_on_a_loopback():
    assert theory.invisible_below(100, 0.00005)


def test_the_same_trips_are_obvious_across_a_network():
    assert not theory.invisible_below(100, 0.002)


def test_the_threshold_is_crossed_somewhere_between_them():
    visible = [theory.invisible_below(100, r) for r in
               (0.00005, 0.0001, 0.0005, 0.001, 0.002)]
    assert visible[0] is True
    assert visible[-1] is False
    assert visible == sorted(visible, reverse=True)


def test_a_join_returns_fewer_rows_than_the_batched_pair():
    """The trap in counting rows: fewer rows, more payload."""
    assert theory.rows_returned("join", 50, 4) < theory.rows_returned("batched", 50, 4)


def test_but_a_join_sends_more_bytes():
    joined = theory.bytes_returned("join", 50, 4, parent_width=200, child_width=20)
    batched = theory.bytes_returned("batched", 50, 4, parent_width=200, child_width=20)
    assert joined > batched


def test_the_gap_widens_with_the_parent_width():
    def ratio(width: int) -> float:
        joined = theory.bytes_returned("join", 50, 4, width, 20)
        batched = theory.bytes_returned("batched", 50, 4, width, 20)
        return joined / batched

    assert ratio(2000) > ratio(200) > ratio(20)


def test_a_join_duplicates_one_parent_row_per_extra_child():
    assert theory.duplicated_parent_rows(50, 4) == 150
    assert theory.duplicated_parent_rows(50, 1) == 0


def test_duplicated_bytes_are_the_duplicated_rows_times_the_width():
    assert theory.duplicated_bytes(50, 4, 200) == 150 * 200


def test_a_single_child_each_makes_the_join_free_of_duplication():
    joined = theory.bytes_returned("join", 50, 1, 200, 20)
    batched = theory.bytes_returned("batched", 50, 1, 200, 20)
    assert joined == batched
