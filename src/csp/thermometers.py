"""Thermometers compiled to Boolean cells, one relation per thermometer and line counts.

Every cell of the board belongs to one thermometer, a path of cells that starts at its
bulb. Mercury fills a thermometer from the bulb on, without gaps, so the filled cells of a
thermometer are a prefix of its path. The numbers around the board give how many cells
of each row and column are filled.

    Family: thermometers
    Size: 4
    Thermometers:
    r1c1 r2c1 r3c1
    r1c2 r1c3 r1c4
    ...
    Rows:
    2 1 3 2
    Columns:
    1 2 2 3
    Givens:          # optional: '.', '0' (empty) or '1' (filled)

The first cell of each thermometer line is its bulb. Boards are square.
"""

from collections.abc import Sequence
from itertools import pairwise

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

SIZES = range(3, 11)

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def is_mercury(values: Sequence[bool]) -> bool:
    """Whether `values`, bulb first, are a filled prefix: the rule both solvers share."""
    return all(first or not second for first, second in pairwise(values))


class Puzzle:
    def __init__(
        self,
        size: int,
        paths: list[tuple[Cell, ...]],
        rows: list[int],
        columns: list[int],
        givens: list[list[int]],
    ) -> None:
        self.size = size
        self.paths = paths
        self.rows = rows
        self.columns = columns
        self.givens = givens  # -1 unknown, 0 empty, 1 filled


def parse(text: str) -> Puzzle:
    """Read a Thermometers file: Size, Thermometers, Rows, Columns and optional Givens."""
    section = read_sections(text)
    for required in ("Family", "Size", "Thermometers", "Rows", "Columns"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() != "thermometers":
        raise ValueError("Family must be 'thermometers'")
    try:
        n = int(section["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be an integer") from exc
    if n not in SIZES:
        raise ValueError(
            f"Thermometers boards are {SIZES.start}x{SIZES.start} to {SIZES[-1]}x{SIZES[-1]}"
        )
    paths = [tuple(_cell(token, n) for token in line.split()) for line in section["Thermometers"]]
    seen: set[Cell] = set()
    for path in paths:
        if len(path) < 2:
            raise ValueError("a thermometer needs at least two cells")
        if any(abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1 for a, b in pairwise(path)):
            raise ValueError(f"thermometer {' '.join(map(cell_name, path))} has a gap")
        if seen & set(path) or len(set(path)) != len(path):
            raise ValueError("thermometers may not share cells")
        seen |= set(path)
    if len(seen) != n * n:
        raise ValueError(f"thermometers cover {len(seen)} cells but the board has {n * n}")
    rows = _counts(section["Rows"], n, "Rows")
    columns = _counts(section["Columns"], n, "Columns")
    if sum(rows) != sum(columns):
        raise ValueError("Rows and Columns count a different number of filled cells")
    return Puzzle(n, paths, rows, columns, _givens(section.get("Givens", []), n))


def _cell(token: str, n: int) -> Cell:
    body = token.lower()
    if not (body.startswith("r") and "c" in body):
        raise ValueError(f"bad cell {token!r}, expected like r2c3")
    try:
        row, col = body[1:].split("c")
        cell = int(row) - 1, int(col) - 1
    except ValueError as exc:
        raise ValueError(f"bad cell {token!r}, expected like r2c3") from exc
    if not (0 <= cell[0] < n and 0 <= cell[1] < n):
        raise ValueError(f"cell {token!r} is off the board")
    return cell


def _counts(lines: list[str], n: int, name: str) -> list[int]:
    tokens = [t for line in lines for t in line.split()]
    if len(tokens) != n or any(not t.isdigit() or int(t) > n for t in tokens):
        raise ValueError(f"{name}: expected {n} counts from 0 to {n}")
    return [int(t) for t in tokens]


def _givens(lines: list[str], n: int) -> list[list[int]]:
    if not lines:
        return [[-1] * n for _ in range(n)]
    rows = [line.split() for line in lines]
    if len(rows) != n or any(len(row) != n for row in rows):
        raise ValueError(f"Givens is not {n}x{n}")
    if any(t not in {".", "0", "1"} for row in rows for t in row):
        raise ValueError("Givens cells must be '.', '0' or '1'")
    return [[-1 if t == "." else int(t) for t in row] for row in rows]


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """Boolean cells, a mercury relation per thermometer and a COUNT per row and column."""
    puzzle = parse(text)
    n = puzzle.size
    model = Model()
    for r in range(n):
        for c in range(n):
            name = cell_name((r, c))
            model.constrain(
                f"{name} is filled or empty",
                Kind.EXACTLY_ONE,
                [model.literal(name, True), model.literal(name, False)],
                defines=name,
                family="each cell is filled or empty",
            )
    for path in puzzle.paths:
        model.relate(
            f"mercury rises from {cell_name(path[0])}",
            [cell_name(cell) for cell in path],
            lambda *values: is_mercury(values),
        )
    for i, count in enumerate(puzzle.rows):
        model.constrain(
            f"{count} filled in row {i + 1}",
            Kind.COUNT,
            [model.literal(cell_name((i, c)), True) for c in range(n)],
            allowed_counts=(count,),
            family="filled cells per row",
        )
    for i, count in enumerate(puzzle.columns):
        model.constrain(
            f"{count} filled in column {i + 1}",
            Kind.COUNT,
            [model.literal(cell_name((r, i)), True) for r in range(n)],
            allowed_counts=(count,),
            family="filled cells per column",
        )
    for r in range(n):
        for c in range(n):
            if puzzle.givens[r][c] >= 0:
                model.assign(
                    model.literal(cell_name((r, c)), bool(puzzle.givens[r][c])), "given", "given"
                )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Rows as `#` (mercury), `.` (empty) or `?`, bulbs in brackets, counts around the board."""
    changed = {step.var for step in steps if step.asserted}
    bulbs = {path[0] for path in puzzle.paths}
    out = [f"\n{BOLD}{title}{RESET}", "    " + " ".join(f"{v:>2}" for v in puzzle.columns)]
    for r in range(puzzle.size):
        marks = []
        for c in range(puzzle.size):
            name = cell_name((r, c))
            chosen = model.chosen(name)
            mark = "#" if chosen is True else "." if chosen is False else "?"
            mark = f"({mark})" if (r, c) in bulbs else f" {mark} "
            marks.append(f"{NEW if name in changed else ''}{mark}{RESET}")
        out.append(f"{puzzle.rows[r]:>2} " + "".join(marks))
    return "\n".join(out)
