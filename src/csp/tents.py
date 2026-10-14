"""Tents and Trees using Boolean cells and existing count/relation primitives."""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]


class Puzzle:
    def __init__(
        self,
        size: int,
        trees: set[Cell],
        row_counts: list[int],
        column_counts: list[int],
    ) -> None:
        self.size = size
        self.trees = trees
        self.row_counts = row_counts
        self.column_counts = column_counts
        self.tent_candidates = {
            cell
            for cell in self.all_cells
            if cell not in self.trees and len(self.adjacent_trees(cell)) == 1
        }

    @property
    def all_cells(self) -> tuple[Cell, ...]:
        return tuple((row, col) for row in range(self.size) for col in range(self.size))

    def adjacent_trees(self, cell: Cell) -> tuple[Cell, ...]:
        return tuple(
            neighbor for neighbor in self.orthogonal_neighbors(cell) if neighbor in self.trees
        )

    def orthogonal_neighbors(self, cell: Cell) -> tuple[Cell, ...]:
        row, col = cell
        return tuple(
            neighbor
            for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
            if 0 <= neighbor[0] < self.size and 0 <= neighbor[1] < self.size
        )

    def neighbors(self, cell: Cell) -> tuple[Cell, ...]:
        row, col = cell
        return tuple(
            (row + dr, col + dc)
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr or dc) and 0 <= row + dr < self.size and 0 <= col + dc < self.size
        )


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def parse(text: str) -> Puzzle:
    sections = read_sections(text)
    for required in ("Family", "Size", "Trees", "RowCounts", "ColumnCounts"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() != "tents":
        raise ValueError("Family must be 'tents'")
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be a positive integer") from exc
    if size < 2:
        raise ValueError("Tents needs a board at least 2x2")
    tree_rows = [line.split() for line in sections["Trees"]]
    if len(tree_rows) != size or any(len(row) != size for row in tree_rows):
        raise ValueError(f"Trees is not {size}x{size}")
    if any(token not in (".", "T") for row in tree_rows for token in row):
        raise ValueError("Trees: cells must be '.' or 'T'")
    trees = {
        (row, col)
        for row, values in enumerate(tree_rows)
        for col, value in enumerate(values)
        if value == "T"
    }
    if not trees:
        raise ValueError("Trees: must contain at least one tree")
    row_counts = _counts(sections["RowCounts"], size, "RowCounts")
    column_counts = _counts(sections["ColumnCounts"], size, "ColumnCounts")
    if sum(row_counts) != len(trees) or sum(column_counts) != len(trees):
        raise ValueError("row and column tent totals must equal the number of trees")
    puzzle = Puzzle(size, trees, row_counts, column_counts)
    if any(
        not any(cell in puzzle.tent_candidates for cell in puzzle.orthogonal_neighbors(tree))
        for tree in trees
    ):
        raise ValueError("every tree needs an adjacent empty cell that touches no other tree")
    return puzzle


def _counts(lines: list[str], size: int, section: str) -> list[int]:
    values = [int(token) for line in lines for token in line.split()]
    if len(values) != size or any(value < 0 or value > size for value in values):
        raise ValueError(f"{section}: expected {size} counts between 0 and {size}")
    return values


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    model = Model()
    for cell in puzzle.all_cells:
        name = cell_name(cell)
        model.constrain(
            f"{name} is a tent or empty",
            Kind.EXACTLY_ONE,
            [model.literal(name, True), model.literal(name, False)],
            defines=name,
            family="each cell is a tent or empty",
        )
        if cell not in puzzle.tent_candidates:
            model.assign(
                model.literal(name, False), "tree adjacency", "a tent needs exactly one tree"
            )
    for row in range(puzzle.size):
        cells = [(row, col) for col in range(puzzle.size)]
        model.constrain(
            f"{puzzle.row_counts[row]} tents in row {row + 1}",
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in cells],
            allowed_counts=(puzzle.row_counts[row],),
            family="tent count per row",
        )
    for col in range(puzzle.size):
        cells = [(row, col) for row in range(puzzle.size)]
        model.constrain(
            f"{puzzle.column_counts[col]} tents in column {col + 1}",
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in cells],
            allowed_counts=(puzzle.column_counts[col],),
            family="tent count per column",
        )
    for tree in sorted(puzzle.trees):
        neighbors = [
            cell for cell in puzzle.orthogonal_neighbors(tree) if cell in puzzle.tent_candidates
        ]
        model.constrain(
            f"one tent beside tree {cell_name(tree)}",
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in neighbors],
            allowed_counts=(1,),
            family="one tent per tree",
        )
    for row in range(puzzle.size - 1):
        for col in range(puzzle.size - 1):
            window = (
                (row, col),
                (row, col + 1),
                (row + 1, col),
                (row + 1, col + 1),
            )
            model.constrain(
                f"tents do not touch near r{row + 1}c{col + 1}",
                Kind.AT_MOST_ONE,
                [model.literal(cell_name(cell), True) for cell in window],
                family="tents do not touch",
            )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    changed = {step.var for step in steps if step.asserted}
    out = [f"\n{title}"]
    for row in range(puzzle.size):
        cells = []
        for col in range(puzzle.size):
            cell = (row, col)
            name = cell_name(cell)
            if cell in puzzle.trees:
                mark = "T"
            else:
                chosen = model.chosen(name)
                mark = "*" if chosen is True else "." if chosen is False else "?"
            tint = "\033[38;5;21m" if name in changed else ""
            cells.append(f"{tint}{mark}\033[0m")
        out.append(" ".join(cells))
    out.append("Rows: " + " ".join(map(str, puzzle.row_counts)))
    out.append("Cols: " + " ".join(map(str, puzzle.column_counts)))
    return "\n".join(out)
