"""Murdoku expressed as exact cover, count constraints, and relations.

The variables are *people*, not squares: each person picks one square. That
is the shape the puzzle actually has: at most one figure per row and column.
When the number of people matches the board width, every row and column is
occupied; on larger boards, some may stay empty.

Literals are "person stands on square". The constraint families:
  * each person stands on exactly one square
  * each square holds at most one person   (many squares stay empty)
  * each row holds exactly one person
  * each column holds exactly one person

Positional clues then either delete literals outright ("Jos is in the
kitchen") or become relations between two or three people ("Jos is left of
Otto", "Luna is furthest from Mao").
"""

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from .core import Kind, Model, Step

RESET = "\033[0m"
BOLD = "\033[1m"
INK = "\033[38;5;233m"
NEW = "\033[38;5;21m"  # blue: changed by the step just shown
FADED = "\033[38;5;245m"
# Pastel backgrounds, in the spirit of the printed board.
PALETTE = [217, 223, 157, 183, 153, 158, 222, 211, 195]


def _bg(colour: int) -> str:
    return f"\033[48;5;{colour}m"


@dataclass(frozen=True, order=True)
class Square:
    row: int
    col: int

    def __str__(self) -> str:
        return f"r{self.row + 1}c{self.col + 1}"

    __repr__ = __str__


def steps_between(a: Square, b: Square) -> int:
    """Orthogonal step count, as the puzzle counts distance."""
    return abs(a.row - b.row) + abs(a.col - b.col)


def knight_move(a: Square, b: Square) -> bool:
    """Two squares straight, then one to the side."""
    return {abs(a.row - b.row), abs(a.col - b.col)} == {1, 2}


type ObjectKind = Literal["blocking", "standable"]
type EdgeItemKind = Literal["door", "window"]
type OccupantCondition = Literal["alone", "not_alone"]


@dataclass(frozen=True)
class BoardObject:
    """One connected footprint of a named object type and explicit occupancy kind."""

    name: str
    kind: ObjectKind
    squares: tuple[Square, ...]

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError(f"object name {self.name!r} must be a single token")
        if self.kind not in ("blocking", "standable"):
            raise ValueError(f"object {self.name!r} kind must be 'blocking' or 'standable'")
        cells = set(self.squares)
        if not cells:
            raise ValueError(f"object {self.name!r} needs at least one cell")
        if len(cells) != len(self.squares):
            raise ValueError(f"object {self.name!r} footprint repeats a cell")
        reached = {next(iter(cells))}
        pending = list(reached)
        while pending:
            square = pending.pop()
            for neighbor in (
                Square(square.row - 1, square.col),
                Square(square.row + 1, square.col),
                Square(square.row, square.col - 1),
                Square(square.row, square.col + 1),
            ):
                if neighbor in cells and neighbor not in reached:
                    reached.add(neighbor)
                    pending.append(neighbor)
        if reached != cells:
            raise ValueError(f"object {self.name!r} footprint must be connected")


@dataclass(frozen=True)
class EdgeItem:
    """A referenceable boundary item represented by the cells it touches."""

    name: str
    kind: EdgeItemKind
    cells: tuple[Square, ...]

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError(f"edge item name {self.name!r} must be a single token")
        if self.kind not in ("door", "window"):
            raise ValueError(f"edge item {self.name!r} kind must be 'door' or 'window'")
        if self.kind == "door" and len(self.cells) != 2:
            raise ValueError(f"door {self.name!r} must touch exactly two neighboring cells")
        if self.kind == "window" and len(self.cells) != 1:
            raise ValueError(f"window {self.name!r} must list exactly one inside cell")
        if len(set(self.cells)) != len(self.cells):
            raise ValueError(f"edge item {self.name!r} repeats a touched cell")


@dataclass(frozen=True)
class CornerObject:
    """An object anchored at the common corner of its four surrounding cells."""

    name: str
    cells: tuple[Square, ...]

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError(f"corner object name {self.name!r} must be a single token")
        cells = set(self.cells)
        if len(cells) != 4:
            raise ValueError(f"corner object {self.name!r} must list four cells around one corner")
        rows = {square.row for square in cells}
        cols = {square.col for square in cells}
        if (
            len(rows) != 2
            or len(cols) != 2
            or cells != {Square(row, col) for row in rows for col in cols}
        ):
            raise ValueError(f"corner object {self.name!r} cells must surround one grid corner")


@dataclass(frozen=True)
class CellMark:
    """A named set of marked cells and an optional condition on their occupants."""

    name: str
    cells: tuple[Square, ...]
    occupant_condition: OccupantCondition | None = None

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError(f"mark name {self.name!r} must be a single token")
        if not self.cells:
            raise ValueError(f"mark {self.name!r} needs at least one cell")
        if len(set(self.cells)) != len(self.cells):
            raise ValueError(f"mark {self.name!r} repeats a cell")
        if self.occupant_condition not in (None, "alone", "not_alone"):
            raise ValueError(f"mark {self.name!r} condition must be 'alone' or 'not_alone'")


