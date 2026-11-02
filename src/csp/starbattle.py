"""One-star Queens and multi-star Star Battle share a parser and puzzle model."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .core import Kind, Model, Step
from .icons import symbol
from .regiongrid import RegionGrid, is_connected, read_region_grid

type Cell = tuple[int, int]


@dataclass(frozen=True)
class Puzzle:
    areas: RegionGrid
    stars: int
    givens: list[list[int]]
    icon: str

    @property
    def size(self) -> int:
        return self.areas.size

    @property
    def name(self) -> str:
        return "Queens" if self.stars == 1 else "Star Battle"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def cell_assignment(puzzle: Puzzle, solution: Mapping[str, Any]) -> dict[str, bool]:
    """Translate a solver or brute-force answer into a board-cell assignment."""
    if puzzle.stars == 1:
        chosen = set(solution.values())
        return {
            cell_name((row, col)): (row, col) in chosen
            for row in range(puzzle.size)
            for col in range(puzzle.size)
        }
    return {
        cell_name((row, col)): bool(solution.get(cell_name((row, col)), False))
        for row in range(puzzle.size)
        for col in range(puzzle.size)
    }


def parse(text: str) -> Puzzle:
    sections, areas = read_region_grid(text, ("queens", "starbattle"))
    values = sections.get("Stars", [])
    family = sections["Family"][0].casefold()
    if family == "queens":
        if values and (len(values) != 1 or values[0] != "1"):
            raise ValueError("Family: queens is an alias for Star Battle with Stars: 1")
        icons = sections.get("Icon", [])
        if icons and (len(icons) != 1 or icons[0].casefold() not in {"queen", "dog", "puppy"}):
            raise ValueError("Icon must be one of queen, dog, puppy")
        icon = icons[0].casefold() if icons else "queen"
        stars = 1
    else:
        if len(values) != 1 or not values[0].isdigit():
            raise ValueError("Stars: must give one positive stars-per-line count")
        stars = int(values[0])
        icon = "queen" if stars == 1 else "star"
    if not 1 <= stars <= areas.size:
        raise ValueError(f"Stars: must be between 1 and {areas.size}")
    cells_by_region = areas.cells_by_region
    if len(cells_by_region) != areas.size:
        raise ValueError(f"Star Battle needs {areas.size} regions, got {len(cells_by_region)}")
    if small := {
        region: len(cells) for region, cells in cells_by_region.items() if len(cells) < stars
    }:
        raise ValueError(f"each region needs at least {stars} cells, got {small}")
    if split := [region for region, cells in cells_by_region.items() if not is_connected(cells)]:
        raise ValueError(f"each region must be one connected area, but {split} are not")
    if stars * 2 > areas.size * areas.size:
        raise ValueError("Stars: count exceeds the number of board cells")
    lines = sections.get("Givens", [])
    given_rows = [line.split() for line in lines]
    if not given_rows:
        givens = [[-1] * areas.size for _ in range(areas.size)]
    elif family == "queens" and (
        len(given_rows) != areas.size or any(len(row) != areas.size for row in given_rows)
    ):
        givens = [[-1] * areas.size for _ in range(areas.size)]
        for line in lines:
            parts = line.split()
            match = (
                re.fullmatch(r"r(\d+)c(\d+)", parts[1], flags=re.IGNORECASE)
                if len(parts) == 2
                else None
            )
            if match is None or parts[0] not in areas.names:
                raise ValueError(f"bad queen given {line!r}, expected 'region r1c2'")
            row, col = int(match[1]) - 1, int(match[2]) - 1
            if not (0 <= row < areas.size and 0 <= col < areas.size):
                raise ValueError(f"queen square {parts[1]!r} is off the board")
            if areas.cells[row][col] != parts[0]:
                raise ValueError(f"given queen {parts[0]} {parts[1]} is outside its region")
            if givens[row][col] >= 0:
                raise ValueError(f"queen square {parts[1]!r} is given more than once")
            givens[row][col] = 1
    else:
        if len(given_rows) != areas.size or any(len(row) != areas.size for row in given_rows):
            raise ValueError(f"Givens is not {areas.size}x{areas.size}")
        if any(value not in ("?", ".", "*") for row in given_rows for value in row):
            raise ValueError("Givens cells must be '?', '.', or '*'")
        givens = [
            [-1 if value == "?" else int(value == "*") for value in row] for row in given_rows
        ]
    for row in range(areas.size):
        if sum(value == 1 for value in givens[row]) > stars:
            raise ValueError(f"Givens exceed the star count in row {row + 1}")
    for col in range(areas.size):
        if sum(givens[row][col] == 1 for row in range(areas.size)) > stars:
            raise ValueError(f"Givens exceed the star count in column {col + 1}")
    for row in range(areas.size - 1):
        for col in range(areas.size - 1):
            if (
                sum(
                    givens[r][c] == 1
                    for r, c in ((row, col), (row, col + 1), (row + 1, col), (row + 1, col + 1))
                )
                > 1
            ):
                raise ValueError("Givens contain touching stars")
    return Puzzle(areas, stars, givens, icon)


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    size, model = puzzle.size, Model()
    cells_by_region = puzzle.areas.cells_by_region
    if puzzle.stars == 1:
        for region, cells in cells_by_region.items():
            model.constrain(
                f"one queen in {puzzle.areas.names[region]}",
                Kind.EXACTLY_ONE,
                [model.literal(region, cell) for cell in cells],
                defines=region,
                family="one queen per region",
            )
        for row in range(size):
            model.constrain(
                f"one queen in row {row + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(puzzle.areas.cells[row][col], (row, col)) for col in range(size)],
                family="one queen per row",
            )
        for col in range(size):
            model.constrain(
                f"one queen in column {col + 1}",
                Kind.EXACTLY_ONE,
                [model.literal(puzzle.areas.cells[row][col], (row, col)) for row in range(size)],
                family="one queen per column",
            )
        for row in range(size - 1):
            for col in range(size - 1):
                cells = (
                    (row, col),
                    (row, col + 1),
                    (row + 1, col),
                    (row + 1, col + 1),
                )
                model.constrain(
                    f"queens do not touch near r{row + 1}c{col + 1}",
                    Kind.AT_MOST_ONE,
                    [model.literal(puzzle.areas.cells[r][c], (r, c)) for r, c in cells],
                    family="queens do not touch",
                )
        for row, line in enumerate(puzzle.givens):
            for col, value in enumerate(line):
                if value >= 0:
                    region = puzzle.areas.cells[row][col]
                    literal = model.literal(region, (row, col))
                    if value:
                        model.assign(literal, "given", "stated in the puzzle")
                    else:
                        model.eliminate(literal, "given", "stated in the puzzle")
        return model, puzzle

    for row in range(size):
        for col in range(size):
            name = cell_name((row, col))
            model.constrain(
                f"{name} is a star or empty",
                Kind.EXACTLY_ONE,
                [model.literal(name, True), model.literal(name, False)],
                defines=name,
                family="each cell is a star or empty",
            )
            if puzzle.givens[row][col] >= 0:
                model.assign(
                    model.literal(name, bool(puzzle.givens[row][col])),
                    "given",
                    "stated in the puzzle",
                )

    def exact_count(name: str, cells: Sequence[Cell], line: str) -> None:
        model.constrain(
            name,
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in cells],
            allowed_counts=(puzzle.stars,),
            family=f"exactly {puzzle.stars} stars per {line}",
        )

    for row in range(size):
        exact_count(
            f"{puzzle.stars} stars in row {row + 1}",
            [(row, col) for col in range(size)],
            "row",
        )
    for col in range(size):
        exact_count(
            f"{puzzle.stars} stars in column {col + 1}",
            [(row, col) for row in range(size)],
            "column",
        )
    for region, cells in cells_by_region.items():
        exact_count(f"{puzzle.stars} stars in region {puzzle.areas.names[region]}", cells, "region")
    for row in range(size - 1):
        for col in range(size - 1):
            window = (
                (row, col),
                (row, col + 1),
                (row + 1, col),
                (row + 1, col + 1),
            )
            model.constrain(
                f"at most one star near r{row + 1}c{col + 1}",
                Kind.AT_MOST_ONE,
                [model.literal(cell_name(cell), True) for cell in window],
                family="stars do not touch",
            )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    changed = {step.var for step in steps if step.asserted}
    changed_options = {(step.var, step.value) for step in steps if step.asserted}
    out = [f"\n{title}"]
    mark = symbol(puzzle.icon)
    if puzzle.stars == 1:
        regions = tuple(puzzle.areas.names)
        symbols = {region: _region_symbol(index) for index, region in enumerate(regions)}
        options = {
            region: {model.value_of(literal) for literal in model.options(region)}
            for region in regions
        }
        region_choices = {region: model.chosen(region) for region in regions}
        for row in range(puzzle.size):
            values = []
            for col in range(puzzle.size):
                cell = (row, col)
                region = puzzle.areas.cells[row][col]
                value = (
                    mark
                    if region_choices[region] == cell
                    else symbols[region]
                    if cell in options[region]
                    else "."
                )
                tint = "\033[38;5;21m" if (region, cell) in changed_options else ""
                values.append(f"{tint}{value}\033[0m")
            out.append(f"{row + 1:>2} " + " ".join(values))
        out.append("   " + " ".join(str(col + 1) for col in range(puzzle.size)))
        out.append(
            "Regions: "
            + ", ".join(f"{symbols[region]}={puzzle.areas.names[region]}" for region in regions)
        )
        return "\n".join(out)
    for row in range(puzzle.size):
        cells = []
        for col in range(puzzle.size):
            name = cell_name((row, col))
            chosen_value = model.chosen(name)
            value = mark if chosen_value is True else "." if chosen_value is False else "?"
            tint = "\033[38;5;21m" if name in changed else ""
            cells.append(f"{tint}{value}\033[0m")
        out.append(f"{row + 1:>2} " + " ".join(cells))
    out.append("   " + " ".join(str(col + 1) for col in range(puzzle.size)))
    piece = "queen" if puzzle.stars == 1 else "stars"
    out.append(f"Regions: {len(puzzle.areas.names)}; {piece} per line/region: {puzzle.stars}")
    return "\n".join(out)


def _region_symbol(index: int) -> str:
    symbol_text = ""
    while True:
        index, remainder = divmod(index, 26)
        symbol_text = chr(ord("A") + remainder) + symbol_text
        if index == 0:
            return symbol_text
        index -= 1
