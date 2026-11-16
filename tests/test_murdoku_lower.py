from dataclasses import replace
from random import Random

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
        "count empty areas = 1",
        "count (empty areas in tag:outside) = 1",
        "count (occupied areas on mark:red) >= 1",
        "area:hall is empty iff count empty areas = 1",
        "area:hall in area:hall",
        "area:garden in tag:outside",
        "area:garden on tag:outside",
        "not area:hall touches area:hall",
        "not area:hall dir:areas area:hall = 0",
        "area:hall in area:garden or Ada is role:guard",
        "some area:hall,garden in tag:outside",
        "every ?a in areas: ?a in ?a",
        "every ?a in tag:outside: ?a in tag:outside",
        "every ?a, ?b in areas: ?a != ?b",
        "some ?a in area:hall,garden: ?a on area:hall",
        "some ?a in areas: Ada in ?a and Ben in ?a",
        "every ?a in empty areas: no people in ?a",
        "some ?a in occupied areas: Ada in ?a",
        "exactly 1 ?a in empty areas: ?a in tag:outside",
        "no ?a, ?b in empty areas: ?a on ?b",
        "some ?a in (occupied areas on mark:red): Ben in ?a",
        "Ada in area of Ben",
        "Ada in area of Ada",
        "Ada on row of Ben",
        "Ada touches area of Ben",
        "Ada dir:rows cell of Ada = 0",
        "Ben beside area of Ada or Ada is role:guard",
        "count (people in area of Ada) = 1",
        "count (people in area of Ada) > count (people in area of Ben) or Ada is role:guard",
        "every ?p in people: count (people in area of ?p) >= 1",
        "every ?r in rows: ?r on ?r",
        "every ?r, ?s in rows: ?r != ?s",
        "some ?r in rows: Ada in ?r and Ben in ?r",
        "rows:1 in area:hall",
        "rows:1 on columns:1",
        "not rows:1 touches rows:1",
        "some rows:1,3 on columns:2",
        "count role:guard = count (people in area:hall)",
        "count role:guard + count (people in area:hall) >= 2",
        "count role:guard - count (people on mark:red) = 0",
        "(count role:guard + 1) odd",
        "if count role:guard > count (people on mark:red) then Ada is role:guard",
        "some ?r in roles: Ada is ?r",
        "every ?r in roles: not Ada is ?r",
        "some ?r in roles: not Ada is ?r",
        "exactly 1 ?r in roles: Ada is ?r",
        "every ?r in roles: ?r is ?r",
        "every ?r, ?s in roles: ?r != ?s",
        "(some ?r, ?s in roles: ?r = ?s) or Ada is role:guard",
    ],
)
def test_boolean_compilation_matches_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


def _assert_compilation_matches_reference(board, formula):
    statement = parse_statement(formula)
    model = compile_statements(board, [statement])
    for candidate in solutions(board, [], limit=1000):
        trial = model.clone()
        try:
            for person in board.people:
                trial.assign(trial.literal(person, candidate[person]), "test", "fixed placement")
                for role in board.roles:
                    variable = board.role_variable(person, role.name)
                    trial.assign(trial.literal(variable, candidate[variable]), "test", "fixed role")
            accepted = Solver(trial).solve().contradiction is None
        except Contradiction:
            accepted = False
        placed = {person: candidate[person] for person in board.people}
        roles = {
            (person, role.name): candidate[board.role_variable(person, role.name)]
            for person in board.people
            for role in board.roles
        }
        assert accepted == holds(statement, board, placed, roles), candidate


