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
from itertools import combinations
from typing import Any, Literal, cast

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
class PointObject:
    """An object on a grid point, touching the cells whose square contains that point.

    `anchor` is the point as doubled 1-based (row, col) coordinates, so that
    whole numbers on the half-step lattice stay integers: an even value is a
    cell centre line and an odd value a grid line (1 and 2N+1 are the outer
    edges). `r2.5c2.5` is `(5, 5)`. At least one coordinate lies on a grid line.
    """

    name: str
    anchor: tuple[int, int]
    cells: tuple[Square, ...]

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError(f"point object name {self.name!r} must be a single token")
        if not self.cells:
            raise ValueError(f"point object {self.name!r} touches no cell")

    @property
    def label(self) -> str:
        """The anchor as written in a puzzle file, such as `r2.5c4`."""
        return _anchor_label(self.anchor)

    @classmethod
    def at(cls, name: str, anchor: tuple[int, int], size: int) -> "PointObject":
        """The point object at a doubled anchor on a board of `size`, with its touched cells."""
        row2, col2 = anchor
        shown = _anchor_label(anchor)
        if not all(1 <= value <= 2 * size + 1 for value in anchor):
            raise ValueError(f"point object {name!r} at {shown} is off the board")
        if row2 % 2 == 0 and col2 % 2 == 0:
            raise ValueError(
                f"point object {name!r} at {shown} is a cell centre; use .5 for a grid line"
            )
        rows = _touched_lines(row2, size)
        cols = _touched_lines(col2, size)
        return cls(name, anchor, tuple(Square(row, col) for row in rows for col in cols))


def _anchor_label(anchor: tuple[int, int]) -> str:
    row2, col2 = anchor
    return f"r{row2 / 2:g}c{col2 / 2:g}"


