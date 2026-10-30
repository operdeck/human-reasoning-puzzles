"""Queens-style placement: one queen per row, column and region, never touching.

An optional `Icon:` section (`queen`, `dog` or `puppy`) changes only the
piece's appearance, never the puzzle family or rules.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .core import Kind, Model, Step
from .puzzlefile import read_sections

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"
QUEEN_MARK = "♛"
DOG_MARK = "🐕"
PUPPY_MARK = "🐶"
ICONS = ("queen", "dog", "puppy")
ICON_MARKS = {"queen": QUEEN_MARK, "dog": DOG_MARK, "puppy": PUPPY_MARK}


@dataclass(frozen=True, order=True)
class Cell:
    row: int
    col: int

    def __str__(self) -> str:
        return f"r{self.row + 1}c{self.col + 1}"


@dataclass(frozen=True)
class Puzzle:
    region_names: dict[str, str]
    grid: list[list[str]]
    givens: dict[str, Cell]
    icon: str = "queen"

    @property
    def size(self) -> int:
        return len(self.grid)

    @property
    def region_ids(self) -> tuple[str, ...]:
        return tuple(self.region_names)

    @property
    def cells_by_region(self) -> dict[str, tuple[Cell, ...]]:
        cells: dict[str, list[Cell]] = {region: [] for region in self.region_ids}
        for row, line in enumerate(self.grid):
            for col, region in enumerate(line):
                cells[region].append(Cell(row, col))
        return {region: tuple(squares) for region, squares in cells.items()}

    @property
    def symbols(self) -> dict[str, str]:
        return {region: _symbol(index) for index, region in enumerate(self.region_ids)}


def _connected(grid: list[list[str]], region: str) -> bool:
    """True if the region's cells form one area joined by shared sides."""
    cells = {
        (r, c) for r, line in enumerate(grid) for c, value in enumerate(line) if value == region
    }
    seen: set[tuple[int, int]] = set()
    todo = [next(iter(cells))]
    while todo:
        row, col = todo.pop()
        if (row, col) in seen:
            continue
        seen.add((row, col))
        todo.extend(
            near
            for near in ((row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1))
            if near in cells and near not in seen
        )
    return seen == cells


def _display_width(mark: str) -> int:
    """Terminal columns a mark takes: emoji are double width."""
    return 2 if ord(mark[0]) >= 0x1F000 else 1


def _centre(mark: str, width: int) -> str:
    missing = width - _display_width(mark) - (len(mark) - 1)
    left = missing // 2
    return " " * left + mark + " " * (missing - left)


def _symbol(index: int) -> str:
    label = ""
    while True:
        index, remainder = divmod(index, 26)
        label = chr(ord("A") + remainder) + label
        if index == 0:
            return label
        index -= 1


