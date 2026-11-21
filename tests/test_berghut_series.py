"""The berghut series: 6x6, 8x8 and 10x10 Murdokus with a hallway and distance clues."""

import re
from collections.abc import Iterator

import pytest

from csp import audit, clue_search
from csp.bruteforce import murdoku as murdoku_brute
from csp.core import DEFAULT_RULES
from csp.murdoku_expression_file import keyed_expression_clue_numbers
from csp.murdoku_lang import Atom, Binary, Formula, Name, parse_statement
from csp.puzzlefile import load_board_layout
from tests.examples import example

FILES = (
    "berghut-murdoku-1.txt",
    "berghut-murdoku-2.txt",
    "berghut-murdoku-3.txt",
)
ANSWERS = {
    "berghut-murdoku-1.txt": "Greta",
    "berghut-murdoku-2.txt": "Reinhart",
    "berghut-murdoku-3.txt": "Ute",
}
TIMEOUT = 15
SIZES_AND_GUESTS = (
    ("berghut-murdoku-1.txt", 6),
    ("berghut-murdoku-2.txt", 8),
    ("berghut-murdoku-3.txt", 10),
)
# (chair cells, the rule's occupied count, how many people qualify, the trait).
CHAIRS = {
    "berghut-murdoku-1.txt": (3, 1, 1, "bikkel"),
    "berghut-murdoku-2.txt": (4, 2, 2, "bikkel"),
    "berghut-murdoku-3.txt": (4, 3, 4, "topganger"),
}
NON_AXIS_MODES = ("manhattan", "king", "euclidean", "diagonal", "areas", "knight")


def _text(name: str) -> str:
    return example(name).read_text()


def _section(text: str, name: str) -> list[str]:
    lines, inside = [], False
    for line in text.splitlines():
        if re.fullmatch(r"[A-Za-z]+:\s*", line.strip()):
            inside = line.strip() == name
            continue
        if inside and line.strip():
            lines.append(line.strip())
    return lines


@pytest.mark.parametrize(("name", "size"), SIZES_AND_GUESTS)
def test_berghut_board_size_matches_guest_count(name, size):
    text = _text(name)
    assert re.search(rf"(?m)^Size: {size}$", text), name
    assert len(_section(text, "People:")) == size, name


def _without_key_clues(text: str) -> str:
    """The puzzle without its `Key:` block, for the key-necessity checks."""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        if line.strip() == "Key:":
            skipping = True
            continue
        if skipping and re.fullmatch(r"[A-Za-z]+:\s*", line.strip()):
            skipping = False
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


@pytest.mark.parametrize("name", FILES)
def test_berghut_puzzle_is_unique_and_deductive(name):
    result = clue_search.outcome(_text(name), TIMEOUT)
    assert result.good, (name, result)
    assert result.grade in {"subsumption", "cover2", "cover3"}, (name, result.grade)


def test_berghut_series_grades_do_not_decrease():
    order = [rule.name for rule in DEFAULT_RULES]
    grades = [clue_search.outcome(_text(name), TIMEOUT).grade for name in FILES]
    assert grades == sorted(grades, key=order.index), grades


@pytest.mark.parametrize("name", FILES)
def test_berghut_axis_key_clue_is_necessary(name):
    text = _text(name)
    lines = clue_search.clue_lines(text)
    keyed = keyed_expression_clue_numbers(text)
    assert keyed, name
    base = _without_key_clues(text)
    for number in sorted(keyed):
        kept = [line for index, line in enumerate(lines, 1) if index != number]
        without = clue_search.with_clues(base, kept)
        if len(murdoku_brute.solutions(without, 2)) > 1:
            continue
        assert not clue_search.outcome(without, TIMEOUT).good, (name, number)


@pytest.mark.parametrize("name", FILES)
def test_berghut_answer_appears_in_no_clue(name):
    clues = "\n".join(clue_search.clue_lines(_text(name)))
    assert re.search(rf"\b{ANSWERS[name]}\b", clues) is None, name


def _fixed_axes(formula: Formula) -> Iterator[tuple[str, str]]:
    if isinstance(formula, Binary) and formula.operator.text == "and":
        yield from _fixed_axes(formula.left)
        yield from _fixed_axes(formula.right)
    if (
        isinstance(formula, Atom)
        and formula.operator.text == "in"
        and isinstance(formula.subject, Name)
        and isinstance(formula.target, Name)
    ):
        selector = re.fullmatch(r"(rows|columns):(?:\\d+|first|last)", formula.target.token.text)
        if selector:
            yield formula.subject.token.text, selector[1]


@pytest.mark.parametrize("name", FILES)
def test_berghut_clues_do_not_give_both_coordinates(name):
    fixed_axes: dict[str, set[str]] = {}
    for clue in clue_search.clue_lines(_text(name)):
        for person, axis in _fixed_axes(parse_statement(clue).formula):
            fixed_axes.setdefault(person, set()).add(axis)
    giveaways = sorted(person for person, axes in fixed_axes.items() if len(axes) == 2)
    assert not giveaways, f"{name} gives both coordinates for {', '.join(giveaways)}"


