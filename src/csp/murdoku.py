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

from collections import Counter, deque
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
type WindowSide = Literal["top", "bottom", "left", "right"]
WINDOW_SIDES: tuple[WindowSide, ...] = ("top", "bottom", "left", "right")
type OccupantCondition = Literal["alone", "not_alone"]


@dataclass(frozen=True)
class BoardObject:
    """One connected footprint of a named object type and explicit occupancy kind."""

    name: str
    kind: ObjectKind
    squares: tuple[Square, ...]
    side: WindowSide | None = None  # the wall a seat's back is against; only drawing uses it

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError(f"object name {self.name!r} must be a single token")
        if self.side is not None and self.side not in WINDOW_SIDES:
            raise ValueError(f"object {self.name!r}: side must be one of {', '.join(WINDOW_SIDES)}")
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
    side: WindowSide | None = None  # the wall a window sits in; only drawing uses it

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
        if self.side is not None and (self.kind != "window" or self.side not in WINDOW_SIDES):
            raise ValueError(
                f"edge item {self.name!r}: only a window takes a side ({', '.join(WINDOW_SIDES)})"
            )


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
    (region id -> '#RRGGBB'), `hatched` (region ids), `backdrop` (an icon
    name or `U+XXXX` drawn large behind the board) and `decorations` (icon
    names on doubled grid-point anchors, as for point objects) only affect
    pictures.

    `area_tags` map reusable tags to named regions. `attributes` are fixed
    traits on named people, while `roles` are solver-managed memberships;
    `pronouns` are used only by worked-solution wording. Rules and clues are
    separate expression statements, not part of the fixed layout.
    """

    size: int
    regions: list[list[str]]
    region_names: dict[str, str]
    objects: list[BoardObject]
    people: list[str]
    area_tags: dict[str, list[str]] = field(default_factory=dict)
    colours: dict[str, str] = field(default_factory=dict)
    hatched: set[str] = field(default_factory=set)
    backdrop: str | None = None
    decorations: list[tuple[str, tuple[int, int]]] = field(default_factory=list)
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


# --- shared spatial and lowering primitives -------------------------------

type SquareTest = Callable[[Square], bool]
type PairTest = Callable[[Square, Square], bool]


def target_name(token: str) -> str:
    """Return a mark's layout name from an internal target token."""
    kind, separator, name = token.partition(":")
    return name if separator and name and kind == "mark" else token


def _next_to(board: Board, *things: str) -> SquareTest:
    """Beside objects in the same area, a point object's touched cells, an edge
    item's cells, or any cell of a marked set.

    A mark counts across an area border, like a point object: it is a property of
    a square, not a piece of furniture standing in one area. Standing on a marked
    square is not "next to" it unless another cell of the mark lies beside it.
    """
    targets: set[Square] = set()
    marked: set[Square] = set()
    touched: set[Square] = set()
    for thing in things:
        name = target_name(thing)
        if name in board.mark_names:
            marked.update(board.mark_cells([name]))
        elif name in board.edge_item_names:
            touched.update(board.edge_item_cells([name]))
        elif name in board.point_object_names:
            touched.update(board.point_object_cells([name]))
        elif name in ("blocking", "standable"):
            targets.update(
                square for obj in board.objects if obj.kind == name for square in obj.squares
            )
        else:
            targets.update(board.squares_of([name]))

    def test(square: Square) -> bool:
        if square in touched or any(steps_between(square, cell) == 1 for cell in marked):
            return True
        return any(
            steps_between(square, target) == 1
            and board.region_of(target) == board.region_of(square)
            for target in targets
        )

    return test


def next_to_covers_own_squares(board: Board, *things: str) -> bool:
    """True when standing on one of the things already counts as next to them.

    A square of a multi-square standable object borders another square of it, so
    `beside object:bench` includes the bench itself; the same holds when two cells of one
    marked set touch. Clue text must then say "on or next to".
    """
    beside = _next_to(board, *things)
    names = [target_name(thing) for thing in things]
    standable = {obj.name for obj in board.standable_objects}
    own = board.squares_of([name for name in names if name in standable])
    own |= board.mark_cells([name for name in names if name in board.mark_names])
    return any(beside(square) for square in own)


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


