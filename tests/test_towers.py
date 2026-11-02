import pytest

from csp.bruteforce import towers as brute
from csp.core import Solver
from csp.towers import compile_puzzle, parse, visible

# Every edge clue of the grid 4213 / 3421 / 2134 / 1342, which is then the only answer.
PUZZLE = """Family: towers
Size: 4
Top:
1 2 4 2
Bottom:
4 2 1 2
Left:
1 2 3 .
Right:
2 3 1 2
Givens:
. . . .
. . . .
. . . .
. . . 2
"""


def test_visible_counts_the_towers_that_are_not_hidden():
    assert visible([1, 2, 3, 4]) == 4
    assert visible([4, 3, 2, 1]) == 1
    assert visible([2, 1, 4, 3]) == 2
    assert visible([3, 1, 2, 4]) == 2


def test_each_stated_clue_is_one_relation_over_its_line_in_view_order():
    model, puzzle = compile_puzzle(PUZZLE)

    assert len(model.relations) == 15
    bottom = next(c for c in puzzle.lines if c.side == "Bottom")
    assert [cell[0] for cell in bottom.cells] == [3, 2, 1, 0]
    families = {item.family for item in model.constraints}
    assert families == {
        "each cell holds one height",
        "each height once per row",
        "each height once per column",
    }


def test_engine_and_brute_force_agree_on_a_unique_board():
    found = brute.solutions(PUZZLE, limit=3)
    model, _ = compile_puzzle(PUZZLE)
    result = Solver(model).solve()

    assert len(found) == 1
    assert result.solved
    assert result.assignment == found[0]
    assert found[0]["r1c1"] == 4 and found[0]["r4c4"] == 2


@pytest.mark.parametrize(
    "old, new",
    [
        ("Size: 4", "Size: 2"),
        ("Top:\n1 2 4 2", "Top:\n1 2 4 9"),
        ("Top:\n1 2 4 2", "Top:\n1 2 4"),
        ("Family: towers", "Family: mosaic"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_error(old, new):
    with pytest.raises(ValueError):
        parse(PUZZLE.replace(old, new))


def test_a_board_without_any_edge_clue_is_rejected():
    bare = "Family: towers\nSize: 4\nGivens:\n1 2 3 4\n. . . .\n. . . .\n. . . .\n"
    with pytest.raises(ValueError, match="edge clue"):
        parse(bare)
