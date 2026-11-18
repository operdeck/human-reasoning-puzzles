import pytest

from csp import clue_search
from csp.bruteforce import murdoku_expr
from csp.core import Contradiction, Solver
from csp.murdoku import Square
from csp.murdoku_expression_file import (
    keyed_expression_clue_numbers,
    load_expression_board,
)
from csp.murdoku_lang import (
    Atom,
    Count,
    Negation,
    NumberComparison,
    Quantified,
    format_statement,
    holds,
    parse_statement,
)
from csp.murdoku_lower import compile_statements


def accepts(text, placement):
    board, rules, clues = load_expression_board(text)
    return murdoku_expr.accepts(board, clues, placement, rules=rules)


def solutions(text, limit=2):
    board, rules, clues = load_expression_board(text)
    return murdoku_expr.solutions(board, clues, limit, rules=rules)


@pytest.mark.parametrize(
    "expression,formula_type",
    [
        ("not (Ada touches mark:water)", Negation),
        ("every ?a in tag:villages: count (role:guard in ?a) >= 2", Quantified),
        ("every ?a in occupied areas: no occupied areas touches ?a", Quantified),
        ("not (Ada dir:left Ben)", Negation),
        ("Ada is role:guard", Atom),
        ("not Ada is attribute:trained", Negation),
        ("every role:guard is attribute:trained", Atom),
    ],
)
def test_canonical_clue_parser_reads_negation_and_compound_predicates(expression, formula_type):
    statement = parse_statement(expression + " | wording")
    assert isinstance(statement.formula, formula_type)
    assert statement.wording == "wording"
    assert format_statement(parse_statement(format_statement(statement))) == format_statement(
        statement
    )


def test_legacy_murdoku_clues_are_rejected_in_files():
    text = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
in_region Ada room
"""
    with pytest.raises(ValueError, match="line 9, column"):
        load_expression_board(text)


@pytest.mark.parametrize(
    "clue",
    [
        "for_each_area in tag:villages, count people in that area = 1",
        "has_role Ada guard",
        "not_role Ada guard",
        "has_attribute Ada trained",
        "not_attribute Ada trained",
        "not_in Ada area:room",
        "not_on Ada object:bench",
        "not_beside Ada object:bench",
        "not_touches Ada mark:water",
        "not_dir Ada Ben left",
        "role_subset role:guard attribute:trained",
    ],
)
def test_internal_spellings_are_not_accepted_as_clue_syntax(clue):
    with pytest.raises(ValueError, match="line 1, column"):
        parse_statement(clue)


def test_internal_spellings_are_rejected_inside_exactly():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Clues:
exactly 1 not_dir Ada Ben left ; dir Ada Ben right
"""
    with pytest.raises(ValueError, match="line 11, column"):
        load_expression_board(text)


def test_person_selector_uses_bare_names():
    text = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
person:Ada dir:left Ada
"""
    with pytest.raises(ValueError, match="unknown namespace 'person'"):
        load_expression_board(text)


@pytest.mark.parametrize("clue", ["same Ada Ben", "not same Ada Ben"])
def test_same_area_predicates_use_dir_area_distance(clue):
    with pytest.raises(ValueError):
        parse_statement(clue)
    assert isinstance(parse_statement("Ada dir:areas Ben = 0").formula, Atom)
    assert isinstance(parse_statement("Ada dir:areas Ben >= 1").formula, Atom)


def test_area_distance_relations_distinguish_same_and_different_areas():
    template = """Size: 3
Regions:
a: Alpha
b: Bravo
c: Charlie
Grid:
a b c
c a b
b c a
People:
Ada
Ben
Clues:
{clue}
"""
    together = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    apart = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    same = template.format(clue="Ada dir:areas Ben = 0")
    different = template.format(clue="Ada dir:areas Ben >= 1")
    assert accepts(same, together)
    assert not accepts(same, apart)
    assert accepts(different, apart)
    assert not accepts(different, together)


def test_legacy_selector_aliases_are_rejected():
    text = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
Ada in row:1
"""
    with pytest.raises(ValueError, match="unknown namespace 'row'"):
        load_expression_board(text)


