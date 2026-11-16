import pytest

from csp.murdoku_expression_file import _ast_key
from csp.murdoku_lang import (
    AdjectiveAtom,
    AdjectiveFilter,
    Arithmetic,
    Atom,
    Binary,
    Choice,
    Comprehension,
    Count,
    Difference,
    Filter,
    Measure,
    Name,
    Negation,
    NumberComparison,
    NumberRange,
    Parity,
    Projection,
    Qualified,
    Quantified,
    SetComparison,
    Token,
    Union,
    format_statement,
    parse_formula,
    parse_operand,
    parse_statement,
)


@pytest.mark.parametrize(
    "source",
    [
        "Ada in area:hall | Ada is in the hall.",
        "no (people except Ada) in area:water",
        "Ada dir:up+right object:plant <= 2",
        "Ada in rows:1,3-5",
        "some (people beside object:chest) dir:up Ada = 1",
        "every ?p, ?q in role:guard: ?p dir:areas ?q >= 1",
        "count (people in area of Ada) = count (people in area:hall) + 1",
        "count empty free cells odd",
        "count (occupied areas touches area:hall) 1..2",
        "(people on object:carpet) = Ada, Ben",
        "count (?p in people where ?p on object:bed) >= 1",
        "(people is role:guard) != (people is role:chef)",
        "exactly 1 of (Ada on object:bed; not Ben in area:hall)",
        "if Ada in area:hall then (Ben in rows:1 or Ben in rows:3)",
        "every ?r in rows: ?r is empty or ?r is occupied",
        "(every ?r in rows: ?r is empty) and Ada in area:hall",
        "exactly 1 of (every ?r in rows: ?r is empty; Ada in area:hall)",
    ],
)
def test_format_statement_round_trips_structure_and_wording(source):
    statement = parse_statement(source)
    parsed = parse_statement(format_statement(statement))
    assert _ast_key(parsed.formula) == _ast_key(statement.formula)
    assert parsed.wording == statement.wording


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


def test_parse_formula_respects_boolean_precedence():
    result = parse_formula("Ada in area:x or Ben in area:y and not Cleo on mark:z")
    assert isinstance(result, Binary) and result.operator.text == "or"
    assert isinstance(result.right, Binary) and result.right.operator.text == "and"
    assert isinstance(result.right.right, Negation)
    assert isinstance(result.right.right.formula, Atom)


def test_parentheses_and_implication():
    result = parse_formula("if (Ada in area:x or Ben in area:y) then not Cleo in area:z")
    assert isinstance(result, Binary) and result.operator.text == "if"
    assert isinstance(result.left, Binary) and result.left.operator.text == "or"
    assert isinstance(result.right, Negation)


def test_parse_determined_direction_with_filter_and_measure():
    result = parse_formula("some (people beside object:chest) dir:up Ada = 1")
    assert isinstance(result, Atom)
    assert result.determiner == Token("some", 1, 1)
    assert isinstance(result.subject, Filter)
    assert result.operator.text == "dir:up"
    assert result.measure == Measure(Token("=", 1, 46), Token("1", 1, 48))


def test_parse_set_comparison():
    result = parse_formula("(people in area:changing) = Ada, Ben")
    assert isinstance(result, SetComparison)
    assert isinstance(result.left, Filter)
    assert isinstance(result.right, Union)


def test_count_comparison_uses_filter_and_arithmetic():
    result = parse_formula("count people in area:x = 1 + 2")
    assert isinstance(result, NumberComparison)
    assert isinstance(result.left, Count) and isinstance(result.left.operand, Filter)
    assert isinstance(result.right, Arithmetic) and result.right.operator.text == "+"


def test_count_comparison_between_scopes():
    result = parse_formula("count (people in area:a) > count (people in area:b)")
    assert isinstance(result, NumberComparison)
    assert isinstance(result.left, Count) and isinstance(result.right, Count)
    assert result.operator.text == ">"


@pytest.mark.parametrize(
    ("clue", "kind"),
    [
        ("count empty areas odd", Parity),
        ("count rows 1..3", NumberRange),
    ],
)
def test_count_parity_and_range(clue, kind):
    assert isinstance(parse_formula(clue), kind)


def test_count_direction_filter_keeps_its_measure():
    result = parse_formula("count (people dir:up Ada = 1) = 2")
    assert isinstance(result, NumberComparison) and isinstance(result.left, Count)
    assert isinstance(result.left.operand, Filter) and result.left.operand.measure is not None


def test_quantifier_body_extends_over_conjunction():
    result = parse_formula(
        "no ?r in empty rows: some occupied rows dir:up ?r and some occupied rows dir:down ?r"
    )
    assert isinstance(result, Quantified)
    assert [variable.text for variable in result.variables] == ["?r"]
    assert isinstance(result.body, Binary) and result.body.operator.text == "and"


def test_quantified_distinct_variable_declarations_are_preserved():
    result = parse_formula("every ?p, ?q in role:guard: ?p dir:areas ?q >= 1")
    assert isinstance(result, Quantified)
    assert [variable.text for variable in result.variables] == ["?p", "?q"]
    assert isinstance(result.body, Atom)


def test_quantifier_on_right_of_conjunction():
    result = parse_formula("Ada in area:x and every ?p in people: ?p in area:y")
    assert isinstance(result, Binary)
    assert isinstance(result.right, Quantified)


def test_quantifier_body_extends_over_lower_precedence_operators():
    result = parse_formula(
        "P on object:bed and every ?b in object:bed: P on ?b or ?b in empty rows"
    )
    assert isinstance(result, Binary) and result.operator.text == "and"
    assert isinstance(result.right, Quantified)
    assert isinstance(result.right.body, Binary) and result.right.body.operator.text == "or"


