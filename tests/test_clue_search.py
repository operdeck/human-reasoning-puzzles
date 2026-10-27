"""The clue search helpers used to thin and complete Murdoku clue sets."""

import re

from csp import bruteforce, clue_search
from csp.puzzlefile import load_board
from tests.examples import example

ORIENT = example("murdoku_orient_express.txt").read_text()


def test_with_clues_round_trips_the_clue_section():
    lines = clue_search.clue_lines(ORIENT)
    assert len(lines) == 12
    assert clue_search.clue_lines(clue_search.with_clues(ORIENT, lines)) == lines
    fewer = clue_search.with_clues(ORIENT, lines[:3])
    assert clue_search.clue_lines(fewer) == lines[:3]
    assert "Title:" in fewer and "Reveal:" in fewer


def test_outcome_reports_unique_solution_and_grade():
    result = clue_search.outcome(ORIENT, timeout=30)
    assert result.solutions == 1
    assert result.grade == "relations"
    assert result.good


def test_removal_report_and_thin_keep_the_puzzle_unique():
    report = clue_search.removal_report(ORIENT, timeout=30)
    assert [number for number, _, _ in report] == list(range(1, 13))
    removable = [number for number, _, result in report if result.good]
    assert removable == [2, 3]  # only by making the puzzle harder
    assert {report[n - 1][2].grade for n in removable} == {"what_if"}
    lines = clue_search.clue_lines(ORIENT)
    assert clue_search.thin(ORIENT, max_grade="relations", timeout=30) == lines
    padded = clue_search.with_clues(ORIENT, [*lines, "in_region Svetlana coupe_2"])
    assert clue_search.thin(padded, max_grade="relations", timeout=30) == lines


def test_candidate_clues_are_true_of_the_placement_and_skip_excluded_people():
    board, _ = load_board(ORIENT)
    (solution,) = bruteforce.solutions(ORIENT)
    placement = {person: solution[person] for person in board.people}
    found = clue_search.candidate_clues(board, placement, exclude=["Svetlana"])
    assert "in_region Ludmila coupe_1" in found
    assert "in_region Ludmila coupe_2" not in found
    assert not any("Svetlana" in clue for clue in found)


def test_suggest_restores_a_dropped_clue_set():
    lines = clue_search.clue_lines(ORIENT)
    (solution,) = bruteforce.solutions(ORIENT)
    board, _ = load_board(ORIENT)
    placement = {person: solution[person] for person in board.people}
    start = clue_search.with_clues(ORIENT, lines[:4])
    added = clue_search.suggest(start, placement, sample=200, timeout=30)
    completed = clue_search.with_clues(start, lines[:4] + added)
    assert len(bruteforce.solutions(completed, limit=2)) == 1


def test_parse_solution_reads_one_based_squares():
    placement = clue_search.parse_solution("Ada=r1c2, Ben=r3c4")
    assert (placement["Ada"].row, placement["Ada"].col) == (0, 1)
    assert (placement["Ben"].row, placement["Ben"].col) == (2, 3)


def test_suggest_keeps_needed_clues_necessary():
    opener = example("wie-doet-het-met-wie-1.txt").read_text()
    lines = clue_search.clue_lines(opener)
    assert lines[0].startswith("above object:badjas object:sloffen 1")
    start = clue_search.with_clues(opener, lines[:2])
    placement = clue_search.parse_solution("Wouter=r1c1 Marloes=r2c2 Bas=r3c4 Cato=r4c3 Daan=r5c5")
    kinds = [kind for kind in clue_search.SUGGEST_KINDS if kind != "on"]
    added = clue_search.suggest(
        start, placement, kinds, sample=300, timeout=30, exclude=["Wouter"], needs=[1]
    )
    final = clue_search.with_clues(start, [*lines[:2], *added])
    assert len(bruteforce.solutions(final)) == 1
    without = clue_search.with_clues(start, [lines[1], *added])
    assert len(bruteforce.solutions(without)) > 1


def test_occupancy_shows_unused_decoys():
    beach = example("wie-doet-het-met-wie-3.txt").read_text()
    seen, rows = clue_search.occupancy(clue_search.with_clues(beach, []), sample=2000)
    assert 0 < seen < 2000
    used = {(name, square): times for name, square, times in rows}
    # Without clues the sunglasses on r2c3 and on r4c4 are both still possible.
    assert used["zonnebril", "r2c3"] > 0 and used["zonnebril", "r4c4"] > 0


def test_suggest_keeps_each_needed_clue_necessary():
    hotel = example("wie-doet-het-met-wie-5.txt").read_text()
    rule = "alone_with Wouter object:badjas"
    work = re.sub(r"^alone_with Wouter object:badjas \|.*$", "alone_with Wouter", hotel, flags=re.M)
    key = clue_search.clue_lines(hotel)[0]
    start = clue_search.with_clues(work, [rule, key])
    placement = clue_search.parse_solution(
        "Wouter=r1c2 Sven=r2c7 Hanneke=r3c1 Mieke=r4c5 Ruud=r5c4 Jeroen=r6c3 Karin=r7c6"
    )
    kinds = [kind for kind in clue_search.SUGGEST_KINDS if kind != "on"]
    added = clue_search.suggest(
        start, placement, kinds, sample=2000, timeout=30, exclude=["Wouter"], needs=[1, 2]
    )
    assert len(bruteforce.solutions(clue_search.with_clues(start, [rule, key, *added]))) == 1
    for dropped in (rule, key):
        rest = [line for line in (rule, key) if line != dropped]
        assert len(bruteforce.solutions(clue_search.with_clues(start, [*rest, *added]))) > 1
