# n-plus-one-budget

**An N+1 does not raise, does not log, does not appear in a slow query report, and does not
move a p50 on the machine it was written on. Each query is fast. There are simply a hundred
of them, and the cost is a hundred round trips — which are nearly free locally and not at
all free across a network.**

The only instrument that sees it on a developer's machine is a count of queries, because
the count is the same number everywhere and the time is not.

```python
with conn.query_counter.budget(2, label="the author list page"):
    render_authors(conn)
```

```text
the author list page issued 3 queries against a budget of 2.
The query that broke it: SELECT id, title FROM npo_book WHERE author_id = %s ORDER BY id
Queries in this block:
      2 x SELECT id, title FROM npo_book WHERE author_id = %s ORDER BY id
      1 x SELECT id, name, bio FROM npo_author ORDER BY id LIMIT %s
```

## E1. The counts are exact and the local clock is useless

Three strategies, four page sizes, every query count matching its definition exactly —
`1 + n`, `2`, `1` — and every strategy returning identical results, which is the
precondition for comparing their costs at all.

<!-- table:e1 -->
```text
  parents   n+1 q   n+1 ms  batch q  batch ms  join q  join ms  difference
--------------------------------------------------------------------------
       25      26     5.05        2      1.97       1     1.54        3.08
       50      51     7.47        2      2.21       1     1.90        5.27
      100     101    12.28        2      2.62       1     1.92        9.66
      200     201    23.18        2      2.95       1     2.99       20.23
```
<!-- /table:e1 -->

At **200 parents** the N+1 issues **201 queries** and takes **23.2 ms against** the batched
pair's **against 2.9 ms**. The **worst local difference was 20.2 ms** across the whole
sweep — under the threshold where a human notices a page is slow, and far under the noise
of any timing assertion anyone would write.

That is the finding, not a disappointment. The clock on the machine where the code was
written is the wrong instrument.

## E2. The same code at six distances

Nothing changes across this sweep. The page is identical, the query counts are identical,
the database does identical work. Only the round trip moves.

<!-- table:e2 -->
```text
   asked   really   n+1 ms  batch ms  join ms   slower   to a user
------------------------------------------------------------------
     0.0    0.000     13.3      2.36     1.93     5.6x   invisible
     0.1    0.171     36.1      2.97     2.12    12.1x   invisible
     0.5    0.612     99.0      3.79     2.68    26.1x   invisible
     1.0    1.125    155.3      5.28     3.12    29.4x     noticed
     2.0    2.126    263.3      6.88     4.25    38.2x     noticed
     5.0    5.148    576.4     13.20     7.34    43.7x     noticed
```
<!-- /table:e2 -->

On **a page of 100 parents** the N+1 spends **99 more round trips** than it needs. Locally
that makes it **5.6x slower locally**, **10.9 ms of difference** — invisible. **At a 5 ms
round trip** the same code **becomes 44x slower**, **563 ms worse**, and **takes 576 ms**.
The threshold where a user would notice falls **somewhere around 1 ms** of round trip,
which is an ordinary number inside a datacentre and a small one between availability zones.

The apparatus check is on the slope, not the absolute time: cost per extra round trip
should rise one-for-one with the round trip, and it does, at a **slope of 1.05**. The
intercept is the cost of injecting delay with a sleep, an **overhead of 0.33 ms** per
query, disclosed rather than assumed away. Getting that check right took three attempts and
[ADR-003](docs/adr/ADR-003-three-apparatus-mistakes.md) describes all three.

## E3. The fixes are not free, and the counter cannot see why

The obvious conclusion is to use the fewest queries possible, which points at the join: one
round trip instead of two. But a join returns one row per child with every parent column
repeated on each of them.

<!-- table:e3 -->
```text
   parent  join rows  batch rows    bytes  derived    local   at 2ms
--------------------------------------------------------------------
       20        600         700    2.27x    2.37x     join     join
      100        600         700    3.82x    3.88x     join     join
      500        600         700    5.29x    5.31x     join     join
     2000        600         700    5.80x    5.81x  batched     join
     8000        600         700    5.95x    5.95x  batched  batched
```
<!-- /table:e3 -->

At **a parent of 20 characters** the join **sends 2.27x the bytes**; **at 8000 characters**
**that becomes 5.95x**, which is **4005420 characters of repeated** parent row. The join
**loses locally at 2000** characters of parent and across a two millisecond network
**only at 8000 characters** — the further away the database, the longer the single round
trip stays worth paying for.

