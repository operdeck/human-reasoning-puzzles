"""Murdoku board generator: a short theme spec in, ranked draft boards out.

Each candidate is a board (areas, objects, colours) with an intended placement
of the people that satisfies the spec's late-reveal story and key clues. Hard
filters reject ugly or unfair boards; a soft score ranks the survivors so a
person can choose from pictures. Clues beyond the key clues are not written
unless asked: `close` runs `csp.clue_search suggest` on a chosen draft, and
`thin` removes what is not needed afterwards.

What a clue or rule means is never decided here: placements come from the
Murdoku brute force over the draft file itself.
"""

import base64
import dataclasses
import math
import random
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import svg
from .bruteforce import murdoku as brute
from .murdoku import Square
from .puzzlefile import load_board

Cell = tuple[int, int]
Layout = tuple[tuple[int, ...], ...]

# Every tunable threshold of the hard filters and the score, in one place.
THRESHOLDS: dict[str, float] = {
    "min_area": 4,  # smallest area, in squares, unless the spec says otherwise
    "max_ratio": 3.0,  # largest area at most this many times the smallest
    "max_spur": 1,  # one-square-wide spurs may stick out this many squares
    "perturb_steps": 6,  # border moves tried after a template is drawn
    "layout_attempts": 60,  # layouts tried per candidate before giving up
    "object_attempts": 40,  # object arrangements tried per layout
    "placement_sample": 40,  # placements drawn from the brute force per board
    "legal_sample": 120,  # legal placements drawn to test key clues and occupancy
    "contrast": 60.0,  # RGB distance at which neighbouring colours count as distinct
}
SCORE_WEIGHTS: dict[str, float] = {
    "compactness": 2.0,  # low perimeter for the area's size
    "convexity": 2.0,  # area fills its bounding box
    "balance": 1.0,  # area sizes close to each other
    "borders": 1.0,  # short total border, with a bonus for one deliberate staircase
    "spread": 1.0,  # objects spread over the areas and the board
    "asymmetry": 1.0,  # not an obviously mirrored or turned layout
    "story": 1.0,  # areas run in the spec's north-to-south order
    "colours": 1.0,  # neighbouring areas clearly distinct
    "legibility": 1.0,  # every area has room for its label
}
# Soft, light tints; pictures draw dark ink on them.
PALETTE = (
    "#F4CBC3",
    "#CBE6B9",
    "#C4DCF2",
    "#FADFB5",
    "#E3D0F0",
    "#F7EFA8",
    "#BFE8E0",
    "#F2C6DE",
    "#D9D2C2",
    "#D2E7F7",
    "#E9F2C4",
    "#F6D6B8",
)
GRADES = ("single", "count", "relations", "subsumption", "cover2", "cover3", "chains", "what_if")
SIDES = ((-1, 0), (1, 0), (0, -1), (0, 1))


# --- spec --------------------------------------------------------------------


@dataclass(frozen=True)
class ObjectSpec:
    """`count` straight footprints of `length` squares, optionally kept in one area.

    An `across` object (a tunnel, a bridge) instead straddles one border: its
    squares lie in exactly two areas, and it touches no third.
    """

    name: str
    kind: str
    count: int = 1
    length: int = 1
    area: str | None = None
    across: bool = False


@dataclass(frozen=True)
class Spec:
    theme: str
    size: int
    areas: tuple[str, ...]
    people: tuple[str, ...]
    language: str = "en"
    colours: Mapping[str, str] = field(default_factory=dict)
    late: str | None = None
    companions: tuple[str, ...] = ()
    companion_trait: str = "companion"
    objects: tuple[ObjectSpec, ...] = ()
    key_clues: tuple[str, ...] = ()
    template: str = "auto"
    candidates: int = 20
    keep: int = 5
    seed: int = 1
    min_area: int = int(THRESHOLDS["min_area"])
    max_ratio: float = THRESHOLDS["max_ratio"]

    def __post_init__(self) -> None:
        if not 4 <= self.size <= 12:
            raise ValueError("size must be between 4 and 12")
        if len(self.areas) < 2:
            raise ValueError("a board needs at least two areas")
        if len(set(self.areas)) != len(self.areas):
            raise ValueError("area names must differ")
        if not self.people or len(self.people) > self.size:
            raise ValueError(f"between 1 and {self.size} people are needed")
        if len(set(self.people)) != len(self.people):
            raise ValueError("people must differ")
        if self.template not in ("auto", *TEMPLATES):
            raise ValueError(f"template must be auto or one of {', '.join(TEMPLATES)}")
        for name in self.colours:
            if name not in self.areas:
                raise ValueError(f"colour for unknown area {name!r}")
        if self.late is not None and self.late not in self.people:
            raise ValueError(f"late figure {self.late!r} is not among the people")
        if self.companions and self.late is None:
            raise ValueError("companions need a late figure")
        for person in self.companions:
            if person not in self.people or person == self.late:
                raise ValueError(f"companion {person!r} must be one of the other people")
        for obj in self.objects:
            if obj.kind not in ("blocking", "standable"):
                raise ValueError(f"object {obj.name!r}: kind must be blocking or standable")
            if obj.count < 1 or obj.length < 1:
                raise ValueError(f"object {obj.name!r}: count and size must be positive")
            if obj.area is not None and obj.area not in self.areas:
                raise ValueError(f"object {obj.name!r}: unknown area {obj.area!r}")
            if obj.across and (obj.area is not None or obj.length < 2):
                raise ValueError(f"object {obj.name!r}: across needs size 2+ and no area")
        for clue in self.key_clues:
            if self.late is not None and self.late in clue.split():
                raise ValueError(f"key clue {clue!r} names the late figure {self.late}")


