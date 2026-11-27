"""The rooms authoring search and brief check: what a clue set may be."""

import pytest

from csp import rooms_search

pytestmark = pytest.mark.solutions

PLAN = """Solution: Ada=c Ben=a Cleo=c Dirk=d
Family: rooms
Language: en
Plan:
a a b
c d e
Rooms:
a: 2 #D9EAD3 living room
b: 1 #FADFB5 hall
c: 2 #C4DCF2 kitchen
d: 1 #F4CBC3 study
e: 1 #E8D5F2 bathroom
Tags:
window: a c e
clock: a d
People:
Ada
Ben
Cleo
Dirk
"""


def test_a_plan_states_its_placement_and_keeps_it_out_of_the_puzzle():
    surface, placement = rooms_search.read_plan(PLAN)
    assert "Solution:" not in surface
    assert placement == {"Ada": "c", "Ben": "a", "Cleo": "c", "Dirk": "d"}
    _, _, puzzle = rooms_search.plan_puzzle(PLAN)
    assert not puzzle.clues
    assert puzzle.people == ("Ada", "Ben", "Cleo", "Dirk")


def test_clue_kinds_and_areas_are_recognised():
    assert rooms_search.kind_of("Ada in area:c") == "in"
    assert rooms_search.kind_of("not (Ada in area:c)") == "in"
    assert rooms_search.kind_of("Ada dir:up Ben") == "dir"
    assert rooms_search.kind_of("Ada beside Ben") == "beside"
    assert rooms_search.kind_of("Ada alone") == "alone"
    assert rooms_search.kind_of("Ada apart Ben") == "together"
    assert rooms_search.kind_of("count (people in area:a) = 0") == "empty"
    assert rooms_search.kind_of("sum (ages in area:a) = 54") == "age"
    assert rooms_search.kind_of("max (age in area:a) <= 27") == "age"
    assert rooms_search.area_of("count (people in area:window) = 0") == "window"
    assert rooms_search.area_of("sum (ages in area:window) = 54") == "window"
    assert rooms_search.area_of("Ada dir:up Ben") is None


def test_only_emptiness_is_allowed_where_a_brief_forbids_numbers():
    brief = rooms_search.Brief()
    assert rooms_search.allowed("count (people in area:a) = 0", brief)
    assert rooms_search.allowed("count (people in area:a) >= 1", brief)
    assert not rooms_search.allowed("count (people in area:a) = 1", brief)
    assert not rooms_search.allowed("count (people in area:a) >= 2", brief)
    strict = rooms_search.Brief(kinds=frozenset({"beside"}))
    assert rooms_search.allowed("Ada beside Ben", strict)
    assert not rooms_search.allowed("Ada dir:up Ben", strict)


def test_the_search_fits_a_brief_and_the_check_agrees():
    brief = rooms_search.Brief(
        clues=6,
        kinds=frozenset({"in", "dir", "beside", "empty"}),
        attempts=20,
        seconds=30.0,
        seed=3,
    )
    found = rooms_search.search(PLAN, brief)
    assert found is not None
    findings, problems = rooms_search.check(found, brief)
    assert not problems, problems
    assert 1 <= len(findings) <= 6
    assert all(finding.needed and not finding.pins for finding in findings)
    assert all(finding.kind in brief.kinds for finding in findings)


def test_a_late_discovery_names_the_last_person_a_clue_settles():
    """The ladder's order tells which clue-named person is discovered last."""
    surface, _ = rooms_search.read_plan(PLAN)
    clues = ["Ada in area:c", "count (people in area:a) = 2", "Ben in area:clock"]
    order = rooms_search.placement_order(surface, clues)
    assert order, "the ladder should place someone"
    assert rooms_search.placements_last(surface, clues, order[-1])
    assert not rooms_search.placements_last(surface, clues, "Dirk")


def test_the_check_names_a_number_a_reused_area_and_a_missing_room_alias():
    surface, _ = rooms_search.read_plan(PLAN)
    numbered = surface + "Clues:\ncount (people in area:a) = 1\ncount (people in area:b) = 1\n"
    _, problems = rooms_search.check(numbered, rooms_search.Brief(clues=2))
    assert any("gives a number" in problem for problem in problems)
    reused = surface + "Clues:\nAda in area:c\nBen in area:c\n"
    _, problems = rooms_search.check(reused, rooms_search.Brief(clues=2))
    assert any("named by more than one clue" in problem for problem in problems)
