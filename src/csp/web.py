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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

from . import (
    akari,
    bridges,
    dominosa,
    hidato,
    icons,
    mapcolour,
    minesweeper,
    rectangles,
    rooms,
    starbattle,
    svg,
)
from .collection import FAMILY_LABELS
from .core import Kind, Model
from .murdoku import Board, Square
from .murdoku_expression_file import load_expression_board
from .murdoku_expression_words import ExpressionWords
from .murdoku_lower import object_count_scope
from .picture import murdoku_key_symbols
from .puzzlefile import display_family, language_of, load_presentation
from .story import (
    PEER_RULE_LABELS,
    Places,
    Wording,
    attribute_list,
    clue_paragraphs,
    family_rules,
    figure_clues,
    mark_note,
    murdoku_key_items,
    murdoku_reference_rules,
    object_list,
    object_position_text,
    phrase,
    role_list,
)

SCHEMA = (
    5  # 5 added the generic `assign` block; 4 added `solutionSteps`; 3 replaced
    # `conditions` with the board `key`; 2 added `deductive`
)
LICENSE = (
    "\u00a9 Otto Perdeck. All rights reserved. You may play these puzzles on this site; "
    "any other use needs the author's written permission."
)
CELL = re.compile(r'<rect id="r(\d+)c(\d+)" class="cell"')
DIGITS = frozenset({"sudoku", "calcudoku", "futoshiki", "suguru", "towers", "kakuro"})
UNSUPPORTED = {
    "logicgrid": "The logic grid needs its own matrix view; not playable yet.",
}


@dataclass(frozen=True)
class Item:
    """A palette entry, and the solver value it stands for."""

    id: str
    label: str
    icon: str | None = None
    value: Any = True
    symbol: str = ""
    drawing: str = ""  # a ready-made SVG, for items that are not registry icons

    def to_json(self) -> dict[str, Any]:
        picture = self.drawing or (icons.to_svg(self.icon) if self.icon else None)
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
    "mosaic": [Item("black", "Black", "filled")],
    "pattern": [Item("filled", "Filled", "filled")],
    "thermometers": [Item("mercury", "Mercury", "mercury")],
    "map": [
        Item(colour, colour.capitalize(), None, colour, "", svg.swatch(svg.MAP_COLOURS[colour]))
        for colour in mapcolour.COLOURS
    ],
    "undead": [
        Item("ghost", "Ghost", "ghost", "G"),
        Item("vampire", "Vampire", "vampire", "V"),
        Item("zombie", "Zombie", "zombie", "Z"),
    ],
    "magnets": [
        Item("plus", "Plus", "magnet_plus", "+"),
        Item("minus", "Minus", "magnet_minus", "-"),
        Item("neutral", "Neutral", "magnet_neutral", "0"),
    ],
    # Each cell is one half of a domino; the name says where in the pair the cell sits.
    "dominosa": [
        Item(half, f"{half.capitalize()} half", f"domino_{half}", half)
        for half in ("left", "right", "top", "bottom")
    ],
    "binairo": [
        Item("1", "One", "disc_black", True),
        Item("0", "Zero", "disc_white", False),
    ],
}

# Families whose solver variables are not cells (domino types, rectangles): each turns its
# solution into one palette value per cell for the player's board.
CELL_SOLUTIONS: dict[str, Callable[[str, Mapping[str, Any]], dict[str, Any]]] = {
    "dominosa": lambda text, values: dominosa.cell_assignment(values),
    "rectangles": lambda text, values: rectangles.cell_assignment(values),
    "map": lambda text, values: mapcolour.cell_assignment(mapcolour.parse(text), dict(values)),
    "hidato": lambda text, values: hidato.cell_assignment(values),
}


def _number_items(text: str) -> list[Item]:
    """The numbers 1..K of a Hidato or Numbrix board, each placed in one cell."""
    return [Item(str(k), str(k), None, k) for k in range(1, hidato.parse(text).count + 1)]


