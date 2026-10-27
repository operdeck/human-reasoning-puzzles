"""Collection checks across puzzle files: shared solutions, shared layouts and
sections whose files are not listed from easier to harder.

Solutions and layouts are compared as grids up to rotation and reflection, and
region letters are compared by shape, so a relabelled or turned copy of an
existing board still counts as the same board.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from csp import bruteforce, cli, report
from csp.collection import arrange
from csp.core import DEFAULT_RULES, Solver
from csp.puzzle_lab import family_of, rate
from csp.puzzlefile import detect, read_sections

TIER_ORDER = ("trivial", "easy", "medium", "hard")
GRADE_ORDER = tuple(rule.name for rule in DEFAULT_RULES)
# Sections that hold a board's fixed structure rather than its clues.
LAYOUT_SECTIONS = {
    "akari": ("Grid",),
    "calcudoku": ("Grid",),
    "murdoku": ("Grid",),
    "queens": ("Grid",),
    "starbattle": ("Grid",),
    "suguru": ("Grid",),
    "sudoku": ("Boxes",),
    "tents": ("Trees",),
}
# Series folders whose order the author fixed (for example a running story);
# they are still checked for shared solutions and layouts.
FIXED_ORDER = {
    "wie-doet-het-met-wie": "story order chosen by the author",
}
# Families whose solution only means something on its region map: the same
# placement on a different map is a different puzzle.
REGION_SOLUTIONS = {"murdoku", "queens", "starbattle"}
CELL = re.compile(r"r(\d+)c(\d+)")

Grid = tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Profile:
    path: Path
    kind: str
    section: str
    category: str | None
    grade: str
    tier: str
    solution: object
    layout: object

    @property
    def difficulty(self) -> tuple[int, int]:
        """Tier first (non-Murdoku only), then the hardest rule the solve used."""
        tier = TIER_ORDER.index(self.tier) if self.tier in TIER_ORDER else 0
        grade = GRADE_ORDER.index(self.grade) if self.grade in GRADE_ORDER else -1
        return tier, grade

    @property
    def label(self) -> str:
        return f"{self.tier} ({self.grade})" if self.tier else self.grade


@dataclass
class Audit:
    shared_solutions: list[list[Path]] = field(default_factory=list)
    shared_layouts: list[list[Path]] = field(default_factory=list)
    out_of_order: dict[str, list[Profile]] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not (self.shared_solutions or self.shared_layouts or self.out_of_order)


def _symmetries(cells: dict[tuple[int, int], str]) -> list[tuple[tuple[int, int, str], ...]]:
    """The cells after each of the eight turns and mirrorings of the square board."""
    if not cells:
        return [()]
    size = max(max(r, c) for r, c in cells) + 1
    out = []
    for turn in range(4):
        for mirror in (False, True):
            moved = {}
            for (r, c), value in cells.items():
                for _ in range(turn):
                    r, c = c, size - 1 - r
                if mirror:
                    c = size - 1 - c
                moved[(r, c)] = value
            out.append(tuple(sorted((r, c, v) for (r, c), v in moved.items())))
    return out


def _relabel(value: str, names: dict[str, str]) -> str:
    """Region letters by order of first appearance; other symbols as they are."""
    region, _, rest = value.partition("/")
    if region.isalpha():
        region = names.setdefault(region, f"#{len(names)}")
    return f"{region}/{rest}" if rest else region


def _canonical(cells: dict[tuple[int, int], str], relabel: bool = False) -> object:
    """The smallest of a grid's eight turned and mirrored forms."""
    forms = []
    for form in _symmetries(cells):
        if relabel:
            names: dict[str, str] = {}
            form = tuple((r, c, _relabel(v, names)) for r, c, v in form)
        forms.append(form)
    return min(forms)


def _layout_cells(text: str, kind: str) -> dict[tuple[int, int], str]:
    lines = [line for line in read_sections(text).get("Grid", []) if line.strip()]
    rows = [line.split() if " " in line.strip() else list(line.strip()) for line in lines]
    return {(r, c): v for r, row in enumerate(rows) for c, v in enumerate(row)}


