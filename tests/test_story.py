"""Tests for the worked-solution writer and the proof it is built on.

Every placement a story states is checked against the brute force, so a
story can be clumsy but never wrong.
"""

import ast
import dataclasses
import re
from itertools import pairwise
from pathlib import Path

import pytest

import csp
from csp import bruteforce, cli, murdoku, sudoku
from csp.core import Kind, Model, Solver, Step, rule_single
from csp.proof import Episode, Inference, Move, episodes, replay, shortest
from csp.puzzlefile import detect, load_board_layout, load_presentation
from csp.story import (
    Wording,
    board_notes,
    explain,
    family_rules,
    murdoku_key,
    murdoku_reference_rules,
    murdoku_rules,
)
from tests.examples import example, played_examples

pytestmark = pytest.mark.solutions

PRRRDOKUS = ["prrrdoku1.txt", "prrrdoku2.txt", "prrrdoku3.txt"]
PLACED = re.compile(r"(\w+) op r(\d+)k(\d+)")


@pytest.mark.parametrize("number,murderer", [(1, "Carmen"), (2, "Diego"), (3, "Gonzalo")])
def test_halloween_reveal_names_the_unique_solved_murderer(number, murderer):
    text = example(f"halloween-museum-{number}.txt").read_text()
    board = load_board_layout(text)
    solutions = bruteforce.solutions(text, "murdoku", limit=2)
    assert len(solutions) == 1
    assert [
        person for person in board.people if solutions[0][board.role_variable(person, "murderer")]
    ] == [murderer]
    assert text.split("Reveal:\n", 1)[1].startswith(f"{murderer},")


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
    "sudoku_story": {"core", "proof", "story", "sudoku"},
    "generic_story": {"core", "proof", "story"},
    "murdoku_story": {
        "generic_story",
        "core",
        "murdoku",
        "murdoku_eval",
        "murdoku_expression_file",
        "murdoku_expression_words",
        "murdoku_lang",
        "murdoku_lower",
        "proof",
        "story",
    },
    "murdoku": {"core"},
    "murdoku_lang": {"murdoku", "murdoku_eval"},
    "murdoku_declarations": {"murdoku", "murdoku_lang"},
    "murdoku_expr_lint": {"murdoku", "murdoku_lang", "murdoku_lower", "murdoku_typecheck"},
    "murdoku_expression_file": {"murdoku", "murdoku_lang", "murdoku_typecheck", "puzzlefile"},
    "murdoku_expression_report": {"core", "murdoku_lang", "murdoku_lower", "report"},
    "murdoku_expression_words": {"murdoku", "murdoku_lang", "murdoku_typecheck", "puzzlefile"},
    "murdoku_lower": {"core", "murdoku", "murdoku_lang", "murdoku_typecheck"},
    "murdoku_typecheck": {"murdoku", "murdoku_lang"},
    "murdoku_eval": {"murdoku", "murdoku_lang", "murdoku_typecheck"},
    "sudoku": {"core", "puzzlefile", "towers"},
    "calcudoku": {"core", "puzzlefile"},
    "futoshiki": {"core", "puzzlefile"},
    "story": {
        "core",
        "proof",
        "murdoku",
        "murdoku_lang",
        "murdoku_expression_words",
        "murdoku_expression_file",
        "murdoku_story",
        "puzzlefile",
        "sudoku",
        "battleships",
        "minesweeper",
        "starbattle",
    },
    "docx_export": {
        "icons",
        "murdoku",
        "murdoku_expression_file",
        "murdoku_lower",
        "picture",
        "puzzlefile",
        "rooms",
        "story",
    },
    "murdoku_board": {
        "svg",
        "bruteforce",
        "murdoku",
        "puzzlefile",
        "picture",
        "clue_search",
        "murdoku_expression_file",
        "murdoku_lang",
    },
    "regiongrid": {"puzzlefile"},
    "suguru": {"core", "puzzlefile", "regiongrid"},
    "starbattle": {"core", "regiongrid", "icons"},
    "logicgrid": {"core", "puzzlefile"},
    "rooms": {"core", "puzzlefile"},
    "rooms_search": {"bruteforce", "core", "puzzlefile", "report", "rooms"},
    "binairo": {"core", "puzzlefile", "icons"},
    "tents": {"core", "puzzlefile", "icons"},
    "minesweeper": {"core", "puzzlefile", "icons"},
    "akari": {"core", "puzzlefile", "icons"},
    "kakurasu": {"core", "puzzlefile", "icons"},
    "battleships": {"core", "puzzlefile", "icons"},
    "towers": {"core", "puzzlefile"},
    "mosaic": {"core", "puzzlefile"},
    "dominosa": {"core", "puzzlefile"},
    "rectangles": {"core", "puzzlefile"},
    "magnets": {"core", "puzzlefile"},
    "undead": {"core", "puzzlefile"},
    "pattern": {"core", "puzzlefile"},
    "mapcolour": {"core", "puzzlefile"},
    "kakuro": {"core", "puzzlefile"},
    "hidato": {"core", "puzzlefile"},
    "thermometers": {"core", "puzzlefile"},
    "bridges": {"core", "puzzlefile", "icons"},
    "collection": set(),
    "web": {
        "akari",
        "bridges",
        "murdoku_expression_file",
        "murdoku_expression_words",
        "murdoku_lower",
        "collection",
        "core",
        "dominosa",
        "hidato",
        "icons",
        "mapcolour",
        "murdoku",
        "minesweeper",
        "picture",
        "puzzlefile",
        "rectangles",
        "rooms",
        "starbattle",
        "story",
        "svg",
    },
    "picture": {
        "murdoku",
        "bridges",
        "sudoku",
        "calcudoku",
        "futoshiki",
        "suguru",
        "starbattle",
        "logicgrid",
        "rooms",
        "binairo",
        "tents",
        "minesweeper",
        "akari",
        "kakurasu",
        "battleships",
        "towers",
        "mosaic",
        "dominosa",
        "rectangles",
        "magnets",
        "undead",
        "pattern",
        "mapcolour",
        "kakuro",
        "hidato",
        "thermometers",
        "icons",
        "svg",
    },
}


@pytest.mark.parametrize(
    "language,expected",
    [
        (
            "en",
            "Mark the mines: each number tells how many of its eight neighbours are mines. "
            "There are 9 mines in total.",
        ),
        (
            "nl",
            "Markeer de mijnen: elk getal geeft aan hoeveel van de acht buurvakjes een mijn "
            "zijn. Er liggen in totaal 9 mijnen.",
        ),
    ],
)
def test_minesweeper_rules_include_the_total_in_both_languages(language, expected):
    text = example("minesweeper_3_8x8.txt").read_text()
    if language == "nl":
        text += "\nLanguage:\nnl\n"
    assert family_rules(text, "minesweeper") == [expected]


@pytest.mark.parametrize(
    "language",
    ["en", "nl"],
)
def test_minesweeper_rules_without_total_keep_the_existing_wording(language):
    text = example("minesweeper_3_8x8.txt").read_text().split("\nTotalMines:", 1)[0] + "\n"
    if language == "nl":
        text += "Language:\nnl\n"
    assert family_rules(text, "minesweeper") == [
        "Mark the mines: each number tells how many of its eight neighbours are mines."
    ]


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
    model = cli.load(example(name).read_text(), "murdoku").model
    moves = _moves(model)
    kept = shortest(model, moves)
    assert len(kept) <= len(moves)
    assert all(move in moves for move in kept)
    assert replay(model, kept).solution() == replay(model, moves).solution()


def test_shortest_proof_drops_what_ifs_it_can_do_without():
    model = cli.load(example("prrrdoku3.txt").read_text(), "murdoku").model
    moves = _moves(model)
    kept = shortest(model, moves)
    assert sum(m.rule == "what_if" for m in kept) < sum(m.rule == "what_if" for m in moves)


def test_replay_reports_each_change_like_the_solver():
    model = cli.load(example("prrrdoku1.txt").read_text(), "murdoku").model
    fired: list[str] = []
    replay(model, _moves(model), lambda rule, steps: fired.append(rule))
    assert fired.count("single") == len(model.variables)
    assert {"relations", "subsumption"} <= set(fired)


def test_shortest_keeps_required_evidence_without_redundant_moves():
    model = Model()
    options = [model.literal("x", value) for value in (1, 2)]
    model.constrain("x", Kind.EXACTLY_ONE, options, defines="x")
    model.relate("ordinary", ["x"], lambda x: x == 1)
    model.relate("themed", ["x"], lambda x: x == 1)
    ordinary = Move("relations", ("ordinary",))
    themed = Move("relations", ("themed",))

    assert shortest(model, [ordinary, themed]) == [ordinary]
    kept = shortest(model, [ordinary, themed], required=[themed])
    assert kept == [themed]
    assert replay(model, kept).solution() == {"x": 1}
    with pytest.raises(ValueError, match="required moves"):
        shortest(model, [ordinary], required=[themed])
    with pytest.raises(ValueError, match="cannot all fire"):
        shortest(model, [ordinary, themed], required=[ordinary, themed])


def test_shortest_preserves_prerequisites_for_required_moves():
    model = Model()
    for var in ("x", "y", "z"):
        model.constrain(
            var, Kind.EXACTLY_ONE, [model.literal(var, value) for value in (1, 2)], defines=var
        )
    model.relate("prerequisite", ["y"], lambda y: y == 1)
    model.relate("themed", ["x", "y"], lambda x, y: x != y)
    model.relate("later", ["x", "y", "z"], lambda x, y, z: (x, y, z) == (2, 1, 1))
    prerequisite = Move("relations", ("prerequisite",))
    themed = Move("relations", ("themed",))
    later = Move("relations", ("later",))

    kept = shortest(model, [prerequisite, themed, later], required=[themed])
    assert kept == [prerequisite, themed, later]
    _, groups = episodes(model, kept)
    assert any(group.pattern.move is themed for group in groups)


