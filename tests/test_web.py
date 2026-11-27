"""Tests for the browser export: one JSON bundle and one interactive board per puzzle."""

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("fontTools")

from csp import cli, icons, murdoku, story, svg, web
from csp.murdoku_expression_file import load_expression_board
from csp.puzzlefile import load_presentation
from tests.examples import EXAMPLES, example, played_examples

pytestmark = pytest.mark.solutions


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    assert cli.main([str(EXAMPLES / "**" / "*.txt"), "--export", str(out)]) == 0
    return out


def _bundle(out: Path, name: str) -> dict:
    return json.loads((out / f"{name}.json").read_text())


# The `examples/` puzzles this solver only closes with its `what_if` fallback, so
# no deduction path exists: the beyond-deduction frontier. Keep in step with the ladder.
BEYOND_DEDUCTION = {
    "arrow_4_6x6",
    "binairo_3_4x4",
    "calcudoku_6_6x6",
    "killer_5_6x6",
    "skyscrapersudoku_3_6x6",
    "food-murdoku-3",
    "menu-murdoku-3",
    "prrrdoku2",
    "pattern_4_10x10",
    "prrrdoku3",
    "rooms_3_6x8",
    "tamagotchi-murdoku-12x12",
    "tamagotchi-murdoku-9x9",
    "tango_4_4x4",
    "tents_3_4x4",
    "undead_6_5x5",
}


def test_every_example_is_exported_and_indexed(exported):
    index = json.loads((exported / "index.json").read_text())
    names = sorted(path.stem for path in played_examples())
    assert sorted(entry["id"] for entry in index["puzzles"]) == names
    assert "rights reserved" in index["license"]
    for name in names:
        assert (exported / f"{name}.svg").is_file()
        assert _bundle(exported, name)["static"] == f"{name}.svg"
    for entry in index["puzzles"]:
        assert entry["static"] == _bundle(exported, entry["id"])["static"]
        preview = exported / entry["static"]
        assert preview.is_file()
        assert "<svg" in preview.read_text()
    assert not list(exported.glob("*-solution.svg"))


@pytest.mark.parametrize(
    "name",
    [
        "berghut/berghut-murdoku-1.txt",
        "sudoku_17_9x9_pointing.txt",
        "akari_1_6x6.txt",
        "binairo_3_4x4.txt",
    ],
)
def test_bundles_carry_the_worked_solution_but_the_index_does_not(tmp_path, name):
    source = example(name)
    assert cli.main([str(source), "--export", str(tmp_path)]) == 0
    bundle = _bundle(tmp_path, source.stem)
    text = source.read_text()
    kind = cli.detect(text)
    model = cli._expression_model(text) if kind == "murdoku" else cli.load(text, kind).model
    fired = cli._Fired()
    cli.Solver(model.clone()).solve(on_step=fired.append_step)
    told = cli.worked_solution(kind, text, model, fired.items)
    assert told.complete
    assert bundle["solutionSteps"] == {"paragraphs": list(told.paragraphs), "complete": True}
    assert bundle["headings"]["solution_steps"]
    index = (tmp_path / "index.json").read_text()
    assert "solutionSteps" not in index and told.paragraphs[0] not in index


def test_rectangles_bundles_make_each_numbered_cell_a_given(exported):
    from csp import rectangles

    files = sorted(EXAMPLES.rglob("rectangles_*.txt"))
    assert files
    for source in files:
        puzzle = rectangles.parse(source.read_text())
        expected = {
            rectangles.cell_name(cell): rectangles.cell_name(cell) for cell in puzzle.numbered
        }
        bundle = _bundle(exported, source.stem)
        assert bundle["givens"] == expected
        assert all(bundle["solution"][cell] == owner for cell, owner in expected.items())


def test_bundles_record_which_puzzles_need_the_what_if_fallback(exported):
    """`deductive` is False exactly for the frontier: the puzzles graded `what_if`."""
    index = json.loads((exported / "index.json").read_text())
    bundles = {entry["id"]: _bundle(exported, entry["id"]) for entry in index["puzzles"]}
    assert set(bundles) == {path.stem for path in played_examples()}
    for entry in index["puzzles"]:
        bundle = bundles[entry["id"]]
        assert entry["deductive"] == bundle["deductive"] == (bundle["grade"] != "what_if")
    assert {name for name, bundle in bundles.items() if not bundle["deductive"]} == BEYOND_DEDUCTION


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
        if links := bundle.get("links"):
            # Link puzzles are played between drawn nodes, not on every cell.
            nodes = {node["id"] for node in links["nodes"]}
            assert nodes <= ids & board, bundle["id"]
            segments = {segment["id"]: segment for segment in links["segments"]}
            for link, value in bundle["solution"].items():
                assert set(segments[link]["endpoints"]) <= nodes, bundle["id"]
                assert value in segments[link]["values"], bundle["id"]
            continue
        if assign := bundle.get("assign"):
            # Assignment puzzles key the state by item and value it by container.
            items = {item["id"] for item in assign["items"]}
            targets = {target["id"]: target for target in assign["targets"]}
            assert set(bundle["solution"]) == items, bundle["id"]
            assert set(bundle["solution"].values()) <= set(targets), bundle["id"]
            for target in targets.values():
                assert set(target["cells"]) <= ids, bundle["id"]
                assert len(target["slots"]) == target["capacity"], bundle["id"]
            continue
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
    bundle = _bundle(exported, "wie-doet-het-met-wie-1")
    assert bundle["family"] == "murdoku"
    assert bundle["playable"]
    assert bundle["placement"]["perItem"] == 1
    assert [item["id"] for item in bundle["palette"]] == ["Eva", "Bram", "Noor", "Wouter"]
    assert bundle["solution"] == {
        "r1c1": "Eva",
        "r2c3": "Bram",
        "r3c4": "Noor",
        "r4c2": "Wouter",
    }
    assert bundle["clues"][0] == "Eva staat naast de tafel."
    assert bundle["question"]
    assert bundle["intro"]
    assert bundle["reveal"].startswith("Wouter doet het met Noor")
    assert bundle["rules"]
    assert any(
        rule.startswith("Alleen de expliciete regels en aanwijzingen bepalen")
        for rule in bundle["rules"]
    )
    assert "conditions" not in bundle
    assert isinstance(bundle["key"], list)
    assert all(set(item) == {"name", "text"} for item in bundle["key"])


