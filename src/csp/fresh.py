"""Build original puzzles from scratch: a new random solution, then givens removed
while the answer stays unique.

`puzzle_lab.generate` re-masks a seed file, so its candidates share the seed's
solution and layout. Use these builders when an example needs its own board.
"""

import itertools
import random
import re
from collections.abc import Callable, Iterable

from csp import bruteforce
from csp.puzzlefile import detect

type Cell = tuple[int, int]
type Pair = tuple[Cell, Cell]

FAMILIES = ("binairo", "tango", "queens", "dogdoku", "suguru")
REGION_NAMES = [
    "amber",
    "blue",
    "coral",
    "green",
    "violet",
    "silver",
    "gold",
    "teal",
    "rose",
    "olive",
    "navy",
    "peach",
    "lime",
    "plum",
    "sand",
    "sky",
    "mint",
    "rust",
    "grey",
    "clay",
    "cream",
    "jade",
    "ruby",
    "lilac",
    "ochre",
    "pine",
]
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def is_unique(text: str) -> bool:
    return len(bruteforce.solutions(text, detect(text), limit=2)) == 1


def thin[T](
    items: Iterable[T],
    build: Callable[[set[T]], str],
    rng: random.Random,
    keep_at_least: int = 0,
) -> set[T]:
    """Drop items in random order while the puzzle built from the rest stays unique."""
    kept = set(items)
    order = sorted(kept, key=repr)
    rng.shuffle(order)
    for item in order:
        if len(kept) <= keep_at_least:
            break
        if is_unique(build(kept - {item})):
            kept.discard(item)
    return kept


def _name(cell: Cell) -> str:
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def _cells(size: int) -> list[Cell]:
    return [(row, col) for row in range(size) for col in range(size)]


def binairo_solution(size: int, rng: random.Random) -> list[tuple[int, ...]]:
    """A random valid Binairo grid: balanced, no three in a line, all lines distinct."""
    half = size // 2
    rows = [
        bits
        for bits in itertools.product((0, 1), repeat=size)
        if sum(bits) == half and all(len(set(bits[i : i + 3])) > 1 for i in range(size - 2))
    ]
    grid: list[tuple[int, ...]] = []

    def columns_fit() -> bool:
        for col in range(size):
            line = [row[col] for row in grid]
            if max(line.count(0), line.count(1)) > half:
                return False
            if any(len(set(line[i : i + 3])) == 1 for i in range(len(line) - 2)):
                return False
        return True

    def extend() -> bool:
        if len(grid) == size:
            return len({tuple(row[c] for row in grid) for c in range(size)}) == size
        options = rows[:]
        rng.shuffle(options)
        for row in options:
            if row in grid:
                continue
            grid.append(row)
            if columns_fit() and extend():
                return True
            grid.pop()
        return False

    if not extend():
        raise ValueError(f"no Binairo grid of size {size}")
    return grid


def _binairo_text(
    family: str,
    grid: list[tuple[int, ...]],
    givens: set[Cell],
    signs: Iterable[Pair] = (),
    comment: str = "",
) -> str:
    size = len(grid)
    lines = [f"# {comment}"] if comment else []
    lines += [f"Family: {family}", f"Size: {size}", "Givens:"]
    lines += [
        " ".join(str(grid[r][c]) if (r, c) in givens else "." for c in range(size))
        for r in range(size)
    ]
    signs = sorted(signs)
    equal = [(a, b) for a, b in signs if grid[a[0]][a[1]] == grid[b[0]][b[1]]]
    different = [pair for pair in signs if pair not in equal]
    for title, pairs in (("Equal", equal), ("Different", different)):
        if pairs:
            lines.append(f"{title}:")
            lines += [f"{_name(a)} {_name(b)}" for a, b in pairs]
    return "\n".join(lines) + "\n"


