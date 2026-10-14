"""Minesweeper-style boards compiled to Boolean cells and neighborhood counts."""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]


class Puzzle:
    def __init__(self, clues: list[list[int | None]], total_mines: int | None) -> None:
        self.clues = clues
        self.size = len(clues)
        self.total_mines = total_mines
        self.unknown = tuple(
            (row, col)
            for row in range(self.size)
            for col in range(self.size)
            if clues[row][col] is None
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
    for required in ("Family", "Size", "Clues"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() != "minesweeper":
        raise ValueError("Family must be 'minesweeper'")
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be a positive integer") from exc
    if size < 2:
        raise ValueError("Minesweeper needs a board at least 2x2")
    clue_rows = [line.split() for line in sections["Clues"]]
    if len(clue_rows) != size or any(len(clue_row) != size for clue_row in clue_rows):
        raise ValueError(f"Clues is not {size}x{size}")
    clues: list[list[int | None]] = []
    for clue_row in clue_rows:
        parsed: list[int | None] = []
        for token in clue_row:
            if token == ".":
                parsed.append(None)
            elif token.isdigit() and 0 <= int(token) <= 8:
                parsed.append(int(token))
            else:
                raise ValueError(f"bad Minesweeper clue {token!r}, expected '.' or 0..8")
        clues.append(parsed)
    total_mines = _total_mines(
        sections.get("TotalMines", []), sum(value is None for row in clues for value in row)
    )
    puzzle = Puzzle(clues, total_mines)
    for row_index in range(size):
        for col in range(size):
            clue = clues[row_index][col]
            if clue is not None:
                available = sum(clues[r][c] is None for r, c in puzzle.neighbors((row_index, col)))
                if clue > available:
                    raise ValueError(
                        f"clue {clue} at {cell_name((row_index, col))} "
                        "exceeds its unknown neighbors"
                    )
    return puzzle


def _total_mines(lines: list[str], unknown_count: int) -> int | None:
    if not lines:
        return None
    if len(lines) != 1 or not lines[0].isdigit():
        raise ValueError("TotalMines: must contain one non-negative integer")
    total = int(lines[0])
    if total > unknown_count:
        raise ValueError(f"TotalMines: {total} exceeds the {unknown_count} unknown cells")
    return total


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    model = Model()
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            name = cell_name((row, col))
            model.constrain(
                f"{name} is a mine or safe",
                Kind.EXACTLY_ONE,
                [model.literal(name, True), model.literal(name, False)],
                defines=name,
                family="each cell is mined or safe",
            )
            if puzzle.clues[row][col] is not None:
                model.assign(model.literal(name, False), "numbered clue", "a numbered cell is safe")
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            clue = puzzle.clues[row][col]
            if clue is None:
                continue
            cells = puzzle.neighbors((row, col))
            model.constrain(
                f"{clue} mines near {cell_name((row, col))}",
                Kind.COUNT,
                [model.literal(cell_name(cell), True) for cell in cells],
                allowed_counts=(clue,),
                family="mine count in clue neighborhood",
            )
    if puzzle.total_mines is not None:
        model.constrain(
            f"{puzzle.total_mines} mines total",
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in puzzle.unknown],
            allowed_counts=(puzzle.total_mines,),
            family="total mine count",
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
            clue = puzzle.clues[row][col]
            chosen = model.chosen(name)
            mark = (
                str(clue)
                if clue is not None
                else "*"
                if chosen is True
                else "."
                if chosen is False
                else "?"
            )
            tint = "\033[38;5;21m" if name in changed else ""
            cells.append(f"{tint}{mark}\033[0m")
        out.append(" ".join(cells))
    if puzzle.total_mines is not None:
        out.append(f"Total mines: {puzzle.total_mines}")
    return "\n".join(out)
