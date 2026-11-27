"""The rooms family: parsing, clue meaning, the capacity invariant and the examples."""

import pytest

from csp import bruteforce, cli, icons, picture, report, rooms
from csp.bruteforce import rooms as brute
from csp.core import Solver
from tests.examples import example, played_examples

BASE = """Family: rooms
Language: en
Plan:
a a b
c d e
Rooms:
a: 2 #D9EAD3 living room
b: 1 #FADFB5 hall
c: 1 #C4DCF2 kitchen
d: 1 #F4CBC3 study
e: 2 #E8D5F2 attic
Tags:
window: a c e
clock: a d
People:
Ada
Ben
Cleo
Clues:
"""

PLACEMENT = {"Ada": "c", "Ben": "a", "Cleo": "a"}
AGE_BASE = BASE.replace("Clues:\n", "Ages:\nAda: 60\nBen: 26\nCleo: 28\n\nClues:\n")
ROOMS_EXAMPLES = [
    path.name for path in played_examples() if cli.detect(path.read_text()) == "rooms"
]


def puzzle_with(clues: str) -> str:
    return BASE + clues


def with_words(text: str, *lines: str) -> str:
    """The puzzle with a `Words:` section, which a group count uses for its wording."""
    return text.replace("Tags:\n", "Words:\n" + "\n".join(lines) + "\n\nTags:\n")


def test_the_plan_rooms_tags_and_people_are_read():
    puzzle = rooms.parse(puzzle_with("Ada in area:c\n"))
    assert [room.key for room in puzzle.rooms] == ["a", "b", "c", "d", "e"]
    assert puzzle.room("e").capacity == 2
    assert puzzle.room("e").label == "attic"
    assert puzzle.room("a").cells == ((0, 0), (0, 1))
    assert puzzle.areas("window") == ("a", "c", "e")
    assert puzzle.areas("b") == ("b",)
    assert puzzle.people == ("Ada", "Ben", "Cleo")
    assert (puzzle.width, puzzle.height) == (3, 2)


def test_every_clue_kind_means_what_it_says():
    clues = (
        "Ada in area:window",
        "not (Ada in area:clock)",
        "count (people in area:a) = 2",
        "Ben together Cleo",
        "Cleo apart Ada",
        "not (Cleo alone)",
        "exactly 1 of (Ada in area:window; Ben in area:e)",
        "Cleo dir:up Ada",
        "Ben beside Cleo",
    )
    puzzle = rooms.parse(puzzle_with("\n".join(clues) + "\n"))
    assert len(puzzle.clues) == len(clues)
    for clue in puzzle.clues:
        assert clue.holds(PLACEMENT, puzzle), clue.describe(puzzle)
    wrong = dict(PLACEMENT, Ben="e")
    assert not all(clue.holds(wrong, puzzle) for clue in puzzle.clues)


def test_a_rule_holds_for_every_answer_and_can_be_worded():
    rule = "count (people in area:e) in 0, 2 | De zolder is leeg of telt twee mensen."
    text = BASE.replace("Clues:\n", f"Rules:\n{rule}\nClues:\n")
    puzzle = rooms.parse(text + "Ada in area:c\n")
    assert len(puzzle.rules) == 1
    assert isinstance(puzzle.rules[0], rooms.Allowed)
    assert puzzle.rules[0].numbers == (0, 2)
    assert puzzle.rule_lines == ["De zolder is leeg of telt twee mensen."]
    assert rooms.format_clue(puzzle.rules[0]) == "count (people in area:e) in 0, 2"
    assert rooms.parse_clue(rooms.format_clue(puzzle.rules[0]), puzzle) == puzzle.rules[0]
    for where in bruteforce.solutions(text + "Ada in area:c\n", "rooms", limit=20):
        assert list(where.values()).count("attic") in (0, 2)


def test_a_rule_reads_as_a_sentence_without_its_own_wording():
    text = BASE.replace("Clues:\n", "Rules:\ncount (people in area:window) in 0, 2\nClues:\n")
    puzzle = rooms.parse(text + "Ada in area:c\n")
    assert puzzle.rule_lines == ["The window rooms hold no or two people."]
    model, _ = rooms.compile_puzzle(text + "Ada in area:c\n")
    assert any(constraint.family == "a puzzle rule" for constraint in model.constraints)
    puzzle = rooms.parse(puzzle_with("Ada beside Ben\n"))
    beside = rooms.Beside("Ada", "Ben")
    assert beside.holds({"Ada": "c", "Ben": "a"}, puzzle)  # side by side
    assert beside.holds({"Ada": "a", "Ben": "a"}, puzzle)  # one room
    assert not beside.holds({"Ada": "e", "Ben": "a"}, puzzle)  # not touching
    assert not beside.holds({"Ada": "b", "Ben": "c"}, puzzle)  # diagonal only
    assert rooms.Beside("Ada", "Ben", True).holds({"Ada": "e", "Ben": "a"}, puzzle)


