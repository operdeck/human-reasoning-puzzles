"""Hidato and Numbrix: a path of consecutive numbers, as exact cover plus adjacency relations.

Fill the open cells with 1..K, K being their number of cells, so that every number is next
to the following one. Hidato lets neighbours touch at corners as well as along sides;
Numbrix only along sides.

    Family: hidato          # or: numbrix
    Grid:
    1 . . 4
    . X . .
    . . 10 .
    ...

`.` is an open cell, `X` a blocked one and a number is a given. The compiler's variables
are the numbers: "number k sits in this cell", so the adjacency of k and k + 1 is a relation
over two variables, and every cell holds exactly one number.
"""

from collections.abc import Mapping, Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

BIGGEST = 8
FAMILIES = ("hidato", "numbrix")

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def number_name(number: int) -> str:
    return f"n{number}"


def parse_cell(name: str) -> Cell:
    row, col = name[1:].split("c")
    return int(row) - 1, int(col) - 1


def touching(first: Cell, second: Cell, diagonal: bool) -> bool:
    """Whether two cells are neighbours: the one rule both solvers share."""
    dr, dc = abs(first[0] - second[0]), abs(first[1] - second[1])
    return max(dr, dc) == 1 and (diagonal or dr + dc == 1)


class Puzzle:
    def __init__(self, grid: list[list[int]], diagonal: bool) -> None:
        self.grid = grid  # 0 open, -1 blocked, k > 0 given
        self.diagonal = diagonal
        self.rows = len(grid)
        self.cols = len(grid[0])
        self.cells = [(r, c) for r in range(self.rows) for c in range(self.cols) if grid[r][c] >= 0]
        self.count = len(self.cells)  # K: the numbers run 1..K

    @property
    def givens(self) -> dict[int, Cell]:
        return {
            self.grid[r][c]: (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if self.grid[r][c] > 0
        }


def parse(text: str) -> Puzzle:
    """Read a Hidato or Numbrix file: the family name picks the adjacency."""
    section = read_sections(text)
    for required in ("Family", "Grid"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    family = section["Family"][0].casefold() if len(section["Family"]) == 1 else ""
    if family not in FAMILIES:
        raise ValueError("Family must be 'hidato' or 'numbrix'")
    rows = [line.split() for line in section["Grid"]]
    if not 2 <= len(rows) <= BIGGEST or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"Grid must be rectangular with 2 to {BIGGEST} rows")
    if not 2 <= len(rows[0]) <= BIGGEST:
        raise ValueError(f"Grid must have 2 to {BIGGEST} columns")
    grid: list[list[int]] = []
    for row in rows:
        parsed = []
        for token in row:
            if token == ".":
                parsed.append(0)
            elif token == "X":
                parsed.append(-1)
            elif token.isdigit() and int(token) >= 1:
                parsed.append(int(token))
            else:
                raise ValueError(f"bad grid cell {token!r}, expected '.', 'X' or a number")
        grid.append(parsed)
    puzzle = Puzzle(grid, diagonal=family == "hidato")
    seen: set[int] = set()
    for numbers in grid:
        for value in numbers:
            if value > puzzle.count:
                raise ValueError(f"{value} is more than the {puzzle.count} open cells")
            if value > 0 and value in seen:
                raise ValueError(f"{value} is given twice")
            seen.add(value)
    if puzzle.count < 4:
        raise ValueError("a board needs at least four open cells")
    return puzzle


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """One variable per number whose values are cells; consecutive numbers must touch."""
    puzzle = parse(text)
    model = Model()
    numbers = range(1, puzzle.count + 1)
    for k in numbers:
        name = number_name(k)
        model.constrain(
            f"number {k} sits in one cell",
            Kind.EXACTLY_ONE,
            [model.literal(name, cell_name(cell)) for cell in puzzle.cells],
            defines=name,
            family="each number sits in one cell",
        )
    for cell in puzzle.cells:
        model.constrain(
            f"{cell_name(cell)} holds one number",
            Kind.EXACTLY_ONE,
            [model.literal(number_name(k), cell_name(cell)) for k in numbers],
            family="each cell holds one number",
        )
    for k in range(1, puzzle.count):
        model.relate(
            f"{k} and {k + 1} touch",
            [number_name(k), number_name(k + 1)],
            lambda a, b: touching(parse_cell(a), parse_cell(b), puzzle.diagonal),
        )
    for k, cell in puzzle.givens.items():
        model.assign(model.literal(number_name(k), cell_name(cell)), "given", "given")
    return model, puzzle


def cell_assignment(solution: Mapping[str, str]) -> dict[str, int]:
    """The number in each cell, from a solution of "number k -> cell"."""
    return {cell: int(var[1:]) for var, cell in solution.items()}


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The board with the numbers settled so far, `.` for open cells and `X` for blocked ones."""
    changed = {number_name(k) for k in range(1, puzzle.count + 1)} & {
        step.var for step in steps if step.asserted
    }
    where = {
        parse_cell(cell): int(var[1:])
        for var in (number_name(k) for k in range(1, puzzle.count + 1))
        if (cell := model.chosen(var)) is not None
    }
    width = len(str(puzzle.count))
    out = [f"\n{BOLD}{title}{RESET}"]
    for r in range(puzzle.rows):
        marks = []
        for c in range(puzzle.cols):
            if puzzle.grid[r][c] < 0:
                text = "X"
            elif (r, c) in where:
                text = str(where[r, c])
            else:
                text = "."
            fresh = (r, c) in where and number_name(where[r, c]) in changed
            marks.append(f"{NEW if fresh else ''}{text:>{width}}{RESET}")
        out.append(" ".join(marks))
    return "\n".join(out)
