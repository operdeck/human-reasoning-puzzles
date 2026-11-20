"""The berghut series: three 10x10 Murdokus with axis-distance key clues."""

import re

import pytest

from csp import audit, clue_search
from csp.bruteforce import murdoku as murdoku_brute
from csp.murdoku_expression_file import keyed_expression_clue_numbers
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


def _text(name: str) -> str:
    return example(name).read_text()


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
