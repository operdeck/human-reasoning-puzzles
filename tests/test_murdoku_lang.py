import pytest

from csp.murdoku_lang import Token, tokenize


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
