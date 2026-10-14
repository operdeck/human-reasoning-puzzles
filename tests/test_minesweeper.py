from csp.bruteforce import minesweeper as brute
from csp.core import Kind, Solver
from csp.minesweeper import compile_puzzle, parse

PUZZLE = """Family: minesweeper
Size: 3
Clues:
1 1 1
1 . 1
1 1 1
TotalMines:
1
"""


def test_minesweeper_compiles_neighborhood_and_total_counts():
    model, _ = compile_puzzle(PUZZLE)

    assert sum(item.kind is Kind.COUNT for item in model.constraints) == 9
    assert sum(item.family == "mine count in clue neighborhood" for item in model.constraints) == 8
    assert sum(item.family == "total mine count" for item in model.constraints) == 1


def test_minesweeper_independent_search_and_engine_agree():
    (solution,) = brute.solutions(PUZZLE)
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution


def test_minesweeper_neighborhood_respects_corners_edges_and_center():
    puzzle = parse(PUZZLE)

    assert len(puzzle.neighbors((0, 0))) == 3
    assert len(puzzle.neighbors((0, 1))) == 5
    assert len(puzzle.neighbors((1, 1))) == 8
