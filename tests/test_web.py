"""Tests for the browser export: one JSON bundle and one interactive board per puzzle."""

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("fontTools")

from csp import cli, murdoku, story, svg
from tests.examples import EXAMPLES, example, played_examples


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    assert cli.main([str(EXAMPLES / "**" / "*.txt"), "--export", str(out)]) == 0
    return out


def _bundle(out: Path, name: str) -> dict:
    return json.loads((out / f"{name}.json").read_text())


def test_every_example_is_exported_and_indexed(exported):
    index = json.loads((exported / "index.json").read_text())
    names = sorted(path.stem for path in played_examples())
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
    assert bundle["clues"][0] == "Ingrid zit op een stoel."
    assert bundle["question"]
    assert bundle["reveal"].startswith("Wouter doet het met Ingrid")
    assert bundle["rules"]
    names = [condition["name"] for condition in bundle["conditions"]]
    assert names == ["op", "naast"]


def test_murdoku_bundle_lists_its_objects_with_pictures(exported):
    bundle = _bundle(exported, "zoo-murdoku-1")
    assert bundle["headings"]["objects"] == "De voorwerpen"
    objects = bundle["objects"]
    assert objects and all(item["svg"].startswith("<svg") for item in objects)
    assert {item["text"] for item in objects} <= {"hier kun je op staan", "hier kan niemand staan"}


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


def test_display_aliases_keep_their_labels_and_rules(exported):
    dog = _bundle(exported, "dogdoku_5x5")
    assert dog["family"] == "queens"
    assert dog["familyLabel"] == "DogDoku"
    assert "one dog" in dog["rules"][0]

    tango = _bundle(exported, "tango_4x4")
    assert tango["family"] == "binairo"
    assert tango["familyLabel"] == "Tango"
    assert "= signs" in tango["rules"][0]

    binairo = _bundle(exported, "binairo_4x4")
    assert binairo["familyLabel"] == "Binairo"


def test_kakurasu_and_counts_only_battleships_rules_are_precise(exported):
    kakurasu = _bundle(exported, "kakurasu_4x4")
    assert "column number to the row sum" in kakurasu["rules"][0]
    assert "row number to the column sum" in kakurasu["rules"][0]

    battleships = _bundle(exported, "battleships_counts_4x4")
    assert "does not model ship shapes" in battleships["rules"][0]


def test_export_fails_when_a_puzzle_cannot_be_exported(tmp_path, capsys):
    broken = tmp_path / "broken.txt"
    broken.write_text("this is not a puzzle\n")
    assert (
        cli.main([str(example("tents_4x4.txt")), str(broken), "--export", str(tmp_path / "site")])
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
    text = (example("murdoku_intro.txt")).read_text()
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


def test_export_refuses_two_puzzles_with_the_same_name(tmp_path, capsys):
    other = tmp_path / "copy"
    other.mkdir()
    (other / "tents_4x4.txt").write_text((example("tents_4x4.txt")).read_text())
    files = [str(example("tents_4x4.txt")), str(other / "tents_4x4.txt")]
    assert cli.main([*files, "--export", str(tmp_path / "site")]) == 2
    assert "tents_4x4" in capsys.readouterr().err
    assert not (tmp_path / "site").exists()


def test_index_is_numbered_in_reading_order_with_category_sections(exported):
    puzzles = json.loads((exported / "index.json").read_text())["puzzles"]
    assert [entry["number"] for entry in puzzles] == list(range(1, len(puzzles) + 1))
    assert puzzles[0]["section"] == "Murdoku \u00b7 Demo"
    sections = list(dict.fromkeys(entry["section"] for entry in puzzles))
    assert "Murdoku \u00b7 Japanese food" in sections
    assert sections.index("Murdoku \u00b7 Wie doet het met wie") < sections.index("Akari")
    assert _bundle(exported, "food-murdoku-1")["section"] == "Murdoku \u00b7 Japanese food"
    assert "DogDoku" in sections and "Tango" in sections