def test_canonical_location_predicates_and_only_match_selected_cells():
    base = """Size: 3
Regions:
a: west
b: east
Grid:
a b b
a b b
a b b
Marks:
water: r2c2
Attributes:
trained: Ada
People:
Ada
Ben
Clues:
{clue}
"""
    west = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    across = {"Ada": Square(1, 0), "Ben": Square(0, 2)}
    assert accepts(base.format(clue="Ada in area:west"), west)
    assert not accepts(base.format(clue="Ada in area:east"), west)
    assert accepts(base.format(clue="Ada is attribute:trained"), west)
    assert not accepts(base.format(clue="not Ada is attribute:trained"), west)
    assert accepts(
        base.format(clue="Ada on mark:water"),
        {"Ada": Square(1, 1), "Ben": Square(0, 2)},
    )
    assert not accepts(base.format(clue="Ada beside mark:water"), across)
    assert accepts(base.format(clue="Ada touches mark:water"), across)
    assert accepts(base.format(clue="not (Ada touches mark:water)"), west)
    assert accepts(
        base.format(clue="exactly 1 of (Ada in area:west; Ben on mark:water)"),
        west,
    )
    assert not accepts(
        base.format(clue="exactly 1 of (Ada in area:west; Ben on mark:water)"),
        {"Ada": Square(0, 0), "Ben": Square(1, 1)},
    )
    assert accepts(
        base.format(clue="(people on mark:water) = Ada"),
        {"Ada": Square(1, 1), "Ben": Square(0, 2)},
    )
    assert not accepts(base.format(clue="(people on mark:water) = Ada"), west)

    text = base.format(clue="Ada touches mark:water")
    board, rules, clues = load_expression_board(text)
    compiled = compile_statements(board, clues, rules=rules)
    for person, square in across.items():
        compiled.assign(compiled.literal(person, square), "test", "fixed")
    assert Solver(compiled).solve().contradiction is None
    assert holds(clues[0], board, across, {})


def test_exactly_counts_canonical_location_and_direction_predicates():
    base = """Size: 3
Regions:
a: west
b: east
Grid:
a b b
a b b
a b b
People:
Ada
Ben
Clues:
{clue}
"""
    exactly_one = "exactly 1 of (Ada in area:west; Ada dir:right Ben)"
    assert accepts(
        base.format(clue=exactly_one),
        {"Ada": Square(0, 2), "Ben": Square(1, 0)},
    )
    both_true = "exactly 1 of (Ada in area:west; Ada dir:left Ben)"
    assert not accepts(
        base.format(clue=both_true),
        {"Ada": Square(0, 0), "Ben": Square(1, 2)},
    )

    negated = base.replace("Size: 3", "Size: 4").replace(
        "Grid:\na b b\na b b\na b b",
        "Grid:\na b b b\na b b b\na b b b\na b b b",
    )
    one_negated_true = "exactly 1 of (not (Ada in area:west); not (Ada dir:left Ben))"
    assert accepts(
        negated.format(clue=one_negated_true),
        {"Ada": Square(0, 1), "Ben": Square(1, 3)},
    )
    both_negated_true = "exactly 1 of (not (Ada in area:west); not (Ada dir:left Ben))"
    assert not accepts(
        negated.format(clue=both_negated_true),
        {"Ada": Square(0, 3), "Ben": Square(1, 0)},
    )


def test_clue_search_only_generates_parseable_canonical_clues():
    from csp.murdoku_lang import format_statement, holds, parse_statement

    text = """Size: 3
Regions:
a: west
b: east
Grid:
a b b
a b b
a b b
People:
Ada
Ben
"""
    board, _rules, _ = load_expression_board(text)
    placement = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    candidates = clue_search.candidate_clues(board, placement)
    parsed = [parse_statement(clue) for clue in candidates]
    assert {format_statement(statement) for statement in parsed} == set(candidates)
    assert all(holds(statement, board, placement, {}) for statement in parsed)
    assert "Ada in area:west" in candidates
    assert "Ada dir:left Ben" in candidates
    assert "Ada dir:areas Ben >= 1" in candidates
    assert all(
        not clue.startswith(("in_region", "left_of", "same_region", "same ", "not same"))
        for clue in candidates
    )