def test_format_clue_round_trips_every_kind():
    clues = (
        "Ada in area:window",
        "not (Ben in area:window)",
        "count (people in area:a) >= 2",
        "Ada together Ben",
        "Cleo apart Ada",
        "not (Cleo alone)",
        "exactly 1 of (Ada in area:e; Ben in area:e)",
        "Ada dir:up Cleo",
        "Ben beside Cleo",
        "not (Ada beside Cleo)",
    )
    puzzle = rooms.parse(puzzle_with("\n".join(clues) + "\n"))
    for clue in puzzle.clues:
        assert rooms.parse_clue(rooms.format_clue(clue), puzzle) == clue


def test_capacity_is_an_upper_bound_and_never_forces_a_person():
    """A room's capacity forbids a second truth; it never fills a room by itself."""
    text = puzzle_with("Ada in area:c\n")
    model = cli.load(text, "rooms").model
    assert len(model.options("Ben")) == len(rooms.parse(text).rooms)
    assert len(model.options("Cleo")) == len(rooms.parse(text).rooms)
    (solution,) = bruteforce.solutions(text, "rooms", limit=1)
    assert solution["Ada"] == "kitchen"


def test_an_empty_room_stays_empty():
    text = puzzle_with("count (people in area:b) = 0\n")
    for where in bruteforce.solutions(text, limit=20):
        assert "hall" not in where.values()


def test_a_count_about_everyone_is_judged_on_the_whole_placement():
    """The search may not prune on a count until every person is placed."""
    text = puzzle_with("count (people in area:d) = 1\n")
    found = bruteforce.solutions(text, limit=5)
    assert found
    for where in found:
        assert list(where.values()).count("study") == 1


def test_alone_needs_one_hidden_literal_per_other_person():
    """`Alone` counts the rooms shared with the others, never a relation over everyone."""
    model = cli.load(puzzle_with("not (Ada alone)\n"), "rooms").model
    hidden = [var for var in model.all_variables if var not in model.variables]
    assert len(hidden) == 2  # one for each of the other two people
    assert not any(len(relation.variables) > 3 for relation in model.relations)


def test_a_direction_clue_needs_touching_rooms():
    puzzle = rooms.parse(puzzle_with("Cleo dir:north Ada\n"))
    up = rooms.Direction("Cleo", "north", "Ada")
    assert up.holds({"Cleo": "a", "Ada": "c"}, puzzle)
    assert not up.holds({"Cleo": "c", "Ada": "a"}, puzzle)
    assert not up.holds({"Cleo": "a", "Ada": "a"}, puzzle)
    assert not up.holds({"Cleo": "b", "Ada": "c"}, puzzle)
    assert puzzle.sentence(1) == "Cleo is directly north of Ada."


def test_the_plan_top_is_north_so_compass_and_side_words_agree():
    """`dir:up` and `dir:north` are one side, and the compass word is the canonical one."""
    puzzle = rooms.parse(puzzle_with("Cleo dir:up Ada\n"))
    assert puzzle.clues[0] == rooms.Direction("Cleo", "north", "Ada")
    assert rooms.format_clue(puzzle.clues[0]) == "Cleo dir:north Ada"
    assert puzzle.sentence(1) == "Cleo is directly north of Ada."
    dutch = rooms.parse(puzzle_with("Cleo dir:right Ada\n").replace("Language: en", "Language: nl"))
    assert dutch.sentence(1) == "Cleo zit direct ten oosten van Ada."


def test_render_names_every_room_with_its_capacity_and_occupants():
    text = puzzle_with("Ada together Ben\nAda in area:a\nBen in area:a\n")
    model, puzzle = rooms.compile_puzzle(text)
    Solver(model).solve()
    living = next(
        line
        for line in rooms.render(puzzle, model, "The flat").splitlines()
        if "Living room" in line
    )
    assert "(2)" in living and "Ada" in living and "Ben" in living


@pytest.mark.parametrize("name", ROOMS_EXAMPLES)
def test_every_rooms_example_is_unique_and_solved(name):
    text = example(name).read_text()
    (expected,) = bruteforce.solutions(text, "rooms")
    model = cli.load(text, "rooms").model
    fired: list[str] = []
    result = Solver(model).solve(on_step=lambda rule, steps: fired.append(rule))
    assert result.solved, report.grade(fired)
    assert result.assignment == expected


