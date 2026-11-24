"""The generic narrator tells any family's solve from the model alone."""

from pathlib import Path

import pytest

from csp import binairo, cli, generic_story, puzzlefile
from csp.core import Solver, Step
from csp.story import Wording
from tests.examples import example

EXAMPLES = sorted(path for path in Path(__file__).parent.parent.joinpath("examples").rglob("*.txt"))


def told(name: str, language: str = "en") -> generic_story.Explanation:
    text = example(name).read_text()
    if language != "en":
        text = f"Language: {language}\n{text}"
    kind = puzzlefile.detect(text)
    puzzle = cli.load(text, kind)
    start = puzzle.model.clone(keep_log=True)
    fired: list = []
    Solver(puzzle.model).solve(on_step=lambda rule, steps: fired.append((rule, steps)))
    return generic_story.explain(text, start, fired, kind=kind)


def test_compress_names_runs_along_the_shorter_direction():
    say, run = Wording("en"), "\u2013"
    tell = generic_story.compress
    assert tell(["r1c1", "r2c1", "r3c1", "r5c5"], say) == f"r1c1{run}r3c1 and r5c5"
    assert tell(["r1c1", "r1c2", "r1c3", "r2c2"], say) == f"r1c1{run}r1c3 and r2c2"
    assert tell(["r1c1", "r1c2", "r3c3"], say) == "r1c1, r1c2 and r3c3"
    assert tell(["Ada", "Ben", "Cal"], say) == "Ada, Ben and Cal"


def test_futoshiki_is_told_by_its_rules_chains_and_covers():
    story = told("futoshiki_3_5x5.txt")
    text = story.markdown()
    assert story.complete
    # Singles cite the board constraint that left them, in deduction order.
    assert "**r4c4 = 5** by *5 once in col 4*" in text
    assert (
        "**r5c5 = 5**, the only option left in *5 once in row 5* after the earlier exclusions, "
        "once r2c3 = 5 rules out r5c3 = 5 under *each number once per column*"
    ) in text
    assert text.index("**r5c5 = 5**") < text.index("**r5c1 = 3**")
    assert (
        "**Chain.** If r5c4 ≠ 4, then under *4 once in col 4*, r2c4 = 4 or r5c4 = 4 "
        "were the only options; with r5c4 = 4 ruled out, r2c4 = 4"
    ) in text
    assert (
        "Only r5c3 = 4 or r5c4 = 4 remain under *4 once in row 5*. r5c3 = 2 is ruled out:"
    ) in text
    assert text.count("If r1c4 \u2260 3") == 1
    assert "Continuing the same chain" in text
    assert "r5c4 = 3 is ruled out" in text and "r2c4 = 3 is ruled out" in text
    assert "**Combined rules.**" in text
    assert "Stalled" not in text
    # Every placement is named; none is left to "follow the same way".
    assert "follow the same way" not in text


def test_each_single_cites_its_own_reason():
    text = told("akari_1_6x6.txt").markdown()
    assert "**r2c4 = no bulb** by *0 bulbs around wall r2c5*" in text
    assert (
        "**r1c3\u2013r3c3, r4c4 and r4c5 = no bulb**, because r4c3 = bulb "
        "rules out r1c3\u2013r3c3, r4c4 and r4c5 = bulb"
    ) in text
    assert (
        "**r1c4 = bulb**: r2c2\u2013r2c4 = no bulb; with *cell r2c4 is lit*, "
        "that leaves no alternative"
    ) in text
    assert (
        "**r6c2 = no bulb**: r6c4 = bulb; with *1 bulb around wall r6c3*, "
        "that leaves no alternative"
    ) in text
    assert (
        "**r4c1 = no bulb**: r3c2, r4c3 and r5c2 = bulb; with *3 bulbs around wall r4c2*, "
        "that leaves no alternative"
    ) in text
    assert "**r5c2 = bulb**, using the same count from *2 bulbs around wall r5c3*" in text
    assert "With r3c6 = bulb already counted" in text
    assert "r5c6 = bulb and r4c5 = bulb" in text
    assert "*1 bulb around wall r5c5*" in text
    assert "every open cell is lit*, one option" not in text


