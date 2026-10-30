"""Build original puzzles from scratch: a new random solution, then givens removed
while the answer stays unique.

`puzzle_lab.generate` re-masks a seed file, so its candidates share the seed's
solution and layout. Use these builders when an example needs its own board.
"""

import itertools
import random
import re
from collections.abc import Callable, Iterable

from csp import battleships, bruteforce
from csp.puzzlefile import detect

type Cell = tuple[int, int]
type Pair = tuple[Cell, Cell]

FAMILIES = (
    "binairo",
    "tango",
    "queens",
    "suguru",
    "minesweeper",
    "akari",
    "sudoku",
    "futoshiki",
    "calcudoku",
    "starbattle",
    "tents",
    "battleships",
)
SUDOKU_BOXES = {4: (2, 2), 6: (2, 3), 9: (3, 3)}
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
    size: int, rng: random.Random, attempts: int = 4000, comment: str = ""
) -> str | None:
    """A new Queens board with no givens: regions grown around a hidden placement."""
    for _ in range(attempts):
        cols = list(range(size))
        rng.shuffle(cols)
        if any(abs(cols[i] - cols[i + 1]) < 2 for i in range(size - 1)):
            continue
        owner = _grow(size, [(row, cols[row]) for row in range(size)], rng)
        text = _region_text("queens", size, owner, [], comment)
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


def fresh_minesweeper(
    size: int, rng: random.Random, unknown_share: float = 0.5, comment: str = ""
) -> str:
    """Build a Minesweeper board from a new mine layout and hidden safe cells."""
    if size < 4:
        raise ValueError("fresh Minesweeper boards need to be at least 4x4")
    cells = _cells(size)
    mine_count = max(3, round(size * size * 0.14))
    unknown_count = max(mine_count + 1, round(size * size * unknown_share))
    unknown_count = min(size * size - 1, unknown_count)
    mines = set(rng.sample(cells, mine_count))
    safe_cells = [cell for cell in cells if cell not in mines]
    hidden = mines | set(rng.sample(safe_cells, unknown_count - mine_count))
    lines = [f"# {comment}"] if comment else []
    lines += ["Family: minesweeper", f"Size: {size}", "Clues:"]
    for row in range(size):
        clues = []
        for col in range(size):
            cell = (row, col)
            if cell in hidden:
                clues.append(".")
                continue
            count = sum(
                (near_row, near_col) in mines
                for near_row in range(max(0, row - 1), min(size, row + 2))
                for near_col in range(max(0, col - 1), min(size, col + 2))
                if (near_row, near_col) != cell
            )
            clues.append(str(count))
        lines.append(" ".join(clues))
    lines += ["TotalMines:", str(mine_count)]
    return "\n".join(lines) + "\n"


def fresh_akari(size: int, rng: random.Random, tier: str, comment: str = "") -> str | None:
    """Build an Akari board with a new wall layout and clues derived from its solution."""
    if size < 4:
        raise ValueError("fresh Akari boards need to be at least 4x4")
    wall_share = 0.32 if size <= 6 else 0.25
    clue_share = {"easy": 0.9, "medium": 0.75, "hard": 0.75}[tier]
    for _ in range(10):
        board = [
            ["W" if rng.random() < wall_share else "." for _ in range(size)] for _ in range(size)
        ]
        if not any(cell == "W" for row in board for cell in row):
            continue
        blank = f"Family: akari\nSize: {size}\nGrid:\n" + "\n".join(" ".join(row) for row in board)
        solutions = bruteforce.solutions(blank, "akari", limit=1)
        if not solutions:
            continue
        bulbs = {
            (row, col)
            for row in range(size)
            for col in range(size)
            if solutions[0].get(f"r{row + 1}c{col + 1}", False)
        }
        numbered = 0
        for row in range(size):
            for col in range(size):
                if board[row][col] != "W":
                    continue
                count = sum(
                    (near_row, near_col) in bulbs
                    for near_row, near_col in (
                        (row - 1, col),
                        (row + 1, col),
                        (row, col - 1),
                        (row, col + 1),
                    )
                    if 0 <= near_row < size and 0 <= near_col < size
                )
                if rng.random() < clue_share:
                    board[row][col] = str(count)
                    numbered += 1
        if numbered == 0:
            return None
        lines = [f"# {comment}"] if comment else []
        lines += ["Family: akari", f"Size: {size}", "Grid:"]
        lines += [" ".join(row) for row in board]
        return "\n".join(lines) + "\n"
    return None


