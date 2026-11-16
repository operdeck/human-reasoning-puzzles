import pytest

from csp.bruteforce.murdoku_expr import solutions
from csp.core import Solver
from csp.murdoku import Square
from csp.murdoku_expression_file import keyed_expression_clue_numbers, load_expression_board
from csp.murdoku_lang import Atom, Name
from csp.murdoku_lower import compile_statements
from csp.puzzlefile import load_board
from csp.story import (
    attribute_list,
    board_notes,
    clue_paragraphs,
    figure_clues,
    murdoku_key_items,
    murdoku_rules,
    object_list,
    role_list,
)

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
Rules:
  Ada in rows:1 | Ada stays in the first row.
Clues:
  Ben in columns:1 | Ben is in the first column.
"""


def test_expression_file_keeps_source_positions_and_separate_rules():
    board, rules, clues = load_expression_board(TEXT)
    assert not board.rules
    assert len(rules) == len(clues) == 1
    assert rules[0].wording == "Ada stays in the first row."
    assert clues[0].wording == "Ben is in the first column."
    assert isinstance(rules[0].formula, Atom)
    assert isinstance(rules[0].formula.subject, Name)
    assert (rules[0].formula.subject.token.line, rules[0].formula.subject.token.column) == (11, 3)
    assert isinstance(clues[0].formula, Atom)
    assert (clues[0].formula.operator.line, clues[0].formula.operator.column) == (13, 7)

    expected = [{"Ada": Square(0, 1), "Ben": Square(1, 0)}]
    assert solutions(board, clues, limit=3, rules=rules) == expected
    model = compile_statements(board, clues, rules=rules)
    sources = {source for step in model.log for source in step.sources}
    assert {"rule 1", "clue 1"} <= sources
    result = Solver(model).solve()
    assert result.contradiction is None
    assert result.solved
    assert model.solution() == expected[0]


def test_expression_file_reports_type_error_at_original_position():
    text = TEXT.replace("Ben in columns:1", "Ben in area:unknown")
    with pytest.raises(ValueError, match=r"line 13.*unknown"):
        load_expression_board(text)


@pytest.mark.parametrize(
    ("legacy", "replacement"),
    [
        ("people_on:bed", "(people on X)"),
        ("adjacent_to:hall", "((areas touches X) except X)"),
        ("people:any", "use people"),
    ],
)
def test_removed_legacy_namespaces_suggest_replacements(legacy, replacement):
    text = TEXT.replace("Ben in columns:1", f"Ben in {legacy}")
    with pytest.raises(ValueError) as error:
        load_expression_board(text)
    assert "line 13, column 10" in str(error.value)
    assert replacement in str(error.value)


@pytest.mark.parametrize("name", ["not", "of", "empty", "people", "roles"])
def test_expression_file_rejects_reserved_person_names_with_location(name):
    text = TEXT.replace("Ada\nBen\n", f"  {name}\nBen\n")
    with pytest.raises(ValueError, match=rf"line 8, column 3: person name '{name}' is reserved"):
        load_expression_board(text)


def test_expression_file_rejects_reserved_person_in_inline_header():
    text = "People: not\n" + TEXT.replace("People:\nAda\nBen\n", "")
    with pytest.raises(ValueError, match=r"line 1, column 9: person name 'not' is reserved"):
        load_expression_board(text)


@pytest.mark.parametrize("name", ["Not", "empty-handed", "People"])
def test_expression_file_allows_case_sensitive_non_keywords(name):
    text = TEXT.replace("Ada", name)
    board, _, _ = load_expression_board(text)
    assert name in board.people


def test_legacy_reader_still_interprets_legacy_rules_and_clues():
    text = TEXT.replace("Ada in rows:1", "in Ada rows:1").replace(
        "Ben in columns:1", "in Ben columns:1"
    )
    board, clues = load_board(text)
    assert len(board.rules) == len(clues) == 1
    assert board.rules[0] == ("in", ["Ada", "rows:1"])
    assert clues[0] == ("in", ["Ben", "columns:1"])


def test_layout_presentation_does_not_parse_expression_clues_as_legacy():
    text = (
        TEXT
        + "Objects:\nchair: standable r1c1\n"
        + "Roles:\nguard: 1\n"
        + "Attributes:\nstaff: Ada\n"
    )
    assert object_list(text) == [("chair", "Chair", True)]
    assert [name for name, _ in role_list(text)] == ["guard"]
    assert [name for name, _ in attribute_list(text)] == ["staff"]
    assert murdoku_key_items(text) == []


def test_expression_figure_clues_use_syntax_not_custom_wording_for_ownership():
    text = TEXT.replace(
        "  Ben in columns:1 | Ben is in the first column.",
        "  Ben in columns:1 | A custom sentence!\n"
        "  Ada in rows:1 and Ben in columns:1\n"
        "  not Ada in rows:2",
    )
    board, _, clues = load_expression_board(text)
    result = figure_clues(text, expressions=clues)
    assert [figure.person for figure in result.figures] == board.people
    ada, ben = result.figures
    assert [clue.sources for clue in ada.clues] == [(3,)]
    assert [(clue.text, clue.sources) for clue in ben.clues] == [("A custom sentence!", (1,))]
    assert [clue.sources for clue in result.other] == [(2,)]
    assert clue_paragraphs(text, {1: "A replacement"}, expressions=clues) == [
        "It is not true that (Ada is in rows 2).",
        "A replacement.",
        "(Ada is in rows 1) and (Ben is in columns 1).",
    ]


def test_expression_board_notes_include_generated_and_authored_rules():
    text = TEXT.replace(
        "  Ada in rows:1 | Ada stays in the first row.",
        "  Ada in rows:1 | Ada stays in the first row!\n  Ben in columns:1",
    )
    _, rules, _ = load_expression_board(text)
    assert board_notes(text, expression_rules=rules) == [
        "Ada stays in the first row!",
        "Ben is in columns 1.",
    ]


def test_expression_player_presentation_uses_dutch_wording():
    text = "Language: nl\n" + TEXT.replace(" | Ada stays in the first row.", "").replace(
        " | Ben is in the first column.", ""
    )
    _, rules, clues = load_expression_board(text)
    entries = figure_clues(text, expressions=clues)
    assert entries.figures[1].clues[0].text == "Ben is in kolommen 1."
    assert "Ada is in rijen 1." in murdoku_rules(
        text, expression_rules=rules, expression_clues=clues
    )


def test_expression_figure_name_override_preserves_person_identity():
    text = TEXT.replace(" | Ben is in the first column.", "") + "Words:\nBen: the detective\n"
    _, _, clues = load_expression_board(text)
    entries = figure_clues(text, expressions=clues)
    assert entries.figures[1].person == "Ben"
    assert entries.figures[1].name == "The detective"
    assert entries.figures[1].clues[0].text == "The detective is in columns 1."
    assert entries.figures[1].clues[0].id == "clue:1"


def test_expression_figure_clues_recognize_alone_and_only_on_idioms():
    text = TEXT.replace(
        "  Ben in columns:1 | Ben is in the first column.",
        "  count (people in area of Ada) = 1\n"
        "  (people on object:chair) = Ben\n"
        "  (people on object:chair) != Ada",
    )
    text += "Objects:\nchair: standable r1c1\n"
    _, _, clues = load_expression_board(text)
    entries = figure_clues(text, expressions=clues)
    assert [clue.sources for clue in entries.figures[0].clues] == [(1,)]
    assert [clue.sources for clue in entries.figures[1].clues] == [(2,)]
    assert [clue.sources for clue in entries.other] == [(3,)]


def test_expression_player_rules_use_ast_for_notes_and_deduplicate_intro():
    text = (
        "Intro: Ada stays in the first row.\n"
        + TEXT.replace(
            "  Ben in columns:1 | Ben is in the first column.",
            "  Ben beside object:chair\n  Ben dir:manhattan Ada >= 1",
        )
        + "Objects:\nchair: standable r1c1\n"
    )
    _, rules, clues = load_expression_board(text)
    output = murdoku_rules(text, expression_rules=rules, expression_clues=clues)
    assert output.count("Ada stays in the first row.") == 1
    assert any("Beside an object" in note for note in output)
    assert "Distance counts steps across sides, not diagonals." in output


def test_expression_player_rules_cover_mixed_feature_targets():
    text = TEXT.replace("a: hall\nGrid:\na a\na a", "a: hall\nb: yard\nGrid:\na b\na b").replace(
        "  Ben in columns:1 | Ben is in the first column.",
        "  Ben on edge_item:door,window\n"
        "  Ada on point_object:fountain\n"
        "  Ada touches mark:red\n"
        "  Ben dir:nearest:euclidean Ada",
    )
    text += (
        "EdgeItems:\ndoor: door r1c1 r1c2\nwindow: window r2c1\n"
        "PointObjects:\nfountain: r1.5c1.5\n"
        "Marks:\nred: r2c2\n"
    )
    _, rules, clues = load_expression_board(text)
    output = murdoku_rules(text, expression_rules=rules, expression_clues=clues)
    assert any("On a door" in note for note in output)
    assert any("On a window" in note for note in output)
    assert any("On a point object" in note for note in output)
    assert any("touches a marked square" in note for note in output)
    assert any("straight line" in note for note in output)


def test_expression_keys_match_ast_after_reordering_or_rewording():
    extra = "  Ada in rows:1 | Another wording.\n"
    text = TEXT.replace("  Ben in columns:1", extra + "  Ben in columns:1")
    text += "Key:\nclue: Ben   in columns:1\nrule: Ada in rows:1\n"
    assert keyed_expression_clue_numbers(text) == {2}
    load_expression_board(text)
    reordered = text.replace(extra + "  Ben", "  Ben").replace(
        "  Ben in columns:1 | Ben is in the first column.\n",
        "  Ben in columns:1 | Changed wording.\n" + extra,
    )
    assert keyed_expression_clue_numbers(reordered) == {1}
    load_expression_board(reordered)


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("clue: Ada in columns:1", "unresolved Key clue"),
        ("clue: Ben in columns:1\nclue: Ben   in columns:1", "duplicate Key entry"),
        ("clue: Ben in columns:1 | text", "bad Key entry"),
    ],
)
def test_expression_keys_reject_invalid_references(key, message):
    with pytest.raises(ValueError, match=message):
        load_expression_board(TEXT + "Key:\n" + key + "\n")


def test_expression_key_requires_a_unique_ast_match():
    text = TEXT.replace(
        "  Ben in columns:1 | Ben is in the first column.",
        "  Ben in columns:1 | First wording.\n  Ben in columns:1 | Second wording.",
    )
    with pytest.raises(ValueError, match="unresolved Key clue"):
        load_expression_board(text + "Key:\nclue: Ben in columns:1\n")


def test_expression_key_normalizes_whitespace_inside_quantifier():
    text = TEXT.replace("Ben in columns:1", "at   least 1 ?p in people: ?p in columns:1")
    text += "Key:\nclue: at least 1 ?p in people: ?p in columns:1\n"
    assert keyed_expression_clue_numbers(text) == {1}
    load_expression_board(text)