def test_episodes_preserve_replay_order_and_pattern_evidence():
    model, _ = sudoku.compile_puzzle(example("sudoku_17_9x9_pointing.txt").read_text())
    moves = shortest(model, _moves(model))
    expected: list[tuple[str, tuple[Step, ...]]] = []
    solved = replay(model, moves, lambda rule, steps: expected.append((rule, tuple(steps))))
    result, groups = episodes(model, moves)
    inferences = [
        inference for group in groups for inference in (group.pattern, *group.consequences)
    ]

    assert [(item.rule, item.steps) for item in inferences] == expected
    assert result.solution() == solved.solution()
    assert any(group.pattern.rule == "subsumption" for group in groups)
    assert any(group.consequences for group in groups)
    for current, following in pairwise(inferences):
        trial = current.before.clone()
        changed = rule_single(trial) if current.move is None else current.move.apply(trial)
        assert changed
        assert tuple(trial.log) == current.steps
        assert all(
            trial.is_true(lit) == following.before.is_true(lit)
            and trial.is_false(lit) == following.before.is_false(lit)
            for lit in range(trial.num_literals)
        )
    for group in groups:
        if group.pattern.rule == "subsumption":
            assert group.pattern.steps[0].sources
            assert group.pattern.steps[0].scope


# --- story ----------------------------------------------------------------

MOST_TOKYO = (
    "every ?b in (areas except area:Tokyo): count (people in ?b) < count (people in area:Tokyo)"
)
LEAST_OKINAWA = (
    "every ?b in (area of free cells except area:Okinawa): "
    "count (people in ?b) > count (people in area:Okinawa)"
)
TIED_QUIETEST = (
    "count (people in area:Hiroshima) = count (people in area:Okinawa) and "
    "every ?b in (area of free cells except area:Okinawa,area:Hiroshima): "
    "count (people in ?b) > count (people in area:Okinawa)"
)


def _move_clue_to_rules(text, source):
    assert text.count(source + "\n") == 1
    assert "Rules:" not in text
    return text.replace(source + "\n", "").replace("Clues:\n", f"Rules:\n{source}\n\nClues:\n")


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_every_placement_in_the_story_is_right(name):
    text = (example(name)).read_text()
    (solution,) = bruteforce.solutions(text)
    story = explain(text)
    placed = {who: f"r{solution[who].row + 1}k{solution[who].col + 1}" for who in solution}
    stated = [
        (who, f"r{r}k{c}")
        for bold in re.findall(r"\*\*(.*?)\*\*", story, flags=re.DOTALL)
        for who, r, c in PLACED.findall(bold)
        if who in placed
    ]
    assert {who for who, _ in stated} == set(placed)
    assert all(placed[who] == square for who, square in stated)


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_story_is_bullets_and_leads_with_the_direct_clues(name):
    story = explain((example(name)).read_text())
    paragraphs = story.split("\n\n")
    assert all(p.startswith("- ") and "**" in p for p in paragraphs)
    assert paragraphs[0].startswith("- **De directe aanwijzingen.**")


def test_story_never_reads_out_the_english_label_of_a_hidden_population_literal():
    """`busiest_area`/`quietest_area` compile hidden "holds at least k" literals.

    Their names are engine labels, so a Dutch explanation has to say them in Dutch
    instead of quoting "Voor Hiroshima holds at least 2 ...".
    """
    story = explain(example("japan-1-samen-in-de-blauwe-bladeren.txt").read_text())
    assert "holds at least" not in story
    assert "toegestane aantallen" not in story
    assert (
        "Goro bezet rij 4 en kolom 6, Tatsuya bezet kolom 7 en Renji bezet kolom 5: "
        "alle andere vrije vakjes in Hiroshima vallen af, dus **alleen Goro zit in Hiroshima**."
    ) in story
    assert (
        "De gebieden met de minste mensen zijn Hiroshima en Okinawa (2), "
        "dus **alleen Tatsuya zit in Okinawa**."
    ) in story


def test_tied_population_explanation_uses_the_puzzles_own_names_and_language():
    text = (
        example("japan-1-samen-in-de-blauwe-bladeren.txt")
        .read_text()
        .replace("Language: nl", "Language: en")
        .replace("Hiroshima", "Harbor")
        .replace("Okinawa", "Island")
        .replace("Goro", "Alex")
        .replace("Tatsuya", "Robin")
    )
    story = explain(text)
    assert (
        "all other free squares in Harbor are unavailable, so **only Alex is in Harbor**." in story
    )
    assert (
        "The areas with the fewest people are Harbor and Island (2), "
        "so **only Robin is in Island**."
    ) in story


def test_tied_population_explanation_accepts_an_unnumbered_rule():
    text = _move_clue_to_rules(
        example("japan-1-samen-in-de-blauwe-bladeren.txt").read_text(), TIED_QUIETEST
    )
    story = explain(text)
    assert (
        "De gebieden met de minste mensen zijn Hiroshima en Okinawa, "
        "dus **alleen Tatsuya zit in Okinawa**."
    ) in story


def test_story_says_area_capacity_the_way_a_person_does():
    """The count rule's shared-capacity step reads as the counting argument."""
    story = explain(example("japan-2-samen-onderweg.txt").read_text())
    assert "Keiko staat naast de lantaarn (3): **in Osaka**." in story
    assert "Mio zit op de bank (4): **in Osaka**." in story
    assert "Keiko en Mio zijn in Osaka, dus **daar zijn minstens twee mensen**." in story
    assert (
        "Het gebied met de meeste mensen is Tokyo (1), "
        "dus **zijn er in Tokyo minstens drie mensen**."
    ) in story
    assert "Samen zijn dat alle vijf mensen, dus **niemand is in Okinawa**." in story
    assert (
        "Haru staat boven Jun (5), dus **Haru staat niet in rij 5** en **Jun staat niet in rij 1**."
    ) in story
    assert "Haru zit niet in Okinawa, Isamu zit niet in Okinawa" not in story
    assert "holds at least" not in story
    assert "minstens één mensen" not in story


def test_story_explains_the_area_comparison_in_english():
    text = example("japan-2-samen-onderweg.txt").read_text().replace("Language: nl", "Language: en")
    story = explain(text)
    assert "Keiko and Mio are in Osaka, so **at least two people are there**." in story
    assert (
        "The area with the most people is Tokyo (1), so **at least three people are in Tokyo**."
    ) in story
    assert "Together that accounts for all five people, so **nobody is in Okinawa**." in story


def test_story_uses_the_actual_population_clue_number():
    text = example("japan-2-samen-onderweg.txt").read_text()
    original = MOST_TOKYO + "\n" + LEAST_OKINAWA
    assert original in text
    text = text.replace(original, LEAST_OKINAWA + "\n" + MOST_TOKYO)
    story = explain(text)
    assert "Het gebied met de meeste mensen is Tokyo (2)" in story


def test_story_population_reason_uses_the_puzzles_own_areas():
    text = (
        example("japan-2-samen-onderweg.txt")
        .read_text()
        .replace("Tokyo", "North")
        .replace("Osaka", "West")
        .replace("Okinawa", "East")
    )
    story = explain(text)
    assert "Keiko en Mio zijn in West, dus **daar zijn minstens twee mensen**." in story
    assert "Het gebied met de meeste mensen is North (1)" in story
    assert "dus **niemand is in East**" in story


def test_story_does_not_invent_population_witnesses():
    text = (
        example("japan-2-samen-onderweg.txt")
        .read_text()
        .replace("Keiko beside object:lantaarn", "Keiko beside object:torii")
    )
    story = explain(text)
    assert "Keiko staat naast de torii (3): **in Tokyo**." in story
    assert "Keiko en Mio zijn in Osaka" not in story


def test_story_does_not_treat_tied_busiest_areas_as_strictly_ordered():
    text = example("japan-2-samen-onderweg.txt").read_text()
    assert MOST_TOKYO in text
    text = text.replace(
        MOST_TOKYO,
        "count (people in area:Tokyo) = count (people in area:Osaka) and "
        + MOST_TOKYO.replace("except area:Tokyo", "except area:Tokyo,area:Osaka"),
    )
    board = load_board_layout(text)
    solutions = bruteforce.solutions(text, "murdoku", limit=2)
    assert solutions
    for solution in solutions:
        areas = [board.region_of(solution[person]) for person in board.people]
        assert areas.count(board.region_id("Tokyo")) == areas.count(board.region_id("Osaka"))
    assert "minstens drie mensen" not in explain(text)


def test_story_can_explain_an_unnumbered_population_rule():
    text = _move_clue_to_rules(example("japan-2-samen-onderweg.txt").read_text(), MOST_TOKYO)
    story = explain(text)
    assert (
        "Het gebied met de meeste mensen is Tokyo, dus **zijn er in Tokyo minstens drie mensen**."
        in story
    )


def test_story_omits_population_clue_numbers_in_unnumbered_explanations():
    story = explain(example("japan-2-samen-onderweg.txt").read_text(), numbered=False)
    assert (
        "Het gebied met de meeste mensen is Tokyo, dus **zijn er in Tokyo minstens drie mensen**."
        in story
    )
    assert not re.search(r"\(\d+\)", story)


def test_story_describes_by_region_and_row_before_squares():
    story = explain((example("prrrdoku3.txt")).read_text())
    assert "Luna is op de woonboot of Luna is in het water" in story
    assert "Otto en Pip staan in hetzelfde gebied" in story
    assert "Luna moet in kolom 1 staan" in story
    assert "de regel van één persoon per rij of kolom sluit iedereen anders uit" in story
    assert (
        "sluit Luna op r6k2 uit: ieder overgebleven vakje voor Jos (r8k3 of r8k4) ligt minstens "
        "zo ver van elk overgebleven vakje voor Mao (r1k8, r1k9, r2k9 of r6k9) als Luna zou liggen"
        in story
    )
    assert story.index("sluit Luna op r6k2 uit:") < story.index("Luna moet in kolom 1 staan")


def test_opening_uses_shared_columns_across_regions():
    opening = explain(example("japan-1-samen-in-de-blauwe-bladeren.txt").read_text()).split("\n\n")[
        0
    ]
    assert (
        "Mizuki zit op een vakje dat de torii raakt (5): **in kolom 1**, dus "
        "**streep de zes andere nog open vakjes in die kolom weg: "
        "r2k1, r5k1, r6k1, r7k1, r8k1 en r9k1**."
    ) in opening
    assert (
        "Goro zit op een vakje dat het uithangbord met kanji raakt (7): **in kolom 6**, dus "
        "**streep de zes andere nog open vakjes in die kolom weg: "
        "r2k6, r5k6, r6k6, r7k6, r8k6 en r9k6**."
    ) in opening