@pytest.mark.parametrize(
    ("language", "phrase"),
    [
        ("en", "*the requirement to light r2c4*"),
        ("nl", "*de regel dat r2c4 verlicht moet zijn*"),
    ],
)
def test_akari_lighting_sources_read_naturally(language, phrase):
    text = f"Language: {language}\n" + example("akari_1_6x6.txt").read_text()
    puzzle = cli.load(text, "akari")
    assert phrase in cli.pattern_story("akari", text, puzzle.model).markdown()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "battleships_1_6x6_fleet.txt",
            "**r2c4\u2013r2c6 = ship**, using the same count from *5 occupied cells in row 2*",
        ),
        (
            "thermometers_1_4x4.txt",
            "**r2c1\u2013r4c1 = empty**: r1c1 = mercury; with *1 filled in column 1*, "
            "that leaves no alternative",
        ),
    ],
)
def test_boolean_singles_say_the_alternative_was_ruled_out(name, expected):
    assert expected in told(name).markdown()


def test_count_cover_names_already_counted_values():
    text = told("minesweeper_2_5x5.txt").markdown()
    assert (
        "With r4c1 = mine and r4c4 = mine already counted, "
        "under *1 mine near r1c5*, one of r2c4 = mine or r2c5 = mine must hold "
        "and under *1 mine near r2c1*, one of r2c2 = mine or r3c1 = mine must hold. "
        "These separate options fill the remaining capacity of *4 mines total*, "
        "so **r1c3 = safe**"
    ) in text


def test_boolean_and_count_cover_premises_are_in_dutch():
    text = told("minesweeper_2_5x5.txt", "nl").markdown()
    assert (
        "r3c3 = veilig**: r4c4 = mijn; met *1 mine near r4c3* "
        "blijft er geen andere mogelijkheid over"
    ) in text
    assert (
        "Met r4c1 = mijn en r4c4 = mijn al meegeteld, onder *1 mine near r1c5* moet "
        "r2c4 = mijn of r2c5 = mijn gelden en onder *1 mine near r2c1* moet "
        "r2c2 = mijn of r3c1 = mijn gelden. Deze afzonderlijke mogelijkheden vullen "
        "de resterende ruimte van *4 mines total*"
    ) in text


@pytest.mark.parametrize(
    ("name", "singular", "plural"),
    [
        ("battleships_1_6x6_fleet.txt", "1 occupied cell", "0 occupied cells"),
        ("minesweeper_2_5x5.txt", "1 mine near", "2 mines near"),
        ("tents_3_4x4.txt", "1 tent in", "tents do not touch"),
        ("undead_1_4x4.txt", "1 vampire in all", "3 zombies in all"),
    ],
)
def test_count_clue_names_use_singular_and_plural(name, singular, plural):
    text = told(name).markdown()
    assert singular in text
    assert plural in text


def test_singles_explain_eliminations_from_givens_and_earlier_placements():
    text = told("suguru_1_4x4.txt").markdown()
    assert (
        "**r2c2 = 4**, the only option left once r3c3 = 1 rules out 1 "
        "under *no equal numbers in touching cells* and r1c2 = 2 and r2c1 = 3 "
        "rule out 2 and 3 under *each number once per region*"
    ) in text
    assert (
        "**r1c1 = 1**, the only option left once r1c2 = 2, r2c1 = 3 and r2c2 = 4 "
        "rule out 2, 3 and 4 under *each number once per region*"
    ) in text
    assert len(text.split("\n\n")) > 2


def test_singles_do_not_repeat_previously_explained_eliminations():
    text = told("arrow_1_4x4.txt").markdown()
    assert "**r4c2 cannot be 3 or 4**" in text
    assert (
        "**r4c2 = 1**, the only option left after the earlier exclusions, once "
        "r2c2 = 2 rules out 2 under *each digit once per column*"
    ) in text


