import random

import pytest

from csp import fresh
from csp.bruteforce import undead as brute
from csp.core import Solver
from csp.undead import compile_puzzle, parse, seen

pytestmark = pytest.mark.solutions

# A mirror turns a line of sight: "/" sends one entering downwards to the left.
MIRRORED = """Family: undead
Grid:
. / .
. . \\
. . .
Counts:
2 3 2
Top:
1 . .
"""


def _fresh_board(size: int = 4) -> str:
    for seed in range(100):
        text = fresh.fresh("undead", size, random.Random(seed), 0.4)
        if text is not None:
            return text
    pytest.fail("no unique fresh Undead in 100 seeds")


def test_visibility_rule():
    assert [seen("Z", False), seen("Z", True)] == [True, True]
    assert [seen("V", False), seen("V", True)] == [True, False]
    assert [seen("G", False), seen("G", True)] == [False, True]


def test_sight_lines_bend_at_mirrors_and_keep_track_of_the_bend():
    puzzle = parse(MIRRORED)

    # Down column 2 hits "/" at r1c2 and turns left: r1c1 is the only cell after it.
    assert puzzle.trace("Top", 1) == (((0, 0), True),)
    # Along row 2 from the right: r2c3 is a mirror "\\", so the line turns up column 3.
    assert puzzle.trace("Right", 1) == (((0, 2), True),)
    # Straight lines are not reflected.
    assert puzzle.trace("Left", 2) == (((2, 0), False), ((2, 1), False), ((2, 2), False))


def test_the_model_has_a_relation_per_sight_and_a_count_per_monster():
    model, puzzle = compile_puzzle(MIRRORED)

    assert len(model.relations) == len(puzzle.sights) == 1
    totals = [item for item in model.constraints if item.family == "monster totals"]
    assert len(totals) == 3


def test_the_engine_and_the_brute_force_agree_on_a_unique_board():
    text = _fresh_board(4)
    found = brute.solutions(text, limit=2)
    result = Solver(compile_puzzle(text)[0]).solve()

    assert len(found) == 1
    assert result.solved and result.assignment == found[0]


def test_a_solution_matches_every_border_clue_traced_independently():
    text = _fresh_board(5)
    (solution,) = brute.solutions(text)
    puzzle = parse(text)
    grid = puzzle.grid
    rows, cols = puzzle.rows, puzzle.cols
    starts = {
        "Top": lambda i: (0, i, 1, 0),
        "Bottom": lambda i: (rows - 1, i, -1, 0),
        "Left": lambda i: (i, 0, 0, 1),
        "Right": lambda i: (i, cols - 1, 0, -1),
    }
    for side, values in puzzle.clues.items():
        for i, count in enumerate(values):
            if count < 0:
                continue
            r, c, dr, dc = starts[side](i)
            bent, tally = False, 0
            while 0 <= r < rows and 0 <= c < cols:
                if grid[r][c] == "/":
                    dr, dc, bent = -dc, -dr, True
                elif grid[r][c] == "\\":
                    dr, dc, bent = dc, dr, True
                else:
                    monster = solution[f"r{r + 1}c{c + 1}"]
                    tally += (
                        monster == "Z" or (monster == "V" and not bent) or (monster == "G" and bent)
                    )
                r, c = r + dr, c + dc
            assert tally == count


@pytest.mark.parametrize(
    "old, new",
    [
        ("Family: undead", "Family: mosaic"),
        ("Counts:\n2 3 2", "Counts:\n2 3"),
        ("Counts:\n2 3 2", "Counts:\n1 1 1"),
        ("Top:\n1 . .", "Top:\n1 ."),
        (". / .", ". x ."),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(old, new):
    with pytest.raises(ValueError):
        parse(MIRRORED.replace(old, new))
