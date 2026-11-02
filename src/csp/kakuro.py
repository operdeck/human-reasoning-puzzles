"""Kakuro compiled to digit cells and one sum relation per run.

White cells hold the digits 1 to 9. A black clue cell carries the sum of the run of white
cells below it (down) and the run to its right (across); a run holds distinct digits that
add up to its sum.

    Family: kakuro
    Grid:
    X   X    16\\   7\\
    \\3  .    .     .
    \\10 .    .     .
    ...

A cell is `.` (white), `X` (black without clues) or `down\\across` with either number left
out: `16\\` (a down clue only), `\\3` (across only) or `4\\6` (both). Runs are 2 to 5 cells
long, because a run's relation enumerates every digit combination of its cells.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

LONGEST_RUN = 5
BIGGEST = 10

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def run_holds(values: Sequence[int], total: int) -> bool:
    """Whether a run's digits are distinct and add up: the one rule both solvers share."""
    return len(set(values)) == len(values) and sum(values) == total


@dataclass(frozen=True)
class Run:
    """The white cells a clue covers, in reading order, and the sum they must make."""

    clue: Cell
    direction: str  # "down" or "across"
    cells: tuple[Cell, ...]
    total: int

    @property
    def label(self) -> str:
        return f"{self.direction} run from {cell_name(self.clue)} sums to {self.total}"


class Puzzle:
    def __init__(self, grid: list[list[str]], clues: dict[Cell, tuple[int, int]]) -> None:
        self.grid = grid  # "." white, "X" black, "C" clue cell
        self.clues = clues  # clue cell -> (down sum, across sum), 0 for none
        self.rows = len(grid)
        self.cols = len(grid[0])
        self.whites = [
            (r, c) for r in range(self.rows) for c in range(self.cols) if grid[r][c] == "."
        ]

    @property
    def runs(self) -> list[Run]:
        out: list[Run] = []
        for (r, c), (down, across) in sorted(self.clues.items()):
            if across:
                cells = _walk(self, r, c, 0, 1)
                out.append(Run((r, c), "across", cells, across))
            if down:
                cells = _walk(self, r, c, 1, 0)
                out.append(Run((r, c), "down", cells, down))
        return out


def _walk(puzzle: Puzzle, r: int, c: int, dr: int, dc: int) -> tuple[Cell, ...]:
    cells = []
    r, c = r + dr, c + dc
    while 0 <= r < puzzle.rows and 0 <= c < puzzle.cols and puzzle.grid[r][c] == ".":
        cells.append((r, c))
        r, c = r + dr, c + dc
    return tuple(cells)


def parse(text: str) -> Puzzle:
    """Read a Kakuro file: a `Grid:` of `.`, `X` and `down\\across` clue cells."""
    section = read_sections(text)
    for required in ("Family", "Grid"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() != "kakuro":
        raise ValueError("Family must be 'kakuro'")
    rows = [line.split() for line in section["Grid"]]
    if not 3 <= len(rows) <= BIGGEST or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"Grid must be rectangular with 3 to {BIGGEST} rows")
    if not 3 <= len(rows[0]) <= BIGGEST:
        raise ValueError(f"Grid must have 3 to {BIGGEST} columns")
    grid: list[list[str]] = []
    clues: dict[Cell, tuple[int, int]] = {}
    for r, row in enumerate(rows):
        marks = []
        for c, token in enumerate(row):
            if token in (".", "X"):
                marks.append(token)
            elif "\\" in token:
                down, _, across = token.partition("\\")
                if (down and not down.isdigit()) or (across and not across.isdigit()):
                    raise ValueError(f"bad clue cell {token!r}, expected like 16\\7, 16\\ or \\7")
                clues[r, c] = (int(down or 0), int(across or 0))
                marks.append("C")
            else:
                raise ValueError(f"bad grid cell {token!r}, expected '.', 'X' or down\\across")
        grid.append(marks)
    puzzle = Puzzle(grid, clues)
    covered: set[Cell] = set()
    for run in puzzle.runs:
        if not 2 <= len(run.cells) <= LONGEST_RUN:
            raise ValueError(
                f"{run.label}: runs are 2 to {LONGEST_RUN} cells, not {len(run.cells)}"
            )
        low, high = sum(range(1, len(run.cells) + 1)), sum(range(10 - len(run.cells), 10))
        if not low <= run.total <= high:
            raise ValueError(f"{run.label}: {len(run.cells)} cells sum to {low} to {high}")
        covered.update(run.cells)
    if uncovered := [cell for cell in puzzle.whites if cell not in covered]:
        raise ValueError(f"white cell {cell_name(uncovered[0])} is in no run")
    return puzzle


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """A digit per white cell and one distinct-sum relation per run."""

    puzzle = parse(text)
    model = Model()
    for cell in puzzle.whites:
        name = cell_name(cell)
        model.constrain(
            f"{name} holds one digit",
            Kind.EXACTLY_ONE,
            [model.literal(name, d) for d in range(1, 10)],
            defines=name,
            family="each white cell holds one digit",
        )
    for run in puzzle.runs:
        model.relate(
            run.label,
            [cell_name(cell) for cell in run.cells],
            lambda *values, total=run.total: run_holds(values, total),
        )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Clue cells as `down\\across`, white cells as their digit or `.`."""
    changed = {step.var for step in steps if step.asserted}
    out = [f"\n{BOLD}{title}{RESET}"]
    for r in range(puzzle.rows):
        marks = []
        for c in range(puzzle.cols):
            kind = puzzle.grid[r][c]
            if kind == "X":
                text = "###"
            elif kind == "C":
                down, across = puzzle.clues[r, c]
                text = f"{down or ''}\\{across or ''}"
            else:
                value = model.chosen(cell_name((r, c)))
                text = str(value) if value is not None else "."
            fresh = kind == "." and cell_name((r, c)) in changed
            marks.append(f"{NEW if fresh else ''}{text:^6}{RESET}")
        out.append("".join(marks))
    return "\n".join(out)
