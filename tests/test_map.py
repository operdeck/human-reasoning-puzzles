import random

import pytest

from csp import fresh
from csp.bruteforce import mapcolour as brute
from csp.core import Solver
from csp.mapcolour import compile_puzzle, parse

# Four regions that all touch each other need all four colours.
CORNERS = """Family: map
Regions:
a a b b
a c c b
d d c b
Givens:
a red
b yellow
c green
"""


def _fresh_board(size: int = 6) -> str:
    for seed in range(100):
        text = fresh.fresh("map", size, random.Random(seed), 0.6)
        if text is not None:
            return text
    pytest.fail("no unique fresh Map in 100 seeds")


def test_borders_are_pairs_of_regions_sharing_a_side_not_a_corner():
    puzzle = parse(CORNERS)

    assert puzzle.borders == [("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("c", "d")]
    assert ("b", "d") not in puzzle.borders


def test_the_model_has_a_colour_per_region_and_a_separation_per_border_and_colour():
    model, puzzle = compile_puzzle(CORNERS)

    assert len(model.variables) == 4
    separation = [i for i in model.constraints if i.family == "neighbouring regions differ"]
    assert len(separation) == 4 * len(puzzle.borders)


def test_a_free_region_with_two_open_colours_leaves_two_answers():
    found = brute.solutions(CORNERS, limit=5)
    result = Solver(compile_puzzle(CORNERS)[0]).solve()

    # d touches a (red) and c (green) only, so blue, yellow are both open: two answers.
    assert sorted(solution["d"] for solution in found) == ["blue", "yellow"]
    assert not result.solved


def test_a_fresh_board_is_unique_and_solved_by_the_engine():
    text = _fresh_board()
    found = brute.solutions(text, limit=2)
    result = Solver(compile_puzzle(text)[0]).solve()

    assert len(found) == 1
    assert result.solved and result.assignment == found[0]
    puzzle = parse(text)
    for a, b in puzzle.borders:
        assert found[0][a] != found[0][b]


@pytest.mark.parametrize(
    "old, new",
    [
        ("Family: map", "Family: mosaic"),
        ("a red", "a purple"),
        ("a red", "z red"),
        ("a red", "a red\na blue"),
        ("b yellow", "b red"),
        ("d d c b", "d d c a"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(old, new):
    with pytest.raises(ValueError):
        parse(CORNERS.replace(old, new))