@pytest.mark.parametrize(
    "formula",
    [
        "Ada dir:up empty rows = 1",
        "Ada on object:bed and every ?b in object:bed: Ada on ?b or ?b in empty rows",
        "some (people beside object:chest) dir:up Ada = 1",
        "Ada in rows:1,last and count people in rows:1,last = 1",
    ],
)
def test_issue_243_clues_match_reference_for_every_placement(board, formula):
    board = replace(
        board,
        objects=[
            BoardObject("bed", "standable", (Square(0, 0),)),
            BoardObject("bed", "standable", (Square(2, 0),)),
            BoardObject("chest", "blocking", (Square(1, 1),)),
        ],
    )
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "every ?b in areas except area:hall: count (people in ?b) < count (people in area:hall)",
        "no ?r in empty rows: some occupied rows dir:up ?r and some occupied rows dir:down ?r",
        "some ?p in people: every ?c in (cells in area:hall): ?p dir:left ?c",
        "(people in area of role:guard) = Ada, role:guard",
        "every ?p, ?q in people: ?p dir:areas ?q >= 1",
    ],
)
def test_composed_glossary_clues_match_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


def test_random_small_well_typed_statements_match_reference():
    random = Random(244)
    formulas = [
        "Ada in area:hall",
        "not Ada on mark:red",
        "Ada dir:up empty rows = 1",
        "count people on mark:red = 1",
        "Ada is role:guard iff Ben on mark:red",
        "every ?a in areas: count (people in ?a) <= count people",
        "some ?r in rows: ?r is empty",
        "(people in area:hall) = Ada",
        "every ?p, ?q in people: ?p dir:areas ?q >= 1",
        "some (people on mark:red) dir:rows Ada = 0",
    ]
    for _ in range(30):
        size = random.choice([2, 3])
        cells = [Square(row, col) for row in range(size) for col in range(size)]
        regions = ["a", "b", *(random.choice(["a", "b"]) for _ in cells[2:])]
        random.shuffle(regions)
        red = tuple(random.sample(cells, random.randint(1, min(3, len(cells)))))
        objects = (
            [BoardObject("rock", "blocking", (random.choice(cells),))]
            if random.choice([False, True])
            else []
        )
        board = Board(
            size=size,
            regions=[regions[row * size : (row + 1) * size] for row in range(size)],
            region_names={"a": "hall", "b": "garden"},
            objects=objects,
            people=["Ada", "Ben"],
            marks=[CellMark("red", red)],
            roles=[RoleSpec("guard", frozenset({0, 1, 2}))],
        )
        first, second = random.sample(formulas, 2)
        operator = random.choice(["and", "or", "iff", "if"])
        formula = (
            f"if ({first}) then ({second})"
            if operator == "if"
            else f"({first}) {operator} ({second})"
        )
        try:
            _assert_compilation_matches_reference(board, formula)
        except Contradiction:
            assert not solutions(board, [parse_statement(formula)], limit=1000)


@pytest.mark.parametrize(
    "formula",
    [
        "some ?r in roles: Ada is ?r",
        "some ?r in roles: not Ada is ?r",
        "exactly 1 ?r in roles: Ada is ?r",
        "every ?r in roles: Ada is ?r",
        "every ?r, ?s in roles: ?r != ?s",
        "every ?r in roles: ?r is ?r",
        "no ?r, ?s in roles: ?r is ?s",
        "every ?r, ?s in roles: count (?r, ?s) = 2",
        "count roles = 2",
        "every ?r in roles: every ?s in (roles except ?r): ?s != ?r",
        "every ?r in roles: count (roles except ?r) = 1",
    ],
)
def test_bound_role_membership_with_multiple_roles(board, formula):
    board = replace(board, roles=[*board.roles, RoleSpec("guest", frozenset({0, 1, 2}))])
    _assert_compilation_matches_reference(board, formula)


def test_bound_role_membership_with_no_roles(board):
    board = replace(board, roles=[])
    _assert_compilation_matches_reference(board, "every ?r in roles: Ada is ?r")
    _assert_compilation_matches_reference(board, "not (some ?r in roles: Ada is ?r)")


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
        "count empty cells - count empty free cells = 1",
        "count occupied cells = count role:guard",
        "count empty areas + count occupied areas = 2",
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


def test_area_emptiness_is_reused_between_atom_and_count(board):
    model = compile_statements(
        board,
        [
            parse_statement("area:hall is empty"),
            parse_statement("count empty areas = 1"),
        ],
    )
    counts = {constraint.name: constraint for constraint in model.constraints}
    assert counts["clue 1"].reified_by in counts["clue 2"].literals