AREA_POPULATION = {
    "busiest_area": "most",
    "quietest_area": "fewest",
}
POPULATION_PREFIX = "area_population"
POPULATION_FAMILY = "area population"


type TargetKind = Literal[
    "person",
    "people",
    "people_on",
    "anyone",
    "attribute",
    "role",
    "area",
    "tag",
    "adjacent_to",
    "intersection",
    "union",
    "corner",
    "object_kind",
    "object",
    "mark",
    "edge_item",
    "point_object",
    "rows",
    "columns",
    "anyone",
]


@dataclass(frozen=True)
class TargetSelector:
    kind: TargetKind
    name: str
    parts: tuple["TargetSelector", ...] = ()


@dataclass(frozen=True)
class AreaPopulationCondition:
    """A recognised expression pattern comparing extreme area populations.

    The named areas share one count, and every other area compares with them:
    strictly fewer people for `busiest`, strictly more for `quietest`. Areas
    nobody can stand in hold nobody and are left out of the comparison.
    """

    label: str
    kind: str
    regions: tuple[str, ...]
    tokens: tuple[str, ...]
    number: int | None
    index: int


@dataclass(frozen=True)
class QuantifiedCondition:
    """A bounded-arity clue that asks for a person matching a target selector.

    The subject is a named person, or, with `subject_selector`, anyone matching
    that selector: `above object:badjas object:sloffen 1` holds when somebody on
    a bathrobe is exactly one row above somebody on the slippers.
    """

    label: str
    kind: str
    subject: str
    selector: TargetSelector
    pair_test: PairTest | None = None
    number: int | None = None
    rest: tuple[str, ...] = ()
    subject_selector: TargetSelector | None = None

    @property
    def companions(self) -> int:
        """How many others `alone_with` puts in the subject's region (default one)."""
        return int(self.rest[0]) if self.kind == "alone_with" and self.rest else 1

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
            return count == self.companions
        if self.subject_selector is not None:
            return any(
                first != second
                and _target_matches(board, self.subject_selector, first, placed[first], roles)
                and self.pair_state(board, placed[first], second, placed[second], roles)[0]
                for first in board.people
                for second in board.people
            )
        return any(
            person != self.subject
            and self.pair_state(board, placed[self.subject], person, placed[person], roles)[0]
            for person in board.people
        )