def test_clue_search_suggests_same_area_as_zero_area_distance():
    text = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
People:
Ada
Ben
"""
    board, _rules, _ = load_expression_board(text)
    placement = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    candidates = clue_search.candidate_clues(board, placement)
    assert "Ada dir:areas Ben = 0" in candidates
    assert not any(clue.startswith(("same ", "not same ")) for clue in candidates)


def test_key_metadata_resolves_clue_and_rule_text_without_wording():
    text = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Rules:
count people in area:room = 1 | rule wording
Clues:
Ada in area:room | clue wording
Key:
rule: count people in area:room = 1
clue: Ada in area:room
"""
    assert keyed_expression_clue_numbers(text) == {1}
    load_expression_board(text)


def test_key_metadata_rejects_stale_and_duplicate_references():
    base = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
Ada in area:room
Key:
clue: Ada in area:wrong
"""
    with pytest.raises(ValueError, match="unresolved Key clue"):
        load_expression_board(base)
    with pytest.raises(ValueError, match="duplicate Key"):
        load_expression_board(
            base.replace(
                "clue: Ada in area:wrong",
                "clue: Ada in area:room\nclue: Ada in area:room",
            )
        )


def test_clue_search_preserves_keyed_clues_even_when_redundant():
    text = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
Ada in area:room
Key:
clue: Ada in area:room
"""
    assert clue_search.thin(text) == ["Ada in area:room"]
    report = clue_search.removal_report(text)
    assert report[0][2] == clue_search.outcome(text)


def test_dir_euclidean_uses_squared_integer_distance_in_both_solvers():
    text = """Size: 5
Regions:
a: room
Grid:
a a a a a
a a a a a
a a a a a
a a a a a
a a a a a
People:
Ada
Ben
Clues:
Ada dir:euclidean Ben = 5
"""
    board, rules, clues = load_expression_board(text)
    model = compile_statements(board, clues, rules=rules)
    assert model.relations
    valid = {"Ada": Square(0, 0), "Ben": Square(3, 4)}
    invalid = {"Ada": Square(0, 0), "Ben": Square(3, 3)}
    assert holds(clues[0], board, valid, {})
    assert not holds(clues[0], board, invalid, {})
    assert accepts(text, valid)
    assert not accepts(text, invalid)
    valid_model = compile_statements(board, clues, rules=rules)
    for person, square in valid.items():
        valid_model.assign(valid_model.literal(person, square), "test", "fixed")
    assert Solver(valid_model).solve().contradiction is None
    invalid_model = compile_statements(board, clues, rules=rules)
    for person, square in invalid.items():
        invalid_model.assign(invalid_model.literal(person, square), "test", "fixed")
    assert Solver(invalid_model).solve().contradiction is not None
    assert all(
        (solution["Ada"].row - solution["Ben"].row) ** 2
        + (solution["Ada"].col - solution["Ben"].col) ** 2
        == 25
        for solution in solutions(text, limit=10)
    )


def test_dir_negation_is_the_negation_of_the_existential_relation():
    text = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
People:
Ada
Ben
Clues:
not (Ada dir:left Ben)
"""
    board, rules, clues = load_expression_board(text)
    left = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    right = {"Ada": Square(0, 2), "Ben": Square(1, 0)}
    assert not holds(clues[0], board, left, {})
    assert holds(clues[0], board, right, {})
    assert not accepts(text, left)
    assert accepts(text, right)

    rejected_model = compile_statements(board, clues, rules=rules)
    for person, square in left.items():
        rejected_model.assign(rejected_model.literal(person, square), "test", "fixed")
    assert Solver(rejected_model).solve().contradiction is not None


def test_negated_distance_from_multiple_blocking_objects_is_universal():
    text = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
Objects:
tree: blocking r1c1
rock: blocking r1c2
People:
Ada
Clues:
not (Ada dir:king object:tree,rock <= 1)
"""
    board, rules, clues = load_expression_board(text)
    safe = {"Ada": Square(2, 2)}
    near_one_target = {"Ada": Square(1, 2)}
    assert accepts(text, safe)
    assert not accepts(text, near_one_target)

    safe_model = compile_statements(board, clues, rules=rules)
    safe_model.assign(safe_model.literal("Ada", safe["Ada"]), "test", "fixed")
    assert Solver(safe_model).solve().contradiction is None
    unsafe_model = compile_statements(board, clues, rules=rules)
    with pytest.raises(Contradiction, match="already ruled out"):
        unsafe_model.assign(unsafe_model.literal("Ada", near_one_target["Ada"]), "test", "fixed")


