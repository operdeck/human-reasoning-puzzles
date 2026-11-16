from dataclasses import replace
from itertools import permutations

import pytest

from csp.murdoku import Board, BoardObject, CellMark, RoleSpec, Square
from csp.murdoku_expr_lint import role_negation_warnings, size_budget_warnings, vacuous_errors
from csp.murdoku_lang import holds, parse_statement
from csp.murdoku_lower import compile_statements_with_origins


@pytest.fixture
def board():
    return Board(
        size=2,
        regions=[["a", "a"], ["b", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[],
        people=["Ada", "Ben"],
        roles=[RoleSpec("guard", frozenset({0, 1, 2}))],
    )


@pytest.mark.parametrize(
    "source",
    [
        "not Ada dir:areas role:guard = 0",
        "no Ada dir:areas role:guard = 0",
        "if Ben in area:hall then not Ada dir:areas role:guard = 0",
    ],
)
def test_warns_when_negated_relation_allows_role_membership(board, source):
    statement = parse_statement(source, line=7)
    warnings = role_negation_warnings(board, [statement])
    assert len(warnings) == 1
    assert warnings[0].startswith("line 7, column ")
    assert "not Ada is role:guard" in warnings[0]


def test_warning_reflects_reference_semantics(board):
    statement = parse_statement("not Ada dir:areas role:guard = 0")
    assert holds(
        statement,
        board,
        {"Ada": Square(0, 0), "Ben": Square(1, 1)},
        {("Ada", "guard"): True, ("Ben", "guard"): False},
    )
    assert role_negation_warnings(board, [statement])


@pytest.mark.parametrize(
    "source",
    [
        "not (Ada dir:areas role:guard = 0 and Ben in area:hall)",
        "not (Ada dir:areas role:guard = 0 or Ben in area:hall)",
        "not (every ?p in people: Ada dir:areas role:guard = 0 and ?p in area:hall)",
    ],
)
def test_warns_when_negation_wraps_a_compound_formula(board, source):
    assert role_negation_warnings(board, [parse_statement(source)])


def test_double_negation_inside_compound_formula_does_not_warn(board):
    statement = parse_statement("not (not Ada dir:areas role:guard = 0 or Ben in area:hall)")
    assert not role_negation_warnings(board, [statement])


def test_warns_for_each_eligible_role_in_a_union(board):
    board = replace(
        board,
        roles=[
            RoleSpec("guard", frozenset({1})),
            RoleSpec("chef", frozenset({1})),
            RoleSpec("pilot", frozenset({1}), eligible_people=frozenset({"Ben"})),
        ],
    )
    statement = parse_statement("not Ada dir:areas role:guard,chef,pilot = 0")
    warnings = role_negation_warnings(board, [statement])
    assert len(warnings) == 2
    assert "not Ada is role:guard" in warnings[0]
    assert "not Ada is role:chef" in warnings[1]


@pytest.mark.parametrize(
    "source",
    [
        "Ada dir:areas role:guard = 0",
        "not not Ada dir:areas role:guard = 0",
        "not Ada is role:guard",
        "not Ada in area:hall",
    ],
)
def test_does_not_warn_for_other_statements(board, source):
    assert not role_negation_warnings(board, [parse_statement(source)])


@pytest.mark.parametrize(
    "role",
    [
        RoleSpec("guard", frozenset({0})),
        RoleSpec("guard", frozenset({1}), eligible_people=frozenset({"Ben"})),
    ],
)
def test_does_not_warn_for_an_ineligible_subject(board, role):
    board = replace(board, roles=[role])
    assert not role_negation_warnings(board, [parse_statement("not Ada dir:areas role:guard = 0")])


@pytest.mark.parametrize(
    "source",
    [
        "Ada beside Ben",
        "Ada in area:hall and Ada beside Ben",
        "Ada beside Ada",
        "Ada touches Ben",
        "Ada touches Ada",
    ],
)
def test_impossible_required_people_adjacency_is_an_error(board, source):
    errors = vacuous_errors(board, [parse_statement(source, line=4)])
    assert len(errors) == 1
    assert errors[0].startswith("line 4, column ")
    assert "different rows and columns" in errors[0]


@pytest.mark.parametrize("operator", ["beside", "touches"])
def test_person_adjacency_is_impossible_for_every_valid_placement(board, operator):
    statement = parse_statement(f"Ada {operator} Ben")
    for columns in permutations(range(board.size), len(board.people)):
        placed = {person: Square(row, columns[row]) for row, person in enumerate(board.people)}
        roles = {(person, "guard"): False for person in board.people}
        assert not holds(statement, board, placed, roles)


def test_impossible_occupied_scope_direction_is_an_error(board):
    board = replace(
        board,
        marks=[
            CellMark("left", (Square(0, 0),)),
            CellMark("right", (Square(0, 1),)),
            CellMark("lower", (Square(1, 1),)),
        ],
    )
    same_row = parse_statement(
        "some (people on mark:left) dir:right (people on mark:right)", line=6
    )
    assert "line 6, column " in vacuous_errors(board, [same_row])[0]
    for columns in permutations(range(board.size), len(board.people)):
        placed = {person: Square(row, columns[row]) for row, person in enumerate(board.people)}
        roles = {(person, "guard"): False for person in board.people}
        assert not holds(same_row, board, placed, roles)

    possible = parse_statement("some (people on mark:left) dir:up (people on mark:lower)")
    assert not vacuous_errors(board, [possible])
    blocked = replace(board, objects=[BoardObject("cabinet", "blocking", (Square(1, 1),))])
    assert vacuous_errors(blocked, [possible])


@pytest.mark.parametrize(
    "source",
    [
        "no (people on mark:left) dir:right (people on mark:right)",
        "not some (people on mark:left) dir:right (people on mark:right)",
        "some (people on mark:left) dir:right (people on mark:right) or Ada in area:hall",
        "if some (people on mark:left) dir:right (people on mark:right) then Ada in area:hall",
    ],
)
def test_impossible_occupied_scope_not_required_is_not_an_error(board, source):
    board = replace(
        board,
        marks=[
            CellMark("left", (Square(0, 0),)),
            CellMark("right", (Square(0, 1),)),
        ],
    )
    assert not vacuous_errors(board, [parse_statement(source)])


@pytest.mark.parametrize(
    "source",
    ["Ada dir:left Ada", "Ada dir:areas Ada = 0", "Ada dir:nearest Ada"],
)
def test_required_self_direction_is_an_error(board, source):
    statement = parse_statement(source, line=4)
    errors = vacuous_errors(board, [statement])
    assert len(errors) == 1
    assert errors[0].startswith("line 4, column ")
    assert "distinct entities" in errors[0]
    placed = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    roles = {(person, "guard"): False for person in board.people}
    assert not holds(statement, board, placed, roles)


@pytest.mark.parametrize("mode", ["rows", "cols"])
@pytest.mark.parametrize("comparison", ["=", "<="])
def test_required_same_line_for_people_is_an_error(board, mode, comparison):
    statement = parse_statement(f"Ada dir:{mode} Ben {comparison} 0", line=4)
    errors = vacuous_errors(board, [statement])
    assert len(errors) == 1
    assert "cannot share a row or column" in errors[0]
    placed = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    roles = {(person, "guard"): False for person in board.people}
    assert not holds(statement, board, placed, roles)


@pytest.mark.parametrize(
    "source",
    [
        "not Ada beside Ben",
        "not Ada touches Ben",
        "no Ada beside Ben",
        "no Ada touches Ben",
        "Ada beside Ben or Ada in area:hall",
        "Ada dir:left Ada or Ada in area:hall",
        "if Ada beside Ben then Ada in area:hall",
        "not Ada dir:areas Ada = 0",
        "no Ada dir:left Ada",
        "Ada dir:rows Ben >= 0",
        "not Ada dir:cols Ben = 0",
        "Ada dir:rows Ben = 0 or Ada in area:hall",
        "Ada in Ada",
        "Ada on Ada",
        "Ada beside object:bed",
    ],
)
def test_adjacency_error_does_not_reject_nonrequired_or_other_relations(board, source):
    assert not vacuous_errors(board, [parse_statement(source)])


def test_size_budget_warns_for_emitted_position_and_role_variables(board):
    clue = parse_statement("Ada dir:left role:guard", line=6)
    compiled = compile_statements_with_origins(board, [clue])
    assert not size_budget_warnings(board, compiled)
    warnings = size_budget_warnings(board, compiled, budget=2)
    assert len(warnings) == 1
    assert warnings[0].startswith("line 6, column 1: clue 1")
    assert "3 position/role variables (budget 2)" in warnings[0]
    assert "splitting" in warnings[0]


def test_default_budget_warns_at_four_ground_variables():
    board = Board(
        size=3,
        regions=[["a"] * 3 for _ in range(3)],
        region_names={"a": "hall"},
        objects=[],
        people=["Ada", "Ben", "Cy"],
        roles=[RoleSpec("guard", frozenset({0, 1, 2, 3}))],
    )
    compiled = compile_statements_with_origins(board, [parse_statement("Ada is role:guard")])
    compiled.model.relate(
        "large clue",
        ("Ada", "Ben", "Cy", board.role_variable("Cy", "guard")),
        lambda *_values: True,
    )
    compiled.relation_origins[len(compiled.model.relations) - 1] = (compiled.origins[0],)
    warnings = size_budget_warnings(board, compiled)
    assert len(warnings) == 1
    assert "4 position/role variables (budget 3)" in warnings[0]


def test_size_budget_must_be_positive(board):
    compiled = compile_statements_with_origins(board, [])
    with pytest.raises(ValueError, match="positive"):
        size_budget_warnings(board, compiled, budget=0)
