"""Every `Key:` clue must be load-bearing, for every published Murdoku.

A `Key:` entry marks the clue a puzzle is built around (a themed distance, an
avoidance rule). `csp.clue_search thin` never drops such a clue; this test adds
the other half of the contract: removing one must cost the puzzle its unique
solution or its deduction, so a declared key can never be decoration.
"""

import pytest

from csp import clue_search
from csp.bruteforce import murdoku as murdoku_brute
from csp.murdoku_expression_file import keyed_expression_clue_numbers
from csp.puzzlefile import detect
from tests.examples import played_examples

pytestmark = pytest.mark.solutions

TIMEOUT = 15


def _keyed_puzzles() -> list[tuple[str, str, set[int]]]:
    found = []
    for path in played_examples():
        text = path.read_text()
        if detect(text) != "murdoku":
            continue
        numbers = keyed_expression_clue_numbers(text)
        if numbers:
            found.append((path.name, text, numbers))
    return found


KEYED = _keyed_puzzles()


def test_some_published_murdoku_declares_key_clues():
    assert KEYED, "no example declares Key clues; the contract below would be untested"


@pytest.mark.parametrize(("name", "text", "numbers"), KEYED, ids=[name for name, *_ in KEYED])
def test_every_key_clue_is_necessary(name, text, numbers):
    lines = clue_search.clue_lines(text)
    assert numbers <= set(range(1, len(lines) + 1)), name
    base = clue_search.without_keys(text)
    for number in sorted(numbers):
        kept = [line for index, line in enumerate(lines, 1) if index != number]
        without = clue_search.with_clues(base, kept)
        if len(murdoku_brute.solutions(without, 2)) > 1:
            continue
        assert not clue_search.outcome(without, TIMEOUT).good, (name, number)