def read_spec(text: str) -> Spec:
    """A spec from `key: value` lines; `object:` and `key_clue:` may repeat.

    `object: bank standable x2 size 2 in Hue` asks for two standable benches of two
    squares in area Hue. `colours: Hanoi=#F4CBC3` fixes area colours. `#` starts a
    comment.
    """
    values: dict[str, str] = {}
    objects: list[ObjectSpec] = []
    clues: list[str] = []
    for raw in text.splitlines():
        # A comment is `#` at the start or after a space, but not a colour like `=#F4CBC3`.
        line = re.sub(r"(?:^|\s)#(?![0-9A-Fa-f]{6}\b).*$", "", raw).strip()
        if not line:
            continue
        key, colon, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if not colon or not value:
            raise ValueError(f"spec line {raw!r} is not 'key: value'")
        if key == "object":
            objects.append(_object_spec(value))
        elif key == "key_clue":
            clues.append(value)
        elif key in values:
            raise ValueError(f"spec key {key!r} given twice")
        else:
            values[key] = value
    known = {
        "theme",
        "size",
        "language",
        "areas",
        "colours",
        "people",
        "late",
        "companions",
        "companion_trait",
        "template",
        "candidates",
        "keep",
        "seed",
        "min_area",
        "max_ratio",
    }
    if unknown := set(values) - known:
        raise ValueError(f"unknown spec keys: {', '.join(sorted(unknown))}")
    for required in ("theme", "size", "areas", "people"):
        if required not in values:
            raise ValueError(f"spec needs '{required}:'")
    people = values["people"].split()
    late = values.get("late")
    if late and late not in people:
        people.append(late)
    colours = {}
    for item in values.get("colours", "").split():
        area, _, colour = item.partition("=")
        if not colour.startswith("#") or len(colour) != 7:
            raise ValueError(f"colour {item!r} is not like Area=#F4CBC3")
        colours[area] = colour.upper()
    return Spec(
        theme=values["theme"],
        size=int(values["size"]),
        areas=tuple(values["areas"].split()),
        people=tuple(people),
        language=values.get("language", "en"),
        colours=colours,
        late=late,
        companions=tuple(values.get("companions", "").split()),
        companion_trait=values.get("companion_trait", "companion"),
        objects=tuple(objects),
        key_clues=tuple(clues),
        template=values.get("template", "auto"),
        candidates=int(values.get("candidates", 20)),
        keep=int(values.get("keep", 5)),
        seed=int(values.get("seed", 1)),
        min_area=int(values.get("min_area", THRESHOLDS["min_area"])),
        max_ratio=float(values.get("max_ratio", THRESHOLDS["max_ratio"])),
    )


def _object_spec(value: str) -> ObjectSpec:
    name, kind, *rest = value.split()
    count, length, area, across = 1, None, None, False
    words = iter(rest)
    for word in words:
        if word.startswith("x") and word[1:].isdigit():
            count = int(word[1:])
        elif word == "size":
            length = int(next(words))
        elif word == "in":
            area = next(words)
        elif word == "across":
            across = True
        else:
            raise ValueError(f"object {value!r}: unexpected {word!r}")
    default = 2 if across else 1
    return ObjectSpec(name, kind, count, default if length is None else length, area, across)


# --- area geometry -------------------------------------------------------------


def area_cells(layout: Layout) -> dict[int, set[Cell]]:
    out: dict[int, set[Cell]] = {}
    for r, row in enumerate(layout):
        for c, area in enumerate(row):
            out.setdefault(area, set()).add((r, c))
    return out


def _neighbours(cell: Cell, size: int) -> Iterable[Cell]:
    r, c = cell
    for dr, dc in SIDES:
        if 0 <= r + dr < size and 0 <= c + dc < size:
            yield r + dr, c + dc


def _connected(cells: set[Cell], size: int) -> bool:
    if not cells:
        return True
    start = next(iter(cells))
    seen = {start}
    stack = [start]
    while stack:
        for nb in _neighbours(stack.pop(), size):
            if nb in cells and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen == cells


def _in_block(cell: Cell, cells: set[Cell]) -> bool:
    """Whether the square lies in a 2x2 block of the same area."""
    r, c = cell
    return any(
        {(r + dr, c + dc), (r + dr, c), (r, c + dc)} <= cells for dr in (-1, 1) for dc in (-1, 1)
    )


