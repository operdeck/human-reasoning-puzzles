from dataclasses import replace

import pytest

from csp.bruteforce import murdoku_expr
from csp.bruteforce.murdoku_expr import solutions
from csp.murdoku import Board, BoardObject, CellMark, RoleSpec, Square
from csp.murdoku_declarations import statements as declaration_statements
from csp.murdoku_eval import grounded_dependencies, holds_grounded
from csp.murdoku_lang import holds, parse_statement


def _board(*, blocked=False, roles=False, marked=False, one_area=False):
    return Board(
        size=2,
        regions=[["a", "a"], ["a", "a"] if one_area else ["b", "b"]],
        region_names={"a": "room"} if one_area else {"a": "north", "b": "south"},
        objects=[BoardObject("rock", "blocking", (Square(0, 0),))] if blocked else [],
        people=["Ada", "Ben"],
        marks=[CellMark("quiet", (Square(0, 0),), "alone")] if marked else [],
        roles=[RoleSpec("guard", frozenset({1}))] if roles else [],
    )


def test_search_returns_expected_placements():
    board = _board()
    statements = [parse_statement("Ada in rows:1")]
    results = solutions(board, statements, limit=10)
    assert results == [
        {"Ada": Square(0, 0), "Ben": Square(1, 1)},
        {"Ada": Square(0, 1), "Ben": Square(1, 0)},
    ]


@pytest.mark.parametrize(
    "source",
    [
        "Ada in rows:1",
        "not Ada dir:areas Ben = 0",
        "Ada dir:up Ben",
        "Ada on rows:1,2",
        "Ada in (areas except area:north)",
        "no Ada in rows:1",
    ],
)
def test_grounded_pruning_matches_reference_for_every_completion(source):
    board = _board(roles=True)
    statement = parse_statement(source)
    dependencies = grounded_dependencies(board, statement)
    assert dependencies is not None
    for candidate in solutions(board, [], limit=20):
        complete = {person: candidate[person] for person in board.people}
        partial = {person: complete[person] for person in dependencies}
        roles = {
            (person, "guard"): candidate[board.role_variable(person, "guard")]
            for person in board.people
        }
        assert holds_grounded(statement, board, partial) == holds(statement, board, complete, roles)


@pytest.mark.parametrize(
    "source",
    [
        "Ada is role:guard",
        "Ada on role:guard",
        "Ada dir:nearest Ben",
        "Ada in empty rows",
        "count people in rows:1 = 1",
    ],
)
def test_non_groundable_formulas_are_never_pruned(source):
    board = _board(roles=True)
    statement = parse_statement(source)
    assert grounded_dependencies(board, statement) is None
    with pytest.raises(ValueError, match="not grounded"):
        holds_grounded(statement, board, {"Ada": Square(0, 0)})


def test_grounded_clue_prunes_before_enumerating_role_assignments(monkeypatch):
    board = _board(roles=True)
    called = []
    roles = murdoku_expr._roles

    def record(current_board, placed):
        called.append(dict(placed))
        return roles(current_board, placed)

    monkeypatch.setattr(murdoku_expr, "_roles", record)
    assert len(solutions(board, [parse_statement("Ada in rows:1")], limit=20)) == 4
    assert len(called) == 2
    assert all(placement["Ada"].row == 0 for placement in called)


def test_role_independent_aggregate_prunes_before_enumerating_roles(monkeypatch):
    board = _board(roles=True)
    called = []
    roles = murdoku_expr._roles

    def record(current_board, placed):
        called.append(dict(placed))
        return roles(current_board, placed)

    monkeypatch.setattr(murdoku_expr, "_roles", record)
    statement = parse_statement("count people in area:north = 0")
    assert grounded_dependencies(board, statement) is None
    assert solutions(board, [statement], limit=20) == []
    assert not called


def test_bound_role_entities_are_evaluated_after_role_assignments():
    board = _board(roles=True)
    statement = parse_statement("every ?r in roles: Ada is ?r")
    results = solutions(board, [statement], limit=20)
    assert len(results) == 4
    assert all(result["Ada has role guard"] is True for result in results)


def test_search_enumerates_roles_and_uses_role_membership():
    board = _board(roles=True)
    assert len(solutions(board, [], limit=10)) == 8
    results = solutions(board, [parse_statement("Ada is role:guard")], limit=10)
    assert len(results) == 4
    assert all(result["Ada has role guard"] is True for result in results)
    assert all(result["Ben has role guard"] is False for result in results)


def test_blocked_cell_and_free_empty_count():
    board = _board(blocked=True)
    statements = [
        parse_statement("count empty cells = 2"),
        parse_statement("count empty free cells = 1"),
    ]
    results = solutions(board, statements, limit=10)
    assert len(results) == 2
    assert all(Square(0, 0) not in result.values() for result in results)


def test_mark_occupant_declaration_is_not_ignored():
    board = _board(marked=True, one_area=True)
    results = solutions(board, [], limit=10)
    assert len(results) == 2
    assert all(Square(0, 0) not in result.values() for result in results)


def test_legacy_board_rules_are_not_silently_ignored():
    board = _board()
    board.rules = [("in", ["Ada", "area:north"])]
    with pytest.raises(ValueError, match="board rules must be migrated"):
        solutions(board, [])


