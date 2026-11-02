"""Authors and their books: the smallest schema that can have an N+1 in it."""

from __future__ import annotations

import psycopg

SCHEMA = """
DROP TABLE IF EXISTS npo_book;
DROP TABLE IF EXISTS npo_author;
CREATE TABLE npo_author (
    id int PRIMARY KEY,
    name text NOT NULL,
    bio text NOT NULL
);
CREATE TABLE npo_book (
    id int PRIMARY KEY,
    author_id int NOT NULL REFERENCES npo_author (id),
    title text NOT NULL
);
CREATE INDEX npo_book_author ON npo_book (author_id);
"""


def ensure_schema(dsn: str, authors: int, books_each: int,
                  bio_width: int = 200) -> None:
    """Build the fixture.

    `bio_width` is a knob rather than decoration. A join repeats every parent column on
    every child row, so how much a join wastes depends on how wide the parent is, and E3
    varies it rather than picking one and generalising.
    """
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(SCHEMA)
        conn.execute(
            "INSERT INTO npo_author (id, name, bio) "
            "SELECT g, 'author-' || g, repeat('b', %s) "
            "FROM generate_series(1::bigint, %s::bigint) AS g",
            (bio_width, authors),
        )
        conn.execute(
            "INSERT INTO npo_book (id, author_id, title) "
            "SELECT g, ((g - 1) / %s) + 1, 'title-' || g "
            "FROM generate_series(1::bigint, %s::bigint) AS g",
            (books_each, authors * books_each),
        )
        conn.execute("ANALYZE npo_author")
        conn.execute("ANALYZE npo_book")
