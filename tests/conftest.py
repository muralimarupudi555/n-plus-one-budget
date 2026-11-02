"""Shared fixtures.

Tests that need a database take `dsn`. There is no skip-if-unavailable guard: a suite that
quietly passes with half its tests skipped means something different from one machine to
the next.
"""

from __future__ import annotations

import pytest

from n_plus_one_budget.config import DEFAULT_DSN
from n_plus_one_budget.counting import connect
from n_plus_one_budget.database import ensure_schema

# Exposed as fixtures rather than imported from here. A test module cannot import from
# conftest without the tests being a package, and duplicating the numbers in each module
# invites them to drift apart from the fixture that builds the schema.
PARENTS = 20
CHILDREN = 3


@pytest.fixture(scope="session")
def dsn() -> str:
    return DEFAULT_DSN


@pytest.fixture
def parents() -> int:
    return PARENTS


@pytest.fixture
def children() -> int:
    return CHILDREN


@pytest.fixture
def fixture_db(dsn: str) -> str:
    ensure_schema(dsn, PARENTS, CHILDREN)
    return dsn


@pytest.fixture
def conn(fixture_db: str):
    with connect(fixture_db) as connection:
        yield connection
