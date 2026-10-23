import pytest

from csp import report, starbattle
from csp.bruteforce import starbattle as brute
from csp.core import Kind, Solver
from csp.starbattle import compile_puzzle, render
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
    assert "★" in render(puzzle, model, "Solved")


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
        ("starbattle_8x8", 2, 8, "cover2"),
        ("starbattle_10x10", 2, 10, "chains"),
        ("starbattle_12x12", 3, 12, "cover3"),
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
