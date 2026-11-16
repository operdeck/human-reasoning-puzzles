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
    try_lower_role_atom,
    try_lower_role_target,
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
        "some role:guard in area:hall",
        "every role:guard in area:hall",
        "no role:guard in area:hall",
        "not every role:guard in area:hall",
        "not no role:guard in area:hall",
        "some role:guard is attribute:trained",
        "every role:guard is attribute:trained",
        "not every role:guard is attribute:trained",
    ],
)
def test_lowered_role_determiners_match_reference(board, formula):
    _assert_matches_reference(board, formula, try_lower_role_atom, solve=True)


def test_role_determiners_on_an_empty_role_are_not_miscompiled(board):
    board = replace(board, roles=[RoleSpec("guard", frozenset({0}))])
    _assert_matches_reference(
        board, "some role:guard in area:hall", try_lower_role_atom, solve=True
    )
    _assert_matches_reference(
        board, "every role:guard in area:hall", try_lower_role_atom, solve=True
    )


@pytest.mark.parametrize(
    "formula",
    [
        "some role:guard is role:guest",
        "every role:guard is role:guest",
        "no role:guard is role:guest",
        "not every role:guard is role:guest",
        "every role:guard is role:guard",
        "not every role:guard is role:guard",
    ],
)
def test_lowered_role_overlap_matches_reference(board, formula):
    board = replace(board, roles=[*board.roles, RoleSpec("guest", frozenset({0, 1, 2}))])
    _assert_matches_reference(board, formula, try_lower_role_atom, solve=True)


@pytest.mark.parametrize(
    "formula",
    [
        "Ada dir:areas role:guard = 0",
        "not Ada dir:areas role:guard = 0",
        "no Ada dir:up role:guard",
        "Ada on role:guard",
        "not Ada on role:guard",
        "Ada touches role:guard",
    ],
)
def test_lowered_relation_to_role_matches_reference(board, formula):
    _assert_matches_reference(board, formula, try_lower_role_target, solve=True)


def test_one_person_role_target_distinguishes_self_overlap_from_other_relations():
    board = Board(
        size=1,
        regions=[["a"]],
        region_names={"a": "hall"},
        objects=[],
        people=["Ada"],
        roles=[RoleSpec("guard", frozenset({0, 1}))],
    )
    for formula in (
        "Ada dir:areas role:guard = 0",
        "not Ada dir:areas role:guard = 0",
        "Ada on role:guard",
    ):
        _assert_matches_reference(board, formula, try_lower_role_target, solve=True)


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


@pytest.mark.parametrize(
    "formula",
    [
        "Ada in area:hall and Ben in rows:3",
        "Ada on mark:red or Ben on mark:blue",
        "Ada is role:guard iff Ben is role:guard",
        "if Ada is role:guard then Ben is attribute:staff",
        "if Ada is attribute:trained then Ben dir:left Ada",
        "not (Ada touches Ben or Ada on Ada)",
        "exactly 1 of (Ada on mark:red; Ben on mark:blue; Ada is role:guard)",
        "at least 2 of (Ada is role:guard; not Ada is role:guard; Ben in area:hall)",
        "at most 1 of (Ada is role:guard; Ben is role:guard)",
        "Ada is role:guard and not Ada is role:guard",
        "Ada on Ada iff not Ada touches Ada",
        "if count role:guard = 0 then Ada in area:hall",
        "count (role:guard on mark:red) >= 1 iff Ben is role:guard",
        "not (count people on mark:red odd or count people in area:hall = 0)",
        "exactly 1 of (count role:guard = 1; count people on mark:blue = 0)",
        "count people on object:bed = 2 or Ada is role:guard",
        "some ?p in people: ?p on mark:red",
        "every ?p in people: ?p is role:guard",
        "no ?p in attribute:trained: ?p in area:hall",
        "exactly 1 ?p in people: ?p is role:guard",
        "at least 1 ?p in people: ?p touches Ben",
        "at most 1 ?p in people: ?p in area:hall",
        "every ?p, ?q in people: ?p dir:areas ?q = 0",
        "some ?p in people: every ?q in people: ?p on ?q",
        "every ?p in (attribute:trained except Ada): ?p on mark:red",
        "(some ?p in (attribute:trained except Ada): ?p on mark:red) or Ada in area:hall",
        "if Ada is role:guard then some ?p in people: ?p on mark:blue",
        "some ?p in role:guard: ?p on mark:red",
        "every ?p in role:guard: ?p in area:hall",
        "no ?p in role:guard: ?p touches Ben",
        "exactly 1 ?p in role:guard: ?p on mark:blue",
        "at least 1 ?p in role:guard: ?p is attribute:trained",
        "at most 1 ?p in role:guard: ?p in area:hall",
        "every ?p, ?q in role:guard: ?p dir:areas ?q = 0",
        "some ?p, ?q in role:guard: ?p dir:left ?q",
        "some ?p in people: every ?q in role:guard: ?p dir:areas ?q = 0",
        "some role:guard on mark:red or Ada in area:hall",
        "every role:guard is attribute:trained iff Ben is role:guard",
        "no role:guard in area:hall and Ada on mark:red",
        "not (Ada touches role:guard) or Ben is role:guard",
        "no Ada on role:guard iff Ada is role:guard",
        "some role:guard touches role:guard or Ada is role:guard",
        "role:guard = Ada",
        "role:guard != Ada, Ben",
        "(people in area:hall) = Ada",
        "(role:guard on mark:red) = (people on mark:blue)",
        "(people except role:guard) = Ada",
        "(role:guard = Ada) iff Ben on mark:red",
        "every ?p in people: (role:guard = ?p) or ?p in area:hall",
        "role:guard,attribute:trained = Ada",
        "every ?p in (people in area:hall): ?p is role:guard",
        "some ?p in (role:guard except Ada): ?p on mark:red",
        "exactly 1 ?p in role:guard,attribute:trained: ?p on mark:blue",
        "count (people except role:guard) = 1",
        "count role:guard,attribute:trained = 1",
        "count ((people except role:guard) in area:hall) odd",
        "count ((role:guard,attribute:trained) on mark:red) >= 1 or Ben in rows:3",
        "some (people except role:guard) on mark:red",
        "every Ada,Ben is role:guard,attribute:trained",
        "Ada is (people in area:hall) iff Ben is role:guard",
        "no Ada touches (people except role:guard)",
        "some (role:guard,attribute:trained) touches role:guard",
        "area:hall is empty",
        "object:bed is occupied",
        "rows:3 is empty iff Ada is role:guard",
        "if object:bed is occupied then Ada on object:bed",
        "no area:hall is empty",
    ],
)
def test_boolean_compilation_matches_reference(board, formula):
    statement = parse_statement(formula)
    model = compile_statements(board, [statement])
    for candidate in solutions(board, [], limit=1000):
        trial = model.clone()
        try:
            for person in board.people:
                trial.assign(trial.literal(person, candidate[person]), "test", "fixed placement")
                role = board.role_variable(person, "guard")
                trial.assign(trial.literal(role, candidate[role]), "test", "fixed role")
            accepted = Solver(trial).solve().contradiction is None
        except Contradiction:
            accepted = False
        placed = {person: candidate[person] for person in board.people}
        roles = {
            (person, "guard"): candidate[board.role_variable(person, "guard")]
            for person in board.people
        }
        assert accepted == holds(statement, board, placed, roles), candidate