def fresh_binairo(
    size: int,
    rng: random.Random,
    open_share: float,
    family: str = "binairo",
    sign_share: float = 0.25,
    comment: str = "",
) -> str:
    """A new Binairo (or Tango, with signs) with about `open_share` of the cells empty."""
    grid = binairo_solution(size, rng)
    signs: list[Pair] = []
    if family == "tango":
        pairs = [((r, c), (r, c + 1)) for r in range(size) for c in range(size - 1)]
        pairs += [((r, c), (r + 1, c)) for r in range(size - 1) for c in range(size)]
        signs = [pair for pair in pairs if rng.random() < sign_share]
    keep = size * size - round(open_share * size * size)
    givens = set(_cells(size))
    order = sorted(givens)
    rng.shuffle(order)
    for cell in order:
        if len(givens) <= keep:
            break
        if is_unique(_binairo_text(family, grid, givens - {cell}, signs)):
            givens.discard(cell)
    if signs:
        kept = thin(
            signs,
            lambda chosen: _binairo_text(family, grid, givens, chosen),
            rng,
            keep_at_least=max(size, len(signs) // 2),
        )
        signs = [pair for pair in signs if pair in kept]
    return _binairo_text(family, grid, givens, signs, comment)


def _region_text(
    family: str, size: int, owner: dict[Cell, int], extra: list[str], comment: str
) -> str:
    count = max(owner.values()) + 1
    if count > len(REGION_NAMES):
        raise ValueError(f"{count} regions is more than the {len(REGION_NAMES)} names")
    ids = [f"{chr(97 + i % 26)}{i // 26 or ''}" for i in range(count)]
    lines = [f"# {comment}"] if comment else []
    lines += [f"Family: {family}", f"Size: {size}", "Regions:"]
    lines += [f"{ids[i]}: {REGION_NAMES[i]}" for i in range(count)]
    lines.append("Grid:")
    lines += [" ".join(ids[owner[(r, c)]] for c in range(size)) for r in range(size)]
    return "\n".join(lines + extra) + "\n"


def _grow(size: int, seeds: list[Cell], rng: random.Random) -> dict[Cell, int]:
    """Grow one connected region from each seed until the board is covered."""
    owner = {cell: i for i, cell in enumerate(seeds)}
    while len(owner) < size * size:
        options = [
            ((r + dr, c + dc), i)
            for (r, c), i in owner.items()
            for dr, dc in STEPS
            if 0 <= r + dr < size and 0 <= c + dc < size and (r + dr, c + dc) not in owner
        ]
        cell, region = rng.choice(options)
        owner[cell] = region
    return owner


def fresh_queens(
    size: int, rng: random.Random, family: str = "queens", attempts: int = 4000, comment: str = ""
) -> str | None:
    """A new Queens/DogDoku board with no givens: regions grown around a hidden placement."""
    for _ in range(attempts):
        cols = list(range(size))
        rng.shuffle(cols)
        if any(abs(cols[i] - cols[i + 1]) < 2 for i in range(size - 1)):
            continue
        owner = _grow(size, [(row, cols[row]) for row in range(size)], rng)
        text = _region_text(family, size, owner, [], comment)
        if is_unique(text):
            return text
    return None


def _carve(size: int, rng: random.Random, largest: int = 5) -> dict[Cell, int]:
    """Cut the board into connected regions of 3..`largest` cells, merging leftovers."""
    owner: dict[Cell, int] = {}
    count = 0
    for start in _cells(size):
        if start in owner:
            continue
        target = rng.randint(3, largest)
        region = [start]
        owner[start] = count
        while len(region) < target:
            options = [
                (r + dr, c + dc)
                for r, c in region
                for dr, dc in STEPS
                if 0 <= r + dr < size and 0 <= c + dc < size and (r + dr, c + dc) not in owner
            ]
            if not options:
                break
            cell = rng.choice(options)
            owner[cell] = count
            region.append(cell)
        count += 1
    merged = True
    while merged:
        merged = False
        sizes = {i: list(owner.values()).count(i) for i in set(owner.values())}
        for small, cells_in in sizes.items():
            if cells_in >= 3:
                continue
            members = [cell for cell, i in owner.items() if i == small]
            near = {
                owner[(r + dr, c + dc)]
                for r, c in members
                for dr, dc in STEPS
                if owner.get((r + dr, c + dc), small) != small
            }
            near = {i for i in near if sizes[i] + cells_in <= largest + 1}
            if near:
                target = rng.choice(sorted(near))
                for cell in members:
                    owner[cell] = target
                merged = True
                break
    renumber = {old: new for new, old in enumerate(sorted(set(owner.values())))}
    return {cell: renumber[i] for cell, i in owner.items()}


def fresh_suguru(
    size: int, rng: random.Random, attempts: int = 60, comment: str = ""
) -> str | None:
    """A new Suguru: carved regions, a solver-found filling, then minimal givens."""
    for _ in range(attempts):
        owner = _carve(size, rng)
        blank = _region_text("suguru", size, owner, [], comment)
        found = bruteforce.solutions(blank, "suguru", limit=1)
        if not found:
            continue
        values = {
            (int(m.group(1)) - 1, int(m.group(2)) - 1): value
            for key, value in found[0].items()
            if (m := re.fullmatch(r"r(\d+)c(\d+)", key))
        }

        def build(
            givens: set[Cell], owner: dict[Cell, int] = owner, values: dict[Cell, object] = values
        ) -> str:
            rows = [
                " ".join(str(values[(r, c)]) if (r, c) in givens else "." for c in range(size))
                for r in range(size)
            ]
            return _region_text("suguru", size, owner, ["Givens:", *rows], comment)

        return build(thin(set(owner), build, rng))
    return None


def fresh(
    family: str, size: int, rng: random.Random, open_share: float = 0.5, comment: str = ""
) -> str | None:
    """A new puzzle of `family`; `open_share` applies to Binairo and Tango."""
    if family in {"binairo", "tango"}:
        return fresh_binairo(size, rng, open_share, family, comment=comment)
    if family in {"queens", "dogdoku"}:
        return fresh_queens(size, rng, family, comment=comment)
    if family == "suguru":
        return fresh_suguru(size, rng, comment=comment)
    raise ValueError(f"no fresh builder for {family}; choose from {', '.join(FAMILIES)}")