def _longest_spur(cells: set[Cell], size: int) -> int:
    """The longest one-square-wide run sticking out of a wider part of the area."""
    if not any(_in_block(cell, cells) for cell in cells):
        return 0
    longest = 0
    for cell in cells:
        if sum(nb in cells for nb in _neighbours(cell, size)) != 1:
            continue
        length, previous, current = 0, None, cell
        while not _in_block(current, cells):
            length += 1
            onward = [nb for nb in _neighbours(current, size) if nb in cells and nb != previous]
            if len(onward) != 1:
                break
            previous, current = current, onward[0]
        longest = max(longest, length)
    return longest


def _straight(cells: set[Cell]) -> bool:
    return len({r for r, _ in cells}) == 1 or len({c for _, c in cells}) == 1


def area_problems(
    layout: Layout, min_area: int, max_ratio: float, max_spur: int | None = None
) -> list[str]:
    """Why a layout fails the hard area filters; empty when it passes."""
    size = len(layout)
    spur_limit = int(THRESHOLDS["max_spur"]) if max_spur is None else max_spur
    areas = area_cells(layout)
    problems = []
    for area, cells in sorted(areas.items()):
        if not _connected(cells, size):
            problems.append(f"area {area} is split")
        if len(cells) < min_area:
            problems.append(f"area {area} has only {len(cells)} squares")
        if not any(_in_block(cell, cells) for cell in cells) and not _straight(cells):
            problems.append(f"area {area} is a winding one-square-wide strip")
        elif _longest_spur(cells, size) > spur_limit:
            problems.append(f"area {area} has a spur")
        edge = any(r in (0, size - 1) or c in (0, size - 1) for r, c in cells)
        touching = {
            layout[nr][nc]
            for cell in cells
            for nr, nc in _neighbours(cell, size)
            if layout[nr][nc] != area
        }
        if not edge and len(touching) == 1:
            problems.append(f"area {area} is a pocket inside area {touching.pop()}")
    sizes = [len(cells) for cells in areas.values()]
    if sizes and max(sizes) > max_ratio * min(sizes):
        problems.append(f"area sizes {min(sizes)}..{max(sizes)} differ too much")
    for r in range(size - 1):
        for c in range(size - 1):
            a, b = layout[r][c], layout[r][c + 1]
            d, e = layout[r + 1][c], layout[r + 1][c + 1]
            if (a == e and a != b and a != d) or (b == d and b != a and b != e):
                problems.append(f"squares meet only at a corner near r{r + 1}c{c + 1}")
    return problems


# --- templates ---------------------------------------------------------------


def _split(total: int, parts: int) -> list[int]:
    """Cut points dividing `total` into `parts` nearly equal runs."""
    return [round(total * i / parts) for i in range(1, parts)]


def bands(size: int, count: int, rng: random.Random) -> Layout:
    """Horizontal bands; a border steps one row up or down where both sides stay thick."""
    cuts = _split(size, count)
    heights = [b - a for a, b in zip([0, *cuts], [*cuts, size], strict=True)]
    borders = []
    for i, cut in enumerate(cuts):
        step = rng.choice((-1, 1))
        thinned = i + 1 if step == 1 else i
        if heights[thinned] > 2:
            heights[thinned] -= 1
        else:
            step = 0
        borders.append((cut, step, rng.randrange(2, size - 1)))
    rows = [
        [sum(r >= cut + (step if c >= at else 0) for cut, step, at in borders) for c in range(size)]
        for r in range(size)
    ]
    layout = tuple(tuple(row) for row in rows)
    return tuple(zip(*layout, strict=True)) if rng.random() < 0.5 else layout


def staircase(size: int, count: int, rng: random.Random) -> Layout | None:
    """Bands whose borders all climb one staircase; None when the bands are too thin to step.

    Every band stays at least two squares thick and every step is at least two
    squares from the board edge and from the next step, so no spur appears.
    """
    cuts = _split(size, count)
    heights = [b - a for a, b in zip([0, *cuts], [*cuts, size], strict=True)]
    if min(heights[1:-1], default=2) < 2:
        return None
    low = rng.randrange(0, max(1, heights[0] - 1))
    high = rng.randrange(0, max(1, heights[-1] - 1))
    if low + high == 0:
        if heights[0] > 2:
            low = 1
        elif heights[-1] > 2:
            high = 1
    gaps = list(range(1, size - 2))
    rng.shuffle(gaps)
    steps: list[int] = []
    for gap in gaps:
        if len(steps) < low + high and all(abs(gap - s) >= 2 for s in steps):
            steps.append(gap)
    if not steps:
        return None
    low = min(low, len(steps))
    offsets = [-low + sum(g < c for g in steps) for c in range(size)]
    rows = [[sum(r >= cut + offsets[c] for cut in cuts) for c in range(size)] for r in range(size)]
    layout = tuple(tuple(row) for row in rows)
    if rng.random() < 0.5:
        layout = tuple(tuple(reversed(row)) for row in layout)
    if rng.random() < 0.5:
        layout = tuple(zip(*layout, strict=True))
    return layout


