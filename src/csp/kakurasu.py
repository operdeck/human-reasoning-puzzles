"""Kakurasu compiled as generic predicates over weighted Boolean rows/columns."""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]
type Grid = list[list[int]]


class Puzzle:
    def __init__(self, givens: Grid, row_sums: list[int], column_sums: list[int]) -> None:
        self.givens = givens
        self.row_sums = row_sums
        self.column_sums = column_sums
        self.size = len(givens)


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def parse(text: str) -> Puzzle:
    sections = read_sections(text)
    for required in ("Family", "Size", "RowSums", "ColumnSums"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() != "kakurasu":
        raise ValueError("Family must be 'kakurasu'")
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be a positive integer") from exc
    if size < 2:
        raise ValueError("Kakurasu needs a board at least 2x2")
    row_sums = _line_sums(sections["RowSums"], size, "RowSums")
    column_sums = _line_sums(sections["ColumnSums"], size, "ColumnSums")
    maximum = size * (size + 1) // 2
    if any(value > maximum for value in (*row_sums, *column_sums)):
        raise ValueError(f"line sums must be between 0 and {maximum}")
    givens = _givens(sections.get("Givens", []), size)
    return Puzzle(givens, row_sums, column_sums)


def _line_sums(lines: list[str], size: int, name: str) -> list[int]:
    values = [token for line in lines for token in line.split()]
    if len(values) != size or any(not token.isdigit() for token in values):
        raise ValueError(f"{name}: expected {size} non-negative integer sums")
    return [int(token) for token in values]


def _givens(lines: list[str], size: int) -> Grid:
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
                f"{name} is filled or empty",
                Kind.EXACTLY_ONE,
                [model.literal(name, True), model.literal(name, False)],
                defines=name,
                family="each cell is filled or empty",
            )
            if puzzle.givens[row][col] >= 0:
                model.assign(
                    model.literal(name, bool(puzzle.givens[row][col])),
                    "given",
                    "stated in the puzzle",
                )

    for row, target in enumerate(puzzle.row_sums):
        variables = [cell_name((row, col)) for col in range(size)]
        weights = tuple(range(1, size + 1))
        model.relate(
            f"row {row + 1} weighted sum is {target}",
            variables,
            lambda *values, target=target, weights=weights: (
                sum(weight for value, weight in zip(values, weights, strict=True) if value)
                == target
            ),
        )
    for col, target in enumerate(puzzle.column_sums):
        variables = [cell_name((row, col)) for row in range(size)]
        weights = tuple(range(1, size + 1))
        model.relate(
            f"column {col + 1} weighted sum is {target}",
            variables,
            lambda *values, target=target, weights=weights: (
                sum(weight for value, weight in zip(values, weights, strict=True) if value)
                == target
            ),
        )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    changed = {step.var for step in steps if step.asserted}
    out = [f"\n{title}"]
    for row in range(puzzle.size):
        marks = []
        for col in range(puzzle.size):
            name = cell_name((row, col))
            chosen = model.chosen(name)
            mark = "#" if chosen is True else "." if chosen is False else "?"
            tint = "\033[38;5;21m" if name in changed else ""
            marks.append(f"{tint}{mark}\033[0m")
        out.append(" ".join(marks) + f"  {puzzle.row_sums[row]}")
    out.append("\nColumn sums: " + " ".join(map(str, puzzle.column_sums)))
    return "\n".join(out)
