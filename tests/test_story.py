"""Tests for the worked-solution writer and the proof it is built on.

Every placement a story states is checked against the brute force, so a
story can be clumsy but never wrong.
"""

import ast
import re
from pathlib import Path

import pytest

import csp
from csp import bruteforce, cli, murdoku
from csp.core import Kind, Model, Solver
from csp.proof import Move, replay, shortest
from csp.puzzlefile import load_board
from csp.story import Story, Wording, explain

EXAMPLES = Path(__file__).parent.parent / "examples"
PRRRDOKUS = ["prrrdoku1.txt", "prrrdoku2.txt", "prrrdoku3.txt"]
PLACED = re.compile(r"\*\*(\w+) op r(\d+)k(\d+)\*\*")


def _moves(model: Model) -> list[Move]:
    moves: list[Move] = []

    def collect(rule, steps):
        if (move := Move.of(rule, steps)) is not None:
            moves.append(move)

    Solver(model.clone()).solve(on_step=collect)
    return moves


# --- layering -------------------------------------------------------------

# Who may import whom inside the package; anything not listed may import freely.
ALLOWED = {
    "core": set(),
    "svg": set(),
    "icons": {"svg"},
    "proof": {"core"},
    "murdoku": {"core"},
    "sudoku": {"core", "puzzlefile"},
    "calcudoku": {"core", "puzzlefile"},
    "futoshiki": {"core", "puzzlefile"},
    "story": {"core", "proof", "murdoku", "puzzlefile"},
    "docx_export": {"icons", "murdoku", "picture", "puzzlefile", "story"},
    "regiongrid": {"puzzlefile"},
    "queens": {"core", "puzzlefile"},
    "suguru": {"core", "puzzlefile", "regiongrid"},
    "starbattle": {"core", "regiongrid", "icons"},
    "logicgrid": {"core", "puzzlefile"},
    "binairo": {"core", "puzzlefile", "icons"},
    "tents": {"core", "puzzlefile", "icons"},
    "minesweeper": {"core", "puzzlefile", "icons"},
    "akari": {"core", "puzzlefile", "icons"},
    "kakurasu": {"core", "puzzlefile", "icons"},
    "battleships": {"core", "puzzlefile", "icons"},
    "picture": {
        "murdoku",
        "sudoku",
        "calcudoku",
        "futoshiki",
        "queens",
        "suguru",
        "starbattle",
        "logicgrid",
        "binairo",
        "tents",
        "minesweeper",
        "akari",
        "kakurasu",
        "battleships",
        "icons",
        "svg",
    },
}


