# ADR-001: Counting at the cursor, and failing on the query that broke the budget

**Status.** Accepted.

## The decision

Queries are counted by a cursor subclass, so every statement that leaves the process is
seen. A budget is a context manager that raises the moment the count passes its limit.

## Why the cursor

An application does not decide how many queries it issues. Its ORM does, two layers down,
in response to an attribute access that looks free. `for author in authors: print(
author.books)` is the entire defect, and nothing in that line says "query".

So counting has to happen where the queries actually are, not where somebody remembered to
instrument. A counter at the cursor sees the ones nobody wrote, which are the only ones
worth catching - a developer who knows they are issuing a hundred queries does not need a
tool.

In a real application the same hook exists: SQLAlchemy has `before_cursor_execute`, Django
has `connection.queries` and `CaptureQueriesContext`. The mechanism here is the stripped
down version of what those give you, so that what the budget does is visible rather than
framework-shaped.

## Why it raises immediately

A budget that checks at the end of the block can only name the block. A budget that raises
on the offending query puts that query's call site in the traceback, which is the line
somebody has to change. For an N+1 inside an ORM that line is often in a template or a
serialiser rather than anywhere near the query, and finding it from a block-level count
means reading the whole block.

## Why counts are relative to the block

The first version reported absolute counts against an absolute limit, so a block with a
budget of two that ran three queries was reported as four queries against three when one
query had run earlier in the connection's life. The numbers were correct and the message
sent the reader looking in the wrong place. A budget is a statement about one code path,
so what it reports is that path.

## Why the message shows shapes

The output of an N+1 is the same statement a hundred times. Printing all hundred buries
the one line that matters - the other statement, the one that fetched the parents - under
a hundred copies of the symptom. The message groups by shape with a count, so the two
lines that explain the problem are the first two lines of the output.

## What this costs

The counter takes a lock per query. That is real overhead and it is tiny next to a round
trip, which is the thing this whole repository is about. It is also optional: nothing
forces a production deployment to use the counting cursor, and the usual arrangement is to
enable it in tests, where the budget lives.
