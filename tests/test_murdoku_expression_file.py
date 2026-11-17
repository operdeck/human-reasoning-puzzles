import json
from dataclasses import fields, is_dataclass
from typing import get_args

import pytest

from csp import cli, clue_search
from csp.bruteforce.murdoku_expr import accepts, sample, solutions
from csp.core import Solver
from csp.murdoku import Square
from csp.murdoku_expression_file import keyed_expression_clue_numbers, load_expression_board
from csp.murdoku_lang import Atom, Formula, Measure, Name, Number, Operand, format_statement, holds
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


def test_expression_authoring_outcome_thinning_and_key_protection():
    text = TEXT.replace(
        "  Ben in columns:1 | Ben is in the first column.",
        "  Ben in columns:1 | Ben is in the first column.\n  Ben in rows:2",
    )
    text += "Key:\nclue: Ben in columns:1\n"
    result = clue_search.outcome(text, expressions=True)
    assert result.good
    kept = clue_search.thin(text, expressions=True)
    assert kept == ["Ben in columns:1 | Ben is in the first column."]
    report = clue_search.removal_report(text, expressions=True)
    assert report[0][2] == result
    assert report[1][2].good


def test_expression_placement_acceptance_checks_rules_roles_and_board_constraints():
    text = TEXT.replace(
        "  Ada in rows:1 | Ada stays in the first row.",
        "  Ada in rows:1 | Ada stays in the first row.\n  Ada is role:guard",
    )
    text += "Roles:\nguard: 1\n"
    board, rules, clues = load_expression_board(text)
    accepted = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    assert accepts(board, clues, accepted, rules=rules)
    assert not accepts(board, clues, {"Ada": Square(0, 0), "Ben": Square(1, 1)}, rules=rules)
    assert not accepts(board, clues, {"Ada": Square(0, 0), "Ben": Square(0, 1)}, rules=rules)
    with pytest.raises(ValueError, match="every person"):
        accepts(board, clues, {"Ada": Square(0, 1)}, rules=rules)


def test_expression_placement_acceptance_matches_search_for_optional_roles():
    text = TEXT.replace(
        "  Ada in rows:1 | Ada stays in the first row.",
        "  Ada is role:guard",
    )
    text += "Roles:\nguard: any\n"
    board, rules, clues = load_expression_board(text)
    found = solutions(board, clues, limit=100, rules=rules)
    placements = (
        {"Ada": Square(0, 0), "Ben": Square(1, 1)},
        {"Ada": Square(0, 1), "Ben": Square(1, 0)},
        {"Ada": Square(1, 0), "Ben": Square(0, 1)},
        {"Ada": Square(1, 1), "Ben": Square(0, 0)},
    )
    for placed in placements:
        assert accepts(board, clues, placed, rules=rules) == any(
            all(result[person] == square for person, square in placed.items()) for result in found
        )


def test_expression_sampling_spreads_valid_solutions_and_preserves_role_assignments():
    text = TEXT.replace(
        "  Ada in rows:1 | Ada stays in the first row.",
        "  Ada is role:guard",
    )
    text += "Roles:\nguard: any\n"
    board, rules, clues = load_expression_board(text)
    found = sample(board, clues, 8, rules=rules)
    assert len(found) == 4
    assert len({tuple(sorted(result.items())) for result in found}) == len(found)
    assert {result["Ada"] for result in found} == {Square(0, 1), Square(1, 1)}
    all_solutions = solutions(board, clues, 100, rules=rules)
    assert all(result in all_solutions for result in found)
    with pytest.raises(ValueError, match="positive"):
        sample(board, clues, 0, rules=rules)


def test_expression_mentions_use_ast_instead_of_wording_or_token_positions():
    clues = [
        "Ada in rows:1 | Ben is mentioned in the wording only.",
        "not (Ada dir:left Ben) and some ?p in people: ?p is role:guard",
    ]
    assert clue_search._mentions(["Ada", "Ben"], clues, expressions=True) == {"Ada": 2, "Ben": 1}
    assert clue_search._unnamed(["Ada", "Ben"], clues[:1], (), expressions=True) == ["Ben"]


def test_expression_authoring_cli_thin(tmp_path, capsys):
    text = TEXT.replace(
        "  Ben in columns:1 | Ben is in the first column.",
        "  Ben in columns:1 | Ben is in the first column.\n  Ben in rows:2",
    )
    text += "Key:\nclue: Ben in columns:1\n"
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(text)
    assert clue_search.main(["thin", str(puzzle), "--expressions"]) == 0
    result = capsys.readouterr().out
    assert "dropped 2: Ben in rows:2" in result
    assert "result: unique, grade single" in result
    assert "Ben in columns:1 | Ben is in the first column." in result
    assert clue_search.main(["report", str(puzzle), "--expressions"]) == 0
    assert "required by Key; current puzzle: unique" in capsys.readouterr().out