@pytest.mark.parametrize("module", sorted(ALLOWED))
def test_modules_only_import_their_own_layer(module):
    """Solving knows nothing of explaining or drawing, and they know nothing of each other."""
    source = Path(csp.__file__).parent / f"{module}.py"
    tree = ast.parse(source.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module:
                imported.add(node.module.split(".")[0])
            else:
                imported |= {alias.name for alias in node.names}
    assert imported <= ALLOWED[module], f"{module} imports {imported - ALLOWED[module]}"


# --- proof ----------------------------------------------------------------


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_shortest_proof_still_solves_and_drops_moves(name):
    board, clues = load_board((EXAMPLES / name).read_text())
    model = murdoku.compile_puzzle(board, clues)
    moves = _moves(model)
    kept = shortest(model, moves)
    assert len(kept) <= len(moves)
    assert all(move in moves for move in kept)
    assert replay(model, kept).solution() == replay(model, moves).solution()


def test_shortest_proof_drops_what_ifs_it_can_do_without():
    board, clues = load_board((EXAMPLES / "prrrdoku3.txt").read_text())
    model = murdoku.compile_puzzle(board, clues)
    moves = _moves(model)
    kept = shortest(model, moves)
    assert sum(m.rule == "what_if" for m in kept) < sum(m.rule == "what_if" for m in moves)


def test_replay_reports_each_change_like_the_solver():
    board, clues = load_board((EXAMPLES / "prrrdoku1.txt").read_text())
    model = murdoku.compile_puzzle(board, clues)
    fired: list[str] = []
    replay(model, _moves(model), lambda rule, steps: fired.append(rule))
    assert fired.count("single") == len(board.people)
    assert {"relations", "subsumption"} <= set(fired)


# --- story ----------------------------------------------------------------


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_every_placement_in_the_story_is_right(name):
    text = (EXAMPLES / name).read_text()
    (solution,) = bruteforce.solutions(text)
    story = explain(text)
    placed = {who: f"r{solution[who].row + 1}k{solution[who].col + 1}" for who in solution}
    stated = {who: f"r{r}k{c}" for who, r, c in PLACED.findall(story)}
    assert stated == placed


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_story_is_bullets_and_leads_with_the_direct_clues(name):
    story = explain((EXAMPLES / name).read_text())
    paragraphs = story.split("\n\n")
    assert all(p.startswith("- **") for p in paragraphs)
    assert paragraphs[0].startswith("- **De directe aanwijzingen.**")


def test_story_describes_by_region_and_row_before_squares():
    story = explain((EXAMPLES / "prrrdoku3.txt").read_text())
    assert "Luna zit in het water" in story
    assert "Otto zit in een klimgebied, dus Pip zit in een klimgebied" in story
    assert "Luna kan alleen in kolom 1, daar kan verder niemand" in story


def test_new_murdoku_clues_have_dutch_wording():
    square = murdoku.Square
    board = murdoku.Board(
        3,
        [["a"] * 3 for _ in range(3)],
        {"a": "zaal"},
        [
            murdoku.BoardObject("stoel", "standable", (square(0, 0),)),
            murdoku.BoardObject("bed", "standable", (square(0, 1),)),
        ],
        ["Anna", "Betsy", "Eli"],
    )
    story = Story(board, [], Wording("nl", {"stoel": "de stoel", "bed": "het bed"}))
    assert story._clue_text("not_on", ["Anna", "stoel"], ("Anna",)) == "Anna zit niet op de stoel"
    assert story._clue_text("only_on", ["Anna", "bed"], ("Betsy",)) == "alleen Anna zit op het bed"
    assert (
        story._clue_text("in_corner", ["Eli"], ("Eli",)) == "Eli staat in een hoek van het raster"
    )
    assert story._clue_text("left_of", ["Anna", "Eli", "1"], ("Anna", "Eli")) == (
        "Anna is precies één kolom links van Eli"
    )


def test_story_can_name_a_boundary_door():
    square = murdoku.Square
    board = murdoku.Board(
        2,
        [["west", "east"], ["west", "east"]],
        {"west": "west", "east": "east"},
        [],
        ["Ada", "Ben"],
        edge_items=[murdoku.EdgeItem("gate", "door", (square(0, 0), square(0, 1)))],
    )
    story = Story(board, [], Wording("nl", {"gate": "de deur"}))
    assert story._clue_text("next_to", ["Ada", "gate"], ("Ada",)) == "Ada zit naast de deur"
    assert story._clue_text("at", ["Ada", "gate"], ("Ada",)) == "Ada is bij de deur"


def test_story_words_cell_mark_clues_in_english_and_dutch():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Marks:
safe_zone: r1c2
Clues:
on_mark Ada safe_zone
not_on_mark Ben safe_zone
"""
    board, clues = load_board(text)
    english = Story(board, clues, Wording())
    dutch = Story(board, clues, Wording("nl"))

    assert english._clue_text("on_mark", ["Ada", "safe_zone"], ("Ada",)) == (
        "Ada is on the safe zone"
    )
    assert english._clue_text("not_on_mark", ["Ben", "safe_zone"], ("Ben",)) == (
        "Ben is not on the safe zone"
    )
    assert dutch._clue_text("on_mark", ["Ada", "safe_zone"], ("Ada",)) == (
        "Ada staat op de safe zone"
    )


def test_new_clues_targets_names_and_pronouns_are_worded_in_english_and_dutch():
    english_text = """Language: en
Size: 3
Regions:
a: kitchen
b: hall
Grid:
a a b
a b b
b b b
People:
Ada
Ben
Cal
Attributes:
glasses: Ben
Pronouns:
Ada: she her her
AreaTags:
inside: kitchen
Objects:
chair: standable r2c3
Roles:
guide: any
Marks:
altar: r1c3
quiet: r1c1
social: r1c2
Words:
glasses: glasses
guide: guide
inside: in the kitchen
chair: the chair
altar: the altar
quiet: the quiet square
social: the social square
Rules:
role_subset guide attribute:glasses
Clues:
alone_with Ada role:guide
above Ada tag:inside
role_on Ada guide altar
"""
    dutch_text = english_text.replace("Language: en", "Language: nl")
    dutch_text = dutch_text.replace("a: kitchen", "a: keuken").replace("b: hall", "b: gang")
    dutch_text = dutch_text.replace("inside: kitchen", "inside: keuken")
    dutch_text = dutch_text.replace("Ada: she her her", "Ada: zij haar haar")
    dutch_text = dutch_text.replace("glasses: glasses", "glasses: bril")
    dutch_text = dutch_text.replace("guide: guide", "guide: gids")
    dutch_text = dutch_text.replace("inside: in the kitchen", "inside: in de keuken")
    dutch_text = dutch_text.replace("altar: the altar", "altar: het altaar")
    dutch_text = dutch_text.replace("quiet: the quiet square", "quiet: het stille vakje")
    dutch_text = dutch_text.replace("social: the social square", "social: het sociale vakje")

    stories = []
    for text in (english_text, dutch_text):
        board, clues = load_board(text)
        stories.append(Story(board, clues, Wording.read(text)))
    english, dutch = stories

    assert english._clue_text("in_row", ["Ada", "2"], ("Ada",)) == "Ada is in row 2"
    assert english._clue_text("not_in_row", ["Ben", "1"], ("Ben",)) == "Ben is not in row 1"
    assert english._clue_text("in_column", ["Cal", "3"], ("Cal",)) == "Cal is in column 3"
    assert english._clue_text("not_in_column", ["Ada", "1"], ("Ada",)) == ("Ada is not in column 1")
    assert english._clue_text("in_area_corner", ["Ada", "kitchen"], ("Ada",)) == (
        "Ada is in a corner, in the kitchen"
    )
    assert english._clue_text("adjacent_regions", ["Ada", "Ben"], ("Ada", "Ben")) == (
        "Ada and Ben are in neighboring regions"
    )
    assert english._clue_text("not_on_mark", ["Cal", "quiet", "social"], ("Cal",)) == (
        "Cal is not on the quiet square or the social square"
    )
    assert english._clue_text("has_attribute", ["Ben", "glasses"], ("Ben",)) == (
        "Ben has the glasses attribute"
    )
    assert english._clue_text("not_attribute", ["Ada", "glasses"], ("Ada",)) == (
        "Ada does not have the glasses attribute"
    )
    assert (
        english._clue_text("unique_attribute", ["glasses", "Ada", "Ben", "Cal"], ("Ada",))
        == "exactly one of Ada, Ben and Cal has the glasses attribute"
    )
    assert english._quantified_text(english.quantified_conditions["alone_with Ada role:guide"]) == (
        "Ada shares a region with exactly one other person, and that is a guide holder"
    )
    assert english._quantified_text(english.quantified_conditions["above Ada tag:inside"]) == (
        "Ada is somewhere above someone in the kitchen"
    )
    assert english._target_text(murdoku.TargetSelector("object_kind", "standable")) == (
        "someone on standable objects"
    )
    assert "she must be on the altar" in english._role_condition_text(
        next(rule for rule in english.role_conditions.values() if rule.kind == "role_on")
    )

    assert dutch._clue_text("in_row", ["Ada", "2"], ("Ada",)) == "Ada staat in rij 2"
    assert dutch._clue_text("not_in_column", ["Ada", "1"], ("Ada",)) == (
        "Ada staat niet in kolom 1"
    )
    assert dutch._clue_text("in_area_corner", ["Ada", "keuken"], ("Ada",)) == (
        "Ada staat in een hoek, in de keuken"
    )
    assert dutch._clue_text("has_attribute", ["Ben", "glasses"], ("Ben",)) == (
        "Ben heeft het kenmerk bril"
    )
    assert dutch._quantified_text(dutch.quantified_conditions["alone_with Ada role:guide"]) == (
        "Ada deelt een gebied met precies één ander persoon, en dat is een gids-drager"
    )
    assert "iemand in de keuken" in dutch._quantified_text(
        dutch.quantified_conditions["above Ada tag:inside"]
    )
    assert "zij" in dutch._role_condition_text(
        next(rule for rule in dutch.role_conditions.values() if rule.kind == "role_on")
    )


def test_explain_names_quantified_clue_that_determines_a_role():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Pronouns:
Ada: she her her
Roles:
guide: any
Marks:
altar: r1c1
Rules:
has_role Ada guide
Clues:
alone_with Ada role:guide
role_on Ada guide altar
"""
    story = explain(text)

    assert (
        "Ada shares a region with exactly one other person, and that is a guide holder (1)" in story
    )
    assert "she must be on the altar" in story


def test_explain_includes_static_attribute_and_uniqueness_clues():
    text = """Language: en
Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Attributes:
glasses: Ben
Words:
glasses: glasses
Clues:
has_attribute Ben glasses
not_attribute Ada glasses
unique_attribute glasses Ada Ben
"""
    story = explain(text)
    assert "Ben has the glasses attribute (1)" in story
    assert "Ada does not have the glasses attribute (2)" in story
    assert "Exactly one of Ada and Ben has the glasses attribute (3)" in story

    dutch_text = text.replace("Language: en", "Language: nl").replace(
        "glasses: glasses", "glasses: bril"
    )
    dutch = explain(dutch_text)
    assert "Ben heeft het kenmerk bril (1)" in dutch
    assert "Ada heeft het kenmerk bril niet (2)" in dutch
    assert "Precies één van Ada en Ben heeft het kenmerk bril (3)" in dutch


def test_region_capacity_count_explains_the_placement_it_forces():
    text = """Size: 2
Regions:
a: alcove
b: room
Grid:
a b
b b
People:
Ada
Ben
Clues:
in_row Ada 1
in_row Ben 2
count people in area:alcove = 1
"""
    solutions = bruteforce.solutions(text, "murdoku", limit=5)
    assert len(solutions) == 1
    assert solutions[0]["Ada"] == murdoku.Square(0, 0)

    story = explain(text)
    assert "Region capacity: exactly one person is in the alcove (3)" in story
    assert "Ada on r1c1" in story


def test_global_count_clues_are_explained_in_english_and_dutch():
    english_text = """Language: en
Size: 3
Regions:
a: west
b: east
c: garden
Grid:
a b c
a b c
a b c
People:
Ada
Ben
Roles:
bandit: any
Attributes:
glasses: Ben
AreaTags:
inside: east garden
Objects:
bed: standable r1c1
Marks:
seats: r1c2 r2c2
Words:
bed: the bed
inside: in the east or garden
glasses: glasses
bandit: bandit
seats: the seats
Clues:
count people on object:bed = 1
count people in rows:1,3 = 2
count people with role:bandit odd
count people with attribute:glasses = 1
count empty areas all = 1
count empty areas in tag:inside <= 1
count empty cells in mark:seats 1..2
count people in area:west = 1
count people in tag:inside odd
count people in columns:1-2 = 2
count people in mark:seats = 1
"""
    english = explain(english_text)
    assert "__global_" not in english
    assert "Exactly one person is on the bed (1)" in english
    assert "Exactly two people are in row 1 or 3 (2)" in english
    assert "An odd number of people have the bandit role (3)" in english
    assert "Exactly one person has the glasses attribute (4)" in english
    assert "Exactly one area is empty (5)" in english
    assert "At most one area is empty in the east or garden (6)" in english
    assert "Between one and two free cells are empty on the seats (7)" in english
    assert "Exactly one person is in the west (8)" in english
    assert "An odd number of people are in the east or garden (9)" in english
    assert "Exactly two people are in column 1 or 2 (10)" in english
    assert "Exactly one person is on the seats (11)" in english

    dutch_text = english_text.replace("Language: en", "Language: nl")
    dutch_text = dutch_text.replace("a: west", "a: westen").replace("b: east", "b: oosten")
    dutch_text = dutch_text.replace("c: garden", "c: tuin")
    dutch_text = dutch_text.replace("area:west", "area:westen")
    dutch_text = dutch_text.replace("inside: east garden", "inside: oosten tuin")
    dutch_text = dutch_text.replace(
        "Words:\n", "Words:\nwesten: in het westen\noosten: in het oosten\ntuin: in de tuin\n"
    )
    dutch_text = dutch_text.replace(
        "inside: in the east or garden", "inside: in het oosten of de tuin"
    )
    dutch_text = dutch_text.replace("bed: the bed", "bed: het bed")
    dutch_text = dutch_text.replace("glasses: glasses", "glasses: bril")
    dutch_text = dutch_text.replace("bandit: bandit", "bandit: bandiet")
    dutch_text = dutch_text.replace("seats: the seats", "seats: de stoelen")
    dutch = explain(dutch_text)
    assert "__global_" not in dutch
    assert "Precies één persoon staat op het bed (1)" in dutch
    assert "Precies twee mensen" in dutch
    assert "Een oneven aantal mensen" in dutch
    assert "Precies één persoon heeft het kenmerk bril (4)" in dutch
    assert "Precies één gebied is leeg (5)" in dutch
    assert "Precies één persoon is in het westen (8)" in dutch
    assert "Een oneven aantal mensen zijn in het oosten of de tuin (9)" in dutch
    assert "Precies twee mensen zijn in kolom 1 of 2 (10)" in dutch
    assert "Precies één persoon is op de stoelen (11)" in dutch


def test_story_explains_known_and_absent_roles():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Roles:
seer: any
Rules:
has_role Ada seer
Clues:
not_role Ben seer
"""
    story = explain(text)

    assert "Ada has the seer role" in story
    assert "Ben does not have the seer role (1)" in story
    assert "__occupant" not in story


def test_story_explains_role_deduced_from_eligibility_and_count():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Roles:
bandit: 1
RoleEligibility:
bandit: Ada
"""
    story = explain(text)

    assert "Ada has the bandit role" in story
    assert "Ben does not have the bandit role" in story
    assert "__occupant" not in story


def test_story_explains_role_conditioned_location_rule():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Roles:
captain: 1
Marks:
altar: r1c1
Rules:
has_role Ada captain
Clues:
role_on Ada captain altar
"""
    story = explain(text)

    assert "Ada has the captain role" in story
    assert "Ada's" not in story
    assert "If Ada has role captain, they must be on the altar" in story


def test_story_explains_a_reified_count_constraint():
    square = murdoku.Square
    board = murdoku.Board(
        2,
        [["west", "east"], ["west", "east"]],
        {"west": "west", "east": "east"},
        [],
        ["Ada", "Ben"],
    )
    story = Story(board, [("outside", ["Ada", "west"])], Wording())
    west_cells = [story.model.literal("Ada", square(row, 0)) for row in range(2)]
    is_empty = story.model.literal("west_empty", "yes")
    is_occupied = story.model.literal("west_empty", "no")
    story.model.constrain(
        "west occupancy",
        Kind.COUNT,
        west_cells,
        allowed_counts={0},
        reified_by=is_empty,
    )
    story.model.constrain(
        "west empty state", Kind.EXACTLY_ONE, [is_empty, is_occupied], defines="west_empty"
    )

    assert (
        "The allowed counts for west occupancy are zero, so the literal west_empty=yes must hold."
        in story.tell()
    )


def test_mark_occupant_story_hides_internal_auxiliary_variables():
    text = """Size: 2
Regions:
a: room
b: garden
Grid:
a b
a b
People:
Ada
Ben
Marks:
quiet: r1c1 ; alone
Clues:
on_mark Ada quiet
outside Ben room
"""
    story = explain(text)

    assert "Ada on r1c1" in story
    assert "Ben on r2c2" in story
    assert "__occupant_" not in story


def test_story_explains_complementary_reified_counts():
    square = murdoku.Square
    board = murdoku.Board(
        2,
        [["west", "east"], ["west", "east"]],
        {"west": "west", "east": "east"},
        [],
        ["Ada", "Ben"],
    )
    story = Story(board, [], Wording())
    first, second = square(0, 0), square(1, 0)
    first_literal = story.model.literal("Ada", first)
    second_literal = story.model.literal("Ada", second)
    empty = story.model.literal("west_empty", True)
    occupied = story.model.literal("west_empty", False)
    story.model.constrain(
        "west empty state", Kind.EXACTLY_ONE, [empty, occupied], defines="west_empty"
    )
    story.model.constrain(
        "west occupancy",
        Kind.COUNT,
        [first_literal, second_literal],
        allowed_counts={0},
        reified_by=empty,
    )
    story.model.eliminate(empty, "setup", "known occupied")
    story.model.eliminate(first_literal, "setup", "not this square")
    story.model.log.clear()

    assert "The allowed counts for west occupancy are one or two" in story.tell()


@pytest.mark.parametrize(
    "name",
    ["murdoku_intro.txt", "murdoku_house.txt", "murdoku_sparse_mystery.txt"],
)
def test_english_story_places_everyone_right_and_titles_name_them(name):
    text = (EXAMPLES / name).read_text()
    (solution,) = bruteforce.solutions(text)
    story = explain(text)
    stated = re.findall(r"\*\*(\w+) on r(\d+)c(\d+)\*\*", story)
    assert {who: (int(r) - 1, int(c) - 1) for who, r, c in stated} == {
        who: (sq.row, sq.col) for who, sq in solution.items()
    }
    assert len(stated) == len(solution), "each person is placed in bold exactly once"
    for paragraph in story.split("\n\n")[1:]:
        title = re.match(r"- \*\*(.+?)\.\*\*", paragraph)[1]
        placed = re.findall(r"\*\*(\w+) on ", paragraph)
        assert title == "The rest" or all(who in title for who in placed), paragraph


def test_opening_narrows_clue_by_clue_and_places_whoever_it_pins_down():
    story = explain((EXAMPLES / "murdoku_house.txt").read_text())
    opening = story.split("\n\n")[0]
    assert "Ben is on the sofa (4): r3c3 or r3c4." in opening
    assert "Ben is not next to the lamp (6): **Ben on r3c4**." in opening


def test_counting_clue_is_worded_and_known_placements_are_not_bold_again():
    story = explain((EXAMPLES / "murdoku_house.txt").read_text())
    assert "Either Ada is in the study, or Ben is in the hall, but not both (1)." in story
    assert "Ben is on r3c4, so Ada is not in the study" in story


def test_chains_are_told_as_if_then_with_the_reason_for_each_link():
    text = (EXAMPLES / "prrrdoku2.txt").read_text()
    original_clues = text.replace("above Anna Mao 5\n", "in_region Jos keukenwinkel\n")
    story = explain(original_clues.replace("at_least Jos Mao 13\n", ""))
    assert (
        "Als Otto niet op r6k5 zit, dan zit Otto op r7k6, dan zit Luna niet op r7k4 (rij 7), "
        "dan zit Luna op r8k3. Dus Otto zit op r6k5 of Luna zit op r8k3; hoe dan ook"
    ) in story
    assert "Tjitske zit op r5k2 of Tjitske zit op r6k1; hoe dan ook" in story


def test_story_cites_clue_numbers():
    story = explain((EXAMPLES / "prrrdoku1.txt").read_text())
    assert "Otto is precies één rij boven Tjitske (5)" in story
    assert "Jos is ergens links van Otto (8)" in story


def test_story_in_english():
    board, clues = load_board((EXAMPLES / "prrrdoku1.txt").read_text())
    story = Story(board, clues, Wording()).tell()
    assert story.startswith("- **The direct clues.**")
    assert "**Tim on r1c1**" in story
    assert "Otto is exactly one row above Tjitske (5)" in story


def test_wording_reads_its_sections_and_rejects_unknown_languages():
    say = Wording.read("Language: nl\nWords:\nvuurtje: het vuurtje\n")
    assert say.language == "nl" and say.words == {"vuurtje": "het vuurtje"}
    with pytest.raises(ValueError, match="no wording for language"):
        Wording.read("Language: xx\n")
    with pytest.raises(ValueError, match="Words"):
        Wording.read("Words:\nvuurtje\n")


def test_cli_explain(capsys):
    assert cli.main([str(EXAMPLES / "prrrdoku1.txt"), "--explain"]) == 0
    assert "**Tim op r1k1**" in capsys.readouterr().out
    assert cli.main([str(EXAMPLES / "sudoku_easy.txt"), "--explain"]) == 2


def test_board_rules_are_what_the_model_is_built_from():
    board, clues = load_board((EXAMPLES / "prrrdoku1.txt").read_text())
    model = murdoku.compile_puzzle(board, clues)
    names = {rule.name for rule in murdoku.board_rules(board)}
    assert names == {c.name for c in model.constraints}