LINE_RESERVATIONS = """Size: 4
Language: en
Regions:
a: west
b: east
Grid:
a a b b
a a b b
b b a a
b b a a
PointObjects:
beacon: r2.5c0.5
sign: r0.5c2.5
People:
Ada
Ben
Cleo
Dirk
Clues:
Ada on point_object:beacon
Ben on point_object:sign
"""


def test_opening_crosses_out_each_open_square_only_once():
    opening = explain(LINE_RESERVATIONS).split("\n\n")[0]
    assert (
        "Ada is on a cell touching the beacon (1): **in column 1**, so "
        "**cross out the other two open squares in that column: r1c1 and r4c1**."
    ) in opening
    assert (
        "Ben is on a cell touching the sign (2): **in row 1**, so "
        "**cross out the other open square in that row**."
    ) in opening

    solutions = bruteforce.solutions(LINE_RESERVATIONS, limit=1000)
    assert len(solutions) == 16
    crossed = {murdoku.Square(0, 0), murdoku.Square(3, 0), murdoku.Square(0, 3)}
    assert all(not crossed.intersection(solution.values()) for solution in solutions)


def test_opening_does_not_count_blocking_objects_as_open_squares():
    text = LINE_RESERVATIONS.replace(
        "PointObjects:", "Objects:\nrock: blocking r4c1\nPointObjects:"
    )
    opening = explain(text).split("\n\n")[0]
    assert (
        "Ada is on a cell touching the beacon (1): **in column 1**, so "
        "**cross out the other open square in that column**."
    ) in opening


def test_opening_reserves_the_clue_owners_line_for_exclusive_objects():
    text = LINE_RESERVATIONS.replace(
        "PointObjects:", "Objects:\nbench: standable r1c1 r1c2 r1c3\nPointObjects:"
    ).replace(
        "Ada on point_object:beacon\nBen on point_object:sign\n", "(people on object:bench) = Ada"
    )
    opening = explain(text).split("\n\n")[0]
    assert (
        "Ada is the only person on the bench (1): **in row 1**, so "
        "**cross out the other open square in that row**."
    ) in opening
    solutions = bruteforce.solutions(text, limit=1000)
    assert solutions
    assert all(murdoku.Square(0, 3) not in solution.values() for solution in solutions)


def test_opening_skips_crossing_out_when_nothing_is_still_open():
    text = (
        LINE_RESERVATIONS.replace(
            "PointObjects:", "Objects:\nstool: standable r1c2\nchair: standable r4c4\nPointObjects:"
        )
        .replace("Ada\nBen\nCleo\nDirk", "Eva\nFaye\nAda\nBen")
        .replace(
            "Ada on point_object:beacon\nBen on point_object:sign\n",
            "Eva on object:stool\nFaye on object:chair\nAda on point_object:beacon\n",
        )
    )
    opening = explain(text).split("\n\n")[0]
    assert "Ada is on a cell touching the beacon (3): **in column 1**." in opening
    assert "cross out" not in opening


def test_opening_does_not_cross_out_from_an_unstated_line_premise():
    text = LINE_RESERVATIONS.replace("beacon: r2.5c0.5", "beacon: r2.5c2.5").replace(
        "Clues:", "Rules:\nnot (Ada in rows:3)\nClues:"
    )
    opening = explain(text).split("\n\n")[0]
    premise = "rule 1: Ada is not in row 3"
    deduction = (
        "Ada is on a cell touching the beacon (1): **in row 2**, so "
        "**cross out the other two open squares in that row: r2c1 and r2c4**."
    )
    assert deduction in opening
    assert opening.index(premise) < opening.index(deduction)


def test_opening_does_not_repeat_a_clue_as_its_own_deduction():
    opening = explain(example("murdoku_1_first_case.txt").read_text()).split("\n\n")[0]
    assert "Ingrid is on a chair (1)." in opening
    assert "Ingrid is on a chair (1): on a chair." not in opening


@pytest.mark.parametrize(
    ("name", "clue"),
    [
        ("zoo-murdoku-2.txt", "De makaak is in kolom 5 (4)."),
        (
            "zoo-murdoku-2.txt",
            "De tijger is in rij 1 (8), dus **streep het andere nog open vakje in die rij weg**.",
        ),
        ("food-murdoku-2.txt", "Tempura is in row 4 (3)."),
        (
            "food-murdoku-2.txt",
            "Ramen is in column 4 (8), so **cross out the other two open squares in that "
            "column: r2c4 and r5c4**.",
        ),
        (
            "murdoku_orient_express_3.txt",
            "Bogdan zit op een vakje dat een raam raakt (10): **bij een raam**.",
        ),
    ],
)
def test_opening_does_not_restate_line_or_edge_clues(name, clue):
    opening = explain(example(name).read_text()).split("\n\n")[0]
    assert clue in opening


def test_new_murdoku_clues_have_dutch_wording():
    from csp.murdoku_expression_words import ExpressionWords
    from csp.murdoku_lang import parse_statement

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
    words = ExpressionWords(board, "nl", {"stoel": "de stoel", "bed": "het bed"})
    assert words.statement(parse_statement("not Anna on object:stoel")) == (
        "Anna zit niet op de stoel"
    )
    assert words.statement(parse_statement("(people on object:bed) = Anna")) == (
        "Anna is de enige persoon op het bed"
    )
    assert words.statement(parse_statement("Eli in corner:board")) == "Eli is in een rasterhoek"
    assert words.statement(parse_statement("Anna dir:left Eli = 1")) == (
        "Anna staat precies één kolom links van Eli"
    )


