"""Tests for the browser export: one JSON bundle and one interactive board per puzzle."""

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("fontTools")

from csp import cli, murdoku, story, svg

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    assert cli.main([str(EXAMPLES / "*.txt"), "--export", str(out)]) == 0
    return out


def _bundle(out: Path, name: str) -> dict:
    return json.loads((out / f"{name}.json").read_text())


def test_every_example_is_exported_and_indexed(exported):
    index = json.loads((exported / "index.json").read_text())
    names = sorted(path.stem for path in EXAMPLES.glob("*.txt"))
    assert sorted(entry["id"] for entry in index["puzzles"]) == names
    assert "rights reserved" in index["license"]
    for name in names:
        assert (exported / f"{name}.svg").is_file()
        assert _bundle(exported, name)["static"] == f"{name}.svg"
    assert not list(exported.glob("*-solution.svg"))


def test_every_playable_cell_is_on_the_board(exported):
    for path in exported.glob("*.json"):
        if path.name == "index.json":
            continue
        bundle = json.loads(path.read_text())
        if not bundle["playable"]:
            continue
        rows, cols = bundle["size"]
        ids = set(svg.ids((exported / bundle["static"]).read_text()))
        board = {f"r{r}c{c}" for r in range(1, rows + 1) for c in range(1, cols + 1)}
        assert board <= ids, bundle["id"]
        cells = (
            set(bundle["solution"]) | set(bundle["givens"]) | set(bundle["placement"]["blocked"])
        )
        assert cells <= board, bundle["id"]
        items = {item["id"] for item in bundle["palette"]}
        assert set(bundle["solution"].values()) <= items, bundle["id"]
        for cell, given in bundle["givens"].items():
            assert bundle["solution"].get(cell, given) == given, bundle["id"]


def test_murdoku_bundle_has_everything_to_play(exported):
    bundle = _bundle(exported, "murdoku_intro")
    assert bundle["family"] == "murdoku"
    assert bundle["playable"]
    assert bundle["placement"]["perItem"] == 1
    assert [item["id"] for item in bundle["palette"]] == ["Ingrid", "Joost", "Lotte", "Wouter"]
    assert bundle["solution"] == {
        "r1c1": "Joost",
        "r2c3": "Wouter",
        "r3c4": "Ingrid",
        "r4c2": "Lotte",
    }
    assert bundle["clues"][0] == "Ingrid is on a chair."
    assert bundle["question"]
    assert bundle["rules"]
    names = [condition["name"] for condition in bundle["conditions"]]
    assert names == ["on", "next to"]


def test_dutch_murdoku_is_worded_in_dutch(exported):
    bundle = _bundle(exported, "zoo-murdoku-1")
    assert bundle["language"] == "nl"
    assert bundle["headings"]["clues"] == "Aanwijzingen"
    assert bundle["headings"]["conditions"] == "Voorwaarden"
    assert all(item["svg"].startswith("<svg") for item in bundle["palette"])


def test_logic_grids_are_listed_but_not_playable(exported):
    bundle = _bundle(exported, "logicgrid_3x3")
    assert not bundle["playable"]
    assert bundle["unsupported"]


def test_export_fails_when_a_puzzle_cannot_be_exported(tmp_path, capsys):
    broken = tmp_path / "broken.txt"
    broken.write_text("this is not a puzzle\n")
    assert (
        cli.main([str(EXAMPLES / "tents_4x4.txt"), str(broken), "--export", str(tmp_path / "site")])
        == 1
    )
    assert "broken.txt" in capsys.readouterr().err


def test_every_murdoku_clue_kind_has_a_condition_in_both_languages():
    kinds = (
        set(murdoku.FILTERS)
        | set(murdoku.RELATIONS)
        | set(murdoku.GROUP_CLUES)
        | set(murdoku.ROLE_CONDITION_KINDS)
        | {"exactly", "count", "alone_with", "only_on", "unique_attribute", "at", "on", "on_mark"}
    )
    assert kinds <= set(story.CONDITION_KEYS)
    for language in ("en", "nl"):
        for key in set(story.CONDITION_KEYS.values()):
            assert f"cond.{key}" in story.PHRASES[language]
            assert f"cond.{key}.name" in story.PHRASES[language]


def test_conditions_only_list_the_kinds_a_puzzle_uses():
    text = (EXAMPLES / "murdoku_intro.txt").read_text()
    used = {kind for kind, _ in re.findall(r"^\s*(\w+)\s+(.*)$", text, re.M)}
    assert len(story.condition_list(text)) <= len(used)


def test_digit_puzzles_get_pencil_marks_and_peer_groups(exported):
    bundle = _bundle(exported, "sudoku_4x4")
    assert bundle["notes"] is True
    assert bundle["autoMark"]["default"] is True
    groups = [frozenset(group["cells"]) for group in bundle["peers"]]
    rows = [frozenset(f"r{r}c{c}" for c in range(1, 5)) for r in range(1, 5)]
    cols = [frozenset(f"r{r}c{c}" for r in range(1, 5)) for c in range(1, 5)]
    assert set(rows + cols) <= set(groups)
    assert len(groups) == len(set(groups)) == 12
    assert all("items" not in group for group in bundle["peers"])


def test_anti_knight_pairs_are_peers(exported):
    groups = {frozenset(group["cells"]) for group in _bundle(exported, "sudoku_anti_4x4")["peers"]}
    assert frozenset({"r1c1", "r2c3"}) in groups


def test_akari_lights_what_a_bulb_sees(exported):
    bundle = _bundle(exported, "akari_2x2")
    assert "notes" not in bundle
    assert bundle["autoMark"] == {"default": True, "mark": "light", "onPlace": [{"scope": "peers"}]}
    # Only lines of sight, never the cells around a numbered wall.
    assert sorted(sorted(group["cells"]) for group in bundle["peers"]) == [
        ["r1c1", "r2c1"],
        ["r2c1", "r2c2"],
    ]


def test_placement_puzzles_without_at_most_one_rules_get_no_peers(exported):
    bundle = _bundle(exported, "murdoku_intro")
    assert "peers" not in bundle
    assert "notes" not in bundle