def test_cli_expression_model_preview_groups_source_statements(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    assert cli.main([str(puzzle), "--expressions", "--show-model"]) == 0
    result = capsys.readouterr().out
    assert "rule 1: Ada in rows:1" in result
    assert "clue 1: Ben in columns:1" in result
    assert "constraints" in result and "relations" in result


def test_cli_expression_model_preview_rejects_unimplemented_operations(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    with pytest.raises(SystemExit) as error:
        cli.main([str(puzzle), "--expressions", "--nosolution"])
    assert error.value.code == 2
    assert "--expressions currently supports only" in capsys.readouterr().err


def test_cli_expression_svg_writes_puzzle_and_solution(tmp_path):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    assert cli.main([str(puzzle), "--expressions", "--svg"]) == 0
    assert (tmp_path / "puzzle.svg").read_text().startswith("<svg")
    assert (tmp_path / "puzzle-solution.svg").exists()


def test_cli_expression_explain_uses_the_generic_story(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    assert cli.main([str(puzzle), "--expressions", "--explain"]) == 0
    assert "Ben = r2c1" in capsys.readouterr().out


def test_cli_expression_normal_solve_and_stalled_board(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    assert cli.main([str(puzzle), "--expressions"]) == 0
    result = capsys.readouterr().out
    assert "Start" in result and "Solved" in result
    assert "deductions logged" in result
    puzzle.write_text(clue_search.with_clues(TEXT, []))
    assert cli.main([str(puzzle), "--expressions"]) == 1
    assert "As far as the rules go" in capsys.readouterr().out


def test_cli_expression_grade_and_brute_force(tmp_path, capsys, monkeypatch):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    assert cli.main([str(puzzle), "--expressions", "--grade"]) == 0
    assert capsys.readouterr().out.strip() == "single"

    def unsupported(*args, **kwargs):
        raise AssertionError("independent search must not invoke expression lowering")

    monkeypatch.setattr(cli, "compile_statements_with_origins", unsupported)
    assert cli.main([str(puzzle), "--expressions", "--brute-force"]) == 0
    assert "brute force: unique solution" in capsys.readouterr().out
    puzzle.write_text(clue_search.with_clues(TEXT, []))
    assert cli.main([str(puzzle), "--expressions", "--brute-force"]) == 1
    assert "more than one solution" in capsys.readouterr().out


def test_cli_expression_lint_reports_role_warnings_without_legacy_parsing(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    text = TEXT.replace(
        "  Ben in columns:1 | Ben is in the first column.",
        "  not Ben dir:areas role:guard = 0",
    )
    puzzle.write_text(text + "Roles:\nguard: any\nchef: any\n")
    assert cli.main([str(puzzle), "--expressions", "--lint"]) == 0
    result = capsys.readouterr().out
    assert "Ben may still be role:guard" in result
    assert "role chef is declared but unused" in result
    assert "role guard is declared but unused" not in result


def test_cli_expression_lint_rejects_impossible_relations_and_bad_wording(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT.replace("Ben in columns:1", "Ben beside Ada"))
    assert cli.main([str(puzzle), "--expressions", "--lint"]) == 1
    assert "people cannot beside each other" in capsys.readouterr().out
    puzzle.write_text(TEXT + "Words:\nrel.besid: next to\n")
    assert cli.main([str(puzzle), "--expressions", "--lint"]) == 1
    assert "rel.besid" in capsys.readouterr().err


def test_cli_expression_verbose_names_source_statements(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    assert cli.main([str(puzzle), "--expressions", "--verbose"]) == 0
    assert "single" in capsys.readouterr().out


def test_cli_expression_require_forward(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    assert cli.main([str(puzzle), "--expressions", "--require-forward"]) == 0
    assert "require-forward: solved without what_if" in capsys.readouterr().out
    puzzle.write_text(clue_search.with_clues(TEXT, []))
    assert cli.main([str(puzzle), "--expressions", "--require-forward"]) == 1
    assert "does not solve using forward rules" in capsys.readouterr().err


def test_expression_authoring_cli_rejects_unimplemented_commands(tmp_path, capsys):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    with pytest.raises(SystemExit) as error:
        clue_search.main(["ease", str(puzzle), "--expressions"])
    assert error.value.code == 2
    assert "--expressions is supported only by report, thin and suggest" in capsys.readouterr().err


def test_expression_suggest_closes_puzzle_and_cli_uses_expression_syntax(tmp_path, capsys):
    text = clue_search.with_clues(TEXT, [])
    placement = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    added = clue_search.suggest(text, placement, kinds=["line"], expressions=True)
    board, rules, clues = load_expression_board(clue_search.with_clues(text, added))
    assert solutions(board, clues, 2, rules=rules) == [placement]
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(text)
    assert (
        clue_search.main(
            [
                "suggest",
                str(puzzle),
                "--expressions",
                "--kinds",
                "line",
                "--solution",
                "Ada=r1c2 Ben=r2c1",
            ]
        )
        == 0
    )
    assert "unique with" in capsys.readouterr().out


def test_expression_suggest_preserves_keyed_needed_clue_and_coverage():
    text = TEXT.replace("  Ada in rows:1 | Ada stays in the first row.\n", "")
    text += "Key:\nclue: Ben in columns:1\n"
    placement = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    added = clue_search.suggest(
        text, placement, kinds=["line"], needs=[1], cover=True, expressions=True
    )
    final = clue_search.with_clues(text, [*clue_search.clue_lines(text), *added])
    board, rules, clues = load_expression_board(final)
    assert solutions(board, clues, 2, rules=rules) == [placement]
    assert not clue_search._unnamed(
        board.people, clue_search.clue_lines(final), (), expressions=True
    )
    board, rules, clues = load_expression_board(
        clue_search.with_clues(text, added), validate_keys=False
    )
    assert len(solutions(board, clues, 2, rules=rules)) == 2


def test_expression_suggest_preserves_needed_mark_effect():
    text = """Size: 3
Regions:
a: alcove
b: hall
Grid:
a b b
b a b
b b b
People:
Ada
Ben
Cal
Marks:
quiet: r1c1 ; alone
Clues:
count (people on mark:quiet) = 1
Ada in rows:1
"""
    placement = clue_search.parse_solution("Ada=r1c1 Ben=r2c3 Cal=r3c2")
    added = clue_search.suggest(
        text, placement, kinds=["line"], needs_marks=["quiet"], sample=100, expressions=True
    )
    final = clue_search.with_clues(text, [*clue_search.clue_lines(text), *added])
    board, rules, clues = load_expression_board(final)
    assert len(solutions(board, clues, 2, rules=rules)) == 1
    board, rules, clues = load_expression_board(clue_search.without_mark_condition(final, "quiet"))
    assert len(solutions(board, clues, 2, rules=rules)) == 2


def test_mark_ablation_reads_layout_without_parsing_clues():
    text = TEXT + "Marks:\nred: r1c1 ; alone\n"
    without = clue_search.without_mark_condition(text, "red")
    board, rules, clues = load_expression_board(without)
    assert len(rules) == len(clues) == 1
    assert board.marks[0].occupant_condition is None


def test_expression_candidate_templates_use_reference_semantics_and_exclusions():
    text = TEXT + "Objects:\nchair: standable r1c2\nstatue: blocking r2c2\n"
    board, _, _ = load_expression_board(text)
    placement = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    candidates = clue_search.expression_candidate_clues(
        board,
        placement,
        kinds=["in", "on", "beside", "not beside", "line"],
        exclude=iter(["Ben"]),
        exclude_targets=["statue"],
    )
    rendered = [format_statement(clue) for clue in candidates]
    assert "Ada on object:chair" in rendered
    assert "Ada in rows:1" in rendered
    assert all("Ben" not in clue and "statue" not in clue for clue in rendered)
    assert all(holds(clue, board, placement, {}) for clue in candidates)


def test_expression_direction_candidates_use_expression_syntax():
    board, _, _ = load_expression_board(TEXT)
    placement = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    candidates = clue_search.expression_candidate_clues(board, placement, kinds=["dir"])
    rendered = [format_statement(clue) for clue in candidates]
    assert "Ada dir:up Ben" in rendered
    assert "Ben dir:down Ada" in rendered
    assert all(holds(clue, board, placement, {}) for clue in candidates)


def test_expression_suggestion_construct_inventory_tracks_public_ast():
    types = {
        *get_args(Operand.__value__),
        *get_args(Number.__value__),
        *get_args(Formula.__value__),
        Measure,
    }
    offered = clue_search.EXPRESSION_SUGGESTED_NODES
    excluded = clue_search.EXPRESSION_EXCLUDED_NODES
    assert not offered & excluded.keys()
    assert offered | excluded.keys() == {node.__name__ for node in types}
    assert all(excluded.values())

    def node_names(value):
        if isinstance(value, tuple):
            return set().union(*(node_names(item) for item in value))
        if is_dataclass(value):
            return {type(value).__name__} | set().union(
                *(node_names(getattr(value, item.name)) for item in fields(value))
            )
        return set()

    board, _, _ = load_expression_board(TEXT)
    placement = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    candidates = clue_search.expression_candidate_clues(board, placement, kinds=["line", "dir"])
    emitted = set().union(*(node_names(clue.formula) for clue in candidates))
    assert offered <= emitted


def test_cli_expression_export_writes_a_playable_bundle(tmp_path):
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    out = tmp_path / "web"
    assert cli.main([str(puzzle), "--expressions", "--export", str(out)]) == 0
    bundle = json.loads((out / "puzzle.json").read_text())
    assert bundle["playable"] and bundle["solution"]["r2c1"] == "Ben"
    assert bundle["clueEntries"] and all(e["sources"] for e in bundle["clueEntries"])


def test_cli_expression_docx_has_puzzle_and_solution_pages(tmp_path):
    docx = pytest.importorskip("docx")
    puzzle = tmp_path / "puzzle.txt"
    puzzle.write_text(TEXT)
    out = tmp_path / "booklet.docx"
    assert cli.main([str(puzzle), "--expressions", "--docx", str(out)]) == 0
    text = "\n".join(p.text for p in docx.Document(str(out)).paragraphs)
    assert "Ben" in text
