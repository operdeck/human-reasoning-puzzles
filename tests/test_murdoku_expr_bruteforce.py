import pytest

from csp.bruteforce.murdoku_expr import solutions
from csp.murdoku import Board, BoardObject, CellMark, RoleSpec, Square
from csp.murdoku_lang import parse_statement


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