def test_story_can_name_a_boundary_door():
    from csp.murdoku_expression_words import ExpressionWords
    from csp.murdoku_lang import parse_statement

    square = murdoku.Square
    board = murdoku.Board(
        2,
        [["west", "east"], ["west", "east"]],
        {"west": "west", "east": "east"},
        [],
        ["Ada", "Ben"],
        edge_items=[murdoku.EdgeItem("gate", "door", (square(0, 0), square(0, 1)))],
    )
    words = ExpressionWords(board, "nl", {"gate": "de deur"})
    assert words.statement(parse_statement("Ada on edge_item:gate")) == (
        "Ada zit op een vakje dat de deur raakt"
    )
    assert words.statement(parse_statement("Ada beside edge_item:gate")) == (
        "Ada staat naast een vakje dat de deur raakt"
    )


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
Ada on mark:safe_zone
not Ben on mark:safe_zone
"""
    assert csp.story.clue_texts(text) == [
        "Ada is on a cell marked safe zone.",
        "Ben is not on a cell marked safe zone.",
    ]
    assert csp.story.clue_texts("Language: nl\n" + text) == [
        "Ada zit op een vakje met de markering safe zone.",
        "Ben zit niet op een vakje met de markering safe zone.",
    ]


def test_expression_targets_and_names_are_worded_in_english_and_dutch():
    from csp.murdoku_expression_file import load_expression_board
    from csp.murdoku_expression_words import ExpressionWords
    from csp.murdoku_lang import parse_statement

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
every role:guide is attribute:glasses
Clues:
count (people in area of Ada) = 2 and every ((people in area of Ada) except Ada) is role:guide
Ada dir:up tag:inside
if Ada is role:guide then Ada on mark:altar
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

    languages = {}
    for text in (english_text, dutch_text):
        board, _, clues = load_expression_board(text)
        words = ExpressionWords.read(board, text)
        languages[words.language] = words, clues

    def say(source, language="en"):
        return languages[language][0].statement(parse_statement(source))

    assert say("Ada in rows:2") == "Ada is in row 2"
    assert say("not Ben in rows:1") == "Ben is not in row 1"
    assert say("Cal in columns:3") == "Cal is in column 3"
    assert say("not Ada in columns:1") == "Ada is not in column 1"
    assert say("Ada in area:kitchen") == "Ada is in the kitchen"
    assert say("Ada in rows:2", "nl") == "Ada is in rij 2"
    assert say("not Ada in columns:1", "nl") == "Ada is niet in kolom 1"
    assert say("Ada in area:keuken", "nl") == "Ada is in de keuken"
    for language, attribute, guide, quiet, social, room, altar in (
        ("en", "glasses", "guide", "the quiet square", "the social square", "kitchen", "the altar"),
        ("nl", "bril", "gids", "het stille vakje", "het sociale vakje", "keuken", "het altaar"),
    ):
        assert attribute in say("Ben is attribute:glasses", language)
        negative = say("not Ada is attribute:glasses", language)
        assert attribute in negative
        assert ("not" if language == "en" else "niet") in negative
        union = say("not Cal on (mark:quiet, social)", language)
        assert quiet in union and social in union
        counted = say("count ((Ada, Ben, Cal) is attribute:glasses) = 1", language)
        assert attribute in counted and "1" in counted
        words, clues = languages[language]
        companion = words.statement(clues[0])
        assert guide in companion
        assert ("one other person" if language == "en" else "één ander persoon") in companion
        assert room in words.statement(clues[1])
        conditional = words.statement(clues[2])
        assert guide in conditional and altar in conditional
        assert ("if" if language == "en" else "als") in conditional.casefold()
        assert "standable" in say("some (people on object_kind:standable) dir:up Ada", language)


@pytest.mark.parametrize("number", [1, 2, 3])
def test_vietnam_avoidance_clues_name_dish_cells_not_occupants(number):
    from csp.murdoku_expression_file import load_expression_board
    from csp.murdoku_expression_words import ExpressionWords
    from csp.story import figure_clues

    text = example(f"vietnam-murdoku-{number}.txt").read_text()
    board, _, statements = load_expression_board(text)
    words = ExpressionWords.read(board, text)
    clues = [words.statement(dataclasses.replace(clue, wording=None)) for clue in statements]
    for person, clue in zip(("Pippo", "Swena"), clues[:2], strict=True):
        assert clue.startswith(f"{person} staat niet op of direct naast een vakje van de bún chả")
        assert "een vakje van de thịt kho" in clue
        assert "een vakje van de phá lấu" in clue
        assert "(ook niet schuin, en dit geldt zelfs over gebiedsgrenzen heen)" in clue
        assert "iemand" not in clue
        assert "koningszet" not in clue
        assert "Het is niet zo" not in clue
    figures = figure_clues(text).figures
    for figure, clue_number in zip(figures[:2], (1, 2), strict=True):
        assert any(clue_number in paragraph.sources for paragraph in figure.clues)
        assert "staat niet op of direct naast een vakje met een varkensvleesgerecht" in (
            figure.clues[0].text
        )
        assert "(ook niet schuin, en dit geldt zelfs over gebiedsgrenzen heen)" in (
            figure.clues[0].text
        )


@pytest.mark.parametrize("number", [1, 2, 3])
def test_vietnam_pork_dish_group_matches_both_travelers_clues(number):
    from csp import murdoku_lang as lang
    from csp.murdoku_expression_file import load_expression_board
    from csp.puzzlefile import load_presentation

    text = example(f"vietnam-murdoku-{number}.txt").read_text()
    board, _, clues = load_expression_board(text)
    targets = []
    for statement, person in zip(clues[:2], ["Pippo", "Swena"], strict=True):
        assert isinstance(statement.formula, lang.Negation)
        condition = statement.formula.formula
        assert isinstance(condition, lang.Atom)
        assert isinstance(condition.subject, lang.Name)
        assert condition.subject.token.text == person
        assert condition.operator.text == "dir:king"
        assert condition.measure is not None
        assert condition.measure.comparison.text == "<="
        assert condition.measure.value.text == "1"
        assert isinstance(condition.target, lang.Union)
        assert all(isinstance(item, lang.Name) for item in condition.target.items)
        targets.append(
            [
                item.token.text.removeprefix("object:")
                for item in condition.target.items
                if isinstance(item, lang.Name)
            ]
        )
    assert targets[0] == targets[1]
    assert set(targets[0]) == board.object_names - {"tunnel", "kruk"}
    say = Wording.read(text)
    dishes = [say.words[name].removeprefix("de ") for name in targets[0]]
    intro = " ".join(load_presentation(text).intro)
    assert (
        f"De varkensvleesgerechten op het bord (soms met orgaanvlees) zijn {say.join(dishes)}."
        in intro
    )


@pytest.mark.parametrize("language", ["en", "nl"])
@pytest.mark.parametrize("negated", [False, True])
def test_king_adjacency_wording_distinguishes_cells_from_people(language, negated):
    from csp.story import clue_texts

    text = (
        example("vietnam-murdoku-1.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    prefix = "not " if negated else ""
    text = text[: text.index("Clues:")] + (
        f"Clues:\n{prefix}Pippo dir:king object:buncha <= 1\n"
        f"{prefix}Pippo dir:king (people on object:buncha) <= 1\n"
        f"{prefix}Pippo dir:king object:buncha = 1\n"
    )
    cell, person, exact = clue_texts(text)
    assert ("directly next to" if language == "en" else "direct naast") in cell
    assert (("not on" if language == "en" else "niet op") in cell) == negated
    assert ("someone on" if language == "en" else "iemand op") in person
    assert ("king-step distance" if language == "en" else "koningsstapafstand") in exact
    assert ("directly next to" if language == "en" else "direct naast") not in exact
    assert ("a square of" if language == "en" else "een vakje van") in exact


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
Ada is role:guide
Clues:
count (people in area of Ada) = 1 + 1 and every ((people except Ada) in area of Ada) is role:guide
if Ada is role:guide then Ada on mark:altar
"""
    story = explain(text)

    assert "Ada shares an area with exactly one other person" in story
    assert "and that person holds the guide role" in story
    assert "(1), so **Ben has the guide role**" in story
    assert (
        "then (Ada is on a cell marked altar) (2); therefore **Ada on r1c1**"
        " is the only remaining place"
    ) in story


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
Ben is attribute:glasses
not Ada is attribute:glasses
count attribute:glasses = 1
"""
    facts = csp.story.clue_texts(text)
    assert len(facts) == 3
    assert "Ben" in facts[0] and "glasses" in facts[0]
    assert "Ada" in facts[1] and "not" in facts[1] and "glasses" in facts[1]
    assert "glasses" in facts[2] and "equal to 1" in facts[2]
    assert not re.search(r"\*\*(Ada|Ben) on r", explain(text))

    dutch_text = text.replace("Language: en", "Language: nl").replace(
        "glasses: glasses", "glasses: bril"
    )
    dutch = csp.story.clue_texts(dutch_text)
    assert "Ben" in dutch[0] and "bril" in dutch[0]
    assert "Ada" in dutch[1] and "niet" in dutch[1] and "bril" in dutch[1]
    assert "bril" in dutch[2] and "1" in dutch[2]


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
Ada in rows:1
Ben in rows:2
count people in area:alcove = 1
"""
    solutions = bruteforce.solutions(text, "murdoku", limit=5)
    assert len(solutions) == 1
    assert solutions[0]["Ada"] == murdoku.Square(0, 0)

    story = explain(text)
    assert "clue 3: exactly one person is in the alcove" in story
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
count role:bandit odd
count attribute:glasses = 1
count empty areas = 1
count empty areas in tag:inside <= 1
count (empty free cells on mark:seats) 1..2
count people in area:west = 1
count people in tag:inside odd
count people in columns:1-2 = 2
count people on mark:seats = 1
"""
    english_clues = csp.story.clue_texts(english_text)
    english = "\n".join(english_clues)
    assert len(english_clues) == 11
    assert "__global_" not in english
    assert english_clues[0] == "Exactly one person is on the bed."
    assert "Exactly two people" in english_clues[1]
    assert "row 1" in english_clues[1] and "row 3" in english_clues[1]
    assert "role bandit is odd" in english_clues[2]
    assert "attribute glasses is equal to 1" in english_clues[3]
    assert "empty areas is equal to 1" in english_clues[4]
    assert "east or garden" in english_clues[5] and "at most 1" in english_clues[5]
    assert "empty free cells" in english_clues[6] and "between 1 and 2" in english_clues[6]
    assert english_clues[7] == "Exactly one person is in the west."
    assert "east or garden" in english_clues[8] and "odd" in english_clues[8]
    assert "Exactly two people" in english_clues[9] and "columns 1-2" in english_clues[9]
    assert english_clues[10] == "Exactly one person is on the seats."

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
    dutch_clues = csp.story.clue_texts(dutch_text)
    dutch = "\n".join(dutch_clues)
    assert len(dutch_clues) == 11
    assert "__global_" not in dutch
    assert "Precies één persoon staat op het bed." in dutch
    assert "Precies twee mensen" in dutch
    assert "bandiet" in dutch_clues[2] and "oneven" in dutch_clues[2]
    assert "bril" in dutch_clues[3] and "1" in dutch_clues[3]
    assert "lege gebieden" in dutch_clues[4]
    assert "het oosten of de tuin" in dutch_clues[5]
    assert "lege vrije vakjes" in dutch_clues[6]
    assert "Precies één persoon" in dutch_clues[7] and "het westen" in dutch_clues[7]
    assert "het oosten of de tuin" in dutch_clues[8] and "oneven" in dutch_clues[8]
    assert "kolommen 1-2" in dutch_clues[9]
    assert "Precies één persoon" in dutch_clues[10] and "de stoelen" in dutch_clues[10]


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Exactly one person is on the squares marked quiet."),
        ("nl", "Precies één persoon staat op de vakjes met markering quiet."),
    ],
)
def test_global_count_names_marked_squares(language, expected):
    text = f"""Language: {language}
Size: 2
Regions:
a: hall
Grid:
a a
a a
People:
Ada
Ben
Marks:
quiet: r1c1 r2c2 ; alone
Clues:
count (people on mark:quiet) = 1
"""
    assert csp.story.clue_texts(text) == [expected]


def test_what_if_explains_the_alone_mark_used_in_its_contradiction():
    text = """Language: en
Size: 6
Regions:
a: Atrium
b: Tomb
c: Crypt
d: Hall
e: Workshop
Grid:
a a a b b b
a a a b b b
c c a b d d
c c c d d d
c c e e d d
e e e e d d
Marks:
quiet: r1c2 r4c6 r5c1 r6c2 r3c5 ; alone
People:
Ada
Bo
Cal
Dee
Eva
Fay
Clues:
count people on mark:quiet = 2
Eva dir:areas Fay = 0
Bo in area:Tomb
Bo dir:left Dee
Cal in area:Crypt
Eva dir:left Fay
Ada in area:Atrium
Eva dir:up Fay
"""
    explanation = explain(text)
    assert (
        "the square is marked quiet, so Dee would be alone in the Hall "
        "and its other squares would be empty, then Fay would be on r2c6, "
        "then nobody can fill row 6"
    ) in explanation
    assert "brute force" not in explanation
    dutch = explain(text.replace("Language: en", "Language: nl"))
    assert (
        "het vakje heeft markering quiet, dus Dee zou alleen zijn in de Hall "
        "en de andere vakjes daar zouden leeg zijn"
    ) in dutch


def test_what_if_explains_a_missing_companion_on_a_marked_square():
    text = """Size: 9
Regions:
a: garden
b: school
c: cafe
d: library
e: market
f: playground
w: stream
Grid:
a a a w b b b b b
a a a w b b b b b
a a a w b b b b b
c c c w w b b b b
c c c c w d d d d
c c c c w d d d d
e e e e w d d d d
e e e e w f f f f
e e e e w f f f f
Marks:
social: r1c5 r2c6 r4c2 r6c3 r9c7 ; not_alone
Objects:
sakura: blocking r1c1
backpack: blocking r3c8
cake: blocking r5c2
books: blocking r6c7
basket: blocking r8c2
slide: blocking r9c9
water: blocking r1c4 r2c4 r3c4 r4c4 r4c5 r5c5 r6c5
water: blocking r8c5 r9c5
bench: standable r1c3 r2c3
chair: standable r2c8
tatami: standable r6c1 r6c2
bridge: standable r7c4 r7c5 r7c6
carpet: standable r9c3
People:
Mametchi
Kuchipatchi
Memetchi
Lovelitchi
Tarakotchi
Masktchi
Gozarutchi
Violetchi
Akumatchi
Clues:
count people on mark:social = 1
Mametchi dir:areas Masktchi = 0
Lovelitchi on object:bench
Gozarutchi beside object:cake
Mametchi dir:up Lovelitchi
Violetchi dir:up Masktchi
Tarakotchi in area:library
Kuchipatchi on object:bridge
Tarakotchi dir:left Memetchi
not (Memetchi beside object:slide)
not (Tarakotchi beside object:books)
not (Violetchi beside object:backpack)
"""
    explanation = explain(text)
    assert "Memetchi is not beside the slide (10)." in explanation
    assert "64 squares" not in explanation
    assert (
        "then Memetchi would be on r9c7, then Akumatchi would be in the market, "
        "but a social square needs company, "
        "and nobody else can be in the playground"
    ) in explanation
    dutch = explain("Language: nl\n" + text)
    assert (
        "maar op een vakje met markering social moet iemand gezelschap hebben "
        "en verder kan niemand in de playground zijn"
    ) in dutch


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "then Ben would be on r2c2, Cal on r3c3 and Dee on r4c4"),
        ("nl", "dan zou Ben op r2k2 zitten, Cal op r3k3 en Dee op r4k4"),
    ],
)
def test_what_if_groups_hypothetical_placements(monkeypatch, language, expected):
    from csp.murdoku_expression_file import load_expression_board
    from csp.murdoku_lower import compile_statements_with_origins
    from csp.murdoku_story import _Narrator

    text = """Size: 4