def parse(text: str) -> Puzzle:
    """Read a Queens file containing its size and one region ID per cell."""
    sections = read_sections(text)
    for required in ("Family", "Size", "Regions", "Grid"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() != "queens":
        raise ValueError("Family must be 'queens'")
    icon = "queen"
    if "Icon" in sections:
        if len(sections["Icon"]) != 1 or sections["Icon"][0].casefold() not in ICONS:
            raise ValueError(f"Icon must be one of {', '.join(ICONS)}")
        icon = sections["Icon"][0].casefold()
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be a positive integer") from exc
    if size < 1:
        raise ValueError("Size must be a positive integer")

    region_names: dict[str, str] = {}
    for line in sections["Regions"]:
        identifier, separator, name = line.partition(":")
        identifier, name = identifier.strip(), name.strip()
        if (
            not separator
            or not identifier
            or any(char.isspace() for char in identifier)
            or not name
        ):
            raise ValueError(f"bad region {line!r}, expected 'id: name'")
        if identifier in region_names:
            raise ValueError(f"region ID {identifier!r} is defined more than once")
        region_names[identifier] = name
    if len(region_names) != size:
        raise ValueError(f"Queens needs {size} regions, got {len(region_names)}")

    grid = [line.split() for line in sections["Grid"]]
    if len(grid) != size or any(len(row) != size for row in grid):
        raise ValueError(f"Grid is not {size}x{size}")
    unknown = {region for row in grid for region in row} - set(region_names)
    if unknown:
        raise ValueError(f"Grid uses region IDs with no name: {sorted(unknown)}")
    if empty := sorted(set(region_names) - {region for row in grid for region in row}):
        raise ValueError(f"regions with no cells in Grid: {empty}")
    if split := [region for region in region_names if not _connected(grid, region)]:
        raise ValueError(f"each region must be one connected area, but {split} are not")
    givens: dict[str, Cell] = {}
    given_rows: set[int] = set()
    given_columns: set[int] = set()
    for line in sections.get("Givens", []):
        parts = line.split()
        if len(parts) != 2 or parts[0] not in region_names:
            raise ValueError(f"bad queen given {line!r}, expected 'region r1c1'")
        match = re.fullmatch(r"r(\d+)c(\d+)", parts[1], flags=re.IGNORECASE)
        if match is None:
            raise ValueError(f"bad queen square {parts[1]!r}, expected like r2c3")
        cell = Cell(int(match[1]) - 1, int(match[2]) - 1)
        if not (0 <= cell.row < size and 0 <= cell.col < size):
            raise ValueError(f"queen square {parts[1]!r} is off the board")
        if grid[cell.row][cell.col] != parts[0]:
            raise ValueError(f"given queen {parts[0]} {parts[1]} is outside its region")
        if parts[0] in givens or cell.row in given_rows or cell.col in given_columns:
            raise ValueError("queen givens must use distinct regions, rows, and columns")
        givens[parts[0]] = cell
        given_rows.add(cell.row)
        given_columns.add(cell.col)
    return Puzzle(region_names, grid, givens, icon)


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """Compile Queens rules to generic exact-one and at-most-one constraints."""
    puzzle = parse(text)
    size = puzzle.size
    model = Model()

    for region, cells in puzzle.cells_by_region.items():
        model.constrain(
            f"one queen in {puzzle.region_names[region]}",
            Kind.EXACTLY_ONE,
            [model.literal(region, cell) for cell in cells],
            defines=region,
            family="one queen per region",
        )

    for row in range(size):
        model.constrain(
            f"one queen in row {row + 1}",
            Kind.EXACTLY_ONE,
            [model.literal(puzzle.grid[row][col], Cell(row, col)) for col in range(size)],
            family="one queen per row",
        )
    for col in range(size):
        model.constrain(
            f"one queen in column {col + 1}",
            Kind.EXACTLY_ONE,
            [model.literal(puzzle.grid[row][col], Cell(row, col)) for row in range(size)],
            family="one queen per column",
        )
    for row in range(size - 1):
        for col in range(size - 1):
            cells = (
                Cell(row, col),
                Cell(row, col + 1),
                Cell(row + 1, col),
                Cell(row + 1, col + 1),
            )
            model.constrain(
                f"queens do not touch near r{row + 1}c{col + 1}",
                Kind.AT_MOST_ONE,
                [model.literal(puzzle.grid[cell.row][cell.col], cell) for cell in cells],
                family="queens do not touch",
            )
    for region, cell in puzzle.givens.items():
        model.assign(model.literal(region, cell), "given", "stated in the puzzle")
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Draw region candidates and placed queens, highlighting the latest changes."""
    options = {
        region: {model.value_of(literal) for literal in model.options(region)}
        for region in puzzle.region_ids
    }
    chosen = {region: model.chosen(region) for region in puzzle.region_ids}
    changed = {(step.var, step.value) for step in steps}
    symbols = puzzle.symbols
    queen_mark = ICON_MARKS[puzzle.icon]
    wide = _display_width(queen_mark) > 1  # emoji take two terminal columns
    width = max(1, 2 if wide else 1, max(map(len, symbols.values())))
    out = [f"\n{BOLD}{title}{RESET}"]
    for row, line in enumerate(puzzle.grid):
        cells = []
        for col, region in enumerate(line):
            cell = Cell(row, col)
            if chosen[region] == cell:
                mark = queen_mark
            elif cell in options[region]:
                mark = symbols[region]
            else:
                mark = "."
            tint = NEW if (region, cell) in changed else ""
            cells.append(f"{tint}{_centre(mark, width)}{RESET}")
        out.append(f"{row + 1:>2} " + " ".join(cells))
    out.append("   " + " ".join(str(col + 1).rjust(width) for col in range(puzzle.size)))
    out.append(
        "Regions: "
        + ", ".join(
            f"{symbols[region]}={puzzle.region_names[region]}" for region in puzzle.region_ids
        )
    )
    return "\n".join(out)
