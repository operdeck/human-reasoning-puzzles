from csp.bruteforce import starbattle as brute
from csp.core import Kind, Solver
from csp.starbattle import compile_puzzle, render

PUZZLE = """Family: starbattle
Size: 4
Stars: 1
Regions:
a: amber
b: blue
c: coral
d: green
Grid:
a a a b
a b b b
c c c c
d d d d
"""


def test_starbattle_uses_count_and_no_touch_constraints():
    model, _ = compile_puzzle(PUZZLE)

    assert sum(item.kind is Kind.COUNT for item in model.constraints) == 12
    assert sum(item.family == "stars do not touch" for item in model.constraints) == 9
    assert not model.relations


def test_starbattle_backtracker_and_engine_agree():
    (solution,) = brute.solutions(PUZZLE)
    model, puzzle = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
    assert "*" in render(puzzle, model, "Solved")
