from csp.bruteforce import kakurasu as brute
from csp.core import Solver
from csp.kakurasu import compile_puzzle

PUZZLE = """Family: kakurasu
Size: 4
RowSums:
10 6 3 1
ColumnSums:
10 6 3 1
"""


def test_kakurasu_uses_generic_relations_for_weighted_lines():
    model, _ = compile_puzzle(PUZZLE)

    assert len(model.relations) == 8
    assert not model.constraints or all(
        item.family == "each cell is filled or empty" for item in model.constraints
    )


def test_kakurasu_backtracker_and_engine_agree_on_unique_board():
    (solution,) = brute.solutions(PUZZLE)
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