def test_dominosa_cell_singles_explain_used_domino_alternatives():
    text = told("dominosa_1_5x6.txt").markdown()
    assert (
        "**2-2 = r5c5-r5c6**, the only option left in *r5c6 is covered once* once "
        "2-3 = r1c6-r2c6 rules out 2-3 = r4c6-r5c6 under *each domino is used once*"
    ) in text
    assert (
        "**3-4 = r3c6-r4c6**, the only option left in *r3c6 is covered once* once "
        "2-3 = r1c6-r2c6 rules out 2-4 = r2c6-r3c6 under *each cell is covered once* "
        "and 0-4 = r4c4-r5c4 rules out 0-4 = r3c5-r3c6 under *each domino is used once*"
    ) in text


def test_singles_group_already_assigned_alternatives_without_misdescribing_cells():
    text = told("numbrix_1_4x4.txt").markdown()
    assert "n1, n2, n7, n14 and n16 are already assigned values other than r4c1" in text
    text = told("futoshiki_3_5x5.txt").markdown()
    assert "r3c2 and r3c5 are already assigned values other than 3" in text


def test_mosaic_count_includes_its_clue_cell_and_uses_singular():
    text = told("mosaic_1_5x5.txt").markdown()
    assert "1 black cell in the 3x3 window centered on" in text
    assert "1 black cells" not in text


def test_queens_story_uses_board_coordinates():
    text = example("queens_1_4x4.txt").read_text()
    kind = puzzlefile.detect(text)
    story = cli.pattern_story(kind, text, cli.load(text, kind).model).markdown()
    assert "**d = r4c2**, the only option left in *one queen in column 2*" in story
    assert "b = r2c1 rules out a = r1c2 and c = r3c2" in story
    assert "b = r2c1 rules out a = r2c2" in story
    assert "(3, 1)" not in story
    assert "(2, 1)" not in story


def test_boolean_cells_are_grouped_into_runs_in_family_words():
    text = told("pattern_4_10x10.txt").markdown()
    assert (
        "**r2c1, r2c2 and r2c7 = empty** and **r2c4\u2013r2c6 and r2c8\u2013r2c10 = filled**"
        in text
    )


def test_a_what_if_names_the_rule_it_breaks_and_the_intermediate_placements():
    story = told("calcudoku_6_6x6.txt")
    assert story.complete
    first = next(p for p in story.paragraphs if p.startswith("**Suppose r2c2 = 6.**"))
    assert "r2c3 cannot be 2 by *18x cage r2c2 r2c3 r3c3*; r4c3 = 2" in first
    assert "r4c2 cannot be 4 and r5c2 cannot be 1 by *4x cage" in first
    assert "r4c2 = 1 is the only option" in first
    assert "r1c4\u2013r1c6 cannot be 3 by *3 once in row 1*" in first
    assert (
        "But r1c5 = 1, 2 or 6, r1c6 = 1, 2 or 6 and r2c6 = 3 "
        "break *9+ cage r1c5 r1c6 r2c6*, so r2c2 ≠ 6."
    ) in first
    assert first.count(". Next ") >= 2
    assert first.index("r4c2 = 1 is the only option") < first.index("r1c2 = 3 is the only option")
    second = next(p for p in story.paragraphs if p.startswith("**Suppose r1c4 = 3.**"))
    assert "r2c5 cannot be 1, 4 or 5 by *12+ cage" in second
    assert "r2c5 = 6 is the only option" in second
    third = next(p for p in story.paragraphs if p.startswith("**Suppose r1c2 = 2.**"))
    assert "r2c1 cannot be 1, 4 or 6 by *13+ cage" in third
    assert "r2c1 = 5 is the only option" in third
    assert (
        "But r1c1 = 6, r1c2 = 5 and r2c1 = 5 break *13+ cage r1c1 r1c2 r2c1*"
    ) in story.markdown()
    assert "so r1c4 ≠ 3" in story.markdown()
    assert "*13+ cage r1c1 r1c2 r2c1* rules out 3" not in story.markdown()


