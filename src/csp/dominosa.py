"""Dominosa as pure exact cover over domino types and board edges.

A grid of numbers 0..N, N + 2 columns by N + 1 rows. Cover it with dominoes so
that every domino of the full set {0-0, 0-1, ..., N-N} is used exactly once.

    Family: dominosa
    Numbers:
    0 2 1 1
    ...

There is one variable per domino type; its values are the edges (two touching
cells) whose numbers match that type. Choosing a type's edge is the domain
constraint (exactly one edge per type), and each cell is covered exactly once:
EXACTLY_ONE over every (type, edge) literal that touches it.
"""

from collections.abc import Mapping, Sequence

from .core import Kind, Model, Step
from .puzzlefile import read_sections

type Cell = tuple[int, int]
type Edge = tuple[Cell, Cell]

MAXIMUM = range(1, 7)  # highest number on a domino: boards 2x3 up to 7x8

BOLD = "\033[1m"
NEW = "\033[38;5;21m"
RESET = "\033[0m"

# Where each cell of a placed domino sits, by the direction of its partner cell.
HALVES = {(0, 1): "left", (0, -1): "right", (1, 0): "top", (-1, 0): "bottom"}


def cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def type_name(low: int, high: int) -> str:
    return f"{low}-{high}"


def edge_name(edge: Edge) -> str:
    return f"{cell_name(edge[0])}-{cell_name(edge[1])}"


class Puzzle:
    def __init__(self, numbers: list[list[int]]) -> None:
        self.numbers = numbers
        self.rows = len(numbers)
        self.cols = len(numbers[0])
        self.top = self.rows - 1  # the highest number

    def edges(self) -> list[Edge]:
        """Every pair of touching cells, in reading order."""
        out: list[Edge] = []
        for r in range(self.rows):
            for c in range(self.cols):
                if c + 1 < self.cols:
                    out.append(((r, c), (r, c + 1)))
                if r + 1 < self.rows:
                    out.append(((r, c), (r + 1, c)))
        return out

    def kind_of(self, edge: Edge) -> tuple[int, int]:
        """The domino type an edge would be: its two numbers, smaller first."""
        (r0, c0), (r1, c1) = edge
        return tuple(sorted((self.numbers[r0][c0], self.numbers[r1][c1])))  # type: ignore[return-value]

    @property
    def types(self) -> list[tuple[int, int]]:
        return [(low, high) for low in range(self.top + 1) for high in range(low, self.top + 1)]


def parse(text: str) -> Puzzle:
    """Read a Dominosa file: `Numbers:` is (N+1) rows of N+2 numbers 0..N."""
    section = read_sections(text)
    for required in ("Family", "Numbers"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(section["Family"]) != 1 or section["Family"][0].casefold() != "dominosa":
        raise ValueError("Family must be 'dominosa'")
    rows = [line.split() for line in section["Numbers"]]
    top = len(rows) - 1
    if top not in MAXIMUM:
        raise ValueError(f"Numbers needs {MAXIMUM.start + 1} to {MAXIMUM[-1] + 1} rows")
    if any(len(row) != top + 2 for row in rows):
        raise ValueError(f"Numbers rows must each hold {top + 2} numbers for {top + 1} rows")
    numbers = []
    for row in rows:
        if bad := [t for t in row if not (t.isdigit() and int(t) <= top)]:
            raise ValueError(f"Numbers holds {bad[0]!r}; expected 0-{top}")
        numbers.append([int(t) for t in row])
    return Puzzle(numbers)


def compile_puzzle(text: str) -> tuple[Model, Puzzle]:
    """One variable per domino type, whose values are the edges it could occupy."""
    puzzle = parse(text)
    model = Model()
    by_type: dict[tuple[int, int], list[Edge]] = {kind: [] for kind in puzzle.types}
    for edge in puzzle.edges():
        by_type[puzzle.kind_of(edge)].append(edge)
    touching: dict[Cell, list[tuple[str, str]]] = {
        (r, c): [] for r in range(puzzle.rows) for c in range(puzzle.cols)
    }
    for kind, edges in by_type.items():
        name = type_name(*kind)
        if not edges:
            raise ValueError(f"domino {name} cannot be placed anywhere on this board")
        model.constrain(
            f"domino {name} goes in one place",
            Kind.EXACTLY_ONE,
            [model.literal(name, edge_name(edge)) for edge in edges],
            defines=name,
            family="each domino is used once",
        )
        for edge in edges:
            for cell in edge:
                touching[cell].append((name, edge_name(edge)))
    for cell, options in touching.items():
        model.constrain(
            f"{cell_name(cell)} is covered once",
            Kind.EXACTLY_ONE,
            [model.literal(name, value) for name, value in options],
            family="each cell is covered once",
        )
    return model, puzzle


def placed_edges(solution: Mapping[str, str]) -> list[Edge]:
    """The edges a solution (domino type to edge name) uses, as cell pairs."""
    edges: list[Edge] = []
    for value in solution.values():
        first, second = value.split("-")
        edges.append((_cell(first), _cell(second)))
    return edges


def _cell(name: str) -> Cell:
    row, col = name[1:].split("c")
    return int(row) - 1, int(col) - 1


def cell_assignment(solution: Mapping[str, str]) -> dict[str, str]:
    """Which half of its domino each cell is: `left`, `right`, `top` or `bottom`."""
    out: dict[str, str] = {}
    for first, second in placed_edges(solution):
        out[cell_name(first)] = HALVES[second[0] - first[0], second[1] - first[1]]
        out[cell_name(second)] = HALVES[first[0] - second[0], first[1] - second[1]]
    return out


def render(puzzle: Puzzle, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """The numbers, with `-` and `|` joining a pair once that edge is placed."""
    changed = {step.var for step in steps if step.asserted}
    placed: dict[Edge, bool] = {}
    for edge in puzzle.edges():
        name = type_name(*puzzle.kind_of(edge))
        chosen = model.chosen(name)
        placed[edge] = chosen == edge_name(edge)
    out = [f"\n{BOLD}{title}{RESET}"]
    for r in range(puzzle.rows):
        line = ""
        for c in range(puzzle.cols):
            line += str(puzzle.numbers[r][c])
            if c + 1 < puzzle.cols:
                edge = ((r, c), (r, c + 1))
                line += _join(placed[edge], type_name(*puzzle.kind_of(edge)) in changed, "-")
        out.append(line)
        if r + 1 < puzzle.rows:
            below = ""
            for c in range(puzzle.cols):
                edge = ((r, c), (r + 1, c))
                below += _join(placed[edge], type_name(*puzzle.kind_of(edge)) in changed, "|") + " "
            out.append(below.rstrip())
    return "\n".join(out)


def _join(placed: bool, fresh: bool, mark: str) -> str:
    if not placed:
        return " "
    return f"{NEW}{mark}{RESET}" if fresh else mark
