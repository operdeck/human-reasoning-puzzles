"""The clue search helpers used to thin and complete Murdoku clue sets."""

import multiprocessing
import time

import pytest

from csp import bruteforce, clue_search
from csp.bruteforce import murdoku_expr
from csp.murdoku_expression_file import load_expression_board
from csp.murdoku_lang import format_statement
from tests.examples import example

pytestmark = pytest.mark.solutions

SOLUTION_1 = "Alba=r1c5 Bernardo=r2c1 Carmen=r3c3 Diego=r4c6 Fernando=r5c2 Elena=r6c4"

ORIENT = example("murdoku_orient_express.txt").read_text()


def _count(text, limit=2):
    return len(bruteforce.solutions(text, limit=limit))


def test_with_clues_round_trips_the_clue_section():
    lines = clue_search.clue_lines(ORIENT)
    assert len(lines) == 12
    assert clue_search.clue_lines(clue_search.with_clues(ORIENT, lines)) == lines
    fewer = clue_search.with_clues(ORIENT, lines[:3])
    assert clue_search.clue_lines(fewer) == lines[:3]
    assert "Title:" in fewer and "Reveal:" in fewer


def test_outcome_reports_unique_solution_and_grade():
    result = clue_search.outcome(ORIENT, timeout=90)
    assert result.solutions == 1
    assert result.grade == "relations"
    assert result.good


@pytest.mark.skipif("fork" not in multiprocessing.get_all_start_methods(), reason="fork-only stubs")
def test_outcome_times_each_solver_separately_and_preserves_a_completed_count(monkeypatch):
    def solutions(_text, _limit):
        time.sleep(0.6)
        return [{}]

    def grade(_text, _late_person):
        time.sleep(0.6)
        return "count", None

    monkeypatch.setattr(clue_search.brute, "solutions", solutions)
    monkeypatch.setattr(clue_search, "_measure", grade)
    assert clue_search.outcome("", timeout=1) == clue_search.Outcome(1, "count")

    def slow_grade(_text, _late_person):
        time.sleep(2)
        return "count", None

    monkeypatch.setattr(clue_search, "_measure", slow_grade)
    assert clue_search.outcome("", timeout=1) == clue_search.Outcome(1, None)


def test_outcome_checks_that_the_late_figure_is_resolved_last():
    menu = example("menu-murdoku-1.txt").read_text()
    result = clue_search.outcome(menu, timeout=60, late_person="Vla")
    assert result.good
    assert result.late_last
    assert not clue_search.outcome(menu, timeout=60, late_person="Aardappel").late_last
    assert clue_search.outcome(menu, timeout=60).late_last is None


def test_removal_report_and_thin_keep_the_puzzle_unique():
    # A small puzzle keeps this quick: each trial is a solve in a child process.
    zoo = example("zoo-murdoku-1.txt").read_text()
    report = clue_search.removal_report(zoo, timeout=60)
    assert [number for number, _, _ in report] == list(range(1, 8))
    removable = [number for number, _, result in report if result.good]
    assert removable == [4, 5, 6]  # only by making the puzzle harder
    assert [report[n - 1][2].grade for n in removable] == ["what_if", "subsumption", "what_if"]
    lines = clue_search.clue_lines(zoo)
    assert clue_search.thin(zoo, max_grade="relations", timeout=60) == lines
    padded = clue_search.with_clues(zoo, [*lines, "Gibbon in area:bergen"])
    assert clue_search.thin(padded, max_grade="relations", timeout=60) == lines


def test_suggest_restores_a_dropped_clue_set():
    house = example("murdoku_3_house.txt").read_text()
    lines = clue_search.clue_lines(house)
    (solution,) = bruteforce.solutions(house)
    board = load_expression_board(house)[0]
    placement = {person: solution[person] for person in board.people}
    start = clue_search.with_clues(house, lines[:2])
    added = clue_search.suggest(start, placement, sample=50, timeout=10)
    completed = clue_search.with_clues(start, lines[:2] + added)
    assert _count(completed) == 1


