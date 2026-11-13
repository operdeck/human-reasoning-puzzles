"""Pattern-first Sudoku explanations stay grounded in the replayed proof."""

import re

import pytest

from csp import bruteforce, cli, sudoku, sudoku_story
from csp.core import Solver
from csp.proof import Move, episodes, shortest
from csp.story import Wording
from tests.examples import example

pytestmark = pytest.mark.solutions


def _proof(name):
    text = example(name).read_text()
    model, puzzle = sudoku.compile_puzzle(text)
    moves = []

    def collect(rule, steps):
        if (move := Move.of(rule, steps)) is not None:
            moves.append(move)

    Solver(model.clone()).solve(on_step=collect)
    return text, model, puzzle, moves


def test_locked_candidates_and_singles_follow_a_sound_shortened_proof():
    text, model, _, moves = _proof("sudoku_17_9x9_pointing.txt")
    solved, groups = episodes(model, shortest(model, moves))
    (answer,) = bruteforce.solutions(text, "sudoku", limit=2)
    assert solved.solution() == answer
    for group in groups:
        for inference in (group.pattern, *group.consequences):
            for step in inference.steps:
                assert (answer[step.var] == step.value) == step.asserted

    narrative = sudoku_story.explain(text)
    assert narrative.complete
    assert "In column 4, every remaining place for 4 is in the box containing r7c4" in (
        narrative.markdown()
    )
    assert "cross 4 out from the other candidates" in narrative.markdown()
    placements = re.findall(r"place (\d+) in (r\d+c\d+)", narrative.markdown())
    assert placements and all(answer[cell] == int(digit) for digit, cell in placements)
    assert narrative.markdown().endswith("The remaining squares then follow by singles.")


def test_locked_candidate_works_from_box_to_column_and_column_to_box():
    text, model, puzzle, moves = _proof("sudoku_17_9x9_pointing.txt")
    _, groups = episodes(model, moves)
    narrator = sudoku_story._Narrator(puzzle, model, Wording.read(text))
    patterns = [
        narrator.pattern(group.pattern) for group in groups if group.pattern.rule == "subsumption"
    ]
    assert any(
        text is not None and "In the box containing r4c4" in text and "in column 6" in text
        for text in patterns
    )
    assert any(
        text is not None and "In column 4" in text and "in the box containing r7c4" in text
        for text in patterns
    )


@pytest.mark.parametrize(
    ("name", "pattern", "premise"),
    [
        ("sudoku_21_9x9_naked_pair.txt", "**Naked set.**", "r1c1 and r3c3 can only contain"),
        ("sudoku_19_9x9_hidden_pair.txt", "**Hidden set.**", "5 and 6 can only go in"),
        ("sudoku_22_9x9_xwing.txt", "**Line pattern.**", "row 4 and row 7"),
        ("sudoku_28_9x9_swordfish.txt", "**Line pattern.**", "column"),
    ],
)
def test_subset_and_line_patterns_name_their_evidence(name, pattern, premise):
    narrative = sudoku_story.explain(example(name).read_text())
    assert narrative.complete
    assert pattern in narrative.markdown()
    assert premise in narrative.markdown()


def test_dutch_explanations_use_localized_houses_and_coordinates():
    text = "Language: nl\nGivens:\n" + example("sudoku_17_9x9_pointing.txt").read_text()
    narrative = sudoku_story.explain(text)
    assert narrative.complete
    assert "**Enkele kandidaten.**" in narrative.markdown()
    assert "In kolom 4" in narrative.markdown()
    assert "het blok met r7k4" in narrative.markdown()
    assert "streep 4 weg" in narrative.markdown()


def test_unsupported_deductions_do_not_masquerade_as_a_complete_explanation(capsys):
    path = example("sudoku_33_9x9_chains.txt")
    narrative = sudoku_story.explain(path.read_text())
    assert not narrative.complete
    assert narrative.markdown().endswith(
        "**The next step needs a chain.** A pattern-first explanation is not available for "
        "that deduction yet; use --verbose for its detailed trace."
    )
    assert cli.main([str(path), "--explain"]) == 2
    assert "The next step needs a chain" in capsys.readouterr().out


def test_unsupported_deductions_are_localized():
    text = "Language: nl\nGivens:\n" + example("sudoku_33_9x9_chains.txt").read_text()
    narrative = sudoku_story.explain(text)
    assert not narrative.complete
    assert "De volgende stap gebruikt een keten" in narrative.markdown()
    assert "nog geen patroonverklaring" in narrative.markdown()


def test_stalled_and_already_completed_grids_are_reported_accurately():
    empty = "....\n....\n....\n....\n"
    filled = "1234\n3412\n2143\n4321\n"
    assert not sudoku_story.explain(empty).complete
    assert "do not finish this grid" in sudoku_story.explain(empty).markdown()
    assert sudoku_story.explain(filled).complete
    assert "givens already fill the grid" in sudoku_story.explain(filled).markdown()


def test_saved_solve_requires_both_start_and_history():
    text, model, _, _ = _proof("sudoku_17_9x9_pointing.txt")
    with pytest.raises(ValueError, match="supplied together"):
        sudoku_story.explain(text, start=model)