Regions:
a: room
Grid:
a a a a
a a a a
a a a a
a a a a
People:
Ada
Ben
Cal
Dee
"""
    text = f"Language: {language}\n" + text
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = _Narrator(text, board, compilation, numbered=True)
    trail = tuple(
        Step(person, murdoku.Square(i, i), True, "single", "")
        for i, person in enumerate(board.people)
    )
    refutation = Step("Ada", murdoku.Square(0, 0), False, "what_if", "", trail=trail)
    inference = Inference("what_if", compilation.model, (refutation,), None)
    monkeypatch.setattr("csp.murdoku_story.essential", lambda *_args: list(range(len(trail))))
    assert expected in narrator._what_if(inference, [])


def test_tamagotchi_combines_necessary_marks_and_narrates_the_case():
    text = example("tamagotchi-murdoku-9x9.txt").read_text()
    board = load_board_layout(text)
    solutions = bruteforce.solutions(text, "murdoku", limit=2)
    assert len(solutions) == 1
    solution = solutions[0]
    assert {
        person for person in board.people if solution[person] in board.mark_cells(["social"])
    } == {"Mametchi"}

    assert len(bruteforce.solutions(text.replace("; not_alone", ""), "murdoku", limit=2)) == 2

    explanation = explain(text)
    assert "__" not in explanation
    assert "occupant count" not in explanation
    assert (
        "**Kuchipatchi cannot be on r7c5**: then Memetchi would be on r9c7, "
        "then Akumatchi would be in the market, but a social square needs company"
    ) in explanation


def test_alone_mark_excludes_squares_in_an_occupied_area():
    text = """Size: 6
Regions:
a: garden
b: school
c: square
d: library
e: arcade
Grid:
a a a b b b
a a a b b b
a a c c b b
d d c c e e
d d d e e e
d d d e e e
Marks:
quiet: r4c4 r1c3 r2c3 r5c6 r6c4 ; alone
Objects:
sakura: blocking r1c1
fountain: blocking r3c3
arcade: blocking r5c5
chair: standable r2c5
carpet: standable r5c1 r5c2
People:
Mametchi
Kuchipatchi
Memetchi
Lovelitchi
Masktchi
Akumatchi
Clues:
count people on mark:quiet = 1
Masktchi beside object:sakura
Lovelitchi dir:areas Mametchi = 0
Memetchi in corner:board
Kuchipatchi dir:left Mametchi
not (Lovelitchi beside object:chair)
not (Kuchipatchi beside object:carpet)
Mametchi dir:left Lovelitchi
"""
    explanation = explain(text)
    assert (
        "Masktchi is in the garden but cannot stand on a quiet square there. "
        "Anyone on a quiet square would be alone, so "
        "**nobody can use those squares in the garden**."
    ) in explanation
    assert len(bruteforce.solutions(text)) == 1
    assert len(bruteforce.solutions(text.replace("; alone", ""))) > 1


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            "**Ada cannot be on r1c1**: the square is marked social, so Ada would have "
            "company in the cafe, then Ben would be on r2c2, which goes against "
            "\u2018Ada and Ben are exactly one area boundary apart (1)\u2019.",
        ),
        (
            "nl",
            "**Ada kan niet op r1k1**: het vakje heeft markering social, dus Ada zou "
            "samen met iemand zijn in de cafe, dan zou Ben op r2k2 zitten, "
            "en dat strookt niet met \u2018Ada en Ben zijn precies één gebiedsgrens van elkaar "
            "verwijderd (1)\u2019.",
        ),
    ],
)
def test_hidden_mark_case_uses_its_only_possible_occupant(monkeypatch, language, expected):
    from csp.murdoku_expression_file import load_expression_board
    from csp.murdoku_lower import compile_statements_with_origins
    from csp.murdoku_story import _Narrator

    text = """Size: 3
Regions:
a: cafe
b: garden
Grid:
a a b
a a b
b b b
Marks:
social: r1c1 ; not_alone
People:
Ada
Ben
Cal
Clues:
Ada dir:areas Ben = 1
"""
    text = f"Language: {language}\n" + text
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = _Narrator(text, board, compilation, numbered=True)
    sources = murdoku.occupant_condition_sources(murdoku.mark_occupant_name(board.marks[0], "cafe"))
    constraint = next(c for c in compilation.model.constraints if c.name == sources["trigger"])
    assert constraint.reified_by is not None
    var = compilation.model.var_of(constraint.reified_by)
    value = compilation.model.value_of(constraint.reified_by)
    ada, ben = murdoku.Square(0, 0), murdoku.Square(1, 1)
    trail = (
        Step(var, value, True, "what_if", "assumed"),
        Step("Ada", ada, True, "count", "", sources=(constraint.name,)),
        Step(
            "Ben",
            ben,
            True,
            "count",
            "",
            sources=(sources["count"],),
        ),
    )
    refutation = Step(
        var, value, False, "what_if", "", sources=(compilation.origins[0].label,), trail=trail
    )
    before = {person: set(board.free) - {ada} for person in board.people}
    before["Ada"].add(ada)
    narrator.options = before
    step = Step("Ada", ada, False, "count", "", sources=(constraint.name,))
    inference = Inference("count", compilation.model, (step,), None)
    monkeypatch.setattr("csp.murdoku_story.essential", lambda *_args: [0, 1, 2])

    assert narrator._mark_case_deduction(inference, [refutation]) == expected

    replayed = _Narrator(text, board, compilation, numbered=True)
    replayed.options = {person: set(squares) for person, squares in before.items()}
    groups = [
        Episode(Inference("what_if", compilation.model, (refutation,), None)),
        Episode(inference),
    ]
    result = replayed.tell(compilation.model, groups, solved=False).markdown()
    assert expected in result
    assert "__" not in result
    assert replayed.options["Ada"] == before["Ada"] - {ada}

    unnumbered = _Narrator(text, board, compilation, numbered=False)
    unnumbered.options = {person: set(squares) for person, squares in before.items()}
    unnumbered_case = unnumbered._mark_case_deduction(inference, [refutation])
    assert unnumbered_case is not None
    distance_caption = (
        "Ada and Ben are exactly one area boundary apart"
        if language == "en"
        else "Ada en Ben zijn precies één gebiedsgrens van elkaar verwijderd"
    )
    assert distance_caption in unnumbered_case
    assert "(1)" not in unnumbered_case
    assert ("clue 1" if language == "en" else "aanwijzing 1") not in unnumbered_case

    before["Cal"].add(ada)
    assert narrator._mark_case_deduction(inference, [refutation]) is None
    before["Cal"].remove(ada)
    assert narrator._mark_case_deduction(inference, []) is None
    no_placement = dataclasses.replace(refutation, trail=trail[:1])
    assert narrator._mark_case_deduction(inference, [no_placement]) is None


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            "someone on a square marked social in the school must have company",
        ),
        (
            "nl",
            "wie op een vakje met markering social in de school staat, moet gezelschap hebben",
        ),
    ],
)
def test_mark_occupancy_count_is_explained_as_a_square_rule(language, expected):
    from csp.murdoku_expression_file import load_expression_board
    from csp.murdoku_lower import compile_statements_with_origins
    from csp.murdoku_story import _Narrator

    text = f"""Size: 2
Language: {language}
Regions:
a: school
Grid:
a a
a a
Marks:
social: r1c1 ; not_alone
People:
Ada
Ben
"""
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = _Narrator(text, board, compilation, numbered=True)
    mark = board.marks[0]
    sources = murdoku.occupant_condition_sources(murdoku.mark_occupant_name(mark, "school"))
    assert any(constraint.name == sources["count"] for constraint in compilation.model.constraints)
    for source in sources.values():
        assert narrator.source_words[source] == expected


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
Ada is role:seer
Clues:
not Ben is role:seer
"""
    story = explain(text)

    assert "Ada has the seer role" in story
    assert "**Ben does not have the seer role**" in story
    assert "seer (1)" in story
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


@pytest.mark.parametrize("holders", [1, 2])
def test_known_role_holder_keeps_explicit_exclusions_and_does_not_repeat_them(holders):
    from csp.murdoku_expression_file import load_expression_board
    from csp.murdoku_lower import compile_statements_with_origins
    from csp.murdoku_story import _Narrator

    text = f"""Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
People:
Ada
Ben
Cal
Roles:
team: {holders}
"""
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = _Narrator(text, board, compilation, numbered=True)
    narrator.told.add((board.role_variable("Ada", "team"), True))
    step = Step(board.role_variable("Ben", "team"), False, True, "single", "test")

    assert narrator.conclusion([step]) == "**Ben does not have the team role**"
    assert (step.var, False) in narrator.told
    assert narrator.conclusion([step]) is None


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
Ada is role:captain
Clues:
if Ada is role:captain then Ada on mark:altar
"""
    story = explain(text)

    assert "Ada has the captain role" in story
    assert "Ada's" not in story
    assert "If (Ada is a member of the captain)" in story
    assert (
        "then (Ada is on a cell marked altar) (1); therefore **Ada on r1c1**"
        " is the only remaining place"
    ) in story


def test_story_explains_a_reified_count_constraint():
    text = """Size: 2
