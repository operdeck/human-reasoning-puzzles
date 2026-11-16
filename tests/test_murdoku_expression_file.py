import pytest

from csp.bruteforce.murdoku_expr import solutions
from csp.core import Solver
from csp.murdoku import Square
from csp.murdoku_expression_file import keyed_expression_clue_numbers, load_expression_board
from csp.murdoku_lang import Atom, Name
from csp.murdoku_lower import compile_statements
from csp.puzzlefile import load_board

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
