from csp.murdoku import Board, RoleSpec
from csp.murdoku_expression_report import describe
from csp.murdoku_lang import parse_statement
from csp.murdoku_lower import compile_statements_with_origins


def test_report_groups_model_primitives_by_source_ast():
    board = Board(
        size=2,
        regions=[["a", "a"], ["b", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[],
        people=["Ada", "Ben"],
        roles=[RoleSpec("guard", frozenset({0, 1, 2}))],
    )
    rule = parse_statement("Ada in area:hall | Own wording")
    clue = parse_statement("count role:guard = 1")
    output = describe(compile_statements_with_origins(board, [clue], rules=[rule]))

    assert "rule 1: Ada in area:hall" in output
    assert "clue 1: count role:guard = 1" in output
    assert "constraint: clue 1" in output
    assert "Own wording" not in output
    assert "The model" in output


def test_report_includes_shared_constraints_under_each_source():
    board = Board(
        size=2,
        regions=[["a", "a"], ["b", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[],
        people=["Ada", "Ben"],
    )
    clues = [
        parse_statement("area:hall is empty"),
        parse_statement("count empty areas = 1"),
    ]
    output = describe(compile_statements_with_origins(board, clues))
    first, second = output.split("clue 2: count empty areas = 1", 1)
    assert "constraint: clue 1 state" in first
    assert "constraint: clue 1 state" in second