def test_suggest_with_cover_names_everyone():
    house = example("murdoku_3_house.txt").read_text()
    board = load_expression_board(house)[0]
    (solution,) = bruteforce.solutions(house)
    placement = {person: solution[person] for person in board.people}
    start = clue_search.with_clues(house, [])
    candidates = [
        format_statement(statement)
        for statement in clue_search.expression_candidate_clues(board, placement)
    ]
    target = next(
        name
        for name in sorted(board.object_names)
        if any(f"object:{name}" in clue.split() for clue in candidates)
    )
    added = clue_search.suggest(
        start, placement, sample=200, timeout=30, cover=True, exclude_targets=[target]
    )
    assert not clue_search._unnamed(board.people, added, (), expressions=True)
    assert all(f"object:{target}" not in clue.split() for clue in added)
    assert _count(clue_search.with_clues(start, added)) == 1


def test_parse_solution_reads_one_based_squares():
    placement = clue_search.parse_solution("Ada=r1c2, Ben=r3c4")
    assert (placement["Ada"].row, placement["Ada"].col) == (0, 1)
    assert (placement["Ben"].row, placement["Ben"].col) == (2, 3)


def test_suggest_keeps_needed_clues_necessary():
    opener = example("wie-doet-het-met-wie-1.txt").read_text()
    lines = clue_search.clue_lines(opener)
    assert lines[0].startswith("some (people on object:badjas) dir:up")
    start = clue_search.with_clues(opener, lines[:2])
    placement = clue_search.parse_solution("Wouter=r1c1 Marloes=r2c2 Bas=r3c4 Cato=r4c3 Daan=r5c5")
    kinds = [kind for kind in clue_search.SUGGEST_KINDS if kind != "on"]
    added = clue_search.suggest(
        start, placement, kinds, sample=50, timeout=15, exclude=["Wouter"], needs=[1]
    )
    final = clue_search.with_clues(start, [*lines[:2], *added])
    assert _count(final) == 1
    without = clue_search.with_clues(start, [lines[1], *added])
    assert _count(without) > 1


@pytest.mark.parametrize(
    ("effect", "placement"),
    [
        ("alone", "Ada=r1c1 Ben=r2c3 Cal=r3c2"),
        ("not_alone", "Ada=r1c1 Ben=r2c2 Cal=r3c3"),
    ],
)
def test_suggest_keeps_mark_occupancy_condition_necessary(effect, placement):
    text = f"""Size: 3
Regions:
a: alcove
b: hall
Grid:
a b b
b a b
b b b
People:
Ada
Ben
Cal
Marks:
quiet: r1c1 ; {effect}
Clues:
count (people on mark:quiet) = 1
Ada in rows:1
"""
    placement = clue_search.parse_solution(placement)
    board = load_expression_board(text)[0]
    offered = clue_search.expression_candidate_clues(board, placement, ["in"])
    assert "Ada in corner:board" in [format_statement(statement) for statement in offered]
    added = clue_search.suggest(text, placement, kinds=["line"], needs_marks=["quiet"], sample=100)
    final = clue_search.with_clues(text, [*clue_search.clue_lines(text), *added])
    assert _count(final) == 1
    without = clue_search.without_mark_condition(final, "quiet")
    assert _count(without) > 1
    assert "quiet: r1c1\n" in without
    with pytest.raises(ValueError, match="no occupancy condition"):
        clue_search.without_mark_condition(without, "quiet")


def test_needs_mark_is_rejected_for_commands_that_cannot_enforce_it(capsys):
    with pytest.raises(SystemExit) as error:
        clue_search.main(["thin", "unused.txt", "--needs-mark", "quiet"])
    assert error.value.code == 2
    assert "--needs-mark is supported only by suggest and ease" in capsys.readouterr().err


