import random

import pytest

from csp import fresh
from csp.bruteforce import mosaic as brute
from csp.core import Solver
from csp.mosaic import compile_puzzle, parse

# A cross: the centre and its four neighbours are black.
CROSS = """Family: mosaic
Size: 3
Clues:
3 4 3
4 5 4
3 4 3
"""


def test_a_numbered_window_counts_its_own_cell():
    model, puzzle = compile_puzzle(CROSS)

    assert len(puzzle.window((0, 0))) == 4
    assert len(puzzle.window((1, 1))) == 9
    counts = [
        item for item in model.constraints if item.family == "black cells in a numbered window"
    ]
    assert len(counts) == 9
    assert all(
        len(item.literals) == len(puzzle.window(cell))
        for item, cell in zip(counts, puzzle.numbered, strict=True)
    )


def test_the_engine_and_the_brute_force_agree_on_the_cross():
    (solution,) = brute.solutions(CROSS)
    model, _ = compile_puzzle(CROSS)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
    assert solution["r2c2"] and solution["r1c1"] is False


def test_a_fresh_board_is_unique_and_solved_by_the_engine():
    # A unique board can still lie beyond the ladder, so look for one the engine closes.
    for seed in range(40):
        text = fresh.fresh("mosaic", 5, random.Random(seed), 0.5)
        result = Solver(compile_puzzle(text)[0]).solve() if text else None
        if result and result.solved:
            break
    else:
        pytest.fail("no unique, engine-solved fresh Mosaic in 40 seeds")
    found = brute.solutions(text, limit=2)

    assert len(found) == 1
    assert result.assignment == found[0]


@pytest.mark.parametrize(
    "old, new",
    [
        ("3 4 3\n4 5 4\n3 4 3", "3 4 3\n4 5 4"),
        ("4 5 4", "4 x 4"),
        ("3 4 3\n4 5 4\n3 4 3", "9 4 3\n4 5 4\n3 4 3"),
        ("Family: mosaic", "Family: minesweeper"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(old, new):
    with pytest.raises(ValueError):
        parse(CROSS.replace(old, new))