def _target_selector(board: Board, token: str) -> TargetSelector:
    """Parse a typed selector; a bare known person is accepted as a person target."""
    kind, separator, name = token.partition(":")
    if not separator and token in board.people:
        return TargetSelector("person", token)
    if not separator or not name:
        raise ValueError(f"bad target selector {token!r}; use kind:name")
    if kind == "person":
        raise ValueError(f"use the bare person name instead of {token!r}")
    supported = {
        "people",
        "people_on",
        "anyone",
        "attribute",
        "role",
        "area",
        "tag",
        "adjacent_to",
        "corner",
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
    if "," in name and kind in {
        "area",
        "tag",
        "object",
        "mark",
        "edge_item",
        "point_object",
        "rows",
        "columns",
    }:
        names = name.split(",")
        if any(not item for item in names):
            raise ValueError(f"selector {token!r} contains an empty name")
        return TargetSelector(
            "union", "", tuple(_target_selector(board, f"{kind}:{item}") for item in names)
        )
    selector = TargetSelector(cast(TargetKind, kind), name)
    if kind == "person" and name not in board.people:
        raise ValueError(f"unknown target person {name!r}")
    if kind == "people":
        if name == "any":
            return TargetSelector("anyone", "")
        people = name.split(",")
        if any(not person or person not in board.people for person in people):
            unknown = sorted(set(people) - set(board.people))
            raise ValueError(f"unknown people in selector {token!r}: {unknown}")
        if len(set(people)) != len(people):
            raise ValueError(f"people selector {token!r} repeats a person")
    if kind == "people_on":
        nested = _target_selector(board, name)
        if nested.kind in ("person", "people", "people_on", "anyone", "attribute", "role"):
            raise ValueError(f"people_on requires a location selector, not {name!r}")
    if kind == "attribute" and name not in board.attribute_names:
        raise ValueError(f"unknown target attribute {name!r}; have {sorted(board.attribute_names)}")
    if kind == "role" and name not in board.role_names:
        raise ValueError(f"unknown target role {name!r}; have {sorted(board.role_names)}")
    if kind == "area":
        board.area_ids([name])
    if kind == "tag":
        board.tagged_region_ids([name])
    if kind == "adjacent_to":
        if name.startswith("tag:"):
            _target_selector(board, name)
        else:
            board.area_ids([name])
    if kind == "corner" and name != "board":
        nested = _target_selector(board, name)
        if nested.kind != "area":
            raise ValueError(f"corner requires 'board' or 'area:name', not {name!r}")
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


def _adjacent_region_ids(board: Board, selector: TargetSelector) -> set[str]:
    if selector.kind != "adjacent_to":
        raise ValueError(f"selector {selector.kind!r} is not adjacent_to")
    if selector.name.startswith("tag:"):
        source_regions = board.tagged_region_ids([selector.name.partition(":")[2]])
    else:
        source_regions = board.area_ids([selector.name])
    return {
        region
        for border in board.borders
        for region in border
        if any(other in source_regions for other in border)
    } - source_regions


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
    if selector.kind == "adjacent_to":
        adjacent = _adjacent_region_ids(board, selector)
        return {square for square in board.free if board.region_of(square) in adjacent}
    if selector.kind == "intersection":
        if not selector.parts:
            return set()
        return set.intersection(*(_selector_cells(board, part) for part in selector.parts))
    if selector.kind == "union":
        return set().union(*(_selector_cells(board, part) for part in selector.parts))
    if selector.kind == "corner":
        if selector.name == "board":
            corners = {
                Square(0, 0),
                Square(0, board.size - 1),
                Square(board.size - 1, 0),
                Square(board.size - 1, board.size - 1),
            }
            return corners & set(board.free)
        area = _target_selector(board, selector.name)
        return {square for square in board.free if _in_area_corner(board, area.name)(square)}
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
    if selector.kind == "anyone":
        return True
    if selector.kind == "person":
        return person == selector.name
    if selector.kind == "people":
        return person in selector.name.split(",")
    if selector.kind == "attribute":
        return board.has_attribute(person, selector.name)
    if selector.kind == "role":
        return roles.get((person, selector.name), False)
    if selector.kind == "people_on":
        location = _target_selector(board, selector.name)
        return square in _selector_cells(board, location)
    return square in _selector_cells(board, selector)


def _area_distances(board: Board) -> dict[tuple[str, str], int]:
    """Shortest side-sharing border distance between every pair of logical areas."""
    neighbors: dict[str, set[str]] = {region: set() for region in board.region_names}
    for border in board.borders:
        first, second = border
        neighbors[first].add(second)
        neighbors[second].add(first)
    distances: dict[tuple[str, str], int] = {}
    for start in neighbors:
        distances[start, start] = 0
        pending = deque([start])
        while pending:
            current = pending.popleft()
            for neighbor in neighbors[current]:
                if (start, neighbor) not in distances:
                    distances[start, neighbor] = distances[start, current] + 1
                    pending.append(neighbor)
    return distances


def _direction_test(
    board: Board, mode: str, comparison: str | None, distance: int | None
) -> PairTest:
    if mode in ("left", "right", "up", "down"):
        sign = 1 if mode in ("left", "up") else -1

        def directional(first: Square, second: Square) -> bool:
            gap = second.col - first.col if mode in ("left", "right") else second.row - first.row
            delta = gap * sign
            return delta > 0 if comparison is None else delta == distance

        return directional
    if mode in ("rows", "cols", "manhattan", "euclidean", "king", "areas"):
        distances = _area_distances(board) if mode == "areas" else {}

        def value(first: Square, second: Square) -> int:
            row_gap, col_gap = abs(first.row - second.row), abs(first.col - second.col)
            if mode == "rows":
                return row_gap
            if mode == "cols":
                return col_gap
            if mode == "manhattan":
                return row_gap + col_gap
            if mode == "euclidean":
                return row_gap * row_gap + col_gap * col_gap
            if mode == "king":
                return max(row_gap, col_gap)
            return distances[board.region_of(first), board.region_of(second)]

        assert distance is not None
        threshold = distance * distance if mode == "euclidean" else distance

        def compared(first: Square, second: Square) -> bool:
            actual = value(first, second)
            if comparison == "=":
                return actual == threshold
            if comparison == "<=":
                return actual <= threshold
            assert comparison == ">="
            return actual >= threshold

        return compared
    if mode == "knight":
        return knight_move
    if mode == "furthest":
        return lambda first, second: first != second
    raise ValueError(f"unknown dir mode {mode!r}")


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


def occupant_condition_sources(name: str) -> dict[str, str]:
    """Name the proof sources of one conditional occupancy declaration."""
    return {
        "impossible": f"{name} cannot be satisfied",
        "trigger_state": f"{name} trigger state",
        "trigger": f"{name} trigger count",
        "condition_state": f"{name} condition state",
        "count": f"{name} occupant count",
        "implication": f"{name} applies only when triggered",
    }


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
    sources = occupant_condition_sources(name)
    # A count above the number of squares can never be met, e.g. in an area that is all blocked.
    allowed = frozenset(n for n in allowed_counts if 0 <= n <= len(occupants))
    if not triggers:
        return
    if not allowed:
        model.constrain(
            sources["impossible"],
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
        sources["trigger_state"],
        Kind.EXACTLY_ONE,
        [active, inactive],
        defines=trigger_var,
        family="conditional occupancy",
    )
    model.constrain(
        sources["trigger"],
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
        sources["condition_state"],
        Kind.EXACTLY_ONE,
        [valid, invalid],
        defines=condition_var,
        family="conditional occupancy",
    )
    model.constrain(
        sources["count"],
        Kind.COUNT,
        occupants,
        allowed_counts=allowed,
        reified_by=valid,
        family="conditional occupancy",
    )
    model.constrain(
        sources["implication"],
        Kind.AT_MOST_ONE,
        [active, invalid],
        family="conditional occupancy",
    )


def compile_board(board: Board) -> Model:
    """Compile the fixed layout, role declarations and conditional marks."""
    model = Model()
    _add_board_rules(model, board)
    _add_roles(model, board)
    for mark in board.marks:
        if mark.occupant_condition is not None:
            _compile_mark_occupant_condition(model, board, mark, mark.occupant_condition)
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


def _compile_area_population(
    model: Model,
    board: Board,
    conditions: Sequence[AreaPopulationCondition],
    *,
    provenance: Callable[[AreaPopulationCondition, set[int], set[int]], None] | None = None,
) -> None:
    """Lower recognised strict-extreme and tied-area population expressions.

    "This area holds at least k people" is a hidden Boolean per area and k, so
    one comparison between two areas costs one implication per k and stays sound
    for any board, however many people or areas it has.
    """
    if not conditions:
        return
    maximum = len(board.people)
    occupants: dict[str, list[int]] = {
        region: [
            model.literal(person, square)
            for person in board.people
            for square in sorted(board.free)
            if board.region_of(square) == region
        ]
        for region in board.region_names
    }
    usable = [region for region in sorted(board.region_names) if occupants[region]]
    levels: dict[tuple[str, int], tuple[int, int]] = {}
    level_origins: dict[tuple[str, int], tuple[set[int], set[int]]] = {}
    comparisons: dict[tuple[str, str], tuple[set[int], set[int]]] = {}
    equalities: dict[frozenset[str], tuple[set[int], set[int]]] = {}

    def area_name(region: str) -> str:
        name = board.region_names[region]
        if list(board.region_names.values()).count(name) > 1:
            return f"{name} ({region})"
        return name

    def level(region: str, k: int, constraints: set[int], steps: set[int]) -> tuple[int, int]:
        """(the area holds at least k people, the area holds fewer than k)."""
        if (region, k) not in levels:
            constraint_start, step_start = len(model.constraints), len(model.log)
            name = area_name(region)
            _variable, is_at_least, is_below = _hidden_boolean(
                model,
                f"{POPULATION_PREFIX}_{region}_{k}",
                f"{name} holds at least {k}",
                POPULATION_FAMILY,
            )
            if k > len(occupants[region]):
                model.assign(
                    is_below,
                    POPULATION_FAMILY,
                    f"{name} cannot hold {k} people",
                    sources=(f"{name} has {len(occupants[region])} free squares",),
                )
            else:
                model.constrain(
                    f"{name} holds at least {k}",
                    Kind.COUNT,
                    occupants[region],
                    allowed_counts=set(range(k, len(occupants[region]) + 1)),
                    reified_by=is_at_least,
                    family=POPULATION_FAMILY,
                )
            levels[region, k] = (is_at_least, is_below)
            level_origins[region, k] = (
                set(range(constraint_start, len(model.constraints))),
                set(range(step_start, len(model.log))),
            )
        source_constraints, source_steps = level_origins[region, k]
        constraints.update(source_constraints)
        steps.update(source_steps)
        return levels[region, k]

    def above(more: str, fewer: str) -> tuple[set[int], set[int]]:
        """`more` holds strictly more people than `fewer`."""
        if (more, fewer) in comparisons:
            return comparisons[more, fewer]
        constraint_start, step_start = len(model.constraints), len(model.log)
        constraints: set[int] = set()
        steps: set[int] = set()
        more_name, fewer_name = area_name(more), area_name(fewer)
        # A nonnegative population is at least zero, so the greater one is nonempty.
        at_least_one, _ = level(more, 1, constraints, steps)
        model.constrain(
            f"{more_name} outnumbers {fewer_name}: nonempty",
            Kind.EXACTLY_ONE,
            [at_least_one],
            family=POPULATION_FAMILY,
        )
        for k in range(1, maximum + 1):
            at_least, below = level(fewer, k, constraints, steps)
            if k == maximum:
                model.assign(
                    below,
                    POPULATION_FAMILY,
                    f"{fewer_name} holds fewer than {k}",
                    sources=(f"{more_name} holds more",),
                )
                continue
            _, short = level(more, k + 1, constraints, steps)
            model.constrain(
                f"{more_name} outnumbers {fewer_name} at level {k}",
                Kind.AT_MOST_ONE,
                [at_least, short],
                family=POPULATION_FAMILY,
            )
        constraints.update(range(constraint_start, len(model.constraints)))
        steps.update(range(step_start, len(model.log)))
        comparisons[more, fewer] = constraints, steps
        return constraints, steps

    def same(first: str, second: str) -> tuple[set[int], set[int]]:
        """`first` and `second` hold the same number of people."""
        pair = frozenset((first, second))
        if pair in equalities:
            return equalities[pair]
        constraint_start, step_start = len(model.constraints), len(model.log)
        constraints: set[int] = set()
        steps: set[int] = set()
        for k in range(1, maximum + 1):
            up, _ = level(first, k, constraints, steps)
            _, short = level(second, k, constraints, steps)
            model.constrain(
                f"{area_name(first)} and {area_name(second)} agree on {k}",
                Kind.AT_MOST_ONE,
                [up, short],
                family=POPULATION_FAMILY,
            )
            up, _ = level(second, k, constraints, steps)
            _, short = level(first, k, constraints, steps)
            model.constrain(
                f"{area_name(second)} and {area_name(first)} agree on {k}",
                Kind.AT_MOST_ONE,
                [up, short],
                family=POPULATION_FAMILY,
            )
        constraints.update(range(constraint_start, len(model.constraints)))
        steps.update(range(step_start, len(model.log)))
        equalities[pair] = constraints, steps
        return constraints, steps

    def include(
        dependencies: tuple[set[int], set[int]], constraints: set[int], steps: set[int]
    ) -> None:
        constraints.update(dependencies[0])
        steps.update(dependencies[1])

    for condition in conditions:
        condition_constraints: set[int] = set()
        condition_steps: set[int] = set()
        named = condition.regions
        others = [region for region in usable if region not in named]
        for first, second in combinations(named, 2):
            include(same(first, second), condition_constraints, condition_steps)
        for region in named:
            for other in others:
                if AREA_POPULATION[condition.kind] == "most":
                    include(above(region, other), condition_constraints, condition_steps)
                else:
                    include(above(other, region), condition_constraints, condition_steps)
        if provenance is not None:
            provenance(condition, condition_constraints, condition_steps)


def _compile_quantified_condition(
    model: Model, board: Board, condition: QuantifiedCondition
) -> None:
    if condition.subject_selector is not None:
        _compile_selector_subject_condition(model, board, condition)
        return
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
    allowed = (
        {condition.companions} if condition.kind == "alone_with" else range(1, len(witnesses) + 1)
    )
    model.constrain(
        condition.label,
        Kind.COUNT,
        witnesses,
        allowed_counts=allowed,
        family="quantified target",
    )


def _compile_selector_subject_condition(
    model: Model, board: Board, condition: QuantifiedCondition
) -> None:
    """At least one ordered pair of people matches subject, target and relation.

    When both selectors name cells (objects, areas, marks, lines, ...), the
    clue is only about which squares are taken: each fitting pair of squares
    gets a witness that is true exactly when both are occupied. Otherwise each
    ordered pair of people gets a witness relation.
    """
    subject_selector = condition.subject_selector
    assert subject_selector is not None
    if subject_selector.kind in CELL_SELECTOR_KINDS and condition.selector.kind in (
        CELL_SELECTOR_KINDS
    ):
        _compile_cell_pair_condition(model, board, condition)
        return
    witnesses: list[int] = []
    for first in board.people:
        for second in board.people:
            if first == second:
                continue
            role_variable = (
                board.role_variable(second, condition.selector.name)
                if condition.selector.kind == "role"
                else None
            )
            variable, is_match, _ = _hidden_boolean(
                model,
                "target_witness",
                f"{condition.label} witness {first} {second}",
                "target witness",
            )
            witnesses.append(is_match)
            variables: tuple[str, ...] = (first, second, variable)
            if role_variable is not None:
                variables = (first, second, role_variable, variable)

            def holds(
                *values: Any,
                subject: str = first,
                candidate: str = second,
                has_role_var: str | None = role_variable,
            ) -> bool:
                if has_role_var is not None:
                    subject_square, candidate_square, has_role, witness = values
                    role_values = {(candidate, condition.selector.name): has_role}
                else:
                    subject_square, candidate_square, witness = values
                    role_values = {}
                selected = _target_matches(
                    board, subject_selector, subject, subject_square, role_values
                )
                expected = (
                    selected
                    and condition.pair_state(
                        board, subject_square, candidate, candidate_square, role_values
                    )[0]
                )
                return bool(witness == expected)

            model.relate(f"{condition.label} witness {first} {second}", variables, holds)
    model.constrain(
        condition.label,
        Kind.COUNT,
        witnesses,
        allowed_counts=range(1, len(witnesses) + 1),
        family="quantified target",
    )


CELL_SELECTOR_KINDS = frozenset(
    {"area", "tag", "object_kind", "object", "mark", "edge_item", "point_object", "rows", "columns"}
)


def _compile_cell_pair_condition(
    model: Model, board: Board, condition: QuantifiedCondition
) -> None:
    assert condition.subject_selector is not None and condition.pair_test is not None
    _compile_cell_pair_scopes(
        model,
        board,
        condition.label,
        set(_selector_cells(board, condition.subject_selector)),
        set(_selector_cells(board, condition.selector)),
        condition.pair_test,
    )


def _compile_cell_pair_scopes(
    model: Model,
    board: Board,
    label: str,
    first_scope: set[Square],
    second_scope: set[Square],
    pair_test: PairTest,
) -> None:
    free = set(board.free)
    firsts = sorted(first_scope & free)
    seconds = sorted(second_scope & free)
    witnesses: list[int] = []
    for first in firsts:
        for second in seconds:
            if first == second or not pair_test(first, second):
                continue
            _, is_match, _ = _hidden_boolean(
                model,
                "target_witness",
                f"{label} witness {first} {second}",
                "target witness",
            )
            occupants = [model.literal(person, square) for person in board.people
                         for square in (first, second)]  # fmt: skip
            model.constrain(
                f"{label} witness {first} {second}",
                Kind.COUNT,
                occupants,
                allowed_counts={2},
                reified_by=is_match,
                family="quantified target",
            )
            witnesses.append(is_match)
    if not witnesses:
        raise ValueError(f"clue {label!r} can never hold on this board")
    model.constrain(
        label,
        Kind.COUNT,
        witnesses,
        allowed_counts=range(1, len(witnesses) + 1),
        family="quantified target",
    )


def mark_occupant_name(mark: CellMark, region: str) -> str:
    """The shared source name for a mark's occupancy effect in an area."""
    return f"mark {mark.name} {mark.occupant_condition} in {region}"


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
            mark_occupant_name(mark, board.region_names[region]),
            triggers,
            occupants,
            _occupant_counts(condition, len(board.people)),
        )


