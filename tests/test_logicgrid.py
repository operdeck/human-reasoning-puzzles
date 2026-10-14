from csp.bruteforce import logicgrid as brute
from csp.core import Solver
from csp.logicgrid import compile_puzzle

PUZZLE = """Family: logicgrid
Size: 3
Categories:
resident: Ada Ben Cal
color: red blue green
pet: cat dog fox
Clues:
same Ada red
same Ben dog
same Cal fox
same red cat
left_of dog green
before Ada Ben
"""


def test_logicgrid_compiles_categories_and_relations():
    model, puzzle = compile_puzzle(PUZZLE)

    assert model.variables == ["Ada", "Ben", "Cal", "red", "blue", "green", "cat", "dog", "fox"]
    assert len(model.relations) == len(puzzle.clues) == 6
    assert len(model.constraints) == 18


def test_logicgrid_backtracker_and_engine_agree_on_unique_positions():
    (solution,) = brute.solutions(PUZZLE)
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
