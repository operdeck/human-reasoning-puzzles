"""Battleships: line totals, an optional fleet, straight ships and no touching."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from .core import Kind, Model, Step
from .icons import symbol
from .puzzlefile import read_sections

type Cell = tuple[int, int]


@dataclass
class Puzzle:
    size: int
    row_counts: list[int]
    column_counts: list[int]
    givens: list[list[int]]
    fleet: tuple[int, ...] = ()
    segments: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class Ship:
    cells: tuple[Cell, ...]
    halo: frozenset[Cell]

    @property
    def name(self) -> str:
        return f"ship {len(self.cells)} {cell_name(self.cells[0])}-{cell_name(self.cells[-1])}"


SEGMENTS = {".", "0", "1", "O", "N", "S", "E", "W", "M"}


def segment(cells: Sequence[Cell], cell: Cell) -> str:
    """The shape at a cell of a straight ship; ends point towards open water."""
    if len(cells) == 1:
        return "O"
    first, last = min(cells), max(cells)
    if cell not in (first, last):
        return "M"
    if first[0] == last[0]:
        return "W" if cell == first else "E"
    return "N" if cell == first else "S"


def ships(puzzle: Puzzle) -> list[Ship]:
    """Legal straight positions, filtered only by explicit clues and line totals."""
    positions = []
    for length in sorted(set(puzzle.fleet)):
        for row in range(puzzle.size):
            for col in range(puzzle.size):
                for dr, dc in ((0, 1),) if length == 1 else ((0, 1), (1, 0)):
                    cells = tuple((row + i * dr, col + i * dc) for i in range(length))
                    if any(r >= puzzle.size or c >= puzzle.size for r, c in cells):
                        continue
                    if any(
                        count > puzzle.row_counts[r]
                        for r, count in Counter(r for r, _ in cells).items()
                    ) or any(
                        count > puzzle.column_counts[c]
                        for c, count in Counter(c for _, c in cells).items()
                    ):
                        continue
                    halo = frozenset(
                        (r + rd, c + cd)
                        for r, c in cells
                        for rd in (-1, 0, 1)
                        for cd in (-1, 0, 1)
                        if 0 <= r + rd < puzzle.size and 0 <= c + cd < puzzle.size
                    ) - set(cells)
                    if any(puzzle.givens[r][c] == 0 for r, c in cells):
                        continue
                    if any(puzzle.givens[r][c] == 1 for r, c in halo):
                        continue
                    if any(
                        puzzle.segments[r][c] not in {".", "1", segment(cells, (r, c))}
                        for r, c in cells
                    ):
                        continue
                    positions.append(Ship(cells, halo))
    return positions


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def parse(text: str) -> Puzzle:
    sections = read_sections(text)
    for required in ("Family", "Size", "RowCounts", "ColumnCounts"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() != "battleships":
        raise ValueError("Family must be 'battleships'")
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be a positive integer") from exc
    if size < 2:
        raise ValueError("Battleships needs a board at least 2x2")
    row_counts = _counts(sections["RowCounts"], size, "RowCounts")
    column_counts = _counts(sections["ColumnCounts"], size, "ColumnCounts")
    if sum(row_counts) != sum(column_counts):
        raise ValueError("row and column totals must agree")
    tokens = _givens(sections.get("Givens", []), size)
    givens = [[-1 if v == "." else 0 if v == "0" else 1 for v in row] for row in tokens]
    fleet: tuple[int, ...] = ()
    if "Fleet" in sections:
        values = [token for line in sections["Fleet"] for token in line.split()]
        if not values or any(not v.isdigit() or not 1 <= int(v) <= size for v in values):
            raise ValueError(f"Fleet: list ship lengths between 1 and {size}")
        fleet = tuple(sorted(map(int, values), reverse=True))
        if sum(fleet) != sum(row_counts):
            raise ValueError("Fleet total must equal row and column totals")
    elif any(v not in {".", "0", "1"} for row in tokens for v in row):
        raise ValueError("shaped Givens require a Fleet")
    if any(sum(v == 1 for v in row) > row_counts[index] for index, row in enumerate(givens)):
        raise ValueError("Givens exceed a row count")
    if any(
        sum(givens[row][col] == 1 for row in range(size)) > column_counts[col]
        for col in range(size)
    ):
        raise ValueError("Givens exceed a column count")
    if any(sum(v != 0 for v in row) < row_counts[index] for index, row in enumerate(givens)) or any(
        sum(givens[row][col] != 0 for row in range(size)) < column_counts[col]
        for col in range(size)
    ):
        raise ValueError("Givens leave too few cells for a line count")
    return Puzzle(size, row_counts, column_counts, givens, fleet, tuple(map(tuple, tokens)))


def _counts(lines: list[str], size: int, name: str) -> list[int]:
    values = [token for line in lines for token in line.split()]
    if len(values) != size or any(not token.isdigit() for token in values):
        raise ValueError(f"{name}: expected {size} non-negative integer counts")
    counts = [int(token) for token in values]
    if any(count > size for count in counts):
        raise ValueError(f"{name}: counts cannot exceed {size}")
    return counts


def _givens(lines: list[str], size: int) -> list[list[str]]:
    if not lines:
        return [["."] * size for _ in range(size)]
    rows = [line.split() for line in lines]
    if len(rows) != size or any(len(row) != size for row in rows):
        raise ValueError(f"Givens is not {size}x{size}")
    if any(value not in SEGMENTS for row in rows for value in row):
        raise ValueError("Givens cells must be '.', '0', '1', 'O', 'N', 'S', 'E', 'W', or 'M'")
    return rows


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    size, model = puzzle.size, Model()
    for row in range(size):
        for col in range(size):
            name = cell_name((row, col))
            model.constrain(
                f"{name} is occupied or empty",
                Kind.EXACTLY_ONE,
                [model.literal(name, True), model.literal(name, False)],
                defines=name,
                family="each cell is occupied or empty",
            )
            given = puzzle.givens[row][col]
            if given >= 0:
                model.assign(model.literal(name, bool(given)), "given", "stated in the puzzle")
    for row, count in enumerate(puzzle.row_counts):
        model.constrain(
            f"{count} occupied cells in row {row + 1}",
            Kind.COUNT,
            [model.literal(cell_name((row, col)), True) for col in range(size)],
            allowed_counts=(count,),
            family="occupied-cell count per row",
        )
    for col, count in enumerate(puzzle.column_counts):
        model.constrain(
            f"{count} occupied cells in column {col + 1}",
            Kind.COUNT,
            [model.literal(cell_name((row, col)), True) for row in range(size)],
            allowed_counts=(count,),
            family="occupied-cell count per column",
        )
    if puzzle.fleet:
        _compile_fleet(model, puzzle)
    return model, puzzle


def _compile_fleet(model: Model, puzzle: Puzzle) -> None:
    positions = ships(puzzle)
    for ship in positions:
        present = model.literal(ship.name, True)
        model.constrain(
            f"{ship.name} is present or absent",
            Kind.EXACTLY_ONE,
            [present, model.literal(ship.name, False)],
            defines=ship.name,
            hidden=True,
            family="each ship position is present or absent",
        )
        for cell in sorted(ship.halo):
            model.constrain(
                f"{ship.name} needs water at {cell_name(cell)}",
                Kind.AT_MOST_ONE,
                [present, model.literal(cell_name(cell), True)],
                family="ships do not touch, even diagonally",
            )
    for length, count in Counter(puzzle.fleet).items():
        options = [
            model.literal(ship.name, True) for ship in positions if len(ship.cells) == length
        ]
        if len(options) < count:
            raise ValueError(
                f"Fleet: too few possible positions for {count} ships of length {length}"
            )
        model.constrain(
            f"fleet has {count} ships of length {length}",
            Kind.COUNT,
            options,
            allowed_counts=(count,),
            family="fleet count per ship length",
        )
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            cell = (row, col)
            name = cell_name(cell)
            model.constrain(
                f"{name} is water or belongs to exactly one straight ship",
                Kind.EXACTLY_ONE,
                [model.literal(name, False)]
                + [model.literal(ship.name, True) for ship in positions if cell in ship.cells],
                family="occupied cells belong to one straight ship",
            )


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    changed = {step.var for step in steps if step.asserted}
    out = [f"\n{title}"]
    for row in range(puzzle.size):
        cells = []
        for col in range(puzzle.size):
            name = cell_name((row, col))
            chosen = model.chosen(name)
            mark = symbol("filled") if chosen is True else "." if chosen is False else "?"
            tint = "\033[38;5;21m" if name in changed else ""
            cells.append(f"{tint}{mark}\033[0m")
        out.append(" ".join(cells) + f"  {puzzle.row_counts[row]}")
    out.append("\nColumn counts: " + " ".join(map(str, puzzle.column_counts)))
    if puzzle.fleet:
        out.append("Fleet (ship lengths): " + " ".join(map(str, puzzle.fleet)))
        out.append("Ships are straight and may not touch, even diagonally.")
    else:
        out.append("Counts-only model: ship shape and connectivity are not represented.")
    return "\n".join(out)