@pytest.mark.parametrize("number", [1, 2, 3])
def test_zoo_intro_is_separate_from_player_rules(number):
    text = example(f"zoo-murdoku-{number}.txt").read_text()
    bundle = web._murdoku(text, {})
    assert any(
        "Een aap is nooit alleen in zijn verblijf." in paragraph for paragraph in bundle["intro"]
    )
    assert all(
        "Elke aap deelt zijn verblijf altijd met iemand." not in paragraph
        for paragraph in bundle["intro"]
    )
    assert all("Een aap is nooit alleen in zijn verblijf." not in rule for rule in bundle["rules"])


def test_murdoku_intros_are_exported_separately_from_reference_rules(exported):
    for source in played_examples():
        bundle = _bundle(exported, source.stem)
        if bundle["family"] != "murdoku":
            continue
        intro = load_presentation(source.read_text()).intro
        assert bundle.get("intro", []) == intro
        assert not set(intro) & set(bundle["rules"])


def test_every_murdoku_web_bundle_includes_the_character_description_note(exported):
    expected = {
        "en": "Only the puzzle's stated rules and clues determine what is possible;",
        "nl": "Alleen de expliciete regels en aanwijzingen bepalen",
    }
    for path in exported.glob("*.json"):
        bundle = json.loads(path.read_text())
        if bundle.get("family") == "murdoku":
            assert any(rule.startswith(expected[bundle["language"]]) for rule in bundle["rules"]), (
                path.name
            )


def test_murdoku_cards_cover_every_source_clue_once(exported):
    for source in played_examples():
        bundle = _bundle(exported, source.stem)
        if bundle["family"] != "murdoku":
            continue
        board, rules, clues = load_expression_board(source.read_text())
        entries = bundle["clueEntries"]
        expected = [
            *(f"clue:{number}" for number in range(1, len(clues) + 1)),
            *(f"rule:{number}" for number in range(1, len(rules) + 1)),
        ]
        actual = [source for entry in entries for source in entry["sources"]]
        assert sorted(actual) == sorted(expected), source.name
        assert [item["id"] for item in bundle["palette"]] == board.people
        assert all(entry.get("item") in (None, *board.people) for entry in entries)
        assert len({entry["id"] for entry in entries}) == len(entries)


def test_murdoku_custom_wording_keeps_its_semantic_owner_in_export():
    text = (
        example("murdoku_3_house.txt")
        .read_text()
        .replace("Clues:\n", "Clues:\nAda in area:study | Ben remembers Ada in the study.\n")
    )
    bundle = web._murdoku(text, {})
    entry = next(entry for entry in bundle["clueEntries"] if "clue:1" in entry["sources"])
    assert entry["item"] == "Ada"
    assert "Ben remembers Ada in the study." in entry["text"]


@pytest.mark.parametrize("number", [1, 2, 3])
def test_vietnam_web_groups_pork_dish_clues_with_their_travelers(number):
    text = example(f"vietnam-murdoku-{number}.txt").read_text()
    bundle = web._murdoku(text, {})
    assert any("De varkensvleesgerechten op het bord" in paragraph for paragraph in bundle["intro"])
    for person, clue_number in (("Pippo", 1), ("Swena", 2)):
        entry = next(
            entry for entry in bundle["clueEntries"] if f"clue:{clue_number}" in entry["sources"]
        )
        assert entry["item"] == person
        assert "een vakje met een varkensvleesgerecht" in entry["text"]
        assert "(ook niet schuin, en dit geldt zelfs over gebiedsgrenzen heen)" in entry["text"]
        assert "bún chả" not in entry["text"]