def _touched_lines(doubled: int, size: int) -> list[int]:
    """0-based rows (or columns) whose cells contain the doubled 1-based coordinate."""
    if doubled % 2 == 0:
        return [doubled // 2 - 1]
    return [line for line in ((doubled - 3) // 2, (doubled - 1) // 2) if 0 <= line < size]


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


@dataclass(frozen=True)
class RoleSpec:
    """A data-defined role's allowed holder counts and optional eligibility."""

    name: str
    allowed_counts: frozenset[int]
    different_regions: bool = False
    eligible_people: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError(f"role name {self.name!r} must be a single token")
        if not self.allowed_counts:
            raise ValueError(f"role {self.name!r} needs at least one allowed count")


@dataclass(frozen=True)
class PronounSet:
    subject: str
    object: str
    possessive: str

    def __post_init__(self) -> None:
        forms = (self.subject, self.object, self.possessive)
        if any(not form or any(char.isspace() for char in form) for form in forms):
            raise ValueError("pronoun forms must each be one non-empty token")


@dataclass
class Board:
    """The fixed layout: regions, things on the board, and who is playing.

    `regions` holds a short region id per square (a letter, say) and
    `region_names` maps each id to its name. `objects` lists connected object
    footprints with explicit blocking or standable kinds. Multiple instances
    of one type may share a name. `edge_items` and `point_objects` are named
    cell sets that occupy no square. `marks` are named cell sets that may
    overlap and optionally carry an occupant condition. `colours`
    (region id -> '#RRGGBB') and `hatched` (region ids) only affect pictures.

    `area_tags` map reusable tags to named regions. `attributes` are fixed
    traits on named people, while `roles` are solver-managed memberships;
    `pronouns` are used only by worked-solution wording. `rules` are clues that
    come with the board rather than the puzzle, such as "only Luna can be in
    the water"; they are not numbered.
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
    point_objects: list[PointObject] = field(default_factory=list)
    marks: list[CellMark] = field(default_factory=list)
    roles: list[RoleSpec] = field(default_factory=list)
    attributes: dict[str, frozenset[str]] = field(default_factory=dict)
    pronouns: dict[str, PronounSet] = field(default_factory=dict)
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
            point_names = {obj.name for obj in self.point_objects}
            if item.name in self.object_names or item.name in point_names:
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
        for point in self.point_objects:
            if point.name in object_names or point.name in edge_kinds:
                raise ValueError(f"point object name {point.name!r} overlaps another item name")
            if any(
                square.row not in range(self.size) or square.col not in range(self.size)
                for square in point.cells
            ):
                raise ValueError(f"point object {point.name!r} is off the grid")
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
        role_names: set[str] = set()
        for role in self.roles:
            if role.name in role_names:
                raise ValueError(f"role {role.name!r} is defined more than once")
            role_names.add(role.name)
            if any(count < 0 or count > len(self.people) for count in role.allowed_counts):
                raise ValueError(
                    f"role {role.name!r} count must be between 0 and {len(self.people)}"
                )
            if role.eligible_people is not None:
                unknown = role.eligible_people - set(self.people)
                if unknown:
                    raise ValueError(
                        f"role {role.name!r} eligibility names unknown people {sorted(unknown)}"
                    )
        for attribute, holders in self.attributes.items():
            if not attribute or any(char.isspace() for char in attribute):
                raise ValueError(f"attribute {attribute!r} must be a single token")
            unknown = holders - set(self.people)
            if unknown:
                raise ValueError(f"attribute {attribute!r} names unknown people {sorted(unknown)}")
        for person in self.pronouns:
            if person not in self.people:
                raise ValueError(f"pronouns name unknown person {person!r}")

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
    def point_object_names(self) -> set[str]:
        return {item.name for item in self.point_objects}

    @property
    def mark_names(self) -> set[str]:
        return {mark.name for mark in self.marks}

    @property
    def role_names(self) -> set[str]:
        return {role.name for role in self.roles}

    def role_variable(self, person: str, role: str) -> str:
        if person not in self.people:
            raise ValueError(f"unknown person {person!r}; have {self.people}")
        if role not in self.role_names:
            raise ValueError(f"unknown role {role!r}; have {sorted(self.role_names)}")
        return f"{person} has role {role}"

    @property
    def attribute_names(self) -> set[str]:
        return set(self.attributes)

    def has_attribute(self, person: str, attribute: str) -> bool:
        if person not in self.people:
            raise ValueError(f"unknown person {person!r}; have {self.people}")
        if attribute not in self.attributes:
            raise ValueError(
                f"unknown attribute {attribute!r}; have {sorted(self.attribute_names)}"
            )
        return person in self.attributes[attribute]

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

    def point_object_cells(self, names: Iterable[str]) -> set[Square]:
        """Cells surrounding named corner-anchored objects."""
        names = set(names)
        unknown = names - self.point_object_names
        if unknown:
            raise ValueError(
                f"unknown point objects {sorted(unknown)}; have {sorted(self.point_object_names)}"
            )
        return {cell for item in self.point_objects if item.name in names for cell in item.cells}

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
        elif thing in board.point_object_names:
            touched.update(board.point_object_cells([thing]))
        elif thing in board.mark_names:
            targets.update(board.mark_cells([thing]))
        elif thing in ("blocking", "standable"):
            targets.update(
                square for obj in board.objects if obj.kind == thing for square in obj.squares
            )
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


def _in_row(board: Board, row: str) -> SquareTest:
    index = int(row) - 1
    if index not in range(board.size):
        raise ValueError(f"row must be between 1 and {board.size}")
    return lambda square: square.row == index


def _not_in_row(board: Board, row: str) -> SquareTest:
    in_row = _in_row(board, row)
    return lambda square: not in_row(square)


def _in_column(board: Board, column: str) -> SquareTest:
    index = int(column) - 1
    if index not in range(board.size):
        raise ValueError(f"column must be between 1 and {board.size}")
    return lambda square: square.col == index


def _not_in_column(board: Board, column: str) -> SquareTest:
    in_column = _in_column(board, column)
    return lambda square: not in_column(square)


def _in_area_corner(board: Board, *areas: str) -> SquareTest:
    """Cells where the area boundary turns through a right angle."""
    region_ids = board.area_ids(areas) if areas else set(board.region_names)
    directions = ((-1, 0), (1, 0), (0, -1), (0, 1))
    corners: set[Square] = set()
    for row in range(board.size):
        for col in range(board.size):
            square = Square(row, col)
            region = board.region_of(square)
            if region not in region_ids:
                continue
            missing = {
                direction
                for direction in directions
                if (neighbor := Square(row + direction[0], col + direction[1])).row
                not in range(board.size)
                or neighbor.col not in range(board.size)
                or board.region_of(neighbor) != region
            }
            if any(a[0] != b[0] and a[1] != b[1] for a, b in combinations(missing, 2)):
                corners.add(square)
    return corners.__contains__


def _same_region(board: Board) -> PairTest:
    return lambda a, b: board.region_of(a) == board.region_of(b)


def _different_region(board: Board) -> PairTest:
    return lambda a, b: board.region_of(a) != board.region_of(b)


def _adjacent_regions(board: Board) -> PairTest:
    return lambda a, b: (
        board.region_of(a) != board.region_of(b)
        and board.regions_touch(board.region_of(a), board.region_of(b))
    )


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
    "in_row": _in_row,  # in_row <person> <1-based row>
    "not_in_row": _not_in_row,  # not_in_row <person> <1-based row>
    "in_column": _in_column,  # in_column <person> <1-based column>
    "not_in_column": _not_in_column,  # not_in_column <person> <1-based column>
    "in_area_corner": _in_area_corner,  # in_area_corner <person> [area ...]
}

RELATIONS: dict[str, Callable[..., PairTest]] = {
    # No "two people side by side": with one person per row and column it never holds.
    "same_region": _same_region,  # same_region <a> <b>
    "different_region": _different_region,  # different_region <a> <b>
    "adjacent_regions": _adjacent_regions,  # adjacent_regions <a> <b>
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
GLOBAL_COUNTING = "count"
COUNTED_PEOPLE = 3
ATTRIBUTE_FILTERS = frozenset(("has_attribute", "not_attribute"))


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


@dataclass(frozen=True)
class RoleCondition:
    """A generic role constraint from a board rule or numbered clue."""

    label: str
    kind: str
    args: tuple[str, ...]
    number: int | None = None


type TargetKind = Literal[
    "person",
    "attribute",
    "role",
    "area",
    "tag",
    "object_kind",
    "object",
    "mark",
    "edge_item",
    "point_object",
    "rows",
    "columns",
]


@dataclass(frozen=True)
class TargetSelector:
    kind: TargetKind
    name: str


type GlobalCountKind = Literal[
    "people_on", "people_in", "people_with", "empty_areas", "empty_cells"
]


@dataclass(frozen=True)
class GlobalCountCondition:
    """A count over named people, cells, or logical areas on the whole board."""

    label: str
    kind: GlobalCountKind
    selector: TargetSelector | None
    comparison: str
    operands: tuple[int, ...]
    allowed_counts: frozenset[int]
    number: int | None
    index: int
    tokens: tuple[str, ...]

    @property
    def description(self) -> str:
        return " ".join((GLOBAL_COUNTING, *self.tokens))

    def cells(self, board: Board) -> set[Square]:
        if self.selector is None:
            return set()
        return _selector_cells(board, self.selector) & set(board.free)

    def scope_cells(self, board: Board) -> set[Square]:
        if self.kind == "empty_areas":
            regions = self.regions(board)
            return {square for square in board.free if board.region_of(square) in regions}
        if self.kind == "people_with":
            return set()
        return self.cells(board)

    def regions(self, board: Board) -> set[str]:
        if self.selector is None:
            return set(board.region_names)
        if self.selector.kind == "area":
            return board.area_ids([self.selector.name])
        if self.selector.kind == "tag":
            return board.tagged_region_ids([self.selector.name])
        raise ValueError(f"selector {self.selector.kind!r} does not identify areas")

    def maximum(self, board: Board) -> int:
        if self.kind in ("people_on", "people_in"):
            return min(len(board.people), len(self.cells(board)))
        if self.kind == "people_with":
            assert self.selector is not None
            if self.selector.kind == "attribute":
                return len(board.attributes[self.selector.name])
            role = next(role for role in board.roles if role.name == self.selector.name)
            return len(board.people) if role.eligible_people is None else len(role.eligible_people)
        if self.kind == "empty_areas":
            return len(self.regions(board))
        return len(self.cells(board))

    def count(
        self,
        board: Board,
        placed: dict[str, Square],
        roles: dict[tuple[str, str], bool],
    ) -> int:
        if self.kind in ("people_on", "people_in"):
            cells = self.cells(board)
            return sum(square in cells for square in placed.values())
        if self.kind == "people_with":
            assert self.selector is not None
            if self.selector.kind == "role":
                return sum(
                    roles.get((person, self.selector.name), False) for person in board.people
                )
            return sum(board.has_attribute(person, self.selector.name) for person in board.people)
        if self.kind == "empty_areas":
            occupied = {board.region_of(square) for square in placed.values()}
            return sum(region not in occupied for region in self.regions(board))
        cells = self.cells(board)
        return len(cells - set(placed.values()))


def global_count_conditions(board: Board, clues: Iterable[Clue]) -> list[GlobalCountCondition]:
    """Parse and validate whole-board count clues in rules and numbered clues."""
    rules: list[tuple[str, list[str], int | None]] = [
        (kind, args, None) for kind, args in board.rules
    ]
    rules.extend((kind, args, number) for number, (kind, args) in enumerate(clues, 1))
    out: list[GlobalCountCondition] = []
    for kind, args, number in rules:
        if kind != GLOBAL_COUNTING:
            continue
        selector_kind, selector, comparison_tokens = _global_count_selector(board, args)
        maximum = _global_count_maximum(board, selector_kind, selector)
        comparison, operands, allowed = _parse_count_comparison(comparison_tokens, maximum)
        source = f"rule {len(out) + 1}" if number is None else f"clue {number}"
        label = f"{source} global count: {' '.join(args)}"
        out.append(
            GlobalCountCondition(
                label,
                selector_kind,
                selector,
                comparison,
                operands,
                allowed,
                number,
                len(out),
                tuple(args),
            )
        )
    return out


def _global_count_selector(
    board: Board, args: list[str]
) -> tuple[GlobalCountKind, TargetSelector | None, list[str]]:
    if len(args) >= 3 and args[0:2] in (["people", "on"], ["people", "in"]):
        kind: GlobalCountKind = "people_on" if args[1] == "on" else "people_in"
        selector = _target_selector(board, args[2])
        allowed = (
            ("object", "object_kind", "mark", "edge_item", "point_object")
            if kind == "people_on"
            else (
                "area",
                "tag",
                "rows",
                "columns",
                "object",
                "object_kind",
                "mark",
                "edge_item",
                "point_object",
            )
        )
        if selector.kind not in allowed:
            raise ValueError(f"count people {args[1]} needs a cell, area, row, or column selector")
        return kind, selector, args[3:]
    if len(args) >= 3 and args[:2] == ["people", "with"]:
        selector = _target_selector(board, args[2])
        if selector.kind not in ("role", "attribute"):
            raise ValueError("count people with requires a role:name or attribute:name selector")
        return "people_with", selector, args[3:]
    if len(args) >= 3 and args[:2] == ["empty", "areas"]:
        if args[2] == "all":
            return "empty_areas", None, args[3:]
        if len(args) >= 4 and args[2] == "in":
            selector = _target_selector(board, args[3])
            if selector.kind not in ("area", "tag"):
                raise ValueError("count empty areas in requires area:name or tag:name")
            return "empty_areas", selector, args[4:]
    if len(args) >= 4 and args[:3] == ["empty", "cells", "in"]:
        selector = _target_selector(board, args[3])
        if selector.kind not in (
            "area",
            "tag",
            "rows",
            "columns",
            "object",
            "object_kind",
            "mark",
            "edge_item",
            "point_object",
        ):
            raise ValueError("count empty cells in requires a cell-set selector")
        return "empty_cells", selector, args[4:]
    raise ValueError(
        "count expects 'people on|in|with ...', 'empty areas all|in ...', or 'empty cells in ...'"
    )


def _global_count_maximum(
    board: Board, kind: GlobalCountKind, selector: TargetSelector | None
) -> int:
    condition = GlobalCountCondition("", kind, selector, "=", (0,), frozenset({0}), None, 0, ())
    return condition.maximum(board)


def global_count_unit_prefix(kind: Literal["area", "cell"], unit: str) -> str:
    """Reserved base name for the hidden empty-area/cell Boolean of one unit."""
    return f"global_empty_{kind}_{unit}"


def _parse_count_comparison(
    tokens: list[str], maximum: int
) -> tuple[str, tuple[int, ...], frozenset[int]]:
    operands: tuple[int, ...]
    if len(tokens) == 2 and tokens[0] in ("=", "<=", ">="):
        if not tokens[1].isdigit():
            raise ValueError(f"count comparison needs a non-negative integer: {tokens}")
        operands = (int(tokens[1]),)
        value = operands[0]
        if tokens[0] == "=":
            allowed = {value}
        elif tokens[0] == "<=":
            allowed = set(range(0, min(value, maximum) + 1))
        else:
            allowed = set(range(value, maximum + 1))
        comparison = tokens[0]
    elif len(tokens) == 1 and tokens[0] in ("odd", "even"):
        comparison = tokens[0]
        operands = ()
        parity = 1 if comparison == "odd" else 0
        allowed = {count for count in range(maximum + 1) if count % 2 == parity}
    elif len(tokens) == 1 and ".." in tokens[0]:
        lower_text, separator, upper_text = tokens[0].partition("..")
        if not separator or not lower_text.isdigit() or not upper_text.isdigit():
            raise ValueError(f"count range must use inclusive low..high integers: {tokens[0]!r}")
        lower, upper = int(lower_text), int(upper_text)
        if lower > upper:
            raise ValueError(f"count range lower bound exceeds upper bound: {tokens[0]!r}")
        comparison, operands = "range", (lower, upper)
        allowed = set(range(lower, min(upper, maximum) + 1))
    else:
        raise ValueError(
            f"bad count comparison {tokens}; use = n, <= n, >= n, odd, even, or lo..hi"
        )
    feasible = frozenset(count for count in allowed if 0 <= count <= maximum)
    if not feasible:
        raise ValueError(f"count comparison {tokens} has no possible value from 0 to {maximum}")
    return comparison, operands, feasible


@dataclass(frozen=True)
class QuantifiedCondition:
    """A bounded-arity clue that asks for a person matching a target selector."""

    label: str
    kind: str
    subject: str
    selector: TargetSelector
    pair_test: PairTest | None = None
    number: int | None = None
    rest: tuple[str, ...] = ()

    def pair_state(
        self,
        board: Board,
        subject_square: Square,
        candidate: str,
        candidate_square: Square,
        roles: dict[tuple[str, str], bool],
    ) -> tuple[bool, bool]:
        selected = _target_matches(board, self.selector, candidate, candidate_square, roles)
        if self.kind == "alone_with":
            same_region = board.region_of(subject_square) == board.region_of(candidate_square)
            return same_region, not same_region or selected
        assert self.pair_test is not None
        return selected and self.pair_test(subject_square, candidate_square), True

    def holds(
        self,
        board: Board,
        placed: dict[str, Square],
        roles: dict[tuple[str, str], bool],
    ) -> bool:
        if self.kind == "alone_with":
            count = 0
            for person in board.people:
                if person == self.subject:
                    continue
                witness, valid = self.pair_state(
                    board, placed[self.subject], person, placed[person], roles
                )
                if not valid:
                    return False
                count += witness
            return count == 1
        return any(
            person != self.subject
            and self.pair_state(board, placed[self.subject], person, placed[person], roles)[0]
            for person in board.people
        )


ROLE_CONDITION_KINDS = frozenset(
    {
        "has_role",
        "not_role",
        "some_role",
        "roleless",
        "at_most_one_role",
        "role_subset",
        "role_in_tagged",
        "role_not_in_tagged",
        "min_role_in_tagged",
        "role_occupant",
        "role_on",
        "role_not_on",
        "role_next_to",
        "role_below",
        "sole_role_companion",
    }
)


def conditions(board: Board, clues: Iterable[Clue]) -> list[Condition]:
    """Board rules, mark effects, and clues as predicates over their people."""
    out: list[Condition] = []
    for kind, args in board.rules:
        if kind in ROLE_CONDITION_KINDS or _is_quantified_target(kind, args):
            continue
        if kind == GLOBAL_COUNTING:
            continue
        out += _conditions(board, kind, args, None)
    out.extend(
        _mark_occupant_condition(board, mark) for mark in board.marks if mark.occupant_condition
    )
    for number, (kind, args) in enumerate(clues, 1):
        if kind in ROLE_CONDITION_KINDS or _is_quantified_target(kind, args):
            continue
        if kind == GLOBAL_COUNTING:
            continue
        out += _conditions(board, kind, args, number)
    return out


def _is_quantified_target(kind: str, args: Sequence[str]) -> bool:
    return kind == "alone_with" or (kind in RELATIONS and len(args) > 1 and ":" in args[1])


def quantified_conditions(board: Board, clues: Iterable[Clue]) -> list[QuantifiedCondition]:
    """Target-based clues, each compiled using only pairwise placement relations."""
    rules: list[tuple[str, list[str], int | None]] = [
        (kind, args, None) for kind, args in board.rules
    ]
    rules.extend((kind, args, number) for number, (kind, args) in enumerate(clues, 1))
    out: list[QuantifiedCondition] = []
    for kind, args, number in rules:
        if not _is_quantified_target(kind, args):
            continue
        if kind == "alone_with":
            if len(args) != 2:
                raise ValueError(f"alone_with expects a person and one target selector: {args}")
            subject, selector_text = args
            pair_test = None
            rest: list[str] = []
        else:
            if len(args) < 2:
                raise ValueError(f"quantified {kind} expects a person and target selector: {args}")
            subject, selector_text, *rest = args
            pair_test = RELATIONS[kind](board, *rest)
        if subject not in board.people:
            raise ValueError(f"clue {kind!r} names unknown person {subject!r}")
        selector = _target_selector(board, selector_text)
        out.append(
            QuantifiedCondition(
                " ".join((kind, *args)), kind, subject, selector, pair_test, number, tuple(rest)
            )
        )
    return out


def _target_selector(board: Board, token: str) -> TargetSelector:
    """Parse `kind:name`; a bare known person is accepted as a person target."""
    kind, separator, name = token.partition(":")
    if not separator and token in board.people:
        return TargetSelector("person", token)
    if not separator or not name or any(char.isspace() for char in name):
        raise ValueError(f"bad target selector {token!r}; use kind:name")
    kind = {"cells": "mark", "cellset": "mark", "row": "rows", "column": "columns"}.get(kind, kind)
    supported = {
        "person",
        "attribute",
        "role",
        "area",
        "tag",
        "object_kind",
        "object",
        "mark",
        "edge_item",
        "point_object",
        "rows",
        "columns",
    }
    if kind not in supported:
        raise ValueError(f"unknown target kind {kind!r}; have {sorted(supported)}")
    selector = TargetSelector(cast(TargetKind, kind), name)
    if kind == "person" and name not in board.people:
        raise ValueError(f"unknown target person {name!r}")
    if kind == "attribute" and name not in board.attribute_names:
        raise ValueError(f"unknown target attribute {name!r}; have {sorted(board.attribute_names)}")
    if kind == "role" and name not in board.role_names:
        raise ValueError(f"unknown target role {name!r}; have {sorted(board.role_names)}")
    if kind == "area":
        board.area_ids([name])
    if kind == "tag":
        board.tagged_region_ids([name])
    if kind == "object_kind" and name not in ("blocking", "standable"):
        raise ValueError("object_kind target must be 'blocking' or 'standable'")
    if kind == "object":
        board.squares_of([name])
    if kind == "mark":
        board.mark_cells([name])
    if kind == "edge_item":
        board.edge_item_cells([name])
    if kind == "point_object":
        board.point_object_cells([name])
    if kind in ("rows", "columns"):
        line_indices(name, board.size)
    return selector


def line_indices(spec: str, size: int) -> set[int]:
    """Parse 1-based line lists/ranges such as `1,3-5` to zero-based indices."""
    indices: set[int] = set()
    for part in spec.split(","):
        start_text, separator, end_text = part.partition("-")
        if not start_text.isdigit() or (separator and not end_text.isdigit()):
            raise ValueError(f"bad line selector {spec!r}; use values like 1,3-5")
        start = int(start_text)
        end = int(end_text) if separator else start
        if start < 1 or end < start or end > size:
            raise ValueError(f"line selector {spec!r} must be between 1 and {size}")
        indices.update(range(start - 1, end))
    if not indices:
        raise ValueError("line selector cannot be empty")
    return indices


def _membership_selector(board: Board, token: str) -> TargetSelector:
    if ":" not in token and token in board.role_names:
        return TargetSelector("role", token)
    selector = _target_selector(board, token)
    if selector.kind not in ("role", "attribute", "person"):
        raise ValueError(f"membership selector must be a person, role or attribute: {token!r}")
    return selector


def _membership_literals(
    board: Board,
    membership: dict[tuple[str, str], tuple[int, int]],
    selector: TargetSelector,
    person: str,
) -> tuple[int | bool, int | bool]:
    if selector.kind == "role":
        return membership[person, selector.name]
    present = (
        board.has_attribute(person, selector.name)
        if selector.kind == "attribute"
        else person == selector.name
    )
    return present, not present


def _selector_cells(board: Board, selector: TargetSelector) -> set[Square]:
    if selector.kind == "rows":
        rows = line_indices(selector.name, board.size)
        return {square for square in board.free if square.row in rows}
    if selector.kind == "columns":
        columns = line_indices(selector.name, board.size)
        return {square for square in board.free if square.col in columns}
    if selector.kind == "area":
        ids = board.area_ids([selector.name])
        return {square for square in board.free if board.region_of(square) in ids}
    if selector.kind == "tag":
        ids = board.tagged_region_ids([selector.name])
        return {square for square in board.free if board.region_of(square) in ids}
    if selector.kind == "object_kind":
        return {
            square for obj in board.objects if obj.kind == selector.name for square in obj.squares
        }
    if selector.kind == "object":
        return board.squares_of([selector.name])
    if selector.kind == "mark":
        return board.mark_cells([selector.name])
    if selector.kind == "edge_item":
        return board.edge_item_cells([selector.name])
    if selector.kind == "point_object":
        return board.point_object_cells([selector.name])
    raise ValueError(f"target selector {selector.kind!r} does not identify cells")


def _target_matches(
    board: Board,
    selector: TargetSelector,
    person: str,
    square: Square,
    roles: dict[tuple[str, str], bool],
) -> bool:
    if selector.kind == "person":
        return person == selector.name
    if selector.kind == "attribute":
        return board.has_attribute(person, selector.name)
    if selector.kind == "role":
        return roles.get((person, selector.name), False)
    return square in _selector_cells(board, selector)


def role_conditions(board: Board, clues: Iterable[Clue]) -> list[RoleCondition]:
    """Role rules and clues, validated against declared people and roles."""
    rules: list[tuple[str, list[str], int | None]] = [
        (kind, args, None) for kind, args in board.rules
    ]
    rules.extend((kind, args, number) for number, (kind, args) in enumerate(clues, 1))
    roles = board.role_names
    role_positions = {
        "has_role": (1,),
        "not_role": (1,),
        "role_in_tagged": (1,),
        "role_not_in_tagged": (1,),
        "role_on": (1,),
        "role_not_on": (1,),
        "role_next_to": (1,),
        "role_below": (1,),
        "sole_role_companion": (1,),
        "min_role_in_tagged": (0,),
        "role_occupant": (0,),
    }
    minimum_arity = {
        "has_role": 2,
        "not_role": 2,
        "some_role": 1,
        "roleless": 1,
        "at_most_one_role": 1,
        "role_subset": 2,
        "role_in_tagged": 3,
        "role_not_in_tagged": 3,
        "min_role_in_tagged": 3,
        "role_occupant": 2,
        "role_on": 3,
        "role_not_on": 3,
        "role_next_to": 3,
        "role_below": 3,
        "sole_role_companion": 2,
    }
    out: list[RoleCondition] = []
    for kind, args, number in rules:
        if kind not in ROLE_CONDITION_KINDS:
            continue
        if len(args) < minimum_arity[kind] or (kind == "role_below" and len(args) > 4):
            raise ValueError(f"role rule {kind!r} has the wrong number of arguments: {args}")
        if kind == "some_role" and not roles:
            raise ValueError("some_role requires at least one declared role")
        if kind == "role_subset":
            _membership_selector(board, args[0])
            _membership_selector(board, args[1])
        for index in role_positions.get(kind, ()):
            if args[index] not in roles:
                raise ValueError(f"role rule {kind!r} names unknown role {args[index]!r}")
        person_kinds = {
            "has_role",
            "not_role",
            "some_role",
            "roleless",
            "at_most_one_role",
            "role_in_tagged",
            "role_not_in_tagged",
            "role_on",
            "role_not_on",
            "role_next_to",
            "role_below",
            "sole_role_companion",
        }
        if kind in person_kinds and args[0] not in board.people:
            raise ValueError(f"role rule {kind!r} names unknown person {args[0]!r}")
        if kind in ("role_in_tagged", "role_not_in_tagged"):
            board.tagged_region_ids([args[2]])
        if kind == "role_occupant" and args[1] not in ("alone", "not_alone"):
            raise ValueError("role_occupant condition must be 'alone' or 'not_alone'")
        if kind == "min_role_in_tagged":
            board.tagged_region_ids([args[1]])
            try:
                minimum = int(args[2])
            except ValueError as exc:
                raise ValueError(f"min_role_in_tagged needs a non-negative count: {args}") from exc
            if minimum < 0 or minimum > len(board.people):
                raise ValueError(
                    f"min_role_in_tagged count must be between 0 and {len(board.people)}"
                )
        if kind in ("role_on", "role_not_on", "role_next_to"):
            _role_target_cells(board, args[2:])
        if kind == "role_below" and len(args) == 4:
            try:
                gap = int(args[3])
            except ValueError as exc:
                raise ValueError(f"role_below needs an optional positive row gap: {args}") from exc
            if gap < 1:
                raise ValueError("role_below row gap must be at least 1")
        out.append(RoleCondition(" ".join((kind, *args)), kind, tuple(args), number))
    for role in board.roles:
        if role.eligible_people is not None:
            out.extend(
                RoleCondition(
                    f"{person} not eligible for role {role.name}",
                    "not_role",
                    (person, role.name),
                )
                for person in board.people
                if person not in role.eligible_people
            )
    return out


def _role_target_cells(board: Board, names: Iterable[str]) -> set[Square]:
    """Cell targets for role bindings: objects, object kinds, edge items, corners or marks."""
    cells: set[Square] = set()
    for name in names:
        if name in ("blocking", "standable"):
            cells.update(
                square for obj in board.objects if obj.kind == name for square in obj.squares
            )
        elif name in board.mark_names:
            cells.update(board.mark_cells([name]))
        elif name in board.object_names:
            cells.update(board.squares_of([name]))
        elif name in board.edge_item_names:
            cells.update(board.edge_item_cells([name]))
        elif name in board.point_object_names:
            cells.update(board.point_object_cells([name]))
        else:
            raise ValueError(f"unknown role target {name!r}")
    return cells


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
    while name in model.all_variables:
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
    if kind in ATTRIBUTE_FILTERS:
        if len(args) != 2:
            raise ValueError(f"clue {kind!r} expects a person and one attribute")
        person, attribute = args
        if person not in board.people:
            raise ValueError(f"clue {kind!r} names unknown person {person!r}")
        if attribute not in board.attribute_names:
            raise ValueError(f"clue {kind!r} names unknown attribute {attribute!r}")
        expected = kind == "has_attribute"
        holds = board.has_attribute(person, attribute) == expected
        return [
            Condition(
                " ".join((kind, *args)),
                (person,),
                lambda _square, holds=holds: holds,
                kind,
                tuple(args),
                number,
            )
        ]
    if kind == "unique_attribute":
        if len(args) < 2:
            raise ValueError("unique_attribute expects an attribute and at least one person")
        attribute, *selected = args
        if attribute not in board.attribute_names:
            raise ValueError(f"unique_attribute names unknown attribute {attribute!r}")
        unknown = set(selected) - set(board.people)
        if unknown:
            raise ValueError(f"unique_attribute names unknown people {sorted(unknown)}")
        if len(set(selected)) != len(selected):
            raise ValueError("unique_attribute cannot select a person more than once")
        unique = len(board.attributes[attribute] & set(selected)) == 1
        return [
            Condition(
                " ".join((kind, *args)),
                (selected[0],),
                lambda _square, unique=unique: unique,
                kind,
                tuple(args),
                number,
            )
        ]
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
        if _is_quantified_target(kind, rest):
            raise ValueError(f"{COUNTING} cannot count quantified target clues such as {kind!r}")
        if kind not in FILTERS and kind not in RELATIONS and kind not in ATTRIBUTE_FILTERS:
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
    clues = tuple(clues)
    model = Model()
    _add_board_rules(model, board)
    role_literals = _add_roles(model, board)
    role_rules = role_conditions(board, clues)
    _compile_role_conditions(model, board, role_literals, role_rules)
    count_conditions = global_count_conditions(board, clues)
    attribute_membership = _global_attribute_membership(model, board, count_conditions)
    _compile_global_counts(model, board, count_conditions, role_literals, attribute_membership)
    for target_condition in quantified_conditions(board, clues):
        _compile_quantified_condition(model, board, target_condition)
    for location_condition in conditions(board, clues):
        if location_condition.kind == "occupant_condition":
            (mark_name, _) = location_condition.args
            mark = next(mark for mark in board.marks if mark.name == mark_name)
            assert mark.occupant_condition is not None
            _compile_mark_occupant_condition(model, board, mark, mark.occupant_condition)
            continue
        if len(location_condition.people) == 1:
            (person,) = location_condition.people
            for sq in board.free:
                if not location_condition.test(sq):
                    model.eliminate(
                        model.literal(person, sq),
                        "clue",
                        location_condition.label,
                        sources=(location_condition.label,),
                    )
        else:
            model.relate(
                location_condition.label, location_condition.people, location_condition.test
            )
    return model


def _hidden_boolean(model: Model, prefix: str, name: str, family: str) -> tuple[str, int, int]:
    variable = _auxiliary_variable(model, prefix)
    is_true = model.literal(variable, True)
    is_false = model.literal(variable, False)
    model.constrain(
        f"{name} state",
        Kind.EXACTLY_ONE,
        [is_true, is_false],
        defines=variable,
        hidden=True,
        family=family,
    )
    return variable, is_true, is_false


def _global_attribute_membership(
    model: Model, board: Board, conditions: Sequence[GlobalCountCondition]
) -> dict[tuple[str, str], tuple[int, int]]:
    """Expose fixed attributes as hidden Booleans for generic count constraints."""
    attributes = {
        condition.selector.name
        for condition in conditions
        if condition.kind == "people_with"
        and condition.selector is not None
        and condition.selector.kind == "attribute"
    }
    membership: dict[tuple[str, str], tuple[int, int]] = {}
    for attribute in sorted(attributes):
        for person in board.people:
            _, present, absent = _hidden_boolean(
                model,
                "global_attribute",
                f"{person} attribute {attribute}",
                "attribute membership",
            )
            membership[person, attribute] = (present, absent)
            model.assign(
                present if board.has_attribute(person, attribute) else absent,
                "clue",
                f"{person} has attribute {attribute}"
                if board.has_attribute(person, attribute)
                else f"{person} does not have attribute {attribute}",
                sources=(f"attribute {attribute} for {person}",),
            )
    return membership


def _compile_global_counts(
    model: Model,
    board: Board,
    conditions: Sequence[GlobalCountCondition],
    roles: dict[tuple[str, str], tuple[int, int]],
    attributes: dict[tuple[str, str], tuple[int, int]],
) -> None:
    empty_areas: dict[str, int] = {}
    empty_cells: dict[Square, int] = {}
    for condition in conditions:
        if condition.kind in ("people_on", "people_in"):
            cells = condition.cells(board)
            literals = [
                model.literal(person, square) for person in board.people for square in sorted(cells)
            ]
        elif condition.kind == "people_with":
            assert condition.selector is not None
            name = condition.selector.name
            literals = [
                (roles if condition.selector.kind == "role" else attributes)[person, name][0]
                for person in board.people
            ]
        elif condition.kind == "empty_areas":
            literals = []
            for region in sorted(condition.regions(board)):
                if region not in empty_areas:
                    _, is_empty, _ = _hidden_boolean(
                        model,
                        global_count_unit_prefix("area", region),
                        f"area {board.region_names[region]} is empty",
                        "global empty area",
                    )
                    occupants = [
                        model.literal(person, square)
                        for person in board.people
                        for square in board.free
                        if board.region_of(square) == region
                    ]
                    model.constrain(
                        f"area {board.region_names[region]} empty state",
                        Kind.COUNT,
                        occupants,
                        allowed_counts={0},
                        reified_by=is_empty,
                        family="global empty area",
                    )
                    empty_areas[region] = is_empty
                literals.append(empty_areas[region])
        else:
            literals = []
            for square in sorted(condition.cells(board)):
                if square not in empty_cells:
                    _, is_empty, _ = _hidden_boolean(
                        model,
                        global_count_unit_prefix("cell", str(square)),
                        f"cell {square} is empty",
                        "global empty cell",
                    )
                    occupants = [model.literal(person, square) for person in board.people]
                    model.constrain(
                        f"cell {square} empty state",
                        Kind.COUNT,
                        occupants,
                        allowed_counts={0},
                        reified_by=is_empty,
                        family="global empty cell",
                    )
                    empty_cells[square] = is_empty
                literals.append(empty_cells[square])
        model.constrain(
            condition.label,
            Kind.COUNT,
            literals,
            allowed_counts=condition.allowed_counts,
            family=f"global count clue {condition.number or condition.index + 1}: {condition.kind}",
        )


def _compile_quantified_condition(
    model: Model, board: Board, condition: QuantifiedCondition
) -> None:
    witnesses: list[int] = []
    for person in board.people:
        if person == condition.subject:
            continue
        variable, is_match, _ = _hidden_boolean(
            model, "target_witness", f"{condition.label} witness {person}", "target witness"
        )
        witnesses.append(is_match)
        role_variable = (
            board.role_variable(person, condition.selector.name)
            if condition.selector.kind == "role"
            else None
        )
        variables: tuple[str, ...] = (condition.subject, person, variable)
        if role_variable is not None:
            variables = (condition.subject, person, role_variable, variable)

        def holds(
            *values: Any,
            candidate: str = person,
            has_role_var: str | None = role_variable,
            selector: TargetSelector = condition.selector,
        ) -> bool:
            if has_role_var is not None:
                subject_square, candidate_square, has_role, witness = values
                role_values = {(candidate, selector.name): has_role}
            else:
                subject_square, candidate_square, witness = values
                role_values = {}
            expected, valid = condition.pair_state(
                board, subject_square, candidate, candidate_square, role_values
            )
            return valid and witness == expected

        model.relate(f"{condition.label} witness {person}", variables, holds)

    if not witnesses:
        model.relate(condition.label, (condition.subject,), lambda _square: False)
        return
    allowed = {1} if condition.kind == "alone_with" else range(1, len(witnesses) + 1)
    model.constrain(
        condition.label,
        Kind.COUNT,
        witnesses,
        allowed_counts=allowed,
        family="quantified target",
    )


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
            [model.literal(person_name, square) for person_name, square in rule.options],
            defines=person,
            family=rule.family,
        )


def _add_roles(model: Model, board: Board) -> dict[tuple[str, str], tuple[int, int]]:
    """Create independent Boolean membership variables and role-wide counts."""
    membership: dict[tuple[str, str], tuple[int, int]] = {}
    for role in board.roles:
        true_literals: list[int] = []
        for person in board.people:
            variable = board.role_variable(person, role.name)
            is_role = model.literal(variable, True)
            not_role = model.literal(variable, False)
            membership[person, role.name] = (is_role, not_role)
            model.constrain(
                f"{person} role state {role.name}",
                Kind.EXACTLY_ONE,
                [is_role, not_role],
                defines=variable,
                hidden=True,
                family="role membership",
            )
            true_literals.append(is_role)
            if role.eligible_people is not None and person not in role.eligible_people:
                model.assign(
                    not_role,
                    "clue",
                    f"{person} is not eligible for role {role.name}",
                    sources=(f"{person} not eligible for {role.name}",),
                )
        if role.allowed_counts != frozenset(range(len(board.people) + 1)):
            model.constrain(
                f"role {role.name} cardinality",
                Kind.COUNT,
                true_literals,
                allowed_counts=role.allowed_counts,
                family="role cardinality",
            )
        if role.different_regions:
            for index, first in enumerate(board.people):
                for second in board.people[index + 1 :]:
                    first_var = board.role_variable(first, role.name)
                    second_var = board.role_variable(second, role.name)
                    model.relate(
                        f"{first} and {second} {role.name} in different regions",
                        (first_var, first, second_var, second),
                        lambda a, x, b, y: (
                            not (a and b) or board.region_of(x) != board.region_of(y)
                        ),
                    )
    return membership


def _compile_role_conditions(
    model: Model,
    board: Board,
    membership: dict[tuple[str, str], tuple[int, int]],
    role_rules: Sequence[RoleCondition],
) -> None:
    for rule in role_rules:
        kind, args = rule.kind, rule.args
        if kind in ("has_role", "not_role"):
            person, role = args[:2]
            is_role = membership[person, role][0]
            if kind == "has_role":
                model.assign(is_role, "clue", f"{person} has role {role}", sources=(rule.label,))
            else:
                model.assign(
                    membership[person, role][1],
                    "clue",
                    f"{person} is not role {role}",
                    sources=(rule.label,),
                )
        elif kind in ("some_role", "roleless", "at_most_one_role"):
            (person,) = args
            literals = [membership[person, role.name][0] for role in board.roles]
            if kind == "some_role" and not literals:
                raise ValueError(f"some_role names {person}, but no roles are declared")
            counts = {
                "some_role": frozenset(range(1, len(literals) + 1)),
                "roleless": frozenset((0,)),
                "at_most_one_role": frozenset((0, 1)),
            }[kind]
            if literals:
                model.constrain(
                    rule.label,
                    Kind.COUNT,
                    literals,
                    allowed_counts=counts,
                    family="person role cardinality",
                )
        elif kind == "role_subset":
            subset, superset = args
            for person in board.people:
                left = _membership_literals(
                    board, membership, _membership_selector(board, subset), person
                )
                right = _membership_literals(
                    board, membership, _membership_selector(board, superset), person
                )
                label = f"{person} {subset} implies {superset}"
                if type(left[0]) is int and type(right[0]) is int:
                    model.constrain(
                        label,
                        Kind.AT_MOST_ONE,
                        [left[0], right[1]],
                        family="role implication",
                    )
                elif type(left[0]) is int and not right[0]:
                    model.assign(left[1], "clue", label, sources=(rule.label,))
                elif type(right[0]) is int and left[0]:
                    model.assign(right[0], "clue", label, sources=(rule.label,))
                elif left[0] and not right[0]:
                    model.relate(label, (person,), lambda _square: False)
        elif kind in ("role_in_tagged", "role_not_in_tagged"):
            person, role, tag = args[:3]
            ids = board.tagged_region_ids([tag])
            inside = kind == "role_in_tagged"
            variable = board.role_variable(person, role)

            def holds(
                has_role: bool,
                square: Square,
                role_regions: set[str] = ids,
                must_be_inside: bool = inside,
            ) -> bool:
                return not has_role or (board.region_of(square) in role_regions) == must_be_inside

            model.relate(
                rule.label,
                (variable, person),
                holds,
            )
        elif kind in ("role_on", "role_not_on", "role_next_to"):
            person, role, *targets = args
            role_variable = board.role_variable(person, role)
            target_test: SquareTest
            if kind == "role_next_to":
                target_test = _next_to(board, *targets)
            else:
                cells = _role_target_cells(board, targets)
                on = kind == "role_on"

                def on_target(
                    square: Square, cells: set[Square] = cells, on_target: bool = on
                ) -> bool:
                    return (square in cells) == on_target

                target_test = on_target

            def role_location_test(
                has_role: bool, square: Square, target: SquareTest = target_test
            ) -> bool:
                return not has_role or target(square)

            model.relate(
                rule.label,
                (role_variable, person),
                role_location_test,
            )
        elif kind == "min_role_in_tagged":
            role, tag, minimum_text = args
            minimum = int(minimum_text)
            for region in sorted(board.tagged_region_ids([tag])):
                holders = [
                    _role_in_region_literal(model, board, membership, person, role, region)
                    for person in board.people
                ]
                if minimum:
                    model.constrain(
                        f"{rule.label} in {board.region_names[region]}",
                        Kind.COUNT,
                        holders,
                        allowed_counts=range(minimum, len(holders) + 1),
                        family="role area cardinality",
                    )
        elif kind == "role_below":
            person, role, *gap_arg = args
            gap = int(gap_arg[0]) if gap_arg else None
            qualifying: list[int] = []
            for other in board.people:
                if other == person:
                    continue
                indicator = _auxiliary_variable(model, "role_below")
                is_below = model.literal(indicator, True)
                not_below = model.literal(indicator, False)
                model.constrain(
                    f"{rule.label} witness {other}",
                    Kind.EXACTLY_ONE,
                    [is_below, not_below],
                    defines=indicator,
                    hidden=True,
                    family="role witness",
                )
                other_role = board.role_variable(other, role)
                model.relate(
                    f"{rule.label} witness {other}",
                    (person, other_role, other, indicator),
                    lambda subject, has_role, candidate, witness, gap=gap: (
                        witness
                        == (
                            has_role
                            and candidate.row < subject.row
                            and (gap is None or subject.row - candidate.row == gap)
                        )
                    ),
                )
                qualifying.append(is_below)
            if qualifying:
                model.constrain(
                    rule.label,
                    Kind.COUNT,
                    qualifying,
                    allowed_counts=range(1, len(qualifying) + 1),
                    family="role position",
                )
            else:
                raise ValueError(f"role_below {person} has no other people to compare")
        elif kind == "sole_role_companion":
            person, role = args
            companions: list[int] = []
            for other in board.people:
                if other == person:
                    continue
                witness = _auxiliary_variable(model, "role_companion")
                same_region = model.literal(witness, True)
                different_region = model.literal(witness, False)
                model.constrain(
                    f"{rule.label} companion state {other}",
                    Kind.EXACTLY_ONE,
                    [same_region, different_region],
                    defines=witness,
                    hidden=True,
                    family="role witness",
                )
                model.relate(
                    f"{rule.label} companion {other}",
                    (person, other, witness),
                    lambda first, second, same: (
                        same == (board.region_of(first) == board.region_of(second))
                    ),
                )
                model.constrain(
                    f"{rule.label} companion has role {role} {other}",
                    Kind.AT_MOST_ONE,
                    [same_region, membership[other, role][1]],
                    family="role companion",
                )
                companions.append(same_region)
            model.constrain(
                rule.label,
                Kind.COUNT,
                companions,
                allowed_counts={1},
                family="role companion",
            )
        elif kind == "role_occupant":
            role, condition = args
            occupant_condition: OccupantCondition = "alone" if condition == "alone" else "not_alone"
            allowed = _occupant_counts(occupant_condition, len(board.people))
            for region in sorted(board.region_names):
                triggers = [
                    _role_in_region_literal(model, board, membership, person, role, region)
                    for person in board.people
                ]
                occupants = [
                    model.literal(person, square)
                    for person in board.people
                    for square in board.free
                    if board.region_of(square) == region
                ]
                apply_occupant_condition(
                    model,
                    f"role {role} {condition} in {board.region_names[region]}",
                    triggers,
                    occupants,
                    allowed,
                )


def _role_in_region_literal(
    model: Model,
    board: Board,
    membership: dict[tuple[str, str], tuple[int, int]],
    person: str,
    role: str,
    region: str,
) -> int:
    """Hidden Boolean: this person has `role` and occupies `region`."""
    variable = _auxiliary_variable(model, f"role_in_{person}_{role}_{region}")
    in_region = model.literal(variable, True)
    outside_region = model.literal(variable, False)
    model.constrain(
        f"{variable} state",
        Kind.EXACTLY_ONE,
        [in_region, outside_region],
        defines=variable,
        hidden=True,
        family="role area membership",
    )
    locations = [
        model.literal(person, square) for square in board.free if board.region_of(square) == region
    ]
    if locations:
        model.constrain(
            f"{variable} role and area",
            Kind.COUNT,
            [membership[person, role][0], *locations],
            allowed_counts={2},
            reified_by=in_region,
            family="role area membership",
        )
    else:
        model.eliminate(
            in_region,
            "clue",
            f"{variable} has no free squares in its area",
            sources=(f"{variable} no free area cells",),
        )
    return in_region


def role_statuses(board: Board, model: Model) -> dict[tuple[str, str], bool | None]:
    """Known role membership per person; None means the status remains unknown."""
    statuses: dict[tuple[str, str], bool | None] = {}
    for role in board.roles:
        for person in board.people:
            value = model.chosen(board.role_variable(person, role.name))
            statuses[person, role.name] = value if isinstance(value, bool) else None
    return statuses


# --- rendering ------------------------------------------------------------


def render(
    board: Board,
    model: Model,
    title: str,
    steps: Sequence[Step] = (),
    *,
    global_counts: Sequence[GlobalCountCondition] = (),
) -> str:
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
    active_sources = {source for step in steps for source in step.sources}
    count_scope = {
        square
        for condition in global_counts
        if condition.label in active_sources
        for square in condition.scope_cells(board)
    }
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
                tint = NEW if person in placed or sq in count_scope else INK
                body = f"{tint}{person[:3]:^4}"
            elif sq in count_scope:
                body = f"{NEW}*   "
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
    out += _global_count_progress(model, global_counts, active_sources)
    if count_scope:
        out.append(f"  {NEW}*{RESET} cells in the global count scope for this step")

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
    if board.point_objects:
        listed = ", ".join(
            f"{item.name} {item.label} {' '.join(map(str, item.cells))}"
            for item in board.point_objects
        )
        out.append(f"  point objects: {listed}")
    if board.marks:
        listed = ", ".join(
            f"{mark.name} {' '.join(map(str, mark.cells))}"
            + (f" ; {mark.occupant_condition}" if mark.occupant_condition else "")
            for mark in board.marks
        )
        out.append(f"  marks: {listed}")
    if board.roles:
        statuses = role_statuses(board, model)
        role_variables = {
            board.role_variable(person, role.name)
            for role in board.roles
            for person in board.people
        }
        changed = {
            step.var: step.value if step.asserted else not step.value
            for step in steps
            if step.var in role_variables
        }
        out.append("\n  role membership (+ present, - absent, ? unknown):")
        for role in board.roles:
            entries = []
            for person in board.people:
                state = statuses[person, role.name]
                marker = "+" if state is True else "-" if state is False else "?"
                entry = f"{person}{marker}"
                variable = board.role_variable(person, role.name)
                entries.append(f"{NEW}{entry}{RESET}" if variable in changed else entry)
            out.append(f"    {role.name}: {' '.join(entries)}")
    return "\n".join(out)


def _reachable(board: Board, model: Model) -> set[Square]:
    """Squares at least one person can still stand on."""
    return {model.value_of(lit) for p in board.people for lit in model.options(p)}


def _global_count_progress(
    model: Model, conditions: Sequence[GlobalCountCondition], active_sources: set[str]
) -> list[str]:
    if not conditions:
        return []
    lines = ["  global counts:"]
    for condition in conditions:
        constraint = next(c for c in model.constraints if c.name == condition.label)
        current = sum(model.is_true(literal) for literal in constraint.literals)
        undecided = sum(
            not model.is_true(literal) and not model.is_false(literal)
            for literal in constraint.literals
        )
        feasible = model.feasible_counts(constraint.index)
        possible = ",".join(map(str, sorted(feasible))) or "none"
        additional = sorted(count - current for count in feasible)
        if not additional:
            needed = "none"
        elif additional[0] == additional[-1]:
            needed = f"{additional[0]} more"
        else:
            needed = f"{additional[0]}..{additional[-1]} more"
        allowed = ",".join(map(str, sorted(condition.allowed_counts)))
        marker = NEW if condition.label in active_sources else INK
        reference = f" ({condition.number})" if condition.number is not None else ""
        lines.append(
            f"    {marker}{condition.description}{reference}: {current} true, "
            f"{undecided} open; need {needed}, possible {possible}, allowed {allowed}{RESET}"
        )
    return lines


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


def implied_clues(clues: Sequence[Clue]) -> list[tuple[int, int]]:
    """Pairs (clue, other) of 1-based clue numbers where `other` alone already says what
    `clue` says, so `clue` can go: a person put in one region needs no 'not in' another
    region, and two people put in different regions need no 'different region' clue."""
    placed: dict[str, list[tuple[int, set[str]]]] = {}
    for number, (kind, args) in enumerate(clues, 1):
        if kind == "in_region":
            placed.setdefault(args[0], []).append((number, set(args[1:])))
    found = []
    for number, (kind, args) in enumerate(clues, 1):
        if kind == "outside":
            found += [
                (number, other)
                for other, regions in placed.get(args[0], [])
                if not regions & set(args[1:])
            ]
        elif kind == "different_region":
            found += [
                (number, other)
                for other, first in placed.get(args[0], [])
                for _, second in placed.get(args[1], [])
                if not first & second
            ][:1]
        elif kind == "in_region":
            found += [
                (number, other)
                for other, regions in placed.get(args[0], [])
                if other != number and regions < set(args[1:])
            ]
    return found