Regions:
w: west
e: east
Grid:
w e
w e
People:
Ada
Ben
Roles:
guard: any
RoleEligibility:
guard: Ada
Rules:
not Ada in area:west
Clues:
(count (Ada in area:west) = 0) iff Ada is role:guard
"""
    explanation = explain(text)
    assert "Ada has the guard role" in explanation
    assert "the number of Ada that are in the west is equal to 0" in explanation
    assert "__" not in explanation
    assert "literal" not in explanation

    solutions = bruteforce.solutions(text, limit=3)
    assert len(solutions) == 2
    role = load_board_layout(text).role_variable("Ada", "guard")
    assert all(solution[role] for solution in solutions)


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
Ada on mark:quiet
not Ben in area:room
"""
    story = explain(text)

    assert "Ada on r1c1" in story
    assert "Ben on r2c2" in story
    assert "Ada is on a quiet square, so **Ada is alone in the room**" in story
    assert "__occupant_" not in story


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Ada is on a social square, so **Ada has company in the room**"),
        (
            "nl",
            "Ada staat op een vakje met markering social, dus **Ada heeft gezelschap in de room**",
        ),
    ],
)
def test_story_explains_company_when_a_marked_square_is_occupied(language, expected):
    text = f"""Language: {language}
Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Marks:
social: r1c1 ; not_alone
Clues:
Ada on mark:social
"""
    assert expected in explain(text)


def test_story_explains_a_marked_square_placed_after_a_direct_clue():
    text = """Size: 3
Regions:
a: room
b: hall
c: garden
Grid:
a b b
a b b
c c c
People:
Ada
Ben
Cal
Marks:
quiet: r2c1 r3c2 ; alone
bench: r1c2
Clues:
Ada in area:room
Ben on mark:bench
count people on mark:quiet = 1
"""
    explanation = explain(text)
    assert "Ada is in the room (1)." in explanation
    assert "Ada is in the room (1): **in the room**" not in explanation
    expected = (
        "Ben takes row 1; therefore **Ada on r2c1** is the only remaining "
        "place. Ada is on a quiet square, so **Ada is alone in the room**"
    )
    assert expected in explanation
    assert (
        "That is the only occupied quiet square, so **all other quiet squares are empty**"
        in explanation
    )
    dutch = explain("Language: nl\n" + text)
    assert (
        "Dat is het enige bezette vakje met markering quiet, "
        "dus **alle andere vakjes met die markering zijn leeg**"
    ) in dutch
    no_limit = explain(
        text.replace("count people on mark:quiet = 1", "count people on mark:quiet >= 1")
    )
    assert "all other quiet squares are empty" not in no_limit
    excluded = explain(text.replace("Ada in area:room", "not Ada in (area:hall, garden)"))
    assert "It is not true that (Ada is in the hall or Ada is in the garden) (1)" in excluded


def test_direct_area_clue_does_not_repeat_the_area_when_it_fixes_a_square():
    explanation = explain(example("murdoku_2_point_objects.txt").read_text())
    assert "Cal is in the greenhouse (4): **Cal on r3c5**" in explanation
    assert "the in greenhouse, (4):, **in, the, greenhouse**" not in explanation


def test_story_explains_complementary_reified_counts():
    text = """Size: 2
Regions:
w: west
e: east
Grid:
w e
w e
People:
Ada
Ben
Roles:
guard: any
RoleEligibility:
guard: Ada
Rules:
not Ada is role:guard
Ada in rows:2
Clues:
(count (Ada in area:west) = 0) iff Ada is role:guard
"""
    explanation = explain(text)
    assert "**Ada on r2c1**" in explanation
    assert "the number of Ada that are in the west is equal to 0" in explanation
    assert "__" not in explanation
    assert "literal" not in explanation

    (solution,) = bruteforce.solutions(text, limit=2)
    assert solution["Ada"] == murdoku.Square(1, 0)
    assert solution[load_board_layout(text).role_variable("Ada", "guard")] is False


@pytest.mark.parametrize(
    "name",
    ["murdoku_1_first_case.txt", "murdoku_3_house.txt", "murdoku_sparse_mystery.txt"],
)
def test_english_story_places_everyone_right_and_once(name):
    text = (example(name)).read_text()
    (solution,) = bruteforce.solutions(text)
    story = explain(text)
    stated = re.findall(r"\*\*(\w+) on r(\d+)c(\d+)\*\*", story)
    assert {who: (int(r) - 1, int(c) - 1) for who, r, c in stated} == {
        who: (sq.row, sq.col) for who, sq in solution.items()
    }
    assert len(stated) == len(solution), "each person is placed in bold exactly once"
    assert all(
        paragraph.startswith("- ") and "**" in paragraph for paragraph in story.split("\n\n")
    )


def test_murder_hotel_story_handles_role_rule_covering_rows():
    story = explain(example("murder-hotel-1.txt").read_text())
    assert "**Donatella is the murderer**" in story
    assert "murderer holder" not in story


def test_area_tag_note_uses_singular_grammar_for_one_region():
    notes = board_notes(example("murder-hotel-1.txt").read_text())

    assert "The crime scene is the west guest room." in notes


def test_area_tag_note_keeps_the_article_and_case_of_an_english_room_phrase():
    notes = board_notes(example("halloween-museum-2.txt").read_text())
    assert "The crime scene is the armoury." in notes
    text = (
        example("halloween-museum-2.txt")
        .read_text()
        .replace("crime_scene: armoury", "crime_scene: El_Greco_room")
    )
    assert "The crime scene is the El Greco room." in board_notes(text)


def test_murder_hotel_role_clue_reveals_identity_after_the_last_placement():
    story = explain(example("murder-hotel-3.txt").read_text())
    reveal = "Luca is above the murderer (14), so **Marcella has the murderer role**."

    assert reveal in story
    assert story.index("Marcella on r10c5") < story.index(reveal)
    assert "does not have the murderer role" not in story


def test_opening_narrows_clue_by_clue_and_places_whoever_it_pins_down():
    story = explain((example("murdoku_3_house.txt")).read_text())
    opening = story.split("\n\n")[0]
    assert "Ben is on the carpet (4): **in the hall**." in opening
    assert "Ben is not beside the lamp (6): **Ben on r3c4**." in opening


def test_counting_clue_is_worded_and_known_placements_are_not_bold_again():
    story = explain((example("murdoku_3_house.txt")).read_text())
    assert (
        "Either Ada is in the study, or Ben is in the hall, but not both (1), "
        "so **Ada is not in the study**"
    ) in story
    assert story.index("**Ben on r3c4**") < story.index("**Ada is not in the study**")
    assert story.count("**Ben on r3c4**") == 1
    assert "**Ben is on r3c4**" not in story


def test_chains_are_told_as_if_then_with_the_reason_for_each_link():
    text = (example("prrrdoku2.txt")).read_text()
    assert "Anna dir:up Mao = 5\n" in text
    assert "Jos dir:manhattan Mao >= 13\n" in text
    original_clues = text.replace("Anna dir:up Mao = 5\n", "Jos in area:keukenwinkel\n")
    story = explain(original_clues.replace("Jos dir:manhattan Mao >= 13\n", ""))
    assert "Als Otto niet op r6k5 zit" in story
    assert (
        "waren alleen Otto op r6k5 of Otto op r7k6 mogelijk; "
        "nu Otto op r6k5 afvalt, geldt Otto op r7k6"
    ) in story
    assert "dan zit Luna niet op r7k4 (rij 7)" in story
    assert "Otto zit op r6k5 of Luna zit op r8k3." in story
    assert "Tjitske op r6k3 valt af: Otto op r6k5 botst ermee" in story


def test_story_cites_clue_numbers():
    story = explain((example("prrrdoku1.txt")).read_text())
    assert "Otto staat precies één rij boven Tjitske (5)" in story
    assert "Jos staat links van Otto (8)" in story


def test_story_in_english():
    text = example("prrrdoku1.txt").read_text().replace("Language: nl", "Language: en")
    story = explain(text)
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
    assert cli.main([str(example("prrrdoku1.txt")), "--explain"]) == 0
    assert "**Tim op r1k1**" in capsys.readouterr().out
    assert cli.main([str(example("sudoku_5_9x9.txt")), "--explain"]) == 0
    assert "**Singles.**" in capsys.readouterr().out


def test_board_rules_are_what_the_model_is_built_from():
    from csp.murdoku_lower import compile_statements

    board = load_board_layout(example("prrrdoku1.txt").read_text())
    model = compile_statements(board, [])
    names = {rule.name for rule in murdoku.board_rules(board)}
    assert names == {c.name for c in model.constraints}


def test_story_explains_a_different_regions_role_step():
    story = explain((example("menu-murdoku-1.txt")).read_text())

    assert "zijn allebei zetmeel, en er staat nooit meer dan één zetmeel op dezelfde dag" in story


def test_quantified_clue_is_only_said_with_its_upshot():
    """A quantified step that only narrows its hidden witnesses says nothing."""
    story = explain(example("wie-doet-het-met-wie-5.txt").read_text())
    sentences = re.split(r"(?<=\.) ", story)
    bare = [s for s in sentences if "iemand op een badjas" in s and ", dus " not in s]
    assert not bare, bare


def test_role_rules_are_told_without_engine_names():
    story = explain(example("murdoku_orient_express.txt").read_text())
    for leak in ("__", "role and area", "occupant count", "has role", "cardinality"):
        assert leak not in story
    reveal = next(
        paragraph
        for paragraph in story.split("\n\n")
        if "**Svetlana is de moordenaar**" in paragraph
    )
    assert "Regel 2: de moordenaar is op de plaats delict" in reveal
    assert story.count("**Svetlana is de moordenaar**") == 1
    assert "**Svetlana zit op de plaats delict**" in story or "**Svetlana op r3k8**" in story


@pytest.mark.parametrize("name", ["murdoku_orient_express_2.txt", "murdoku_orient_express_3.txt"])
def test_role_literals_are_told_as_role_sentences(name):
    story = explain(example(name).read_text())
    for leak in ("has role", "letterlijke keuze", "=True", "=False"):
        assert leak not in story


ON_OR_NEXT_TO = """Size: 4
Language: {lang}
Regions:
a: Room #FFFFFF
Grid:
a a a a
a a a a
a a a a
a a a a
Objects:
bench: standable r1c1 r1c2
chair: standable r3c3
stool: standable r4c1
stool: standable r4c2
table: blocking r2c4 r3c4
People:
Ann
Bob
Cy
Di
Clues:
not Ann beside object:bench
Bob beside object:chair
not Cy beside object:table
Di beside object:stool
"""


