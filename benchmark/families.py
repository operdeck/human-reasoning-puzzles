"""Benchmark the checked-in small/larger examples for each added family.

    uv run python benchmark/families.py --runs 3 --seed 42

Examples are fixed, unique, and checked into the repository. The seed shuffles
case order; timings include standalone parsing, CLI load/compile, deduction, and
independent brute-force validation so runs are reproducible and comparable.
"""

import argparse
import random
import statistics
import time
from collections.abc import Callable
from pathlib import Path

from csp import (
    akari,
    battleships,
    binairo,
    bruteforce,
    cli,
    kakurasu,
    logicgrid,
    minesweeper,
    queens,
    report,
    starbattle,
    sudoku,
    suguru,
    tents,
)
from csp.core import Solver
from csp.puzzlefile import detect

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"

PARSERS: dict[str, Callable[[str], object]] = {
    "sudoku": sudoku.parse,
    "queens": queens.parse,
    "suguru": suguru.parse,
    "logicgrid": logicgrid.parse,
    "starbattle": starbattle.parse,
    "binairo": binairo.parse,
    "tents": tents.parse,
    "minesweeper": minesweeper.parse,
    "akari": akari.parse,
    "kakurasu": kakurasu.parse,
    "battleships": battleships.parse,
}

CASES = (
    "queens_6_4x4.txt",
    "queens_4_8x8.txt",
    "sudoku_9_4x4_kropki_consecutive_thermometers.txt",
    "sudoku_7_9x9_kropki_consecutive_thermometers.txt",
    "sudoku_2_4x4_anti_knight.txt",
    "sudoku_3_9x9_anti_knight.txt",
    "sudoku_16_6x6_anti_king.txt",
    "sudoku_4_9x9_anti_king.txt",
    "suguru_1_4x4.txt",
    "suguru_2_8x8.txt",
    "starbattle_2_8x8.txt",
    "starbattle_4_10x10.txt",
    "starbattle_3_12x12.txt",
    "logicgrid_1_3x3.txt",
    "logicgrid_2_6x6.txt",
    "binairo_3_4x4.txt",
    "binairo_2_8x8.txt",
    "tango_2_4x4.txt",
    "tango_4_8x8.txt",
    "tents_3_4x4.txt",
    "tents_1_8x8.txt",
    "minesweeper_2_5x5.txt",
    "minesweeper_3_8x8.txt",
    "akari_1_6x6.txt",
    "akari_2_8x8.txt",
    "kakurasu_1_4x4.txt",
    "kakurasu_2_8x8.txt",
    "battleships_1_6x6_fleet.txt",
    "battleships_2_8x8_fleet.txt",
)


def measure(name: str) -> tuple[str, float, float, float, float]:
    text = next(EXAMPLES.rglob(name)).read_text()
    kind = detect(text)

    start = time.perf_counter()
    PARSERS[kind](text)
    parse_ms = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    puzzle = cli.load(text, kind)
    compile_ms = (time.perf_counter() - start) * 1000

    fired: list[str] = []
    start = time.perf_counter()
    result = Solver(puzzle.model).solve(on_step=lambda rule, steps: fired.append(rule))
    solve_ms = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    found = bruteforce.solutions(text, kind, limit=2)
    brute_ms = (time.perf_counter() - start) * 1000
    if len(found) != 1 or not result.solved or result.assignment != found[0]:
        raise ValueError(f"{name} failed uniqueness or engine agreement")
    return report.grade(fired), parse_ms, compile_ms, solve_ms, brute_ms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")

    cases = list(CASES)
    random.Random(args.seed).shuffle(cases)
    print(f"{len(cases)} family examples, {args.runs} runs, seed {args.seed}\n")
    print("| Example | Grade | Parse ms | Load/compile ms | Solve ms | Brute-force ms |")
    print("|---|---|---:|---:|---:|---:|")
    for name in cases:
        measured = [measure(name) for _ in range(args.runs)]
        grade_name = measured[0][0]
        medians = [statistics.median(run[index] for run in measured) for index in range(1, 5)]
        print(
            f"| `{name}` | `{grade_name}` | "
            + " | ".join(f"{value:.2f}" for value in medians)
            + " |"
        )


if __name__ == "__main__":
    main()
