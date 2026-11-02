"""Read the experiment outputs and write the file every document is checked against."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = ROOT / "docs" / "experiments"
OUT = ROOT / "docs" / "metrics.json"

CHECKED_DOCUMENTS = (
    "README.md",
    "docs/adr/ADR-001-counting-at-the-cursor.md",
    "docs/adr/ADR-002-simulating-distance-with-a-sleep.md",
    "docs/adr/ADR-003-three-apparatus-mistakes.md",
    "docs/adr/ADR-004-what-this-cannot-measure.md",
)


def load(name: str) -> dict:
    path = EXPERIMENTS / name
    if not path.exists():
        raise SystemExit(
            f"missing {path.relative_to(ROOT)}. Run `make bench` first: the documents "
            "are checked against measurements."
        )
    return json.loads(path.read_text())


def count_tests() -> int:
    out = subprocess.run(
        ["python3", "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout
    per_file = re.findall(r"^\S+\.py: (\d+)$", out, re.MULTILINE)
    if per_file:
        return sum(int(n) for n in per_file)
    for line in reversed(out.splitlines()):
        match = re.match(r"^(\d+) tests? collected", line.strip())
        if match:
            return int(match.group(1))
    node_ids = sum(1 for line in out.splitlines() if "::" in line)
    if node_ids == 0:
        raise SystemExit("could not count tests from pytest's output; fix count_tests().")
    return node_ids


def main() -> None:
    e1, e2, e3 = (load(f"e{i}.json") for i in (1, 2, 3))

    largest = max(e1["sizes"])
    largest_rows = {r["strategy"]: r for r in e1["rows"] if r["parents"] == largest}
    narrow, wide = e3["rows"][0], e3["rows"][-1]

    metrics = {
        "largest_page": largest,
        "largest_page_queries": largest_rows["n_plus_one"]["queries"],
        "largest_page_npo_ms": largest_rows["n_plus_one"]["ms"],
        "largest_page_batched_ms": largest_rows["batched"]["ms"],
        "worst_local_difference_ms": e1["worst_local_difference_ms"],

        "sweep_parents": e2["parents"],
        "extra_round_trips": e2["extra_round_trips"],
        "local_slowdown": e2["local_slowdown"],
        "local_extra_ms": e2["local_extra_ms"],
        "remote_round_trip_ms": e2["remote_round_trip_ms"],
        "remote_slowdown": e2["remote_slowdown"],
        "remote_extra_ms": e2["remote_extra_ms"],
        "remote_npo_ms": e2["remote_n_plus_one_ms"],
        "first_noticeable_ms": e2["first_noticeable_round_trip_ms"],
        "cost_per_trip_slope": e2["cost_per_trip_slope"],
        "injection_overhead_ms": e2["injection_overhead_ms"],

        "narrow_parent": narrow["bio_width"],
        "narrow_bytes_ratio": narrow["bytes_ratio"],
        "wide_parent": wide["bio_width"],
        "wide_bytes_ratio": wide["bytes_ratio"],
        "wide_duplicated_bytes": int(wide["duplicated_bytes"]),
        "join_rows": wide["join_rows"],
        "batched_rows": wide["batched_rows"],
        "local_crossover": e3["local_crossover_width"],
        "remote_crossover": e3["remote_crossover_width"],

        "tests": count_tests(),
    }

    display = {
        "largest_page_npo_ms": f"{metrics['largest_page_npo_ms']:.1f}",
        "largest_page_batched_ms": f"{metrics['largest_page_batched_ms']:.1f}",
        "worst_local_difference_ms": f"{metrics['worst_local_difference_ms']:.1f}",
        "local_slowdown": f"{metrics['local_slowdown']:.1f}",
        "local_extra_ms": f"{metrics['local_extra_ms']:.1f}",
        "remote_slowdown": f"{metrics['remote_slowdown']:.0f}",
        "remote_extra_ms": f"{metrics['remote_extra_ms']:.0f}",
        "remote_npo_ms": f"{metrics['remote_npo_ms']:.0f}",
        "remote_round_trip_ms": f"{metrics['remote_round_trip_ms']:g}",
        "first_noticeable_ms": f"{metrics['first_noticeable_ms']:g}",
        "cost_per_trip_slope": f"{metrics['cost_per_trip_slope']:.2f}",
        "injection_overhead_ms": f"{metrics['injection_overhead_ms']:.2f}",
        "narrow_bytes_ratio": f"{metrics['narrow_bytes_ratio']:.2f}",
        "wide_bytes_ratio": f"{metrics['wide_bytes_ratio']:.2f}",
    }
    for key, value in metrics.items():
        display.setdefault(key, str(value))

    anchors = {
        "largest_page": ["{} parents"],
        "largest_page_queries": ["{} queries"],
        "largest_page_npo_ms": ["{} ms against"],
        "largest_page_batched_ms": ["against {} ms"],
        "worst_local_difference_ms": ["worst local difference was {} ms"],
        "sweep_parents": ["a page of {} parents"],
        "extra_round_trips": ["{} more round trips"],
        "local_slowdown": ["{}x slower locally"],
        "local_extra_ms": ["{} ms of difference"],
        "remote_round_trip_ms": ["at a {} ms round trip"],
        "remote_slowdown": ["becomes {}x slower"],
        "remote_extra_ms": ["{} ms worse"],
        "remote_npo_ms": ["takes {} ms"],
        "first_noticeable_ms": ["somewhere around {} ms"],
        "cost_per_trip_slope": ["slope of {}"],
        "injection_overhead_ms": ["overhead of {} ms"],
        "narrow_parent": ["a parent of {} characters"],
        "narrow_bytes_ratio": ["sends {}x the bytes"],
        "wide_parent": ["at {} characters"],
        "wide_bytes_ratio": ["that becomes {}x"],
        "wide_duplicated_bytes": ["{} characters of repeated"],
        "join_rows": ["{} rows against"],
        "batched_rows": ["against {} rows"],
        "local_crossover": ["loses locally at {}"],
        "remote_crossover": ["only at {} characters"],
        "tests": ["{} tests"],
    }

    OUT.write_text(json.dumps({
        "metrics": metrics, "display": display, "anchors": anchors,
        "checked_documents": list(CHECKED_DOCUMENTS),
    }, indent=2) + "\n")
    print(f"collected {len(metrics)} metrics into {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
