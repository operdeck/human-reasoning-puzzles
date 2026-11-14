import pytest

from csp import clue_search
from csp.bruteforce.murdoku import accepts, solutions
from csp.core import Contradiction, Solver
from csp.murdoku import (
    Square,
    area_isolation_conditions,
    area_occupancy_conditions,
    compile_puzzle,
    conditional_conditions,
    conditions,
    directional_conditions,
    global_count_conditions,
    quantified_conditions,
    role_conditions,
)
from csp.puzzlefile import keyed_clue_numbers, load_board, parse_clue_line


def test_canonical_clue_parser_reads_negation_and_compound_predicates():
    assert parse_clue_line("not touches Ada mark:water | wording") == (
        "not_touches",
        ["Ada", "mark:water"],
    )
    assert parse_clue_line(
        "for each area in tag:villages, count people in that area with role:guard >= 2"
    ) == (
        "for_each_area",
        [
            "in",
            "tag:villages,",
            "count",
            "people",
            "in",
            "that",
            "area",
            "with",
            "role:guard",
            ">=",
            "2",
        ],
    )
    assert parse_clue_line("no_adjacent_occupied areas in tag:villages") == (
        "no_adjacent_occupied",
        ["in", "tag:villages"],
    )
    assert parse_clue_line("not dir Ada Ben left") == ("not_dir", ["Ada", "Ben", "left"])
    assert parse_clue_line("has Ada role:guard") == ("has_role", ["Ada", "guard"])
    assert parse_clue_line("not has Ada attribute:trained") == (
        "not_attribute",
        ["Ada", "trained"],
    )
    assert parse_clue_line("subset role:guard attribute:trained") == (
        "role_subset",
        ["role:guard", "attribute:trained"],
    )
    assert (
        parse_clue_line(
            "for each area in tag:villages, count people in that area with role:guard >= 1"
        )[0]
        == "for_each_area"
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
    with pytest.raises(ValueError, match="legacy or unknown clue syntax"):
        load_board(text)


def test_legacy_selector_aliases_are_rejected():
    text = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
in Ada row:1
"""
    board, clues = load_board(text)
    with pytest.raises(ValueError, match="unknown target kind 'row'"):
        conditions(board, clues)


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
    assert accepts(base.format(clue="in Ada area:west"), west)
    assert not accepts(base.format(clue="in Ada area:east"), west)
    assert accepts(base.format(clue="has Ada attribute:trained"), west)
    assert not accepts(base.format(clue="not has Ada attribute:trained"), west)
    assert accepts(
        base.format(clue="on Ada mark:water"),
        {"Ada": Square(1, 1), "Ben": Square(0, 2)},
    )
    assert not accepts(base.format(clue="beside Ada mark:water"), across)
    assert accepts(base.format(clue="touches Ada mark:water"), across)
    assert accepts(base.format(clue="not touches Ada mark:water"), west)
    assert accepts(
        base.format(clue="exactly 1 in Ada area:west ; on Ben mark:water"),
        west,
    )
    assert not accepts(
        base.format(clue="exactly 1 in Ada area:west ; on Ben mark:water"),
        {"Ada": Square(0, 0), "Ben": Square(1, 1)},
    )
    assert accepts(
        base.format(clue="only Ada on mark:water"),
        {"Ada": Square(1, 1), "Ben": Square(0, 2)},
    )
    assert not accepts(base.format(clue="only Ada on mark:water"), west)

    text = base.format(clue="touches Ada mark:water")
    board, clues = load_board(text)
    compiled = compile_puzzle(board, clues)
    for person, square in across.items():
        compiled.assign(compiled.literal(person, square), "test", "fixed")
    assert Solver(compiled).solve().contradiction is None
    condition = conditions(board, clues)[0]
    assert condition.test(across["Ada"])


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
    exactly_one = "exactly 1 in Ada area:west ; dir Ada Ben right"
    assert accepts(
        base.format(clue=exactly_one),
        {"Ada": Square(0, 2), "Ben": Square(1, 0)},
    )
    both_true = "exactly 1 in Ada area:west ; dir Ada Ben left"
    assert not accepts(
        base.format(clue=both_true),
        {"Ada": Square(0, 0), "Ben": Square(1, 2)},
    )

    negated = base.replace("Size: 3", "Size: 4").replace(
        "Grid:\na b b\na b b\na b b",
        "Grid:\na b b b\na b b b\na b b b\na b b b",
    )
    one_negated_true = "exactly 1 not in Ada area:west ; not dir Ada Ben left"
    assert accepts(
        negated.format(clue=one_negated_true),
        {"Ada": Square(0, 1), "Ben": Square(0, 3)},
    )
    both_negated_true = "exactly 1 not in Ada area:west ; not dir Ada Ben left"
    assert not accepts(
        negated.format(clue=both_negated_true),
        {"Ada": Square(0, 3), "Ben": Square(0, 0)},
    )


def test_clue_search_only_generates_parseable_canonical_clues():
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
    board, _ = load_board(text)
    placement = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    candidates = clue_search.candidate_clues(board, placement)
    parsed = [parse_clue_line(clue) for clue in candidates]
    assert ("in", ["Ada", "area:west"]) in parsed
    assert ("dir", ["Ada", "Ben", "left"]) in parsed
    assert all(not clue.startswith(("in_region", "left_of", "same_region")) for clue in candidates)


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
in Ada area:room | clue wording
Key:
rule: count people in area:room = 1
clue: in Ada area:room
"""
    assert keyed_clue_numbers(text) == {1}
    load_board(text)


def test_key_metadata_rejects_stale_and_duplicate_references():
    base = """Size: 1
Regions:
a: room
Grid:
a
People:
Ada
Clues:
in Ada area:room
Key:
clue: in Ada area:wrong
"""
    with pytest.raises(ValueError, match="unresolved Key clue"):
        load_board(base)
    with pytest.raises(ValueError, match="duplicate Key"):
        load_board(
            base.replace(
                "clue: in Ada area:wrong",
                "clue: in Ada area:room\nclue: in Ada area:room",
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
in Ada area:room
Key:
clue: in Ada area:room
"""
    assert clue_search.thin(text) == ["in Ada area:room"]
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
dir Ada Ben euclidean = 5
"""
    board, clues = load_board(text)
    (condition,) = directional_conditions(board, clues)
    assert condition.test(Square(0, 0), Square(3, 4))
    assert not condition.test(Square(0, 0), Square(3, 3))

    model = compile_puzzle(board, clues)
    assert model.relations
    valid = {"Ada": Square(0, 0), "Ben": Square(3, 4)}
    invalid = {"Ada": Square(0, 0), "Ben": Square(3, 3)}
    assert accepts(text, valid)
    assert not accepts(text, invalid)
    valid_model = compile_puzzle(board, clues)
    for person, square in valid.items():
        valid_model.assign(valid_model.literal(person, square), "test", "fixed")
    assert Solver(valid_model).solve().contradiction is None
    invalid_model = compile_puzzle(board, clues)
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
not dir Ada Ben left
"""
    board, clues = load_board(text)
    (condition,) = directional_conditions(board, clues)
    left = {"Ada": Square(1, 0), "Ben": Square(1, 2)}
    right = {"Ada": Square(1, 2), "Ben": Square(1, 0)}
    assert not condition.holds(board, left, {})
    assert condition.holds(board, right, {})
    assert not accepts(text, left)
    assert accepts(text, right)

    rejected_model = compile_puzzle(board, clues)
    with pytest.raises(Contradiction):
        for person, square in left.items():
            rejected_model.assign(rejected_model.literal(person, square), "test", "fixed")


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
not dir Ada object:tree,rock king <= 1
"""
    board, clues = load_board(text)
    safe = {"Ada": Square(2, 2)}
    near_one_target = {"Ada": Square(1, 2)}
    assert accepts(text, safe)
    assert not accepts(text, near_one_target)

    safe_model = compile_puzzle(board, clues)
    safe_model.assign(safe_model.literal("Ada", safe["Ada"]), "test", "fixed")
    assert Solver(safe_model).solve().contradiction is None
    unsafe_model = compile_puzzle(board, clues)
    unsafe_model.assign(unsafe_model.literal("Ada", near_one_target["Ada"]), "test", "fixed")
    assert Solver(unsafe_model).solve().contradiction is not None


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
dir Ada adjacent_to:west areas = 0
"""
    board, clues = load_board(text)
    (condition,) = directional_conditions(board, clues)
    assert not condition.holds(board, {"Ada": Square(0, 0)}, {})
    assert condition.holds(board, {"Ada": Square(0, 2)}, {})

    tagged = text.replace("adjacent_to:west", "adjacent_to:tag:coast")
    tagged_board, tagged_clues = load_board(tagged)
    (tagged_condition,) = directional_conditions(tagged_board, tagged_clues)
    assert not tagged_condition.holds(tagged_board, {"Ada": Square(0, 0)}, {})


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
count occupied areas in adjacent_to:west = 2
count occupied areas in tag:neighbors and adjacent_to:west = 2
count people in adjacent_to:west = 2
"""
    board, clues = load_board(text)
    placement = {
        "Ada": Square(0, 0),
        "Ben": Square(1, 2),
        "Cal": Square(2, 1),
    }
    counts = global_count_conditions(board, clues)
    assert [condition.count(board, placement, {}) for condition in counts] == [2, 2, 2]
    assert accepts(text, placement)
    model = compile_puzzle(board, clues)
    for person, square in placement.items():
        model.assign(model.literal(person, square), "test", "fixed")
    assert Solver(model).solve().contradiction is None

    wrong_count = text.replace("adjacent_to:west = 2", "adjacent_to:west = 1", 1)
    wrong_board, wrong_clues = load_board(wrong_count)
    wrong_model = compile_puzzle(wrong_board, wrong_clues)
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
count empty areas all = 1
count empty areas in adjacent_to:west = 1
count occupied areas in adjacent_to:west = 0
"""
    board, clues = load_board(text)
    placement = {"Ada": Square(0, 0)}
    assert accepts(text, placement)
    counts = global_count_conditions(board, clues)
    assert [condition.count(board, placement, {}) for condition in counts] == [1, 1, 0]
    model = compile_puzzle(board, clues)
    model.assign(model.literal("Ada", Square(0, 0)), "test", "fixed")
    assert Solver(model).solve().contradiction is None


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
no_adjacent_occupied areas in tag:coast
"""
    board, clues = load_board(text)
    checks = area_isolation_conditions(board, clues)
    assert checks[0].borders(board)

    together = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    adjacent = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    assert checks[0].holds(board, together)
    assert not checks[0].holds(board, adjacent)
    assert accepts(text, together)
    assert not accepts(text, adjacent)

    model = compile_puzzle(board, clues)
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
    assert accepts(base.format(clue="alone in area:east"), together) is False
    assert accepts(base.format(clue="alone Ada in area:east"), together) is False
    assert accepts(base.format(clue="with role:guard in area:east"), together)
    assert accepts(
        base.format(clue="with Ada role:guard in area:east exactly 1"),
        together,
    )
    assert not accepts(
        base.format(clue="with Ada role:guard in area:east exactly 2"),
        together,
    )
    alone = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    assert accepts(base.format(clue="alone in area:east"), alone)
    assert accepts(base.format(clue="alone Ada in area:east"), alone)

    text = base.format(clue="with Ada role:guard in area:east exactly 1")
    board, clues = load_board(text)
    assert len(area_occupancy_conditions(board, clues)) == 1
    model = compile_puzzle(board, clues)
    for person, square in together.items():
        model.assign(model.literal(person, square), "test", "fixed")
    assert Solver(model).solve().contradiction is None

    same_area = base.format(clue="with Ada role:guard in same area exactly 1")
    same_board, same_clues = load_board(same_area)
    assert len(quantified_conditions(same_board, same_clues)) == 1
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
if has Ada role:guard then in Ada area:west
"""
    board, clues = load_board(text)
    assert len(conditional_conditions(board, clues)) == 1
    valid = {"Ada": Square(0, 0), "Ben": Square(1, 2)}
    invalid = {"Ada": Square(0, 1), "Ben": Square(1, 0)}
    assert accepts(text, valid)
    assert not accepts(text, invalid)
    model = compile_puzzle(board, clues)
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
for each area in tag:villages, count people in that area with role:guard >= 1
for each area in all occupied by role:guard, count people in that area = 1
"""
    board, clues = load_board(text)
    assert len(role_conditions(board, clues)) == 2
    placement = {"Ada": Square(0, 0), "Ben": Square(1, 1)}
    assert accepts(text, placement)
    model = compile_puzzle(board, clues)
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
dir role:guard Ben up
"""
    board, clues = load_board(role_text)
    (role_condition,) = directional_conditions(board, clues)
    placement = {"Ada": Square(0, 0), "Ben": Square(2, 2)}
    assert role_condition.holds(
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
dir people_on:object:coat people_on:object:slippers down
"""
    locations, location_clues = load_board(location_text)
    (location_condition,) = directional_conditions(locations, location_clues)
    on_items = {"Ada": Square(2, 0), "Ben": Square(0, 2)}
    assert location_condition.holds(locations, on_items, {})
    assert accepts(location_text, on_items)
    empty_items = {"Ada": Square(2, 1), "Ben": Square(0, 0)}
    assert not location_condition.holds(locations, empty_items, {})
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
    for clue in ("dir Ada Ben rows >= 3", "dir Ada Ben cols >= 4"):
        board, clues = load_board(base.format(clue=clue))
        (condition,) = directional_conditions(board, clues)
        assert condition.holds(board, pair, {})
        assert accepts(base.format(clue=clue), pair)

    for clue in ("dir Ada Ben rows <= 2", "dir Ada Ben cols <= 3"):
        board, clues = load_board(base.format(clue=clue))
        (condition,) = directional_conditions(board, clues)
        assert not condition.holds(board, pair, {})

    for clue in ("dir Ada Ben rows = 0", "dir Ada Ben cols >= 0"):
        board, clues = load_board(base.format(clue=clue))
        with pytest.raises(ValueError, match="distance must be at least 1"):
            directional_conditions(board, clues)


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
dir Ada Ben areas = 2
"""
    board, clues = load_board(text)
    (area_condition,) = directional_conditions(board, clues)
    assert area_condition.holds(
        board,
        {"Ada": Square(0, 0), "Ben": Square(1, 2)},
        {},
    )

    for mode, expected in (("king", True), ("knight", True)):
        board, clues = load_board(
            text.replace("areas = 2", mode + (" >= 2" if mode == "king" else ""))
        )
        (condition,) = directional_conditions(board, clues)
        assert (
            condition.holds(
                board,
                {"Ada": Square(0, 0), "Ben": Square(1, 2)},
                {},
            )
            is expected
        )
