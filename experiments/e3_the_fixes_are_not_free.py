"""E3. A join is one query and the batched pair is two, and that is not the whole bill.

The obvious conclusion from E1 and E2 is to use the fewest queries possible, which points
at the join. It is one round trip rather than two, and round trips are the thing that
costs.

The join pays elsewhere. It returns one row per child with every parent column repeated on
each of them, so a wide parent is sent again and again. The batched pair sends each parent
once and spends an extra round trip to do it. Which is cheaper is a trade between the width
of the parent and the distance to the database, and neither term is a constant.

Rows are the wrong unit for this and are reported anyway, because they are the unit people
reach for first: the join returns *fewer* rows than the batched pair while sending more
data. A row count says the join is the cheaper option at every width in this sweep.

This is also the limit of the tool this repository is named for. A query counter sees one
query and approves. The cost is in the payload, and nothing about counting queries will
ever show it.
"""

from __future__ import annotations

import json
from pathlib import Path

from n_plus_one_budget import theory
from n_plus_one_budget.config import DEFAULT_DSN, LoadConfig
from n_plus_one_budget.counting import connect
from n_plus_one_budget.database import ensure_schema
from n_plus_one_budget.harness import run_load
from n_plus_one_budget.loaders import payload_bytes

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
PARENTS = 100
CHILDREN = 6
WIDTHS = (20, 100, 500, 2000, 8000)
ROUND_TRIPS_MS = (0.0, 2.0)
REPEATS = 5


def measured_widths(parents: int) -> tuple[float, float]:
    """Average characters in a parent row and in a child row, as the loaders see them.

    Estimated at first, as a constant guessed from the fixture's shape. That was fine at
    wide parents, where the parent term dominates the ratio, and visibly wrong at narrow
    ones, where the child term does: the derived ratio missed the measurement by a sixth
    at the narrowest width in the sweep. Both widths are measured now.
    """
    with connect(DEFAULT_DSN) as conn:
        authors = conn.execute(
            "SELECT id, name, bio FROM npo_author ORDER BY id LIMIT %s",
            (parents,),
        ).fetchall()
        books = conn.execute(
            "SELECT author_id, id, title FROM npo_book WHERE author_id = ANY(%s)",
            ([author[0] for author in authors],),
        ).fetchall()
    return payload_bytes(authors) / len(authors), payload_bytes(books) / len(books)


def main() -> None:
    rows = []
    for width in WIDTHS:
        ensure_schema(DEFAULT_DSN, PARENTS, CHILDREN, width)
        entry = {"bio_width": width}
        for rtt in ROUND_TRIPS_MS:
            measured = {}
            for strategy in ("batched", "join"):
                config = LoadConfig(strategy=strategy, parents=PARENTS,
                                    children_each=CHILDREN, bio_width=width,
                                    round_trip_ms=rtt, repeats=REPEATS,
                                    dsn=DEFAULT_DSN)
                measured[strategy] = run_load(config, build_schema=False)
            key = f"rtt_{rtt:g}"
            entry[f"{key}_batched_ms"] = round(measured["batched"].ms, 3)
            entry[f"{key}_join_ms"] = round(measured["join"].ms, 3)
            entry[f"{key}_join_wins"] = measured["join"].ms < measured["batched"].ms
            if rtt == 0.0:
                entry["batched_bytes"] = measured["batched"].bytes_returned
                entry["join_bytes"] = measured["join"].bytes_returned
                entry["batched_rows"] = measured["batched"].rows_returned
                entry["join_rows"] = measured["join"].rows_returned

        parent_width, child_width = measured_widths(PARENTS)
        entry["measured_parent_width"] = round(parent_width, 2)
        entry["measured_child_width"] = round(child_width, 2)
        entry["bytes_ratio"] = round(entry["join_bytes"] / entry["batched_bytes"], 3)
        entry["predicted_bytes_ratio"] = round(
            theory.bytes_returned("join", PARENTS, CHILDREN, parent_width, child_width)
            / theory.bytes_returned(
                "batched", PARENTS, CHILDREN, parent_width, child_width), 3)
        entry["duplicated_bytes"] = round(
            theory.duplicated_bytes(PARENTS, CHILDREN, parent_width))
        rows.append(entry)

        print(f"  parent width {width:5}  join sends "
              f"{entry['bytes_ratio']:5.2f}x the bytes "
              f"(derived {entry['predicted_bytes_ratio']:5.2f}x) "
              f"in {entry['join_rows']} rows against {entry['batched_rows']}   "
              f"local: join {'wins' if entry['rtt_0_join_wins'] else 'LOSES'}, "
              f"at 2ms: join {'wins' if entry['rtt_2_join_wins'] else 'LOSES'}")

    ratios = [r["bytes_ratio"] for r in rows]
    predicted = [r["predicted_bytes_ratio"] for r in rows]
    agree = all(abs(a - b) / b < 0.1 for a, b in zip(ratios, predicted, strict=True))
    rows_always_favour_join = all(r["join_rows"] < r["batched_rows"] for r in rows)
    local_crossover = next(
        (r["bio_width"] for r in rows if not r["rtt_0_join_wins"]), None)
    remote_crossover = next(
        (r["bio_width"] for r in rows if not r["rtt_2_join_wins"]), None)

    payload = {
        "experiment": "e3_the_fixes_are_not_free",
        "parents": PARENTS, "children_each": CHILDREN, "repeats": REPEATS,
        "widths": list(WIDTHS), "rows": rows,
        "bytes_ratio_matches_derivation": agree,
        "ratio_grows_with_width": ratios == sorted(ratios),
        "rows_always_favour_the_join": rows_always_favour_join,
        "narrowest_ratio": ratios[0],
        "widest_ratio": ratios[-1],
        "widest_width": WIDTHS[-1],
        "widest_duplicated_bytes": rows[-1]["duplicated_bytes"],
        "local_crossover_width": local_crossover,
        "remote_crossover_width": remote_crossover,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e3.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"the payload ratio matches the derivation: {agree}")
    print(f"a row count favours the join at every width: {rows_always_favour_join}")
    print(f"at a parent of {WIDTHS[-1]} characters the join repeats "
          f"{rows[-1]['duplicated_bytes']:.0f} characters of parent row")
    print(f"the join stops winning locally at a parent width of "
          f"{local_crossover}, and across a 2ms network at {remote_crossover}")


if __name__ == "__main__":
    main()
