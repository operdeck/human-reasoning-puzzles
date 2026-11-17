"""The Murdoku board generator: filters, templates, spec reading and drafts."""

import random
from pathlib import Path

import pytest

from csp import audit, clue_search
from csp import murdoku_board as mb
from csp.bruteforce import murdoku as brute
from csp.bruteforce import murdoku_expr as expression_brute
from csp.murdoku_expression_file import keyed_expression_clue_numbers, load_expression_board

SPEC = """theme: test
size: 5
areas: West East North
colours: West=#F6E3A1  # sandy
people: Ann Bob Cas Dee
late: Dee
companions: Ann
object: rots blocking x2
object: kruk standable x1
key_clue: not Ann beside object:rots
candidates: 2
keep: 2
seed: 3
"""


def test_read_spec_keeps_hex_colours_and_drops_comments():
    spec = mb.read_spec(SPEC)
    assert spec.expressions
    assert spec.colours == {"West": "#F6E3A1"}
    assert spec.companions == ("Ann",)
    assert [(o.name, o.kind, o.count) for o in spec.objects] == [
        ("rots", "blocking", 2),
        ("kruk", "standable", 1),
    ]


@pytest.mark.parametrize("name", ["japan-6x6", "vietnam-5x5", "vietnam-6x6", "vietnam-7x7"])
def test_published_specs_use_expression_key_clues_by_default(name):
    source = Path(__file__).parents[1] / "specs" / "murdoku" / f"{name}.txt"
    spec = mb.read_spec(source.read_text())
    assert spec.expressions and spec.key_clues


def test_read_spec_accepts_only_declared_decorative_objects():
    spec = mb.read_spec(SPEC + "decor: kruk\n")
    assert spec.decor == ("kruk",)
    with pytest.raises(ValueError, match="decor names unknown objects"):
        mb.read_spec(SPEC + "decor: lantern\n")
    with pytest.raises(ValueError, match=r"key clue .* decorative objects"):
        mb.read_spec(SPEC + "decor: rots\n")


def test_expression_spec_uses_ast_for_late_and_decor_exclusions():
    text = SPEC
    spec = mb.read_spec(text + "decor: kruk\n", expressions=True)
    assert spec.expressions
    with pytest.raises(ValueError, match="names the late figure"):
        mb.read_spec(text + "key_clue: (Dee in rows:1) or (Ann in rows:1)\n", expressions=True)
    with pytest.raises(ValueError, match="decorative objects"):
        mb.read_spec(
            text + "decor: kruk\nkey_clue: (Ann on object:kruk) or (Bob in rows:1)\n",
            expressions=True,
        )


def test_expression_late_rule_matches_legacy_placement_semantics():
    text = SPEC.replace("key_clue: not Ann beside object:rots\n", "")
    spec = mb.read_spec(text, expressions=False)
    expression_spec = mb.read_spec(text, expressions=True)
    layout = ((0, 0, 0, 1, 1),) * 2 + ((0, 0, 2, 1, 1),) * 3
    colours = ["#F4CBC3", "#CBE6B9", "#C4DCF2"]
    legacy = mb.draft_text(spec, layout, colours, [])
    expression = mb.draft_text(expression_spec, layout, colours, [])
    base = mb.draft_text(spec, layout, colours, [], rules=False)
    for placement in brute.solutions(base, 1000):
        assert mb._accepts(legacy, placement, False) == mb._accepts(expression, placement, True)


def test_expression_board_candidate_and_close():
    text = SPEC
    spec = mb.read_spec(text + "decor: kruk\n", expressions=True)
    item = mb.candidate(spec, 0)
    assert item is not None
    assert mb._accepts(item.text, item.placement, True)
    closed = mb.close(spec, item)
    board, rules, clues = load_expression_board(closed.text)
    assert keyed_expression_clue_numbers(closed.text) == {1}
    found = expression_brute.solutions(board, clues, 2, rules=rules)
    assert item.placement in found
    assert len(found) == 2
    assert "not closed (several" in closed.closing
    assert mb._accepts(closed.text, item.placement, True)
    assert not clue_search._unnamed(
        board.people, clue_search.clue_lines(closed.text), ("Dee",), expressions=True
    )
    assert rules and clues


@pytest.mark.parametrize(
    "line, problem",
    [
        ("key_clue: Dee beside object:rots", "names the late figure"),
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
    board, rules, clues = load_expression_board(first.text)
    assert expression_brute.accepts(board, clues, first.placement, rules=rules)
    dee = board.region_of(first.placement["Dee"])
    others = {p for p, sq in first.placement.items() if p != "Dee" and board.region_of(sq) == dee}
    assert others == {"Ann"}


def test_candidate_skips_layouts_already_in_the_collection():
    spec = mb.read_spec(SPEC)
    original = mb.candidate(spec, 0)
    assert original is not None
    original_layout = audit.layout_key(original.text, "murdoku")
    rejected: dict[str, int] = {}
    replacement = mb.candidate(
        spec,
        0,
        rejected,
        lambda text: audit.layout_key(text, "murdoku") == original_layout,
    )
    assert replacement is not None
    assert audit.layout_key(replacement.text, "murdoku") != original_layout
    assert rejected["layout already in the collection"] > 0


def test_close_adds_clues_that_leave_the_late_figure_out():
    spec = mb.read_spec(SPEC + "decor: kruk\n")
    first = mb.candidate(spec, 0)
    assert first is not None
    closed = mb.close(spec, first)
    assert closed.closing.startswith(f"{len(clue_search.clue_lines(closed.text)) - 1} clues added")
    assert "# Suggested clues:" in closed.text
    assert keyed_expression_clue_numbers(closed.text) == {1}
    assert not any("Dee" in line.split() for line in clue_search.clue_lines(closed.text))
    assert all("object:kruk" not in line.split() for line in clue_search.clue_lines(closed.text))
    board, rules, clues = load_expression_board(closed.text)
    assert expression_brute.accepts(board, clues, closed.placement, rules=rules)


def test_a_key_clue_that_rules_nothing_out_is_rejected():
    spec = mb.read_spec(SPEC.replace("not Ann beside object:rots", "Ann in area:West,East,North"))
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


def test_board_cli_closes_expression_drafts_without_a_language_flag(tmp_path):
    from csp.puzzle_lab import main

    source = tmp_path / "theme.txt"
    source.write_text(SPEC.replace("candidates: 2", "candidates: 1"))
    output = tmp_path / "drafts"
    assert (
        main(["murdoku-board", str(source), "--output", str(output), "--no-pictures", "--suggest"])
        == 0
    )
    (draft,) = output.glob("*-c*.txt")
    _, rules, clues = load_expression_board(draft.read_text())
    assert rules and clues
    assert keyed_expression_clue_numbers(draft.read_text()) == {1}