def test_adjacent_to_selectors_use_distinct_side_neighbor_areas():
    text = """Size: 3
Regions:
a: west
b: east
c: south
Grid:
a a b
a b b
c c c
AreaTags:
coast: west
People:
Ada
Clues:
Ada in ((areas touches area:west) except area:west)
"""
    board, _rules, clues = load_expression_board(text)
    assert not holds(clues[0], board, {"Ada": Square(0, 0)}, {})
    assert holds(clues[0], board, {"Ada": Square(0, 2)}, {})

    tagged = text.replace("area:west", "tag:coast")
    tagged_board, _tagged_rules, tagged_clues = load_expression_board(tagged)
    assert not holds(tagged_clues[0], tagged_board, {"Ada": Square(0, 0)}, {})


def test_occupied_area_counts_and_adjacent_people_counts_share_scope_semantics():
    text = """Size: 4
Regions:
a: west
b: east
c: south
d: north
Grid:
a b b b
b a c c
d d c c
d d c c
AreaTags:
coast: west
neighbors: east south north
People:
Ada
Ben
Cal
Clues:
count ((occupied areas touches area:west) except area:west) = 2
count (?a in tag:neighbors where ?a is occupied and ?a touches area:west) = 2
count (people in ((areas touches area:west) except area:west)) = 2
"""
    board, rules, clues = load_expression_board(text)
    placement = {
        "Ada": Square(0, 0),
        "Ben": Square(1, 2),
        "Cal": Square(2, 1),
    }
    assert all(holds(statement, board, placement, {}) for statement in clues)
    assert accepts(text, placement)
    model = compile_statements(board, clues, rules=rules)
    for person, square in placement.items():
        model.assign(model.literal(person, square), "test", "fixed")
    assert Solver(model).solve().contradiction is None

    wrong_count = text.replace("= 2", "= 1", 1)
    wrong_board, wrong_rules, wrong_clues = load_expression_board(wrong_count)
    wrong_model = compile_statements(wrong_board, wrong_clues, rules=wrong_rules)
    for person, square in placement.items():
        wrong_model.assign(wrong_model.literal(person, square), "test", "fixed")
    assert Solver(wrong_model).solve().contradiction is not None


def test_occupied_area_counts_exclude_regions_without_free_cells():
    text = """Size: 2
Regions:
a: west
b: east
Grid:
a b
a b
Objects:
wall: blocking r1c2 r2c2
People:
Ada
Clues:
count empty areas = 1
count ((empty areas touches area:west) except area:west) = 1
count ((occupied areas touches area:west) except area:west) = 0
"""
    board, rules, clues = load_expression_board(text)
    placement = {"Ada": Square(0, 0)}
    assert accepts(text, placement)
    assert all(holds(statement, board, placement, {}) for statement in clues)
    model = compile_statements(board, clues, rules=rules)
    model.assign(model.literal("Ada", Square(0, 0)), "test", "fixed")
    assert Solver(model).solve().contradiction is None


def test_with_same_area_defaults_to_any_companion():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Clues:
count (people in area of Ada) = 1 + 1
"""
    board, _rules, clues = load_expression_board(text)
    placement = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    assert holds(clues[0], board, placement, {})
    assert accepts(text, placement)


def test_with_same_area_rejects_explicit_any_selector():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Clues:
count (people in area of Ada) = 1 + 1 and every ((people except Ada) in area of Ada) on people:any
"""
    with pytest.raises(ValueError, match="people:any is removed; use people"):
        load_expression_board(text)