@pytest.mark.parametrize("name", ROOMS_EXAMPLES)
def test_every_rooms_example_needs_each_of_its_clues(name):
    text = example(name).read_text()
    lines = text.splitlines()
    start = lines.index("Clues:") + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].strip().endswith(":")),
        len(lines),
    )
    clues = [line for line in lines[start:end] if line.strip()]
    for number, clue in enumerate(clues):
        kept = [item for index, item in enumerate(clues) if index != number]
        fewer = "\n".join([*lines[:start], *kept, *lines[end:]]) + "\n"
        assert len(bruteforce.solutions(fewer, "rooms", limit=2)) > 1, clue


@pytest.mark.parametrize("name", ROOMS_EXAMPLES)
def test_every_room_property_in_the_examples_has_a_picture(name):
    puzzle = rooms.parse(example(name).read_text())
    assert puzzle.tags, name
    for tag in puzzle.tags:
        assert icons.object_icon(tag) is not None, tag


def test_the_picture_shows_each_rooms_properties_with_a_key():
    puzzle = rooms.parse(example("rooms_2_5x7.txt").read_text())
    image = picture.rooms_picture(puzzle, cell=70).to_svg()
    for tag in puzzle.tags:
        icon = icons.object_icon(tag)
        assert icon is not None
        marker = f"emoji-{icon.emoji}" if icon.emoji else f"icon-{icon.name}"
        assert marker in image, tag
        assert puzzle.phrase(tag) in image, tag


def test_property_icons_shrink_to_fit_a_small_room():
    """A one-room-wide plan with four properties gets icons that fit inside it."""
    side, columns, rows, gap = picture._layout_properties(4, 150, 150, 39)
    assert columns >= 1 and rows >= 1
    assert columns * (side + gap) <= 150
    assert rows * (side + gap) <= 150 * 0.45 + 1
    empty = picture._layout_properties(0, 150, 150, 39)
    assert empty[2] == 0


def test_a_property_the_catalogue_does_not_know_gets_a_lettered_badge():
    """An unknown property still gets a marker in its rooms and a line in the key."""
    assert icons.object_icon("zorblax") is None
    text = puzzle_with("Ada in area:c\n").replace("clock: a d\n", "clock: a d\nzorblax: a c\n")
    puzzle = rooms.parse(text)
    image = picture.rooms_picture(puzzle, cell=70).to_svg()
    assert "zorblax" in puzzle.tags
    assert "zorblax" in image


@pytest.mark.parametrize("name", ROOMS_EXAMPLES)
def test_every_rooms_example_draws_every_room_and_its_people(name):
    text = example(name).read_text()
    puzzle = rooms.parse(text)
    image = picture.rooms_picture(puzzle, cell=60).to_svg()
    for room in puzzle.rooms:
        assert room.title in image
    (solution,) = bruteforce.solutions(text, "rooms")
    solved = picture.rooms_picture(puzzle, solution, cell=60).to_svg()
    for room in solution.values():
        assert room[:1].upper() + room[1:] in solved


def test_bruteforce_count_matches_the_number_of_solutions():
    text = puzzle_with("count (people in area:window) >= 1\n")
    assert brute.count(text) == len(bruteforce.solutions(text, "rooms", limit=1000))


def test_a_clue_line_can_carry_its_own_wording():
    puzzle = rooms.parse(puzzle_with("Ada in area:c | Ada zat in de keuken.\n"))
    assert puzzle.sentence(1) == "Ada zat in de keuken."
    assert puzzle.clue_lines == ["Ada zat in de keuken."]


def test_age_clues_use_the_declared_ages():
    puzzle = rooms.parse(AGE_BASE + "sum (ages in area:a) = 54\nmax (age in area:a) = 28\n")
    assert puzzle.ages == {"Ada": 60, "Ben": 26, "Cleo": 28}
    assert puzzle.age_lines == ["Ages: Ada 60, Ben 26, Cleo 28."]
    assert puzzle.clue_lines == [
        "The people in the living room are 54 years old together.",
        "The oldest person in the living room is 28.",
    ]
    for clue in puzzle.clues:
        assert clue.holds(PLACEMENT, puzzle), clue.describe(puzzle)
        assert rooms.parse_clue(rooms.format_clue(clue), puzzle) == clue