def _dynamic_items(kind: str, text: str) -> list[Item]:
    """The palette of a family whose items depend on the puzzle itself."""
    return _number_items(text) if kind == "hidato" else _rectangle_items(text)


def _rectangle_items(text: str) -> list[Item]:
    """One coloured tile per number; painting a cell with it says which rectangle it is in.

    The tile is the colour the solved picture gives that rectangle, and its label tells
    the number and where it sits, so the palette and the board agree on which is which.
    """
    puzzle = rectangles.parse(text)
    items = []
    for index, cell in enumerate(puzzle.numbered):
        name = rectangles.cell_name(cell)
        items.append(
            Item(
                name,
                f"{puzzle.clues[cell[0]][cell[1]]} at {name}",
                None,
                name,
                str(puzzle.clues[cell[0]][cell[1]]),
                svg.swatch(svg.pastel(index)),
            )
        )
    return items


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


def peers(
    model: Model,
    cells: set[str],
    by_value: Mapping[Any, str],
    only: str | None = None,
    language: str = "en",
) -> list[dict[str, Any]]:
    """Groups of cells that may hold an item at most once, from the model's constraints.

    These are the rule's own "sees each other" sets: Sudoku houses and anti-knight
    pairs, or the cells an Akari bulb lights. A group lists its `items` unless it
    holds for every palette item. Cell domains and reified constraints are skipped;
    `only` keeps just the constraints of that puzzle rule (`Constraint.family`).
    """
    domains = {model.domain_of(var) for var in model.variables}
    every = set(by_value.values())
    groups: dict[tuple[str, ...], set[str]] = {}
    labels: dict[tuple[str, ...], set[str]] = {}
    for constraint in model.constraints:
        if constraint.index in domains or constraint.reified_by is not None:
            continue
        if only is not None and constraint.family != only:
            continue
        if constraint.kind is Kind.COUNT and max(constraint.allowed_counts, default=0) != 1:
            continue
        members = [(model.var_of(lit), model.value_of(lit)) for lit in constraint.literals]
        names = tuple(sorted({var for var, _ in members}))
        items = {by_value.get(value) for _, value in members}
        if len(names) != len(members) or len(names) < 2 or not set(names) <= cells:
            continue
        if None in items or len(items) != 1:
            continue
        groups.setdefault(names, set()).update(item for item in items if item is not None)
        if label := PEER_RULE_LABELS[language].get(constraint.family or ""):
            labels.setdefault(names, set()).add(label)
    return [
        {"cells": list(names)}
        | ({} if items == every else {"items": sorted(items)})
        | ({"description": ", ".join(sorted(labels[names]))} if names in labels else {})
        for names, items in sorted(groups.items())
    ]


def bundle(
    text: str,
    kind: str,
    stem: str,
    model: Model,
    solution: Mapping[str, Any],
    picture: str,
    grade: str,
    deductive: bool,
    *,
    number: int = 0,
    section: str = "",
    expressions: bool = False,
    steps: Sequence[str] = (),
    steps_complete: bool = False,
) -> dict[str, Any]:
    """The JSON-ready bundle of one puzzle; `model` is compiled but not yet solved.

    `number` and `section` place it in the collection (see `collection.arrange`).
    `steps` are the worked solution's paragraphs (inline Markdown emphasis only),
    and `steps_complete` says whether they account for the whole solution.
    """
    display_name = display_family(text, kind)
    family_label = FAMILY_LABELS.get(display_name, FAMILY_LABELS[kind])
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "id": stem,
        "family": kind,
        "familyLabel": family_label,
        "section": section or family_label,
        "number": number,
        "title": _title(text, kind, stem),
        "grade": grade,
        "deductive": deductive,
        "static": f"{stem}.svg",
        "license": LICENSE,
    }
    if kind == "murdoku":
        out |= _murdoku(text, solution, expressions=expressions)
    else:
        out |= _family(text, kind, model, solution, picture)
    if steps:
        out["solutionSteps"] = {"paragraphs": list(steps), "complete": steps_complete}
    out["headings"] = {
        **out.get("headings", {}),
        "solution_steps": phrase(text, "web.solution_steps"),
        "spoiler": phrase(text, "web.spoiler"),
        "steps_incomplete": phrase(text, "web.steps_incomplete"),
        "steps_unavailable": phrase(text, "web.steps_unavailable"),
    }
    return out