@pytest.mark.parametrize(
    ("language", "premise", "case"),
    [
        (
            "en",
            "Each row and column contains the numbers 1 to 6 exactly once. Whenever a cage is "
            "cited below, use its arithmetic together with those row and column rules; cage "
            "cells not sharing a row or column may repeat",
            "r1c2 cannot be 1 and r2c1 cannot be 3 by *13+ cage",
        ),
        (
            "nl",
            "In elke rij en kolom staan de getallen 1 tot en met 6 precies één keer. Gebruik "
            "bij elke kooi hieronder zowel de berekening als deze rij- en kolomregels; "
            "kooivakjes die geen rij of kolom delen mogen gelijk zijn",
            "r1c2: geen 1 en r2c1: geen 3 door *13+ cage",
        ),
    ],
)
def test_calcudoku_case_cites_shared_line_uniqueness(language, premise, case):
    text = f"Language: {language}\n" + example("calcudoku_6_6x6.txt").read_text()
    puzzle = cli.load(text, "calcudoku")
    narrative = cli.pattern_story("calcudoku", text, puzzle.model).markdown()
    assert premise in narrative
    assert case in narrative
    assert narrative.index(premise) < narrative.index(case)


def test_case_contradiction_shows_candidates_in_dutch():
    text = told("calcudoku_6_6x6.txt", "nl").markdown()
    assert ("r1c5 = 1, 2 of 6, r1c6 = 1, 2 of 6 en r2c6 = 3 met *9+ cage r1c5 r1c6 r2c6*") in text
    assert ". Verder: " in text
    assert ". Maar dan " in text


def test_tent_case_and_chain_include_their_essential_premises():
    text = told("tents_3_4x4.txt").markdown()
    assert "r2c1 = no tent by *1 tent in column 1*" in text
    assert "r2c2 = no tent by *one tent beside tree r1c2*" in text
    assert "r3c2 = no tent by *tents do not touch near r2c2*" in text
    assert "r3c4 = no tent by *one tent beside tree r2c4*" in text
    assert (
        "**Chain.** Only r1c3 = tent or r2c2 = tent remain under *one tent beside tree r1c2*"
    ) in text


def test_case_does_not_repeat_a_boolean_placement_as_a_single():
    text = told("binairo_3_4x4.txt").markdown()
    case = next(paragraph for paragraph in text.split("\n\n") if "Suppose r1c2" in paragraph)
    assert case.count("r1c4 = white") == 2  # once in the trail, once in the contradiction
    assert "r1c4 = white is the only option" not in case


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            "r1c1 and r2c1 = white, r1c2 and r2c2 = black and r1c3 and r2c3 = black; "
            "the corresponding cells match",
        ),
        (
            "nl",
            "r1c1 en r2c1 = wit, r1c2 en r2c2 = zwart en r1c3 en r2c3 = zwart; "
            "de overeenkomstige vakjes zijn gelijk",
        ),
    ],
)
def test_binairo_case_shows_the_matching_cells(language, expected):
    text = f"Language: {language}\n" + example("binairo_3_4x4.txt").read_text()
    puzzle = cli.load(text, "binairo")
    narrative = cli.pattern_story("binairo", text, puzzle.model).markdown()
    assert expected in narrative
    if language == "en":
        assert narrative.startswith("- Here 1 is black and 0 is white.")
        assert "break *the rule that rows 1 and 2 must differ*" in narrative
    else:
        assert narrative.startswith("- Hier is 1 zwart en 0 wit.")
        assert "de regel dat rij 1 en rij 2 moeten verschillen" in narrative


def test_binairo_case_does_not_claim_unsettled_cells_match():
    text = example("binairo_3_4x4.txt").read_text()
    model, puzzle = binairo.compile_puzzle(text)
    narrator = generic_story.Narrator(
        model, Wording("en"), kind="binairo", comparisons=binairo.story_comparisons(puzzle)
    )
    broken = "rows 1 differs from 2 through cell 4"
    step = Step("r1c2", True, False, "what_if", "", sources=(broken,))
    assert narrator._comparison_premise(step, model, broken, ()) is None


