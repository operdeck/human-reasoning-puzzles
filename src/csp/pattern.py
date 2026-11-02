"""Pattern (nonogram, picross) compiled to Boolean cells and one run relation per line.

Fill cells so that every row and column holds the run lengths given for it, in
order, each run separated from the next by at least one empty cell.

    Family: pattern
    Rows:
    1 1
    3
    0
    ...
    Columns:
    2
    1 1
    ...

One clue per line of the file, one line per row (then per column); `0` is an
empty line. The board may be rectangular. Relations cost grows exponentially with
line length, so lines are limited to `LONGEST` cells.
"""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

LONGEST = 15

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def runs(filled: Sequence[bool]) -> tuple[int, ...]:
    """The lengths of the runs of filled cells in a line, in order.

    This is the one rule the compiler and the brute force both call.
    """
    out: list[int] = []
    length = 0
    for value in filled:
        if value:
            length += 1
        elif length:
            out.append(length)
            length = 0
    if length:
        out.append(length)
    return tuple(out)


class Puzzle:
    def __init__(self, rows: list[tuple[int, ...]], columns: list[tuple[int, ...]]) -> None:
        self.row_clues = rows
        self.column_clues = columns
        self.rows = len(rows)
        self.cols = len(columns)


def parse(text: str) -> Puzzle:
    """Read a Pattern file: `Rows:` and `Columns:`, a line of run lengths for each."""
    section = read_sections(text)
    for required in ("Family", "Rows", "Columns"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() not in {
        "pattern",
        "nonogram",
        "picross",
    }:
        raise ValueError("Family must be 'pattern'")
    rows = [_clue(line, "Rows") for line in section["Rows"]]
    columns = [_clue(line, "Columns") for line in section["Columns"]]
    if not 2 <= len(rows) <= LONGEST or not 2 <= len(columns) <= LONGEST:
        raise ValueError(f"Pattern boards are 2 to {LONGEST} cells on a side")
    for name, clues, length in (("Rows", rows, len(columns)), ("Columns", columns, len(rows))):
        for number, clue in enumerate(clues, 1):
            if sum(clue) + max(0, len(clue) - 1) > length:
                raise ValueError(f"{name} line {number} needs more than {length} cells")
    if sum(map(sum, rows)) != sum(map(sum, columns)):
        raise ValueError("rows and columns count a different number of filled cells")
    return Puzzle(rows, columns)


def _clue(line: str, name: str) -> tuple[int, ...]:
    tokens = line.split()
    if not tokens or any(not t.isdigit() for t in tokens):
        raise ValueError(f"{name}: bad clue {line!r}, expected run lengths such as '2 1' or '0'")
    values = tuple(int(t) for t in tokens)
    if values == (0,):
        return ()
    if 0 in values:
        raise ValueError(f"{name}: a run of 0 is only allowed alone, as an empty line")
    return values


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """One Boolean per cell and a relation per line comparing its runs to the clue."""
    puzzle = parse(text)
    model = Model()
    for r in range(puzzle.rows):
        for c in range(puzzle.cols):
            name = cell_name((r, c))
            model.constrain(
                f"{name} is filled or empty",
                Kind.EXACTLY_ONE,
                [model.literal(name, True), model.literal(name, False)],
                defines=name,
                family="each cell is filled or empty",
            )
    for r, clue in enumerate(puzzle.row_clues):
        model.relate(
            f"row {r + 1} runs are {_text(clue)}",
            [cell_name((r, c)) for c in range(puzzle.cols)],
            lambda *values, clue=clue: runs(values) == clue,
        )
    for c, clue in enumerate(puzzle.column_clues):
        model.relate(
            f"column {c + 1} runs are {_text(clue)}",
            [cell_name((r, c)) for r in range(puzzle.rows)],
            lambda *values, clue=clue: runs(values) == clue,
        )
    return model, puzzle


def _text(clue: tuple[int, ...]) -> str:
    return " ".join(map(str, clue)) if clue else "empty"


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The board with filled squares, dots for empty cells and the run clues around it."""
    changed = {step.var for step in steps if step.asserted}
    tall = max(len(clue) for clue in puzzle.column_clues)
    out = [f"\n{BOLD}{title}{RESET}"]
    for level in range(tall):
        top = []
        for clue in puzzle.column_clues:
            index = level - (tall - len(clue))
            top.append(str(clue[index]) if index >= 0 else " ")
        out.append(" " * 12 + " ".join(f"{t:>2}" for t in top))
    for r in range(puzzle.rows):
        marks = []
        for c in range(puzzle.cols):
            name = cell_name((r, c))
            chosen = model.chosen(name)
            mark = "■" if chosen is True else "·" if chosen is False else "?"
            marks.append(f"{NEW if name in changed else ''}{mark:>2}{RESET}")
        label = " ".join(map(str, puzzle.row_clues[r])) or "0"
        out.append(f"{label:>11} " + " ".join(marks))
    return "\n".join(out)
