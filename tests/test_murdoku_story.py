import re
from dataclasses import replace

import pytest

from csp import cli, generic_story, murdoku_story, story
from csp.bruteforce import solutions
from csp.core import Kind, Model, Solver, Step
from csp.murdoku import Board, CellMark, RoleSpec, Square
from csp.murdoku_expression_file import load_expression_board
from csp.murdoku_lower import compile_statements_with_origins
from csp.proof import Inference, Move, replay
from tests.examples import example

TEXT = """\
Size: 2
Regions:
a: hall
Grid:
a a
a a
People:
Ada
Ben
Roles:
guard: 1
Rules:
Ada in rows:1 | Ada stays in the first row.
Clues:
Ben in columns:1 | Ben is in the first column.
some role:guard in rows:1 | The guard is in the first row.
"""


@pytest.mark.parametrize(
    ("language", "positive", "negative", "label", "cardinality"),
    [
        (
            "en",
            "Ada has the guard role",
            "Ben does not have the guard role",
            "(2)",
            "allowed number",
        ),
        (
            "nl",
            "Ada heeft de rol guard",
            "Ben heeft de rol guard niet",
            "(2)",
            "toegestane aantal",
        ),
    ],
)
def test_expressions_explain_clue_wording_and_roles_even_after_all_people_are_placed(
    language, positive, negative, label, cardinality
):
    text = f"Language: {language}\n" + TEXT
    result = murdoku_story.explain(text)
    assert result.complete
    words = result.markdown()
    assert positive in words and negative in words
    assert words.count(f"**{positive}**") == 1
    assert words.count(f"**{negative}**") == 1
    assert any(
        cardinality in paragraph and negative in paragraph for paragraph in result.paragraphs
    )
    assert "Ada stays in the first row" in words
    assert "The guard is in the first row" in words
    assert label in words
    assert "__" not in words
    assert "binding" not in words
    assert "intermediate" not in words
    assert "role state" not in words
    assert story.explain(text) == words
    assert label not in murdoku_story.explain(text, numbered=False).markdown()


def test_proof_settles_hidden_singletons_after_visible_solution():
    model = Model()
    person = model.literal("Ada", "hall")
    model.constrain("Ada", Kind.EXACTLY_ONE, [person], defines="Ada")
    guard, not_guard = (model.literal("guard", value) for value in (True, False))
    model.constrain(
        "guard state", Kind.EXACTLY_ONE, [guard, not_guard], defines="guard", hidden=True
    )
    model.constrain("the guard", Kind.EXACTLY_ONE, [guard])
    result = replay(model, [])
    assert result.solution() == {"Ada": "hall"}
    assert result.chosen("guard") is True


def test_last_candidate_is_announced_once_before_the_later_assignment():
    board, rules, clues = load_expression_board(TEXT)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = murdoku_story._Narrator(TEXT, board, compilation, numbered=True)
    first, last = Square(0, 0), Square(0, 1)
    narrator.options["Ada"] = {first, last}
    assert narrator.conclusion([Step("Ada", first, False, "relations", "")]) == ("**Ada on r1c2**")
    assert narrator.conclusion([Step("Ada", last, True, "single", "")]) is None


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "on the squares marked red"),
        ("nl", "op de vakjes met markering red"),
    ],
)
def test_candidate_scopes_name_marked_squares_instead_of_an_imaginary_object(language, expected):
    board, _, _ = load_expression_board(TEXT)
    cells = (Square(0, 0), Square(1, 1))
    board.marks.append(CellMark("red", cells))
    places = story.Places(board, story.Wording(language))
    assert places.where(set(cells), set(board.free)) == expected
    places = story.Places(board, story.Wording(language, {"red": "the mat"}))
    assert "the mat" in places.where(set(cells), set(board.free))


@pytest.mark.parametrize(("language", "row"), [("en", "row 1"), ("nl", "rij 1")])
@pytest.mark.parametrize("numbered", [True, False])
def test_chain_link_reasons_use_board_metadata_and_expression_origins(language, row, numbered):
    text = f"Language: {language}\n" + TEXT
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = murdoku_story._Narrator(text, board, compilation, numbered)
    source = next(name for name, about in narrator.board_sources.items() if about == ("row", 0))
    assert narrator._link_reason(source) == f" ({row})"
    origin = next(item for item in compilation.origins if item.kind == "clue" and item.number == 2)
    source = next(
        constraint.name
        for index, constraint in enumerate(compilation.model.constraints)
        if origin in compilation.constraint_origins.get(index, ())
    )
    reason = narrator._link_reason(source)
    assert reason == (" (2)" if numbered else " (The guard is in the first row)")
    assert "__" not in reason


