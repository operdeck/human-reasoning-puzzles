"""Bridges: numbered islands joined by at most two straight, non-crossing bridges.

    Family: bridges
    Size: 3 5
    Islands:
    2 . . . 2
    . . . . .
    2 . . . 2

Every island belongs to one connected network. Only the nearest island in
each orthogonal direction can be joined; island numbers count individual bridges.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]
type Pair = tuple[Cell, Cell]


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def pair_name(pair: Pair) -> str:
    return f"{cell_name(pair[0])}-{cell_name(pair[1])}"


def neighbours(islands: Mapping[Cell, int]) -> tuple[Pair, ...]:
    """The nearest island pairs in each row and column, each listed once."""
    pairs = []
    ordered = sorted(islands)
    for cell in ordered:
        for axis in (0, 1):
            candidates = [
                other
                for other in ordered
                if other[axis] > cell[axis] and other[1 - axis] == cell[1 - axis]
            ]
            if candidates:
                pairs.append((cell, min(candidates, key=lambda other: other[axis])))
    return tuple(sorted(pairs))


def crosses(first: Pair, second: Pair) -> bool:
    """Whether two bridge corridors intersect strictly between their endpoints."""
    if (first[0][0] == first[1][0]) == (second[0][0] == second[1][0]):
        return False
    horizontal, vertical = (first, second) if first[0][0] == first[1][0] else (second, first)
    return (
        horizontal[0][1] < vertical[0][1] < horizontal[1][1]
        and vertical[0][0] < horizontal[0][0] < vertical[1][0]
    )


@dataclass
class Puzzle:
    height: int
    width: int
    islands: dict[Cell, int]
    pairs: tuple[Pair, ...]

    def crossings(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (i, j)
            for i, first in enumerate(self.pairs)
            for j, second in enumerate(self.pairs)
            if i < j and crosses(first, second)
        )


def parse(text: str) -> Puzzle:
    """Read a rectangular island grid; one Size number denotes a square."""
    sections = read_sections(text)
    if [value.casefold() for value in sections.get("Family", [])] != ["bridges"]:
        raise ValueError("Family must be 'bridges'")
    size = sections.get("Size", [])
    try:
        dimensions = [int(token) for token in size[0].split()] if len(size) == 1 else []
    except ValueError as exc:
        raise ValueError("Size must be one or two positive integers") from exc
    if len(dimensions) not in (1, 2) or any(value < 2 for value in dimensions):
        raise ValueError("Size must be one or two integers of at least 2")
    height, width = (dimensions[0], dimensions[0]) if len(dimensions) == 1 else dimensions
    rows = [line.split() for line in sections.get("Islands", [])]
    if len(rows) != height or any(len(row) != width for row in rows):
        raise ValueError(f"Islands must contain a {height}x{width} grid")
    if any(token not in {".", *map(str, range(1, 9))} for row in rows for token in row):
        raise ValueError("Islands cells must be '.' or a number from 1 to 8")
    islands = {
        (row, col): int(token)
        for row, values in enumerate(rows)
        for col, token in enumerate(values)
        if token != "."
    }
    if len(islands) < 2:
        raise ValueError("Bridges needs at least two islands")
    return Puzzle(height, width, islands, neighbours(islands))


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """Pair multiplicities, reified bridge units, island counts and connectivity."""
    puzzle = parse(text)
    model = Model()
    units: dict[Pair, tuple[int, int]] = {}
    for pair in puzzle.pairs:
        name = pair_name(pair)
        model.constrain(
            f"{name} has zero, one or two bridges",
            Kind.EXACTLY_ONE,
            [model.literal(name, count) for count in range(3)],
            defines=name,
            family="at most two bridges between neighbouring islands",
        )
        thresholds = []
        for threshold in (1, 2):
            auxiliary = f"{name} at least {threshold}"
            present = model.literal(auxiliary, True)
            model.constrain(
                f"{auxiliary} is true or false",
                Kind.EXACTLY_ONE,
                [present, model.literal(auxiliary, False)],
                defines=auxiliary,
                hidden=True,
                family="bridge multiplicity indicators",
            )
            model.constrain(
                f"{auxiliary} matches its bridge count",
                Kind.COUNT,
                [model.literal(name, count) for count in range(threshold, 3)],
                allowed_counts=(1,),
                reified_by=present,
                family="bridge multiplicity indicators",
            )
            thresholds.append(present)
        units[pair] = thresholds[0], thresholds[1]
    for island, count in puzzle.islands.items():
        model.constrain(
            f"island {cell_name(island)} has {count} bridges",
            Kind.COUNT,
            [unit for pair in puzzle.pairs if island in pair for unit in units[pair]],
            allowed_counts=(count,),
            family="each island has its numbered bridge count",
        )
    for first, second in puzzle.crossings():
        a, b = puzzle.pairs[first], puzzle.pairs[second]
        model.constrain(
            f"{pair_name(a)} and {pair_name(b)} cannot cross",
            Kind.AT_MOST_ONE,
            [units[a][0], units[b][0]],
            family="bridges never cross",
        )
    model.connect(
        "all islands form one connected network",
        {cell_name(island): None for island in puzzle.islands},
        [(cell_name(pair[0]), cell_name(pair[1]), units[pair][0]) for pair in puzzle.pairs],
        family="all islands form one connected network",
    )
    return model, puzzle


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Island numbers and single/double bridge corridors in a text board."""
    grid = [[" " for _ in range(puzzle.width * 3)] for _ in range(puzzle.height * 2)]
    for pair in puzzle.pairs:
        count = model.chosen(pair_name(pair))
        if not count:
            continue
        a, b = pair
        if a[0] == b[0]:
            for column in range(a[1] * 3 + 1, b[1] * 3):
                grid[a[0] * 2][column] = "-" if count == 1 else "="
        else:
            for row in range(a[0] * 2 + 1, b[0] * 2):
                grid[row][a[1] * 3] = "|" if count == 1 else "H"
    for (row, col), count in puzzle.islands.items():
        grid[row * 2][col * 3] = str(count)
    return "\n".join([f"\n{title}", *("".join(row).rstrip() for row in grid[:-1])])