@pytest.mark.parametrize("clue", ["count empty areas all = 1", "count occupied areas all = 1"])
def test_area_counts_reject_redundant_all_scope(clue):
    text = f"""Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
{clue}
"""
    with pytest.raises(ValueError, match="line 9, column"):
        load_expression_board(text)


def test_empty_and_occupied_area_counts_default_to_all():
    text = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
count empty areas = 0
count occupied areas = 1
"""
    board, _rules, clues = load_expression_board(text)
    assert all(
        isinstance(statement.formula, NumberComparison)
        and isinstance(statement.formula.left, Count)
        for statement in clues
    )
    assert all(holds(statement, board, {"Ada": Square(0, 0)}, {}) for statement in clues)


def test_scoped_area_isolation_covers_borders_leaving_the_scope():
    text = """Size: 4
Regions:
a: west
b: east
c: south
d: north
Grid:
a b b b
b a c c
d d c c
d d c c
AreaTags:
coast: west
People:
Ada
Ben
Rules:
every ?a in (occupied tag:coast): no occupied areas touches ?a
"""
    board, rules, clues = load_expression_board(text)
    together = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    adjacent = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    assert holds(rules[0], board, together, {})
    assert not holds(rules[0], board, adjacent, {})
    assert accepts(text, together)
    assert not accepts(text, adjacent)

    model = compile_statements(board, clues, rules=rules)
    for person, square in adjacent.items():
        model.assign(model.literal(person, square), "test", "fixed")
    assert Solver(model).solve().contradiction is not None


def test_area_occupancy_conditions_use_roles_and_person_relative_counts():
    base = """Size: 3
Regions:
a: west
b: east
Grid:
a b b
a b b
a b b
People:
Ada
Ben
Roles:
guard: any
RoleEligibility:
guard: Ada Ben
Clues:
{clue}
"""
    together = {"Ada": Square(0, 1), "Ben": Square(1, 2)}
    alone_in_east = "count (people in area:east) = 1"
    ada_alone_in_east = "Ada in area:east and count (people in area:east) = 1"
    assert not accepts(base.format(clue=alone_in_east), together)
    assert not accepts(base.format(clue=ada_alone_in_east), together)
    assert accepts(
        base.format(clue="count (people in area:east) >= 2 and some role:guard in area:east"),
        together,
    )
    one_guard_companion = (
        "Ada in area:east and count ((people except Ada) in area:east) = 1 "
        "and every ((people except Ada) in area:east) is role:guard"
    )
    assert accepts(
        base.format(clue=one_guard_companion),
        together,
    )
    assert not accepts(
        base.format(clue=one_guard_companion.replace("= 1", "= 2")),
        together,
    )
    alone = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    assert accepts(base.format(clue=alone_in_east), alone)
    assert accepts(base.format(clue=ada_alone_in_east), alone)
    assert not accepts(
        base.format(clue=ada_alone_in_east),
        {"Ada": Square(0, 0), "Ben": Square(1, 1)},
    )

    text = base.format(clue=one_guard_companion)
    board, rules, clues = load_expression_board(text)
    model = compile_statements(board, clues, rules=rules)
    for person, square in together.items():
        model.assign(model.literal(person, square), "test", "fixed")
    assert Solver(model).solve().contradiction is None

    same_area = base.format(
        clue="count (people in area of Ada) = 1 + 1 "
        "and every ((people except Ada) in area of Ada) is role:guard"
    )
    assert accepts(same_area, together)
    assert not accepts(
        same_area,
        {"Ada": Square(0, 1), "Ben": Square(1, 0)},
    )


def test_role_conditionals_apply_atomic_location_predicates_only_to_holders():
    text = """Size: 3
Regions:
a: west
b: east
Grid:
a b b
a b b
a b b
People:
Ada
Ben
Roles:
guard: 1
RoleEligibility:
guard: Ada
Clues:
if Ada is role:guard then Ada in area:west
"""
    board, rules, clues = load_expression_board(text)
    valid = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    invalid = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    assert accepts(text, valid)
    assert not accepts(text, invalid)
    model = compile_statements(board, clues, rules=rules)
    for person, square in invalid.items():
        model.assign(model.literal(person, square), "test", "fixed")
    assert Solver(model).solve().contradiction is not None


def test_for_each_area_role_counts_use_existing_role_semantics():
    text = """Size: 2
