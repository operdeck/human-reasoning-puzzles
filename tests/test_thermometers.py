import random

import pytest

from csp import fresh
from csp.bruteforce import thermometers as brute
from csp.core import Solver
from csp.thermometers import compile_puzzle, is_mercury, parse


def _fresh_board(size: int = 4) -> str:
    for seed in range(60):
        text = fresh.fresh("thermometers", size, random.Random(seed), 0.5)
        if text is not None:
            return text
    pytest.fail("no unique fresh Thermometers in 60 seeds")


def test_mercury_is_a_filled_prefix_from_the_bulb():
    assert is_mercury([True, True, False])
    assert is_mercury([False, False])
    assert is_mercury([True, True, True])
    assert not is_mercury([False, True])
    assert not is_mercury([True, False, True])


def test_the_model_has_a_relation_per_thermometer_and_a_count_per_line():
    model, puzzle = compile_puzzle(_fresh_board())

    assert len(model.relations) == len(puzzle.paths)
    counts = [c for c in model.constraints if c.family.startswith("filled cells per")]
    assert len(counts) == 2 * puzzle.size
    assert sum(len(path) for path in puzzle.paths) == puzzle.size**2


def test_the_engine_and_the_brute_force_agree_on_a_unique_board():
    text = _fresh_board(5)
    found = brute.solutions(text, limit=2)
    result = Solver(compile_puzzle(text)[0]).solve()

    assert len(found) == 1
    assert result.solved and result.assignment == found[0]


def test_a_solution_fills_every_thermometer_from_its_bulb_and_meets_the_counts():
    text = _fresh_board(5)
    (solution,) = brute.solutions(text)
    puzzle = parse(text)
    for path in puzzle.paths:
        assert is_mercury([solution[f"r{r + 1}c{c + 1}"] for r, c in path])
    for i, count in enumerate(puzzle.rows):
        assert sum(solution[f"r{i + 1}c{c + 1}"] for c in range(puzzle.size)) == count


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace("Family: thermometers", "Family: towers"),
        lambda t: t.replace("Size: 4", "Size: 99"),
        lambda t: t.replace("Rows:", "Rows:\n9 9 9 9\nX:"),
        lambda t: t.replace("Thermometers:\n", "Thermometers:\nr1c1 r4c4\n"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(mutate):
    with pytest.raises(ValueError):
        parse(mutate(_fresh_board(4)))
