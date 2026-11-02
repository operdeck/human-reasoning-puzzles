import pytest

from csp import report, starbattle
from csp.bruteforce import starbattle as brute
from csp.core import Kind, Solver
from csp.starbattle import compile_puzzle, render
from csp.story import family_rules
from tests.examples import example

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


def test_one_star_starbattle_uses_exactly_one_and_no_touch_constraints():
    model, puzzle = compile_puzzle(PUZZLE)

    counts = [item for item in model.constraints if item.family.startswith("one queen per")]
    assert len(counts) == 12
    assert all(item.kind is Kind.EXACTLY_ONE for item in counts)
    assert not any(item.kind is Kind.COUNT for item in model.constraints)
    assert sum(item.family == "queens do not touch" for item in model.constraints) == 9
    assert not model.relations
    assert puzzle.name == "Queens"
    assert family_rules(PUZZLE, "starbattle") == [
        "Place one queen in every row, column and region; queens may not touch, "
        "not even diagonally."
    ]


def test_starbattle_backtracker_and_engine_agree():
    (solution,) = brute.solutions(PUZZLE)
    model, puzzle = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert result.solved
    assert result.assignment == solution
    assert "♛" in render(puzzle, model, "Solved")


def test_one_star_is_presented_as_queens_without_changing_the_solver_rules():
    text = (example("queens_1_4x4.txt")).read_text()
    puzzle = starbattle.parse(text)

    assert puzzle.name == "Queens"
    assert puzzle.icon == "queen"


def test_one_star_empty_given_excludes_the_cell_from_its_region():
    text = PUZZLE + "Givens:\n. ? ? ?\n? ? ? ?\n? ? ? ?\n? ? ? ?\n"
    model, puzzle = compile_puzzle(text)
    region = puzzle.areas.cells[0][0]

    assert model.is_false(model.literal(region, (0, 0)))


def _grid(stars, rows, names="abcde"):
    size = len(rows)
    regions = "\n".join(f"{name}: zone_{name}" for name in names[:size])
    body = "\n".join(rows)
    return f"Family: starbattle\nSize: {size}\nStars: {stars}\nRegions:\n{regions}\nGrid:\n{body}\n"


def test_regions_may_differ_in_size_but_must_be_connected_and_hold_the_stars():
    uneven = _grid(1, ["a b b", "b b c", "b c c"], "abc")
    puzzle = starbattle.parse(uneven)
    assert sorted(len(cells) for cells in puzzle.areas.cells_by_region.values()) == [1, 3, 5]

    with pytest.raises(ValueError, match="connected"):
        starbattle.parse(_grid(1, ["a b a", "b b c", "c c c"], "abc"))
    with pytest.raises(ValueError, match="at least 2 cells"):
        starbattle.parse(_grid(2, ["a b b", "b b c", "b c c"], "abc"))


@pytest.mark.parametrize(
    "name, stars, size, grade",
    [
        ("starbattle_2_8x8", 2, 8, "cover2"),
        ("starbattle_4_10x10", 2, 10, "chains"),
        ("starbattle_3_12x12", 3, 12, "cover3"),
    ],
)
def test_irregular_multi_star_examples_are_unique_and_graded(name, stars, size, grade):
    text = (example(f"{name}.txt")).read_text()
    puzzle = starbattle.parse(text)
    sizes = [len(cells) for cells in puzzle.areas.cells_by_region.values()]

    assert (puzzle.stars, puzzle.size) == (stars, size)
    assert len(set(sizes)) > 1  # irregular regions, not N cells each
    assert len(brute.solutions(text)) == 1
    model, _ = compile_puzzle(text)
    fired: list[str] = []
    result = Solver(model).solve(on_step=lambda rule, steps, log=fired: log.append(rule))
    assert result.solved
    assert report.grade(fired) == grade


@pytest.mark.parametrize(
    "name,grade",
    [
        ("queens_1_4x4", "single"),
        ("queens_2_5x5", "single"),
        ("queens_3_7x7", "subsumption"),
        ("queens_4_8x8", "subsumption"),
        ("queens_5_9x9", "cover2"),
        ("queens_6_4x4", "chains"),
    ],
)
def test_one_star_queens_gallery_stays_unique_and_keeps_its_grade(name, grade):
    text = example(f"{name}.txt").read_text()
    puzzle = starbattle.parse(text)
    assert (puzzle.stars, puzzle.icon) == (1, "queen")
    assert len(brute.solutions(text)) == 1
    model, _ = compile_puzzle(text)
    fired: list[str] = []
    assert Solver(model).solve(on_step=lambda rule, steps: fired.append(rule)).solved
    assert report.grade(fired) == grade