def _murdoku(
    text: str, solution: Mapping[str, Any], *, expressions: bool = False
) -> dict[str, Any]:
    board, rule_statements, clue_statements = load_expression_board(text)
    presentation = load_presentation(text)
    count_details = []
    if rule_statements or clue_statements:
        words = ExpressionWords.read(board, text)
        numbered = [
            *((None, statement) for statement in rule_statements),
            *enumerate(clue_statements, 1),
        ]
        for number, statement in numbered:
            scope = object_count_scope(board, [statement])
            if scope:
                caption = presentation.clue_text.get(number) if number is not None else None
                count_details.append(
                    (scope, caption if caption is not None else words.statement(statement))
                )
    entries = figure_clues(text, expressions=clue_statements, expression_rules=rule_statements)
    say = Wording.read(text)
    palette = []
    for entry in entries.figures:
        person = entry.person
        figure = presentation.figures.get(person)
        item: dict[str, Any] = {"id": person, "label": entry.name, "symbol": person[:2]}
        if entry.description:
            item["description"] = entry.description
        icon = icons.object_icon(figure.icon) if figure and figure.icon else None
        if icon is not None and (picture := icons.to_svg(icon)):
            item["svg"] = picture
        palette.append(item)
    placed = {str(sq): person for person, sq in solution.items() if isinstance(sq, Square)}
    rules = murdoku_reference_rules(
        text, expression_rules=rule_statements, expression_clues=clue_statements
    )
    return {
        "language": language_of(text),
        "size": [board.size, board.size],
        "playable": True,
        "palette": palette,
        "textNames": list(
            dict.fromkeys(
                name
                for entry in entries.figures
                for name in (entry.person, entry.name, say.words.get(entry.person, entry.person))
            )
        ),
        "placement": {
            "perItem": 1,
            "blocked": sorted(str(sq) for sq in board.blocked),
        },
        "autoMark": {"default": True, "mark": "cross", "onPlace": LINES},
        "givens": {},
        "solution": dict(sorted(placed.items())),
        "cellDetails": _murdoku_cell_details(board, text, count_details=count_details),
        "detailTargets": _murdoku_point_details(board, text),
        "headings": {
            **{
                key: phrase(text, f"doc.{key}")
                for key in (
                    "rules_title",
                    "clues",
                    "question",
                    "figures",
                    "figure_clues",
                    "other_clues",
                    "attributes",
                    "roles",
                    "objects",
                    "key",
                )
            },
            "cell": phrase(text, "web.cell"),
            "cell_figure": phrase(text, "web.cell_figure"),
            "extras": phrase(text, "web.extras"),
        },
        "combineExtras": True,
        "intro": presentation.intro,
        "rules": rules,
        "clues": clue_paragraphs(
            text,
            presentation.clue_text,
            expressions=clue_statements,
        ),
        "clueEntries": [
            {
                "id": clue.id,
                "text": clue.text,
                "sources": [
                    *(f"clue:{number}" for number in clue.sources),
                    *(f"rule:{number}" for number in clue.rule_sources),
                ],
                **({"item": clue.person} if clue.person is not None else {}),
            }
            for clue in (
                *(clue for figure in entries.figures for clue in figure.clues),
                *entries.other,
            )
        ],
        "key": [
            {
                "name": shown[:1].upper() + shown[1:] if shown else label,
                "text": label if shown else "",
                "svg": symbol,
            }
            for name, label, shown in murdoku_key_items(text)
            for symbol in murdoku_key_symbols(board, name)
        ],
        "question": presentation.question,
        "reveal": " ".join(presentation.reveal),
        "attributes": [{"name": n, "text": t} for n, t in attribute_list(text)],
        "roles": [{"name": n, "text": t} for n, t in role_list(text)],
        "objects": _objects(text),
    }


