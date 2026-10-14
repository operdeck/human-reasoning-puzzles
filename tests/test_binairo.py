from csp.binairo import compile_puzzle
from csp.bruteforce import binairo as brute
from csp.core import Solver

PUZZLE = """Family: binairo
Size: 4
Givens:
0 0 1 1
0 1 0 1
1 0 1 0
1 1 0 0
"""


def test_binairo_compiles_line_counts_and_hidden_unique_line_relations():
    model, _ = compile_puzzle(PUZZLE)

    assert len(model.relations) == 48
    assert len(model.variables) == 16
    assert len(model.all_variables) > len(model.variables)
    assert sum(item.family == "no three equal in a line" for item in model.constraints) == 16
    no_three = [item for item in model.constraints if item.family == "no three equal in a line"]
    assert len(no_three) == 16
    assert all(
        model.var_of(literal) in model.variables
        for constraint in no_three
        for literal in constraint.literals
    )


def test_binairo_backtracker_and_engine_agree():
    (solution,) = brute.solutions(PUZZLE)
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