Regions:
a: west
b: east
Grid:
a b
a b
AreaTags:
villages: west east
People:
Ada
Ben
Roles:
guard: 2 different_regions
RoleEligibility:
guard: Ada Ben
Clues:
every ?a in tag:villages: some role:guard in ?a
every ?p in role:guard: count (people in area of ?p) = 1
"""
    board, rules, clues = load_expression_board(text)
    placement = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    assert accepts(text, placement)
    model = compile_statements(board, clues, rules=rules)
    for person, square in placement.items():
        model.assign(model.literal(person, square), "test", "fixed")
    assert Solver(model).solve().contradiction is None


def test_dir_uses_role_and_occupied_location_person_selectors():
    role_text = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
People:
Ada
Ben
Roles:
guard: 1
RoleEligibility:
guard: Ada
Clues:
some role:guard dir:up Ben
"""
    board, _rules, clues = load_expression_board(role_text)
    placement = {"Ada": Square(0, 0), "Ben": Square(2, 2)}
    assert holds(
        clues[0],
        board,
        placement,
        {("Ada", "guard"): True, ("Ben", "guard"): False},
    )
    assert accepts(role_text, placement)

    location_text = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
Objects:
coat: standable r3c1
slippers: standable r1c3
People:
Ada
Ben
Clues:
some (people on object:coat) dir:down (people on object:slippers)
"""
    locations, _location_rules, location_clues = load_expression_board(location_text)
    on_items = {"Ada": Square(2, 0), "Ben": Square(0, 2)}
    assert holds(location_clues[0], locations, on_items, {})
    assert accepts(location_text, on_items)
    empty_items = {"Ada": Square(2, 1), "Ben": Square(0, 0)}
    assert not holds(location_clues[0], locations, empty_items, {})
    assert not accepts(location_text, empty_items)


def test_dir_axis_comparisons_validate_bounds_and_use_absolute_gaps():
    base = """Size: 5
Regions:
a: room
Grid:
a a a a a
a a a a a
a a a a a
a a a a a
a a a a a
People:
Ada
Ben
Clues:
{clue}
"""
    pair = {"Ada": Square(0, 0), "Ben": Square(3, 4)}
    for clue in ("Ada dir:rows Ben >= 3", "Ada dir:cols Ben >= 4"):
        board, _, clues = load_expression_board(base.format(clue=clue))
        assert holds(clues[0], board, pair, {})
        assert accepts(base.format(clue=clue), pair)

    for clue in ("Ada dir:rows Ben <= 2", "Ada dir:cols Ben <= 3"):
        board, _rules, clues = load_expression_board(base.format(clue=clue))
        assert not holds(clues[0], board, pair, {})

    for clue in ("Ada dir:rows Ben = 5", "Ada dir:cols Ben >= 5"):
        assert not solutions(base.format(clue=clue))
    for clue in ("Ada dir:left Ben = 0", "Ada dir:up+right Ben <= 0"):
        with pytest.raises(ValueError, match="no feasible value"):
            load_expression_board(base.format(clue=clue))


def test_dir_area_king_and_knight_modes_use_documented_distances():
    text = """Size: 3
Regions:
a: west
b: east
c: center
Grid:
a a c
a c b
c b b
People:
Ada
Ben
Clues:
Ada dir:areas Ben = 2
"""
    board, _, clues = load_expression_board(text)
    assert holds(
        clues[0],
        board,
        {"Ada": Square(0, 0), "Ben": Square(1, 2)},
        {},
    )

    for mode, expected in (("king", True), ("knight", True)):
        board, _rules, clues = load_expression_board(
            text.replace("areas = 2", mode + (" >= 2" if mode == "king" else ""))
        )
        assert (
            holds(
                clues[0],
                board,
                {"Ada": Square(0, 0), "Ben": Square(1, 2)},
                {},
            )
            is expected
        )