def test_blocked_footprint_is_empty(board):
    blocked = Square(0, 2)
    board = replace(
        board,
        objects=[*board.objects, BoardObject("rock", "blocking", (blocked,))],
    )
    statement = parse_statement("object:rock is empty")
    model = compile_statements(board, [statement])
    assert Solver(model).solve().contradiction is None
    for candidate in solutions(board, [], limit=1000):
        placed = {person: candidate[person] for person in board.people}
        roles = {
            (person, "guard"): candidate[board.role_variable(person, "guard")]
            for person in board.people
        }
        assert holds(statement, board, placed, roles)


@pytest.mark.parametrize(
    "formula",
    [
        "count empty cells = 7",
        "count empty free cells = 6",
        "count occupied cells = 2",
        "count empty cells odd iff Ada is role:guard",
        "count (empty cells on mark:blocked) = 1",
        "count (empty free cells on mark:blocked) = 0",
        "count (empty cells in area:hall) >= 1",
    ],
)
def test_cell_occupancy_counts_include_blocked_cells(board, formula):
    blocked = Square(0, 2)
    board = replace(
        board,
        objects=[*board.objects, BoardObject("rock", "blocking", (blocked,))],
        marks=[*board.marks, CellMark("blocked", (blocked,))],
    )
    statement = parse_statement(formula)
    model = compile_statements(board, [statement])
    for candidate in solutions(board, [], limit=1000):
        trial = model.clone()
        try:
            for person in board.people:
                trial.assign(trial.literal(person, candidate[person]), "test", "fixed placement")
                role = board.role_variable(person, "guard")
                trial.assign(trial.literal(role, candidate[role]), "test", "fixed role")
            accepted = Solver(trial).solve().contradiction is None
        except Contradiction:
            accepted = False
        placed = {person: candidate[person] for person in board.people}
        roles = {
            (person, "guard"): candidate[board.role_variable(person, "guard")]
            for person in board.people
        }
        assert accepted == holds(statement, board, placed, roles), candidate


def test_overlapping_cell_counts_share_empty_literals(board):
    board = replace(
        board,
        objects=[*board.objects, BoardObject("rock", "blocking", (Square(0, 2),))],
    )
    model = compile_statements(
        board,
        [
            parse_statement("count empty cells = 7"),
            parse_statement("count empty free cells = 6"),
        ],
    )
    counts = {constraint.name: constraint for constraint in model.constraints}
    assert set(counts["clue 2"].literals) < set(counts["clue 1"].literals)
    assert len(set(counts["clue 2"].literals)) == len(board.free)


def test_compiler_explicitly_rejects_unimplemented_shapes(board):
    with pytest.raises(NotImplementedError, match="clue 1: expression lowering is not implemented"):
        compile_statements(board, [parse_statement("Ada dir:nearest Ben")])
