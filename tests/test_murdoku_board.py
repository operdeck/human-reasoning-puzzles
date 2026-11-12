"""The Murdoku board generator: filters, templates, spec reading and drafts."""

import random

import pytest

from csp import clue_search
from csp import murdoku_board as mb
from csp.bruteforce import murdoku as brute
from csp.puzzlefile import load_board

SPEC = """theme: test
size: 5
areas: West East North
colours: West=#F6E3A1  # sandy
people: Ann Bob Cas Dee
late: Dee
companions: Ann
object: rots blocking x2
object: kruk standable x1
key_clue: not_next_to Ann rots
candidates: 2
keep: 2
seed: 3
"""


def test_read_spec_keeps_hex_colours_and_drops_comments():
    spec = mb.read_spec(SPEC)
    assert spec.colours == {"West": "#F6E3A1"}
    assert spec.companions == ("Ann",)
    assert [(o.name, o.kind, o.count) for o in spec.objects] == [
        ("rots", "blocking", 2),
        ("kruk", "standable", 1),
    ]


@pytest.mark.parametrize(
    "line, problem",
    [
        ("key_clue: next_to Dee rots", "names the late figure"),
        ("late_extra: x", "unknown spec keys"),
        ("template: spiral", "template must be"),
    ],
)
def test_read_spec_rejects_bad_specs(line, problem):
    with pytest.raises(ValueError, match=problem):
        mb.read_spec(SPEC + line + "\n")


def test_area_problems_flag_small_and_disconnected_areas():
    split = ((0, 0, 1, 1), (0, 0, 1, 1), (1, 1, 1, 0), (1, 1, 1, 0))
    problems = mb.area_problems(split, min_area=4, max_ratio=3.0)
    assert any("is split" in p for p in problems)
    assert not mb.area_problems(((0, 0, 1, 1),) * 4, min_area=4, max_ratio=3.0)


def test_staircase_returns_none_when_the_bands_are_too_thin():
    rng = random.Random(1)
    assert mb.staircase(6, 4, rng) is None
    layout = mb.staircase(8, 3, rng)
    assert layout is not None and set(mb.area_cells(layout)) == {0, 1, 2}


def test_spread_counts_people_one_per_row_and_column():
    assert mb._spread({(0, 0), (0, 1), (0, 2)}) == 1
    assert mb._spread({(0, 0), (1, 1), (1, 0)}) == 2


def test_an_across_object_joins_exactly_two_areas():
    layout = ((0, 0, 1, 1),) * 3 + ((2, 2, 2, 2),)
    tunnel = mb.Placed("tunnel", "blocking", ((0, 1), (0, 2)), across=True)
    assert not mb.object_problems(layout, [tunnel])
    inside = mb.Placed("tunnel", "blocking", ((0, 0), (1, 0)), across=True)
    assert "tunnel does not join two areas" in mb.object_problems(layout, [inside])
    third = mb.Placed("tunnel", "blocking", ((2, 1), (2, 2)), across=True)
    assert "tunnel touches an area border" in mb.object_problems(layout, [third])
    spec = mb.read_spec(SPEC + "object: tunnel blocking across\n")
    placed = mb.place_objects(layout, spec, random.Random(0))
    assert placed is not None
    (cells,) = [p.cells for p in placed if p.name == "tunnel"]
    assert len({layout[r][c] for r, c in cells}) == 2
    with pytest.raises(ValueError, match="across needs"):
        mb.read_spec(SPEC + "object: tunnel blocking across in West\n")


def test_candidates_are_reproducible_and_satisfy_the_late_rule():
    spec = mb.read_spec(SPEC)
    first = mb.candidate(spec, 0)
    assert first is not None
    assert mb.candidate(spec, 0) == first
    assert brute.accepts(first.text, first.placement)
    board, _ = load_board(first.text)
    dee = board.region_of(first.placement["Dee"])
    others = {p for p, sq in first.placement.items() if p != "Dee" and board.region_of(sq) == dee}
    assert others == {"Ann"}


def test_close_adds_clues_that_leave_the_late_figure_out():
    spec = mb.read_spec(SPEC)
    first = mb.candidate(spec, 0)
    assert first is not None
    closed = mb.close(spec, first)
    assert closed.closing.startswith(f"{len(clue_search.clue_lines(closed.text)) - 1} clues added")
    assert "# Suggested clues:" in closed.text
    assert not any("Dee" in line.split() for line in clue_search.clue_lines(closed.text))
    assert brute.accepts(closed.text, closed.placement)


def test_a_key_clue_that_rules_nothing_out_is_rejected():
    spec = mb.read_spec(SPEC.replace("not_next_to Ann rots", "in_region Ann West East North"))
    tally: dict[str, int] = {}
    assert mb.candidate(spec, 0, tally) is None
    assert tally.get("key clue rules nothing out")


def test_write_refuses_to_overwrite(tmp_path):
    spec = mb.read_spec(SPEC)
    report = mb.generate(spec)
    paths = mb.write(report, spec, tmp_path, pictures=False)
    assert any(p.name.endswith("-report.txt") for p in paths)
    with pytest.raises(FileExistsError):
        mb.write(report, spec, tmp_path, pictures=False)