@pytest.mark.parametrize(("number", "person"), [(1, "PhoGa"), (2, "Loempia"), (3, "RauMuong")])
def test_vietnam_web_combines_figure_rules_with_clues(number, person):
    text = example(f"vietnam-murdoku-{number}.txt").read_text()
    bundle = web._murdoku(text, {})
    entry = next(entry for entry in bundle["clueEntries"] if entry["sources"] == ["rule:1"])
    assert entry["item"] == person
    assert "precies twee anderen" in entry["text"]
    assert "allebei reizigers" in entry["text"]
    assert entry["text"] not in bundle["rules"]
    figure = next(item for item in bundle["palette"] if item["id"] == person)
    assert "zonder eigen aanwijzingen" not in figure["description"]
    assert "precies twee anderen: Pippo en Swena" in " ".join(bundle["intro"])


def test_murdoku_cell_details_describe_board_facts_without_solution():
    text = (
        example("murdoku_composition.txt")
        .read_text()
        .replace("quiet: r1c1 r2c1 ; alone", "quiet: r1c1 r2c1 ; alone\nbusy: r2c1 ; not_alone")
    )
    details = web._murdoku(text, {"Ada": murdoku.Square(0, 0)})["cellDetails"]

    assert len(details) == 16
    assert details["r1c1"] == [
        "Area: Atrium",
        "Area tag: north",
        "Area tag: west",
        "Cells marked QU are quiet cells: whoever stands on one is alone in their area.",
    ]
    assert any("shares the area with someone else" in line for line in details["r2c1"])
    assert "Object: the tree (nobody can stand here)" in details["r1c4"]
    assert "Object: the bench (you can stand on it)" in details["r4c2"]
    assert all("Touches: the archway" in details[cell] for cell in ("r2c2", "r2c3"))
    assert "Touches: the archway" not in details["r2c1"]
    assert all(
        "Touches: the fountain" in details[cell] for cell in ("r3c1", "r3c2", "r4c1", "r4c2")
    )
    assert all("Ada" not in line for lines in details.values() for line in lines)


def test_murdoku_cell_details_use_dutch_and_author_wording():
    text = example("zoo-murdoku-1.txt").read_text()
    details = web._murdoku(text, {})["cellDetails"]
    assert "Gebied: Savanne" in details["r1c2"]
    assert "Voorwerp: de acacia (hier kan niemand staan)" in details["r1c2"]
    assert "Voorwerp: het gras (hier kun je op staan)" in details["r2c2"]

    point_text = example("murdoku_2_point_objects.txt").read_text()
    points = web._murdoku(point_text, {})["cellDetails"]
    assert "Touches: the mouse on the top edge" in points["r1c4"]
    assert "Touches: the mouse on the top edge" in points["r1c5"]


@pytest.mark.parametrize(
    ("name", "cell", "label", "caption"),
    [
        ("berghut-murdoku-1.txt", "r1c1", "De koude buitendouche", "hier kun je onder staan"),
        ("berghut-murdoku-1.txt", "r2c4", "Bikkelstoel", "hier kun je op staan"),
        ("berghut-murdoku-3.txt", "r1c1", "De koude buitendouche", "hier kun je onder staan"),
        ("berghut-murdoku-3.txt", "r10c1", "Matras", "hier kun je op staan"),
    ],
)
def test_berghut_object_position_text_matches_details_and_board(name, cell, label, caption):
    bundle = web._murdoku(example(name).read_text(), {})
    assert next(item["text"] for item in bundle["objects"] if item["name"] == label) == caption
    details = bundle["cellDetails"][cell]
    assert any(line.startswith("Voorwerp: ") and line.endswith(f"({caption})") for line in details)


def test_berghut_3_uses_the_authored_distance_wording():
    bundle = web._murdoku(example("berghut-murdoku-3.txt").read_text(), {})
    assert "Reinhart en Sepp staan negen kolommen van elkaar af." in bundle["clues"]
    assert "Waltraud en Siegfried staan precies één rij van elkaar af." in bundle["clues"]
    for cell in ("r3c1", "r6c1"):
        assert "Gebied: Keuken" in bundle["cellDetails"][cell]


def test_berghut_cell_details_localize_standard_doors_and_windows():
    text = example("berghut-murdoku-3.txt").read_text()
    details = web._murdoku(text, {})["cellDetails"]
    assert all("Raakt: een deur" in details[cell] for cell in ("r1c3", "r1c4"))
    assert "Raakt: een raam" in details["r2c1"]

    custom = web._murdoku(text.replace("Words:\n", "Words:\ndoor: de houten deur\n"), {})
    assert "Raakt: de houten deur" in custom["cellDetails"]["r1c3"]


def test_berghut_cell_labels_keep_the_authored_article_for_repeated_objects():
    details = web._murdoku(example("berghut-murdoku-3.txt").read_text(), {})["cellDetails"]
    for cell in ("r3c9", "r6c10"):
        assert "Voorwerp: de stinksokken (hier kan niemand staan)" in details[cell]


