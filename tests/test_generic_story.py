"""The generic narrator tells any family's solve from the model alone."""

from pathlib import Path

import pytest

from csp import cli, generic_story, puzzlefile
from csp.core import Solver
from csp.story import Wording
from tests.examples import example

EXAMPLES = sorted(
    path
    for path in Path(__file__).parent.parent.joinpath("examples").rglob("*.txt")
    if puzzlefile.detect(path.read_text()) != "murdoku"
)


def told(name: str) -> generic_story.Explanation:
    text = example(name).read_text()
    puzzle = cli.load(text, puzzlefile.detect(text))
    start = puzzle.model.clone()
    fired: list = []
    Solver(puzzle.model).solve(on_step=lambda rule, steps: fired.append((rule, steps)))
    return generic_story.explain(text, start, fired)


def test_compress_names_runs_along_the_shorter_direction():
    say, run = Wording("en"), "\u2013"
    tell = generic_story.compress
    assert tell(["r1c1", "r2c1", "r3c1", "r5c5"], say) == f"r1c1{run}r3c1 and r5c5"
    assert tell(["r1c1", "r1c2", "r1c3", "r2c2"], say) == f"r1c1{run}r1c3 and r2c2"
    assert tell(["r1c1", "r1c2", "r3c3"], say) == "r1c1, r1c2 and r3c3"
    assert tell(["Ada", "Ben", "Cal"], say) == "Ada, Ben and Cal"


def test_futoshiki_is_told_by_its_rules_chains_and_covers():
    story = told("futoshiki_3_5x5.txt")
    text = story.markdown()
    assert story.complete
    assert "*each number once per column*" in text
    assert "**Chain.** If r5c4 ≠ 4, then r2c4 = 4" in text
    assert "**Combined rules.**" in text
    assert "Stalled" not in text


def test_yes_no_cells_are_grouped_into_runs():
    text = told("pattern_4_10x10.txt").markdown()
    assert "**r2c1, r2c2 and r2c7 no** and **r2c4\u2013r2c6 and r2c8\u2013r2c10 yes**" in text


def test_a_what_if_names_the_rule_it_breaks():
    story = told("calcudoku_6_6x6.txt")
    assert story.complete
    assert (
        "**Suppose r2c2 = 6.** Then r4c3 = 2, r4c2 = 1, r5c2 = 2, r3c1 = 2 and 6 more steps "
        "would follow, but *9+ cage r1c5 r1c6 r2c6* fails; so r2c2 ≠ 6."
    ) in story.markdown()


def test_cli_falls_back_to_the_generic_story_for_sudoku(capsys):
    assert cli.main([str(example("sudoku_33_9x9_chains.txt")), "--explain"]) == 0
    assert "**Chain.** If r3c7 ≠ 8, then r1c9 = 8" in capsys.readouterr().out


@pytest.mark.solutions
@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_every_example_is_told_completely_with_unique_names(path):
    text = path.read_text()
    puzzle = cli.load(text, puzzlefile.detect(text))
    names = [c.name for c in puzzle.model.constraints] + [r.name for r in puzzle.model.relations]
    assert len(names) == len(set(names)), "proof replay looks constraints up by name"
    start = puzzle.model.clone()
    fired: list = []
    Solver(puzzle.model).solve(on_step=lambda rule, steps: fired.append((rule, steps)))
    story = generic_story.explain(text, start, fired)
    assert story.complete