def test_overlapping_area_tags_share_one_empty_literal(board):
    board = replace(
        board,
        regions=[["a", "b", "a"], ["b", "a", "b"], ["b", "b", "b"]],
        area_tags={"outside": ["garden"], "other": ["garden"]},
    )
    model = compile_statements(
        board,
        [
            parse_statement("count (empty areas in tag:outside) = 1"),
            parse_statement("count (empty areas in tag:other) = 1"),
        ],
    )
    counts = {constraint.name: constraint for constraint in model.constraints}
    assert counts["clue 1"].literals == counts["clue 2"].literals


@pytest.mark.parametrize(
    "formula",
    [
        "every ?a in areas: ?a in ?a",
        "every ?a, ?b in areas: ?a != ?b",
        "every ?a in empty areas: ?a is empty",
        "every ?a in area of people: ?a is occupied",
        "every ?a in areas: count (?p in people where ?p in ?a) >= 0",
        "every ?a in areas: count (people in ?a) <= count people",
        "every ?a in areas: count (people in ?a) >= 1",
        "every ?a in areas: (people in ?a) = Ada",
        "every ?a in areas: some (people in ?a) on mark:red",
    ],
)
def test_area_quantifier_preserves_region_identity_with_duplicate_names(board, formula):
    board = replace(board, region_names={"a": "same", "b": "same"}, area_tags={})
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "(count cells = 9) iff Ada is role:guard",
        "(count free cells = 8) iff Ada is role:guard",
        "(count corner:board = 4) iff Ada is role:guard",
        "(count cell of mark:red = 2) iff Ada is role:guard",
        "(count row of mark:red = 2) iff Ada is role:guard",
        "(count area of mark:red = 2) iff Ada is role:guard",
        "(count objects + count mark:red = 3) iff Ada is role:guard",
        "(object_kind:standable = object:bed) iff Ada is role:guard",
        "(mark:red = mark:copy) iff Ada is role:guard",
        "(mark:red on mark:copy) iff Ada is role:guard",
        "(mark:red touches mark:copy) iff Ada is role:guard",
        "(count (objects except object:bed) = 1) iff Ada is role:guard",
        "(cell of mark:red = cell of mark:copy) iff Ada is role:guard",
        "(count cell of (mark:red,copy) = 2) iff Ada is role:guard",
    ],
)
def test_static_spatial_sets_preserve_entity_identity(board, formula):
    board = replace(
        board,
        objects=[*board.objects, BoardObject("rock", "blocking", (Square(0, 2),))],
        marks=[*board.marks, CellMark("copy", board.marks[0].cells)],
    )
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "(count (areas in tag:outside) = 1) iff Ada is role:guard",
        "(count (areas on area:hall) = 1) iff Ada is role:guard",
        "(count (areas touches area:hall) = 1) iff Ada is role:guard",
        "(count (rows on mark:red) = 2) iff Ada is role:guard",
        "(count (cells in area:hall) = 3) iff Ada is role:guard",
        "(count (objects on mark:red) = 0) iff Ada is role:guard",
        "(Ada in (rows on mark:red)) iff Ben is role:guard",
        "(Ada on cell of object:bed) iff Ben is role:guard",
        "(Ada in (areas except area:hall)) iff Ben is role:guard",
    ],
)
def test_static_spatial_filters_match_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "count (?p in people where ?p in area:hall) = 1",
        "count (?p in role:guard where ?p on mark:red) = 1",
        "count (?p in people where not ?p is role:guard) = 2",
        "(?p in people where ?p is role:guard) = role:guard",
        "Ada is (?p in people where ?p in area:hall)",
        "every ?p in (?q in people where ?q is role:guard): ?p in area:hall",
        "every ?p in people: count (?q in people where ?q beside ?p) = 0",
        "every ?r in roles: count (?p in people where ?p is ?r) = count role:guard",
        "some ?p in people: ?p beside (?q in people where ?q is role:guard)",
        "count (?p in people where count (?q in people where ?q is ?p) = 1) = 2",
        "count (?p in people where (?p on mark:red) or (?p is role:guard)) >= 1",
    ],
)
def test_person_comprehensions_match_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "every ?c in cells: ?c in ?c",
        "every ?c in corner:board: ?c is free",
        "exactly 1 ?c in cells: ?c is occupied",
        "every ?c in (cells on mark:red): ?c on mark:red",
        "some ?c in cells: Ada on ?c",
        "every ?c in cells: ?c in row of ?c",
        "every ?c in cells: count (cells except ?c) = 8",
        "every ?o in objects: ?o on ?o",
        "every ?o in objects: count cell of ?o >= 1",
        "some ?a, ?b in mark:red,copy: ?a != ?b",
        "some ?a, ?b in mark:red,copy: ?a on ?b",
        "every ?a in mark:red,copy: ?a is empty iff count (people on ?a) = 0",
        "every ?a in (areas on mark:red): ?a on mark:red",
        "every ?r in (rows on mark:red): ?r on mark:red",
    ],
)
def test_static_spatial_quantifiers_match_reference(board, formula):
    board = replace(board, marks=[*board.marks, CellMark("copy", board.marks[0].cells)])
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "every ?c in occupied cells: ?c is free",
        "every ?c in empty cells: ?c is empty",
        "some ?c in empty cells: not ?c is free",
        "no ?c in empty free cells: not ?c is free",
        "exactly 2 ?c in occupied cells: ?c is occupied",
        "at least 1 ?c in (empty cells on mark:red): ?c on mark:red",
        "every ?a, ?b in occupied cells: ?a != ?b",
        "every ?c in occupied cells: some ?p in people: ?p on ?c",
    ],
)
def test_occupancy_dependent_cell_quantifiers_match_reference(board, formula):
    board = replace(
        board,
        objects=[*board.objects, BoardObject("rock", "blocking", (Square(0, 2),))],
    )
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "(area:hall is empty and area:hall is empty) iff Ada is role:guard",
        "(area:hall is empty iff area:hall is empty) iff Ada is role:guard",
        "(exactly 1 of (area:hall is empty; area:hall is empty)) iff Ada is role:guard",
        "(exactly 2 of (area:hall is empty; area:hall is empty)) iff Ada is role:guard",
    ],
)
def test_repeated_boolean_operands_retain_multiplicity(board, formula):
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "area of Ada = area of Ben",
        "area of Ada != area of Ben",
        "row of Ada = row of Ben",
        "cell of Ada != cell of Ben",
        "count area of people = 1",
        "count area of role:guard = 0",
        "count row of people = 2",
        "count cell of people = 2",
        "count area of role:guard + count role:guard >= 1",
        "count (area of people except area:hall) = 1",
        "count (area:hall, area of role:guard) >= 1",
        "every ?p in people: count area of ?p = 1",
    ],
)
def test_person_projection_sets_match_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "every ?a in area of people: ?a is occupied",
        "every ?a in area of role:guard: some ?p in role:guard: ?p in ?a",
        "exactly 1 ?a in area of role:guard: ?a in area:hall",
        "some ?r in row of people: Ada in ?r",
        "every ?c in cell of people: ?c is occupied",
        "every ?a, ?b in area of people: ?a != ?b",
        "no ?a in (area of people except areas): ?a is occupied",
        "every ?a in (area of people on mark:red): ?a is occupied",
        "count (area of people in area of Ada) = 1",
        "count (row of role:guard on mark:red) >= 1",
        "count (cell of people on area of Ada) >= 1",
        "count occupied (area of people) = count area of people",
        "count empty (area of people) = 0",
        "every ?r in occupied (row of role:guard): ?r is occupied",
    ],
)
def test_projected_spatial_quantifiers_match_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "some area of people in area:hall",
        "every area of people is occupied",
        "every area of role:guard in tag:outside",
        "no area of role:guard on area:hall",
        "area:hall in area of people",
        "area:hall on area of Ben",
        "row of Ada on column of Ben",
        "cell of Ada on area of Ben",
        "object:bed in area of Ben",
        "Ada in area of role:guard",
        "not Ada in area of role:guard",
        "every people on row of role:guard",
        "no Ben on cell of role:guard",
        "Ada beside (area of role:guard except area:hall)",
        "some area:hall on role:guard",
        "area of Ada on Ben",
        "every row of people touches role:guard",
        "count (area of people on role:guard) >= 1",
        "every ?a in area of people: ?a in area of people",
        "no ?a in area of people: ?a touches ?a",
    ],
)
def test_dynamic_spatial_relations_match_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "count (?a in areas where ?a is empty) = count empty areas",
        "count (?r in rows where ?r on Ada) = 1",
        "every ?c in (?x in cells where ?x on people): ?c is occupied",
        "count (?a in area of people where ?a on role:guard) = 1",
        "every ?p in people: count (?a in areas where ?p in ?a) = 1",
        "Ada in (?a in areas where ?a is occupied)",
        "count (?o in objects where ?o is occupied) <= 1",
        "every ?o in (?x in objects where ?x on people): ?o is occupied",
        "Ada on (?o in objects where ?o is occupied)",
        "(?o in objects where ?o is occupied) = object:bed",
    ],
)
def test_spatial_comprehensions_match_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "area of occupied cells = area of people",
        "row of occupied cells = row of people",
        "cell of occupied (row of people) = cell of row of people",
        "count area of (?o in objects where ?o is occupied) <= 1",
        "every ?a in area of occupied cells: ?a is occupied",
    ],
)
def test_dynamic_spatial_projections_match_reference(board, formula):
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "Ada dir:nearest Ben",
        "Ada dir:furthest Ben",
        "not Ada dir:furthest Ben",
        "Ada dir:nearest:rows Ben",
        "Ada dir:furthest:cols Ben",
        "Ada dir:nearest:king Ben",
        "Ada dir:furthest:euclidean Ben",
        "Ada dir:nearest:areas Ben",
        "not Ada dir:furthest Ada",
    ],
)
def test_named_person_superlatives_match_reference(board, formula):
    board = replace(board, people=["Ada", "Ben", "Cy"], roles=[])
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "Ada dir:nearest role:guard",
        "Ada dir:furthest role:guard",
        "no Ada dir:nearest role:guard",
        "Ada dir:nearest object:bed",
        "Ada dir:furthest:king mark:red,blue",
        "Ada dir:nearest area of Ben",
        "Ada dir:nearest (people except Ada)",
    ],
)
def test_set_target_superlatives_match_reference(board, formula):
    board = replace(
        board,
        people=["Ada", "Ben", "Cy"],
        roles=[RoleSpec("guard", frozenset({0, 1, 2, 3}))],
    )
    _assert_compilation_matches_reference(board, formula)


