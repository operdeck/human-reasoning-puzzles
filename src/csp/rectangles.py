"""Rectangles (Shikaku) as exact cover over candidate rectangles.

Some cells carry a number. Divide the grid into rectangles so that each holds
exactly one number, equal to its area.

    Family: rectangles
    Clues:
    . . 4 . .
    3 . . . 2
    ...

There is one variable per numbered cell, named after that cell. Its values are
the rectangles of the right area that contain it and no other number. The domain
constraint picks one; every grid cell is covered exactly once, an EXACTLY_ONE
over every (clue, rectangle) literal that includes the cell.
"""

from collections.abc import Mapping, Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]
type Rect = tuple[int, int, int, int]  # top, left, bottom, right (inclusive)

BIGGEST = 16

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def rect_name(rect: Rect) -> str:
    top, left, bottom, right = rect
    return f"{cell_name((top, left))}:{cell_name((bottom, right))}"


def parse_rect(name: str) -> Rect:
    first, second = name.split(":")
    (top, left), (bottom, right) = parse_cell(first), parse_cell(second)
    return top, left, bottom, right


def parse_cell(name: str) -> Cell:
    row, col = name[1:].split("c")
    return int(row) - 1, int(col) - 1


def cells_of(rect: Rect) -> list[Cell]:
    top, left, bottom, right = rect
    return [(r, c) for r in range(top, bottom + 1) for c in range(left, right + 1)]


class Puzzle:
    def __init__(self, clues: list[list[int]]) -> None:
        self.clues = clues  # 0 where there is no number
        self.rows = len(clues)
        self.cols = len(clues[0])

    @property
    def numbered(self) -> list[Cell]:
        return [(r, c) for r in range(self.rows) for c in range(self.cols) if self.clues[r][c] > 0]

    def candidates(self, cell: Cell) -> list[Rect]:
        """Every rectangle of the cell's area that contains it and no other number."""
        area = self.clues[cell[0]][cell[1]]
        found: list[Rect] = []
        for height in range(1, area + 1):
            if area % height:
                continue
            width = area // height
            for top in range(cell[0] - height + 1, cell[0] + 1):
                for left in range(cell[1] - width + 1, cell[1] + 1):
                    rect = (top, left, top + height - 1, left + width - 1)
                    if top < 0 or left < 0 or rect[2] >= self.rows or rect[3] >= self.cols:
                        continue
                    if all(self.clues[r][c] == 0 or (r, c) == cell for r, c in cells_of(rect)):
                        found.append(rect)
        return found


def parse(text: str) -> Puzzle:
    """Read a Rectangles file: `Clues:` is a grid of numbers and `.`."""
    section = read_sections(text)
    for required in ("Family", "Clues"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() != "rectangles":
        raise ValueError("Family must be 'rectangles'")
    rows = [line.split() for line in section["Clues"]]
    if not 2 <= len(rows) <= BIGGEST or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"Clues must be a rectangular grid of 2 to {BIGGEST} rows")
    if not 2 <= len(rows[0]) <= BIGGEST:
        raise ValueError(f"Clues must have 2 to {BIGGEST} columns")
    clues = []
    for row in rows:
        parsed = []
        for token in row:
            if token == ".":
                parsed.append(0)
            elif token.isdigit() and int(token) >= 1:
                parsed.append(int(token))
            else:
                raise ValueError(f"bad Rectangles clue {token!r}, expected '.' or a number")
        clues.append(parsed)
    puzzle = Puzzle(clues)
    if sum(map(sum, clues)) != puzzle.rows * puzzle.cols:
        raise ValueError("the numbers must add up to the number of cells")
    return puzzle


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """One variable per number, whose values are its candidate rectangles."""
    puzzle = parse(text)
    model = Model()
    covering: dict[Cell, list[tuple[str, str]]] = {
        (r, c): [] for r in range(puzzle.rows) for c in range(puzzle.cols)
    }
    for cell in puzzle.numbered:
        name = cell_name(cell)
        options = puzzle.candidates(cell)
        if not options:
            raise ValueError(f"no rectangle fits the number at {name}")
        model.constrain(
            f"the number at {name} has one rectangle",
            Kind.EXACTLY_ONE,
            [model.literal(name, rect_name(rect)) for rect in options],
            defines=name,
            family="each number owns one rectangle",
        )
        for rect in options:
            for covered in cells_of(rect):
                covering[covered].append((name, rect_name(rect)))
    for cell, options_here in covering.items():
        model.constrain(
            f"{cell_name(cell)} is in one rectangle",
            Kind.EXACTLY_ONE,
            [model.literal(name, value) for name, value in options_here],
            family="each cell is in one rectangle",
        )
    return model, puzzle


def cell_assignment(solution: Mapping[str, str]) -> dict[str, str]:
    """For every cell, the number (named by its own cell) whose rectangle covers it."""
    return {
        cell_name(cell): owner
        for owner, value in solution.items()
        for cell in cells_of(parse_rect(value))
    }


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The numbers; a cell shows a letter once the rectangle covering it is settled."""
    changed = {step.var for step in steps if step.asserted}
    letters = {cell: chr(ord("a") + i % 26) for i, cell in enumerate(puzzle.numbered)}
    owner: dict[Cell, Cell] = {}
    for cell in puzzle.numbered:
        chosen = model.chosen(cell_name(cell))
        if chosen is not None:
            for covered in cells_of(parse_rect(chosen)):
                owner[covered] = cell
    out = [f"\n{BOLD}{title}{RESET}"]
    for r in range(puzzle.rows):
        marks = []
        for c in range(puzzle.cols):
            clue = puzzle.clues[r][c]
            text = str(clue) if clue else "."
            if (r, c) in owner:
                text = f"{text}{letters[owner[r, c]]}"
            fresh = (r, c) in owner and cell_name(owner[r, c]) in changed
            marks.append(f"{NEW if fresh else ''}{text:>3}{RESET}")
        out.append(" ".join(marks))
    return "\n".join(out)
