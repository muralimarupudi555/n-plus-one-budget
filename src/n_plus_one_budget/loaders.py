"""Three ways to load authors with their books, returning exactly the same thing.

That last part is the precondition for every number in this repository. Three strategies
that return different data are not three strategies, they are three features, and comparing
their costs is meaningless. Every loader here builds the same structure - authors in id
order, each with its books in id order - and the harness checks that they agree before it
reports a timing.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

AUTHORS_SQL = "SELECT id, name, bio FROM npo_author ORDER BY id LIMIT %s"
BOOKS_FOR_ONE_SQL = "SELECT id, title FROM npo_book WHERE author_id = %s ORDER BY id"
BOOKS_FOR_MANY_SQL = (
    "SELECT author_id, id, title FROM npo_book WHERE author_id = ANY(%s) "
    "ORDER BY author_id, id"
)
JOIN_SQL = (
    "SELECT a.id, a.name, a.bio, b.id, b.title "
    "FROM npo_author a JOIN npo_book b ON b.author_id = a.id "
    "WHERE a.id <= %s ORDER BY a.id, b.id"
)


def payload_bytes(rows: list[tuple]) -> int:
    """Characters in everything the database handed back.

    A proxy for wire bytes, not a measurement of them: the real protocol adds framing and
    type headers this does not count. It is the right proxy for the question E3 asks,
    which is how much of the payload is the same parent row sent again, and that ratio is
    unaffected by a constant per-row overhead.

    Rows are the wrong unit here, which is worth stating because they are the obvious one.
    A join returns *fewer* rows than the batched pair - one per child rather than parents
    plus children - while sending every parent column on each of them. Counting rows makes
    the join look cheaper than it is.
    """
    return sum(len(str(field)) for row in rows for field in row)


@dataclass(frozen=True)
class Loaded:
    """The result, plus what crossed the wire to produce it."""

    authors: list[tuple]
    rows_returned: int
    bytes_returned: int

    def shape(self) -> list[tuple]:
        """A comparable form: author id, name, and its book ids."""
        return [(author[0], author[1], tuple(book[0] for book in books))
                for author, books in self.authors]


def load_n_plus_one(conn: psycopg.Connection, parents: int) -> Loaded:
    """One query for the authors, then one per author. The accident, not the design.

    Nobody writes this on purpose. It is what an ORM does when a loop touches a related
    attribute, and the loop usually looks like it is only formatting output.
    """
    authors = conn.execute(AUTHORS_SQL, (parents,)).fetchall()
    rows = len(authors)
    size = payload_bytes(authors)
    out = []
    for author in authors:
        books = conn.execute(BOOKS_FOR_ONE_SQL, (author[0],)).fetchall()
        rows += len(books)
        size += payload_bytes(books)
        out.append((author, books))
    return Loaded(authors=out, rows_returned=rows, bytes_returned=size)


def load_batched(conn: psycopg.Connection, parents: int) -> Loaded:
    """Authors, then every book for all of them in one more query."""
    authors = conn.execute(AUTHORS_SQL, (parents,)).fetchall()
    ids = [author[0] for author in authors]
    books = conn.execute(BOOKS_FOR_MANY_SQL, (ids,)).fetchall()

    grouped: dict[int, list[tuple]] = {author_id: [] for author_id in ids}
    for author_id, book_id, title in books:
        grouped[author_id].append((book_id, title))
    return Loaded(
        authors=[(author, grouped[author[0]]) for author in authors],
        rows_returned=len(authors) + len(books),
        bytes_returned=payload_bytes(authors) + payload_bytes(books),
    )


def load_join(conn: psycopg.Connection, parents: int) -> Loaded:
    """One query, with every author column repeated on every one of its books.

    The single round trip is the attraction. The repetition is the price, and it is paid
    in bytes on the wire rather than in queries, so it is invisible to a query counter -
    which is worth saying out loud in a repository about counting queries.
    """
    rows = conn.execute(JOIN_SQL, (parents,)).fetchall()

    out: list[tuple] = []
    current_id = None
    books: list[tuple] = []
    author: tuple | None = None
    for author_id, name, bio, book_id, title in rows:
        if author_id != current_id:
            if author is not None:
                out.append((author, books))
            current_id, author, books = author_id, (author_id, name, bio), []
        books.append((book_id, title))
    if author is not None:
        out.append((author, books))
    return Loaded(authors=out, rows_returned=len(rows),
                  bytes_returned=payload_bytes(rows))


LOADERS = {
    "n_plus_one": load_n_plus_one,
    "batched": load_batched,
    "join": load_join,
}


def load(strategy: str, conn: psycopg.Connection, parents: int) -> Loaded:
    try:
        loader = LOADERS[strategy]
    except KeyError:
        raise ValueError(f"unknown strategy {strategy!r}") from None
    return loader(conn, parents)