def _seeds(size: int, count: int, rng: random.Random) -> list[Cell]:
    """Spread-out starting squares: the farthest of a few random tries each time."""
    seeds = [(rng.randrange(size), rng.randrange(size))]
    while len(seeds) < count:
        options = [(rng.randrange(size), rng.randrange(size)) for _ in range(12)]
        seeds.append(
            max(options, key=lambda o: min(abs(o[0] - s[0]) + abs(o[1] - s[1]) for s in seeds))
        )
    return seeds


def blobs(size: int, count: int, rng: random.Random) -> Layout:
    """Nearest-seed areas (a Voronoi diagram by steps), with ties broken at random."""
    seeds = _seeds(size, count, rng)
    weights = [rng.uniform(0.8, 1.2) for _ in seeds]
    rows = [[0] * size for _ in range(size)]
    for r in range(size):
        for c in range(size):
            rows[r][c] = min(
                range(count),
                key=lambda i: (
                    (abs(r - seeds[i][0]) + abs(c - seeds[i][1])) * weights[i],
                    rng.random(),
                ),
            )
    return tuple(tuple(row) for row in rows)


def grow(size: int, count: int, rng: random.Random) -> Layout:
    """Seeded growth: the smallest area takes a random neighbouring square each turn."""
    seeds = _seeds(size, count, rng)
    owner: dict[Cell, int] = {seed: i for i, seed in enumerate(seeds)}
    sizes = [1] * count
    while len(owner) < size * size:
        for area in sorted(range(count), key=lambda i: (sizes[i], rng.random())):
            frontier = sorted(
                {
                    nb
                    for cell, owned in owner.items()
                    if owned == area
                    for nb in _neighbours(cell, size)
                    if nb not in owner
                }
            )
            if frontier:
                # Prefer squares with more same-area neighbours, for rounder shapes.
                best = max(
                    frontier,
                    key=lambda cell: (
                        sum(owner.get(nb) == area for nb in _neighbours(cell, size)),
                        rng.random(),
                    ),
                )
                owner[best] = area
                sizes[area] += 1
                break
        else:
            break
    rows = [[owner.get((r, c), 0) for c in range(size)] for r in range(size)]
    return tuple(tuple(row) for row in rows)


TEMPLATES: dict[str, Callable[[int, int, random.Random], Layout | None]] = {
    "bands": bands,
    "blobs": blobs,
    "staircase": staircase,
    "free": grow,
}


def perturb(
    layout: Layout, rng: random.Random, steps: int, keep: Callable[[Layout], bool]
) -> Layout:
    """Move up to `steps` border squares to a neighbouring area, keeping `keep` true."""
    size = len(layout)
    current = layout
    for _ in range(steps):
        border = [
            (r, c, layout_nb)
            for r in range(size)
            for c in range(size)
            for nr, nc in _neighbours((r, c), size)
            if (layout_nb := current[nr][nc]) != current[r][c]
        ]
        if not border:
            break
        r, c, area = rng.choice(border)
        rows = [list(row) for row in current]
        rows[r][c] = area
        moved = tuple(tuple(row) for row in rows)
        if keep(moved):
            current = moved
    return current


def story_order(layout: Layout) -> Layout:
    """Renumber areas north to south (then west to east) by their centres."""
    areas = area_cells(layout)
    centre = {
        area: (sum(r for r, _ in cells) / len(cells), sum(c for _, c in cells) / len(cells))
        for area, cells in areas.items()
    }
    order = {area: i for i, area in enumerate(sorted(areas, key=centre.__getitem__))}
    return tuple(tuple(order[a] for a in row) for row in layout)


# --- objects -------------------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    name: str
    kind: str
    cells: tuple[Cell, ...]
    across: bool = False


def object_problems(layout: Layout, objects: Sequence[Placed]) -> list[str]:
    """Why an object arrangement fails the hard filters; empty when it passes."""
    size = len(layout)
    problems = []
    taken: dict[Cell, int] = {}
    for index, obj in enumerate(objects):
        for cell in obj.cells:
            if cell in taken:
                problems.append(f"{obj.name} overlaps another object")
            taken[cell] = index
    for index, obj in enumerate(objects):
        areas = {layout[r][c] for r, c in obj.cells}
        if obj.across and len(areas) != 2:
            problems.append(f"{obj.name} does not join two areas")
        if not obj.across and len(areas) > 1:
            problems.append(f"{obj.name} crosses an area border")
        if obj.kind == "blocking":
            for cell in obj.cells:
                if any(layout[r][c] not in areas for r, c in _neighbours(cell, size)):
                    problems.append(f"{obj.name} touches an area border")
                    break
        for cell in obj.cells:
            if any(taken.get(nb, index) != index for nb in _neighbours(cell, size)):
                problems.append(f"{obj.name} touches another object")
                break
    blocked = {cell for obj in objects if obj.kind == "blocking" for cell in obj.cells}
    for area, cells in sorted(area_cells(layout).items()):
        free = cells - blocked
        if not free:
            problems.append(f"area {area} has no free square")
        elif not _connected(free, size):
            problems.append(f"objects cut area {area} in two")
    return problems