@dataclass
class Board:
    """The fixed layout: regions, things on the board, and who is playing.

    `regions` holds a short region id per square (a letter, say) and
    `region_names` maps each id to its name. `objects` lists connected object
    footprints with explicit blocking or standable kinds. Multiple instances
    of one type may share a name. `edge_items` and `corner_objects` are named
    cell sets that occupy no square. `marks` are named cell sets that may
    overlap and optionally carry an occupant condition. `colours`
    (region id -> '#RRGGBB') and `hatched` (region ids) only affect pictures.

    `area_tags` map reusable tags to named regions. `rules` are clues that come
    with the board rather than the puzzle, such as "only Luna can be in the
    water"; they are not numbered.
    """

    size: int
    regions: list[list[str]]
    region_names: dict[str, str]
    objects: list[BoardObject]
    people: list[str]
    area_tags: dict[str, list[str]] = field(default_factory=dict)
    colours: dict[str, str] = field(default_factory=dict)
    hatched: set[str] = field(default_factory=set)
    rules: list["Clue"] = field(default_factory=list)
    edge_items: list[EdgeItem] = field(default_factory=list)
    corner_objects: list[CornerObject] = field(default_factory=list)
    marks: list[CellMark] = field(default_factory=list)
    free: list[Square] = field(init=False)
    borders: set[frozenset[str]] = field(init=False)

    def __post_init__(self) -> None:
        if not self.people or len(self.people) > self.size:
            raise ValueError(
                f"{len(self.people)} people on a {self.size}x{self.size} board; "
                f"the number of people must be between 1 and {self.size}"
            )
        names: dict[str, ObjectKind] = {}
        occupied: set[Square] = set()
        for obj in self.objects:
            if obj.name in names and names[obj.name] != obj.kind:
                raise ValueError(f"object type {obj.name!r} has conflicting kinds")
            names[obj.name] = obj.kind
            if any(
                square.row not in range(self.size) or square.col not in range(self.size)
                for square in obj.squares
            ):
                raise ValueError(f"object {obj.name!r} has a cell off the grid")
            if overlap := occupied & set(obj.squares):
                raise ValueError(f"objects overlap at {sorted(overlap)}")
            occupied.update(obj.squares)
        squares = [Square(r, c) for r in range(self.size) for c in range(self.size)]
        self.free = [sq for sq in squares if sq not in self.blocked]
        self.borders = {
            frozenset((self.region_of(sq), self.region_of(nb)))
            for sq in squares
            for nb in (Square(sq.row, sq.col + 1), Square(sq.row + 1, sq.col))
            if nb.row < self.size
            and nb.col < self.size
            and self.region_of(sq) != self.region_of(nb)
        }
        for tag, members in self.area_tags.items():
            if not tag or any(char.isspace() for char in tag):
                raise ValueError(f"area tag {tag!r} must be a single token")
            if tag in self.region_names or tag in self.region_names.values():
                raise ValueError(f"area tag {tag!r} conflicts with a region identifier or name")
            if not members:
                raise ValueError(f"area tag {tag!r} needs at least one region")
            self.region_ids(members)
        edge_kinds: dict[str, EdgeItemKind] = {}
        for item in self.edge_items:
            corner_names = {obj.name for obj in self.corner_objects}
            if item.name in self.object_names or item.name in corner_names:
                raise ValueError(f"edge item name {item.name!r} overlaps another item name")
            if item.name in edge_kinds and edge_kinds[item.name] != item.kind:
                raise ValueError(f"edge item {item.name!r} has conflicting kinds")
            edge_kinds[item.name] = item.kind
            if any(
                square.row not in range(self.size) or square.col not in range(self.size)
                for square in item.cells
            ):
                raise ValueError(f"edge item {item.name!r} is off the grid")
            if item.kind == "door":
                first, second = item.cells
                if steps_between(first, second) != 1:
                    raise ValueError(f"door {item.name!r} must touch neighboring cells")
                if self.region_of(first) == self.region_of(second):
                    raise ValueError(f"door {item.name!r} must be on an area boundary")
        object_names = self.object_names
        for corner in self.corner_objects:
            if corner.name in object_names or corner.name in edge_kinds:
                raise ValueError(f"corner object name {corner.name!r} overlaps another item name")
            if any(
                square.row not in range(self.size) or square.col not in range(self.size)
                for square in corner.cells
            ):
                raise ValueError(f"corner object {corner.name!r} is off the grid")
        mark_names: set[str] = set()
        for mark in self.marks:
            if mark.name in mark_names:
                raise ValueError(f"mark {mark.name!r} is defined more than once")
            mark_names.add(mark.name)
            if any(
                square.row not in range(self.size) or square.col not in range(self.size)
                for square in mark.cells
            ):
                raise ValueError(f"mark {mark.name!r} has a cell off the grid")

    def region_of(self, square: Square) -> str:
        return self.regions[square.row][square.col]

    def region_id(self, name: str) -> str:
        for rid, rname in self.region_names.items():
            if rname == name:
                return rid
        raise ValueError(f"unknown region {name!r}; have {sorted(self.region_names.values())}")

    def region_ids(self, names: Iterable[str]) -> set[str]:
        """Region ids for named regions; disconnected cells share the same id."""
        return {self.region_id(name) for name in names}

    def tagged_region_ids(self, tags: Iterable[str]) -> set[str]:
        """Region ids carrying any of the named area tags."""
        tags = set(tags)
        unknown = tags - set(self.area_tags)
        if unknown:
            raise ValueError(f"unknown area tags {sorted(unknown)}; have {sorted(self.area_tags)}")
        return {self.region_id(region) for tag in tags for region in self.area_tags[tag]}

    def area_ids(self, names: Iterable[str]) -> set[str]:
        """Region ids named directly or through an area tag, for area-wide styling."""
        ids: set[str] = set()
        for name in names:
            if name in self.area_tags:
                ids.update(self.tagged_region_ids([name]))
            else:
                ids.add(self.region_id(name))
        return ids

    def regions_touch(self, a: str, b: str) -> bool:
        """Share a side somewhere; a shared corner does not count."""
        return frozenset((a, b)) in self.borders

    @property
    def blocked(self) -> set[Square]:
        return {square for obj in self.objects if obj.kind == "blocking" for square in obj.squares}

    @property
    def object_names(self) -> set[str]:
        return {obj.name for obj in self.objects}

    @property
    def edge_item_names(self) -> set[str]:
        return {item.name for item in self.edge_items}

    @property
    def corner_object_names(self) -> set[str]:
        return {item.name for item in self.corner_objects}

    @property
    def mark_names(self) -> set[str]:
        return {mark.name for mark in self.marks}

    @property
    def standable_objects(self) -> list[BoardObject]:
        return [obj for obj in self.objects if obj.kind == "standable"]

    def squares_of(self, names: Iterable[str]) -> set[Square]:
        """Every square occupied by an object of one of these types."""
        names = set(names)
        unknown = names - self.object_names
        if unknown:
            raise ValueError(
                f"nothing called {sorted(unknown)} on the board; have {sorted(self.object_names)}"
            )
        return {square for obj in self.objects if obj.name in names for square in obj.squares}

    def edge_item_cells(self, names: Iterable[str]) -> set[Square]:
        """Cells touched by named doors or windows."""
        names = set(names)
        unknown = names - self.edge_item_names
        if unknown:
            raise ValueError(
                f"unknown edge items {sorted(unknown)}; have {sorted(self.edge_item_names)}"
            )
        return {cell for item in self.edge_items if item.name in names for cell in item.cells}

    def edge_item_kind(self, name: str) -> EdgeItemKind:
        """The kind shared by all simple edge items with this reference name."""
        if name not in self.edge_item_names:
            raise ValueError(f"unknown edge item {name!r}; have {sorted(self.edge_item_names)}")
        return next(item.kind for item in self.edge_items if item.name == name)

    def corner_object_cells(self, names: Iterable[str]) -> set[Square]:
        """Cells surrounding named corner-anchored objects."""
        names = set(names)
        unknown = names - self.corner_object_names
        if unknown:
            raise ValueError(
                f"unknown corner objects {sorted(unknown)}; have {sorted(self.corner_object_names)}"
            )
        return {cell for item in self.corner_objects if item.name in names for cell in item.cells}

    def mark_cells(self, names: Iterable[str]) -> set[Square]:
        """Cells carrying any of the named marks."""
        names = set(names)
        unknown = names - self.mark_names
        if unknown:
            raise ValueError(f"unknown marks {sorted(unknown)}; have {sorted(self.mark_names)}")
        return {cell for mark in self.marks if mark.name in names for cell in mark.cells}


