from csp.bruteforce import tents as brute
from csp.core import Kind, Solver
from csp.tents import compile_puzzle

PUZZLE = """Family: tents
Size: 4
Trees:
. T . .
. . . T
T . . .
. . T .
RowCounts:
1 1 1 1
ColumnCounts:
1 1 1 1
"""


def test_tents_uses_counts_and_non_touching_constraints():
    model, _ = compile_puzzle(PUZZLE)

    assert sum(item.kind is Kind.COUNT for item in model.constraints) >= 12
    assert any(item.family == "tents do not touch" for item in model.constraints)
    assert any(item.family == "one tent per tree" for item in model.constraints)


def test_tents_independent_search_and_engine_agree():
    solutions = brute.solutions(PUZZLE, limit=2)
    assert len(solutions) == 1
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solutions[0]
