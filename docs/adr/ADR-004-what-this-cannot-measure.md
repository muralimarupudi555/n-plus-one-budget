# ADR-004: What this cannot measure

**Status.** Accepted. Read this before quoting any figure from here.

## A query counter cannot see the join's bill

This is the limit of the tool the repository is named for, and E3 exists to make it
explicit. A join is one query. A counter sees one query and approves, at every parent width
in the sweep, including the widths where the join is the slower option.

The cost is in the payload, and a row count does not show it either: the join returns **600
rows against** the batched pair's **against 700 rows** while sending **that becomes 5.95x**
the bytes at the widest parent. Fewer rows, more data. Any budget expressed in queries will
approve of a query that ships megabytes.

So a query budget is a check on one failure mode, not a definition of a good query. It
catches the N+1, which is the common accident, and it is silent about the other one.

## The round trip is a sleep

ADR-002 argues why that is the right shape and ADR-003 describes what it costs. The
headline is that the absolute milliseconds here carry an injection overhead a real network
does not have, so the ratios travel and the times do not.

## One connection, no pool, no concurrency

Every measurement runs on a single connection with nothing else happening. A real
application has a pool, and an N+1 holds a connection for the whole of its hundred round
trips - so under load the defect does not only make one request slow, it occupies a
connection a hundred times longer than it needs to and starves everything else. That effect
is larger than anything measured here and is entirely absent from it.

## No ORM

The N+1 is written out by hand, which makes the mechanism legible and misses the part that
makes it common: in a real codebase nobody writes the loop that issues the queries. They
write a template that touches an attribute. Whether a given ORM configuration produces an
N+1 is a question about that ORM, and this cannot answer it.

What does transfer is the budget: the same context manager over `before_cursor_execute` or
`CaptureQueriesContext` catches the same defect, and the count it produces means the same
thing.

## The fixture is uniform

Every parent has the same number of children. Real data has a long tail, and the page that
is fine in testing is the one whose worst parent has ten thousand children. Nothing here
varies that, and the arithmetic says the query count would not change - which is exactly
why a query budget would pass that page while the payload sank it.

## Server time is near zero

The queries are trivial and the tables are small and cached, so the server time term in
`queries * (round_trip + server_time)` is nearly nothing. That flatters the batched and
join strategies in one specific way: a join of large tables can choose a worse plan than
two simple queries, and no plan in this repository is ever in doubt. A join that turns into
a hash join over a spilled sort is a different subject.

## What is left standing

That the three strategies issue `1 + n`, `2` and `1` queries; that the cost of the extra
ones is round trips, which are nearly free locally and not at all free across a network;
that the gap therefore cannot be seen on the machine the code is written on; and that
counting queries sees it anyway, on any machine, before the code ships.