# --- clue vocabulary ------------------------------------------------------
# A filter narrows one person's squares; a relation links two people's.
# Each builder takes the board plus the clue's extra words.

type Clue = tuple[str, list[str]]
type SquareTest = Callable[[Square], bool]
type PairTest = Callable[[Square, Square], bool]


def _in_region(board: Board, *names: str) -> SquareTest:
    ids = board.region_ids(names)
    return lambda sq: board.region_of(sq) in ids


def _outside(board: Board, *names: str) -> SquareTest:
    ids = board.region_ids(names)
    return lambda sq: board.region_of(sq) not in ids


def _in_tagged(board: Board, *tags: str) -> SquareTest:
    ids = board.tagged_region_ids(tags)
    return lambda sq: board.region_of(sq) in ids


def _at(board: Board, *items: str) -> SquareTest:
    cells = board.edge_item_cells(items)
    return lambda square: square in cells


def _not_in_tagged(board: Board, *tags: str) -> SquareTest:
    ids = board.tagged_region_ids(tags)
    return lambda sq: board.region_of(sq) not in ids


def _on_mark(board: Board, *names: str) -> SquareTest:
    cells = board.mark_cells(names)
    return lambda square: square in cells


def _not_on_mark(board: Board, *names: str) -> SquareTest:
    cells = board.mark_cells(names)
    return lambda square: square not in cells


