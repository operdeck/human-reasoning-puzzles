"""Star Battle compiled to exact line counts and 2x2 at-most-one windows."""

from collections.abc import Sequence
from dataclasses import dataclass

from .core import Kind, Model, Step
from .icons import symbol
from .regiongrid import RegionGrid, is_connected, read_region_grid

type Cell = tuple[int, int]


@dataclass(frozen=True)
class Puzzle:
    areas: RegionGrid
    stars: int
    givens: list[list[int]]

    @property
    def size(self) -> int:
        return self.areas.size


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def parse(text: str) -> Puzzle:
    sections, areas = read_region_grid(text, ("starbattle",))
    values = sections.get("Stars", [])
    if len(values) != 1 or not values[0].isdigit():
        raise ValueError("Stars: must give one positive stars-per-line count")
    stars = int(values[0])
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
    given_rows = [line.split() for line in sections.get("Givens", [])]
    if not given_rows:
        givens = [[-1] * areas.size for _ in range(areas.size)]
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
    return Puzzle(areas, stars, givens)


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    size, model = puzzle.size, Model()
    cells_by_region = puzzle.areas.cells_by_region
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

    def exact_count(name: str, cells: Sequence[Cell]) -> None:
        model.constrain(
            name,
            Kind.COUNT,
            [model.literal(cell_name(cell), True) for cell in cells],
            allowed_counts=(puzzle.stars,),
            family=f"exactly {puzzle.stars} stars per {name.split()[-1]}",
        )

    for row in range(size):
        exact_count(f"{puzzle.stars} stars in row {row + 1}", [(row, col) for col in range(size)])
    for col in range(size):
        exact_count(
            f"{puzzle.stars} stars in column {col + 1}", [(row, col) for row in range(size)]
        )
    for region, cells in cells_by_region.items():
        exact_count(f"{puzzle.stars} stars in region {puzzle.areas.names[region]}", cells)
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
    out = [f"\n{title}"]
    for row in range(puzzle.size):
        cells = []
        for col in range(puzzle.size):
            name = cell_name((row, col))
            chosen = model.chosen(name)
            mark = symbol("star") if chosen is True else "." if chosen is False else "?"
            tint = "\033[38;5;21m" if name in changed else ""
            cells.append(f"{tint}{mark}\033[0m")
        out.append(f"{row + 1:>2} " + " ".join(cells))
    out.append("   " + " ".join(str(col + 1) for col in range(puzzle.size)))
    out.append(f"Regions: {len(puzzle.areas.names)}; stars per line/region: {puzzle.stars}")
    return "\n".join(out)
