"""Tectonic/Suguru compiled to cell domains and generic peer constraints."""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .regiongrid import RegionGrid, read_region_grid

type Cell = tuple[int, int]


class Puzzle:
    def __init__(self, areas: RegionGrid, givens: list[list[int]]) -> None:
        self.areas = areas
        self.givens = givens
        self.size = areas.size
        self.cells_by_region = areas.cells_by_region
        self.region_of = areas.cells
        self.domain_size = {
            cell: len(self.cells_by_region[region])
            for row, regions in enumerate(areas.cells)
            for col, region in enumerate(regions)
            for cell in ((row, col),)
        }

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
    sections, areas = read_region_grid(text, ("suguru", "tectonic"))
    rows = [
        line.split()
        for line in sections.get("Givens", [" ".join("." for _ in range(areas.size))] * areas.size)
    ]
    if len(rows) != areas.size or any(len(row) != areas.size for row in rows):
        raise ValueError(f"Givens is not {areas.size}x{areas.size}")
    givens: list[list[int]] = []
    sizes = {region: len(cells) for region, cells in areas.cells_by_region.items()}
    for row, values in enumerate(rows):
        parsed = []
        for col, token in enumerate(values):
            if token in (".", "0"):
                parsed.append(0)
                continue
            if not token.isdigit() or int(token) < 1:
                raise ValueError(f"bad Suguru given {token!r}, expected 1 or greater")
            value = int(token)
            region = areas.cells[row][col]
            if value > sizes[region]:
                raise ValueError(
                    f"given {value} at {cell_name((row, col))} exceeds region size {sizes[region]}"
                )
            parsed.append(value)
        givens.append(parsed)
    return Puzzle(areas, givens)


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    puzzle = parse(text)
    model = Model()
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            cell = (row, col)
            name = cell_name(cell)
            model.constrain(
                f"{name} holds one number",
                Kind.EXACTLY_ONE,
                [model.literal(name, value) for value in range(1, puzzle.domain_size[cell] + 1)],
                defines=name,
                family="each cell holds one number",
            )

    for region, cells in puzzle.cells_by_region.items():
        for value in range(1, len(cells) + 1):
            model.constrain(
                f"{value} once in {puzzle.areas.names[region]}",
                Kind.EXACTLY_ONE,
                [model.literal(cell_name(cell), value) for cell in cells],
                family="each number once per region",
            )

    pairs = {
        tuple(sorted((cell, neighbor)))
        for row in range(puzzle.size)
        for col in range(puzzle.size)
        for cell in ((row, col),)
        for neighbor in puzzle.neighbors(cell)
        if cell < neighbor
    }
    for first, second in sorted(pairs):
        for value in range(1, min(puzzle.domain_size[first], puzzle.domain_size[second]) + 1):
            model.constrain(
                f"{value} not repeated at touching cells {cell_name(first)} {cell_name(second)}",
                Kind.AT_MOST_ONE,
                [model.literal(cell_name(first), value), model.literal(cell_name(second), value)],
                family="no equal numbers in touching cells",
            )

    for row, values in enumerate(puzzle.givens):
        for col, value in enumerate(values):
            if value:
                model.assign(
                    model.literal(cell_name((row, col)), value), "given", "stated in the puzzle"
                )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    placed = {step.var for step in steps if step.asserted}
    width = max(1, max(map(len, map(str, set(puzzle.domain_size.values())))))
    out = [f"\n{title}"]
    for row, regions in enumerate(puzzle.areas.cells):
        line = ""
        for col, region in enumerate(regions):
            if col:
                line += "|" if region != regions[col - 1] else " "
            name = cell_name((row, col))
            chosen = model.chosen(name)
            if chosen is not None:
                tint = "\033[94m" if name in placed else ""
                line += f"{tint}{str(chosen).center(width)}\033[0m"
            else:
                options = "".join(str(model.value_of(literal)) for literal in model.options(name))
                line += options.ljust(width) or ".".center(width)
        out.append(line)
    out.append(", ".join(f"{key}: {value}" for key, value in puzzle.areas.names.items()))
    return "\n".join(out)
