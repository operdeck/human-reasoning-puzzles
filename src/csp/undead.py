"""Undead: monsters on a grid of mirrors, counted along sight lines.

Cells marked `/` or `\\` are mirrors; every other cell holds one monster: a ghost
(`G`), a vampire (`V`) or a zombie (`Z`). The total of each kind is given, and so
is the number of monsters seen from every border cell looking in along its row or
column, the line bending at each mirror. A zombie is always seen, a vampire only
when seen directly (before the line has met a mirror), a ghost only when seen
after it has.

    Family: undead
    Grid:
    . / . .
    \\ . . /
    ...
    Counts:
    3 4 2        # ghosts, vampires, zombies
    Top:
    1 . 2 3
    Bottom:
    ...
    Left:
    ...
    Right:
    ...

`.` in a clue line means no clue. The board may be rectangular.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

MONSTERS = ("G", "V", "Z")
NAMES = {"G": "ghost", "V": "vampire", "Z": "zombie"}
SIDES = ("Top", "Bottom", "Left", "Right")
BIGGEST = 8

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def seen(monster: str, reflected: bool) -> bool:
    """Whether a monster is visible: the one rule both solvers share.

    Zombies are always seen, vampires only directly and ghosts only through a mirror.
    """
    return monster == "Z" or (monster == "V" and not reflected) or (monster == "G" and reflected)


@dataclass(frozen=True)
class Sight:
    """One border clue: `count` monsters seen along `path`, as (cell, seen via a mirror) pairs."""

    side: str
    index: int
    count: int
    path: tuple[tuple[Cell, bool], ...]

    @property
    def label(self) -> str:
        return f"{self.count} monsters seen from the {self.side.lower()} at {self.index + 1}"


class Puzzle:
    def __init__(
        self,
        grid: list[list[str]],
        totals: dict[str, int],
        clues: dict[str, list[int]],
    ) -> None:
        self.grid = grid
        self.rows = len(grid)
        self.cols = len(grid[0])
        self.totals = totals
        self.clues = clues  # side -> clue per border cell, -1 for none

    @property
    def empty(self) -> list[Cell]:
        return [
            (r, c) for r in range(self.rows) for c in range(self.cols) if self.grid[r][c] == "."
        ]

    def trace(self, side: str, index: int) -> tuple[tuple[Cell, bool], ...]:
        """The cells a line of sight crosses, with whether a mirror has already bent it."""
        start = {
            "Top": ((0, index), (1, 0)),
            "Bottom": ((self.rows - 1, index), (-1, 0)),
            "Left": ((index, 0), (0, 1)),
            "Right": ((index, self.cols - 1), (0, -1)),
        }[side]
        (r, c), (dr, dc) = start
        reflected = False
        path: list[tuple[Cell, bool]] = []
        while 0 <= r < self.rows and 0 <= c < self.cols:
            mirror = self.grid[r][c]
            if mirror == "/":
                dr, dc = -dc, -dr
                reflected = True
            elif mirror == "\\":
                dr, dc = dc, dr
                reflected = True
            else:
                path.append(((r, c), reflected))
            r, c = r + dr, c + dc
        return tuple(path)

    @property
    def sights(self) -> list[Sight]:
        return [
            Sight(side, i, count, self.trace(side, i))
            for side in SIDES
            for i, count in enumerate(self.clues[side])
            if count >= 0
        ]


def parse(text: str) -> Puzzle:
    """Read an Undead file: Grid, Counts and the four border clue lines."""
    section = read_sections(text)
    for required in ("Family", "Grid", "Counts"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() != "undead":
        raise ValueError("Family must be 'undead'")
    rows = [line.split() for line in section["Grid"]]
    if not 2 <= len(rows) <= BIGGEST or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"Grid must be rectangular with 2 to {BIGGEST} rows")
    if not 2 <= len(rows[0]) <= BIGGEST:
        raise ValueError(f"Grid must have 2 to {BIGGEST} columns")
    if any(cell not in {".", "/", "\\"} for row in rows for cell in row):
        raise ValueError("Grid cells must be '.', '/' or '\\'")
    tokens = " ".join(section["Counts"]).split()
    if len(tokens) != 3 or not all(t.isdigit() for t in tokens):
        raise ValueError("Counts needs three numbers: ghosts vampires zombies")
    totals = dict(zip(MONSTERS, map(int, tokens), strict=True))
    empty = sum(cell == "." for row in rows for cell in row)
    if sum(totals.values()) != empty:
        raise ValueError(
            f"Counts add up to {sum(totals.values())} but there are {empty} empty cells"
        )
    clues: dict[str, list[int]] = {}
    for side in SIDES:
        length = len(rows[0]) if side in ("Top", "Bottom") else len(rows)
        entries = [t for line in section.get(side, []) for t in line.split()] or ["."] * length
        if len(entries) != length or any(t != "." and not t.isdigit() for t in entries):
            raise ValueError(f"{side}: expected {length} counts or '.'")
        clues[side] = [-1 if t == "." else int(t) for t in entries]
    return Puzzle(rows, totals, clues)


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """Three monsters per empty cell, a COUNT per kind, and one relation per sight line."""
    puzzle = parse(text)
    model = Model()
    for cell in puzzle.empty:
        name = cell_name(cell)
        model.constrain(
            f"{name} holds one monster",
            Kind.EXACTLY_ONE,
            [model.literal(name, monster) for monster in MONSTERS],
            defines=name,
            family="each empty cell holds one monster",
        )
    for monster in MONSTERS:
        model.constrain(
            f"{puzzle.totals[monster]} {NAMES[monster]}s in all",
            Kind.COUNT,
            [model.literal(cell_name(cell), monster) for cell in puzzle.empty],
            allowed_counts=(puzzle.totals[monster],),
            family="monster totals",
        )
    for sight in puzzle.sights:
        cells = list(dict.fromkeys(cell for cell, _ in sight.path))  # a line may cross itself
        index = {cell: i for i, cell in enumerate(cells)}
        steps = [(index[cell], reflected) for cell, reflected in sight.path]
        model.relate(
            sight.label,
            [cell_name(cell) for cell in cells],
            lambda *values, steps=steps, count=sight.count: (
                sum(seen(values[i], reflected) for i, reflected in steps) == count
            ),
        )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The grid with mirrors, a letter per settled monster and the border counts."""
    changed = {step.var for step in steps if step.asserted}

    def clue(values: list[int]) -> str:
        return " ".join("." if v < 0 else str(v) for v in values)

    totals = ", ".join(f"{puzzle.totals[m]} {NAMES[m]}s" for m in MONSTERS)
    out = [f"\n{BOLD}{title}{RESET}", totals, f"  {clue(puzzle.clues['Top'])}"]
    for r in range(puzzle.rows):
        marks = []
        for c in range(puzzle.cols):
            if puzzle.grid[r][c] != ".":
                marks.append(puzzle.grid[r][c])
                continue
            name = cell_name((r, c))
            chosen = model.chosen(name)
            letter = chosen if chosen is not None else "?"
            marks.append(f"{NEW if name in changed else ''}{letter}{RESET}")
        left, right = puzzle.clues["Left"][r], puzzle.clues["Right"][r]
        out.append(f"{'.' if left < 0 else left} {' '.join(marks)} {'.' if right < 0 else right}")
    out.append(f"  {clue(puzzle.clues['Bottom'])}")
    return "\n".join(out)