def _murdoku_cell_details(
    board: Board,
    text: str,
    *,
    count_details: Iterable[tuple[Iterable[Square], str]] = (),
) -> dict[str, list[str]]:
    """Player-visible board facts for each cell, independent of the solution."""
    say = Wording.read(text)
    places = Places(board, say)
    tags = {tag: board.region_ids(names) for tag, names in board.area_tags.items()}
    details: dict[str, list[str]] = {}
    for row in range(board.size):
        for col in range(board.size):
            square = Square(row, col)
            region = board.region_of(square)
            name = board.region_names[region].replace("_", " ")
            lines = [say("web.cell_area", name=name[:1].upper() + name[1:])]
            for tag, regions in tags.items():
                if region in regions:
                    name = say.words.get(tag, tag.replace("_", " "))
                    lines.append(say("web.cell_tag", name=name))
            details[str(square)] = lines

    def add(squares: Iterable[Square], line: str) -> None:
        for square in squares:
            lines = details[str(square)]
            if line not in lines:
                lines.append(line)

    for obj in board.objects:
        condition = object_position_text(say, obj.name, obj.kind == "standable")
        name = places.thing(obj.name, as_label=True)
        add(obj.squares, say("web.cell_object", name=name, condition=condition))
    for item in board.edge_items:
        name = places.thing(item.name)
        if item.name == item.kind and item.name not in say.words:
            name = say(f"web.cell_{item.kind}", name=name)
        add(item.cells, say("web.cell_touch", name=name))
    for point in board.point_objects:
        add(point.cells, say("web.cell_touch", name=places.thing(point.name)))
    for mark in board.marks:
        add(mark.cells, mark_note(mark, say))
    for scope, caption in count_details:
        caption = caption[:1].upper() + caption[1:]
        if not caption.endswith((".", "!", "?")):
            caption += "."
        add(scope, caption)
    return details


def _murdoku_point_details(board: Board, text: str) -> list[dict[str, Any]]:
    """Hover targets in cell units, including the part outside the grid."""
    say = Wording.read(text)
    targets = []
    for point in board.point_objects:
        row2, col2 = point.anchor
        name = say.words.get(point.name, point.name.replace("_", " "))
        targets.append(
            {
                "x": (col2 - 1) / 2,
                "y": (row2 - 1) / 2,
                "radius": 1 / 3,
                "lines": [name[:1].upper() + name[1:], say("doc.clue_on_point")],
            }
        )
    return targets


def _objects(text: str) -> list[dict[str, Any]]:
    """Each kind of object with its picture and how figures may occupy its squares."""
    say = Wording.read(text)
    out = []
    for kind, label, standable in object_list(text):
        entry = {
            "name": label,
            "text": object_position_text(say, kind, standable),
        }
        icon = icons.object_icon(kind)
        if icon is not None and (picture := icons.to_svg(icon)):
            entry["svg"] = picture
        out.append(entry)
    return out


def _rooms_key(puzzle: rooms.Puzzle) -> list[dict[str, Any]]:
    """A room puzzle's properties: the words its clues use, with the plan's icons."""
    out = []
    for tag in puzzle.tags:
        entry: dict[str, Any] = {"name": puzzle.phrase(tag), "text": ""}
        icon = icons.object_icon(tag)
        markup = icons.to_svg(icon) if icon is not None else None
        if markup:
            entry["svg"] = markup
        out.append(entry)
    return out