def test_murdoku_cell_details_include_object_count_rules_on_each_matching_object():
    text = example("wie-doet-het-met-wie-4.txt").read_text()
    details = web._murdoku(text, {})["cellDetails"]
    robe = "Precies twee mensen staan op een badjas."
    slippers = "Precies één persoon staat op een paar sloffen."
    glasses = "Precies één persoon staat op een bril."

    assert all(robe in details[cell] for cell in ("r2c3", "r3c6", "r4c3"))
    assert all(slippers in details[cell] for cell in ("r3c5", "r5c4"))
    assert all(glasses in details[cell] for cell in ("r4c4", "r6c5"))
    assert robe not in details["r3c5"]
    assert slippers not in details["r3c6"]
    assert glasses not in details["r3c6"]
    assert robe not in details["r1c2"]


def test_murdoku_object_count_details_use_generated_and_authored_clue_wording():
    text = (
        example("murdoku_3_house.txt")
        .read_text()
        .replace(
            "Clues:\n",
            "Rules:\n"
            "count people on object:carpet <= 1\n"
            "count people in area:garden >= 1\n"
            "count empty cells in object:carpet = 1 | One carpet square is left empty.\n"
            "Clues:\n"
            "count people on object:chair = 1 | Only one guest uses the chair!\n",
        )
    )
    details = web._murdoku(text, {})["cellDetails"]

    for cell in ("r3c3", "r3c4"):
        assert "At most one person is on the carpet." in details[cell]
        assert "One carpet square is left empty." in details[cell]
        assert "Only one guest uses the chair!" not in details[cell]
    assert "Only one guest uses the chair!" in details["r5c2"]
    assert "At most one person is on the carpet." not in details["r5c2"]


def test_murdoku_count_details_follow_edge_and_point_scopes():
    text = (
        example("murdoku_composition.txt")
        .read_text()
        .replace(
            "Clues:\n",
            "Rules:\n"
            "count people on edge_item:archway >= 1\n"
            "count people on point_object:fountain = 1\n"
            "Clues:\n",
        )
    )
    details = web._murdoku(text, {})["cellDetails"]
    archway = "At least one person is on the archway."
    fountain = "Exactly one person is on the fountain."

    assert all(archway in details[cell] for cell in ("r2c2", "r2c3"))
    assert archway not in details["r3c1"]
    assert all(fountain in details[cell] for cell in ("r3c1", "r3c2", "r4c1", "r4c2"))
    assert fountain not in details["r2c2"]


def test_expression_count_hover_keeps_author_wording_on_its_own_scope():
    text = (
        example("murdoku_composition.txt")
        .read_text()
        .replace(
            "Clues:\n",
            "Clues:\ncount people on point_object:fountain = 1 | One guest touches the fountain!\n",
        )
    )
    details = web._murdoku(text, {})["cellDetails"]
    assert all(
        "One guest touches the fountain!" in details[cell]
        for cell in ("r3c1", "r3c2", "r4c1", "r4c2")
    )
    assert "One guest touches the fountain!" not in details["r2c2"]


def test_murdoku_point_hovers_include_outer_edges_and_corners():
    bundle = web._murdoku(example("menu-murdoku-3.txt").read_text(), {})
    targets = bundle["detailTargets"]
    assert len(targets) == 8
    edge = next(target for target in targets if (target["x"], target["y"]) == (8, 4))
    corner = next(target for target in targets if (target["x"], target["y"]) == (8, 8))
    assert edge["lines"][0] == "Sierui"
    assert corner["lines"][0] == "Zonnebloem"
    assert edge["radius"] > 0 and corner["radius"] > 0
    assert "op een vakje staat dat het raakt" in edge["lines"][1]

    text = example("murdoku_2_point_objects.txt").read_text()
    targets = web._murdoku(text, {})["detailTargets"]
    assert any(target["lines"][0] == "The mouse on the top edge" for target in targets)
    assert all("any square it touches" in target["lines"][1] for target in targets)


def test_murdoku_text_names_keep_ids_and_authored_forms():
    text = (
        example("murdoku_3_house.txt")
        .read_text()
        .replace("Regions:\n", "Words:\nAda: de gids\nRegions:\n")
    )
    names = web._murdoku(text, {})["textNames"]
    assert {"Ada", "De gids", "de gids", "Ben", "Cleo", "Dirk", "Eva"} <= set(names)
    assert len(names) == len(set(names))


def test_murdoku_bundle_lists_its_objects_with_pictures(exported):
    bundle = _bundle(exported, "zoo-murdoku-1")
    assert bundle["headings"]["objects"] == "De voorwerpen"
    objects = bundle["objects"]
    assert objects and all(item["svg"].startswith("<svg") for item in objects)
    assert {item["text"] for item in objects} <= {"hier kun je op staan", "hier kan niemand staan"}


@pytest.mark.parametrize(
    ("name", "heading"),
    [("halloween-museum-1.txt", "Case details"), ("zoo-murdoku-1.txt", "Bijzonderheden")],
)
def test_murdoku_bundle_combines_extras_in_the_puzzle_language(name, heading):
    bundle = web._murdoku(example(name).read_text(), {})
    assert bundle["combineExtras"] is True
    assert bundle["headings"]["extras"] == heading


def test_dutch_murdoku_is_worded_in_dutch(exported):
    bundle = _bundle(exported, "zoo-murdoku-1")
    assert bundle["language"] == "nl"
    assert bundle["headings"]["clues"] == "Aanwijzingen"
    assert bundle["headings"]["key"] == "Legenda"
    assert all(item["svg"].startswith("<svg") for item in bundle["palette"])