def test_what_if_announces_its_upshot_before_marking_a_placement_told(monkeypatch):
    board, rules, clues = load_expression_board(TEXT)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = murdoku_story._Narrator(TEXT, board, compilation, numbered=True)
    first, last = Square(0, 0), Square(0, 1)
    narrator.options["Ada"] = {first, last}
    step = Step("Ada", first, False, "what_if", "")
    move = Move.of("what_if", [step])
    assert move is not None
    inference = Inference("what_if", compilation.model, (step,), move)
    monkeypatch.setattr(narrator, "_what_if", lambda *_args: "The alternative contradicts a clue.")
    assert narrator.pattern(inference, []) == (
        "The alternative contradicts a clue. So **Ada on r1c2**."
    )
    assert narrator.conclusion([Step("Ada", last, True, "single", "")]) is None


def test_new_common_line_is_reserved_instead_of_listing_removed_columns():
    board, rules, clues = load_expression_board(TEXT)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = murdoku_story._Narrator(TEXT, board, compilation, numbered=True)
    conclusion = narrator.conclusion(
        [Step("Ada", Square(1, column), False, "relations", "") for column in range(2)]
    )
    assert conclusion == "**Ada can only be in row 1**, **nobody else can be there**"


@pytest.mark.parametrize("language", ["en", "nl"])
@pytest.mark.parametrize("complete", [False, True])
def test_role_exclusions_are_grouped_only_when_every_other_person_is_known(language, complete):
    board = Board(
        size=4,
        regions=[["a"] * 4 for _ in range(4)],
        region_names={"a": "hall"},
        objects=[],
        people=["Ada", "Ben", "Cleo", "Dex"],
        roles=[RoleSpec("guard", frozenset({1}))],
    )
    compilation = compile_statements_with_origins(board, [])
    narrator = murdoku_story._Narrator(f"Language: {language}", board, compilation, numbered=True)
    narrator.told.add((board.role_variable("Ada", "guard"), True))
    excluded = board.people[1:] if complete else board.people[1:3]
    steps = [
        Step(board.role_variable(person, "guard"), False, True, "count", "") for person in excluded
    ]
    conclusion = narrator.conclusion(steps)
    assert conclusion is not None
    grouped = "nobody else" if language == "en" else "niemand anders"
    assert (grouped in conclusion) == complete
    if not complete:
        assert "Ben" in conclusion and "Cleo" in conclusion
    assert narrator.conclusion(steps) is None


@pytest.mark.parametrize(("eligible", "show"), [("Ada", False), ("Ada Ben", True)])
def test_unnumbered_story_omits_only_role_facts_given_by_the_figure_list(eligible, show):
    text = TEXT.replace("Rules:", f"RoleEligibility:\nguard: {eligible}\nRules:")
    numbered = murdoku_story.explain(text).markdown()
    unnumbered = murdoku_story.explain(text, numbered=False).markdown()
    assert "Ada has the guard role" in numbered
    assert "Ben does not have the guard role" in numbered
    assert ("Ada has the guard role" in unnumbered) is show
    assert ("Ben does not have the guard role" in unnumbered) is show


def test_thinning_preserves_required_role_deductions_not_just_visible_placements():
    model = Model()
    person = model.literal("Ada", "hall")
    model.constrain("Ada", Kind.EXACTLY_ONE, [person], defines="Ada")
    guard, not_guard = (model.literal("guard", value) for value in (True, False))
    model.constrain(
        "guard state", Kind.EXACTLY_ONE, [guard, not_guard], defines="guard", hidden=True
    )
    model.relate("the guard is Ada", ["guard"], lambda guard: guard)
    moves = []

    def collect(rule, steps):
        if move := Move.of(rule, steps):
            moves.append(move)

    Solver(model.clone()).solve(on_step=collect)
    assert replay(model, generic_story.thin(model, moves)).chosen("guard") is None
    kept = generic_story.thin(model, moves, required_values={"guard": True})
    assert replay(model, kept).chosen("guard") is True


