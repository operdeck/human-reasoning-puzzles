"""Reader for the sectioned puzzle-file format used by all but plain Sudoku.

A file is a series of `Section:` headers, each followed by its lines. A
one-line section can be written inline before the first header, as in
`Size: 7`. Blank lines and `#` comments are ignored everywhere.
"""

import re
from dataclasses import dataclass, field

from .murdoku import (
    Board,
    BoardObject,
    CellMark,
    Clue,
    CornerObject,
    EdgeItem,
    EdgeItemKind,
    ObjectKind,
    OccupantCondition,
    PronounSet,
    RoleSpec,
    Square,
)

KINDS = (
    "sudoku",
    "murdoku",
    "calcudoku",
    "futoshiki",
    "queens",
    "suguru",
    "logicgrid",
    "starbattle",
    "binairo",
    "tents",
    "minesweeper",
    "akari",
    "kakurasu",
    "battleships",
)

FAMILY_KINDS = {
    "queens": "queens",
    "suguru": "suguru",
    "tectonic": "suguru",
    "logicgrid": "logicgrid",
    "starbattle": "starbattle",
    "binairo": "binairo",
    "tango": "binairo",
    "tents": "tents",
    "minesweeper": "minesweeper",
    "akari": "akari",
    "lightup": "akari",
    "kakurasu": "kakurasu",
    "battleships": "battleships",
}


def detect(text: str) -> str:
    """Which puzzle family a file holds, from its sections."""
    section = read_sections(text)
    if "Family" in section:
        if len(section["Family"]) != 1:
            raise ValueError("Family: must name exactly one puzzle family")
        family = section["Family"][0].casefold()
        if family not in FAMILY_KINDS:
            raise ValueError(f"unknown puzzle family {family!r}")
        return FAMILY_KINDS[family]
    if "Cages" in section:
        return "calcudoku"
    if "Signs" in section:
        return "futoshiki"
    return "murdoku" if "Regions" in section else "sudoku"


def read_sections(text: str) -> dict[str, list[str]]:
    """Section name -> its non-blank, non-comment lines."""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(":") and " " not in line[:-1]:
            current = line[:-1]
            out[current] = []
        elif current is not None:
            out[current].append(line)
        else:
            head, _, rest = line.partition(":")
            if rest.strip():
                out[head.strip()] = [rest.strip()]
    return out


def parse_square(token: str) -> Square:
    """'r2c5' -> Square(1, 4)."""
    match = re.fullmatch(r"r(\d+)c(\d+)", token.strip().lower())
    if match is None:
        raise ValueError(f"bad square {token!r}, expected like r2c5")
    return Square(int(match[1]) - 1, int(match[2]) - 1)


def load_board(text: str) -> tuple[Board, list[Clue]]:
    """Read a Murdoku puzzle file into its board and its list of clues."""
    section = read_sections(text)
    for required in ("Size", "Regions", "Grid", "People"):
        if required not in section:
            raise ValueError(f"puzzle file is missing a {required}: section")

    size = int(section["Size"][0])

    region_names = {}
    colours = {}
    for line in section["Regions"]:
        rid, _, rest = line.partition(":")
        name, *colour = rest.split()
        region_names[rid.strip()] = name
        if colour:
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour[0]):
                raise ValueError(f"region {name}: colour {colour[0]!r} is not like #F4CBC3")
            colours[rid.strip()] = colour[0].upper()

    grid = [line.split() for line in section["Grid"]]
    if len(grid) != size or any(len(row) != size for row in grid):
        raise ValueError(f"Grid is not {size}x{size}")
    unknown = {r for row in grid for r in row} - set(region_names)
    if unknown:
        raise ValueError(f"Grid uses region ids with no name: {sorted(unknown)}")

    if "Groups" in section:
        raise ValueError("Groups: is no longer supported; use AreaTags:")
    area_tags: dict[str, list[str]] = {}
    for line in section.get("AreaTags", []):
        tag, separator, names = line.partition(":")
        members = names.split()
        if not separator or not tag.strip() or not members:
            raise ValueError(f"bad area tag {line!r}, expected 'tag: region_name ...'")
        if tag.strip() in area_tags:
            raise ValueError(f"area tag {tag.strip()!r} is defined more than once")
        area_tags[tag.strip()] = members

    if "Furniture" in section:
        raise ValueError("Furniture: is no longer supported; use Objects: with kind 'standable'")
    if "Doors" in section:
        raise ValueError("Doors: is no longer supported; use EdgeItems:")
    objects = _object_placements(section.get("Objects", []))
    edge_items = _edge_item_placements(section.get("EdgeItems", []))
    corner_objects = _corner_object_placements(section.get("CornerObjects", []))
    marks = _mark_placements(section.get("Marks", []))

    people = list(section["People"])
    attributes = _attribute_placements(section.get("Attributes", []), people)
    pronouns = _pronoun_placements(section.get("Pronouns", []), people)
    role_eligibility = _role_eligibility(section.get("RoleEligibility", []), attributes)
    roles = _role_placements(section.get("Roles", []), people, role_eligibility)

    clues = _clues(section.get("Clues", []))

    board = Board(
        size,
        grid,
        region_names,
        objects,
        people,
        area_tags=area_tags,
        colours=colours,
        edge_items=edge_items,
        corner_objects=corner_objects,
        marks=marks,
        roles=roles,
        attributes=attributes,
        pronouns=pronouns,
    )
    board.hatched = board.area_ids(
        name for line in section.get("Hatched", []) for name in line.split()
    )
    board.rules = _clues(section.get("Rules", []))
    return board, clues