REGION_TARGETS = """Size: 3
Language: {lang}
Regions:
a: west
b: middle
c: east
Grid:
a a b
a b b
c c c
People:
Ann
Bea
Cy
Attributes:
trained: Bea
Clues:
Ann dir:areas attribute:trained = 0
Cy dir:areas attribute:trained >= 1
Ann dir:areas area:east = 1
Cy dir:areas area:west >= 2
"""


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            [
                "Ann is in the same area as people with attribute trained "
                "(distinct from the subject).",
                "Cy is at an area distance from people with attribute trained "
                "(distinct from the subject) (distance at least 1).",
                "Ann is at an area distance from the east "
                "(distinct from the subject) (distance equal to 1).",
                "Cy is at an area distance from the west "
                "(distinct from the subject) (distance at least 2).",
            ],
        ),
        (
            "nl",
            [
                "Ann staat in hetzelfde gebied als personen met eigenschap trained "
                "(verschillend van het onderwerp).",
                "Cy staat op een gebiedsafstand van personen met eigenschap trained "
                "(verschillend van het onderwerp) (afstand minstens 1).",
                "Ann staat op een gebiedsafstand van de east "
                "(verschillend van het onderwerp) (afstand gelijk aan 1).",
                "Cy staat op een gebiedsafstand van de west "
                "(verschillend van het onderwerp) (afstand minstens 2).",
            ],
        ),
    ],
)
def test_region_relation_with_a_target_names_the_target(language, expected):
    text = REGION_TARGETS.format(lang=language)
    assert csp.story.clue_texts(text) == expected


def test_beside_object_clues_use_spatial_adjacency():
    board = load_board_layout(ON_OR_NEXT_TO.format(lang="en"))
    assert murdoku.next_to_covers_own_squares(board, "bench")
    assert murdoku.next_to_covers_own_squares(board, "stool"), "two touching stools"
    assert not murdoku.next_to_covers_own_squares(board, "chair"), "one square"
    assert not murdoku.next_to_covers_own_squares(board, "table"), "blocking"
    text = ON_OR_NEXT_TO.format(lang="en")
    assert csp.story.clue_texts(text) == [
        "Ann is not beside the bench.",
        "Bob is beside the chair.",
        "Cy is not beside the table.",
        "Di is beside a stool.",
    ]
    text = ON_OR_NEXT_TO.format(lang="nl")
    dutch = csp.story.clue_texts(text)
    assert dutch[0] == "Ann staat niet naast de bench."
    assert dutch[1] == "Bob staat naast de chair."


def test_merged_predicates_keep_distinct_beside_and_on_meanings():
    text = ON_OR_NEXT_TO.format(lang="nl").replace(
        "Bob beside object:chair", "not Ann on object:chair"
    )
    paragraphs = csp.story.clue_paragraphs(text)
    assert "Ann staat niet naast de bench en zit niet op de chair." in paragraphs


def test_beside_and_not_on_a_multi_square_object_keep_both_meanings():
    text = ON_OR_NEXT_TO.replace(
        "not Ann beside object:bench",
        "Ann beside object:bench\nnot Ann on object:bench",
    )
    english = text.format(lang="en")
    assert "Ann is beside the bench and is not on the bench." in csp.story.clue_paragraphs(english)
    dutch = text.format(lang="nl")
    assert "Ann staat naast de bench en zit niet op de bench." in csp.story.clue_paragraphs(dutch)

    override = csp.story.clue_paragraphs(english, {1: "Ann is on or beside the bench."})
    assert "Ann is not on the bench. Ann is on or beside the bench." in override


def test_beside_and_not_on_a_single_square_object_keep_both_meanings():
    text = ON_OR_NEXT_TO.replace(
        "Bob beside object:chair",
        "Bob beside object:chair\nnot Bob on object:chair",
    )
    bob = next(
        paragraph
        for paragraph in csp.story.clue_paragraphs(text.format(lang="en"))
        if paragraph.startswith("Bob ")
    )
    assert bob == "Bob is beside the chair and is not on the chair."


@pytest.mark.parametrize("language", ["en", "nl"])
def test_figure_clues_use_semantics_even_when_author_wording_names_someone_else(language):
    from csp.story import figure_clues

    text = ON_OR_NEXT_TO.format(lang=language).replace(
        "not Ann beside object:bench",
        "not Ann beside object:bench | Bob saw Ann away from the bench.",
    )
    result = figure_clues(text)
    assert [figure.person for figure in result.figures] == ["Ann", "Bob", "Cy", "Di"]
    assert result.figures[0].clues[0].text == "Bob saw Ann away from the bench."
    assert result.figures[0].clues[0].sources == (1,)
    assert result.figures[0].clues[0].id == "clue:1"
    assert result.figures[1].clues[0].sources == (2,)


def test_figure_clues_keep_combined_sources_global_clues_and_clueless_figures():
    from csp.story import figure_clues

    text = (
        ON_OR_NEXT_TO.format(lang="en")
        .replace(
            "not Ann beside object:bench",
            "Ann beside object:bench\nnot Ann on object:bench",
        )
        .replace("Di beside object:stool", "count (people on object:stool) = 1\nBob dir:up Cy")
    )
    result = figure_clues(text)
    assert result.figures[0].clues[0].sources == (1, 2)
    assert result.figures[0].clues[0].text == "Ann is beside the bench and is not on the bench."
    assert result.figures[-1].person == "Di"
    assert result.figures[-1].clues == ()
    assert result.other[0].sources == (5,)
    assert result.figures[1].clues[0].sources == (3, 6)
    paragraphs = [clue for figure in result.figures for clue in figure.clues] + list(result.other)
    assert sorted(n for clue in paragraphs for n in clue.sources) == list(range(1, 7))


def test_figure_clues_attach_a_compound_clue_naming_one_person():
    from csp.story import figure_clues

    text = ON_OR_NEXT_TO.format(lang="en").replace(
        "Di beside object:stool",
        "count (people in area of Di) = 1 + 1",
    )
    result = figure_clues(text)
    di = next(figure for figure in result.figures if figure.person == "Di")
    assert [clue.sources for clue in di.clues] == [(4,)]
    assert result.other == ()


def test_figure_clues_attach_a_compound_direction_clue_naming_the_target():
    from csp.story import figure_clues

    text = ON_OR_NEXT_TO.format(lang="en").replace(
        "Di beside object:stool",
        "some (people beside object:bench) dir:up Di = 1",
    )
    result = figure_clues(text)
    di = next(figure for figure in result.figures if figure.person == "Di")
    assert [clue.sources for clue in di.clues] == [(4,)]
    assert result.other == ()


def test_count_rules_and_author_garment_clues_use_expression_wording():
    from csp.story import board_notes, clue_paragraphs, global_count_texts

    text = example("wie-doet-het-met-wie-3.txt").read_text()
    counts = global_count_texts(text)
    assert len(counts) == 3
    assert counts[-2:] == [
        "Precies twee mensen staan op een badjas.",
        "Precies één persoon staat op een paar sloffen.",
    ]
    assert board_notes(text)[-2:] == [
        "Precies twee mensen staan op een badjas.",
        "Precies één persoon staat op een paar sloffen.",
    ]
    story = explain(text)
    assert "Marloes heeft alleen een badjas aan (2): **op een badjas**." in story
    assert "precies twee mensen staan op een badjas" in story.casefold()
    assert (
        "Een van de gasten met een badjas staat precies één rij boven de gast met sloffen."
        in clue_paragraphs(text)
    )


def test_a_rule_the_intro_already_says_is_listed_once():
    """Issue #152: the hotel's intro repeated the wording of Wouter's own rule."""
    from csp.story import murdoku_rules

    wouter = (
        "Wouter wordt als laatste geplaatst en is alleen in een gebied met degene "
        "met wie hij het doet: iemand in een badjas."
    )
    rules = murdoku_rules(example("wie-doet-het-met-wie-5.txt").read_text())

    assert sum(wouter in rule for rule in rules) == 1
    # The intro says it first, so that copy stays; the remaining rules keep their order.
    assert wouter in rules[0]
    entries = csp.story.figure_clues(example("wie-doet-het-met-wie-5.txt").read_text())
    assert [clue.text for clue in entries.other if clue.rule_sources] == [
        "Precies twee mensen staan op een badjas.",
        "Precies één persoon staat op een paar sloffen.",
        "Precies één persoon staat op een bril.",
    ]
    assert rules[-1].startswith("Alleen de expliciete regels en aanwijzingen")
    assert len(rules) == len(dict.fromkeys(rules))


def test_intro_sentences_keep_their_own_order_when_none_repeat_a_rule():
    from csp.story import murdoku_rules

    rules = murdoku_rules(example("wie-doet-het-met-wie-4.txt").read_text())

    assert rules[0].startswith("Zes mensen logeren een weekend in een huis.")
    assert (
        "Wouter wordt als laatste geplaatst en is alleen in een kamer met degene "
        "met wie hij het doet." in rules[0]
    )
    entries = csp.story.figure_clues(example("wie-doet-het-met-wie-4.txt").read_text())
    assert any("Wouter" in clue.text for figure in entries.figures for clue in figure.clues)
    assert [clue.text for clue in entries.other if clue.rule_sources] == [
        "Precies twee mensen staan op een badjas.",
        "Precies één persoon staat op een paar sloffen.",
        "Precies één persoon staat op een bril.",
    ]
    assert len(rules) == len(dict.fromkeys(rules))


def test_reference_rules_leave_the_intro_to_the_block_shown_above():
    for name in ("wie-doet-het-met-wie-5.txt", "vietnam-murdoku-3.txt"):
        text = example(name).read_text()
        intro = load_presentation(text).intro
        assert intro, name
        reference = murdoku_reference_rules(text)
        # Nothing the intro already tells the player is repeated in the reference.
        assert all(paragraph not in reference for paragraph in intro), name
        # The rest keeps its place and order, so the booklet and the rules panel agree.
        assert reference == murdoku_rules(text)[len(intro) :], name
        assert reference, name


def test_a_puzzle_without_an_intro_keeps_its_default_rules():
    text = example("wie-doet-het-met-wie-5.txt").read_text().split("Intro:")[0]
    assert load_presentation(text).intro == []
    assert murdoku_reference_rules(text) == murdoku_rules(text)
    assert murdoku_reference_rules(text)


def test_every_example_has_player_rules_without_duplicates():
    for path in played_examples():
        text = path.read_text()
        kind = detect(text)
        rules = murdoku_rules(text) if kind == "murdoku" else family_rules(text, kind)
        assert rules, path.name
        assert len(rules) == len(dict.fromkeys(rules)), path.name