def latin_square(
    size: int, rng: random.Random, box: tuple[int, int] | None = None
) -> list[list[int]]:
    """A random grid with 1..size once per row and column (and per box, for Sudoku)."""
    grid = [[0] * size for _ in range(size)]

    def allowed(r: int, c: int, value: int) -> bool:
        if value in grid[r] or any(grid[i][c] == value for i in range(r)):
            return False
        if box:
            top, left = r - r % box[0], c - c % box[1]
            block = (
                grid[i][j] for i in range(top, top + box[0]) for j in range(left, left + box[1])
            )
            return value not in block
        return True

    def fill(index: int) -> bool:
        if index == size * size:
            return True
        r, c = divmod(index, size)
        values = list(range(1, size + 1))
        rng.shuffle(values)
        for value in values:
            if allowed(r, c, value):
                grid[r][c] = value
                if fill(index + 1):
                    return True
        grid[r][c] = 0
        return False

    fill(0)
    return grid


def _keep(size: int, open_share: float) -> int:
    return size * size - round(open_share * size * size)


def _given_rows(grid: list[list[int]], givens: set[Cell]) -> list[str]:
    size = len(grid)
    return [
        " ".join(str(grid[r][c]) if (r, c) in givens else "." for c in range(size))
        for r in range(size)
    ]


def _header(comment: str, *lines: str) -> list[str]:
    return ([f"# {comment}"] if comment else []) + list(lines)


def fresh_sudoku(size: int, rng: random.Random, open_share: float, comment: str = "") -> str:
    """A new Sudoku (4x4, 6x6 or 9x9) with about `open_share` of the cells empty."""
    if size not in SUDOKU_BOXES:
        raise ValueError(f"fresh Sudoku boards are {', '.join(map(str, SUDOKU_BOXES))} wide")
    grid = latin_square(size, rng, SUDOKU_BOXES[size])

    def build(givens: set[Cell]) -> str:
        return "\n".join(_header(comment, "Givens:", *_given_rows(grid, givens))) + "\n"

    return build(thin(_cells(size), build, rng, keep_at_least=_keep(size, open_share)))


