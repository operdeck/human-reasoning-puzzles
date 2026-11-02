import random

import pytest

from csp import fresh
from csp.bruteforce import pattern as brute
from csp.core import Solver
from csp.pattern import compile_puzzle, parse, runs

# A plus sign on a 3x3 board.
PLUS = """Family: pattern
Rows:
1
3
1
Columns:
1
3
1
"""


def _fresh_board(size: int = 5) -> str:
    for seed in range(100):
        text = fresh.fresh("pattern", size, random.Random(seed), 0.4)
        if text is not None:
            return text
    pytest.fail("no unique fresh Pattern in 100 seeds")


def test_runs_lists_the_lengths_of_filled_stretches():
    assert runs([True, True, False, True]) == (2, 1)
    assert runs([False, False]) == ()
    assert runs([True, False, True, False, True]) == (1, 1, 1)
    assert runs([True, True, True]) == (3,)


def test_the_model_is_boolean_cells_and_a_relation_per_line():
    model, puzzle = compile_puzzle(PLUS)

    assert len(model.relations) == puzzle.rows + puzzle.cols == 6
    assert {item.family for item in model.constraints} == {"each cell is filled or empty"}


def test_the_plus_is_solved_by_the_engine_and_the_brute_force():
    (solution,) = brute.solutions(PLUS)
    result = Solver(compile_puzzle(PLUS)[0]).solve()

    assert result.solved and result.assignment == solution
    assert [name for name, filled in solution.items() if filled] == [
        "r1c2",
        "r2c1",
        "r2c2",
        "r2c3",
        "r3c2",
    ]


def test_a_fresh_board_is_unique_and_solved_by_the_engine():
    text = _fresh_board(6)
    found = brute.solutions(text, limit=2)
    result = Solver(compile_puzzle(text)[0]).solve()

    assert len(found) == 1
    assert result.solved and result.assignment == found[0]


def test_an_ambiguous_board_has_two_brute_force_answers():
    swap = "Family: pattern\nRows:\n1\n1\nColumns:\n1\n1\n"
    assert len(brute.solutions(swap, limit=3)) == 2


@pytest.mark.parametrize(
    "old, new",
    [
        ("Family: pattern", "Family: mosaic"),
        ("Rows:\n1\n3\n1", "Rows:\n1\n3"),
        ("Columns:\n1\n3\n1", "Columns:\n1\n3\n1 2"),
        ("Rows:\n1\n3\n1", "Rows:\n1\n3\n0 2"),
        ("Rows:\n1\n3\n1", "Rows:\n1\n3\nx"),
        ("Rows:\n1\n3\n1", "Rows:\n1\n3\n3"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(old, new):
    with pytest.raises(ValueError):
        parse(PLUS.replace(old, new))
