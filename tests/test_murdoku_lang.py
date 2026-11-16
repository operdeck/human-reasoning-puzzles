import pytest

from csp.murdoku_lang import (
    Difference,
    Filter,
    Measure,
    Name,
    Projection,
    Qualified,
    Token,
    Union,
    parse_operand,
)


def test_parse_set_operations_preserves_structure_and_positions():
    assert parse_operand("(Ada, Ben) except role:guard", line=4) == Difference(
        Union((Name(Token("Ada", 4, 2)), Name(Token("Ben", 4, 7)))),
        Name(Token("role:guard", 4, 19)),
    )


def test_parse_projection_and_qualifier():
    assert parse_operand("area of free cells") == Projection(
        Token("area", 1, 1),
        Qualified(Token("free", 1, 9), Name(Token("cells", 1, 14))),
    )


def test_parse_union_keeps_shorthand_unresolved():
    assert parse_operand("rows:1,3-5") == Union(
        (Name(Token("rows:1", 1, 1)), Name(Token("3-5", 1, 8)))
    )
    assert parse_operand("object:bed, Ada") == Union(
        (Name(Token("object:bed", 1, 1)), Name(Token("Ada", 1, 13)))
    )


def test_parse_filters_and_nested_difference():
    assert parse_operand("((occupied areas touches tag:square) except tag:square)") == Difference(
        Filter(
            Qualified(Token("occupied", 1, 3), Name(Token("areas", 1, 12))),
            Token("touches", 1, 18),
            Name(Token("tag:square", 1, 26)),
        ),
        Name(Token("tag:square", 1, 45)),
    )


def test_parse_directional_filter_preserves_mode_and_measure():
    assert parse_operand("(people dir:up+right Ada <= 2)") == Filter(
        Name(Token("people", 1, 2)),
        Token("dir:up+right", 1, 9),
        Name(Token("Ada", 1, 22)),
        Measure(Token("<=", 1, 26), Token("2", 1, 29)),
    )


def test_parse_non_ascii_identifiers():
    assert parse_operand("Éva, area:Velázquez_room") == Union(
        (Name(Token("Éva", 1, 1)), Name(Token("area:Velázquez_room", 1, 6)))
    )


@pytest.mark.parametrize(
    "source",
    ["Ada and Ben", "(Ada, Ben", "rows:1,3-x", "Ada except", "(Ada dir:up Ben = -1)"],
)
def test_parse_operand_rejects_malformed_input_with_location(source):
    with pytest.raises(ValueError, match=r"line 1, column \d+: unexpected"):
        parse_operand(source)
