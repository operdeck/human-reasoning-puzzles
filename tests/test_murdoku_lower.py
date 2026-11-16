from dataclasses import replace

import pytest

from csp.bruteforce.murdoku_expr import solutions
from csp.core import Contradiction, Solver, rule_relations
from csp.murdoku import Board, BoardObject, CellMark, RoleSpec, Square, compile_puzzle
from csp.murdoku_lang import holds, parse_statement
from csp.murdoku_lower import (
    compile_statements,
    try_lower_count,
    try_lower_location,
    try_lower_membership,
    try_lower_person_pair,
)


@pytest.fixture
def board():
    return Board(
        size=3,
        regions=[["a", "a", "a"], ["b", "b", "b"], ["b", "b", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[BoardObject("bed", "standable", (Square(2, 0),))],
        people=["Ada", "Ben"],
        area_tags={"outside": ["garden"]},
        attributes={"trained": frozenset({"Ada"}), "staff": frozenset({"Ben"})},
        marks=[
            CellMark("red", (Square(0, 0), Square(1, 1))),
            CellMark("blue", (Square(1, 2), Square(2, 0))),
        ],
        roles=[RoleSpec("guard", frozenset({0, 1, 2}))],
    )


def _assert_matches_reference(board, formula, lower, *, solve=False):
    statement = parse_statement(formula)
    model = compile_puzzle(board, [])
    assert lower(model, board, statement, "clue 1")
    for solution in solutions(board, [], limit=1000):
        placed = {person: solution[person] for person in board.people}
        roles = {
            (person, role.name): solution[board.role_variable(person, role.name)]
            for role in board.roles
            for person in board.people
        }
        trial = model.clone()
        try:
            for person, square in placed.items():
                trial.assign(trial.literal(person, square), "test", "fixed placement")
            for (person, role), present in roles.items():
                trial.assign(
                    trial.literal(board.role_variable(person, role), present),
                    "test",
                    "fixed role",
                )
            if solve:
                accepted = Solver(trial).solve().contradiction is None
            else:
                trial.check()
                rule_relations(trial)
                accepted = True
        except Contradiction:
            accepted = False
        assert accepted == holds(statement, board, placed, roles), solution


@pytest.mark.parametrize(
    "formula",
    [
        "count people in area:hall = 0",
        "count people in area:hall >= 1",
        "count people on mark:red != 1",
        "count people on mark:red < 1",
        "count people on mark:red <= 1",
        "count people on mark:red > 0",
        "count people on mark:red,blue = 0",
        "count people on mark:red,blue odd",
        "count people on mark:red,blue even",
        "count people on mark:red,blue 1..2",
        "count people on mark:red,objects >= 1",
        "count people in tag:outside = 1",
        "count people in rows:1,3 = 1",
        "count people on object:bed = 1",
        "count people beside object:bed = 1",
        "count people touches mark:red >= 1",
        "count (people dir:up object:bed = 1) = 1",
        "count (people dir:rows mark:red = 0) odd",
        "count role:guard = 1",
        "count role:guard != 1",
        "count people = 2",
        "count (people except Ada) in area:garden = 1",
        "count (attribute:trained on mark:red) = 1",
        "count (Ada, Ben is attribute:trained) = 1",
        "count attribute:trained,staff = 2",
    ],
)
def test_lowered_count_matches_reference_for_every_placement_and_role(board, formula):
    _assert_matches_reference(board, formula, try_lower_count)


@pytest.mark.parametrize(
    "formula",
    [
        "Ada in tag:outside",
        "not Ada on mark:red,blue",
        "some Ada on object:bed",
        "Ada beside object:bed",
        "Ada touches mark:red",
        "not Ada beside mark:blue",
        "Ada dir:rows mark:red = 0",
        "Ada dir:up+right mark:red,blue <= 1",
        "Ada dir:diagonal object:bed",
        "Ada dir:areas area:hall = 0",
        "not Ada dir:king object:bed <= 1",
        "no Ada in rows:1,3",
        "not no Ada in rows:1,3",
    ],
)
def test_lowered_location_matches_reference_for_every_placement_and_role(board, formula):
    _assert_matches_reference(board, formula, try_lower_location)


@pytest.mark.parametrize(
    "formula",
    [
        "count (role:guard in area:hall) = 1",
        "count (role:guard on mark:red,blue) = 0",
        "count (role:guard beside object:bed) >= 1",
        "count (role:guard dir:up object:bed = 1) odd",
    ],
)
def test_lowered_role_spatial_counts_match_reference(board, formula):
    _assert_matches_reference(board, formula, try_lower_count, solve=True)


@pytest.mark.parametrize(
    "formula",
    [
        "Ada is role:guard",
        "not Ada is role:guard",
        "no Ada is role:guard",
        "Ada is attribute:trained",
        "Ben is attribute:trained",
        "Ben is attribute:trained,staff",
        "not Ada is Ben",
    ],
)
def test_lowered_membership_matches_reference(board, formula):
    _assert_matches_reference(board, formula, try_lower_membership)


@pytest.mark.parametrize(
    "formula",
    [
        "Ada dir:up Ben",
        "Ada dir:down Ben = 1",
        "Ada dir:up Ben <= 1",
        "Ada dir:right Ben >= 1",
        "Ada dir:up+right Ben = 1",
        "Ada dir:diagonal Ben >= 2",
        "Ada dir:manhattan Ben >= 2",
        "Ada dir:euclidean Ben <= 2",
        "Ada dir:areas Ben = 0",
        "Ada dir:knight Ben",
        "not Ada dir:areas Ben = 0",
        "Ada is Ada",
        "not Ada is Ben",
        "Ada on Ada",
        "Ada on Ben",
        "Ada touches Ada",
        "not Ada beside Ben",
        "Ada dir:up Ada",
    ],
)
def test_lowered_person_pair_matches_reference_for_every_placement_and_role(board, formula):
    _assert_matches_reference(board, formula, try_lower_person_pair)


def test_unsupported_statement_does_not_change_model(board):
    model = compile_puzzle(board, [])
    before = (model.num_literals, len(model.constraints), len(model.relations))
    assert not try_lower_count(model, board, parse_statement("Ada in area:hall"), "clue 1")
    assert not try_lower_person_pair(model, board, parse_statement("Ada dir:nearest Ben"), "clue 2")
    assert before == (model.num_literals, len(model.constraints), len(model.relations))


def test_static_empty_scope_reports_infeasible_count(board):
    square = Square(0, 0)
    board = replace(
        board,
        objects=[BoardObject("rock", "blocking", (square,))],
        marks=[CellMark("blocked", (square,))],
    )
    model = compile_puzzle(board, [])
    assert try_lower_count(model, board, parse_statement("count people on mark:blocked = 0"), "ok")
    with pytest.raises(ValueError, match="no feasible value on this board"):
        try_lower_count(model, board, parse_statement("count people on mark:blocked = 1"), "bad")


def test_blocked_feature_footprints_still_support_adjacency(board):
    blocked = Square(0, 2)
    board = replace(
        board,
        objects=[*board.objects, BoardObject("rock", "blocking", (blocked,))],
    )
    _assert_matches_reference(board, "Ada beside object:rock", try_lower_location)
    _assert_matches_reference(board, "Ada touches object:rock", try_lower_location)
    _assert_matches_reference(board, "Ada dir:king object:rock = 1", try_lower_location)
    _assert_matches_reference(board, "count people on object:rock = 0", try_lower_count)
    _assert_matches_reference(board, "count people beside object:rock = 1", try_lower_count)


def test_compiled_statement_conjunction_matches_reference_search(board):
    statements = [
        parse_statement("Ada in area:hall"),
        parse_statement("Ben in rows:3"),
        parse_statement("count role:guard = 1"),
        parse_statement("Ada dir:left Ben"),
    ]
    expected = solutions(board, statements, limit=1000)
    assert expected
    model = compile_statements(board, statements)
    actual = []
    for candidate in solutions(board, [], limit=1000):
        trial = model.clone()
        try:
            for person in board.people:
                trial.assign(trial.literal(person, candidate[person]), "test", "fixed placement")
                role = board.role_variable(person, "guard")
                trial.assign(trial.literal(role, candidate[role]), "test", "fixed role")
            trial.check()
            rule_relations(trial)
            actual.append(candidate)
        except Contradiction:
            continue
    assert actual == expected


def test_compiler_explicitly_rejects_unimplemented_shapes(board):
    with pytest.raises(NotImplementedError, match="clue 1: expression lowering is not implemented"):
        compile_statements(board, [parse_statement("some role:guard in area:hall")])
