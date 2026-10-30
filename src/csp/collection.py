"""The order, numbers and sections of a set of puzzle files, shared by the booklet
and the web player's index.

A puzzle's category is the folder it sits in below the folder all the files have
in common, so `examples/japanese-food/food-murdoku-2.txt` is in "Japanese food".
Murdoku comes first, by category ("Demo" leads), then the other families. Within
a section files sort naturally, so `x-6x6` comes before `x-12x12`.
"""

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

FAMILY_LABELS = {
    "murdoku": "Murdoku",
    "sudoku": "Sudoku",
    "calcudoku": "Calcudoku",
    "futoshiki": "Futoshiki",
    "queens": "Queens",
    "suguru": "Suguru",
    "starbattle": "Star Battle",
    "binairo": "Binairo",
    "tango": "Tango",
    "tents": "Tents and Trees",
    "minesweeper": "Minesweeper",
    "akari": "Akari",
    "kakurasu": "Kakurasu",
    "battleships": "Battleships",
    "logicgrid": "Logic grid",
}
FIRST_CATEGORY = "demo"


@dataclass(frozen=True)
class Listed:
    """A puzzle file in its place: `number` counts from 1 over the whole set."""

    path: Path
    kind: str
    category: str | None
    number: int
    family_label: str | None = None

    @property
    def section(self) -> str:
        """The heading the puzzle is listed under."""
        family = self.family_label or FAMILY_LABELS.get(self.kind, self.kind.capitalize())
        return f"{family} \u00b7 {category_label(self.category)}" if self.category else family


def category_label(slug: str) -> str:
    """A folder name for reading: "japanese-food" becomes "Japanese food"."""
    words = " ".join(word for word in re.split(r"[-_ ]+", slug) if word)
    return words[:1].upper() + words[1:]


def _natural(text: str) -> list[tuple[int, str]]:
    return [(int(part), "") if part.isdigit() else (0, part) for part in re.split(r"(\d+)", text)]


def categories(paths: Iterable[Path]) -> dict[Path, str | None]:
    """Each file's category: its top folder below the files' common folder."""
    paths = list(paths)
    if not paths:
        return {}
    root = Path(os.path.commonpath([path.resolve().parent for path in paths]))
    out: dict[Path, str | None] = {}
    for path in paths:
        parts = path.resolve().parent.relative_to(root).parts
        out[path] = parts[0] if parts else None
    return out


def arrange(
    kinds: Mapping[Path, str], family_names: Mapping[Path, str] | None = None
) -> list[Listed]:
    """The files of `kinds` (path to family) in reading order, numbered."""
    found = categories(kinds)
    labels = {
        path: FAMILY_LABELS.get((family_names or {}).get(path, kind), FAMILY_LABELS.get(kind, kind))
        for path, kind in kinds.items()
    }

    def key(path: Path) -> tuple[object, ...]:
        kind, category = kinds[path], found[path]
        family = (kind != "murdoku", labels[path].casefold())
        place = (category is not None, category != FIRST_CATEGORY, category_label(category or ""))
        return (*family, *place, _natural(path.stem.casefold()), str(path))

    ordered = sorted(kinds, key=key)
    return [
        Listed(path, kinds[path], found[path], n, labels[path]) for n, path in enumerate(ordered, 1)
    ]
