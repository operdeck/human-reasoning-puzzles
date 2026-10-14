import pytest

from csp import bruteforce, sudoku
from csp.core import Kind

VARIANTS = """Givens:
. . . .
. . . .
. . . .
. . . .
Kropki:
white r1c1 r1c2
black r1c2 r2c2
Consecutive:
r2c3 r2c4
Thermometers:
r1c1 r2c1 r2c2
AntiKnight:
AntiKing:
"""


def test_sudoku_variants_parse_and_compile_to_existing_primitives():
    puzzle = sudoku.parse(VARIANTS)
    model, _ = sudoku.compile_puzzle(VARIANTS)

    assert puzzle.anti_knight and puzzle.anti_king
    assert len(puzzle.links) == len(model.relations) == 5
    assert any(kind == "anti-knight" for _, _, kind in puzzle.anti_peers())
    assert any(kind == "anti-king" for _, _, kind in puzzle.anti_peers())
    assert all(
        constraint.kind is Kind.AT_MOST_ONE
        for constraint in model.constraints
        if "anti-" in (constraint.family or "")
    )
    assert puzzle.links[0].holds(1, 2) is True
    assert puzzle.links[0].holds(1, 3) is False


def test_anti_king_adds_peers_across_jigsaw_regions():
    text = """Givens:
. . . .
. . . .
. . . .
. . . .
Boxes:
a a b b
a c b d
c c d d
a c b d
AntiKing:
"""
    puzzle = sudoku.parse(text)

    assert ((0, 0), (1, 1), "anti-king") in puzzle.anti_peers()


def test_sudoku_variants_require_orthogonal_links():
    text = VARIANTS.replace("white r1c1 r1c2", "white r1c1 r2c2")

    with pytest.raises(ValueError, match="not between neighbouring cells"):
        sudoku.parse(text)


def test_sudoku_brute_force_honors_links_and_anti_peers():
    text = """Givens:
. . . .
. . . .
. . . .
. . . .
Kropki:
white r1c1 r1c2
AntiKnight:
"""
    puzzle = sudoku.parse(text)
    solutions = bruteforce.solutions(text, limit=20)

    assert solutions
    assert all(abs(solution["r1c1"] - solution["r1c2"]) == 1 for solution in solutions)
    assert all(
        solution[sudoku.cell_name(*first)] != solution[sudoku.cell_name(*second)]
        for solution in solutions
        for first, second, _ in puzzle.anti_peers()
    )