def test_an_age_total_can_be_compared_to_two_or_three_people():
    puzzle = rooms.parse(
        AGE_BASE
        + "sum (ages in area:a) < sum (ages of Ada, Cleo)\n"
        + "sum (ages in area:c) > sum (ages of Ben, Cleo)\n"
        + "sum (ages in area:a) < sum (ages of Ada, Ben, Cleo)\n"
    )
    assert puzzle.clue_lines == [
        "The people in the living room are younger together than Ada and Cleo.",
        "The people in the kitchen are older together than Ben and Cleo.",
        "The people in the living room are younger together than Ada, Ben and Cleo.",
    ]
    for clue in puzzle.clues:
        assert clue.holds(PLACEMENT, puzzle), clue.describe(puzzle)
        assert rooms.parse_clue(rooms.format_clue(clue), puzzle) == clue
    with pytest.raises(ValueError):
        rooms.parse(AGE_BASE + "sum (ages in area:a) < sum (ages of Ada)\n")
    with pytest.raises(ValueError):
        rooms.parse(AGE_BASE + "sum (ages in area:a) < sum (ages of Ada, Ada)\n")


def test_the_oldest_of_an_empty_area_is_vacuously_young():
    puzzle = rooms.parse(AGE_BASE + "max (age in area:b) <= 60\nmax (age in area:b) >= 1\n")
    assert puzzle.clues[0].holds(PLACEMENT, puzzle)  # nobody in an empty hall
    assert not puzzle.clues[1].holds(PLACEMENT, puzzle)


def test_age_clues_constrain_the_brute_force():
    text = AGE_BASE + "Ada in area:c\nBen in area:a\nsum (ages in area:a) = 54\n"
    (solution,) = bruteforce.solutions(text, "rooms", limit=2)
    assert solution["Cleo"] == "living room"
    assert solution["Ben"] == "living room"


def test_age_clues_need_one_age_for_every_person():
    with pytest.raises(ValueError):
        rooms.parse(AGE_BASE.replace("Ada: 60\n", "") + "sum (ages in area:a) = 54\n")
    with pytest.raises(ValueError):
        rooms.parse(BASE.replace("Clues:\n", "Ages:\nZed: 40\n\nClues:\n") + "Ada in area:c\n")
    with pytest.raises(ValueError):
        rooms.parse(AGE_BASE.replace("Ben: 26\n", "Ben: 26\nBen: 26\n") + "Ada in area:c\n")


def test_the_picture_prints_the_ages_above_the_clues():
    puzzle = rooms.parse(AGE_BASE + "Ada in area:c\n")
    image = picture.rooms_picture(puzzle, cell=60).to_svg()
    assert "Ada 60" in image


def test_a_group_count_speaks_for_all_its_rooms_together():
    """A count over a tag covers every room of the group, so it reads as a group."""
    group = with_words(
        BASE,
        "window: a room with a window | the rooms with a window",
        "clock: a room with a clock | the rooms with a clock",
    )
    puzzle = rooms.parse(group + "Clues:\ncount (people in area:window) >= 2\n")
    assert puzzle.sentence(1) == "The rooms with a window hold at least two people together."
    assert puzzle.areas("window") == ("a", "c", "e")
    single = rooms.parse(group + "Clues:\ncount (people in area:a) = 1\n")
    assert single.sentence(1) == "The living room holds exactly one person."
    membership = rooms.parse(group + "Clues:\nBen in area:window\n")
    assert membership.sentence(1) == "Ben is in a room with a window."


def test_a_group_count_falls_back_to_its_tag_name_and_dutch_reads_right():
    text = with_words(
        BASE.replace("Language: en", "Language: nl"),
        "window: een kamer met een raam | de kamers met een raam",
    )
    puzzle = rooms.parse(text + "Clues:\ncount (people in area:window) = 0\n")
    assert puzzle.sentence(1) == "De kamers met een raam zijn leeg."
    puzzle = rooms.parse(text + "Clues:\ncount (people in area:window) >= 1\n")
    assert puzzle.sentence(1) == "De kamers met een raam zijn niet leeg."
    plain = rooms.parse(
        BASE.replace("Language: en", "Language: nl") + "Clues:\ncount (people in area:e) >= 1\n"
    )
    assert plain.sentence(1) == "De attic is niet leeg."


def test_an_area_that_may_not_be_empty_reads_as_such():
    puzzle = rooms.parse(puzzle_with("count (people in area:a) >= 1\n"))
    assert puzzle.sentence(1) == "The living room is not empty."
    group = with_words(BASE, "window: a room with a window | the rooms with a window")
    puzzle = rooms.parse(group + "Clues:\ncount (people in area:window) >= 1\n")
    assert puzzle.sentence(1) == "The rooms with a window are not empty."
