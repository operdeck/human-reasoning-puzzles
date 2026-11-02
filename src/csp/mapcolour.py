"""Map (four colouring) compiled to one variable per region and "not both" constraints.

Colour every region of a map with one of four colours so that no two regions that
share a border have the same colour. Some regions come pre-coloured.

    Family: map
    Regions:
    a a b b
    a c c b
    d d c e
    Givens:
    a red
    c blue
    d green

`Regions:` is a grid of region ids; two regions touch where cells of the two share a side
(corners do not count). Each id must form one connected area. Colours are `red`, `yellow`,
`green` and `blue`. The module is named `mapcolour` so it never shadows the builtin `map`.
"""

from collections.abc import Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]

COLOURS = ("red", "yellow", "green", "blue")
BIGGEST = 12

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


class Puzzle:
    def __init__(self, grid: list[list[str]], givens: dict[str, str]) -> None:
        self.grid = grid
        self.rows = len(grid)
        self.cols = len(grid[0])
        self.givens = givens  # region id -> colour
        self.regions = list(dict.fromkeys(region for row in grid for region in row))

    def cells_of(self, region: str) -> list[Cell]:
        return [
            (r, c) for r in range(self.rows) for c in range(self.cols) if self.grid[r][c] == region
        ]

    @property
    def borders(self) -> list[tuple[str, str]]:
        """Every pair of regions that share a side of two cells, each listed once."""
        found: set[tuple[str, str]] = set()
        for r in range(self.rows):
            for c in range(self.cols):
                for dr, dc in ((0, 1), (1, 0)):
                    r2, c2 = r + dr, c + dc
                    if r2 < self.rows and c2 < self.cols:
                        a, b = self.grid[r][c], self.grid[r2][c2]
                        if a != b:
                            found.add((min(a, b), max(a, b)))
        return sorted(found)


def parse(text: str) -> Puzzle:
    """Read a Map file: a `Regions:` grid of ids and `Givens:` lines like `a red`."""
    section = read_sections(text)
    for required in ("Family", "Regions"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() not in {"map", "fourcolour"}:
        raise ValueError("Family must be 'map'")
    grid = [line.split() for line in section["Regions"]]
    if not 2 <= len(grid) <= BIGGEST or any(len(row) != len(grid[0]) for row in grid):
        raise ValueError(f"Regions must be a rectangular grid of 2 to {BIGGEST} rows")
    if not 2 <= len(grid[0]) <= BIGGEST:
        raise ValueError(f"Regions must have 2 to {BIGGEST} columns")
    puzzle = Puzzle(grid, {})
    for region in puzzle.regions:
        if not _connected(puzzle.cells_of(region)):
            raise ValueError(f"region {region!r} is not one connected area")
    givens: dict[str, str] = {}
    for line in section.get("Givens", []):
        parts = line.split()
        if len(parts) != 2 or parts[0] not in puzzle.regions or parts[1] not in COLOURS:
            raise ValueError(f"bad given {line!r}, expected '<region> <{'|'.join(COLOURS)}>'")
        if parts[0] in givens:
            raise ValueError(f"region {parts[0]!r} is given a colour twice")
        givens[parts[0]] = parts[1]
    for a, b in puzzle.borders:
        if givens.get(a) is not None and givens.get(a) == givens.get(b):
            raise ValueError(f"touching regions {a!r} and {b!r} are given the same colour")
    return Puzzle(grid, givens)


def _connected(cells: list[Cell]) -> bool:
    members, seen, todo = set(cells), set(), [cells[0]]
    while todo:
        r, c = todo.pop()
        if (r, c) in seen:
            continue
        seen.add((r, c))
        todo.extend(
            near
            for near in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1))
            if near in members and near not in seen
        )
    return seen == members


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """One four-colour variable per region; a border forbids the same colour on both sides."""
    puzzle = parse(text)
    model = Model()
    for region in puzzle.regions:
        model.constrain(
            f"region {region} has one colour",
            Kind.EXACTLY_ONE,
            [model.literal(region, colour) for colour in COLOURS],
            defines=region,
            family="each region has one colour",
        )
    for a, b in puzzle.borders:
        for colour in COLOURS:
            model.constrain(
                f"{a} and {b} are not both {colour}",
                Kind.AT_MOST_ONE,
                [model.literal(a, colour), model.literal(b, colour)],
                family="neighbouring regions differ",
            )
    # Givens last: `assign` only propagates through the constraints that already exist.
    for region, colour in puzzle.givens.items():
        model.assign(model.literal(region, colour), "given", "given")
    return model, puzzle


def cell_assignment(puzzle: Puzzle, solution: dict[str, str]) -> dict[str, str]:
    """Every cell's colour: that of its region, for the regions the solution colours."""
    return {
        cell_name(cell): solution[region]
        for region in puzzle.regions
        if region in solution
        for cell in puzzle.cells_of(region)
    }


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The region grid with each region's colour initial (or its id while still open)."""
    changed = {step.var for step in steps if step.asserted}
    width = max(len(region) for region in puzzle.regions) + 1
    out = [f"\n{BOLD}{title}{RESET}"]
    for r in range(puzzle.rows):
        marks = []
        for c in range(puzzle.cols):
            region = puzzle.grid[r][c]
            chosen = model.chosen(region)
            text = f"{region}={chosen[0].upper()}" if chosen else region
            marks.append(f"{NEW if region in changed else ''}{text:<{width + 2}}{RESET}")
        out.append(" ".join(marks))
    return "\n".join(out)