def _clues(lines: list[str]) -> list[Clue]:
    """'next_to Tim klimwand' lines -> [('next_to', ['Tim', 'klimwand'])]."""
    return [(kind, args) for kind, *args in (_split_clue(line)[0].split() for line in lines)]


def _split_clue(line: str) -> tuple[str, str]:
    """'next_to Tim bank | Tim zit bij de bank' -> clue part and optional booklet wording."""
    clue, _, wording = line.partition("|")
    return clue, wording.strip()


def _object_placements(lines: list[str]) -> list[BoardObject]:
    """Read explicit object kinds and one connected footprint per declaration."""
    objects: list[BoardObject] = []
    kinds: dict[str, ObjectKind] = {}
    for line in lines:
        name, separator, definition = line.partition(":")
        parts = definition.split()
        if not separator or not name.strip():
            raise ValueError(f"bad object {line!r}, expected 'name: kind r1c1 ...'")
        if not parts or parts[0] not in ("blocking", "standable"):
            raise ValueError(f"object {name.strip()!r} must declare kind 'blocking' or 'standable'")
        kind: ObjectKind = parts[0]  # type: ignore[assignment]
        if name.strip() in kinds and kinds[name.strip()] != kind:
            raise ValueError(f"object type {name.strip()!r} has conflicting kinds")
        kinds[name.strip()] = kind
        if len(parts) == 1:
            raise ValueError(f"object {name.strip()!r} needs at least one cell")
        objects.append(BoardObject(name.strip(), kind, tuple(parse_square(t) for t in parts[1:])))
    return objects


def _edge_item_placements(lines: list[str]) -> list[EdgeItem]:
    """Read named door pairs and window inside-cells; repeated names compose simple items."""
    items: list[EdgeItem] = []
    for line in lines:
        name, separator, definition = line.partition(":")
        parts = definition.split()
        if not separator or not name.strip():
            raise ValueError(f"bad edge item {line!r}, expected 'name: door|window r1c1 ...'")
        if not parts or parts[0] not in ("door", "window"):
            raise ValueError(f"edge item {name.strip()!r} must declare kind 'door' or 'window'")
        kind: EdgeItemKind = parts[0]  # type: ignore[assignment]
        cells = tuple(parse_square(token) for token in parts[1:])
        items.append(EdgeItem(name.strip(), kind, cells))
    return items


def _corner_object_placements(lines: list[str]) -> list[CornerObject]:
    """Read corner objects by listing their four surrounding cells."""
    items: list[CornerObject] = []
    for line in lines:
        name, separator, positions = line.partition(":")
        if not separator or not name.strip():
            raise ValueError(f"bad corner object {line!r}, expected 'name: r1c1 r1c2 r2c1 r2c2'")
        items.append(
            CornerObject(name.strip(), tuple(parse_square(token) for token in positions.split()))
        )
    return items


def _mark_placements(lines: list[str]) -> list[CellMark]:
    """Read named cell sets with optional `; alone` or `; not_alone` conditions."""
    marks: list[CellMark] = []
    for line in lines:
        name, separator, definition = line.partition(":")
        cells_text, condition_separator, condition_text = definition.partition(";")
        tokens = cells_text.split()
        condition: OccupantCondition | None = None
        if condition_separator:
            condition_text = condition_text.strip()
            if condition_text == "alone":
                condition = "alone"
            elif condition_text == "not_alone":
                condition = "not_alone"
            else:
                raise ValueError(f"bad occupant condition in mark {line!r}; use alone or not_alone")
        if not separator or not name.strip() or not tokens:
            raise ValueError(f"bad mark {line!r}, expected 'name: r1c1 ... [; alone|not_alone]'")
        marks.append(
            CellMark(name.strip(), tuple(parse_square(token) for token in tokens), condition)
        )
    return marks


def _role_eligibility(
    lines: list[str], attributes: dict[str, frozenset[str]]
) -> dict[str, frozenset[str]]:
    """Read eligibility lists, expanding `attribute:name` selectors."""
    eligibility: dict[str, frozenset[str]] = {}
    for line in lines:
        role, separator, people = line.partition(":")
        names: set[str] = set()
        for token in people.split():
            if token.startswith("attribute:"):
                attribute = token.partition(":")[2]
                if attribute not in attributes:
                    raise ValueError(f"RoleEligibility names unknown attribute {attribute!r}")
                names.update(attributes[attribute])
            elif token.startswith("person:"):
                names.add(token.partition(":")[2])
            else:
                names.add(token)
        if not separator or not role.strip() or not names:
            raise ValueError(
                f"bad RoleEligibility entry {line!r}, expected 'role: person ...' "
                "or 'attribute:name'"
            )
        if role.strip() in eligibility:
            raise ValueError(f"role {role.strip()!r} eligibility is defined more than once")
        eligibility[role.strip()] = frozenset(names)
    return eligibility