def place_objects(
    layout: Layout, spec: Spec, rng: random.Random, attempts: int | None = None
) -> list[Placed] | None:
    """A random arrangement of the spec's objects that passes the filters, or None."""
    size = len(layout)
    index = {name: i for i, name in enumerate(spec.areas)}
    areas = area_cells(layout)
    tries = int(THRESHOLDS["object_attempts"]) if attempts is None else attempts
    wanted = [obj for obj in spec.objects for _ in range(obj.count)]
    wanted.sort(key=lambda obj: (obj.area is None, -obj.length))
    for _ in range(tries):
        placed: list[Placed] = []
        load = {area: 0 for area in areas}
        for obj in wanted:
            options = []
            for r in range(size):
                for c in range(size):
                    for dr, dc in ((0, 1), (1, 0)) if obj.length > 1 else ((0, 1),):
                        cells = tuple((r + dr * i, c + dc * i) for i in range(obj.length))
                        if any(not (0 <= x < size and 0 <= y < size) for x, y in cells):
                            continue
                        if obj.area is not None and any(
                            layout[x][y] != index[obj.area] for x, y in cells
                        ):
                            continue
                        candidate = [*placed, Placed(obj.name, obj.kind, cells, obj.across)]
                        if not object_problems(layout, candidate):
                            options.append(cells)
            if not options:
                break
            # Fill emptier areas first, so objects spread over the board.
            fewest = min(load[layout[cells[0][0]][cells[0][1]]] for cells in options)
            options = [
                cells for cells in options if load[layout[cells[0][0]][cells[0][1]]] == fewest
            ]
            cells = rng.choice(options)
            load[layout[cells[0][0]][cells[0][1]]] += 1
            placed.append(Placed(obj.name, obj.kind, cells, obj.across))
        else:
            return placed
    return None


# --- colours -------------------------------------------------------------------


