from itertools import product

import pytest

from csp.battleships import compile_puzzle, parse
from csp.bruteforce import battleships as brute
from csp.core import Contradiction, Kind, Solver

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


FLEET = """Family: battleships
Size: 4
Fleet: 3 2 1
RowCounts: 3 0 3 0
ColumnCounts: 2 2 1 1
Givens:
W M E 0
0 0 0 0
W E 0 O
0 0 0 0
"""


def test_fleet_compiles_to_generic_constraints_with_hidden_positions():
    model, puzzle = compile_puzzle(FLEET)
    assert puzzle.fleet == (3, 2, 1)
    assert len(model.variables) == 16
    assert len(model.all_variables) > 16
    result = Solver(model).solve()
    assert result.solved
    assert result.assignment == brute.solutions(FLEET)[0]
    assert any(c.family == "fleet count per ship length" for c in model.constraints)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (FLEET.replace("3 2 1", "3 2"), "Fleet total"),
        (FLEET.replace("3 2 1", "0 6"), "ship lengths"),
        (FLEET.replace("Fleet: 3 2 1\n", "") + "\nFleet:\n", "ship lengths"),
        (FLEET.replace("W M E 0", "W ? E 0"), "Givens cells"),
        (FLEET.replace("Fleet: 3 2 1\n", ""), "require a Fleet"),
        (FLEET.replace("RowCounts: 3 0 3 0", "RowCounts: 2 1 3 0"), "exceed a row"),
    ],
)
def test_invalid_fleet_and_segment_definitions(source, message):
    with pytest.raises(ValueError, match=message):
        parse(source)


def test_north_south_ends_and_generic_occupied_givens():
    source = FLEET.replace(
        "W M E 0\n0 0 0 0\nW E 0 O\n0 0 0 0", "N 0 N 0\nM 0 S 0\nS 0 0 0\n0 0 O 0"
    ).replace(
        "RowCounts: 3 0 3 0\nColumnCounts: 2 2 1 1", "RowCounts: 2 2 1 1\nColumnCounts: 3 0 3 0"
    )
    assert len(brute.solutions(source)) == 1
    assert Solver(compile_puzzle(source)[0]).solve().solved
    assert not brute.solutions(source.replace("N 0 N 0", "S 0 N 0"))
    header, givens = source.split("Givens:\n")
    for token in ("N", "M", "S", "O"):
        givens = givens.replace(token, "1")
    assert len(brute.solutions(header + "Givens:\n" + givens)) == 1


def test_compiler_and_independent_search_agree_on_all_small_boards():
    """Exhaustively check straightness, fleet lengths, touching and water."""
    for bits in product((False, True), repeat=9):
        if sum(bits) != 3:
            continue
        rows = [sum(bits[r * 3 : r * 3 + 3]) for r in range(3)]
        cols = [sum(bits[c::3]) for c in range(3)]
        source = (
            "Family: battleships\nSize: 3\nFleet: 2 1\n"
            f"RowCounts: {' '.join(map(str, rows))}\n"
            f"ColumnCounts: {' '.join(map(str, cols))}\nGivens:\n"
            + "\n".join(" ".join(str(int(v)) for v in bits[r * 3 : r * 3 + 3]) for r in range(3))
        )
        expected = bool(brute.solutions(source))
        try:
            model, _ = compile_puzzle(source)
            actual = Solver(model).solve().solved
        except (ValueError, Contradiction):
            actual = False
        assert actual == expected, source
