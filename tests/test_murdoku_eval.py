import pytest

from csp.murdoku import Board, BoardObject, CellMark, RoleSpec, Square
from csp.murdoku_lang import holds, parse_statement


@pytest.fixture
def case():
    board = Board(
        size=3,
        regions=[["a", "a", "b"], ["a", "a", "b"], ["a", "a", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[
            BoardObject("bed", "standable", (Square(0, 0), Square(0, 1))),
            BoardObject("rock", "blocking", (Square(2, 1),)),
        ],
        people=["Ada", "Ben"],
        area_tags={"outside": ["garden"]},
        marks=[
            CellMark("red", (Square(0, 0),)),
            CellMark("blue", (Square(2, 2),)),
            CellMark("rock", (Square(2, 1),)),
            CellMark("same", (Square(0, 0),)),
        ],
        roles=[RoleSpec("guard", frozenset({1})), RoleSpec("guest", frozenset({0, 2}))],
    )
    placed = {"Ada": Square(0, 0), "Ben": Square(2, 2)}
    roles = {
        ("Ada", "guard"): True,
        ("Ben", "guard"): False,
        ("Ada", "guest"): False,
        ("Ben", "guest"): False,
    }
    return board, placed, roles


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("object:bed in rows:1", True),
        ("object:bed in columns:1", False),
        ("object:bed on columns:1", True),
        ("area:hall in area:hall", True),
        ("area:hall on area:hall", True),
        ("count (areas in tag:outside) = 1", True),
        ("Ada on mark:red", True),
        ("Ada on Ada", True),
        ("mark:red on mark:same", True),
        ("mark:red dir:rows mark:same = 0", True),
        ("mark:red dir:rows mark:red = 0", False),
        ("mark:red touches mark:red", False),
        ("Ada dir:areas Ada = 0", False),
        ("Ben touches mark:rock", True),
        ("Ben beside mark:rock", False),
        ("count people on mark:red,blue = 2", True),
        ("count people on mark:red,blue = 1", False),
        ("count empty cells = 7", True),
        ("count (empty free cells) = 6", True),
        ("count (empty cells in mark:rock) = 1", True),
        ("count (empty free cells in mark:rock) = 0", True),
        ("Ada dir:up Ben = 2", True),
        ("Ada dir:up+left Ben = 2", True),
        ("Ada dir:diagonal Ben = 2", True),
        ("Ada dir:manhattan Ben = 4", True),
        ("Ada dir:king Ben = 2", True),
        ("Ada dir:euclidean Ben <= 2", False),
        ("Ada dir:euclidean Ben <= 3", True),
        ("Ada dir:areas Ben = 1", True),
        ("Ada dir:knight Ben", False),
        ("some ?p, ?q in people: ?p dir:up ?q = 2", True),
        ("some ?r in roles: Ada is ?r", True),
        ("no ?r in roles: Ben is ?r", True),
        ("some ?r in roles: not Ada is ?r", True),
        ("at most 1 ?r in roles: Ada is ?r", True),
    ],
)
def test_reference_semantics(case, formula, expected):
    board, placed, roles = case
    assert holds(parse_statement(formula), board, placed, roles) is expected


def test_zero_roles_and_role_quantification(case):
    board, placed, _ = case
    board.roles.clear()
    assert holds(parse_statement("no ?r in roles: Ada is ?r"), board, placed, {})
    assert not holds(parse_statement("some ?r in roles: Ada is ?r"), board, placed, {})


def test_multiple_roles_are_counted_independently(case):
    board, placed, roles = case
    roles[("Ada", "guest")] = True
    roles[("Ben", "guest")] = True
    assert holds(parse_statement("exactly 2 ?r in roles: Ada is ?r"), board, placed, roles)
    assert not holds(parse_statement("no ?r in roles: Ada is ?r"), board, placed, roles)


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("Ada dir:furthest mark:centre", True),
        ("Ben dir:nearest mark:centre", False),
        ("Ben dir:nearest:rows mark:centre", True),
        ("Cleo dir:nearest:cols mark:centre", True),
        ("Ada dir:nearest:king mark:centre", False),
        ("Ada dir:furthest:euclidean mark:centre", True),
        ("Ada dir:nearest:areas mark:centre", True),
        ("Ben dir:furthest:areas mark:centre", False),
    ],
)
def test_superlative_metrics_and_ties(formula, expected):
    board = Board(
        size=3,
        regions=[["a", "a", "b"], ["a", "a", "b"], ["a", "b", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[],
        people=["Ada", "Ben", "Cleo"],
        marks=[CellMark("centre", (Square(1, 1),))],
    )
    placed = {"Ada": Square(0, 0), "Ben": Square(1, 2), "Cleo": Square(2, 1)}
    assert holds(parse_statement(formula), board, placed, {}) is expected


def test_reference_requires_complete_role_assignments(case):
    board, placed, _ = case
    with pytest.raises(ValueError, match="role assignments must contain"):
        holds(parse_statement("Ada in area:hall"), board, placed, {})