@pytest.mark.parametrize(
    "formula",
    [
        "count (?r in roles where Ada is ?r) = 1",
        "count (?r in roles where Ada is ?r) + count (?r in roles where Ben is ?r) >= 1",
        "(?r in roles where Ada is ?r) = (?r in roles where Ben is ?r)",
        "some (?r in roles where Ada is ?r) is roles",
        "every (?r in roles where Ada is ?r) is roles",
        "every ?r in (?s in roles where Ada is ?s): Ada is ?r",
        "some ?r in roles: count (?s in (roles except ?r) where Ben is ?s) >= 1",
        "count (roles is (?r in roles where Ada is ?r)) = 1",
        "Ada is (?r in roles where Ben is ?r)",
        "not Ada is (?r in roles where Ben is ?r)",
        "every people is (?r in roles where Ada is ?r)",
    ],
)
def test_role_comprehensions_match_reference(board, formula):
    board = replace(board, roles=[*board.roles, RoleSpec("guest", frozenset({0, 1, 2}))])
    _assert_compilation_matches_reference(board, formula)


def test_role_comprehensions_with_no_roles(board):
    board = replace(board, roles=[])
    _assert_compilation_matches_reference(
        board, "every ?r in (?s in roles where Ada is ?s): Ada is ?r"
    )
    _assert_compilation_matches_reference(board, "not Ada is roles")