def _corridor_cells(board) -> set:
    region = next(region for region, label in board.region_names.items() if label == "gang")
    return {square for square in board.free if board.region_of(square) == region}


def _neighbours(cell, cells):
    return [other for other in cells if abs(other.row - cell.row) + abs(other.col - cell.col) == 1]


@pytest.mark.parametrize("name", FILES)
def test_berghut_hallway_is_one_cell_wide_and_runs_from_top_to_bottom(name):
    board = load_board_layout(_text(name))
    cells = _corridor_cells(board)
    assert any(cell.row == 0 for cell in cells), name
    assert any(cell.row == board.size - 1 for cell in cells), name
    degrees = {cell: len(_neighbours(cell, cells)) for cell in cells}
    # A simple path has two ends and no branch, so the hallway is exactly one cell wide.
    assert max(degrees.values()) <= 2, name
    ends = [cell for cell, degree in degrees.items() if degree == 1]
    assert len(ends) == 2, name
    seen, frontier = {ends[0]}, [ends[0]]
    while frontier:
        cell = frontier.pop()
        for other in _neighbours(cell, cells):
            if other not in seen:
                seen.add(other)
                frontier.append(other)
    assert seen == cells, name


@pytest.mark.parametrize("name", FILES)
def test_berghut_hallway_reaches_every_room(name):
    board = load_board_layout(_text(name))
    corridor = next(region for region, label in board.region_names.items() if label == "gang")
    graph: dict[int, set[int]] = {}
    for door in (item for item in board.edge_items if item.kind == "door"):
        first, second = (board.region_of(cell) for cell in door.cells)
        if first != second:
            graph.setdefault(first, set()).add(second)
            graph.setdefault(second, set()).add(first)
    seen, frontier = {corridor}, [corridor]
    while frontier:
        region = frontier.pop()
        for other in graph.get(region, set()):
            if other not in seen:
                seen.add(other)
                frontier.append(other)
    assert seen == set(board.region_names), name


@pytest.mark.parametrize("name", FILES)
def test_berghut_bikkel_chairs_scale_with_the_board(name):
    text = _text(name)
    cells, occupied, qualified, trait = CHAIRS[name]
    chairs = [line for line in _section(text, "Objects:") if line.startswith("stoel:")]
    assert len(chairs) == cells, name
    rules = _section(text, "Rules:")
    counted = next(rule for rule in rules if "count" in rule and "object:stoel" in rule)
    assert f"= {occupied}" in counted, name
    restricted = next(
        rule for rule in rules if "except attribute:" in rule and "object:stoel" in rule
    )
    assert f"attribute:{trait}" in restricted, name
    holders = next(line for line in _section(text, "Attributes:") if line.startswith(f"{trait}:"))
    names = holders.split(":", 1)[1].split()
    assert len(names) == qualified, name
    assert occupied <= qualified, name
    if occupied < qualified:
        # The reveal is the qualified person left without a chair.
        assert ANSWERS[name] in names, name


def _distance_mode(clue: str) -> str | None:
    match = re.search(r"dir:(\w+)", clue)
    return match[1] if match else None


@pytest.mark.parametrize("name", FILES)
def test_berghut_distance_clues_carry_the_series(name):
    text = _text(name)
    clues = clue_search.clue_lines(text)
    modes = [mode for clue in clues if (mode := _distance_mode(clue))]
    assert any(mode in {"rows", "cols"} for mode in modes), name
    assert any(mode in NON_AXIS_MODES for mode in modes), name
    keyed = [clues[number - 1] for number in keyed_expression_clue_numbers(text)]
    assert all(_distance_mode(clue) for clue in keyed), (name, keyed)


def test_berghut_series_uses_both_axes_and_both_bounds():
    clues = [clue for name in FILES for clue in clue_search.clue_lines(_text(name))]
    assert any("dir:rows" in clue for clue in clues)
    assert any("dir:cols" in clue for clue in clues)
    assert any(re.search(r"dir:rows \w+ >=", clue) for clue in clues)
    assert any(re.search(r"dir:rows \w+ <=", clue) for clue in clues)
    assert any(re.search(r"dir:\w+ \w+ = \d", clue) for clue in clues)


def test_berghut_layouts_differ():
    layouts = [audit.layout_key(_text(name), "murdoku") for name in FILES]
    assert len(set(layouts)) == len(FILES)


def test_berghut_3_windows_are_on_outside_walls():
    board = load_board_layout(_text("berghut-murdoku-3.txt"))
    for window in (item for item in board.edge_items if item.kind == "window"):
        (square,) = window.cells
        edge = {
            "top": square.row == 0,
            "bottom": square.row == board.size - 1,
            "left": square.col == 0,
            "right": square.col == board.size - 1,
        }
        assert window.side is not None and edge[window.side], window
