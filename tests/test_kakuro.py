import random

import pytest

from csp import fresh
from csp.bruteforce import kakuro as brute
from csp.core import Solver
from csp.kakuro import compile_puzzle, parse, run_holds

# Columns sum to 3 (1+2) and 4 (1+3), rows to 3 and 4: only 2 1 / 1 3 fits.
SMALL = """Family: kakuro
Grid:
X 3\\ 4\\
\\3 . .
\\4 . .
"""


def _fresh_board(size: int = 5) -> str:
    for seed in range(40):
        text = fresh.fresh("kakuro", size, random.Random(seed), 0.5)
        if text is not None:
            return text
    pytest.fail("no unique fresh Kakuro in 40 seeds")


def test_run_holds_needs_distinct_digits_and_the_right_sum():
    assert run_holds([1, 2], 3)
    assert not run_holds([2, 2], 4)
    assert not run_holds([1, 3], 3)
    assert run_holds([9, 8, 7], 24)


def test_runs_are_read_from_clue_cells_to_the_next_black_cell():
    puzzle = parse(SMALL)

    assert [(run.direction, run.total, len(run.cells)) for run in puzzle.runs] == [
        ("down", 3, 2),
        ("down", 4, 2),
        ("across", 3, 2),
        ("across", 4, 2),
    ] or sorted((run.direction, run.total) for run in puzzle.runs) == [
        ("across", 3),
        ("across", 4),
        ("down", 3),
        ("down", 4),
    ]
    assert len(puzzle.whites) == 4


def test_the_small_board_has_exactly_one_answer_for_both_solvers():
    (found,) = brute.solutions(SMALL, limit=3)
    result = Solver(compile_puzzle(SMALL)[0]).solve()

    assert found == {"r2c2": 2, "r2c3": 1, "r3c2": 1, "r3c3": 3}
    assert result.solved and result.assignment == found


def test_the_model_is_a_digit_per_white_cell_and_a_relation_per_run():
    model, puzzle = compile_puzzle(SMALL)

    assert len(model.variables) == len(puzzle.whites) == 4
    assert len(model.relations) == len(puzzle.runs) == 4


def test_a_fresh_board_is_unique_and_the_engine_agrees():
    text = _fresh_board()
    found = brute.solutions(text, limit=2)
    result = Solver(compile_puzzle(text)[0]).solve()

    assert len(found) == 1
    assert result.solved and result.assignment == found[0]
    puzzle = parse(text)
    for run in puzzle.runs:
        digits = [found[0][f"r{r + 1}c{c + 1}"] for r, c in run.cells]
        assert sum(digits) == run.total and len(set(digits)) == len(digits)


@pytest.mark.parametrize(
    "old, new",
    [
        ("Family: kakuro", "Family: mosaic"),
        ("3\\ 4\\", "3\\ 4x"),
        ("3\\ 4\\", "30\\ 4\\"),
        ("\\3 .", "\\3 X"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(old, new):
    with pytest.raises(ValueError):
        parse(SMALL.replace(old, new))