def test_parentheses_end_quantifier_scope():
    result = parse_formula("(every ?b in object:bed: P on ?b) or P in area:x")
    assert isinstance(result, Binary) and result.operator.text == "or"
    assert isinstance(result.left, Quantified)
    assert isinstance(result.left.body, Atom)


def test_choice_and_bounded_quantifier():
    choice = parse_formula("exactly 1 of (Ada in area:x; Ben in area:y)")
    assert isinstance(choice, Choice) and len(choice.choices) == 2
    result = parse_formula("at most 1 ?r in roles: Ada is ?r")
    assert isinstance(result, Quantified)
    assert result.quantifier.text == "at most" and result.count is not None
    assert result.count.text == "1"


def test_comprehension_carries_variable_and_condition():
    result = parse_operand("(?p in people where ?p on object:chair)")
    assert isinstance(result, Comprehension)
    assert result.variable.text == "?p" and isinstance(result.condition, Atom)


@pytest.mark.parametrize(
    ("formula", "message"),
    [
        ("Ada in ?room", "unbound variable '\\?room'"),
        ("every ?p in ?p: ?p in area:x", "unbound variable '\\?p'"),
        ("every ?p, ?p in people: ?p in area:x", "clashes with an existing binding"),
        ("every ?p in people: Ada in area:x", "unused variable '\\?p'"),
        (
            "every ?p in people: some ?p in people: ?p in area:x",
            "clashes with an existing binding",
        ),
    ],
)
def test_variable_bindings_reject_unbound_clashing_and_unused_names(formula, message):
    with pytest.raises(ValueError, match=message):
        parse_formula(formula)


def test_nested_quantifiers_can_use_outer_variables_in_their_source():
    result = parse_formula("every ?p in people: some ?a in area of ?p: ?p in ?a")
    assert isinstance(result, Quantified) and isinstance(result.body, Quantified)


def test_sibling_quantifiers_can_reuse_a_variable_name():
    result = parse_formula(
        "(some ?p in people: ?p in area:x) and (some ?p in people: ?p in area:y)"
    )
    assert isinstance(result, Binary)


def test_adjective_after_is_is_not_an_entity_name():
    result = parse_formula("rows:last is empty")
    assert isinstance(result, AdjectiveAtom) and result.adjective.text == "empty"
    filtered = parse_operand("(rows is empty)")
    assert isinstance(filtered, AdjectiveFilter) and filtered.adjective.text == "empty"


def test_keyword_prefixes_and_namespaced_keywords_remain_names():
    assert isinstance(parse_operand("somebody"), Name)
    assert isinstance(parse_operand("area:empty"), Name)
    with pytest.raises(ValueError):
        parse_operand("empty")


@pytest.mark.parametrize(
    "formula",
    [
        "P dir:up empty rows = 1",
        "P on object:bed and every ?b in object:bed: P on ?b or ?b in empty rows",
        "some (people beside object:chest) dir:up P = 1",
        "P in rows:1,last and count people in rows:1,last = 1",
    ],
)
def test_previously_inexpressible_clue_shapes_parse(formula):
    assert parse_formula(formula)


def test_formula_source_error_uses_requested_line():
    with pytest.raises(ValueError, match=r"line 7, column \d+: unexpected"):
        parse_formula("Ada in @", line=7)


@pytest.mark.parametrize(
    ("source", "replacement"),
    [
        ("in Ada area:hall", "P in X"),
        ("not_in Ada area:hall", "not P in X"),
        ("Ada is not Ben", "not P is X"),
        ("not has Ada role:guard", "P is role:x"),
        ("if has Ada role:guard then in Ada area:hall", "P is role:x"),
        ("subset role:guard role:chef", "every role:a is role:b"),
        ("count roles of Ada <= 1", "at most N"),
        ("count people with role:guard = 1", "count role:x"),
        ("count people in area:hall with role:guard >= 1", "count (role:y in X)"),
        ("count people from people:Ada,Ben with attribute:t = 1", "count (A, B is attribute:t)"),
        ("alone Ada", "count"),
        ("only Ada on object:bed", "people on X"),
        ("dir Ada Ben up = 1", "P dir:mode X"),
        ("no_adjacent_occupied areas", "occupied areas touches"),
        ("most_populated area:hall", "count comparisons"),
        ("least_populated area:hall", "area of free cells"),
        ("for each area in tag:hall, count people in that area = 1", "every ?a"),
        ("with role:guard in area:hall", "some role:y"),
        ("with Ada in same area exactly 1", "N + 1"),
        ("exactly 1 in Ada area:hall ; in Ben area:hall", "exactly N of"),
    ],
)
def test_removed_legacy_forms_suggest_replacements(source, replacement):
    with pytest.raises(ValueError) as error:
        parse_formula(source, line=7)
    assert "line 7, column " in str(error.value)
    assert "legacy form is removed" in str(error.value)
    assert replacement in str(error.value)


def test_statement_keeps_optional_wording_separate_from_formula():
    statement = parse_statement("Ada in area:hall | Ada is in the hall.")
    assert isinstance(statement.formula, Atom)
    assert statement.wording == "Ada is in the hall."
    assert parse_statement("Ada in area:hall").wording is None


@pytest.mark.parametrize(
    "source",
    ["Ada and Ben", "(Ada, Ben", "rows:1,3-x", "Ada except", "(Ada dir:up Ben = -1)"],
)
def test_parse_operand_rejects_malformed_input_with_location(source):
    with pytest.raises(ValueError, match=r"line 1, column \d+: unexpected"):
        parse_operand(source)
