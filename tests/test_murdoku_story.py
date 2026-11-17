import re

import pytest

from csp import cli, generic_story, murdoku_story, story
from csp.bruteforce import solutions
from csp.core import Kind, Model, Solver
from csp.proof import Move, replay
from tests.examples import example

TEXT = """\
Size: 2
Regions:
a: hall
Grid:
a a
a a
People:
Ada
Ben
Roles:
guard: 1
Rules:
Ada in rows:1 | Ada stays in the first row.
Clues:
Ben in columns:1 | Ben is in the first column.
some role:guard in rows:1 | The guard is in the first row.
"""


@pytest.mark.parametrize(
    ("language", "positive", "negative", "label", "cardinality"),
    [
        (
            "en",
            "Ada has the guard role",
            "Ben does not have the guard role",
            "clue 2",
            "allowed number",
        ),
        (
            "nl",
            "Ada heeft de rol guard",
            "Ben heeft de rol guard niet",
            "aanwijzing 2",
            "toegestane aantal",
        ),
    ],
)
def test_expressions_explain_clue_wording_and_roles_even_after_all_people_are_placed(
    language, positive, negative, label, cardinality
):
    text = f"Language: {language}\n" + TEXT
    result = murdoku_story.explain(text)
    assert result.complete
    words = result.markdown()
    assert positive in words and negative in words
    assert words.count(f"**{positive}**") == 1
    assert words.count(f"**{negative}**") == 1
    assert any(
        cardinality in paragraph and negative in paragraph for paragraph in result.paragraphs
    )
    assert "Ada stays in the first row" in words
    assert "The guard is in the first row" in words
    assert label in words
    assert "__" not in words
    assert "binding" not in words
    assert "intermediate" not in words
    assert "role state" not in words
    assert story.explain(text) == words
    assert label not in murdoku_story.explain(text, numbered=False).markdown()


def test_proof_settles_hidden_singletons_after_visible_solution():
    model = Model()
    person = model.literal("Ada", "hall")
    model.constrain("Ada", Kind.EXACTLY_ONE, [person], defines="Ada")
    guard, not_guard = (model.literal("guard", value) for value in (True, False))
    model.constrain(
        "guard state", Kind.EXACTLY_ONE, [guard, not_guard], defines="guard", hidden=True
    )
    model.constrain("the guard", Kind.EXACTLY_ONE, [guard])
    result = replay(model, [])
    assert result.solution() == {"Ada": "hall"}
    assert result.chosen("guard") is True


def test_thinning_preserves_required_role_deductions_not_just_visible_placements():
    model = Model()
    person = model.literal("Ada", "hall")
    model.constrain("Ada", Kind.EXACTLY_ONE, [person], defines="Ada")
    guard, not_guard = (model.literal("guard", value) for value in (True, False))
    model.constrain(
        "guard state", Kind.EXACTLY_ONE, [guard, not_guard], defines="guard", hidden=True
    )
    model.relate("the guard is Ada", ["guard"], lambda guard: guard)
    moves = []

    def collect(rule, steps):
        if move := Move.of(rule, steps):
            moves.append(move)

    Solver(model.clone()).solve(on_step=collect)
    assert replay(model, generic_story.thin(model, moves)).chosen("guard") is None
    kept = generic_story.thin(model, moves, required_values={"guard": True})
    assert replay(model, kept).chosen("guard") is True


@pytest.mark.parametrize(
    "name",
    [
        "murdoku_3_house.txt",
        "murdoku_composition.txt",
        "halloween-museum-1.txt",
        "samen-onderweg.txt",
    ],
)
def test_expression_narration_names_every_placement_against_independent_solution(name):
    text = example(name).read_text()
    result = murdoku_story.explain(text)
    assert result.complete
    words = result.markdown()
    found = {
        person: (int(row) - 1, int(col) - 1)
        for person, row, col in re.findall(r"\*\*(\w+) (?:on|op) r(\d+)[ck](\d+)\*\*", words)
    }
    (answer,) = solutions(text, "murdoku", limit=2)
    expected = {
        person: (square.row, square.col)
        for person, square in answer.items()
        if not isinstance(square, bool)
    }
    assert found == expected
    assert "__" not in words
    assert "binding" not in words
    assert "body" not in words
    assert "intermediate" not in words


def test_expression_story_routes_cli_booklet_and_public_facade_through_the_same_words(
    tmp_path, capsys
):
    path = tmp_path / "puzzle.txt"
    path.write_text(TEXT)
    assert cli.main([str(path), "--explain"]) == 0
    assert story.explain(TEXT) in capsys.readouterr().out
    assert story.figure_clues(TEXT) == story.figure_clues(
        TEXT, expressions=cli.load_expression_board(TEXT)[2]
    )


def test_role_separation_sources_keep_the_puzzles_thematic_wording():
    words = murdoku_story.explain(example("menu-murdoku-1.txt").read_text()).markdown()
    assert "er staat nooit meer dan één zetmeel op dezelfde dag" in words
    assert "in different regions" not in words
