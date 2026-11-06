"""Advisory per-grade time budget: compare two bench report CSVs (issue #176).

    PYTHONPATH=. uv run python -m benchmark.budget --baseline old.csv new.csv
    PYTHONPATH=. uv run python -m benchmark.budget old.csv new.csv --tolerance 1.25

Reads the per-puzzle CSVs `benchmark.bench` writes (the `grade` and `ms`
columns), summarises each grade as median and p90 ms over the puzzles that
finished, and prints the strength delta (solved count) next to the timing
delta — so a rule's cost is visible beside its gain. Advisory only: nothing
here fails a build; CI keeps failing only on wrong or unsound results.

`read`, `per_grade` and `compare` are importable, so a scratch script can get
the delta without the CLI.
"""

import argparse
import csv
import statistics
from pathlib import Path

from benchmark import bench


def read(path: str | Path) -> list[dict[str, str]]:
    """The rows of a bench report CSV."""
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def _finished_ms(rows: list[dict[str, str]]) -> list[float]:
    return [float(row["ms"]) for row in rows if row.get("timed_out") != "1"]


def per_grade(rows: list[dict[str, str]]) -> dict[str, dict[str, float | int | None]]:
    """grade -> {puzzles, solved, median ms, p90 ms} over the finished puzzles."""
    summary: dict[str, dict[str, float | int | None]] = {}
    for grade in {row["grade"] for row in rows}:
        members = [row for row in rows if row["grade"] == grade]
        times = _finished_ms(members)
        summary[grade] = {
            "puzzles": len(members),
            "solved": sum(1 for row in members if row.get("solved") == "1"),
            "median": statistics.median(times) if times else None,
            "p90": bench.percentile(times, 0.9) if times else None,
        }
    return summary


def _order(grades: set[str]) -> list[str]:
    known = [grade for grade in bench.GRADES if grade in grades]
    return known + sorted(grade for grade in grades if grade not in bench.GRADES)


def compare(
    baseline: list[dict[str, str]],
    current: list[dict[str, str]],
    tolerance: float = 1.25,
) -> list[dict[str, object]]:
    """Per grade: puzzles, solved delta, median/p90 deltas, and an over-budget flag.

    `over` is true when the current p90 exceeds the baseline p90 by more than
    `tolerance` (a 25% budget by default) — the advisory the issue asks for.
    """
    base, cur = per_grade(baseline), per_grade(current)
    lines: list[dict[str, object]] = []
    for grade in _order(set(base) | set(cur)):
        before, after = base.get(grade), cur.get(grade)
        over = bool(
            before
            and after
            and before["p90"]
            and after["p90"]
            and after["p90"] > before["p90"] * tolerance
        )
        lines.append({"grade": grade, "base": before, "current": after, "over": over})
    return lines


def _cell(before: float | None, after: float | None) -> str:
    if before is None and after is None:
        return "n/a"
    if before is None or after is None:
        value = after if after is not None else before
        return f"{value:.0f}"
    delta = 100 * (after - before) / before if before else 0.0
    return f"{before:.0f} → {after:.0f} ({delta:+.0f}%)"


def render(lines: list[dict[str, object]], tolerance: float) -> str:
    """The comparison as a Markdown table (strength delta beside timing delta)."""
    out = [
        f"Per-grade budget, p90 tolerance {tolerance:.2f}x",
        "",
        "| Grade | Puzzles | Solved Δ | Median ms | p90 ms | Budget |",
        "|---|---:|---:|---|---|---|",
    ]
    for line in lines:
        before, after = line["base"], line["current"]
        assert before is not None or after is not None
        b = before or {"puzzles": 0, "solved": 0, "median": None, "p90": None}
        a = after or {"puzzles": 0, "solved": 0, "median": None, "p90": None}
        puzzles = f"{b['puzzles']} → {a['puzzles']}"
        solved = int(a["solved"]) - int(b["solved"])
        budget = "**OVER**" if line["over"] else "ok"
        out.append(
            f"| `{line['grade']}` | {puzzles} | {solved:+d} | "
            f"{_cell(b['median'], a['median'])} | {_cell(b['p90'], a['p90'])} | {budget} |"
        )
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("baseline", type=Path, help="the accepted (older) report CSV")
    parser.add_argument("current", type=Path, help="the new report CSV to judge")
    parser.add_argument("--tolerance", type=float, default=1.25, help="p90 budget, as a ratio")
    args = parser.parse_args()
    print(render(compare(read(args.baseline), read(args.current), args.tolerance), args.tolerance))


if __name__ == "__main__":
    main()
