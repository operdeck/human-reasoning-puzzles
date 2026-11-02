import random

import pytest

from csp import fresh
from csp.bruteforce import dominosa as brute
from csp.core import Solver
from csp.dominosa import cell_assignment, compile_puzzle, parse


def _unique_board(top: int = 2) -> str:
    for seed in range(200):
        text = fresh.fresh("dominosa", top, random.Random(seed))
        if text is not None:
            return text
    pytest.fail("no unique fresh Dominosa in 200 seeds")


def test_the_model_is_one_variable_per_domino_type_and_one_cover_per_cell():
    model, puzzle = compile_puzzle(_unique_board(2))

    assert len(puzzle.types) == 6 and puzzle.rows == 3 and puzzle.cols == 4
    assert len(model.variables) == 6
    families = {item.family for item in model.constraints}
    assert families == {"each domino is used once", "each cell is covered once"}
    covers = [i for i in model.constraints if i.family == "each cell is covered once"]
    assert len(covers) == 12


def test_the_engine_and_the_brute_force_agree_and_cells_get_their_halves():
    text = _unique_board(3)
    (solution,) = brute.solutions(text)
    result = Solver(compile_puzzle(text)[0]).solve()

    assert result.solved and result.assignment == solution
    halves = cell_assignment(solution)
    assert len(halves) == 20
    assert sorted(set(halves.values())) in (
        ["left", "right"],
        ["bottom", "left", "right", "top"],
        ["bottom", "top"],
    )
    assert list(halves.values()).count("left") == list(halves.values()).count("right")
    assert list(halves.values()).count("top") == list(halves.values()).count("bottom")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace("Family: dominosa", "Family: towers"),
        lambda t: t.replace("Numbers:", "Numbers:\n9 9 9 9"),
        lambda t: "Family: dominosa\nNumbers:\n0 1\n1 0\n",
        lambda t: t.rsplit("\n", 2)[0] + "\n",
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(mutate):
    with pytest.raises(ValueError):
        parse(mutate(_unique_board(2)))
