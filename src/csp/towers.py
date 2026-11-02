"""Towers (Skyscrapers) expressed as exact cover plus one relation per edge clue.

An N x N grid holds the heights 1..N once in every row and column. A clue on
the edge of a row or column says how many towers can be seen looking along it:
a tower hides every shorter tower behind it.

    Family: towers
    Size: 4
    Top: 2 . 1 3
    Bottom: . 2 . .
    Left: . 3 . 1
    Right: 2 . . .
    Givens:
    . . . .
    . 4 . .
    ...

`.` (or 0) means no clue. Literals are "cell holds height", as in Futoshiki;
cells, rows and columns are EXACTLY_ONE constraints and every clue is a relation
over the cells of its line, listed in the order the viewer sees them.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

SIZES = range(3, 8)
SIDES = ("Top", "Bottom", "Left", "Right")

BOLD = "\033[1m"
NEW = "\033[38;5;21m"  # blue: changed by the step just shown
FADED = "\033[38;5;245m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def visible(heights: Sequence[int]) -> int:
    """How many towers are seen from the start of `heights`: those taller than all before."""
    seen, tallest = 0, 0
    for height in heights:
        if height > tallest:
            seen, tallest = seen + 1, height
    return seen


@dataclass(frozen=True)
class Clue:
    """`count` towers are visible along `cells`, read in the viewer's order."""

    side: str
    index: int
    count: int
    cells: tuple[Cell, ...]

    @property
    def label(self) -> str:
        line = "column" if self.side in ("Top", "Bottom") else "row"
        return (
            f"{self.count} towers visible from the {self.side.lower()} of {line} {self.index + 1}"
        )


@dataclass(frozen=True)
class Puzzle:
    size: int
    clues: dict[str, list[int]]  # side -> clue per line, 0 for none
    grid: list[list[int]]  # 0 for an open cell

    @property
    def lines(self) -> list[Clue]:
        """Every stated clue with the cells it looks along."""
        n = self.size
        out = []
        for side in SIDES:
            for index, count in enumerate(self.clues[side]):
                if not count:
                    continue
                if side == "Top":
                    cells = tuple((r, index) for r in range(n))
                elif side == "Bottom":
                    cells = tuple((r, index) for r in reversed(range(n)))
                elif side == "Left":
                    cells = tuple((index, c) for c in range(n))
                else:
                    cells = tuple((index, c) for c in reversed(range(n)))
                out.append(Clue(side, index, count, cells))
        return out


def parse(text: str) -> Puzzle:
    """Read a Towers file: Size, the four edges, and optional Givens."""
    section = read_sections(text)
    for required in ("Family", "Size"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() not in {
        "towers",
        "skyscrapers",
    }:
        raise ValueError("Family must be 'towers'")
    try:
        n = int(section["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be an integer") from exc
    if n not in SIZES:
        raise ValueError(
            f"Towers boards are {SIZES.start}x{SIZES.start} to {SIZES[-1]}x{SIZES[-1]}"
        )
    clues: dict[str, list[int]] = {}
    for side in SIDES:
        tokens = [t for line in section.get(side, []) for t in line.split()]
        if not tokens:
            tokens = ["."] * n
        if len(tokens) != n:
            raise ValueError(f"{side}: expected {n} clues, got {len(tokens)}")
        values = []
        for token in tokens:
            if token == ".":
                values.append(0)
            elif token.isdigit() and 1 <= int(token) <= n:
                values.append(int(token))
            else:
                raise ValueError(f"{side} holds {token!r}; expected 1-{n} or '.'")
        clues[side] = values
    grid = _givens(section.get("Givens", []), n)
    if not any(value for side in SIDES for value in clues[side]):
        raise ValueError("Towers needs at least one edge clue")
    return Puzzle(n, clues, grid)


def _givens(lines: list[str], n: int) -> list[list[int]]:
    if not lines:
        return [[0] * n for _ in range(n)]
    rows = [line.split() for line in lines]
    if len(rows) != n or any(len(row) != n for row in rows):
        raise ValueError(f"Givens is not {n}x{n}")
    grid = []
    for row in rows:
        if bad := [t for t in row if t != "." and not (t.isdigit() and 1 <= int(t) <= n)]:
            raise ValueError(f"Givens holds {bad[0]!r}; expected 1-{n} or '.'")
        grid.append([0 if t == "." else int(t) for t in row])
    return grid


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """The model for a Towers puzzle, with its givens already assigned."""
    puzzle = parse(text)
    n = puzzle.size
    heights = range(1, n + 1)
    model = Model()
    for r in range(n):
        for c in range(n):
            name = cell_name((r, c))
            model.constrain(
                f"{name} holds one height",
                Kind.EXACTLY_ONE,
                [model.literal(name, h) for h in heights],
                defines=name,
                family="each cell holds one height",
            )
    for h in heights:
        for i in range(n):
            model.constrain(
                f"height {h} once in row {i + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name((i, c)), h) for c in range(n)],
                family="each height once per row",
            )
            model.constrain(
                f"height {h} once in column {i + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name((r, i)), h) for r in range(n)],
                family="each height once per column",
            )
    for r, row in enumerate(puzzle.grid):
        for c, h in enumerate(row):
            if h:
                model.assign(model.literal(cell_name((r, c)), h), "given", "given")
    for clue in puzzle.lines:
        model.relate(
            clue.label,
            [cell_name(cell) for cell in clue.cells],
            lambda *values, count=clue.count: visible(values) == count,
        )
    return model, puzzle


# --- rendering ------------------------------------------------------------


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The grid with its edge clues and pencil marks; `steps` are highlighted."""
    n = puzzle.size
    placed = {s.var for s in steps if s.asserted}
    narrowed = {s.var for s in steps if not s.asserted}
    width = n if n <= 6 else 1

    def edge(values: Sequence[int]) -> str:
        return " ".join((str(v) if v else "·").center(width) for v in values)

    out = [f"\n{BOLD}{title}{RESET}", f"  {edge(puzzle.clues['Top'])}"]
    for r in range(n):
        cells = " ".join(
            _cell_text(model, cell_name((r, c)), width, placed, narrowed) for c in range(n)
        )
        left, right = puzzle.clues["Left"][r], puzzle.clues["Right"][r]
        out.append(f"{left or chr(0xB7)} {cells} {right or chr(0xB7)}")
    out.append(f"  {edge(puzzle.clues['Bottom'])}")
    return "\n".join(out)


def _cell_text(model: Model, name: str, width: int, placed: set[str], narrowed: set[str]) -> str:
    value = model.chosen(name)
    if value is not None:
        tint = NEW if name in placed else ""
        return f"{BOLD}{tint}{str(value).center(width)}{RESET}"
    if width == 1:
        return ".".center(width)
    marks = "".join(str(model.value_of(lit)) for lit in model.options(name))
    tint = NEW if name in narrowed else FADED
    return f"{tint}{marks.ljust(width)}{RESET}"