def test_chain_explains_cell_single_and_both_conflicts_with_its_target():
    text = told("sudoku_33_9x9_chains.txt").markdown()

    assert text.count("If r3c7 \u2260 8") == 1
    first_chain = next(
        paragraph for paragraph in text.split("\n\n") if "If r3c7 \u2260 8" in paragraph
    )
    assert "Continuing the same chain" in first_chain
    assert "still assuming r3c7 \u2260 8" in first_chain
    assert "r5c7 = 8 is ruled out" in first_chain
    assert "r9c7 = 8 is ruled out" in first_chain
    assert (
        "under *8 once in box 1,3*, r1c9 = 8 or r3c7 = 8 were the only options; "
        "with r3c7 = 8 ruled out, r1c9 = 8"
    ) in text
    assert ("so r8c7 = 2; it is the only value left after r8c7 = 8 is ruled out") in text
    assert (
        "r5c7 = 2 is ruled out: r5c7 = 1 conflicts with it by *r5c7 holds one digit*, "
        "and r8c7 = 2 by *2 once in col 7*."
    ) in text
    reused_chain = next(paragraph for paragraph in text.split("\n\n") if "If r1c2 ≠ 8" in paragraph)
    assert "The earlier chain from r5c2 = 8 shows r9c7 = 6" in reused_chain
    assert reused_chain.count("r5c2 = 8") == 3
    assert "r5c7 = 1, so only r5c7 = 6" not in reused_chain


def test_cli_falls_back_to_the_generic_story_for_sudoku(capsys):
    assert cli.main([str(example("sudoku_33_9x9_chains.txt")), "--explain"]) == 0
    assert (
        "**Chain.** If r3c7 ≠ 8, then under *8 once in box 1,3*, r1c9 = 8 or "
        "r3c7 = 8 were the only options; with r3c7 = 8 ruled out, r1c9 = 8"
    ) in capsys.readouterr().out


@pytest.mark.solutions
@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_every_example_is_told_completely_with_unique_names(path):
    text = path.read_text()
    puzzle = cli.load(text, puzzlefile.detect(text))
    names = [c.name for c in puzzle.model.constraints] + [r.name for r in puzzle.model.relations]
    assert len(names) == len(set(names)), "proof replay looks constraints up by name"
    start = puzzle.model.clone()
    fired: list = []
    Solver(puzzle.model).solve(on_step=lambda rule, steps: fired.append((rule, steps)))
    story = cli.pattern_story(puzzlefile.detect(text), text, start, fired)
    assert story.complete


def test_yes_or_no_premises_read_in_the_family_words():
    text = told("thermometers_3_8x8.txt").markdown()
    assert "With r5c7 = mercury, *" in text
    assert "= True" not in text and "= False" not in text


def test_rooms_hidden_helpers_read_as_facts_about_people():
    text = example("rooms_3_6x8.txt").read_text()
    kind = puzzlefile.detect(text)
    story = cli.pattern_story(kind, text, cli.load(text, kind).model)
    told_text = story.markdown()
    assert story.complete
    assert "**Dirk and Finn are not together**" in told_text
    assert "*people who are together are in the same room* gives" in told_text
    assert (
        "**Ben = study**, the only option left once *Porch holds at most 1* rules out porch."
        in told_text
    )
    assert (
        "**Ada and Dirk = living room**, each the only option left once *Porch holds at most 1*"
        " rules out porch."
    ) in told_text
    assert (
        "**Eva = bathroom**, the only option left once *Exactly one of these two holds: Eva is in"
        " a room with a window; Finn is in a room with a plant* rules out study, *Porch holds at"
        " most 1* rules out porch and *The rooms with a plant hold exactly three people together*"
        " rules out attic."
    ) in told_text
    assert "Then Dirk = hall is the only option;" in told_text
    assert "Dirk and Ben are together by *Dirk is not alone*" in told_text
    for leak in ("intermediate step", "rooms 1", "clue 1", " count*", "; Given"):
        assert leak not in told_text
