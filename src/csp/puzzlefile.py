"""Reader for the sectioned puzzle-file format used by all but plain Sudoku.

A file is a series of `Section:` headers, each followed by its lines. A
one-line section can be written inline before the first header, as in
`Size: 7`. Blank lines and `#` comments are ignored everywhere.
"""

import re

from .murdoku import Board, BoardObject, Clue, ObjectKind, Square

KINDS = ("sudoku", "murdoku", "calcudoku", "futoshiki")


def detect(text: str) -> str:
    """Which puzzle family a file holds, from its sections."""
    if "Cages:" in text:
        return "calcudoku"
    if "Signs:" in text:
        return "futoshiki"
    return "murdoku" if "Regions:" in text else "sudoku"


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

    if "Furniture" in section:
        raise ValueError("Furniture: is no longer supported; use Objects: with kind 'standable'")
    objects = _object_placements(section.get("Objects", []))
    doors = _door_placements(section.get("Doors", []))

    people = list(section["People"])

    groups = {}
    for line in section.get("Groups", []):
        name, _, members = line.partition(":")
        groups[name.strip()] = members.split()

    clues = _clues(section.get("Clues", []))

    board = Board(
        size,
        grid,
        region_names,
        objects,
        people,
        groups=groups,
        colours=colours,
        doors=doors,
    )
    board.region_ids(groups)  # fails now, not mid-solve, if a group names an unknown region
    board.hatched = board.region_ids(
        name for line in section.get("Hatched", []) for name in line.split()
    )
    board.rules = _clues(section.get("Rules", []))
    return board, clues


def _clues(lines: list[str]) -> list[Clue]:
    """'next_to Tim klimwand' lines -> [('next_to', ['Tim', 'klimwand'])]."""
    return [(kind, args) for kind, *args in (line.split() for line in lines)]


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


def _door_placements(lines: list[str]) -> dict[str, list[tuple[Square, Square]]]:
    """Read edges such as 'front: r2c3-r2c4 r5c1-r5c2'."""
    doors: dict[str, list[tuple[Square, Square]]] = {}
    for line in lines:
        name, separator, positions = line.partition(":")
        if not separator or not name.strip():
            raise ValueError(f"bad door {line!r}, expected 'name: r1c1-r1c2'")
        edges = doors.setdefault(name.strip(), [])
        for token in positions.split():
            first, edge, second = token.partition("-")
            if not edge or not first or not second:
                raise ValueError(f"bad door edge {token!r}, expected 'r1c1-r1c2'")
            edges.append((parse_square(first), parse_square(second)))
    return doors