@pytest.mark.parametrize(
    "name",
    [
        "murdoku_3_house.txt",
        "murdoku_composition.txt",
        "halloween-museum-1.txt",
        "samen-onderweg.txt",
    ],
)
def test_expression_narration_names_every_placement_against_independent_solution(name):
    text = example(name).read_text()
    result = murdoku_story.explain(text)
    assert result.complete
    words = result.markdown()
    found = {
        person: (int(row) - 1, int(col) - 1)
        for person, row, col in re.findall(r"\*\*(\w+) (?:on|op) r(\d+)[ck](\d+)\*\*", words)
    }
    (answer,) = solutions(text, "murdoku", limit=2)
    expected = {
        person: (square.row, square.col)
        for person, square in answer.items()
        if not isinstance(square, bool)
    }
    assert found == expected
    assert "__" not in words
    assert "binding" not in words
    assert not re.search(r"\bbody\b", words)
    assert "intermediate" not in words


def test_expression_story_routes_cli_booklet_and_public_facade_through_the_same_words(
    tmp_path, capsys
):
    path = tmp_path / "puzzle.txt"
    path.write_text(TEXT)
    assert cli.main([str(path), "--explain"]) == 0
    assert story.explain(TEXT) in capsys.readouterr().out
    assert story.figure_clues(TEXT) == story.figure_clues(
        TEXT, expressions=cli.load_expression_board(TEXT)[2]
    )


