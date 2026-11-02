import random

import pytest

from csp import fresh
from csp.bruteforce import sudoku as brute
from csp.core import Solver
from csp.sudoku import Rule, compile_puzzle, parse

VARIANTS = ["killer", "arrow", "evenodd", "sandwich", "skyscrapersudoku"]


def test_parity_allows_only_digits_of_its_kind():
    odd, even = Rule("parity", ((0, 0),), 1, 4), Rule("parity", ((0, 0),), 0, 4)

    assert [odd.holds(d) for d in (1, 2, 3, 4)] == [True, False, True, False]
    assert [even.holds(d) for d in (1, 2, 3, 4)] == [False, True, False, True]


def test_an_arrow_bulb_is_the_sum_of_its_arrow_and_partial_answers_are_pruned():
    arrow = Rule("arrow", ((0, 0), (0, 1), (1, 1)), 0, 9)

    assert arrow.holds(5, 2, 3) and not arrow.holds(5, 2, 2)
    assert arrow.feasible([4, 3, 0])  # the last cell can be 1
    assert not arrow.feasible([4, 4, 0])  # no room left for it
    assert arrow.feasible([0, 4, 0])


def test_a_killer_cage_needs_different_digits_and_its_sum():
    cage = Rule("killer", ((0, 0), (0, 1), (1, 0)), 7, 9)

    assert cage.holds(1, 2, 4) and not cage.holds(1, 3, 3) and not cage.holds(2, 2, 3)
    assert not cage.feasible([6, 0, 0])  # 6 and two more cells is at least 8
    assert cage.feasible([1, 0, 0])


def test_sandwich_adds_the_digits_between_the_one_and_the_top_digit():
    line = Rule("sandwich", ((0, 0), (0, 1), (0, 2), (0, 3)), 5, 4)

    assert line.holds(4, 2, 3, 1)  # 2 + 3 between the 4 and the 1
    assert line.holds(4, 3, 2, 1)  # the same two digits in the other order
    assert not line.holds(4, 2, 2, 1)
    assert line.feasible([4, 0, 0, 1])  # undecided until the middle is filled


def test_skyscraper_counts_the_towers_seen_from_the_clue_side():
    line = Rule("skyscraper", ((0, 0), (0, 1), (0, 2), (0, 3)), 2, 4)

    assert line.holds(2, 1, 4, 3) and not line.holds(1, 2, 3, 4)


def _fresh(family: str, size: int = 4) -> str:
    for seed in range(60):
        text = fresh.fresh(family, size, random.Random(seed), 0.5)
        if text is not None and Solver(compile_puzzle(text)[0]).solve().solved:
            return text
    pytest.fail(f"no unique, engine-solved fresh {family} Sudoku in 60 seeds")


@pytest.mark.parametrize("family", VARIANTS)
def test_fresh_variant_boards_are_unique_and_the_engine_agrees(family):
    text = _fresh(family)
    found = brute.solutions(text, limit=2)
    result = Solver(compile_puzzle(text)[0]).solve()

    assert len(found) == 1
    assert result.solved and result.assignment == found[0]
    puzzle = parse(text)
    assert puzzle.rules, "the variant's rules were parsed"
    # Every rule holds in the answer, read back from the file with the shared definition.
    assert all(
        rule.holds(*(found[0][f"r{r + 1}c{c + 1}"] for r, c in rule.cells)) for rule in puzzle.rules
    )


@pytest.mark.parametrize(
    "family, bad",
    [
        ("killer", "Killer:\nx: r1c1 r1c2\n"),
        ("killer", "Killer:\n3: r1c1\n"),
        ("arrow", "Arrows:\nr1c1 r4c4 r2c2\n"),
        ("evenodd", "Parity:\nx x x x\n"),
        ("sandwich", "SandwichRows:\n1 2\n"),
        ("skyscrapersudoku", "SkyscraperTop:\n9 9 9 9 9\n"),
    ],
)
def test_malformed_variant_sections_are_rejected(family, bad):
    # A later section of the same name replaces the earlier one, so appending is enough.
    with pytest.raises(ValueError):
        parse(_fresh(family) + bad)