def _cell_boxes(picture: str) -> dict[str, tuple[float, float, float, float]]:
    """The interactive plan's cell rectangles, by plan cell id."""
    root = ElementTree.fromstring(picture)
    return {
        node.attrib["id"]: (
            float(node.attrib["x"]),
            float(node.attrib["y"]),
            float(node.attrib["width"]),
            float(node.attrib["height"]),
        )
        for node in root.iter()
        if node.attrib.get("class") == "cell" and "id" in node.attrib
    }


def _room_slots(box: tuple[float, float, float, float], capacity: int) -> list[list[float]]:
    """A tidy row of slots inside a room box, independent of its cell count."""
    if capacity < 1:
        return []
    x, y, width, height = box
    pad = max(4.0, min(width, height) * 0.08)
    gap_ratio = 0.18
    available = max(width - 2 * pad, 1.0)
    size = min(max(8.0, min(width, height) * 0.18), height * 0.18)
    size = min(size, available / (capacity * (1 + gap_ratio)))
    size = max(6.0, size)
    gap = size * gap_ratio
    total = capacity * size + (capacity - 1) * gap
    start = x + (width - total) / 2
    top = y + height * 0.40
    top = min(top, y + height * 0.62 - size)
    top = max(top, y + pad)
    return [
        [round(start + index * (size + gap), 1), round(top, 1), round(size, 1)]
        for index in range(capacity)
    ]


def _rooms(text: str, solution: Mapping[str, Any], picture: str) -> dict[str, Any]:
    """The generic assignment interaction for a room plan.

    People are the items, rooms are the targets: a room is a multi-cell container
    with a capacity, so the player state is keyed by person and valued by room.
    """
    puzzle = rooms.parse(text)
    boxes = _cell_boxes(picture)
    label_to_key = {room.label: room.key for room in puzzle.rooms}
    room_keys = set(label_to_key.values())
    items = [{"id": person, "label": person, "symbol": person[:2]} for person in puzzle.people]
    targets = []
    for room in puzzle.rooms:
        cells = [f"r{row + 1}c{col + 1}" for row, col in room.cells]
        rects = [boxes[cell] for cell in cells if cell in boxes]
        if not rects:
            continue
        left = min(rect[0] for rect in rects)
        top = min(rect[1] for rect in rects)
        right = max(rect[0] + rect[2] for rect in rects)
        bottom = max(rect[1] + rect[3] for rect in rects)
        box = (left, top, right - left, bottom - top)
        properties = [puzzle.phrase(tag) for tag in puzzle.tags if room.key in puzzle.tags[tag]]
        targets.append(
            {
                "id": room.key,
                "label": room.title,
                "capacity": room.capacity,
                "box": [round(value, 1) for value in box],
                "cells": cells,
                "colour": room.colour,
                "properties": properties,
                "slots": _room_slots(box, room.capacity),
            }
        )
    placed: dict[str, str] = {}
    for person, value in solution.items():
        if not isinstance(value, str):
            continue
        key = label_to_key.get(value)
        if key is None and value in room_keys:
            key = value
        if key is not None:
            placed[person] = key
    nl = language_of(text) == "nl"
    return {
        "playable": True,
        "assign": {
            "items": items,
            "targets": targets,
            "instructions": (
                "Kies een persoon en tik een kamer aan. Tik een kamer en daarna een "
                "persoon om ze te koppelen. Cijfertoetsen kiezen een persoon, Delete "
                "haalt iemand weg; Tab of pijltjes gaan langs de kamers."
                if nl
                else "Choose a person and tap a room. Tap a room and then a person to "
                "pair them. Number keys choose a person, Delete removes one; Tab or "
                "arrow keys move between rooms."
            ),
        },
        "givens": {},
        "solution": placed,
        "placement": {"blocked": []},
    }


