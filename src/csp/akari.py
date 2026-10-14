"""Light Up/Akari compiled to line-of-sight and numbered-wall counts."""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]


class Puzzle:
    def __init__(self, board: list[list[str]]) -> None:
        self.board = board
        self.size = len(board)
        self.open_cells = tuple(
            (row, col)
            for row in range(self.size)
            for col in range(self.size)
            if board[row][col] == "."
        )
        self.visible = {cell: self._visible_from(cell) for cell in self.open_cells}
        self.segments = self._segments()

    def _visible_from(self, cell: Cell) -> tuple[Cell, ...]:
        row, col = cell
        visible = [cell]
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = row + dr, col + dc
            while 0 <= r < self.size and 0 <= c < self.size and self.board[r][c] == ".":
                visible.append((r, c))
                r, c = r + dr, c + dc
        return tuple(visible)

    def _segments(self) -> tuple[tuple[Cell, ...], ...]:
        segments: set[tuple[Cell, ...]] = set()
        for row in range(self.size):
            current: list[Cell] = []
            for col in range(self.size + 1):
                if col < self.size and self.board[row][col] == ".":
                    current.append((row, col))
                elif current:
                    segments.add(tuple(current))
                    current = []
        for col in range(self.size):
            current = []
            for row in range(self.size + 1):
                if row < self.size and self.board[row][col] == ".":
                    current.append((row, col))
                elif current:
                    segments.add(tuple(current))
                    current = []
        return tuple(sorted(segments))

    def numbered_walls(self) -> tuple[tuple[Cell, int], ...]:
        return tuple(
            ((row, col), int(value))
            for row, line in enumerate(self.board)
            for col, value in enumerate(line)
            if value.isdigit()
        )

    def adjacent_open(self, cell: Cell) -> tuple[Cell, ...]:
        row, col = cell
        return tuple(
            neighbor
            for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
            if 0 <= neighbor[0] < self.size
            and 0 <= neighbor[1] < self.size
            and self.board[neighbor[0]][neighbor[1]] == "."
        )


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def parse(text: str) -> Puzzle:
    sections = read_sections(text)
    for required in ("Family", "Size", "Grid"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() not in ("akari", "lightup"):
        raise ValueError("Family must be 'akari' or 'lightup'")
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be a positive integer") from exc
    if size < 2:
        raise ValueError("Akari needs a board at least 2x2")
    rows = [line.split() for line in sections["Grid"]]
    if len(rows) != size or any(len(row) != size for row in rows):
        raise ValueError(f"Grid is not {size}x{size}")
    if any(token not in (".", "W", "0", "1", "2", "3", "4") for row in rows for token in row):
        raise ValueError("Grid cells must be '.', 'W', or a numbered wall from 0 to 4")
    puzzle = Puzzle(rows)
    for cell, count in puzzle.numbered_walls():
        if count > len(puzzle.adjacent_open(cell)):
            raise ValueError(f"numbered wall {cell_name(cell)} exceeds its open neighbors")
    if not puzzle.open_cells:
        raise ValueError("Grid must contain at least one open cell")
    return puzzle


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    model = Model()
    for cell in puzzle.open_cells:
        name = cell_name(cell)
        model.constrain(
            f"{name} has a bulb or is empty",
            Kind.EXACTLY_ONE,
            [model.literal(name, True), model.literal(name, False)],
            defines=name,
            family="each open cell has a bulb or is empty",
        )
    for segment in puzzle.segments:
        model.constrain(
            f"at most one bulb in sight line from {cell_name(segment[0])}",
            Kind.AT_MOST_ONE,
            [model.literal(cell_name(cell), True) for cell in segment],
            family="bulbs do not see each other",
        )
    for cell in puzzle.open_cells:
        visible = puzzle.visible[cell]
        model.constrain(
            f"cell {cell_name(cell)} is lit",
            Kind.COUNT,
            [model.literal(cell_name(other), True) for other in visible],
            allowed_counts=range(1, len(visible) + 1),
            family="every open cell is lit",
        )
    for wall, count in puzzle.numbered_walls():
        neighbors = puzzle.adjacent_open(wall)
        model.constrain(
            f"{count} bulbs around wall {cell_name(wall)}",
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in neighbors],
            allowed_counts=(count,),
            family="numbered wall bulb count",
        )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    changed = {step.var for step in steps if step.asserted}
    out = [f"\n{title}"]
    for row in range(puzzle.size):
        cells = []
        for col in range(puzzle.size):
            cell = (row, col)
            value = puzzle.board[row][col]
            name = cell_name(cell)
            if value != ".":
                mark = value
            else:
                chosen = model.chosen(name)
                mark = "*" if chosen is True else "." if chosen is False else "?"
            tint = "\033[38;5;21m" if name in changed else ""
            cells.append(f"{tint}{mark}\033[0m")
        out.append(" ".join(cells))
    return "\n".join(out)