SUDOKU_VARIANT_MARKERS = (
    "Boxes:",
    "Extra:",
    "Kropki:",
    "Consecutive:",
    "Thermometers:",
    "AntiKnight:",
    "AntiKing:",
    "Parity:",
    "SandwichRows:",
    "SandwichColumns:",
    "SkyscraperTop:",
    "SkyscraperBottom:",
    "SkyscraperLeft:",
    "SkyscraperRight:",
    "Cages:",
    "Arrow:",
)
SUDOKU_VARIANT_FAMILIES = {
    "killer",
    "arrow",
    "evenodd",
    "sandwich",
    "skyscrapersudoku",
}


def test_every_sudoku_variant_states_its_extra_rule():
    from csp.puzzlefile import display_family

    for path in played_examples():
        text = path.read_text()
        if detect(text) != "sudoku":
            continue
        family = display_family(text, "sudoku")
        if family not in SUDOKU_VARIANT_FAMILIES and not any(
            marker in text for marker in SUDOKU_VARIANT_MARKERS
        ):
            continue
        assert len(family_rules(text, "sudoku")) > 1, path.name


def test_murdoku_key_lists_only_board_symbols():
    key = murdoku_key(example("murdoku_composition.txt").read_text())
    assert [name for name, _ in key] == ["Door", "Point", "Window"]


def test_murdoku_key_uses_the_words_aliases():
    key = murdoku_key(example("murdoku_2_point_objects.txt").read_text())
    assert any("top edge" in text for _, text in key)


def test_only_object_counts_get_a_dashed_scope_ring():
    from csp.murdoku_expression_file import load_expression_board
    from csp.murdoku_lower import object_count_scope

    board, rules, clues = load_expression_board(example("murdoku_composition.txt").read_text())
    assert object_count_scope(board, [*rules, *clues]) == board.squares_of(["bench"])


@pytest.mark.parametrize(
    ("clue", "note"),
    [
        (
            "Ada beside object:tree",
            "Beside an object in a square means sharing a side with one of its squares in the "
            "same area; diagonals do not count.",
        ),
        (
            "not (Ada beside object:tree)",
            "Beside an object in a square means sharing a side with one of its squares in the "
            "same area; diagonals do not count.",
        ),
        (
            "if Ada is role:navigator then Ada beside object:tree",
            "Beside an object in a square means sharing a side with one of its squares in the "
            "same area; diagonals do not count.",
        ),
        (
            "exactly 1 of (Ada beside object:tree; Ben in area:Bravo)",
            "Beside an object in a square means sharing a side with one of its squares in the "
            "same area; diagonals do not count.",
        ),
        (
            "Ada on point_object:fountain",
            "On a point object means standing on any square it touches, even in another area.",
        ),
        (
            "Ada on edge_item:archway",
            "On a door means standing on either square it touches, even across an area boundary.",
        ),
        ("Ada on edge_item:window", "On a window means standing on its one inside square."),
        (
            "Ada touches mark:meadow",
            "A square touches a marked square when they share a side, even across an area "
            "boundary; diagonals do not count.",
        ),
    ],
)
def test_player_rules_explain_location_predicate_targets(clue, note):
    text = f"""Size: 2
Regions:
a: Alpha
b: Bravo
Grid:
a b
a b
Objects:
tree: blocking r2c1
EdgeItems:
archway: door r1c1 r1c2
window: window r2c2
PointObjects:
fountain: r1.5c1.5
Marks:
meadow: r2c1
People:
Ada
Ben
Roles:
navigator: 1
Clues:
{clue}
"""
    rules = murdoku_rules(text)
    notes = {
        csp.story.phrase(text, key)
        for key in (
            "doc.clue_beside_object",
            "doc.clue_on_door",
            "doc.clue_on_point",
            "doc.clue_on_window",
            "doc.clue_touches_mark",
        )
    }
    assert [rule for rule in rules if rule in notes] == [note]


@pytest.mark.parametrize(
    ("key", "clue"),
    [
        ("doc.clue_beside_object", "Ada beside object:tree"),
        ("doc.clue_touches_mark", "Ada touches mark:meadow"),
        ("doc.clue_on_door", "Ada on edge_item:archway"),
        ("doc.clue_on_point", "Ada on point_object:fountain"),
        ("doc.clue_on_window", "Ada on edge_item:window"),
    ],
)
def test_predicate_specific_wording_overrides_are_used(key, clue):
    text = f"""Size: 2
Regions:
a: Alpha
b: Bravo
Grid:
a b
a b
Objects:
tree: blocking r2c1
EdgeItems:
archway: door r1c1 r1c2
window: window r2c2
PointObjects:
fountain: r1.5c1.5
Marks:
meadow: r2c1
People:
Ada
Ben
Words:
{key}: Custom semantic note.
Clues:
{clue}
"""
    assert murdoku_rules(text).count("Custom semantic note.") == 1


@pytest.mark.parametrize(
    ("language", "intro"),
    [
        (
            "en",
            "A square can be on a point in another area. "
            "The distance is a mystery; take your first steps into the garden.",
        ),
        (
            "nl",
            "Een vakje kan op een punt in een ander gebied liggen. "
            "De afstand is een raadsel; zet je eerste stap in de tuin.",
        ),
    ],
)
def test_intro_keywords_do_not_hide_door_or_distance_rules(language, intro):
    text = f"""Size: 2
Language: {language}
Intro: {intro}
Regions:
a: Alpha
b: Bravo
Grid:
a b
a b
EdgeItems:
gate: door r1c1 r1c2
PointObjects:
fountain: r1.5c1.5
People:
Ada
Ben
Clues:
Ada on point_object:fountain
Ben on edge_item:gate
Ada dir:manhattan Ben <= 1
"""
    notes = [
        csp.story.phrase(text, "doc.clue_on_door"),
        csp.story.phrase(text, "doc.clue_on_point"),
        csp.story.phrase(text, "doc.clue_distance"),
    ]
    rules = murdoku_rules(text)
    assert all(note in rules for note in notes)

    text = text.replace(intro, " ".join(notes))
    rules = murdoku_rules(text)
    assert all(sum(note in rule for rule in rules) == 1 for note in notes)


def test_point_intro_does_not_repeat_the_note_or_mention_a_door():
    text = example("murdoku_2_point_objects.txt").read_text()
    rules = murdoku_rules(text)
    point = csp.story.phrase(text, "doc.clue_on_point")
    assert sum(point in rule for rule in rules) == 1
    assert csp.story.phrase(text, "doc.clue_on_door") not in rules

    text = text.replace("PointObjects:", "EdgeItems:\ngate: door r1c3 r1c4\nPointObjects:")
    text = text.replace("Clues:\n", "Clues:\nAda on edge_item:gate\n")
    rules = murdoku_rules(text)
    assert sum(point in rule for rule in rules) == 1
    assert csp.story.phrase(text, "doc.clue_on_door") in rules


@pytest.mark.parametrize(
    ("legacy_key", "replacement"),
    [
        ("doc.clue_next_to_object", "doc.clue_beside_object"),
        (
            "doc.clue_next_to_border",
            "doc.clue_on_door or doc.clue_on_point",
        ),
        ("doc.clue_next_to_door", "doc.clue_on_door"),
        ("doc.clue_next_to_point", "doc.clue_on_point"),
        ("doc.clue_next_to_window", "doc.clue_on_window"),
        ("doc.clue_next_to_mark", "doc.clue_touches_mark"),
        ("doc.clue_next_to_unknown", "doc.clue_on_<target>"),
        (
            "doc.clue_at",
            "doc.clue_on_door or doc.clue_on_window",
        ),
        ("clue.alone_with", "clue.with_same_area"),
        ("clue.alone_with_anyone", "clue.with_same_area_anyone"),
        ("clue.alone_with_n", "clue.with_same_area_n"),
        (
            "clue.alone_with_anyone_n",
            "clue.with_same_area_anyone_n",
        ),
        ("role_occupant.alone", "rule.role_occupancy.alone"),
        ("role_occupant.not_alone", "rule.role_occupancy.not_alone"),
    ],
)
def test_legacy_phrasebook_word_keys_are_rejected(legacy_key, replacement):
    text = (
        example("murdoku_2_point_objects.txt")
        .read_text()
        .replace("Words:\n", f"Words:\n{legacy_key}: Custom wording.\n")
    )
    with pytest.raises(ValueError) as error:
        murdoku_rules(text)
    assert legacy_key in str(error.value)
    assert replacement in str(error.value)


def test_dutch_player_rules_explain_object_adjacency():
    rules = murdoku_rules(example("japan-3-samen-in-japan.txt").read_text())
    assert (
        "Naast een voorwerp in een vakje betekent een zijde delen met een vakje van het "
        "voorwerp in hetzelfde gebied; schuin telt niet."
    ) in rules


@pytest.mark.parametrize("clue", ["Ada dir:areas Ben = 1", "Ada dir:areas Ben >= 2"])
@pytest.mark.parametrize(
    ("language", "note"),
    [
        ("en", "Areas are neighbors when they share a side, not just a corner."),
        ("nl", "Gebieden grenzen aan elkaar als ze een zijde delen, niet alleen een hoek."),
    ],
)
def test_player_rules_explain_area_border_distance(clue, language, note):
    text = f"""Size: 2
Language: {language}
Regions:
a: Alpha
b: Bravo
Grid:
a b
a b
People:
Ada
Ben
Clues:
{clue}
"""
    assert murdoku_rules(text).count(note) == 1
    assert note not in murdoku_rules(text.replace(clue, "Ada dir:manhattan Ben >= 1"))


def test_wrapped_intro_lines_stay_one_rule():
    rules = murdoku_rules(example("japan-3-samen-in-japan.txt").read_text())
    assert rules[0].startswith("Zes reizigers zijn neergestreken")
    assert rules[0].endswith("per kolom.")


def test_inline_intro_is_preserved_in_player_rules():
    from csp.puzzlefile import load_presentation

    text = """#note:
Size: 1
Intro: Ada searches the room.
Regions:
a: Room
Grid:
a
People:
Ada
"""
    assert load_presentation(text).intro == ["Ada searches the room."]
    assert murdoku_rules(text)[0] == "Ada searches the room."

    replaced = text.replace(
        "Regions:\n",
        "Intro:\nThe first line wraps\n#note:\nonto this one.\n\nAnother paragraph.\nRegions:\n",
    )
    assert load_presentation(replaced).intro == [
        "The first line wraps onto this one.",
        "Another paragraph.",
    ]