def _family(
    text: str, kind: str, model: Model, solution: Mapping[str, Any], picture: str
) -> dict[str, Any]:
    cells = grid_cells(picture)
    out: dict[str, Any] = {
        "language": language_of(text),
        "size": [max(r for r, _ in cells), max(c for _, c in cells)] if cells else [0, 0],
        "rules": family_rules(text, kind),
        "headings": {"rules_title": phrase(text, "doc.rules_title")},
        "clues": [],
        "key": [],
        "question": "",
    }
    if kind == "rooms":
        room_plan = rooms.parse(text)
        presentation = load_presentation(text)
        out |= {
            "size": [room_plan.height, room_plan.width],
            "clues": room_plan.clue_lines,
            "question": presentation.question,
            "intro": presentation.intro,
            "key": _rooms_key(room_plan),
            "rules": out["rules"] + room_plan.rule_lines,
            "headings": {
                "rules_title": phrase(text, "doc.rules_title"),
                "clues": phrase(text, "doc.clues"),
                "question": phrase(text, "doc.question"),
                "key": phrase(text, "doc.key"),
            },
        }
        return out | _rooms(text, solution, picture)
    if kind in UNSUPPORTED:
        return out | {"playable": False, "unsupported": UNSUPPORTED[kind]}
    if kind == "bridges":
        return out | _bridges(text, solution, picture)
    if kind == "minesweeper":
        total_mines = minesweeper.parse(text).total_mines
        if total_mines is not None:
            out["totals"] = {"mine": total_mines}
    names = [f"r{row}c{col}" for row, col in cells]
    # Cage targets are clues for the player to enter, not prefilled digits.
    fixed = {} if kind == "calcudoku" else _fixed(model)
    regions: dict[str, str] = {}
    scopes: list[dict[str, Any]] = []
    auto = True
    mark = "cross"
    groups: list[dict[str, Any]] = []
    if kind in DIGITS:
        values = sorted({model.value_of(lit) for var in names for lit in _domain(model, var)})
        items = [Item(str(v), str(v), None, v) for v in values]
        auto = False
    elif kind == "starbattle":
        puzzle_sb = starbattle.parse(text)
        if puzzle_sb.stars == 1:
            fixed = {
                starbattle.cell_name((row, col)): True
                for row, line in enumerate(puzzle_sb.givens)
                for col, value in enumerate(line)
                if value == 1
            }
            solution = starbattle.cell_assignment(puzzle_sb, solution)
        items = [Item(puzzle_sb.icon, puzzle_sb.icon.capitalize(), puzzle_sb.icon)]
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
    else:
        items = ITEMS[kind] if kind in ITEMS else _dynamic_items(kind, text)
        if kind == "tents":
            scopes = NEIGHBOURS
        if kind in CELL_SOLUTIONS:
            solution = CELL_SOLUTIONS[kind](text, solution)
            fixed = CELL_SOLUTIONS[kind](text, fixed)
            if kind == "rectangles":
                puzzle = rectangles.parse(text)
                own_cells = {
                    rectangles.cell_name(cell): rectangles.cell_name(cell)
                    for cell in puzzle.numbered
                }
                fixed = own_cells | fixed
    by_value = {item.value: item.id for item in items}
    if kind in DIGITS:
        groups = peers(model, set(names), by_value, language=language_of(text))
    elif kind == "akari":
        groups = peers(model, set(names), by_value, only=akari.SIGHT)
        scopes = [{"scope": "peers"}]
        mark = "light"
    placed = {
        cell: by_value[value]
        for cell, value in solution.items()
        if cell in names and value in by_value
    }
    givens = {cell: by_value[v] for cell, v in fixed.items() if v in by_value}
    variables = (
        set(names) if kind == "starbattle" or kind in CELL_SOLUTIONS else set(model.variables)
    )
    blocked = [
        cell
        for cell in names
        if cell not in variables
        or (cell in fixed and fixed[cell] not in by_value)
        # a cell-level solution covers every playable cell, so any other cell is blocked
        or (kind in CELL_SOLUTIONS and cell not in solution)
    ]
    out |= {
        "playable": True,
        "palette": [item.to_json() for item in items],
        "placement": {"perCell": 1, "blocked": blocked},
        "autoMark": {
            "default": (auto and bool(scopes)) or bool(groups),
            "mark": mark,
            "onPlace": scopes,
        },
        "givens": dict(sorted(givens.items())),
        "solution": dict(sorted(placed.items())),
    }
    if regions:
        out["regions"] = regions
    if groups:
        out["peers"] = groups
    if kind in DIGITS:
        out["notes"] = True
    return out


