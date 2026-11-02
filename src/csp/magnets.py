"""Magnets compiled to three-valued cells, domino relations and polarity counts.

The board is pre-divided into dominoes. Each domino is a magnet (one cell `+`,
the other `-`) or neutral (both `0`). Row and column clues give how many `+` and
how many `-` a line holds; touching cells of different dominoes may never share a
polarity.

    Family: magnets
    Size: 4
    Dominoes:
    a a b c
    ...
    PlusTop:
    1 . 2 1
    PlusLeft:
    1 2 . 1
    MinusBottom:
    ...
    MinusRight:
    ...
    Givens:          # optional, '+', '-', '0' or '.'

`.` in a clue line means no clue. Boards are square.
"""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

SIZES = range(4, 11, 2)  # an even side, so dominoes can tile the board
CLUES = ("PlusTop", "PlusLeft", "MinusBottom", "MinusRight")
POLES = ("+", "-", "0")
# What a domino may hold, read in either order; the one rule both solvers share.
LEGAL_PAIRS = frozenset({("+", "-"), ("-", "+"), ("0", "0")})

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


class Puzzle:
    def __init__(
        self,
        ids: list[list[str]],
        counts: dict[str, list[int]],
        givens: list[list[str]],
    ) -> None:
        self.ids = ids
        self.size = len(ids)
        self.counts = counts  # clue name -> per-line count, -1 for none
        self.givens = givens  # '.', '+', '-' or '0'
        self.dominoes: dict[str, tuple[Cell, Cell]] = {}
        spots: dict[str, list[Cell]] = {}
        for r, row in enumerate(ids):
            for c, name in enumerate(row):
                spots.setdefault(name, []).append((r, c))
        for name, pair in spots.items():
            self.dominoes[name] = (pair[0], pair[1])

    def line_cells(self, clue: str, index: int) -> list[Cell]:
        """The cells of the row or column a clue is about."""
        n = self.size
        if clue in ("PlusTop", "MinusBottom"):
            return [(r, index) for r in range(n)]
        return [(index, c) for c in range(n)]

    @property
    def clue_lines(self) -> list[tuple[str, int, int]]:
        """Every stated clue as (clue name, line index, count)."""
        return [
            (clue, i, count)
            for clue in CLUES
            for i, count in enumerate(self.counts[clue])
            if count >= 0
        ]

    def foreign_neighbours(self) -> list[tuple[Cell, Cell]]:
        """Orthogonally touching cells that belong to different dominoes."""
        out = []
        for r in range(self.size):
            for c in range(self.size):
                for dr, dc in ((0, 1), (1, 0)):
                    r2, c2 = r + dr, c + dc
                    if r2 < self.size and c2 < self.size and self.ids[r][c] != self.ids[r2][c2]:
                        out.append(((r, c), (r2, c2)))
        return out


def polarity(clue: str) -> str:
    return "+" if clue.startswith("Plus") else "-"