def test_logic_grids_are_listed_but_not_playable(exported):
    bundle = _bundle(exported, "logicgrid_1_3x3")
    assert not bundle["playable"]
    assert bundle["unsupported"]


def test_rooms_bundles_are_playable_and_assign_every_person(exported):
    """A room puzzle exports the plan, its containers and a person-by-person solution."""
    from csp import rooms

    bundle = _bundle(exported, "rooms_2_5x7")
    puzzle = rooms.parse(example("rooms_2_5x7.txt").read_text())
    assert bundle["playable"] and "unsupported" not in bundle
    assert bundle["size"] == [puzzle.height, puzzle.width]
    assert bundle["clues"] == puzzle.clue_lines
    assert [item["name"] for item in bundle["key"]] == [puzzle.phrase(tag) for tag in puzzle.tags]
    assert all(item["svg"].startswith("<svg") for item in bundle["key"])
    assert bundle["intro"] and bundle["question"]
    headings = bundle["headings"]
    assert headings["rules_title"] == "Rules"
    assert headings["clues"] == "Clues"
    assert headings["question"] == "Question"
    assert headings["key"] == "Key"

    assign = bundle["assign"]
    items = {item["id"] for item in assign["items"]}
    targets = {target["id"]: target for target in assign["targets"]}
    assert items == set(puzzle.people)
    assert set(targets) == {room.key for room in puzzle.rooms}
    assert assign["instructions"]
    assert set(bundle["solution"]) == items
    assert set(bundle["solution"].values()) <= set(targets)
    for target in targets.values():
        occupants = [person for person, room in bundle["solution"].items() if room == target["id"]]
        assert len(occupants) <= target["capacity"]
        assert len(target["slots"]) == target["capacity"]
        assert len(target["box"]) == 4
        assert target["box"][2] > 0 and target["box"][3] > 0
        left, top, width, height = target["box"]
        for slot_x, slot_y, size in target["slots"]:
            assert left <= slot_x <= left + width - size
            assert top <= slot_y <= top + height - size
        assert len(target["cells"]) > 0

    board = svg.ids((exported / bundle["static"]).read_text())
    cells = {cell for target in targets.values() for cell in target["cells"]}
    assert cells <= set(board)
    # The clues and the key are the page's text now, not a picture of them.
    board_text = (exported / bundle["static"]).read_text()
    assert puzzle.clue_lines[0] not in board_text
    assert puzzle.phrase(next(iter(puzzle.tags))) not in board_text

    index = json.loads((exported / "index.json").read_text())
    entry = next(item for item in index["puzzles"] if item["id"] == "rooms_2_5x7")
    assert entry["playable"] is True and "unsupported" not in entry


def test_calcudoku_cage_targets_are_editable_clues_not_hidden_givens(tmp_path):
    source = example("calcudoku_single_cell_cages.txt")
    assert cli.main([str(source), "--export", str(tmp_path)]) == 0
    bundle = _bundle(tmp_path, source.stem)
    assert bundle["givens"] == {}
    assert bundle["placement"]["blocked"] == []
    assert bundle["solution"]["r1c1"] == "4"
    assert bundle["solution"]["r4c1"] == "1"
    assert bundle["solution"]["r4c4"] == "2"
    assert len(bundle["solution"]) == 16
    assert {piece["id"] for piece in bundle["palette"]} == {"1", "2", "3", "4"}
    assert {"r1c1", "r4c1", "r4c4"} <= set(svg.ids((tmp_path / bundle["static"]).read_text()))


@pytest.mark.parametrize(
    "number,answer,reason",
    [
        (1, "Carmen, dressed as a witch", "only woman in the Egyptian hall"),
        (2, "Diego, dressed as a vampire", "only guest in costume in the armoury"),
        (3, "Gonzalo, the restorer", "only member of staff in the Goya room"),
    ],
)
def test_halloween_questions_and_web_reveals_explicitly_identify_the_murderer(
    exported, number, answer, reason
):
    bundle = _bundle(exported, f"halloween-museum-{number}")
    assert bundle["question"].startswith("Who is the murderer")
    assert bundle["reveal"].startswith(f"{answer}, is the murderer:")
    assert reason in bundle["reveal"]
    assert "struck with" not in bundle["reveal"]
    assert answer not in bundle["question"]


def test_display_aliases_keep_their_labels_and_rules(exported):
    queens = _bundle(exported, "queens_2_5x5")
    assert queens["family"] == "starbattle"
    assert queens["familyLabel"] == "Queens"
    assert "one queen" in queens["rules"][0]
    assert queens["palette"][0]["id"] == "queen"
    assert queens["palette"][0]["svg"]

    tango = _bundle(exported, "tango_2_4x4")
    assert tango["family"] == "binairo"
    assert tango["familyLabel"] == "Tango"
    assert "= signs" in tango["rules"][0]

    binairo = _bundle(exported, "binairo_3_4x4")
    assert binairo["familyLabel"] == "Binairo"


