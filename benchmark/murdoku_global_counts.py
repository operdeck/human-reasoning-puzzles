"""Benchmark Murdoku global-count parsing, compilation, and propagation.

    uv run python benchmark/murdoku_global_counts.py [--runs 3]

The generated boards use four logical areas and exercise object, area/tag, row,
column, role, attribute, empty-area, and empty-cell counts. Propagation is
measured with `single`/`count` and then `single`/`count`/`chains`, not puzzle
search.
"""

import argparse
import statistics
import time

from csp.core import DEFAULT_RULES, Solver
from csp.murdoku import compile_puzzle
from csp.puzzlefile import load_board

COUNT_RULES = tuple(rule for rule in DEFAULT_RULES if rule.name in ("single", "count"))
COUNT_CHAIN_RULES = tuple(
    rule for rule in DEFAULT_RULES if rule.name in ("single", "count", "chains")
)


def puzzle_text(size: int) -> str:
    half = size // 2
    region_names = {
        "a": "northwest",
        "b": "northeast",
        "c": "southwest",
        "d": "southeast",
    }
    rows = []
    for row in range(size):
        north_south = "a" if row < half else "c"
        east_west = "b" if row < half else "d"
        rows.append(" ".join(north_south if column < half else east_west for column in range(size)))

    people = [f"P{index}" for index in range(size // 2)]
    glasses = people[::2]
    return "\n".join(
        [
            f"Size: {size}",
            "Regions:",
            *(f"{region}: {name}" for region, name in region_names.items()),
            "Grid:",
            *rows,
            "AreaTags:",
            "north: northwest northeast",
            "Objects:",
            "bed: standable r1c1 r1c2",
            "Marks:",
            "focus: r1c1 r1c2 r2c1 r2c2",
            "Attributes:",
            f"glasses: {' '.join(glasses)}",
            "Roles:",
            "guide: any",
            "People:",
            *people,
            "Clues:",
            "count people on object:bed <= 2",
            "count people in tag:north >= 1",
            f"count people in rows:1-{half} >= 2",
            f"count people in columns:1-{half} >= 2",
            f"count people with role:guide 1..{len(people)}",
            f"count people with attribute:glasses = {len(glasses)}",
            "count empty areas all >= 1",
            "count empty areas in tag:north <= 2",
            "count empty cells in mark:focus 1..4",
            "",
        ]
    )


def measure(size: int, runs: int) -> tuple[float, float, float, float, int, int]:
    parsing: list[float] = []
    compiling: list[float] = []
    count_only: list[float] = []
    count_chains: list[float] = []
    constraints = 0
    literals = 0
    text = puzzle_text(size)
    for _ in range(runs):
        start = time.perf_counter()
        board, clues = load_board(text)
        parsing.append((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        model = compile_puzzle(board, clues)
        compiling.append((time.perf_counter() - start) * 1000)
        constraints = len(model.constraints)
        literals = model.num_literals

        start = time.perf_counter()
        Solver(model.clone(), COUNT_RULES).solve()
        count_only.append((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        Solver(model.clone(), COUNT_CHAIN_RULES).solve()
        count_chains.append((time.perf_counter() - start) * 1000)

    return (
        statistics.median(parsing),
        statistics.median(compiling),
        statistics.median(count_only),
        statistics.median(count_chains),
        constraints,
        literals,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")

    print(f"Murdoku global counts; median of {args.runs} runs")
    print("| Size | Parse ms | Compile ms | Count ms | Count+chains ms | Constraints | Literals |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for size in (12, 16):
        parsing, compiling, count_only, count_chains, constraints, literals = measure(
            size, args.runs
        )
        print(
            f"| {size}x{size} | {parsing:.2f} | {compiling:.2f} | {count_only:.2f} | "
            f"{count_chains:.2f} | {constraints} | {literals} |"
        )


if __name__ == "__main__":
    main()
