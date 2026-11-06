"""Confirm parity with the older `operdeck/sudoku` Java solver (issue #78).

    uv run python -m benchmark.java_parity
    uv run python -m benchmark.java_parity --timeout 60 --ladder no-what-if

The Java solver's own corpus is the MagicTour/Norvig `top95` its `main` runs,
the named hard puzzles in its `PuzzleDB.java`, and its four-square (NRC)
puzzles. `top95.txt` is byte-identical to this repo's `norvig` corpus, so
`benchmark.bench --source norvig` already covers it; what is not covered is the
named hard 9x9 set and the NRC puzzles, and those are what this runs.

The corpus is the Java project's source, fetched into the ignored cache by
`corpus.fetch` (the puzzles are published ones -- Trouw, Parool,
extremesudoku.info -- so, like every other corpus here, they are never
committed). `extract_java` and `extract_python` read the puzzle literals out of
that source.

Each puzzle is compiled and solved with one rule ladder, in the same worker and
under the same time limit as `benchmark.bench`, and judged against an
independent answer (the brute force's). `--ladder no-what-if` answers the parity
question directly: a puzzle the Java forcing chains close but this ladder can
only assume is one this engine does not, in fact, deduce.
"""

import argparse
import re
import sys
from pathlib import Path

from benchmark import bench, corpus

JAVA_FILES = (
    (
        "PuzzleDB.java",
        "https://raw.githubusercontent.com/operdeck/sudoku/master/"
        "src/main/java/ottop/sudoku/PuzzleDB.java",
    ),
    (
        "SudokuPuzzles.py",
        "https://raw.githubusercontent.com/operdeck/sudoku/master/python/sudokupy/SudokuPuzzles.py",
    ),
    (
        "top95.txt",
        "https://raw.githubusercontent.com/operdeck/sudoku/master/src/main/resources/top95.txt",
    ),
)

# The four extra 3x3 squares of an NRC (Hyper/Four-Square) Sudoku: rows and
# columns 2-4 and 6-8, exactly as `NRCSudoku.createGroups` builds them.
NRC_EXTRA = (
    ". . . . . . . . .",
    ". a a a . b b b .",
    ". a a a . b b b .",
    ". a a a . b b b .",
    ". . . . . . . . .",
    ". c c c . d d d .",
    ". c c c . d d d .",
    ". c c c . d d d .",
    ". . . . . . . . .",
)

JAVA_CTOR = re.compile(r"new\s+(StandardSudoku|NRCSudoku)\s*\(\s*\"([^\"]*)\"\s*,(.*?)\)\s*;", re.S)
PY_PUZZLE = re.compile(r"(\w+)\s*=\s*\\\s*(NRCSudoku|Sudoku)\(\((.*?)\)\s*\)", re.S)
DIGITS = set("123456789")
# Puzzles that are not a puzzle: the all-blank placeholders and the
# deliberately unsolvable one the Java tests keep for their error paths.
SKIPPED_NAMES = {"unsolvable"}


def _rows(joined: str) -> list[str] | None:
    """Nine 9-character rows from a concatenated puzzle string, or None."""
    if len(joined) != 81:
        return None
    cleaned = joined.replace(" ", ".")
    if not set(cleaned) <= DIGITS | {"."} or cleaned == "." * 81:
        return None
    return [cleaned[start : start + 9] for start in range(0, 81, 9)]


def extract_java(text: str) -> list[tuple[str, bool, list[str]]]:
    """(name, is_nrc, rows) for every Standard/NRC Sudoku in `PuzzleDB.java`."""
    found = []
    for kind, name, args in JAVA_CTOR.findall(text):
        if name.casefold() in SKIPPED_NAMES:
            continue
        rows = _rows("".join(re.findall(r'"([^"]*)"', args)))
        if rows is not None:
            found.append((name, kind == "NRCSudoku", rows))
    return found


def extract_python(text: str) -> list[tuple[str, bool, list[str]]]:
    """(name, is_nrc, rows) for every Sudoku in the Python `SudokuPuzzles.py`."""
    found = []
    for name, kind, inner in PY_PUZZLE.findall(text):
        rows = _rows("".join(re.findall(r'"([^"]*)"', inner)))
        if rows is not None:
            found.append((name, kind == "NRCSudoku", rows))
    return found


def puzzle_text(rows: list[str], nrc: bool) -> str:
    """A puzzle as `csp.sudoku.parse` reads it: a bare grid, or Givens + Extra."""
    if not nrc:
        return "\n".join(rows) + "\n"
    body = "\n".join(" ".join(row) for row in rows)
    return f"Givens:\n{body}\n\nExtra:\n" + "\n".join(NRC_EXTRA) + "\n"


def source() -> corpus.Source:
    """The Java project's source files, fetched with the rest of the corpora."""
    return corpus.Source(name="operdeck-sudoku", kind="grid-lines", files=JAVA_FILES)


def jobs(ladder: str, timeout: float) -> list[bench.Job]:
    """One job per Java-solver puzzle, with the brute force as the oracle."""
    paths = corpus.fetch(source())
    texts = {path.name: path.read_text() for path in paths}
    named = [*extract_java(texts["PuzzleDB.java"]), *extract_python(texts["SudokuPuzzles.py"])]
    out: list[bench.Job] = []
    for name, nrc, rows in named:
        out.append(
            bench.Job(
                index=len(out),
                origin=name,
                group="NRC" if nrc else "named",
                rating=None,
                kind="sudoku",
                text=puzzle_text(rows, nrc),
                answer=None,
                ladder=ladder,
                timeout=timeout,
            )
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ladder", choices=sorted(bench.LADDERS), default="full")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds per puzzle")
    parser.add_argument("--csv", type=Path, default=None, help="where the per-puzzle rows go")
    args = parser.parse_args()

    run = jobs(args.ladder, args.timeout)
    print(f"running {len(run)} Java-solver puzzles, ladder {args.ladder}", file=sys.stderr)
    outcomes = [bench.measure(job) for job in run]
    print(
        bench.report(
            outcomes,
            title="operdeck/sudoku (Java) corpus",
            ladder=args.ladder,
            timeout=args.timeout,
        )
    )
    path = args.csv or corpus.cache_dir("reports") / f"operdeck-java-{args.ladder}.csv"
    bench.write_csv(path, outcomes)
    print(f"\n{bench.wrote(path)}")


if __name__ == "__main__":
    main()
