"""Browser bundles for the online game: one JSON document per puzzle file.

The site never parses puzzle files. Everything it needs to show and play a
puzzle is here: the palette, which cells are blocked or given, the auto-mark
scopes, the solution to check against, and the rules, clues and condition
meanings to read beside the board. The board itself is the interactive SVG
from `picture`, written next to the bundle.

A bundle's `solution` maps a cell id (`r1c1` is top left) to a palette item;
cells it leaves out stay empty. Families that cannot be played yet still get a
bundle, with `playable` false, so the site can show them read-only.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from . import icons, queens, starbattle
from .core import Model
from .murdoku import Square
from .puzzlefile import language_of, load_board, load_presentation
from .story import (
    FAMILY_RULES,
    attribute_list,
    board_notes,
    clue_paragraphs,
    condition_list,
    phrase,
    role_list,
)

SCHEMA = 1
LICENSE = (
    "\u00a9 Otto Perdeck. All rights reserved. You may play these puzzles on this site; "
    "any other use needs the author's written permission."
)
CELL = re.compile(r'<rect id="r(\d+)c(\d+)" class="cell"')
DIGITS = frozenset({"sudoku", "calcudoku", "futoshiki", "suguru"})
FAMILY_LABELS = {
    "murdoku": "Murdoku",
    "sudoku": "Sudoku",
    "calcudoku": "Calcudoku",
    "futoshiki": "Futoshiki",
    "queens": "Queens",
    "suguru": "Suguru",
    "starbattle": "Star Battle",
    "binairo": "Binairo and Tango",
    "tents": "Tents and Trees",
    "minesweeper": "Minesweeper",
    "akari": "Akari",
    "kakurasu": "Kakurasu",
    "battleships": "Battleships",
    "logicgrid": "Logic grid",
}
UNSUPPORTED = {"logicgrid": "The logic grid needs its own matrix view; not playable yet."}


@dataclass(frozen=True)
class Item:
    """A palette entry, and the solver value it stands for."""

    id: str
    label: str
    icon: str | None = None
    value: Any = True
    symbol: str = ""

    def to_json(self) -> dict[str, Any]:
        picture = icons.to_svg(self.icon) if self.icon else None
        out: dict[str, Any] = {"id": self.id, "label": self.label}
        out["symbol"] = self.symbol or (icons.symbol(self.icon) if self.icon else self.id)
        if picture:
            out["svg"] = picture
        return out


# The palette of each family whose cells hold a solver value; values not listed are "empty".
ITEMS = {
    "starbattle": [Item("star", "Star", "star")],
    "tents": [Item("tent", "Tent", "tent")],
    "minesweeper": [Item("mine", "Mine", "mine")],
    "akari": [Item("bulb", "Light", "bulb")],
    "kakurasu": [Item("filled", "Shaded", "filled")],
    "battleships": [Item("ship", "Ship", "filled")],
    "binairo": [
        Item("1", "One", "disc_black", True),
        Item("0", "Zero", "disc_white", False),
    ],
}

NEIGHBOURS = [{"scope": "neighbors8"}]
LINES = [{"scope": "row"}, {"scope": "col"}]


def _title(text: str, kind: str, stem: str) -> str:
    title = load_presentation(text).title
    if title:
        return title
    if kind == "murdoku":
        comment = next((line for line in text.splitlines() if line.startswith("# ")), "")
        return comment.removeprefix("# ").strip() or stem
    return stem.replace("_", " ").capitalize()


def grid_cells(picture: str) -> list[tuple[int, int]]:
    """The (row, col) of every cell element in an interactive picture, 1-based."""
    return [(int(row), int(col)) for row, col in CELL.findall(picture)]


def _fixed(model: Model) -> dict[str, Any]:
    """Variables the puzzle itself decides before any deduction: its givens."""
    return {var: value for var in model.variables if (value := model.chosen(var)) is not None}


def bundle(
    text: str,
    kind: str,
    stem: str,
    model: Model,
    solution: Mapping[str, Any],
    picture: str,
    grade: str,
) -> dict[str, Any]:
    """The JSON-ready bundle of one puzzle; `model` is compiled but not yet solved."""
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "id": stem,
        "family": kind,
        "familyLabel": FAMILY_LABELS[kind],
        "title": _title(text, kind, stem),
        "grade": grade,
        "static": f"{stem}.svg",
        "license": LICENSE,
    }
    if kind == "murdoku":
        out |= _murdoku(text, solution)
    else:
        out |= _family(text, kind, model, solution, picture)
    return out


def _murdoku(text: str, solution: Mapping[str, Any]) -> dict[str, Any]:
    board, _ = load_board(text)
    presentation = load_presentation(text)
    palette = []
    for person in board.people:
        figure = presentation.figures.get(person)
        item: dict[str, Any] = {"id": person, "label": person, "symbol": person[:2]}
        if figure and figure.description:
            item["description"] = figure.description
        icon = icons.object_icon(figure.icon) if figure and figure.icon else None
        if icon is not None and (picture := icons.to_svg(icon)):
            item["svg"] = picture
        palette.append(item)
    placed = {str(sq): person for person, sq in solution.items() if isinstance(sq, Square)}
    rules = [*(presentation.intro or [phrase(text, "doc.rules")]), *board_notes(text)]
    return {
        "language": language_of(text),
        "size": [board.size, board.size],
        "playable": True,
        "palette": palette,
        "placement": {
            "perItem": 1,
            "blocked": sorted(str(sq) for sq in board.blocked),
        },
        "autoMark": {"default": True, "mark": "cross", "onPlace": LINES},
        "givens": {},
        "solution": dict(sorted(placed.items())),
        "headings": {
            key: phrase(text, f"doc.{key}")
            for key in (
                "rules_title",
                "clues",
                "conditions",
                "question",
                "figures",
                "attributes",
                "roles",
            )
        },
        "rules": rules,
        "clues": clue_paragraphs(text, presentation.clue_text),
        "conditions": [{"name": n, "text": t} for n, t in condition_list(text)],
        "question": presentation.question,
        "attributes": [{"name": n, "text": t} for n, t in attribute_list(text)],
        "roles": [{"name": n, "text": t} for n, t in role_list(text)],
    }


def _family(
    text: str, kind: str, model: Model, solution: Mapping[str, Any], picture: str
) -> dict[str, Any]:
    cells = grid_cells(picture)
    out: dict[str, Any] = {
        "language": "en",
        "size": [max(r for r, _ in cells), max(c for _, c in cells)] if cells else [0, 0],
        "rules": [FAMILY_RULES[kind]],
        "clues": [],
        "conditions": [],
        "question": "",
    }
    if kind in UNSUPPORTED:
        return out | {"playable": False, "unsupported": UNSUPPORTED[kind]}
    names = [f"r{row}c{col}" for row, col in cells]
    fixed = _fixed(model)
    regions: dict[str, str] = {}
    scopes: list[dict[str, Any]] = []
    auto = True
    if kind == "queens":
        puzzle = queens.parse(text)
        items = [Item(puzzle.icon, puzzle.icon.capitalize(), puzzle.icon)]
        regions = {
            f"r{r + 1}c{c + 1}": region
            for r, line in enumerate(puzzle.grid)
            for c, region in enumerate(line)
        }
        placed = {str(cell): puzzle.icon for cell in solution.values()}
        givens = {str(cell): puzzle.icon for cell in fixed.values()}
        blocked: list[str] = []
        scopes = [*LINES, {"scope": "region"}, *NEIGHBOURS]
    else:
        if kind in DIGITS:
            values = sorted({model.value_of(lit) for var in names for lit in _domain(model, var)})
            items = [Item(str(v), str(v), None, v) for v in values]
            auto = False
        else:
            items = ITEMS[kind]
        if kind == "starbattle":
            puzzle_sb = starbattle.parse(text)
            regions = {
                f"r{r + 1}c{c + 1}": region
                for r, line in enumerate(puzzle_sb.areas.cells)
                for c, region in enumerate(line)
            }
            full = {"whenFull": puzzle_sb.stars}
            scopes = [
                *NEIGHBOURS,
                {"scope": "row", **full},
                {"scope": "col", **full},
                {"scope": "region", **full},
            ]
        elif kind == "tents":
            scopes = NEIGHBOURS
        by_value = {item.value: item.id for item in items}
        placed = {
            cell: by_value[value]
            for cell, value in solution.items()
            if cell in names and value in by_value
        }
        givens = {cell: by_value[v] for cell, v in fixed.items() if v in by_value}
        variables = set(model.variables)
        blocked = [
            cell
            for cell in names
            if cell not in variables or (cell in fixed and fixed[cell] not in by_value)
        ]
    out |= {
        "playable": True,
        "palette": [item.to_json() for item in items],
        "placement": {"perCell": 1, "blocked": blocked},
        "autoMark": {"default": auto and bool(scopes), "mark": "cross", "onPlace": scopes},
        "givens": dict(sorted(givens.items())),
        "solution": dict(sorted(placed.items())),
    }
    if regions:
        out["regions"] = regions
    return out


def _domain(model: Model, var: str) -> list[Any]:
    if var not in model.variables:
        return []
    return list(model.constraints[model.domain_of(var)].literals)


def index_entry(data: Mapping[str, Any]) -> dict[str, Any]:
    """The landing page's line for one bundle."""
    keys = ("id", "title", "family", "familyLabel", "size", "grade", "playable")
    entry = {key: data[key] for key in keys}
    if "unsupported" in data:
        entry["unsupported"] = data["unsupported"]
    return entry
