"""Quality checks on the published example collection."""

import pytest

from csp import queens
from csp.puzzle_lab import family_of
from csp.puzzlefile import detect
from tests.examples import played_examples

QUEENS_FILES = [path for path in played_examples() if detect(path.read_text()) == "queens"]


@pytest.mark.parametrize("path", QUEENS_FILES, ids=lambda path: path.name)
def test_queens_examples_use_the_piece_of_their_family(path):
    text = path.read_text()
    allowed = {"dog", "puppy"} if family_of(text) == "dogdoku" else {"queen"}
    assert queens.parse(text).icon in allowed
    assert path.name.split("_")[0] == family_of(text)
