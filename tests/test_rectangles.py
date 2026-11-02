import random

import pytest

from csp import fresh
from csp.bruteforce import rectangles as brute
from csp.core import Solver
from csp.rectangles import cell_assignment, compile_puzzle, parse

# 2 x 3: a 4-cell block of one number and a 2-cell strip.
PUZZLE = """Family: rectangles
Clues:
. 4 .
. . 2
"""


def _fresh_board(size: int = 5) -> str:
    for seed in range(100):
        text = fresh.fresh("rectangles", size, random.Random(seed), 0.5)
        if text is not None:
            return text
    pytest.fail("no unique fresh Rectangles in 100 seeds")


def test_candidates_hold_their_number_and_no_other():
    puzzle = parse("Family: rectangles\nClues:\n. 4 . .\n. . . 4\n")
    # The strip, and the two 2x2 blocks that stay clear of the other 4.
    assert sorted(puzzle.candidates((0, 1))) == [(0, 0, 0, 3), (0, 0, 1, 1), (0, 1, 1, 2)]


def test_the_model_is_one_variable_per_number_and_one_cover_per_cell():
    model, puzzle = compile_puzzle(_fresh_board())

    assert len(model.variables) == len(puzzle.numbered)
    assert {item.family for item in model.constraints} == {
        "each number owns one rectangle",
        "each cell is in one rectangle",
    }
    covers = [i for i in model.constraints if i.family == "each cell is in one rectangle"]
    assert len(covers) == puzzle.rows * puzzle.cols


def test_the_engine_and_the_brute_force_agree_and_every_cell_has_an_owner():
    text = _fresh_board(6)
    (solution,) = brute.solutions(text)
    model, puzzle = compile_puzzle(text)
    result = Solver(model).solve()

    assert result.solved and result.assignment == solution
    owners = cell_assignment(solution)
    assert len(owners) == puzzle.rows * puzzle.cols
    for number in puzzle.numbered:
        area = puzzle.clues[number[0]][number[1]]
        name = f"r{number[0] + 1}c{number[1] + 1}"
        assert list(owners.values()).count(name) == area


@pytest.mark.parametrize(
    "old, new",
    [
        ("Family: rectangles", "Family: mosaic"),
        ("2\n", "x\n"),
        (". 4 .", ". 4"),
        (". 4 .", ". 5 ."),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(old, new):
    with pytest.raises(ValueError):
        parse(PUZZLE.replace(old, new))