@dataclass(frozen=True)
class BoardRule:
    """One constraint every Murdoku has, and what it is `about`:
    ('person', name), ('square', Square), ('row', i) or ('col', i), 0-based.

    `compile_board` builds the model from these, so a reader can look a
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
    count_progress: Sequence[tuple[str, tuple[int, ...]]] = (),
    count_scope: Iterable[Square] = (),
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
    active_count_ids = {
        constraint_id
        for _, constraint_ids in count_progress
        for constraint_id in constraint_ids
        if model.constraints[constraint_id].name in active_sources
    }
    active_count_scope = set(count_scope) if active_count_ids else set()
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
                tint = NEW if person in placed or sq in active_count_scope else INK
                body = f"{tint}{person[:3]:^4}"
            elif sq in active_count_scope:
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
    out += _count_progress(model, count_progress, active_count_ids)
    if active_count_scope:
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


def _count_progress(
    model: Model, progress: Sequence[tuple[str, tuple[int, ...]]], active: set[int]
) -> list[str]:
    if not progress:
        return []
    lines = ["  global counts:"]
    for description, constraint_ids in progress:
        for part, constraint_id in enumerate(constraint_ids, 1):
            constraint = model.constraints[constraint_id]
            current = sum(model.is_true(literal) for literal in constraint.literals)
            undecided = len(model.live(constraint_id))
            feasible = model.feasible_counts(constraint_id)
            possible = ",".join(map(str, sorted(feasible))) or "none"
            additional = sorted(count - current for count in feasible)
            if not additional:
                needed = "none"
            elif additional[0] == additional[-1]:
                needed = f"{additional[0]} more"
            else:
                needed = f"{additional[0]}..{additional[-1]} more"
            allowed = ",".join(map(str, sorted(constraint.allowed_counts)))
            marker = NEW if constraint_id in active else INK
            suffix = f" (part {part}/{len(constraint_ids)})" if len(constraint_ids) > 1 else ""
            lines.append(
                f"    {marker}{description}{suffix}: {current} true, {undecided} open; "
                f"need {needed}, possible {possible}, allowed {allowed}{RESET}"
            )
        if not constraint_ids:
            lines.append(f"    {INK}{description}{RESET}")
    return lines


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
    """Describe live squares and conservative region-overlap companions."""
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