def _next_to(board: Board, *things: str) -> SquareTest:
    """Beside objects in the same area, or on a boundary/corner item's cells."""
    targets: set[Square] = set()
    touched: set[Square] = set()
    for thing in things:
        if thing in board.edge_item_names:
            touched.update(board.edge_item_cells([thing]))
        elif thing in board.corner_object_names:
            touched.update(board.corner_object_cells([thing]))
        else:
            targets.update(board.squares_of([thing]))

    def test(square: Square) -> bool:
        beside_thing = any(
            steps_between(square, target) == 1
            and board.region_of(target) == board.region_of(square)
            for target in targets
        )
        return square in touched or beside_thing

    return test


def _knight_from(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: any(knight_move(sq, t) for t in targets)


def _not_next_to(board: Board, *things: str) -> SquareTest:
    beside = _next_to(board, *things)
    return lambda sq: not beside(sq)


def _on(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: sq in targets


def _not_on(board: Board, *things: str) -> SquareTest:
    targets = board.squares_of(things)
    return lambda sq: sq not in targets


def _in_corner(board: Board) -> SquareTest:
    corners = {
        Square(0, 0),
        Square(0, board.size - 1),
        Square(board.size - 1, 0),
        Square(board.size - 1, board.size - 1),
    }
    return lambda sq: sq in corners


def _same_region(board: Board) -> PairTest:
    return lambda a, b: board.region_of(a) == board.region_of(b)


def _different_region(board: Board) -> PairTest:
    return lambda a, b: board.region_of(a) != board.region_of(b)


def _apart(board: Board) -> PairTest:
    def test(a: Square, b: Square) -> bool:
        ra, rb = board.region_of(a), board.region_of(b)
        return ra != rb and not board.regions_touch(ra, rb)

    return test


def _left_of(board: Board, columns: str | None = None) -> PairTest:
    if columns is not None:
        gap = int(columns)
        if gap < 1:
            raise ValueError("left_of column gap must be at least 1")
        return lambda a, b: a.col + gap == b.col
    return lambda a, b: a.col < b.col


def _above(board: Board, rows: str | None = None) -> PairTest:
    if rows is None:
        return lambda a, b: a.row < b.row
    gap = int(rows)
    return lambda a, b: a.row + gap == b.row


def _within(board: Board, steps: str) -> PairTest:
    limit = int(steps)
    return lambda a, b: steps_between(a, b) <= limit


def _at_least(board: Board, steps: str) -> PairTest:
    limit = int(steps)
    return lambda a, b: steps_between(a, b) >= limit


FILTERS: dict[str, Callable[..., SquareTest]] = {
    "in_region": _in_region,  # in_region <person> <region>...
    "outside": _outside,  # outside <person> <region>...
    "in_tagged": _in_tagged,  # in_tagged <person> <area tag>...
    "only_in_tagged": _in_tagged,  # only_in_tagged <person> <area tag>...
    "not_in_tagged": _not_in_tagged,  # not_in_tagged <person> <area tag>...
    "on_mark": _on_mark,  # on_mark <person> <mark>...
    "not_on_mark": _not_on_mark,  # not_on_mark <person> <mark>...
    "at": _at,  # at <person> <edge item>...
    "next_to": _next_to,  # next_to <person> <thing>...: beside any of them
    "not_next_to": _not_next_to,  # not_next_to <person> <thing>...: beside none of them
    "knight_from": _knight_from,  # knight_from <person> <thing>...: a knight's move away
    "on": _on,  # on <person> <standable object>...
    "not_on": _not_on,  # not_on <person> <standable object>...
    "in_corner": _in_corner,  # in_corner <person>
}

RELATIONS: dict[str, Callable[..., PairTest]] = {
    # No "two people side by side": with one person per row and column it never holds.
    "same_region": _same_region,  # same_region <a> <b>
    "different_region": _different_region,  # different_region <a> <b>
    "apart": _apart,  # apart <a> <b>: different regions that do not border
    "left_of": _left_of,  # left_of <a> <b> [n]: somewhere left, or exactly n columns left
    "above": _above,  # above <a> <b> [n]: exactly n rows above, or anywhere above
    "within": _within,  # within <a> <b> <n>: at most n steps apart
    "at_least": _at_least,  # at_least <a> <b> <n>: at least n steps apart
}

# Clues about everyone else, expanded to one relation per other person.
GROUP_CLUES = {
    "alone": 1,  # alone <a>: nobody else in a's region
    "furthest": 2,  # furthest <a> <b>: a strictly further from b than anyone
}

# exactly <n> <clue> ; <clue> ...: exactly n of the listed clues hold. Each
# listed clue is a filter or a relation; together they may name at most
# COUNTED_PEOPLE people, since the engine tries every combination of their squares.
COUNTING = "exactly"
COUNTED_PEOPLE = 3


def counted(args: Sequence[str]) -> tuple[int, list[Clue]]:
    """A counting clue's arguments: '2 next_to Tim boom ; left_of Jos Otto'
    -> (2, [('next_to', ['Tim', 'boom']), ('left_of', ['Jos', 'Otto'])])."""
    if not args or not args[0].isdigit():
        raise ValueError(f"{COUNTING} needs a count first, as in '{COUNTING} 1 <clue> ; <clue>'")
    parts: list[Clue] = []
    words: list[str] = []
    for word in [*args[1:], ";"]:
        if word != ";":
            words.append(word)
        elif words:
            kind, *rest = words
            parts.append((kind, rest))
            words = []
    return int(args[0]), parts


@dataclass(frozen=True)
class Condition:
    """What one clue or board effect requires: `test(*squares)` of `people`.

    This is the puzzle's meaning, independent of how it is solved: the
    compiler turns it into the model, the brute-force checker tests it
    directly. `kind` and `args` are the clue it came from, `number` its
    place in the clue list (None for a board rule).
    """

    label: str
    people: tuple[str, ...]
    test: Callable[..., bool]
    kind: str = ""
    args: tuple[str, ...] = ()
    number: int | None = None


def conditions(board: Board, clues: Iterable[Clue]) -> list[Condition]:
    """Board rules, mark effects, and clues as predicates over their people."""
    out: list[Condition] = []
    for kind, args in board.rules:
        out += _conditions(board, kind, args, None)
    out.extend(
        _mark_occupant_condition(board, mark) for mark in board.marks if mark.occupant_condition
    )
    for number, (kind, args) in enumerate(clues, 1):
        out += _conditions(board, kind, args, number)
    return out


def _mark_occupant_condition(board: Board, mark: CellMark) -> Condition:
    """The mark's occupant rule as one independent all-person predicate."""
    assert mark.occupant_condition is not None
    marked = set(mark.cells)
    regions = {board.region_of(square) for square in mark.cells}
    allowed = _occupant_counts(mark.occupant_condition, len(board.people))

    def test(*squares: Square) -> bool:
        for region in regions:
            triggered = any(
                square in marked and board.region_of(square) == region for square in squares
            )
            occupants = sum(board.region_of(square) == region for square in squares)
            if triggered and occupants not in allowed:
                return False
        return True

    return Condition(
        f"mark {mark.name} occupant {mark.occupant_condition}",
        tuple(board.people),
        test,
        "occupant_condition",
        (mark.name, mark.occupant_condition),
    )


def _occupant_counts(condition: OccupantCondition, people_count: int) -> frozenset[int]:
    if condition == "alone":
        return frozenset((0, 1))
    return frozenset(range(2, people_count + 1))


def _auxiliary_variable(model: Model, prefix: str) -> str:
    name = f"__{prefix}"
    suffix = 2
    while name in model.variables:
        name = f"__{prefix}_{suffix}"
        suffix += 1
    return name


def apply_occupant_condition(
    model: Model,
    name: str,
    trigger_literals: Iterable[int],
    occupant_literals: Iterable[int],
    allowed_counts: Iterable[int],
) -> None:
    """Require an occupant count only when at least one trigger literal holds.

    Cell marks use this helper; other occupancy effects can share the same
    trigger/count interface instead of adding a separate rule system.
    """
    triggers = tuple(dict.fromkeys(trigger_literals))
    occupants = tuple(dict.fromkeys(occupant_literals))
    allowed = frozenset(allowed_counts)
    if not triggers:
        return
    if not allowed:
        model.constrain(
            f"{name} cannot be satisfied",
            Kind.COUNT,
            triggers,
            allowed_counts={0},
            family="conditional occupancy",
        )
        return

    trigger_var = _auxiliary_variable(model, "occupant_trigger")
    active = model.literal(trigger_var, True)
    inactive = model.literal(trigger_var, False)
    model.constrain(
        f"{name} trigger state",
        Kind.EXACTLY_ONE,
        [active, inactive],
        defines=trigger_var,
        family="conditional occupancy",
    )
    model.constrain(
        f"{name} trigger count",
        Kind.COUNT,
        triggers,
        allowed_counts=range(1, len(triggers) + 1),
        reified_by=active,
        family="conditional occupancy",
    )

    condition_var = _auxiliary_variable(model, "occupant_condition")
    valid = model.literal(condition_var, True)
    invalid = model.literal(condition_var, False)
    model.constrain(
        f"{name} condition state",
        Kind.EXACTLY_ONE,
        [valid, invalid],
        defines=condition_var,
        family="conditional occupancy",
    )
    model.constrain(
        f"{name} occupant count",
        Kind.COUNT,
        occupants,
        allowed_counts=allowed,
        reified_by=valid,
        family="conditional occupancy",
    )
    model.constrain(
        f"{name} applies only when triggered",
        Kind.AT_MOST_ONE,
        [active, invalid],
        family="conditional occupancy",
    )


def _conditions(board: Board, kind: str, args: list[str], number: int | None) -> list[Condition]:
    if kind == COUNTING:
        return [_counting(board, args, number)]
    if kind == "at":
        if len(args) < 2:
            raise ValueError("clue 'at' expects a person and at least one edge item")
        person, *items = args
        if person not in board.people:
            raise ValueError(f"clue 'at {' '.join(args)}' names unknown person {person!r}")
        board.edge_item_cells(items)
    if kind in ("on_mark", "not_on_mark"):
        if len(args) < 2:
            raise ValueError(f"clue {kind!r} expects a person and at least one mark")
        board.mark_cells(args[1:])
    if kind in ("on", "not_on"):
        if len(args) < 2:
            raise ValueError(f"clue {kind!r} expects a person and at least one object")
        person, *names = args
        if person not in board.people:
            raise ValueError(f"clue {kind!r} names unknown person {person!r}")
        _validate_standable_objects(board, kind, names)
    if kind == "only_on":
        if len(args) < 2:
            raise ValueError("only_on needs a person and at least one standable object")
        person, *objects = args
        if person not in board.people:
            raise ValueError(f"clue only_on {' '.join(args)} names unknown person {person!r}")
        _validate_standable_objects(board, kind, objects)
        targets = board.squares_of(objects)
        label = " ".join([kind, *args])
        conditions = [
            Condition(label, (person,), lambda sq: sq in targets, kind, tuple(args), number)
        ]
        conditions.extend(
            Condition(label, (other,), lambda sq: sq not in targets, kind, tuple(args), number)
            for other in board.people
            if other != person
        )
        return conditions
    arity = 1 if kind in FILTERS else 2 if kind in RELATIONS else GROUP_CLUES.get(kind)
    if arity is None:
        raise ValueError(f"unknown clue {kind!r}")
    for who in args[:arity]:
        if who not in board.people:
            raise ValueError(f"clue {kind} {' '.join(args)} names unknown person {who!r}")

    def made(label: str, people: tuple[str, ...], test: Callable[..., bool]) -> Condition:
        return Condition(label, people, test, kind, tuple(args), number)

    if kind in FILTERS:
        person, *rest = args
        return [made(" ".join([kind, *args]), (person,), FILTERS[kind](board, *rest))]
    if kind in RELATIONS:
        a, b, *rest = args
        return [made(" ".join([a, kind, b, *rest]), (a, b), RELATIONS[kind](board, *rest))]
    if kind == "alone":
        (a,) = args
        return [
            made(f"{a} alone in region, so not with {p}", (a, p), _different_region(board))
            for p in board.people
            if p != a
        ]
    a, b = args
    return [
        made(f"{a} further from {b} than {p}", (a, b, p), _further)
        for p in board.people
        if p not in (a, b)
    ]


def _validate_standable_objects(board: Board, clue: str, names: Sequence[str]) -> None:
    unknown = set(names) - board.object_names
    if unknown:
        raise ValueError(f"clue {clue!r} names unknown objects {sorted(unknown)}")
    blocking = {obj.name for obj in board.objects if obj.name in names and obj.kind == "blocking"}
    if blocking:
        raise ValueError(f"clue {clue!r} needs standable objects; {sorted(blocking)} are blocking")


def _further(a: Square, b: Square, other: Square) -> bool:
    return steps_between(a, b) > steps_between(other, b)


def _counting(board: Board, args: list[str], number: int | None) -> Condition:
    """One condition over everyone the listed clues name: exactly n of them hold."""
    n, parts = counted(args)
    if not 0 <= n <= len(parts):
        raise ValueError(f"{COUNTING} {n} of {len(parts)} clues can never hold")
    subs: list[Condition] = []
    for kind, rest in parts:
        if kind not in FILTERS and kind not in RELATIONS:
            raise ValueError(f"{COUNTING} can count simple clues only, not {kind!r}")
        (sub,) = _conditions(board, kind, rest, None)
        subs.append(sub)
    people = tuple(dict.fromkeys(p for sub in subs for p in sub.people))
    if len(people) > COUNTED_PEOPLE:
        raise ValueError(
            f"{COUNTING} names {len(people)} people; at most {COUNTED_PEOPLE} are supported"
        )

    def test(*squares: Square) -> bool:
        at = dict(zip(people, squares, strict=True))
        return sum(sub.test(*(at[p] for p in sub.people)) for sub in subs) == n

    label = f"{COUNTING} {n} of: {'; '.join(sub.label for sub in subs)}"
    return Condition(label, people, test, COUNTING, tuple(args), number)


def compile_puzzle(board: Board, clues: Iterable[Clue]) -> Model:
    """The model for a Murdoku board and its clues.

    A condition on one person is applied straight away, ruling out squares
    that fail it. Clues about several people become relations; conditional
    mark effects are compiled to reified counts over their logical areas.
    """
    model = Model()
    _add_board_rules(model, board)
    for condition in conditions(board, clues):
        if condition.kind == "occupant_condition":
            (mark_name, _) = condition.args
            mark = next(mark for mark in board.marks if mark.name == mark_name)
            assert mark.occupant_condition is not None
            _compile_mark_occupant_condition(model, board, mark, mark.occupant_condition)
            continue
        if len(condition.people) == 1:
            (person,) = condition.people
            for sq in board.free:
                if not condition.test(sq):
                    model.eliminate(
                        model.literal(person, sq),
                        "clue",
                        condition.label,
                        sources=(condition.label,),
                    )
        else:
            model.relate(condition.label, condition.people, condition.test)
    return model


def _compile_mark_occupant_condition(
    model: Model, board: Board, mark: CellMark, condition: OccupantCondition
) -> None:
    marked = set(mark.cells)
    for region in sorted({board.region_of(square) for square in mark.cells}):
        triggers = [
            model.literal(person, square)
            for person in board.people
            for square in board.free
            if square in marked and board.region_of(square) == region
        ]
        occupants = [
            model.literal(person, square)
            for person in board.people
            for square in board.free
            if board.region_of(square) == region
        ]
        apply_occupant_condition(
            model,
            f"mark {mark.name} {condition} in {board.region_names[region]}",
            triggers,
            occupants,
            _occupant_counts(condition, len(board.people)),
        )


@dataclass(frozen=True)
class BoardRule:
    """One constraint every Murdoku has, and what it is `about`:
    ('person', name), ('square', Square), ('row', i) or ('col', i), 0-based.

    `compile_puzzle` builds the model from these, so a reader can look a
    constraint's meaning up by name instead of parsing the name.
    """

    name: str
    kind: Kind
    family: str
    about: tuple[str, Any]
    options: tuple[tuple[str, Square], ...]  # (person, square) pairs


def board_rules(board: Board) -> list[BoardRule]:
    people, free = board.people, board.free
    line_kind = Kind.EXACTLY_ONE if len(people) == board.size else Kind.AT_MOST_ONE
    line_capacity = "one person" if line_kind is Kind.EXACTLY_ONE else "at most one person"
    rules = [
        BoardRule(
            f"{p} stands somewhere",
            Kind.EXACTLY_ONE,
            "each person stands on one square",
            ("person", p),
            tuple((p, sq) for sq in free),
        )
        for p in people
    ]
    rules += [
        BoardRule(
            f"{sq} holds at most one",
            Kind.AT_MOST_ONE,
            "each square holds at most one person",
            ("square", sq),
            tuple((p, sq) for p in people),
        )
        for sq in free
    ]
    for line, word in (("row", "row"), ("col", "column")):
        rules += [
            BoardRule(
                f"{line} {i + 1} holds {line_capacity}",
                line_kind,
                f"each {word} holds {line_capacity}",
                (line, i),
                tuple(
                    (p, sq)
                    for p in people
                    for sq in free
                    if (sq.row if line == "row" else sq.col) == i
                ),
            )
            for i in range(board.size)
        ]
    return rules


def _add_board_rules(model: Model, board: Board) -> None:
    for rule in board_rules(board):
        person = rule.about[1] if rule.about[0] == "person" else None
        model.constrain(
            rule.name,
            rule.kind,
            [model.literal(p, sq) for p, sq in rule.options],
            defines=person,
            family=rule.family,
        )


# --- rendering ------------------------------------------------------------


def render(board: Board, model: Model, title: str, steps: Sequence[Step] = ()) -> str:
    """Draw the board, one colour per region, 4 columns per square.

    A square nobody can stand on any more is crossed out, as a person would
    on paper. `steps`, the deductions just made, are highlighted: people
    placed, squares newly crossed out, and whose options narrowed.
    """
    blocked = board.blocked
    standable = board.squares_of(obj.name for obj in board.standable_objects)
    reachable = _reachable(board, model)
    shade = {rid: PALETTE[i % len(PALETTE)] for i, rid in enumerate(board.region_names)}
    placed = {s.var for s in steps if s.asserted}
    eliminated = {s.value for s in steps if not s.asserted}
    at: dict[Square, str] = {}
    for person in board.people:
        square = model.chosen(person)
        if square is not None:
            at[square] = person
    finished = len(at) == len(board.people)  # crosses are a working aid; drop them at the end

    out = [f"\n{BOLD}{title}{RESET}"]
    out.append("   " + "".join(f"{c + 1:^4}" for c in range(board.size)))
    for r in range(board.size):
        line = f"{r + 1:>2} "
        for c in range(board.size):
            sq = Square(r, c)
            colour = _bg(shade[board.region_of(sq)])
            if sq in blocked:
                body = f"{INK} ## "
            elif sq in at:
                person = at[sq]
                tint = NEW if person in placed else INK
                body = f"{tint}{person[:3]:^4}"
            elif sq not in reachable and not finished:
                tint = f"{BOLD}{NEW}" if sq in eliminated else FADED
                body = f"{tint} x  "
            elif sq in standable:
                body = f"{INK} =  "
            else:
                body = f"{INK} .  "
            line += colour + body + RESET
        out.append(line)

    if not finished:
        open_count = len(reachable - set(at))
        empty_count = len(board.free) - len(at)
        out.append(f"\n  {open_count} of {empty_count} empty squares still possible for someone")
    out += _narrowed(board, model, steps)

    out.append("")
    for rid, name in board.region_names.items():
        swatch = _bg(shade[rid]) + "   " + RESET
        out.append(f"  {swatch} {name}")
    out.append(f"\n  {INK}##{RESET} blocking   =  standable   .  open   x  nobody can stand here")
    out.append(f"  {NEW}blue{RESET}: changed by this step")
    for kind in ("blocking", "standable"):
        by_name: dict[str, set[Square]] = {}
        for obj in board.objects:
            if obj.kind == kind:
                by_name.setdefault(obj.name, set()).update(obj.squares)
        if by_name:
            listed = ", ".join(
                f"{name} {' '.join(map(str, sorted(squares)))}"
                for name, squares in sorted(by_name.items())
            )
            out.append(f"  {kind}: {listed}")
    if board.edge_items:
        listed = ", ".join(
            f"{item.name} {item.kind} {' '.join(map(str, item.cells))}" for item in board.edge_items
        )
        out.append(f"  edge items: {listed}")
    if board.corner_objects:
        listed = ", ".join(
            f"{item.name} {' '.join(map(str, item.cells))}" for item in board.corner_objects
        )
        out.append(f"  corner objects: {listed}")
    if board.marks:
        listed = ", ".join(
            f"{mark.name} {' '.join(map(str, mark.cells))}"
            + (f" ; {mark.occupant_condition}" if mark.occupant_condition else "")
            for mark in board.marks
        )
        out.append(f"  marks: {listed}")
    return "\n".join(out)


def _reachable(board: Board, model: Model) -> set[Square]:
    """Squares at least one person can still stand on."""
    return {model.value_of(lit) for p in board.people for lit in model.options(p)}


def _narrowed(board: Board, model: Model, steps: Sequence[Step]) -> list[str]:
    """One line per open person who lost options in `steps`."""
    lost = Counter(s.var for s in steps if not s.asserted and model.chosen(s.var) is None)
    if not lost:
        return []
    lines = ["  narrowed by this step:"]
    for person in board.people:
        if person in lost:
            left = sorted(model.value_of(lit) for lit in model.options(person))
            listed = " ".join(map(str, left[:8])) + (" ..." if len(left) > 8 else "")
            lines.append(f"    {person:<9} -{lost[person]:<3} {len(left):>2} left: {listed}")
    return lines


def open_squares(board: Board, model: Model) -> dict[str, list[Square]]:
    """Remaining candidate squares per person - the working set."""
    return {p: sorted(model.value_of(lit) for lit in model.options(p)) for p in board.people}


def track_person_candidates(
    board: Board, model: Model, person: str
) -> tuple[list[Square], list[str]]:
    """Return a person's live squares and conservative region-overlap companions."""
    if person not in board.people:
        raise ValueError(f"unknown person {person!r}; have {board.people}")

    squares = open_squares(board, model)[person]
    regions = {board.region_of(square) for square in squares}
    companions = [
        candidate
        for candidate in board.people
        if candidate != person
        and any(board.region_of(model.value_of(lit)) in regions for lit in model.options(candidate))
    ]
    return squares, companions


def track_person_status(board: Board, model: Model, person: str) -> str:
    """Describe one person's live squares and region-overlap companions.

    Companion names are a conservative domain-overlap diagnostic, not a test
    that each person-square pair extends to a complete solution.
    """
    squares, companions = track_person_candidates(board, model, person)
    regions = {board.region_of(square) for square in squares}
    region_names = [name for rid, name in board.region_names.items() if rid in regions]

    chosen = model.chosen(person)
    if chosen is not None:
        location = f"{chosen} ({board.region_names[board.region_of(chosen)]})"
    elif not squares:
        location = "no live squares"
    elif len(squares) == 1:
        square = squares[0]
        location = f"1 square {square} ({board.region_names[board.region_of(square)]})"
    else:
        location = f"{len(squares)} squares in {', '.join(region_names)}"
        if len(squares) <= 8:
            location += f" [{', '.join(map(str, squares))}]"

    possible = ", ".join(companions) or "none"
    return f"  tracked {person}: {location}; region-overlap companions: {possible}"
