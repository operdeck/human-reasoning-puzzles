"""Binairo/Takuzu and Tango using COUNT and generic relation constraints."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from .core import Kind, Model, Step
from .icons import symbol
from .puzzlefile import read_sections

type Cell = tuple[int, int]


@dataclass(frozen=True)
class Sign:
    kind: str
    first: Cell
    second: Cell

    @property
    def label(self) -> str:
        return f"{self.kind} {cell_name(self.first)} {cell_name(self.second)}"

    def holds(self, first: bool, second: bool) -> bool:
        return first == second if self.kind == "equal" else first != second


@dataclass(frozen=True)
class Puzzle:
    size: int
    givens: list[list[int]]
    signs: tuple[Sign, ...]


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def parse(text: str) -> Puzzle:
    sections = read_sections(text)
    for required in ("Family", "Size"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() not in ("binairo", "tango"):
        raise ValueError("Family must be 'binairo' or 'tango'")
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be an even integer from 4 to 16") from exc
    if size < 4 or size > 16 or size % 2:
        raise ValueError("Size must be an even integer from 4 to 16")
    givens = _givens(sections.get("Givens", []), size)
    signs = tuple(
        sign
        for kind, section_name in (("equal", "Equal"), ("different", "Different"))
        for sign in (_sign(line, kind, size) for line in sections.get(section_name, []))
    )
    return Puzzle(size, givens, signs)


def _givens(lines: list[str], size: int) -> list[list[int]]:
    if not lines:
        return [[-1] * size for _ in range(size)]
    rows = [line.split() for line in lines]
    if len(rows) != size or any(len(row) != size for row in rows):
        raise ValueError(f"Givens is not {size}x{size}")
    if any(value not in (".", "0", "1") for row in rows for value in row):
        raise ValueError("Givens cells must be '.', '0', or '1'")
    return [[-1 if value == "." else int(value) for value in row] for row in rows]


def _sign(line: str, kind: str, size: int) -> Sign:
    parts = line.split()
    if len(parts) != 2:
        raise ValueError(f"bad {kind} sign {line!r}, expected 'r1c1 r1c2'")
    cells = []
    for token in parts:
        if (match := re.fullmatch(r"r(\d+)c(\d+)", token, flags=re.IGNORECASE)) is None:
            raise ValueError(f"bad cell {token!r}, expected like r2c3")
        cell = int(match[1]) - 1, int(match[2]) - 1
        if not (0 <= cell[0] < size and 0 <= cell[1] < size):
            raise ValueError(f"cell {token!r} is off the grid")
        cells.append(cell)
    if abs(cells[0][0] - cells[1][0]) + abs(cells[0][1] - cells[1][1]) != 1:
        raise ValueError(f"sign {line!r} is not between neighboring cells")
    return Sign(kind, cells[0], cells[1])


def _add_distinct_lines(model: Model, lines: list[list[Cell]], axis: str) -> None:
    """Encode each line pair inequality as a chain of small generic relations."""
    for first_index, second_index in combinations(range(len(lines)), 2):
        previous = f"__{axis}_{first_index + 1}_{second_index + 1}_diff_0"
        model.constrain(
            f"{previous} is false",
            Kind.EXACTLY_ONE,
            [model.literal(previous, False), model.literal(previous, True)],
            defines=previous,
            hidden=True,
            family="auxiliary line-uniqueness state",
        )
        model.assign(model.literal(previous, False), "line uniqueness", "no cells compared yet")
        for index, (left, right) in enumerate(
            zip(lines[first_index], lines[second_index], strict=True), 1
        ):
            current = f"__{axis}_{first_index + 1}_{second_index + 1}_diff_{index}"
            model.constrain(
                f"{current} is a Boolean state",
                Kind.EXACTLY_ONE,
                [model.literal(current, False), model.literal(current, True)],
                defines=current,
                hidden=True,
                family="auxiliary line-uniqueness state",
            )
            model.relate(
                f"{axis} {first_index + 1} differs from {second_index + 1} through cell {index}",
                (previous, cell_name(left), cell_name(right), current),
                lambda seen, first, second, result: result == (seen or first != second),
            )
            previous = current
        model.assign(model.literal(previous, True), "line uniqueness", "the two lines must differ")


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    size, model = puzzle.size, Model()
    for row in range(size):
        for col in range(size):
            name = cell_name((row, col))
            model.constrain(
                f"{name} is zero or one",
                Kind.EXACTLY_ONE,
                [model.literal(name, False), model.literal(name, True)],
                defines=name,
                family="each cell is Boolean",
            )
            if puzzle.givens[row][col] >= 0:
                model.assign(
                    model.literal(name, bool(puzzle.givens[row][col])),
                    "given",
                    "stated in the puzzle",
                )

    for row in range(size):
        cells = [(row, col) for col in range(size)]
        model.constrain(
            f"{size // 2} ones in row {row + 1}",
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in cells],
            allowed_counts=(size // 2,),
            family="equal symbols per row",
        )
    for col in range(size):
        cells = [(row, col) for row in range(size)]
        model.constrain(
            f"{size // 2} ones in column {col + 1}",
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in cells],
            allowed_counts=(size // 2,),
            family="equal symbols per column",
        )
    for row in range(size):
        for col in range(size - 2):
            cells = [(row, col + offset) for offset in range(3)]
            model.constrain(
                f"no three equal near {cell_name(cells[0])}",
                Kind.COUNT,
                [model.literal(cell_name(cell), True) for cell in cells],
                allowed_counts=(1, 2),
                family="no three equal in a line",
            )
    for col in range(size):
        for row in range(size - 2):
            cells = [(row + offset, col) for offset in range(3)]
            model.constrain(
                f"no three equal near {cell_name(cells[0])}",
                Kind.COUNT,
                [model.literal(cell_name(cell), True) for cell in cells],
                allowed_counts=(1, 2),
                family="no three equal in a line",
            )
    _add_distinct_lines(model, [[(row, col) for col in range(size)] for row in range(size)], "rows")
    _add_distinct_lines(
        model, [[(row, col) for row in range(size)] for col in range(size)], "columns"
    )
    for sign in puzzle.signs:
        model.relate(sign.label, (cell_name(sign.first), cell_name(sign.second)), sign.holds)
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    changed = {step.var for step in steps if step.asserted}
    out = [f"\n{title}"]
    for row in range(puzzle.size):
        cells = []
        for col in range(puzzle.size):
            name = cell_name((row, col))
            chosen = model.chosen(name)
            mark = (
                symbol("disc_black")
                if chosen is True
                else symbol("disc_white")
                if chosen is False
                else "?"
            )
            tint = "\033[38;5;21m" if name in changed else ""
            cells.append(f"{tint}{mark}\033[0m")
        out.append(" ".join(cells))
    if puzzle.signs:
        out.append("Signs: " + ", ".join(sign.label for sign in puzzle.signs))
    return "\n".join(out)