def _attribute_placements(lines: list[str], people: list[str]) -> dict[str, frozenset[str]]:
    """Read `attribute: person ...` declarations; unlisted people do not have it."""
    attributes: dict[str, frozenset[str]] = {}
    for line in lines:
        attribute, separator, members = line.partition(":")
        holders = frozenset(members.split())
        if not separator or not attribute.strip() or not holders:
            raise ValueError(f"bad attribute {line!r}, expected 'attribute: person ...'")
        if attribute.strip() in attributes:
            raise ValueError(f"attribute {attribute.strip()!r} is defined more than once")
        unknown = holders - set(people)
        if unknown:
            raise ValueError(
                f"attribute {attribute.strip()!r} names unknown people {sorted(unknown)}"
            )
        attributes[attribute.strip()] = holders
    return attributes


def _pronoun_placements(lines: list[str], people: list[str]) -> dict[str, PronounSet]:
    """Read `person: subject object possessive` wording overrides."""
    pronouns: dict[str, PronounSet] = {}
    for line in lines:
        person, separator, forms = line.partition(":")
        tokens = forms.split()
        if not separator or not person.strip() or len(tokens) != 3:
            raise ValueError(f"bad pronouns {line!r}, expected 'person: subject object possessive'")
        if person.strip() not in people:
            raise ValueError(f"pronouns name unknown person {person.strip()!r}")
        if person.strip() in pronouns:
            raise ValueError(f"pronouns for {person.strip()!r} are defined more than once")
        pronouns[person.strip()] = PronounSet(*tokens)
    return pronouns


def _role_placements(
    lines: list[str], people: list[str], eligibility: dict[str, frozenset[str]]
) -> list[RoleSpec]:
    """Read role cardinalities and the optional distinct-region modifier."""
    roles: list[RoleSpec] = []
    names = {line.partition(":")[0].strip() for line in lines}
    unknown = set(eligibility) - names
    if unknown:
        raise ValueError(f"RoleEligibility names unknown roles {sorted(unknown)}")
    for line in lines:
        name, separator, definition = line.partition(":")
        tokens = definition.split()
        if not separator or not name.strip():
            raise ValueError(f"bad role {line!r}, expected 'name: [count] [different_regions]'")
        allowed_counts = frozenset(range(len(people) + 1))
        if tokens and tokens[0] in ("any", "*"):
            tokens.pop(0)
        elif tokens and tokens[0].isdigit():
            allowed_counts = frozenset((int(tokens.pop(0)),))
        different_regions = False
        for token in tokens:
            if token == "different_regions" and not different_regions:
                different_regions = True
            else:
                raise ValueError(f"unknown role option {token!r} in {line!r}")
        roles.append(
            RoleSpec(name.strip(), allowed_counts, different_regions, eligibility.get(name.strip()))
        )
    return roles


@dataclass(frozen=True)
class Figure:
    """Optional booklet text and picture for one person; never read by the solver."""

    description: str = ""
    image: str = ""


@dataclass(frozen=True)
class Presentation:
    """Author-written booklet metadata. Absent sections leave the fields empty."""

    title: str = ""
    intro: list[str] = field(default_factory=list)
    question: str = ""
    clue_text: dict[int, str] = field(default_factory=dict)
    figures: dict[str, Figure] = field(default_factory=dict)
    reveal: list[str] = field(default_factory=list)


def load_presentation(text: str) -> Presentation:
    """The optional `Title:`, `Intro:`, `Question:`, `Figures:`, `Reveal:` and clue wordings.

    Presentation never affects parsing, solving or pictures. A clue line may end in
    `| wording` to replace its generated sentence; `Figures:` lines are
    `Name: description [; image=path]`.
    """
    section = read_sections(text)
    people = section.get("People", [])
    clue_text = {
        number: wording
        for number, line in enumerate(section.get("Clues", []), 1)
        if (wording := _split_clue(line)[1])
    }
    figures: dict[str, Figure] = {}
    for line in section.get("Figures", []):
        name, separator, rest = line.partition(":")
        description, _, option = rest.partition(";")
        option = option.strip()
        if not separator or name.strip() not in people:
            raise ValueError(f"Figures names unknown person in {line!r}")
        if option and not option.startswith("image="):
            raise ValueError(f"bad Figures option {option!r}, expected 'image=path'")
        figures[name.strip()] = Figure(description.strip(), option.removeprefix("image=").strip())
    return Presentation(
        title=" ".join(section.get("Title", [])),
        intro=section.get("Intro", []),
        question=" ".join(section.get("Question", [])),
        clue_text=clue_text,
        figures=figures,
        reveal=section.get("Reveal", []),
    )
