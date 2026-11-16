import pytest

from csp.murdoku_lang import (
    Difference,
    Name,
    Projection,
    Qualified,
    Token,
    Union,
    parse_operand,
    tokenize,
)


def test_tokenize_quantifier_and_namespaces():
    assert tokenize("every ?a in tag:crime_scene: ?a touches area:river") == (
        Token("every", 1, 1),
        Token("?a", 1, 7),
        Token("in", 1, 10),
        Token("tag:crime_scene", 1, 13),
        Token(":", 1, 28),
        Token("?a", 1, 30),
        Token("touches", 1, 33),
        Token("area:river", 1, 41),
    )


def test_tokenize_operators_unions_and_ranges():
    assert [token.text for token in tokenize("count rows:1,3-5 >= 1..3")] == [
        "count",
        "rows:1",
        ",",
        "3",
        "-",
        "5",
        ">=",
        "1",
        "..",
        "3",
    ]


def test_tokenize_compound_direction_and_locations():
    tokens = tokenize("Ada dir:up+right Ben\n  != 2", line=4)
    assert [token.text for token in tokens] == ["Ada", "dir:up", "+", "right", "Ben", "!=", "2"]
    assert tokens[-2] == Token("!=", 5, 3)


def test_tokenize_non_ascii_identifiers():
    assert [token.text for token in tokenize("Éva in area:Velázquez_room")] == [
        "Éva",
        "in",
        "area:Velázquez_room",
    ]


def test_tokenize_reports_invalid_character_location():
    with pytest.raises(ValueError, match=r"line 2, column 2: unexpected character '@'"):
        tokenize("Ada\n @")


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


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("Ada and Ben", "line 1, column 5: unexpected token 'and'"),
        ("(Ada, Ben", "line 1, column 10: expected '\\)'"),
        ("rows:1,3-x", "line 1, column 10: expected a number"),
        ("Ada except", "line 1, column 11: expected an operand"),
    ],
)
def test_parse_operand_reports_location(source, message):
    with pytest.raises(ValueError, match=message):
        parse_operand(source)
