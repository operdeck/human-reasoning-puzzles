"""Shared parser for puzzle files with named regions over an N x N grid."""

from dataclasses import dataclass

from .puzzlefile import read_sections


@dataclass(frozen=True)
class RegionGrid:
    size: int
    names: dict[str, str]
    cells: list[list[str]]

    @property
    def cells_by_region(self) -> dict[str, tuple[tuple[int, int], ...]]:
        grouped: dict[str, list[tuple[int, int]]] = {region: [] for region in self.names}
        for row, values in enumerate(self.cells):
            for col, region in enumerate(values):
                grouped[region].append((row, col))
        return {region: tuple(members) for region, members in grouped.items()}


def is_connected(cells: tuple[tuple[int, int], ...]) -> bool:
    """True if the cells form one area joined by shared sides."""
    members = set(cells)
    seen: set[tuple[int, int]] = set()
    todo = [cells[0]]
    while todo:
        row, col = todo.pop()
        if (row, col) in seen:
            continue
        seen.add((row, col))
        todo.extend(
            near
            for near in ((row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1))
            if near in members and near not in seen
        )
    return seen == members


def read_region_grid(
    text: str, families: tuple[str, ...]
) -> tuple[dict[str, list[str]], RegionGrid]:
    """Read a family, size, region names and square region-ID grid."""
    sections = read_sections(text)
    for required in ("Family", "Size", "Regions", "Grid"):
        if required not in sections:
            raise ValueError(f"puzzle file is missing a {required}: section")
    if len(sections["Family"]) != 1 or sections["Family"][0].casefold() not in families:
        expected = " or ".join(repr(family) for family in families)
        raise ValueError(f"Family must be {expected}")
    try:
        size = int(sections["Size"][0])
    except (IndexError, ValueError) as exc:
        raise ValueError("Size must be a positive integer") from exc
    if size < 1:
        raise ValueError("Size must be a positive integer")

    names: dict[str, str] = {}
    for line in sections["Regions"]:
        identifier, separator, name = line.partition(":")
        identifier, name = identifier.strip(), name.strip()
        if (
            not separator
            or not identifier
            or any(char.isspace() for char in identifier)
            or not name
        ):
            raise ValueError(f"bad region {line!r}, expected 'id: name'")
        if identifier in names:
            raise ValueError(f"region ID {identifier!r} is defined more than once")
        names[identifier] = name
    if not names:
        raise ValueError("Regions: must declare at least one region")

    cells = [line.split() for line in sections["Grid"]]
    if len(cells) != size or any(len(row) != size for row in cells):
        raise ValueError(f"Grid is not {size}x{size}")
    used = {region for row in cells for region in row}
    unknown = used - set(names)
    if unknown:
        raise ValueError(f"Grid uses region IDs with no name: {sorted(unknown)}")
    unused = set(names) - used
    if unused:
        raise ValueError(f"Regions are not used by Grid: {sorted(unused)}")
    return sections, RegionGrid(size, names, cells)
