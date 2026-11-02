"""Exit codes, because they are the interface a pipeline uses."""

from __future__ import annotations

import json

from n_plus_one_budget.cli import (
    EXIT_BAD_CONFIG,
    EXIT_OVER_BUDGET,
    EXIT_WITHIN_BUDGET,
    main,
)

SMALL = ["--parents", "20", "--repeats", "2"]


def test_an_n_plus_one_exits_four(dsn, capsys):
    assert main(["--strategy", "n_plus_one", "--dsn", dsn, *SMALL]) == EXIT_OVER_BUDGET
    assert "more round trips than it needs" in capsys.readouterr().out


def test_the_batched_loader_exits_zero(dsn):
    assert main(["--strategy", "batched", "--dsn", dsn, *SMALL]) == EXIT_WITHIN_BUDGET


def test_the_join_exits_zero(dsn):
    assert main(["--strategy", "join", "--dsn", dsn, *SMALL]) == EXIT_WITHIN_BUDGET


def test_a_disabled_budget_exits_zero_even_for_an_n_plus_one(dsn):
    assert main(["--strategy", "n_plus_one", "--budget", "0",
                 "--dsn", dsn, *SMALL]) == EXIT_WITHIN_BUDGET


def test_the_report_prices_the_trips_at_several_distances(dsn, capsys):
    main(["--strategy", "n_plus_one", "--dsn", dsn, *SMALL])
    out = capsys.readouterr().out
    assert "at    5 ms round trip" in out
    assert "The first of those is a developer machine" in out


def test_the_join_is_told_what_it_costs(dsn, capsys):
    main(["--strategy", "join", "--dsn", dsn, *SMALL])
    out = capsys.readouterr().out
    assert "parent rows sent again" in out
    assert "worth knowing about query counters" in out


def test_a_parent_with_no_children_exits_two(dsn, capsys):
    assert main(["--children-each", "0", "--dsn", dsn, *SMALL]) == EXIT_BAD_CONFIG
    assert "no N+1 to find" in capsys.readouterr().err


def test_too_few_parents_exits_two(dsn):
    assert main(["--parents", "3", "--dsn", dsn]) == EXIT_BAD_CONFIG


def test_an_unreachable_database_exits_three(capsys):
    code = main(["--dsn", "postgresql://postgres@127.0.0.1:1/postgres", *SMALL])
    assert code == 3
    assert "failed to complete" in capsys.readouterr().err


def test_json_output_parses(dsn, capsys):
    main(["--strategy", "batched", "--json", "--dsn", dsn, *SMALL])
    payload = json.loads(capsys.readouterr().out)
    assert payload["queries"] == 2
    assert payload["over_budget"] is False
    assert payload["measurement_valid"] is True
