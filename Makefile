# `make verify` is the gate. It needs the database but not the network, and must pass on a
# clean clone.
#
# `make bench` runs the experiments and the transcript, which drive real threads against a
# real clock and take a couple of minutes. The transcript lives here rather than in the
# gate because its counts move slightly between runs, and a gate that leaves uncommitted
# changes behind is one people stop reading the output of.

PYTHON := python3
DSN ?= postgresql://postgres:postgres@127.0.0.1:5433/postgres
export NPLUSONE_DSN = $(DSN)

.PHONY: help install db-up db-down lint test verify bench tables cli clean

help:
	@echo "make install   install the package and its development dependencies"
	@echo "make db-up     start the PostgreSQL these loads run against"
	@echo "make verify    lint, tests, law check, number check - the gate"
	@echo "make bench     run the three experiments"

install:
	$(PYTHON) -m pip install -e ".[dev]"

db-up:
	docker compose up -d --wait

db-down:
	docker compose down -v

lint:
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest

tables:
	$(PYTHON) tools/render_tables.py

cli:
	$(PYTHON) tools/capture_cli.py

verify: lint test tables
	$(PYTHON) tools/check_workflow.py
	$(PYTHON) tools/check_laws.py
	$(PYTHON) tools/collect_metrics.py
	$(PYTHON) tools/check_numbers.py

bench: cli
	$(PYTHON) experiments/e1_counting_what_time_cannot_see.py
	$(PYTHON) experiments/e2_the_cost_is_round_trips.py
	$(PYTHON) experiments/e3_the_fixes_are_not_free.py

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info