def fresh_futoshiki(
    size: int, rng: random.Random, open_share: float, sign_share: float = 0.3, comment: str = ""
) -> str:
    """A new Futoshiki: a random Latin square, some inequality signs, then fewer givens."""
    grid = latin_square(size, rng)
    pairs = [((r, c), (r, c + 1)) for r in range(size) for c in range(size - 1)]
    pairs += [((r, c), (r + 1, c)) for r in range(size - 1) for c in range(size)]
    signs = {pair for pair in pairs if rng.random() < sign_share}

    def build(givens: set[Cell], chosen: set[Pair] = signs) -> str:
        lines = _header(comment, "Grid:", *_given_rows(grid, givens), "Signs:")
        for a, b in sorted(chosen):
            sign = ">" if grid[a[0]][a[1]] > grid[b[0]][b[1]] else "<"
            lines.append(f"{_name(a)} {sign} {_name(b)}")
        return "\n".join(lines) + "\n"

    givens = thin(_cells(size), build, rng, keep_at_least=_keep(size, open_share))
    kept = thin(signs, lambda chosen: build(givens, chosen), rng, keep_at_least=len(signs) // 2)
    return build(givens, kept)


def _cages(size: int, rng: random.Random, sizes: tuple[int, ...]) -> dict[Cell, int]:
    """Cut the board into connected cages whose sizes are drawn from `sizes`."""
    owner: dict[Cell, int] = {}
    for start in _cells(size):
        if start in owner:
            continue
        cage, target = len(set(owner.values())), rng.choice(sizes)
        members = [start]
        owner[start] = cage
        while len(members) < target:
            options = [
                (r + dr, c + dc)
                for r, c in members
                for dr, dc in STEPS
                if 0 <= r + dr < size and 0 <= c + dc < size and (r + dr, c + dc) not in owner
            ]
            if not options:
                break
            cell = rng.choice(options)
            owner[cell] = cage
            members.append(cell)
    return owner


def _cage_clue(values: list[int], rng: random.Random) -> str:
    if len(values) == 1:
        return str(values[0])
    if len(values) == 2:
        high, low = max(values), min(values)
        options = [f"{high - low}-", f"{sum(values)}+"]
        if high % low == 0:
            options.append(f"{high // low}/")
        return rng.choice(options)
    product = 1
    for value in values:
        product *= value
    return rng.choice([f"{sum(values)}+", f"{product}x"])


def fresh_calcudoku(
    size: int, rng: random.Random, attempts: int = 200, comment: str = ""
) -> str | None:
    """A new Calcudoku: a random Latin square cut into cages with arithmetic clues."""
    for _ in range(attempts):
        grid = latin_square(size, rng)
        owner = _cages(size, rng, (1, 2, 2, 2, 3, 3, 4))
        count = len(set(owner.values()))
        if count > 26:
            continue
        ids = [chr(97 + i) for i in range(count)]
        lines = _header(comment, f"Size: {size}", "Grid:")
        lines += [" ".join(ids[owner[(r, c)]] for c in range(size)) for r in range(size)]
        lines.append("Cages:")
        for cage in range(count):
            values = [grid[r][c] for (r, c), i in owner.items() if i == cage]
            lines.append(f"{ids[cage]}: {_cage_clue(values, rng)}")
        text = "\n".join(lines) + "\n"
        if is_unique(text):
            return text
    return None


def star_placement(size: int, stars: int, rng: random.Random) -> set[Cell] | None:
    """Random cells with `stars` per row and column, none touching, even diagonally."""
    chosen: set[Cell] = set()
    columns = [0] * size

    def fill(row: int) -> bool:
        if row == size:
            return True
        options = [
            combo
            for combo in itertools.combinations(range(size), stars)
            if all(b - a > 1 for a, b in itertools.pairwise(combo))
            and all(columns[c] < stars for c in combo)
            and not any((row - 1, c + d) in chosen for c in combo for d in (-1, 0, 1))
        ]
        rng.shuffle(options)
        for combo in options:
            for c in combo:
                chosen.add((row, c))
                columns[c] += 1
            if fill(row + 1):
                return True
            for c in combo:
                chosen.discard((row, c))
                columns[c] -= 1
        return False

    return chosen if fill(0) and all(count == stars for count in columns) else None


def _star_regions(
    size: int, placement: set[Cell], stars: int, rng: random.Random
) -> dict[Cell, int] | None:
    """Group the stars `stars` at a time into connected regions, then fill the board."""
    owner: dict[Cell, int] = {}
    left = sorted(placement)
    rng.shuffle(left)
    region = 0
    while left:
        group = [left.pop()]
        while len(group) < stars:
            group.append(min(left, key=lambda s: abs(s[0] - group[0][0]) + abs(s[1] - group[0][1])))
            left.remove(group[-1])
        for star in group[1:]:
            path = _path(size, group[0], star, owner, placement)
            if path is None:
                return None
            for cell in path:
                owner[cell] = region
        owner[group[0]] = region
        region += 1
    while len(owner) < size * size:
        options = [
            ((r + dr, c + dc), i)
            for (r, c), i in owner.items()
            for dr, dc in STEPS
            if 0 <= r + dr < size and 0 <= c + dc < size and (r + dr, c + dc) not in owner
        ]
        cell, chosen = rng.choice(options)
        owner[cell] = chosen
    return owner


def _path(
    size: int, start: Cell, goal: Cell, owner: dict[Cell, int], stars: set[Cell]
) -> list[Cell] | None:
    """A shortest free path between two stars that passes no other star or region."""
    previous: dict[Cell, Cell | None] = {start: None}
    queue = [start]
    for cell in queue:
        if cell == goal:
            path = []
            step: Cell | None = cell
            while step is not None:
                path.append(step)
                step = previous[step]
            return path
        r, c = cell
        for dr, dc in STEPS:
            nxt = (r + dr, c + dc)
            if (
                0 <= nxt[0] < size
                and 0 <= nxt[1] < size
                and nxt not in previous
                and nxt not in owner
                and (nxt not in stars or nxt == goal)
            ):
                previous[nxt] = cell
                queue.append(nxt)
    return None


def fresh_starbattle(
    size: int,
    rng: random.Random,
    stars: int,
    open_share: float = 1.0,
    attempts: int = 200,
    comment: str = "",
) -> str | None:
    """A new Star Battle: a random star placement, regions grown around it, then givens
    only where the regions alone allow more than one solution."""
    for _ in range(attempts):
        placement = star_placement(size, stars, rng)
        owner = _star_regions(size, placement, stars, rng) if placement else None
        if owner is None or placement is None:
            continue
        blank = _region_text("starbattle", size, owner, [], comment).replace(
            "Regions:", f"Stars: {stars}\nRegions:", 1
        )
        if open_share >= 1 and is_unique(blank):
            return blank
        solution = placement

        def build(givens: set[Cell], blank: str = blank, solution: set[Cell] = solution) -> str:
            rows = [
                " ".join(
                    ("*" if (r, c) in solution else ".") if (r, c) in givens else "?"
                    for c in range(size)
                )
                for r in range(size)
            ]
            return blank + "Givens:\n" + "\n".join(rows) + "\n"

        keep = _keep(size, open_share) if open_share < 1 else 0
        return build(thin(_cells(size), build, rng, keep_at_least=keep))
    return None


def fresh_tents(
    size: int, rng: random.Random, attempts: int = 400, comment: str = ""
) -> str | None:
    """A new Tents and Trees board: random tent and tree pairs, then row and column counts."""
    for _ in range(attempts):
        tents: set[Cell] = set()
        trees: set[Cell] = set()
        cells = _cells(size)
        rng.shuffle(cells)
        for r, c in cells[: size * size // 4]:
            near = {(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)}
            if (r, c) in trees or near & tents:
                continue
            if any((r + dr, c + dc) in trees for dr, dc in STEPS):
                continue
            spots = [
                (r + dr, c + dc)
                for dr, dc in STEPS
                if 0 <= r + dr < size
                and 0 <= c + dc < size
                and (r + dr, c + dc) not in trees
                and not any((r + dr + a, c + dc + b) in tents for a, b in STEPS)
            ]
            if spots:
                tents.add((r, c))
                trees.add(rng.choice(spots))
        lines = _header(comment, "Family: tents", f"Size: {size}", "Trees:")
        lines += [
            " ".join("T" if (r, c) in trees else "." for c in range(size)) for r in range(size)
        ]
        lines += ["RowCounts:", " ".join(str(sum(t[0] == r for t in tents)) for r in range(size))]
        lines += [
            "ColumnCounts:",
            " ".join(str(sum(t[1] == c for t in tents)) for c in range(size)),
        ]
        text = "\n".join(lines) + "\n"
        try:
            if is_unique(text):
                return text
        except ValueError:  # a tree without a free neighbour
            continue
    return None


def fresh_battleships(size: int, rng: random.Random, comment: str = "") -> str | None:
    """Place a fresh non-touching fleet, then thin shaped givens by independent search."""
    fleets = {
        4: (2, 1, 1),
        6: (3, 2, 2, 1, 1, 1),
        8: (4, 3, 2, 2, 1, 1, 1),
        10: (4, 3, 3, 2, 2, 2, 1, 1, 1, 1),
    }
    if size not in fleets:
        raise ValueError("fresh Battleships supports sizes 4, 6, 8 and 10")
    fleet = fleets[size]
    template = battleships.Puzzle(
        size,
        [size] * size,
        [size] * size,
        [[-1] * size for _ in range(size)],
        fleet,
        tuple(tuple("." for _ in range(size)) for _ in range(size)),
    )
    positions = battleships.ships(template)
    for _ in range(100):
        chosen: list[battleships.Ship] = []
        occupied: set[Cell] = set()
        forbidden: set[Cell] = set()
        for length in fleet:
            options = [
                ship
                for ship in positions
                if len(ship.cells) == length and not set(ship.cells) & forbidden
            ]
            if not options:
                break
            ship = rng.choice(options)
            chosen.append(ship)
            occupied.update(ship.cells)
            forbidden.update(ship.cells)
            forbidden.update(ship.halo)
        if len(chosen) != len(fleet):
            continue
        shapes = {
            cell: battleships.segment(ship.cells, cell) for ship in chosen for cell in ship.cells
        }

        def build(
            givens: set[Cell],
            occupied: set[Cell] = occupied,
            shapes: dict[Cell, str] = shapes,
        ) -> str:
            lines = _header(comment, "Family: battleships", f"Size: {size}", "Fleet:")
            lines += [" ".join(map(str, fleet)), "RowCounts:"]
            lines += [" ".join(str(sum(r == row for r, _ in occupied)) for row in range(size))]
            lines += ["ColumnCounts:"]
            lines += [" ".join(str(sum(c == col for _, c in occupied)) for col in range(size))]
            lines += ["Givens:"]
            lines += [
                " ".join(shapes.get((r, c), "0") if (r, c) in givens else "." for c in range(size))
                for r in range(size)
            ]
            return "\n".join(lines) + "\n"

        kept = thin(_cells(size), build, rng)
        return build(kept)
    return None


def fresh(
    family: str,
    size: int,
    rng: random.Random,
    open_share: float = 0.5,
    comment: str = "",
    tier: str = "easy",
) -> str | None:
    """A new puzzle of `family`; `open_share` applies to Binairo, Tango, Minesweeper,
    Sudoku and Futoshiki, and sets the least share of Star Battle cells left unknown."""
    if family in {"binairo", "tango"}:
        return fresh_binairo(size, rng, open_share, family, comment=comment)
    if family == "minesweeper":
        return fresh_minesweeper(size, rng, open_share, comment)
    if family == "akari":
        return fresh_akari(size, rng, tier, comment)
    if family == "queens":
        return fresh_queens(size, rng, comment=comment)
    if family == "suguru":
        return fresh_suguru(size, rng, comment=comment)
    if family == "sudoku":
        return fresh_sudoku(size, rng, open_share, comment)
    if family == "futoshiki":
        return fresh_futoshiki(size, rng, open_share, comment=comment)
    if family == "calcudoku":
        return fresh_calcudoku(size, rng, comment=comment)
    if family == "starbattle":
        stars = 2 if size >= 8 else 1
        return fresh_starbattle(size, rng, stars, open_share or 1.0, comment=comment)
    if family == "tents":
        return fresh_tents(size, rng, comment=comment)
    if family == "battleships":
        return fresh_battleships(size, rng, comment=comment)
    raise ValueError(f"no fresh builder for {family}; choose from {', '.join(FAMILIES)}")
