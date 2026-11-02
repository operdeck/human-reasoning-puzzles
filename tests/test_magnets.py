import random

import pytest

from csp import fresh
from csp.bruteforce import magnets as brute
from csp.core import Solver
from csp.magnets import compile_puzzle, parse


def _fresh_board(size: int = 4) -> str:
    for seed in range(100):
        text = fresh.fresh("magnets", size, random.Random(seed), 0.3)
        if text is not None:
            return text
    pytest.fail("no unique fresh Magnets in 100 seeds")


def test_the_model_has_a_relation_per_domino_and_a_count_per_clue():
    text = _fresh_board()
    model, puzzle = compile_puzzle(text)

    assert len(model.relations) == len(puzzle.dominoes) == 8
    counts = [i for i in model.constraints if i.family == "poles counted per line"]
    assert len(counts) == len(puzzle.clue_lines)
    separation = [i for i in model.constraints if i.family == "touching magnets repel"]
    assert len(separation) == 2 * len(puzzle.foreign_neighbours())


def test_the_engine_and_the_brute_force_agree_on_a_unique_board():
    for size in (4, 6):
        text = _fresh_board(size)
        found = brute.solutions(text, limit=2)
        result = Solver(compile_puzzle(text)[0]).solve()

        assert len(found) == 1
        assert result.solved and result.assignment == found[0]


def test_a_solution_honours_every_rule_checked_from_the_text_alone():
    text = _fresh_board(6)
    (solution,) = brute.solutions(text)
    puzzle = parse(text)
    n = puzzle.size
    at = {(r, c): solution[f"r{r + 1}c{c + 1}"] for r in range(n) for c in range(n)}

    for first, second in puzzle.dominoes.values():
        assert {at[first], at[second]} in ({"+", "-"}, {"0"})
    for (r, c), mine in at.items():
        for dr, dc in ((0, 1), (1, 0)):
            near = at.get((r + dr, c + dc))
            if near and puzzle.ids[r][c] != puzzle.ids[r + dr][c + dc] and mine != "0":
                assert near != mine
    for clue, index, count in puzzle.clue_lines:
        sign = "+" if clue.startswith("Plus") else "-"
        assert sum(at[cell] == sign for cell in puzzle.line_cells(clue, index)) == count


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace("Family: magnets", "Family: towers"),
        lambda t: t.replace("Size: 4", "Size: 5"),
        lambda t: t.replace("PlusTop:", "PlusTop:\n9 9 9 9\nX:"),
        lambda t: t.replace("Dominoes:", "Dominoes:\nzz zz zz zz"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(mutate):
    with pytest.raises(ValueError):
        parse(mutate(_fresh_board()))
