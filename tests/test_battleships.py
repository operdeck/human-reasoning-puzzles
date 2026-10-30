from itertools import product

import pytest

from csp.battleships import compile_puzzle, parse
from csp.bruteforce import battleships as brute
from csp.core import Contradiction, Kind, Solver
from tests.examples import played_examples

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


@pytest.mark.parametrize("language", ["en", "nl"])
def test_fleet_rules_describe_the_actual_model(language):
    from csp.story import family_rules

    rules = family_rules(FLEET + f"\nLanguage:\n{language}\n", "battleships")
    assert "3, 2, 1" in rules[0]
    assert "diagona" in rules[2]
    assert "water" in rules[4]


def test_explain_prints_named_deductions(capsys):
    from csp.cli import main
    from tests.examples import example

    assert main([str(example("battleships_1_6x6_fleet.txt")), "--explain"]) == 0
    output = capsys.readouterr().out
    assert "count" in output
    assert "ship" in output
    assert "Solved" in output


@pytest.mark.parametrize(
    "path", [p for p in played_examples() if p.name.startswith("battleships_")]
)
def test_gallery_fleets_are_nontrivial_and_need_the_ship_rules(path):
    from csp.puzzle_lab import rate

    text = path.read_text()
    puzzle = parse(text)
    assert puzzle.fleet
    staircase = list(range(1, puzzle.size + 1))
    assert sorted(puzzle.row_counts) != staircase
    assert sorted(puzzle.column_counts) != staircase
    rating = rate(text)
    assert rating.solutions == "unique"
    assert rating.tier in {"medium", "hard"}
    assert rating.initial_open > puzzle.size**2 * 0.75
    # Counts alone do not determine the answer: the fleet really matters.
    plain = (
        text.split("Title:")[0]
        + (
            f"RowCounts:\n{' '.join(map(str, puzzle.row_counts))}\n"
            f"ColumnCounts:\n{' '.join(map(str, puzzle.column_counts))}\nGivens:\n"
        )
        + "\n".join(" ".join("." if v < 0 else str(v) for v in row) for row in puzzle.givens)
    )
    assert len(brute.solutions(plain)) == 2


@pytest.mark.parametrize(
    ("name", "grade"),
    [
        ("battleships_2_8x8_fleet.txt", "count"),
        ("battleships_3_8x8_fleet.txt", "subsumption"),
        ("battleships_5_8x8_fleet.txt", "chains"),
    ],
)
def test_clue_variety_examples_show_every_explained_symbol_without_lowering_difficulty(name, grade):
    from csp.puzzle_lab import rate
    from tests.examples import example

    text = example(name).read_text()
    puzzle = parse(text)
    tokens = [token for row in puzzle.segments for token in row]
    assert {"0", "1", "O", "M"} <= set(tokens)
    assert set(tokens) & {"N", "S", "E", "W"}
    assert sum(token != "." for token in tokens) < puzzle.size**2 / 4
    assert any(
        token == "0" and puzzle.row_counts[r] and puzzle.column_counts[c]
        for r, row in enumerate(puzzle.segments)
        for c, token in enumerate(row)
    ), "Include water that is not already implied by an empty row or column"
    rating = rate(text)
    assert rating.solutions == "unique"
    assert rating.tier in {"medium", "hard"}
    assert rating.grade == grade
    assert "what_if" not in rating.rule_firings


def test_fleet_mutation_preserves_the_rules_and_never_permutes_lines():
    import random

    from csp.puzzle_lab import _regenerate_count_grid

    changed = _regenerate_count_grid(FLEET, "battleships", {}, random.Random(5))
    assert changed is not None
    before, after = parse(FLEET), parse(changed)
    assert after.fleet == before.fleet
    assert after.row_counts == before.row_counts
    assert after.column_counts == before.column_counts


def test_legacy_partial_givens_count_only_known_occupied_cells():
    source = PUZZLE + "Givens:\n1 . . .\n. . . .\n. . . .\n. . . .\n"
    assert len(brute.solutions(source)) == 1
    with pytest.raises(ValueError, match="exceed a row"):
        parse(source.replace("4 3 2 1", "0 3 2 1"))
