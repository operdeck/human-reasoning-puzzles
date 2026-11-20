"""The berghut series: 9x9, 10x10 and 11x11 Murdokus with axis-distance key clues."""

import re
from collections.abc import Iterator
from itertools import permutations

import pytest

from csp import audit, clue_search
from csp.bruteforce import murdoku as murdoku_brute
from csp.murdoku_eval import grounded_dependencies, holds_grounded
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
    ("berghut-murdoku-1.txt", 9),
    ("berghut-murdoku-2.txt", 10),
    ("berghut-murdoku-3.txt", 11),
)


def _text(name: str) -> str:
    return example(name).read_text()


@pytest.mark.parametrize(("name", "size"), SIZES_AND_GUESTS)
def test_berghut_board_size_matches_guest_count(name, size):
    text = _text(name)
    assert re.search(rf"(?m)^Size: {size}$", text), name
    people = text.split("People:", 1)[1].split("\nRules:", 1)[0]
    assert sum(bool(line.strip()) for line in people.splitlines()) == size, name


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
    assert result.grade in {"relations", "subsumption", "cover2"}, (name, result.grade)


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
        selector = re.fullmatch(r"(rows|columns):(?:\d+|first|last)", formula.target.token.text)
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


def test_berghut_2_brunhilds_clues_do_not_pin_her_to_one_square():
    text = _text("berghut-murdoku-2.txt")
    board = load_board_layout(text)
    people = {"Brunhild", "Hannelore"}
    clues = [
        (clue, deps)
        for line in clue_search.clue_lines(text)
        if (deps := grounded_dependencies(board, clue := parse_statement(line)))
        and "Brunhild" in deps
    ]
    assert clues and all(deps <= people for _, deps in clues)
    candidates = {
        first
        for first, second in permutations(board.free, 2)
        if first.row != second.row
        and first.col != second.col
        and all(
            holds_grounded(clue, board, {"Brunhild": first, "Hannelore": second}, deps)
            for clue, deps in clues
        )
    }
    assert len(candidates) > 1


def test_berghut_series_covers_every_axis_form():
    keys = "\n".join(
        line for name in FILES for line in _text(name).splitlines() if line.startswith("clue: ")
    )
    for mode in ("dir:rows", "dir:cols"):
        assert re.search(rf"{mode} \w+ >=", keys), (mode, ">=")
        assert re.search(rf"{mode} \w+ <=", keys), (mode, "<=")
    assert re.search(r"dir:cols \w+ = \d", keys)


def test_berghut_layouts_differ():
    layouts = [audit.layout_key(_text(name), "murdoku") for name in FILES]
    assert len(set(layouts)) == len(FILES)
