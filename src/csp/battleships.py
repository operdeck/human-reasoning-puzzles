"""Battleships counts-only: Boolean cells with row and column totals."""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .icons import symbol
from .puzzlefile import read_sections

type Cell = tuple[int, int]


class Puzzle:
    def __init__(
        self, size: int, row_counts: list[int], column_counts: list[int], givens: list[list[int]]
    ) -> None:
        self.size = size
        self.row_counts = row_counts
        self.column_counts = column_counts
        self.givens = givens


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
        raise ValueError("Battleships counts-only needs a board at least 2x2")
    row_counts = _counts(sections["RowCounts"], size, "RowCounts")
    column_counts = _counts(sections["ColumnCounts"], size, "ColumnCounts")
    if sum(row_counts) != sum(column_counts):
        raise ValueError("row and column totals must agree")
    givens = _givens(sections.get("Givens", []), size)
    if any(sum(row) > row_counts[index] for index, row in enumerate(givens)):
        raise ValueError("Givens exceed a row count")
    if any(
        sum(givens[row][col] == 1 for row in range(size)) > column_counts[col]
        for col in range(size)
    ):
        raise ValueError("Givens exceed a column count")
    return Puzzle(size, row_counts, column_counts, givens)


def _counts(lines: list[str], size: int, name: str) -> list[int]:
    values = [token for line in lines for token in line.split()]
    if len(values) != size or any(not token.isdigit() for token in values):
        raise ValueError(f"{name}: expected {size} non-negative integer counts")
    counts = [int(token) for token in values]
    if any(count > size for count in counts):
        raise ValueError(f"{name}: counts cannot exceed {size}")
    return counts


def _givens(lines: list[str], size: int) -> list[list[int]]:
    if not lines:
        return [[-1] * size for _ in range(size)]
    rows = [line.split() for line in lines]
    if len(rows) != size or any(len(row) != size for row in rows):
        raise ValueError(f"Givens is not {size}x{size}")
    if any(value not in (".", "0", "1") for row in rows for value in row):
        raise ValueError("Givens cells must be '.', '0', or '1'")
    return [[-1 if value == "." else int(value) for value in row] for row in rows]


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
    return model, puzzle


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
    out.append("Counts-only model: ship shape and connectivity are not represented.")
    return "\n".join(out)