DIRECT = """\
Size: 4
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


@pytest.mark.parametrize(
    ("language", "first", "second"),
    [
        (
            "en",
            "**in column 1**, so **cross out the other two open squares in that column**.",
            "**in row 1**, so **cross out the other open square in that row**.",
        ),
        (
            "nl",
            "**in kolom 1**, dus **streep de twee andere nog open vakjes in die kolom weg**.",
            "**in rij 1**, dus **streep het andere nog open vakje in die rij weg**.",
        ),
    ],
)
def test_direct_clues_reserve_lines_across_areas_without_counting_a_square_twice(
    language, first, second
):
    opening = murdoku_story.explain(f"Language: {language}\n" + DIRECT).paragraphs[0]
    assert first in opening and second in opening
    assert "(1)" in opening and "(2)" in opening
    assert "(1)" not in murdoku_story.explain(DIRECT, numbered=False).paragraphs[0]
    found = solutions(DIRECT, "murdoku", limit=100)
    assert len(found) == 16
    crossed = {Square(0, 0), Square(3, 0), Square(0, 3)}
    assert all(not crossed.intersection(answer.values()) for answer in found)


def test_direct_clue_reservation_excludes_blocked_cells():
    text = DIRECT.replace("PointObjects:", "Objects:\nrock: blocking r4c1\nPointObjects:")
    opening = murdoku_story.explain(text).paragraphs[0]
    assert "**in column 1**, so **cross out the other open square in that column**." in opening


def test_direct_clues_use_an_announced_rule_to_establish_the_line():
    text = DIRECT.replace("beacon: r2.5c0.5", "beacon: r2.5c2.5").replace(
        "Clues:", "Rules:\nnot Ada in rows:3\nClues:"
    )
    opening = murdoku_story.explain(text).paragraphs[0]
    assert "rule 1" in opening
    assert (
        "Ada is on a cell touching the beacon (1): **in row 2**, so "
        "**cross out the other two open squares in that row**."
    ) in opening


def test_hidden_population_work_is_not_cited_for_an_unrelated_directional_deduction():
    paragraphs = murdoku_story.explain(example("samen-onderweg.txt").read_text()).paragraphs
    deduction = next(paragraph for paragraph in paragraphs if "Haru zit niet in rij 5" in paragraph)
    assert "Haru staat boven Jun" in deduction
    assert "Jun zit niet in rij 1" in deduction
    assert "meeste mensen" not in deduction
    assert "minste mensen" not in deduction


def test_role_separation_sources_keep_the_puzzles_thematic_wording():
    words = murdoku_story.explain(example("menu-murdoku-1.txt").read_text()).markdown()
    assert "er staat nooit meer dan één zetmeel op dezelfde dag" in words
    assert "in different regions" not in words


@pytest.mark.parametrize(
    ("language", "known", "minimum", "empty"),
    [
        (
            "en",
            "Keiko and Mio are in Osaka, so **at least two people are there**.",
            "**at least three people are in Tokyo**.",
            "Together that accounts for all five people, so **nobody is in Okinawa**.",
        ),
        (
            "nl",
            "Keiko en Mio zijn in Osaka, dus **daar zijn minstens twee mensen**.",
            "**zijn er in Tokyo minstens drie mensen**.",
            "Samen zijn dat alle vijf mensen, dus **niemand is in Okinawa**.",
        ),
    ],
)
def test_population_capacity_explains_the_people_comparison_and_empty_area(
    language, known, minimum, empty
):
    text = (
        example("samen-onderweg.txt").read_text().replace("Language: nl", f"Language: {language}")
    )
    result = murdoku_story.explain(text)
    paragraph = next(paragraph for paragraph in result.paragraphs if empty in paragraph)
    assert known in paragraph
    assert minimum in paragraph
    assert paragraph.index(known) < paragraph.index(minimum) < paragraph.index(empty)
    assert "(1)" in paragraph
    assert "holds at least" not in result.markdown()
    assert "__area_population" not in result.markdown()
    assert "(1)" not in murdoku_story.explain(text, numbered=False).markdown()


def test_population_capacity_fallback_still_names_the_floors_not_hidden_literals(monkeypatch):
    monkeypatch.setattr(murdoku_story._Narrator, "_population_evidence", lambda *_args: None)
    text = example("samen-onderweg.txt").read_text().replace("Language: nl", "Language: en")
    words = murdoku_story.explain(text).markdown()
    assert "Tokyo area holding at least three people" in words
    assert "Osaka area holding at least two people" in words
    assert "already hold all five people, so **nobody is in Okinawa**." in words
    assert "holds at least" not in words


@pytest.mark.parametrize(
    ("language", "blocked", "tied"),
    [
        (
            "en",
            "all other free squares in Hiroshima are unavailable, "
            "so **only Goro is in Hiroshima**.",
            "The areas with the fewest people are Hiroshima and Okinawa (2), "
            "so **only Tatsuya is in Okinawa**.",
        ),
        (
            "nl",
            "alle andere vrije vakjes in Hiroshima vallen af, "
            "dus **alleen Goro zit in Hiroshima**.",
            "De gebieden met de minste mensen zijn Hiroshima en Okinawa (2), "
            "dus **alleen Tatsuya zit in Okinawa**.",
        ),
    ],
)
def test_tied_populations_explain_geometric_capacity_before_using_the_equality(
    language, blocked, tied
):
    text = (
        example("samen-in-de-blauwe-bladeren.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    result = murdoku_story.explain(text)
    paragraph = next(paragraph for paragraph in result.paragraphs if tied in paragraph)
    assert blocked in paragraph
    assert paragraph.index(blocked) < paragraph.index(tied)
    assert "?b" not in result.markdown()
    assert result.complete


@pytest.mark.parametrize(
    ("language", "reason"),
    [
        ("en", "The area counts allow at most one person in Okinawa"),
        ("nl", "De gebiedstellingen geven in Okinawa hoogstens één persoon"),
    ],
)
def test_population_ceiling_fallback_explains_the_bound_without_auxiliary_names(
    monkeypatch, language, reason
):
    monkeypatch.setattr(murdoku_story._Narrator, "_population_tied", lambda *_args: None)
    text = (
        example("samen-in-de-blauwe-bladeren.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    result = murdoku_story.explain(text)
    assert reason in result.markdown()
    assert "holds at least" not in result.markdown()
    assert "__area_population" not in result.markdown()
    assert result.complete


@pytest.mark.parametrize("case", ["unannounced", "untied", "outside", "placement"])
def test_tied_population_argument_requires_announced_blockers_and_matching_effects(case):
    text = example("samen-in-de-blauwe-bladeren.txt").read_text()
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    if case == "untied":
        compilation = replace(compilation, population_conditions=())
    narrator = murdoku_story._Narrator(text, board, compilation, numbered=True)
    placements = {
        "Kaori": Square(0, 1),
        "Renji": Square(1, 4),
        "Goro": Square(3, 5),
        "Mizuki": Square(2, 0),
        "Tatsuya": Square(8, 6),
    }
    for person, square in placements.items():
        narrator.options[person] = {square}
        if case != "unannounced" or person != "Renji":
            narrator.told.add((person, square))
    constraint = next(
        constraint
        for constraint, region, minimum in narrator.population_levels.values()
        if region == board.region_id("Okinawa") and minimum == 2
    )
    literal = constraint.reified_by
    assert literal is not None
    model = compilation.model
    steps = [Step(model.var_of(literal), model.value_of(literal), False, "count", "")]
    if case in {"outside", "placement"}:
        steps.append(Step("Yuki", Square(4, 8), case == "placement", "count", ""))
    inference = Inference("count", model, tuple(steps), None)
    before = {person: set(cells) for person, cells in narrator.options.items()}
    assert narrator._population_tied(inference) is None
    assert narrator.options == before
