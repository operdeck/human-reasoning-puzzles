"""Quality checks on the published example collection."""

import pytest

from csp import queens
from csp.puzzle_lab import family_of, rate
from csp.puzzlefile import detect
from tests.examples import played_examples

QUEENS_FILES = [path for path in played_examples() if detect(path.read_text()) == "queens"]


@pytest.mark.parametrize("path", QUEENS_FILES, ids=lambda path: path.name)
def test_queens_examples_use_the_piece_of_their_family(path):
    text = path.read_text()
    allowed = {"dog", "puppy"} if family_of(text) == "dogdoku" else {"queen"}
    assert queens.parse(text).icon in allowed
    assert path.name.split("_")[0] == family_of(text)


# Known prefilled boards tracked in their own issues: Minesweeper (#119) and Akari (#121).
PREFILLED_EXCEPTIONS = {"minesweeper_3x3.txt", "minesweeper_8x8.txt", "akari_7x7.txt"}
NON_MURDOKU_FILES = [
    path
    for path in played_examples()
    if detect(path.read_text()) != "murdoku" and path.name not in PREFILLED_EXCEPTIONS
]


@pytest.mark.parametrize("path", NON_MURDOKU_FILES, ids=lambda path: path.name)
def test_examples_leave_enough_to_deduce(path):
    result = rate(path.read_text(), str(path))
    assert result.solutions == "unique"
    assert result.tier != "trivial", f"{path.name} is prefilled or needs no deduction"