def test_ease_does_not_make_an_occupancy_condition_redundant(monkeypatch):
    text = """Size: 3
Regions:
a: alcove
b: hall
Grid:
a b b
b a b
b b b
People:
Ada
Ben
Cal
Marks:
quiet: r1c1 ; alone
Clues:
count (people on mark:quiet) = 1
Ada in rows:1
Ben in rows:2
"""
    placement = clue_search.parse_solution("Ada=r1c1 Ben=r2c3 Cal=r3c2")
    assert _count(text) == 1
    assert _count(clue_search.without_mark_condition(text, "quiet")) > 1
    monkeypatch.setattr(
        clue_search,
        "expression_candidate_clues",
        lambda *args: [clue_search.parse_statement("Ben in columns:3")],
    )
    monkeypatch.setattr(
        clue_search, "outcome", lambda *args, **kwargs: clue_search.Outcome(1, "what_if")
    )
    assert clue_search.ease(text, placement, "relations", needs_marks=["quiet"]) == []
    redundant = clue_search.with_clues(text, [*clue_search.clue_lines(text), "Ben in columns:3"])
    with pytest.raises(ValueError, match="not necessary"):
        clue_search.ease(redundant, placement, "relations", needs_marks=["quiet"])


def test_occupancy_shows_unused_decoys():
    beach = example("wie-doet-het-met-wie-3.txt").read_text()
    seen, rows = clue_search.occupancy(clue_search.with_clues(beach, []), sample=2000)
    assert 0 < seen < 2000
    used = {(name, square): times for name, square, times in rows}
    # Without clues the sunglasses on r2c3 and on r4c4 are both still possible.
    assert used["zonnebril", "r2c3"] > 0 and used["zonnebril", "r4c4"] > 0


def test_sample_spreads_over_the_search_space():
    # The first solutions of one search share their early choices; a clue that
    # rules them out looks perfect to `suggest` while ruling out little else.
    text = clue_search.with_clues(example("halloween-museum-1.txt").read_text(), [])
    board, rules, clues = load_expression_board(text)
    first = murdoku_expr.solutions(board, clues, 40, rules=rules)
    spread = murdoku_expr.sample(board, clues, 40, rules=rules)
    assert len(spread) == 40
    assert len({tuple(sorted(map(str, s.items()))) for s in spread}) == 40

    def squares(found):
        return len({(person, str(square)) for s in found for person, square in s.items()})

    assert squares(spread) > squares(first)


def test_sample_never_hides_a_second_solution():
    puzzle = example("halloween-museum-1.txt").read_text()
    lines = clue_search.clue_lines(puzzle)
    for number in range(len(lines) + 1):
        fewer = clue_search.with_clues(puzzle, lines[:number] + lines[number + 1 :])
        board, rules, clues = load_expression_board(fewer)
        several = len(murdoku_expr.solutions(board, clues, 2, rules=rules)) > 1
        assert (len(murdoku_expr.sample(board, clues, 40, rules=rules)) > 1) == several


def test_mentions_counts_each_person_once_per_clue():
    counts = clue_search._mentions(
        ["Ada", "Ben", "Cy"],
        ["Ada dir:left Ben", "Ada beside object:Ada_bench | Ada sits", "Ben on object:bed"],
        expressions=True,
    )
    assert counts == {"Ada": 2, "Ben": 2, "Cy": 0}


def test_accepts_checks_role_rules():
    # `suggest --needs` finds the rivals of a role rule with `accepts`.
    hotel = example("murder-hotel-1.txt").read_text()
    board, rules, _clues = load_expression_board(hotel)
    loose_rules = [rule for rule in rules if "murderer" not in format_statement(rule)]
    assert len(loose_rules) < len(rules)
    found = [
        clue_search._placement(f, board.people)
        for f in murdoku_expr.sample(board, [], 60, rules=loose_rules)
    ]
    assert any(not murdoku_expr.accepts(board, [], placement, rules=rules) for placement in found)
    assert all(murdoku_expr.accepts(board, [], placement, rules=loose_rules) for placement in found)


def test_suggest_keeps_a_role_rule_necessary():
    museum = example("halloween-museum-1.txt").read_text()
    rule = "every ?a in tag:crime_scene: some role:murderer in ?a"
    start = clue_search.with_clues(museum.replace(rule + "\n", ""), [rule])
    placement = clue_search.parse_solution(SOLUTION_1)
    added = clue_search.suggest(start, placement, sample=200, exclude=["Carmen"], needs=[1])
    assert _count(clue_search.with_clues(start, [rule, *added])) == 1
    assert _count(clue_search.with_clues(start, added)) > 1