A row count never sees any of it: the join returns **600 rows against** the batched pair's
**against 700 rows** at every width in the sweep. Fewer rows, more data.

**And neither does a query counter.** One query, approved, at every width — including the
widths where it is the slower option. That is the honest limit of the tool this repository
is named for: a query budget catches the common accident and is silent about the other one.

## Why a budget and not a timing assertion

A timing assertion encodes the machine it was written on. It passes on a loopback
connection, where a hundred extra round trips cost ten milliseconds, and says nothing about
the same code at two milliseconds of round trip where they cost two hundred.

A query count is the same integer everywhere. `1 + n` is `1 + n` on a laptop, in CI, and in
production, so a budget asserted in a test fails in the place where it is cheapest to fix —
before the code ships — rather than in the place where it is most expensive.

The budget here raises on the query that broke it rather than at the end of the block, so
the traceback points at the line somebody has to change; for an ORM that line is usually in
a template or a serialiser rather than anywhere near a query.
[ADR-001](docs/adr/ADR-001-counting-at-the-cursor.md) covers the mechanism, including the
equivalent hooks in SQLAlchemy and Django.

## How the numbers are kept honest

Every loader is checked against a reference result before any timing is reported. Three
strategies that return different data are not three strategies, and comparing their costs
would be meaningless.

Every query count is checked against its definition. These are exact integers rather than
samples, so a strategy issuing a different number than `1 + n`, `2` or `1` is not the
strategy under test — and the usual cause in a real codebase is an ORM quietly adding one.

`tools/check_laws.py` re-derives the counts and the payload ratios on every `make verify`
and checks them against the committed results, so the published figures stay checkable on a
machine that has never run them. It was run against tampered results before being trusted.

## What this cannot measure

Read [ADR-004](docs/adr/ADR-004-what-this-cannot-measure.md) first:

- **A query counter cannot see the join's bill**, which is the point of E3 and the limit of
  this tool.
- **One connection, no pool.** Under load an N+1 does not only make one request slow, it
  holds a connection a hundred times longer than it needs and starves everything else. That
  effect is larger than anything measured here and entirely absent from it.
- **No ORM.** The N+1 is written out by hand, which makes the mechanism legible and misses
  the part that makes it common: nobody writes the loop, they write a template that touches
  an attribute.
- **A uniform fixture.** Real data has a long tail, and the page that is fine in testing is
  the one whose worst parent has ten thousand children — which a query budget would pass.
- **The round trip is a sleep**, so the absolute milliseconds carry an injection overhead a
  real network does not have. The ratios travel; the times do not.

## Running it

`make verify` is the gate: lint, **68 tests**, the law check and the number check.

```bash
make install
make db-up      # PostgreSQL 16.15, pinned, on port 5433
make verify
make bench      # the three experiments
```

A single page load, with the exit code as the interface:

```bash
n-plus-one-budget --strategy n_plus_one --parents 100 --budget 2
```

| exit | meaning |
| --- | --- |
| 0 | the page stayed within its query budget |
| 2 | the scenario cannot show the effect |
| 3 | the load did not complete |
| 4 | the page issued more queries than it was allowed |
| 5 | the result or the count disagreed with the definition |

Real transcripts are in [docs/cli-output.md](docs/cli-output.md).

## Layout

```text
src/n_plus_one_budget/
  config.py     scenario validation that refuses loads which cannot show the effect
  theory.py     query counts and payload sizes, derived before any measurement
  counting.py   a counting cursor, a budget that fails on the offending query
  database.py   authors and books, with a parent width that can be varied
  loaders.py    N+1, batched and join, all returning exactly the same thing
  harness.py    one page load, checked against a reference result first
  report.py     verdict, and what the extra trips would cost at five distances
  cli.py        exit codes
experiments/    the three experiments above
tools/          metric collection, the two checkers, the tables, the transcripts
docs/adr/       five decision records, including four mistakes and their fixes
```

## How this was built

This repository was built by Murali Marupudi working with Claude, an AI assistant, as a
pair-programming partner. The claim, the experimental design, the decisions about what to
measure and what to throw away, and the judgement calls recorded in the decision records
are the author's. Claude was used for implementation, for argument, and as a second pair of
eyes on the measurements.

## Licence

MIT. See [LICENSE](LICENSE).
