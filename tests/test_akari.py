from csp.akari import compile_puzzle
from csp.bruteforce import akari as brute
from csp.core import Kind, Solver

PUZZLE = """Family: akari
Size: 2
Grid:
. 2
. .
"""


def test_akari_compiles_visibility_and_numbered_wall_counts():
    model, _ = compile_puzzle(PUZZLE)

    assert sum(item.kind is Kind.COUNT for item in model.constraints) == 4
    assert sum(item.family == "bulbs do not see each other" for item in model.constraints) == 4
    assert sum(item.family == "every open cell is lit" for item in model.constraints) == 3


def test_akari_independent_search_and_engine_agree():
    (solution,) = brute.solutions(PUZZLE)
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