def test_kakurasu_and_fleet_battleships_rules_are_precise(exported):
    kakurasu = _bundle(exported, "kakurasu_1_4x4")
    assert "column number to the row sum" in kakurasu["rules"][0]
    assert "row number to the column sum" in kakurasu["rules"][0]

    battleships = _bundle(exported, "battleships_1_6x6_fleet")
    assert "3, 2, 2, 1, 1, 1" in battleships["rules"][0]
    assert "straight" in battleships["rules"][1]
    assert "not even diagonally" in battleships["rules"][2]
    assert battleships["givens"] == {"r4c6": "ship"}
    assert all(re.fullmatch(r"r\d+c\d+", cell) for cell in battleships["solution"])


def test_dutch_battleships_web_rules():
    from csp.web import _family

    text = example("battleships_1_6x6_fleet.txt").read_text() + "\nLanguage:\nnl\n"
    data = _family(text, "battleships", cli.load(text, "battleships").model, {}, "")
    assert data["language"] == "nl"
    assert data["rules"] == story.family_rules(text, "battleships")
    assert "volledige vloot" in data["rules"][0]


def test_minesweeper_bundle_exports_total_and_omits_it_when_unspecified(exported):
    from csp.web import _family

    bundle = _bundle(exported, "minesweeper_3_8x8")
    assert bundle["totals"] == {"mine": 9}

    text = example("minesweeper_3_8x8.txt").read_text().split("\nTotalMines:", 1)[0] + "\n"
    model = cli.load(text, "minesweeper").model
    data = _family(text, "minesweeper", model, {}, '<rect id="r1c1" class="cell"')
    assert "totals" not in data


@pytest.mark.parametrize("number", [2, 3, 5])
def test_varied_battleships_export_preserves_ship_and_water_clues(exported, number):
    from csp import battleships

    name = f"battleships_{number}_8x8_fleet"
    puzzle = battleships.parse(example(f"{name}.txt").read_text())
    bundle = _bundle(exported, name)
    blocked = bundle["placement"]["blocked"]
    assert "question mark" in " ".join(bundle["rules"])
    for r, row in enumerate(puzzle.givens, 1):
        for c, given in enumerate(row, 1):
            cell = f"r{r}c{c}"
            if given == 0:
                assert cell in blocked
                assert cell not in bundle["givens"]
            elif given == 1:
                assert bundle["givens"][cell] == "ship"
            else:
                assert cell not in blocked
                assert cell not in bundle["givens"]
    assert "?" in (exported / bundle["static"]).read_text()


def test_export_fails_when_a_puzzle_cannot_be_exported(tmp_path, capsys):
    broken = tmp_path / "broken.txt"
    broken.write_text("this is not a puzzle\n")
    assert (
        cli.main([str(example("tents_3_4x4.txt")), str(broken), "--export", str(tmp_path / "site")])
        == 1
    )
    assert "broken.txt" in capsys.readouterr().err


def test_murdoku_web_key_lists_board_symbols_only(exported):
    point = _bundle(exported, "murdoku_2_point_objects")
    assert "conditions" not in point
    assert any((item["text"] or item["name"]) in {"Point", "Punt"} for item in point["key"])
    assert all(
        (item["text"] or item["name"]) in {"Deur", "Door", "Raam", "Window", "Punt", "Point"}
        for item in point["key"]
    )

    counted = _bundle(exported, "japan-3-samen-in-japan")
    assert counted["key"] == []


def test_murdoku_web_key_shows_the_symbols_players_see():
    points = web._murdoku(example("murdoku_2_point_objects.txt").read_text(), {})["key"]
    for label, name in (
        ("The cat", "cat"),
        ("Cheese", "cheese"),
        ("Fountain", "fountain"),
        ("The mouse on the top edge", "mouse1"),
        ("The mouse in the corner", "mouse2"),
    ):
        (entry,) = [item for item in points if item["name"] == label]
        assert entry["text"] == "Point"
        assert entry["svg"] == icons.to_svg(icons.object_icon(name))

    train = web._murdoku(example("murdoku_orient_express.txt").read_text(), {})["key"]
    door = next(item for item in train if item["name"] == "Deur")
    window = next(item for item in train if item["name"] == "Raam")
    assert "#754b2f" in door["svg"]
    assert "#d0e4f2" in window["svg"]


EXPORTED_PROSE = {
    "food-murdoku-1": (
        "Jos shares an area with exactly one other person, and that person is a food.",
    ),
    "food-murdoku-2": (
        "Jos shares an area with exactly one other person, and that person is a food.",
    ),
    "zoo-murdoku-3": (
        "De verzorger deelt een gebied met precies één ander persoon, en dat is een dier.",
        "In het gebied van iedere aap staan minstens twee personen.",
    ),
    "japan-1-samen-in-de-blauwe-bladeren": (
        "Gebied Hiroshima en gebied Okinawa hebben evenveel personen.",
        "Gebied Okinawa heeft minder personen dan elk gebied met een vrij vakje "
        "behalve gebied Hiroshima.",
    ),
    "wie-doet-het-met-wie-1": ("Wouter deelt een gebied met precies één ander persoon.",),
    "menu-murdoku-1": ("Vla deelt een gebied met precies twee andere personen.",),
    "berghut-murdoku-2": (
        "Ute en Gerhard staan minstens drie rijen óf minstens drie kolommen van elkaar af.",
        "Het grootste verschil tussen Hannelore en Brunhild is precies drie rijen of kolommen.",
    ),
}


