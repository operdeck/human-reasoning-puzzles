import pytest

from csp.murdoku import Board, BoardObject, CellMark, RoleSpec, Square
from csp.murdoku_lang import parse_formula, parse_operand
from csp.murdoku_typecheck import Shape, Sort, check_formula, infer_operand


@pytest.fixture
def board():
    return Board(
        size=3,
        regions=[["a", "a", "b"], ["a", "a", "b"], ["a", "b", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[
            BoardObject("bed", "standable", (Square(0, 0),)),
            BoardObject("bed", "standable", (Square(1, 1),)),
        ],
        people=["Ada", "Ben"],
        area_tags={"outside": ["garden"]},
        marks=[CellMark("red", (Square(0, 0),)), CellMark("blue", (Square(1, 1),))],
        roles=[RoleSpec("guard", frozenset({1})), RoleSpec("guest", frozenset({0, 2}))],
        attributes={"trained": frozenset({"Ada"})},
    )


def test_infer_shorthand_unions_and_repeat_instances(board):
    assert infer_operand(board, parse_operand("object:bed")).maximum == 2
    assert infer_operand(board, parse_operand("mark:red,blue")) == Shape(Sort.FEATURE, 2, 1)
    assert infer_operand(board, parse_operand("rows:1,3-3")) == Shape(Sort.ROW, 2, 1)


@pytest.mark.parametrize(
    ("formula", "message"),
    [
        ("Ada in area:unknown", "unknown area"),
        ("Ada in thing:hall", "unknown namespace"),
        ("(area:hall, Ada) = area:hall", "mixed sorts"),
        ("role:guest in area:hall", "needs a determiner"),
        ("Ada in rows:4", "must be between"),
        ("Ada is area:hall", "mixed sorts"),
        ("area:hall dir:nearest Ada", "requires a person"),
        ("Ada dir:side Ben", "unknown direction mode"),
        ("Ada dir:knight Ben = 1", "does not take a measure"),
        ("Ada dir:rows Ben", "requires a measure"),
        ("Ada dir:up Ben = 0", "no feasible value"),
        ("Ada is empty", "cannot qualify person"),
        ("count people = 3", "no feasible value"),
        ("count role:guard = 0", "no feasible value"),
    ],
)
def test_typecheck_reports_errors(board, formula, message):
    with pytest.raises(ValueError, match=message):
        check_formula(board, parse_formula(formula))


@pytest.mark.parametrize(
    "formula",
    [
        "Ada in area:hall",
        "role:guard in area:hall",
        "some role:guest in area:hall",
        "no (people except Ada) in area:garden",
        "count people on mark:red,blue = 2",
        "every ?p, ?q in role:guest: ?p dir:areas ?q >= 1",
        "at most 1 ?r in roles: Ada is ?r",
        "no ?r in roles: Ada is ?r",
        "some ?r in roles: not Ada is ?r",
    ],
)
def test_typecheck_accepts_well_typed_formulas(board, formula):
    check_formula(board, parse_formula(formula))