def _rgb(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def _distance(a: str, b: str) -> float:
    return math.dist(_rgb(a), _rgb(b))


def _touching(layout: Layout) -> set[frozenset[int]]:
    size = len(layout)
    return {
        frozenset((layout[r][c], layout[nr][nc]))
        for r in range(size)
        for c in range(size)
        for nr, nc in _neighbours((r, c), size)
        if layout[r][c] != layout[nr][nc]
    }


def choose_colours(layout: Layout, spec: Spec, rng: random.Random) -> list[str]:
    """Spec colours first; each other area takes the free tint farthest from its neighbours.

    Neighbours must clear the contrast threshold; beyond that the tint farthest from
    every other area wins, so two far-apart areas do not share a look-alike yellow.
    """
    touching = _touching(layout)
    enough = THRESHOLDS["contrast"]
    colours: dict[int, str] = {
        i: spec.colours[name] for i, name in enumerate(spec.areas) if name in spec.colours
    }
    palette = [colour for colour in PALETTE if colour not in colours.values()]
    rng.shuffle(palette)
    for area in range(len(spec.areas)):
        if area in colours:
            continue
        near = [colours[o] for o in colours if frozenset((area, o)) in touching]

        def fit(colour: str, near: list[str] = near) -> tuple[float, float]:
            beside = min((_distance(colour, n) for n in near), default=999.0)
            anywhere = min((_distance(colour, o) for o in colours.values()), default=999.0)
            return min(beside, enough), anywhere

        best = max(palette or list(PALETTE), key=fit)
        colours[area] = best
        if best in palette:
            palette.remove(best)
    return [colours[i] for i in range(len(spec.areas))]


# --- draft file ----------------------------------------------------------------


def _ids(count: int) -> list[str]:
    return [chr(ord("a") + i) for i in range(count)]


def _cell_name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def draft_text(
    spec: Spec,
    layout: Layout,
    colours: Sequence[str],
    objects: Sequence[Placed],
    placement: Mapping[str, Square] | None = None,
    clues: Sequence[str] | None = None,
    header: Sequence[str] = (),
    rules: bool = True,
) -> str:
    """The draft puzzle file: board, people, late-reveal rule and key clues; no booklet text.

    `rules=False` leaves out the late-reveal rule, for fast sampling of the bare board.
    """
    ids = _ids(len(spec.areas))
    lines = [f"# {line}" if line else "#" for line in header]
    if placement:
        order = sorted(placement, key=lambda p: (placement[p].row, placement[p].col))
        where = ", ".join(f"{p} {placement[p]}" for p in order)
        lines += [f"# Intended placement: {where}"]
    if lines:
        lines.append("")
    lines += [f"Size: {spec.size}", f"Language: {spec.language}", "", "Regions:"]
    lines += [
        f"{i}: {name} {colour}" for i, name, colour in zip(ids, spec.areas, colours, strict=True)
    ]
    lines += ["", "Grid:"]
    lines += [" ".join(ids[area] for area in row) for row in layout]
    if objects:
        lines += ["", "Objects:"]
        lines += [f"{o.name}: {o.kind} {' '.join(map(_cell_name, o.cells))}" for o in objects]
    lines += ["", "People:", *spec.people]
    if rules and spec.late and spec.companions:
        lines += ["", "Attributes:", f"{spec.companion_trait}: {' '.join(spec.companions)}"]
        lines += [
            "",
            "Rules:",
            f"alone_with {spec.late} attribute:{spec.companion_trait} {len(spec.companions)}",
        ]
    chosen = spec.key_clues if clues is None else clues
    if chosen:
        lines += ["", "Clues:", *chosen]
    return "\n".join(lines) + "\n"


# --- scoring -------------------------------------------------------------------


def _perimeter(cells: set[Cell]) -> int:
    return sum((r + dr, c + dc) not in cells for r, c in cells for dr, dc in SIDES)


def _staircase_steps(layout: Layout) -> int:
    """The longest diagonal run of 3:1 corners between the same two areas."""
    size = len(layout)
    corners: dict[Cell, frozenset[int]] = {}
    for r in range(size - 1):
        for c in range(size - 1):
            window = [layout[r][c], layout[r][c + 1], layout[r + 1][c], layout[r + 1][c + 1]]
            kinds = set(window)
            if len(kinds) == 2 and sorted(window.count(k) for k in kinds) == [1, 3]:
                corners[(r, c)] = frozenset(kinds)
    longest = 0
    for (r, c), pair in corners.items():
        for dc in (1, -1):
            length = 1
            while corners.get((r + length, c + dc * length)) == pair:
                length += 1
            longest = max(longest, length)
    return longest


def _symmetric(layout: Layout) -> bool:
    """Whether a turn or mirror maps the layout onto itself, up to renaming the areas."""
    size = len(layout)
    cells = {(r, c): layout[r][c] for r in range(size) for c in range(size)}

    def canonical(grid: dict[Cell, int]) -> tuple[int, ...]:
        names: dict[int, int] = {}
        return tuple(
            names.setdefault(grid[(r, c)], len(names)) for r in range(size) for c in range(size)
        )

    base = canonical(cells)
    for turn in range(4):
        for mirror in (False, True):
            if turn == 0 and not mirror:
                continue
            moved = {}
            for (r, c), value in cells.items():
                for _ in range(turn):
                    r, c = c, size - 1 - r
                if mirror:
                    c = size - 1 - c
                moved[(r, c)] = value
            if canonical(moved) == base:
                return True
    return False


def score(layout: Layout, objects: Sequence[Placed], colours: Sequence[str]) -> dict[str, float]:
    """Each aspect of `SCORE_WEIGHTS` on a 0..1 scale (1 is best)."""
    size = len(layout)
    areas = area_cells(layout)
    compact, convex = [], []
    for cells in areas.values():
        n = len(cells)
        best = 2 * math.ceil(2 * math.sqrt(n))
        compact.append(min(1.0, best / _perimeter(cells)))
        rows = {r for r, _ in cells}
        cols = {c for _, c in cells}
        convex.append(n / ((max(rows) - min(rows) + 1) * (max(cols) - min(cols) + 1)))
    sizes = [len(cells) for cells in areas.values()]
    inner = sum(
        layout[r][c] != layout[r][c + 1] for r in range(size) for c in range(size - 1)
    ) + sum(layout[r][c] != layout[r + 1][c] for r in range(size - 1) for c in range(size))
    shortest = (len(areas) - 1) * size
    borders = min(1.0, shortest / max(1, inner)) * 0.8 + (
        0.2 if _staircase_steps(layout) >= 2 else 0
    )
    with_objects = {layout[o.cells[0][0]][o.cells[0][1]] for o in objects}
    if objects:
        centres = [
            (sum(r for r, _ in o.cells) / len(o.cells), sum(c for _, c in o.cells) / len(o.cells))
            for o in objects
        ]
        pairs = [math.dist(a, b) for i, a in enumerate(centres) for b in centres[i + 1 :]]
        reach = (sum(pairs) / len(pairs)) / (size / 2) if pairs else 1.0
        spread = 0.5 * len(with_objects) / len(areas) + 0.5 * min(1.0, reach)
    else:
        spread = 0.0
    touching = _touching(layout)
    near = [_distance(colours[a], colours[b]) for a, b in map(tuple, touching)]
    blocked = {cell for o in objects if o.kind == "blocking" for cell in o.cells}
    roomy = sum(
        any({(r, c), (r, c + 1)} <= cells - blocked for r, c in cells) for cells in areas.values()
    )
    story = sorted(
        areas,
        key=lambda a: (sum(r for r, _ in areas[a]) / len(areas[a]), sum(c for _, c in areas[a])),
    )
    ordered = sum(1 for i, area in enumerate(story) if area == i) / len(story)
    return {
        "compactness": sum(compact) / len(compact),
        "convexity": sum(convex) / len(convex),
        "balance": min(sizes) / max(sizes),
        "borders": borders,
        "spread": spread,
        "asymmetry": 0.0 if _symmetric(layout) else 1.0,
        "story": ordered,
        "colours": min(1.0, min(near, default=999.0) / THRESHOLDS["contrast"]),
        "legibility": roomy / len(areas),
    }


def total(scores: Mapping[str, float]) -> float:
    weight = sum(SCORE_WEIGHTS.values())
    return sum(SCORE_WEIGHTS[k] * scores[k] for k in SCORE_WEIGHTS) / weight


# --- placement and key clues ------------------------------------------------------


def _key_clue_bites(spec: Spec, base: str, legal: Sequence[Mapping[str, Square]]) -> list[str]:
    """Key clues that no sampled legal placement breaks (they would rule nothing out)."""
    idle = []
    for clue in spec.key_clues:
        alone = draft_with_clues(base, [clue])
        if all(brute.accepts(alone, dict(placement)) for placement in legal):
            idle.append(clue)
    return idle


def draft_with_clues(text: str, clues: Sequence[str]) -> str:
    head = text.split("\nClues:\n", 1)[0].rstrip("\n")
    return head + ("\n\nClues:\n" + "\n".join(clues) if clues else "") + "\n"


def unused_standables(
    objects: Sequence[Placed], legal: Sequence[Mapping[str, Square]]
) -> list[str]:
    """Standable footprints no sampled legal placement stands on."""
    used = {(sq.row, sq.col) for placement in legal for sq in placement.values()}
    return [
        f"{o.name} {' '.join(map(_cell_name, o.cells))}"
        for o in objects
        if o.kind == "standable" and not used & set(o.cells)
    ]


def _spread(cells: Iterable[Cell]) -> int:
    """How many people the squares can hold, one per row and column (a maximum matching)."""
    match: dict[int, int] = {}
    columns: dict[int, list[int]] = {}
    for r, c in cells:
        columns.setdefault(r, []).append(c)

    def augment(row: int, seen: set[int]) -> bool:
        for col in columns[row]:
            if col not in seen:
                seen.add(col)
                if col not in match or augment(match[col], seen):
                    match[col] = row
                    return True
        return False

    return sum(augment(row, set()) for row in columns)


def late_hosts(spec: Spec, layout: Layout, objects: Sequence[Placed]) -> list[int]:
    """Areas whose free squares can hold the late figure and all companions at once."""
    if not spec.late:
        return list(range(len(spec.areas)))
    blocked = {cell for o in objects if o.kind == "blocking" for cell in o.cells}
    need = len(spec.companions) + 1
    return [
        area
        for area, cells in sorted(area_cells(layout).items())
        if _spread(cells - blocked) >= need
    ]


# --- generator -------------------------------------------------------------------


@dataclass
class Candidate:
    index: int
    seed: str
    template: str
    layout: Layout
    colours: list[str]
    objects: list[Placed]
    placement: dict[str, Square]
    scores: dict[str, float]
    text: str
    closing: str = ""  # what `close` found: clues added and the outcome

    @property
    def total(self) -> float:
        return total(self.scores)


@dataclass
class Report:
    candidates: list[Candidate]
    rejected: dict[str, int]


def _bump(counter: dict[str, int], reason: str) -> None:
    counter[reason] = counter.get(reason, 0) + 1


def candidate(spec: Spec, index: int, rejected: dict[str, int] | None = None) -> Candidate | None:
    """The `index`-th candidate of a spec, rebuilt identically from the same seed."""
    seed = f"{spec.seed}:{index}"
    rng = random.Random(seed)
    tally: dict[str, int] = {} if rejected is None else rejected
    count = len(spec.areas)

    def acceptable(layout: Layout) -> bool:
        return not area_problems(layout, spec.min_area, spec.max_ratio)

    for _ in range(int(THRESHOLDS["layout_attempts"])):
        name = spec.template if spec.template != "auto" else rng.choice(sorted(TEMPLATES))
        layout = TEMPLATES[name](spec.size, count, rng)
        if layout is None:
            _bump(tally, f"{name} does not fit this size")
            continue
        if not acceptable(layout):
            _bump(tally, "layout filters")
            continue
        layout = story_order(perturb(layout, rng, int(THRESHOLDS["perturb_steps"]), acceptable))
        objects = place_objects(layout, spec, rng)
        if objects is None:
            _bump(tally, "object filters")
            continue
        colours = choose_colours(layout, spec, rng)
        if not late_hosts(spec, layout, objects):
            _bump(tally, "no area holds the late figure and companions")
            continue
        base = draft_text(spec, layout, colours, objects, clues=(), rules=False)
        legal = brute.sample(base, int(THRESHOLDS["legal_sample"]))
        if not legal:
            _bump(tally, "nobody fits")
            continue
        if unused_standables(objects, legal):
            _bump(tally, "unused standable object")
            continue
        if _key_clue_bites(spec, base, legal):
            _bump(tally, "key clue rules nothing out")
            continue
        full = draft_text(spec, layout, colours, objects)
        # Most bare-board placements break the late-reveal rule, but checking one is cheap;
        # searching with that rule is not, so it is the fallback.
        fitting = [p for p in legal if brute.accepts(full, dict(p))] or brute.sample(
            full, int(THRESHOLDS["placement_sample"])
        )
        if not fitting:
            _bump(tally, "late rule and key clues unsatisfiable")
            continue
        placement = dict(rng.choice(fitting))
        text = draft_text(
            spec,
            layout,
            colours,
            objects,
            placement,
            header=[
                f"Draft {spec.theme} board, candidate {index} (seed {seed}, template {name}).",
                "Generated by puzzle-lab murdoku-board; clues still to be added",
                "(csp.clue_search suggest/thin), then booklet text.",
            ],
        )
        return Candidate(
            index,
            seed,
            name,
            layout,
            colours,
            objects,
            placement,
            score(layout, objects, colours),
            text,
        )
    return None


def generate(
    spec: Spec, on_candidate: Callable[[int, Candidate | None], None] | None = None
) -> Report:
    """Build `spec.candidates` candidates and rank them, best first."""
    rejected: dict[str, int] = {}
    found = []
    for index in range(spec.candidates):
        built = candidate(spec, index, rejected)
        if on_candidate:
            on_candidate(index, built)
        if built is not None:
            found.append(built)
    found.sort(key=lambda c: (-c.total, c.index))
    return Report(found, rejected)


def close(spec: Spec, item: Candidate, timeout: float = 5.0) -> Candidate:
    """`item` with clues from `clue_search.suggest` added until its placement is unique.

    The late figure is in no added clue, every other figure gets at least one
    where a helping clue exists (`cover`), and every key clue stays necessary,
    as a late-reveal mystery needs. `closing` records the clue count and the
    outcome (unique with a grade, or how far it got), so drafts can be compared
    on how well they close, not only on looks.
    """
    from . import clue_search

    needs = range(1, len(spec.key_clues) + 1)
    exclude = (spec.late,) if spec.late else ()
    added = clue_search.suggest(
        item.text, item.placement, timeout=timeout, exclude=exclude, needs=needs, cover=True
    )
    text = clue_search.with_clues(item.text, [*spec.key_clues, *added])
    outcome = clue_search.outcome(text, timeout)
    state = str(outcome) if outcome.good else f"not closed ({outcome})"
    closing = f"{len(added)} clues added: {state}"
    marker = "# Intended placement:"
    text = text.replace(marker, f"# Suggested clues: {closing}\n{marker}", 1)
    return dataclasses.replace(item, text=text, closing=closing)


# --- output ----------------------------------------------------------------------


def describe(item: Candidate) -> str:
    aspects = " ".join(f"{k}={item.scores[k]:.2f}" for k in SCORE_WEIGHTS)
    line = f"#{item.index} total {item.total:.3f} ({item.template}, seed {item.seed}): {aspects}"
    return f"{line}; {item.closing}" if item.closing else line


def contact_sheet(
    images: Sequence[tuple[str, svg.Canvas]], columns: int = 3, tile: int = 480
) -> svg.Canvas:
    """One picture of several puzzle pictures, each under its caption."""
    rows = math.ceil(len(images) / columns)
    caption = 40
    canvas = svg.Canvas(columns * tile, rows * (tile + caption))
    for i, (title, image) in enumerate(images):
        x = (i % columns) * tile
        y = (i // columns) * (tile + caption)
        canvas.text((x + tile / 2, y + caption / 2), title, (40, 40, 40), 22, anchor="mm")
        data = base64.b64encode(image.to_svg().encode()).decode()
        width, height = image.width, image.height
        canvas.place(
            f"sheet{i}",
            f'<image width="{width}" height="{height}" href="data:image/svg+xml;base64,{data}"/>',
            (0, 0, width, height),
            (x + 8, y + caption, x + tile - 8, y + caption + tile - 16),
        )
    return canvas


def write(report: Report, spec: Spec, folder: Path, pictures: bool = True) -> list[Path]:
    """Write the kept drafts, the report and (with `pictures`) the contact sheets.

    Refuses to overwrite: every target must be new.
    """
    kept = report.candidates[: spec.keep]
    stem = f"{spec.theme}-s{spec.seed}"
    targets = {f"{stem}-c{c.index}.txt": c.text for c in kept}
    lines = [f"{spec.theme}: {len(report.candidates)} of {spec.candidates} candidates passed"]
    if report.rejected:
        lines.append(
            "rejected attempts: "
            + ", ".join(f"{reason} {n}" for reason, n in sorted(report.rejected.items()))
        )
    lines += [describe(c) for c in report.candidates]
    targets[f"{stem}-report.txt"] = "\n".join(lines) + "\n"
    paths = [folder / name for name in targets]
    sheets = [folder / f"{stem}-puzzles.png", folder / f"{stem}-solutions.png"]
    if existing := [p for p in [*paths, *(sheets if pictures else [])] if p.exists()]:
        raise FileExistsError(f"will not overwrite {', '.join(map(str, existing))}")
    folder.mkdir(parents=True, exist_ok=True)
    for path, content in zip(paths, targets.values(), strict=True):
        path.write_text(content)
    if pictures and kept:
        from .picture import murdoku_picture

        for sheet, solved in zip(sheets, (False, True), strict=True):
            images = []
            for item in kept:
                board, _ = load_board(item.text)
                image = murdoku_picture(
                    board, item.placement if solved else None, language=spec.language
                )
                caption = f"#{item.index}  score {item.total:.3f}"
                if item.closing:
                    caption += "  " + item.closing.split(": ", 1)[1]
                images.append((caption, image))
            contact_sheet(images).save(sheet)
            paths.append(sheet)
    return paths