def parse(text: str) -> Puzzle:
    """Read a Magnets file: Size, Dominoes, the four clue lines and optional Givens."""
    section = read_sections(text)
    for required in ("Family", "Size", "Dominoes"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() != "magnets":
        raise ValueError("Family must be 'magnets'")
    try:
        n = int(section["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be an integer") from exc
    if n not in SIZES:
        raise ValueError(
            f"Magnets boards are {SIZES.start}x{SIZES.start} to {SIZES[-1]}x{SIZES[-1]}"
        )
    ids = [line.split() for line in section["Dominoes"]]
    if len(ids) != n or any(len(row) != n for row in ids):
        raise ValueError(f"Dominoes is not {n}x{n}")
    puzzle_ids = ids
    seen: dict[str, list[Cell]] = {}
    for r, row in enumerate(ids):
        for c, name in enumerate(row):
            seen.setdefault(name, []).append((r, c))
    for name, cells in seen.items():
        if len(cells) != 2 or abs(cells[0][0] - cells[1][0]) + abs(cells[0][1] - cells[1][1]) != 1:
            raise ValueError(f"domino {name!r} must be exactly two touching cells")
    counts: dict[str, list[int]] = {}
    for clue in CLUES:
        tokens = [t for line in section.get(clue, []) for t in line.split()]
        if not tokens:
            tokens = ["."] * n
        if len(tokens) != n or any(t != "." and not t.isdigit() for t in tokens):
            raise ValueError(f"{clue}: expected {n} counts or '.'")
        counts[clue] = [-1 if t == "." else int(t) for t in tokens]
        if any(value > n for value in counts[clue]):
            raise ValueError(f"{clue}: a count exceeds the line length")
    givens = _givens(section.get("Givens", []), n)
    return Puzzle(puzzle_ids, counts, givens)


def _givens(lines: list[str], n: int) -> list[list[str]]:
    if not lines:
        return [["."] * n for _ in range(n)]
    rows = [line.split() for line in lines]
    if len(rows) != n or any(len(row) != n for row in rows):
        raise ValueError(f"Givens is not {n}x{n}")
    if any(token not in {".", "+", "-", "0"} for row in rows for token in row):
        raise ValueError("Givens cells must be '.', '+', '-' or '0'")
    return rows


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """Three-valued cells, one relation per domino, a COUNT per clue and polarity separation."""
    puzzle = parse(text)
    model = Model()
    for r in range(puzzle.size):
        for c in range(puzzle.size):
            name = cell_name((r, c))
            model.constrain(
                f"{name} is plus, minus or neutral",
                Kind.EXACTLY_ONE,
                [model.literal(name, pole) for pole in POLES],
                defines=name,
                family="each cell is plus, minus or neutral",
            )
    for name, (first, second) in puzzle.dominoes.items():
        model.relate(
            f"domino {name} is a magnet or neutral",
            [cell_name(first), cell_name(second)],
            lambda a, b: (a, b) in LEGAL_PAIRS,
        )
    for clue, index, count in puzzle.clue_lines:
        pole = polarity(clue)
        model.constrain(
            f"{count} {'plus' if pole == '+' else 'minus'} in {_line_name(clue, index)}",
            Kind.COUNT,
            [model.literal(cell_name(cell), pole) for cell in puzzle.line_cells(clue, index)],
            allowed_counts=(count,),
            family="poles counted per line",
        )
    for first, second in puzzle.foreign_neighbours():
        for pole in ("+", "-"):
            model.constrain(
                f"{cell_name(first)} and {cell_name(second)} are not both {pole}",
                Kind.AT_MOST_ONE,
                [model.literal(cell_name(first), pole), model.literal(cell_name(second), pole)],
                family="touching magnets repel",
            )
    # Givens last: `assign` only propagates through the constraints that already exist.
    for r in range(puzzle.size):
        for c in range(puzzle.size):
            if puzzle.givens[r][c] != ".":
                model.assign(
                    model.literal(cell_name((r, c)), puzzle.givens[r][c]), "given", "given"
                )
    return model, puzzle


def _line_name(clue: str, index: int) -> str:
    line = "column" if clue in ("PlusTop", "MinusBottom") else "row"
    return f"{line} {index + 1}"


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The board with `+`, `-`, `o` (neutral) or `?`, and the clue counts around it."""
    changed = {step.var for step in steps if step.asserted}

    def clue(values: list[int]) -> str:
        return " ".join("." if v < 0 else str(v) for v in values)

    out = [f"\n{BOLD}{title}{RESET}", f"    + {clue(puzzle.counts['PlusTop'])}"]
    for r in range(puzzle.size):
        marks = []
        for c in range(puzzle.size):
            name = cell_name((r, c))
            chosen = model.chosen(name)
            mark = "o" if chosen == "0" else chosen if chosen is not None else "?"
            marks.append(f"{NEW if name in changed else ''}{mark}{RESET}")
        left = puzzle.counts["PlusLeft"][r]
        right = puzzle.counts["MinusRight"][r]
        out.append(
            f"{'.' if left < 0 else left} | {' '.join(marks)} | {'.' if right < 0 else right}"
        )
    out.append(f"    - {clue(puzzle.counts['MinusBottom'])}")
    return "\n".join(out)