@pytest.mark.parametrize("puzzle", sorted(EXPORTED_PROSE))
def test_exported_murdoku_prose_has_no_expression_syntax(exported, puzzle):
    """The player bundle uses the same player prose as the booklet, not fallbacks."""
    bundle = _bundle(exported, puzzle)
    cards = bundle.get("clueEntries") or []
    text = "\n".join([*bundle["rules"], *bundle["clues"], *(card["text"] for card in cards)])
    for fragment in EXPORTED_PROSE[puzzle]:
        assert fragment in text, (puzzle, fragment)
    for forbidden in (
        "plus",
        "?p",
        "?b",
        "every member",
        "at least one of",
        "member of",
        "the number of",
        "aantal personen",
        "ieder lid",
        "koningsstap",
        "king-step",
    ):
        assert forbidden not in text, (puzzle, forbidden)


def test_murdoku_web_key_shows_both_styles_of_window():
    text = (
        example("murdoku_composition.txt")
        .read_text()
        .replace("window: window r3c4", "window: window r3c4\nwindow: window r1c1 top")
    )
    windows = [item for item in web._murdoku(text, {})["key"] if item["name"] == "Window"]
    assert len(windows) == 2
    assert any("#d0e4f2" in item["svg"] for item in windows)
    assert any(item["svg"] == icons.to_svg(icons.object_icon("window")) for item in windows)


def test_murdoku_web_key_keeps_text_fallbacks_for_unknown_symbols():
    text = (
        example("murdoku_composition.txt")
        .read_text()
        .replace("fountain", "unlisted_thing")
        .replace("window: window", "mystery_window: window")
        .replace("Cal on edge_item:window", "Cal on edge_item:mystery_window")
    )
    key = web._murdoku(text, {})["key"]
    point = next(item for item in key if item["name"] == "Unlisted thing")
    window = next(item for item in key if item["name"] == "Mystery window")
    assert point["text"] == "Point"
    assert window["text"] == "Window"
    assert "<ellipse" in point["svg"] and '<use href="#g' in point["svg"]
    assert '<use href="#g' in window["svg"]


def test_every_murdoku_key_lists_only_board_symbols(exported):
    allowed = {
        "Door",
        "Deur",
        "Window",
        "Raam",
        "Point",
        "Punt",
    }
    for path in exported.glob("*.json"):
        if path.name == "index.json":
            continue
        bundle = json.loads(path.read_text())
        assert "conditions" not in bundle, path.name
        if bundle.get("family") != "murdoku":
            continue
        assert {item["text"] or item["name"] for item in bundle["key"]} <= allowed, path.name
        assert all(item.get("svg", "").startswith("<svg") for item in bundle["key"]), path.name


def test_digit_puzzles_get_pencil_marks_and_peer_groups(exported):
    bundle = _bundle(exported, "sudoku_1_4x4")
    assert bundle["notes"] is True
    assert bundle["autoMark"]["default"] is True
    groups = [frozenset(group["cells"]) for group in bundle["peers"]]
    rows = [frozenset(f"r{r}c{c}" for c in range(1, 5)) for r in range(1, 5)]
    cols = [frozenset(f"r{r}c{c}" for r in range(1, 5)) for c in range(1, 5)]
    assert set(rows + cols) <= set(groups)
    assert len(groups) == len(set(groups)) == 12
    assert all("items" not in group for group in bundle["peers"])


def test_anti_knight_pairs_are_peers(exported):
    groups = {
        frozenset(group["cells"])
        for group in _bundle(exported, "sudoku_2_4x4_anti_knight")["peers"]
    }
    assert frozenset({"r1c1", "r2c3"}) in groups


def test_sudoku_peer_rules_have_localized_descriptions():
    from csp.web import peers

    text = example("sudoku_2_4x4_anti_knight.txt").read_text()
    model = cli.load(text, "sudoku").model
    for language, label in (("en", "anti-knight rule"), ("nl", "anti-paardregel")):
        groups = peers(
            model, set(model.variables), {d: str(d) for d in range(1, 5)}, language=language
        )
        pair = next(group for group in groups if set(group["cells"]) == {"r1c1", "r2c3"})
        assert pair["description"] == label


def test_akari_lights_what_a_bulb_sees(exported):
    from csp.akari import parse

    text = example("akari_1_6x6.txt").read_text()
    puzzle = parse(text)
    bundle = _bundle(exported, "akari_1_6x6")
    assert "notes" not in bundle
    assert bundle["autoMark"] == {"default": True, "mark": "light", "onPlace": [{"scope": "peers"}]}
    # Only lines of sight, never the cells around a numbered wall.
    expected = {
        frozenset(f"r{row + 1}c{col + 1}" for row, col in segment)
        for segment in puzzle.segments
        if len(segment) > 1
    }
    assert {frozenset(group["cells"]) for group in bundle["peers"]} == expected


