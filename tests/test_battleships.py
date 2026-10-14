from csp.battleships import compile_puzzle
from csp.bruteforce import battleships as brute
from csp.core import Kind, Solver

PUZZLE = """Family: battleships
Size: 4
RowCounts:
4 3 2 1
ColumnCounts:
4 3 2 1
"""


def test_battleships_counts_only_uses_generic_count_constraints():
    model, _ = compile_puzzle(PUZZLE)

    assert sum(item.kind is Kind.COUNT for item in model.constraints) == 8
    assert all(
        item.family and "occupied-cell count" in item.family
        for item in model.constraints
        if item.kind is Kind.COUNT
    )


def test_battleships_counts_only_has_unique_independent_solution():
    (solution,) = brute.solutions(PUZZLE)
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