@pytest.mark.parametrize(
    ("declared_role", "formulas"),
    [
        (RoleSpec("guard", frozenset({1})), ["count role:guard = 1"]),
        (
            RoleSpec("guard", frozenset({0, 2})),
            ["count role:guard = 0 or count role:guard = 2"],
        ),
        (
            RoleSpec("guard", frozenset({2}), different_regions=True),
            [
                "count role:guard = 2",
                "every ?p, ?q in role:guard: ?p dir:areas ?q >= 1",
            ],
        ),
        (
            RoleSpec("guard", frozenset({1}), eligible_people=frozenset({"Ada", "Ben"})),
            ["count role:guard = 1", "every role:guard is attribute:eligible"],
        ),
        (
            RoleSpec("guard", frozenset(range(4)), eligible_people=frozenset()),
            ["no role:guard is people"],
        ),
    ],
)
def test_role_declarations_match_explicit_statements(declared_role, formulas):
    base = Board(
        size=3,
        regions=[["a", "a", "a"], ["a", "b", "b"], ["a", "b", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[],
        people=["Ada", "Ben", "Cleo"],
        attributes={"eligible": frozenset({"Ada", "Ben"})},
    )
    declared = replace(base, roles=[declared_role])
    unrestricted = replace(base, roles=[RoleSpec("guard", frozenset(range(4)))])

    def all_solutions(board, statements):
        return {tuple(sorted(result.items())) for result in solutions(board, statements, limit=500)}

    expected = all_solutions(declared, [])
    actual = all_solutions(unrestricted, [parse_statement(text) for text in formulas])
    assert expected
    assert actual == expected
    assert all_solutions(unrestricted, declaration_statements(declared)) == expected


@pytest.mark.parametrize(
    ("condition", "comparison"),
    [("alone", "= 1"), ("not_alone", ">= 2")],
)
def test_mark_declarations_match_explicit_statements(condition, comparison):
    base = Board(
        size=2,
        regions=[["a", "a"], ["a", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[],
        people=["Ada", "Ben"],
    )
    cells = (Square(0, 0), Square(1, 1))
    declared = replace(base, marks=[CellMark("quiet", cells, condition)])
    unrestricted = replace(base, marks=[CellMark("quiet", cells)])
    statement = parse_statement(
        f"every ?p in (people on mark:quiet): count (people in area of ?p) {comparison}"
    )
    expected = {tuple(sorted(result.items())) for result in solutions(declared, [], limit=10)}
    actual = {
        tuple(sorted(result.items())) for result in solutions(unrestricted, [statement], limit=10)
    }
    assert expected
    assert actual == expected
    expanded = {
        tuple(sorted(result.items()))
        for result in solutions(unrestricted, declaration_statements(declared), limit=10)
    }
    assert expanded == expected


def test_single_person_not_alone_mark_can_be_left_empty():
    board = Board(
        size=2,
        regions=[["a", "a"], ["a", "a"]],
        region_names={"a": "hall"},
        objects=[],
        people=["Ada"],
        marks=[CellMark("social", (Square(0, 0),), "not_alone")],
    )
    results = solutions(board, [], limit=10)
    assert len(results) == 3
    assert all(result["Ada"] != Square(0, 0) for result in results)


@pytest.mark.parametrize(
    ("ada_cells", "ben_cells", "cards", "expected"),
    [
        (
            (Square(0, 0),),
            (Square(1, 1), Square(2, 1)),
            ("Ada dir:up empty rows = 1",),
            {"Ada": Square(0, 0), "Ben": Square(2, 1)},
        ),
        (
            (Square(0, 0),),
            (Square(1, 1), Square(2, 1)),
            (
                "Ada on object:bed",
                "every ?b in object:bed: Ada on ?b or ?b in empty rows",
            ),
            {"Ada": Square(0, 0), "Ben": Square(1, 1)},
        ),
        (
            (Square(1, 0),),
            (Square(0, 1), Square(0, 2)),
            ("some (people beside object:chest) dir:up Ada = 1",),
            {"Ada": Square(1, 0), "Ben": Square(0, 2)},
        ),
        (
            (Square(0, 0), Square(1, 0)),
            (Square(0, 1), Square(1, 1), Square(2, 1)),
            ("Ada in rows:1,last", "count people in rows:1,last = 1"),
            {"Ada": Square(0, 0), "Ben": Square(1, 1)},
        ),
    ],
)
def test_original_card_examples_are_necessary_for_uniqueness(ada_cells, ben_cells, cards, expected):
    board = Board(
        size=3,
        regions=[["a"] * 3 for _ in range(3)],
        region_names={"a": "hall"},
        objects=[
            BoardObject("bed", "standable", (Square(0, 0),)),
            BoardObject("bed", "standable", (Square(2, 2),)),
            BoardObject("chest", "standable", (Square(0, 1),)),
        ],
        people=["Ada", "Ben"],
        marks=[CellMark("ada", ada_cells), CellMark("ben", ben_cells)],
    )
    givens = [parse_statement("Ada on mark:ada"), parse_statement("Ben on mark:ben")]
    assert len(solutions(board, givens, limit=10)) > 1
    parsed = [parse_statement(card) for card in cards]
    assert solutions(board, givens + parsed, limit=10) == [expected]
    if cards[0] == "Ada in rows:1,last":
        assert all(
            len(solutions(board, givens + parsed[:index] + parsed[index + 1 :], limit=10)) > 1
            for index in range(len(parsed))
        )
