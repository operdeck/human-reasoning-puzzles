import random

import pytest

from csp import fresh
from csp.bruteforce import hidato as brute
from csp.core import Solver
from csp.hidato import cell_assignment, compile_puzzle, parse, touching

# A 2x3 board: 1 2 3 / 6 5 4 is its only orthogonal path with 3 above the 4.
SNAKE = """Family: numbrix
Grid:
1 . 3
. . 4
"""


def _fresh_board(family: str, size: int = 4) -> str:
    for seed in range(60):
        text = fresh.fresh(family, size, random.Random(seed), 0.7)
        if text is not None:
            return text
    pytest.fail(f"no unique fresh {family} in 60 seeds")


def test_touching_depends_on_the_family():
    assert touching((0, 0), (1, 1), diagonal=True)
    assert not touching((0, 0), (1, 1), diagonal=False)
    assert touching((0, 0), (0, 1), diagonal=False)
    assert not touching((0, 0), (0, 2), diagonal=True)


def test_the_model_has_a_variable_per_number_and_a_relation_per_step():
    model, puzzle = compile_puzzle(SNAKE)

    assert puzzle.count == 6 and not puzzle.diagonal
    assert len(model.variables) == 6
    assert len(model.relations) == 5
    assert {c.family for c in model.constraints} == {
        "each number sits in one cell",
        "each cell holds one number",
    }


def test_the_snake_has_one_orthogonal_path_that_the_engine_finds():
    found = brute.solutions(SNAKE, limit=3)
    result = Solver(compile_puzzle(SNAKE)[0]).solve()

    assert len(found) == 1
    assert result.solved and result.assignment == found[0]
    numbers = cell_assignment(found[0])
    assert [numbers[f"r{r}c{c}"] for r, c in ((1, 1), (1, 2), (1, 3), (2, 3), (2, 2), (2, 1))] == [
        1,
        2,
        3,
        4,
        5,
        6,
    ]


@pytest.mark.parametrize("family", ["hidato", "numbrix"])
def test_fresh_boards_are_unique_and_the_engine_agrees(family):
    text = _fresh_board(family)
    found = brute.solutions(text, limit=2)
    result = Solver(compile_puzzle(text)[0]).solve()

    assert len(found) == 1
    assert result.solved and result.assignment == found[0]


@pytest.mark.parametrize(
    "old, new",
    [
        ("Family: numbrix", "Family: mosaic"),
        ("1 . 3", "1 . x"),
        ("1 . 3", "1 . 9"),
        ("1 . 3", "1 . 1"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(old, new):
    with pytest.raises(ValueError):
        parse(SNAKE.replace(old, new))