def _bridges(text: str, solution: Mapping[str, Any], picture: str) -> dict[str, Any]:
    """Export a generic numbered-node/segment interaction, not cell placements."""
    puzzle = bridges.parse(text)
    root = ElementTree.fromstring(picture)
    boxes = {
        node.attrib["id"]: tuple(float(node.attrib[key]) for key in ("x", "y", "width", "height"))
        for node in root.iter()
        if node.attrib.get("class") == "cell"
    }
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    scale = next(iter(boxes.values()))[2]
    nodes = [
        {"id": bridges.cell_name(cell), "total": total} for cell, total in puzzle.islands.items()
    ]
    segments = []
    for pair in puzzle.pairs:
        endpoints = [bridges.cell_name(cell) for cell in pair]
        points = [
            (boxes[name][0] + boxes[name][2] / 2, boxes[name][1] + boxes[name][3] / 2)
            for name in endpoints
        ]
        drawings = {}
        for count in (1, 2):
            drawing = svg.Canvas(width, height, background="none")
            icons.bridge(drawing, points[0], points[1], count, scale=scale)
            drawings[str(count)] = drawing.to_svg()
        conflicts = [
            bridges.pair_name(other) for other in puzzle.pairs if bridges.crosses(pair, other)
        ]
        segments.append(
            {
                "id": bridges.pair_name(pair),
                "endpoints": endpoints,
                "values": ["0", "1", "2"],
                "drawings": drawings,
                "target": [*points[0], *points[1]],
                "hitWidth": scale * 0.32,
                "conflicts": conflicts,
            }
        )
    nl = language_of(text) == "nl"
    return {
        "size": [puzzle.height, puzzle.width],
        "playable": True,
        "palette": [
            Item("1", "Enkele brug" if nl else "Single bridge", "bridge_single", 1).to_json(),
            Item("2", "Dubbele brug" if nl else "Double bridge", "bridge_double", 2).to_json(),
        ],
        "placement": {"blocked": []},
        "givens": {},
        "solution": {
            bridges.pair_name(pair): str(solution[bridges.pair_name(pair)])
            for pair in puzzle.pairs
            if solution.get(bridges.pair_name(pair)) in (1, 2)
        },
        "links": {
            "nodes": nodes,
            "segments": segments,
            "connected": True,
            "instructions": (
                "Kies een enkele of dubbele brug en tik twee eilanden aan. "
                "Tik een verbinding om te wisselen tussen geen, één en twee bruggen. "
                "Tab of pijltjestoetsen kiezen een verbinding; 0, 1 en 2 wijzigen die."
                if nl
                else "Choose a single or double bridge and tap two islands. "
                "Tap a corridor to cycle between no bridge, one and two. "
                "Tab or arrow keys select a corridor; 0, 1 and 2 change it."
            ),
        },
        "intro": load_presentation(text).intro,
    }


def _domain(model: Model, var: str) -> list[Any]:
    if var not in model.variables:
        return []
    return list(model.constraints[model.domain_of(var)].literals)


def index_entry(data: Mapping[str, Any]) -> dict[str, Any]:
    """The landing page's preview and metadata for one bundle."""
    keys = (
        "id",
        "number",
        "section",
        "title",
        "family",
        "familyLabel",
        "size",
        "grade",
        "deductive",
        "static",
        "playable",
    )
    entry = {key: data[key] for key in keys}
    if "unsupported" in data:
        entry["unsupported"] = data["unsupported"]
    return entry