def test_sudoku_web_rules_describe_the_active_variants(exported):
    for name in (
        "sudoku_2_4x4_anti_knight",
        "sudoku_4_9x9_anti_king",
        "sudoku_16_4x4_kropki_consecutive_thermometers",
        "sudoku_6_9x9_nrc",
        "sudoku_20_6x6_jigsaw",
        "sandwich_1_4x4",
        "sandwich_3_6x6",
        "skyscrapersudoku_1_4x4",
        "skyscrapersudoku_3_6x6",
    ):
        text = example(name + ".txt").read_text()
        assert _bundle(exported, name)["rules"] == story.family_rules(text, "sudoku")
        assert len(_bundle(exported, name)["rules"]) > 1


def test_dutch_sudoku_web_rules_are_localized():
    from csp.web import _family

    text = (
        example("sudoku_16_4x4_kropki_consecutive_thermometers.txt").read_text()
        + "\nLanguage:\nnl\n"
    )
    data = _family(text, "sudoku", cli.load(text, "sudoku").model, {}, "")
    assert data["language"] == "nl"
    assert data["headings"]["rules_title"] == "Spelregels"
    assert data["rules"] == story.family_rules(text, "sudoku")


def test_placement_puzzles_without_at_most_one_rules_get_no_peers(exported):
    bundle = _bundle(exported, "wie-doet-het-met-wie-1")
    assert "peers" not in bundle
    assert "notes" not in bundle


def test_export_refuses_two_puzzles_with_the_same_name(tmp_path, capsys):
    other = tmp_path / "copy"
    other.mkdir()
    (other / "tents_3_4x4.txt").write_text((example("tents_3_4x4.txt")).read_text())
    files = [str(example("tents_3_4x4.txt")), str(other / "tents_3_4x4.txt")]
    assert cli.main([*files, "--export", str(tmp_path / "site")]) == 2
    assert "tents_3_4x4" in capsys.readouterr().err
    assert not (tmp_path / "site").exists()


def test_index_is_numbered_in_reading_order_with_category_sections(exported):
    puzzles = json.loads((exported / "index.json").read_text())["puzzles"]
    assert [entry["number"] for entry in puzzles] == list(range(1, len(puzzles) + 1))
    assert puzzles[0]["section"] == "Murdoku \u00b7 Demo"
    sections = list(dict.fromkeys(entry["section"] for entry in puzzles))
    assert "Murdoku \u00b7 Japanese food" in sections
    assert sections.index("Murdoku \u00b7 Wie doet het met wie") < sections.index("Akari")
    assert _bundle(exported, "food-murdoku-2")["section"] == "Murdoku \u00b7 Japanese food"
    assert "Queens" in sections and "Tango" in sections
    queens = [
        entry
        for entry in puzzles
        if entry["family"] == "starbattle" and entry["familyLabel"] == "Queens"
    ]
    assert len(queens) == 6
    assert {entry["section"] for entry in queens} == {"Queens"}
    for entry in queens:
        assert [piece["id"] for piece in _bundle(exported, entry["id"])["palette"]] == ["queen"]


def test_author_wordings_reach_the_web_player(exported):
    bundle = _bundle(exported, "wie-doet-het-met-wie-3")
    texts = [entry["text"] for entry in bundle["clueEntries"]]
    assert "Precies twee mensen staan op een badjas." in texts
    assert "Precies één persoon staat op een paar sloffen." in texts
    assert "Marloes heeft alleen een badjas aan." in bundle["clues"]


def test_every_non_murdoku_bundle_states_its_rules(exported):
    for path in exported.glob("*.json"):
        if path.name == "index.json":
            continue
        bundle = json.loads(path.read_text())
        if bundle.get("family") != "murdoku":
            assert bundle["rules"], path.name


def test_the_hotel_lists_wouters_rule_once(exported):
    """The intro is prominent and its repeated rule is absent from the reference."""
    bundle = _bundle(exported, "wie-doet-het-met-wie-5")
    wouter = (
        "Wouter wordt als laatste geplaatst en is alleen in een gebied met degene "
        "met wie hij het doet: iemand in een badjas."
    )
    assert any(wouter in paragraph for paragraph in bundle["intro"])
    assert all(wouter not in rule for rule in bundle["rules"])


def test_no_puzzle_repeats_the_intro_in_its_rules(exported):
    """Issue #152: the intro is shown above the puzzle, so the reference must not repeat it."""
    for path in sorted(exported.glob("*.json")):
        if path.name == "index.json":
            continue
        bundle = json.loads(path.read_text())
        rules = bundle["rules"]
        for paragraph in bundle.get("intro", []):
            assert all(paragraph not in rule and rule not in paragraph for rule in rules), path.stem


def test_no_puzzle_lists_the_same_rule_twice(exported):
    for path in sorted(exported.glob("*.json")):
        if path.name == "index.json":
            continue
        rules = json.loads(path.read_text())["rules"]
        assert len(rules) == len(dict.fromkeys(rules)), path.stem
