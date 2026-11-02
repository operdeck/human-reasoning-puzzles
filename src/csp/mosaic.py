"""Mosaic compiled to Boolean cells and 3x3 window counts.

Some cells carry a number: how many of the cells in the 3x3 window around it
(the cell itself included) are black. Colour every cell black or white.

    Family: mosaic
    Size: 5
    Clues:
    . 3 . . 2
    ...

This is the Minesweeper construction with the clue cell inside its own count,
and the clue cell free to be black or white.
"""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

SIZES = range(3, 16)

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


class Puzzle:
    def __init__(self, clues: list[list[int | None]]) -> None:
        self.clues = clues
        self.size = len(clues)

    def window(self, cell: Cell) -> tuple[Cell, ...]:
        """The cell and its up to eight neighbours, which one clue counts."""
        row, col = cell
        return tuple(
            (row + dr, col + dc)
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if 0 <= row + dr < self.size and 0 <= col + dc < self.size
        )

    @property
    def numbered(self) -> list[Cell]:
        return [
            (r, c)
            for r in range(self.size)
            for c in range(self.size)
            if self.clues[r][c] is not None
        ]


def parse(text: str) -> Puzzle:
    """Read a Mosaic file: a `Clues:` grid of digits 0-9 and `.`."""
    section = read_sections(text)
    for required in ("Family", "Size", "Clues"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() != "mosaic":
        raise ValueError("Family must be 'mosaic'")
    try:
        n = int(section["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be an integer") from exc
    if n not in SIZES:
        raise ValueError(
            f"Mosaic boards are {SIZES.start}x{SIZES.start} to {SIZES[-1]}x{SIZES[-1]}"
        )
    rows = [line.split() for line in section["Clues"]]
    if len(rows) != n or any(len(row) != n for row in rows):
        raise ValueError(f"Clues is not {n}x{n}")
    clues: list[list[int | None]] = []
    for row in rows:
        parsed: list[int | None] = []
        for token in row:
            if token == ".":
                parsed.append(None)
            elif len(token) == 1 and token.isdigit():
                parsed.append(int(token))
            else:
                raise ValueError(f"bad Mosaic clue {token!r}, expected '.' or 0..9")
        clues.append(parsed)
    puzzle = Puzzle(clues)
    for cell in puzzle.numbered:
        value = clues[cell[0]][cell[1]]
        if value is not None and value > len(puzzle.window(cell)):
            raise ValueError(f"clue {value} at {cell_name(cell)} exceeds its window")
    return puzzle


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """One Boolean per cell (True is black) and one COUNT per numbered window."""
    puzzle = parse(text)
    model = Model()
    for r in range(puzzle.size):
        for c in range(puzzle.size):
            name = cell_name((r, c))
            model.constrain(
                f"{name} is black or white",
                Kind.EXACTLY_ONE,
                [model.literal(name, True), model.literal(name, False)],
                defines=name,
                family="each cell is black or white",
            )
    for cell in puzzle.numbered:
        value = puzzle.clues[cell[0]][cell[1]]
        assert value is not None
        model.constrain(
            f"{value} black cells around {cell_name(cell)}",
            Kind.COUNT,
            [model.literal(cell_name(near), True) for near in puzzle.window(cell)],
            allowed_counts=(value,),
            family="black cells in a numbered window",
        )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Numbers where given, then a filled square (black), a dot (white) or `?`."""
    changed = {step.var for step in steps if step.asserted}
    out = [f"\n{BOLD}{title}{RESET}"]
    for r in range(puzzle.size):
        marks = []
        for c in range(puzzle.size):
            name = cell_name((r, c))
            chosen = model.chosen(name)
            shade = "■" if chosen is True else "·" if chosen is False else "?"
            clue = puzzle.clues[r][c]
            mark = f"{clue}{shade}" if clue is not None else f" {shade}"
            marks.append(f"{NEW if name in changed else ''}{mark}{RESET}")
        out.append(" ".join(marks))
    return "\n".join(out)