def solution_key(text: str, kind: str) -> object:
    """A board-shaped fingerprint of the puzzle's (first) solution, or None."""
    found = bruteforce.solutions(text, kind, limit=1)
    if not found:
        return None
    cells: dict[tuple[int, int], str] = {}
    other = []
    for key, value in found[0].items():
        if hasattr(value, "row") and hasattr(value, "col"):
            cells[(value.row, value.col)] = "x"
        elif (match := CELL.fullmatch(str(value))) and not CELL.fullmatch(str(key)):
            cells[(int(match.group(1)) - 1, int(match.group(2)) - 1)] = "x"
        elif match := CELL.fullmatch(str(key)):
            cells[(int(match.group(1)) - 1, int(match.group(2)) - 1)] = str(value)
        else:
            other.append((str(key), str(value)))
    if other:
        return (kind, tuple(sorted(other)))
    if kind in REGION_SOLUTIONS:
        regions = _layout_cells(text, kind)
        board = {cell: f"{region}/{cells.get(cell, '')}" for cell, region in regions.items()}
        return (kind, _canonical(board, relabel=True))
    return (kind, _canonical(cells))


def layout_key(text: str, kind: str) -> object:
    """A fingerprint of the board's fixed structure (regions, cages, walls), or None."""
    sections = read_sections(text)
    parts = []
    for name in LAYOUT_SECTIONS.get(kind, ()):
        lines = [line for line in sections.get(name, []) if line.strip()]
        if not lines:
            continue
        rows = [line.split() if " " in line.strip() else list(line.strip()) for line in lines]
        if all(len(row) == len(rows) for row in rows):
            cells = {(r, c): v for r, row in enumerate(rows) for c, v in enumerate(row)}
            parts.append((name, _canonical(cells, relabel=True)))
        else:
            parts.append((name, tuple(" ".join(line.split()) for line in lines)))
    return (kind, tuple(parts)) if parts else None


def profile(path: Path, section: str, category: str | None = None) -> Profile:
    text = path.read_text()
    kind = detect(text)
    if kind == "murdoku":
        model = cli.load(text, kind).model.clone()
        fired: list[str] = []
        result = Solver(model).solve(on_step=lambda rule, steps: fired.append(rule))
        grade, tier = (report.grade(fired) if result.solved else "unsolved"), ""
    else:
        rating = rate(text, str(path))
        grade, tier = rating.grade, rating.tier
    return Profile(
        path, kind, section, category, grade, tier, solution_key(text, kind), layout_key(text, kind)
    )


def profiles(paths: Iterable[Path]) -> list[Profile]:
    """Each puzzle file in listing order, with its section, difficulty and fingerprints."""
    texts = {path: path.read_text() for path in paths}
    kinds = {path: detect(text) for path, text in texts.items()}
    names = {path: family_of(text) for path, text in texts.items()}
    return [profile(item.path, item.section, item.category) for item in arrange(kinds, names)]


def boards(paths: Iterable[Path]) -> list[Profile]:
    """Fingerprints only, without grading: enough to find shared solutions and layouts."""
    found = []
    for path in paths:
        text = path.read_text()
        kind = detect(text)
        found.append(
            Profile(path, kind, "", None, "", "", solution_key(text, kind), layout_key(text, kind))
        )
    return found


def audit(items: Sequence[Profile]) -> Audit:
    found = Audit()
    for attribute, target in (
        ("solution", found.shared_solutions),
        ("layout", found.shared_layouts),
    ):
        groups: dict[object, list[Path]] = defaultdict(list)
        for item in items:
            key = getattr(item, attribute)
            if key is not None:
                groups[key].append(item.path)
        target.extend(paths for paths in groups.values() if len(paths) > 1)
    sections: dict[str, list[Profile]] = defaultdict(list)
    for item in items:
        if item.category not in FIXED_ORDER:
            sections[item.section].append(item)
    for name, members in sections.items():
        levels = [member.difficulty for member in members]
        if levels != sorted(levels):
            found.out_of_order[name] = members
    return found


def puzzle_files(paths: Iterable[str | Path]) -> list[Path]:
    """The .txt puzzle files under the given files or folders."""
    out: list[Path] = []
    for raw in paths:
        path = Path(raw)
        out.extend(sorted(path.rglob("*.txt")) if path.is_dir() else [path])
    return out
