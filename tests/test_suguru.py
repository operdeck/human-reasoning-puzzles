from csp.bruteforce import suguru as brute
from csp.core import Kind, Solver
from csp.suguru import compile_puzzle

PUZZLE = """Family: suguru
Size: 4
Regions:
a: amber
b: blue
c: coral
d: green
Grid:
a a b b
a a b b
c c d d
c c d d
Givens:
1 2 1 2
3 4 3 4
1 2 1 2
3 4 3 4
"""


def test_suguru_compiles_region_domains_and_touching_pairs():
    model, puzzle = compile_puzzle(PUZZLE)

    assert model.variables[0] == "r1c1"
    assert model.variables[-1] == "r4c4"
    assert sum(item.family == "each number once per region" for item in model.constraints) == 16
    assert all(
        item.kind is Kind.AT_MOST_ONE
        for item in model.constraints
        if item.family == "no equal numbers in touching cells"
    )
    assert len(puzzle.neighbors((1, 1))) == 8


def test_suguru_independent_search_and_engine_agree():
    (solution,) = brute.solutions(PUZZLE)
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
