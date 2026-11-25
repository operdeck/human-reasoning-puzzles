import re
from dataclasses import replace

import pytest

from csp import cli, generic_story, murdoku_story, story
from csp.bruteforce import solutions
from csp.core import Kind, Model, Solver, Step
from csp.murdoku import Board, CellMark, RoleSpec, Square
from csp.murdoku_expression_file import load_expression_board
from csp.murdoku_lower import compile_statements_with_origins
from csp.proof import Inference, Move, episodes, replay
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
            "clue 2:",
            "allowed number",
        ),
        (
            "nl",
            "Ada heeft de rol guard",
            "Ben heeft de rol guard niet",
            "aanwijzing 2:",
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
    assert label in words or "(2)" in words
    assert "__" not in words
    assert "binding" not in words
    assert "intermediate" not in words
    assert "role state" not in words
    assert story.explain(text) == words
    unnumbered = murdoku_story.explain(text, numbered=False).markdown()
    assert label not in unnumbered and "(2)" not in unnumbered


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
    ("language", "boundary"),
    [
        ("en", "An area boundary separates r2c2 from the tree; beside requires the same area"),
        ("nl", "Tussen r2k2 en de tree ligt een gebiedsgrens; naast vereist hetzelfde gebied"),
    ],
)
@pytest.mark.parametrize("numbered", [True, False])
def test_direct_beside_clue_explains_different_area(language, boundary, numbered):
    text = (
        example("murdoku_1_first_case.txt")
        .read_text()
        .replace("Language: en", f"Language: {language}")
    )
    opening = murdoku_story.explain(text, numbered=numbered).paragraphs[0]
    assert boundary in opening


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "area", "placement"),
    [
        ("en", "on the patio", "**Joost on r1c1** (on the patio)"),
        ("nl", "op het terras", "**Joost op r1k1** (op het terras)"),
    ],
)
def test_direct_clue_puts_placement_and_area_in_one_conclusion(language, area, placement, numbered):
    source = (
        example("murdoku_1_first_case.txt")
        .read_text()
        .replace("Language: en", f"Language: {language}")
        .replace("patio: on the patio", f"patio: {area}")
    )
    opening = murdoku_story.explain(source, numbered=numbered).paragraphs[0]
    assert placement in opening
    assert f"**{area}**:" not in opening
    boundary = "area boundary" if language == "en" else "gebiedsgrens"
    assert opening.index(boundary) < opening.index(placement)


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "feature", "boundary"),
    [
        (
            "nl",
            "de stinksokken",
            "r2k9 grenst aan een vakje met de stinksokken, maar ligt in een ander gebied; "
            "naast vereist hetzelfde gebied",
        ),
        (
            "en",
            "the socks",
            "r2c9 borders a square containing the socks, but is in a different area; "
            "beside requires the same area",
        ),
    ],
)
def test_shared_negative_beside_rule_explains_cross_boundary_square(
    language, feature, boundary, numbered
):
    source = (
        example("berghut-murdoku-3.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
        .replace("stinksokken: de stinksokken", f"stinksokken: {feature}")
    )
    text = murdoku_story.explain(source, numbered=numbered).markdown()
    assert boundary in text
    assert "een stinksokken" not in text


def test_beside_boundary_does_not_exempt_a_same_area_neighbor():
    source = """Size: 3
Regions:
a: hall
b: room
Grid:
a b a
a a a
a a a
People:
Ada
Ben
Cy
Objects:
sock: blocking r1c2
sock: blocking r2c1
Rules:
no people beside object:sock
"""
    board, rules, clues = load_expression_board(source)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = murdoku_story._Narrator(source, board, compilation, numbered=True)
    candidate = {Square(1, 1)}
    assert narrator._beside_different_area(rules[0].formula, candidate, rule=True) is None
    board.objects.pop()
    assert narrator._beside_different_area(rules[0].formula, candidate, rule=True) is not None
    pair = {Square(0, 0), Square(0, 2)}
    assert "Each of r1c1 and r1c3 borders" in narrator._beside_different_area(
        rules[0].formula, pair, rule=True
    )


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


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Ada has five candidate squares left"),
        ("nl", "Ada kan nog op vijf vakjes staan"),
    ],
)
def test_large_candidate_sets_are_described_as_possible_locations(language, expected):
    text = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
People:
Ada
"""
    board, _, _ = load_expression_board(text)
    chosen = {
        Square(0, 0),
        Square(0, 1),
        Square(1, 2),
        Square(2, 0),
        Square(2, 2),
    }

    assert story.Places(board, story.Wording(language)).describe(
        "Ada", chosen, set(board.free)
    ) == (expected)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("food-murdoku-3.txt", ("Jos shares an area with exactly two other dishes",)),
        ("menu-murdoku-2.txt", ("De vla deelt haar dag met precies twee andere gerechten",)),
        ("menu-murdoku-3.txt", ("De vla deelt haar dag met precies twee andere gerechten",)),
        ("wie-doet-het-met-wie-3.txt", ("Wouter deelt een kamer met precies één andere gast",)),
        (
            "zoo-murdoku-1.txt",
            (
                "De leeuw staat alleen in zijn verblijf",
                "De verzorger deelt een verblijf met precies één dier",
            ),
        ),
        (
            "zoo-murdoku-2.txt",
            (
                "De tijger staat alleen in zijn verblijf",
                "Geen aap staat alleen in zijn verblijf",
            ),
        ),
    ],
)
def test_complex_example_rules_use_player_facing_wording(name, expected):
    text = murdoku_story.explain(example(name).read_text()).markdown()

    assert all(phrase in text for phrase in expected)
    assert "every member of people" not in text
    assert "het aantal personen die in het gebied" not in text
    assert "?p" not in text


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
    assert reason == (
        " (The guard is in the first row (2))" if numbered else " (The guard is in the first row)"
    )
    assert "__" not in reason


def test_relation_deduction_shows_the_only_supported_person_pair():
    text = murdoku_story.explain(example("berghut-murdoku-3.txt").read_text()).markdown()

    assert (
        "Van de overgebleven vakjes voldoen alleen **Gunter op r8k9 en Sepp op r1k1** aan "
        "*aanwijzing 4: Gunter staat vijftien vakjes van Sepp af, horizontaal en verticaal "
        "geteld*."
    ) in text


@pytest.mark.parametrize(
    ("language", "excluded", "premise", "row"),
    [
        (
            "nl",
            "Reinhart moet in kolom 10 staan maar kan niet op r4k10 staan; "
            "volgens de regel van één persoon per rij of kolom kan daar dus niemand staan.",
            "alleen r2k5, r3k6 en r4k8 tellen mee. Op elk vakje past hoogstens één persoon, "
            "dus alle vakjes zijn bezet.",
            "r4k8 is bezet en in rij 4 past maar één persoon",
        ),
        (
            "en",
            "Reinhart must be in column 10 but cannot use r4c10; the one-person-per-line "
            "rule means nobody can stand there.",
            "only r2c5, r3c6 and r4c8 can count. At most one person can occupy each square, "
            "so all of them are occupied.",
            "r4c8 is occupied, and only one person can be in row 4",
        ),
    ],
)
@pytest.mark.parametrize("numbered", [True, False])
def test_stool_count_explains_why_each_line_is_reserved(language, excluded, premise, row, numbered):
    source = (
        example("berghut-murdoku-3.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    text = murdoku_story.explain(source, numbered=numbered).markdown()
    assert text.count(premise) == 1
    assert text.index(excluded) < text.index(premise) < text.index(row)


def test_count_reservation_does_not_require_every_square_for_a_lower_count():
    text = example("berghut-murdoku-3.txt").read_text()
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    narrator = murdoku_story._Narrator(text, board, compilation, numbered=True)
    before = compilation.model.clone()
    constraint = narrator.constraints["rule 1"]
    for literal in constraint.literals:
        if before.value_of(literal) == Square(3, 9) and not before.is_false(literal):
            before.eliminate(literal, "test", "exclude one stool")
    move = Move("cover3", ("rule 1",), ("row 4 holds one person",))
    step = Step("Brunhild", Square(3, 1), False, "cover3", "", sources=move.sources)
    inference = Inference("cover3", before, (step,), move)

    narrator.constraints["rule 1"] = replace(constraint, allowed_counts=frozenset({2}))
    assert narrator._count_square_reservation(inference) is None
    narrator.constraints["rule 1"] = replace(constraint, reified_by=constraint.literals[0])
    assert narrator._count_square_reservation(inference) is None
    narrator.constraints["rule 1"] = constraint
    assert narrator._count_square_reservation(inference) is not None


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "nl",
            "Greta, Ute, Waltraud en Siegfried kunnen niet op r4k2, r4k3, r4k4, r4k6 of r4k7 staan",
        ),
        (
            "en",
            "Greta, Ute, Waltraud and Siegfried cannot be on r4c2, r4c3, r4c4, r4c6 or r4c7",
        ),
    ],
)
def test_shared_broad_reductions_name_the_excluded_squares(language, expected):
    source = (
        example("berghut-murdoku-3.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    text = murdoku_story.explain(source).markdown()
    assert expected in text
    assert "40 vakjes staan" not in text


@pytest.mark.parametrize(
    ("language", "first", "second"),
    [
        (
            "nl",
            "Hannelore alleen nog op r5k2, r5k4, r5k7, r6k3, r7k2, r7k7, r10k2 of r10k7 "
            "kan staan en Siegfried alleen nog op r3k6, r5k4, r6k3 of r7k2 kan staan",
            "Gerhard alleen nog op r5k2, r5k4, r5k7, r6k3, r7k2, r7k7, r10k2 of r10k7 "
            "kan staan en Siegfried alleen nog op r3k6, r5k4 of r7k2 kan staan",
        ),
        (
            "en",
            "Hannelore can only be on r5c2, r5c4, r5c7, r6c3, r7c2, r7c7, r10c2 or r10c7 "
            "and Siegfried can only be on r3c6, r5c4, r6c3 or r7c2",
            "Gerhard can only be on r5c2, r5c4, r5c7, r6c3, r7c2, r7c7, r10c2 or r10c7 "
            "and Siegfried can only be on r3c6, r5c4 or r7c2",
        ),
    ],
)
@pytest.mark.parametrize("numbered", [True, False])
def test_distance_deductions_name_the_candidates_used(numbered, language, first, second):
    source = (
        example("berghut-murdoku-3.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    text = murdoku_story.explain(source, numbered=numbered).markdown()
    assert first in text
    assert second in text


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "opening", "excluded", "occupied", "remaining"),
    [
        (
            "nl",
            "Als Reinhart op r10k10 stond",
            "r1k9, r2k8, r4k6, r5k5, r6k4, r8k2 of r9k1",
            "de rijen 1, 2, 6 en 8 en de kolommen 1, 5 en 6",
            "Siegfried kan alleen nog op r3k6, r5k4, r6k3 of r7k2 staan",
        ),
        (
            "en",
            "If Reinhart were on r10c10",
            "r1c9, r2c8, r4c6, r5c5, r6c4, r8c2 or r9c1",
            "rows 1, 2, 6 and 8 and columns 1, 5 and 6",
            "Siegfried can only be on r3c6, r5c4, r6c3 or r7c2",
        ),
    ],
)
def test_distance_elimination_explains_occupied_lines(
    numbered, language, opening, excluded, occupied, remaining
):
    source = (
        example("berghut-murdoku-3.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    paragraph = next(
        paragraph
        for paragraph in murdoku_story.explain(source, numbered=numbered).paragraphs
        if opening in paragraph
    )
    assert excluded in paragraph
    assert occupied in paragraph
    assert remaining in paragraph
    if language == "nl":
        assert "Elk vakje ligt in een al bezette rij of kolom" in paragraph
    else:
        assert "Each square is in an already occupied row or column" in paragraph


def test_distance_elimination_does_not_invent_occupied_lines():
    text = example("berghut-murdoku-3.txt").read_text()
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    fired = []
    Solver(compilation.model.clone()).solve(on_step=lambda rule, steps: fired.append((rule, steps)))
    moves = [move for rule, steps in fired if (move := Move.of(rule, steps)) is not None]
    moves = generic_story.thin(compilation.model, moves)
    _, groups = episodes(compilation.model, moves)
    inference = next(
        inference
        for group in groups
        for inference in (group.pattern, *group.consequences)
        if inference.move and inference.move.sources == ("clue 3",)
    )
    narrator = murdoku_story._Narrator(text, board, compilation, numbered=True)
    assert narrator._relation_occupied_lines(inference) is None


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "candidates", "route", "other"),
    [
        (
            "nl",
            "Greta kan alleen nog op r2k5 (in het schoenenhok)",
            "in het schoenenhok → in de gang → in Kamer Noord",
            "Alle andere mogelijke gebiedsparen zijn gelijk of grenzen aan elkaar",
        ),
        (
            "en",
            "Greta can only be on r2c5 (in het schoenenhok)",
            "in het schoenenhok → in de gang → in Kamer Noord",
            "All other possible area pairs are the same area or share a border",
        ),
    ],
)
def test_area_distance_pair_explains_candidates_and_route(
    numbered, language, candidates, route, other
):
    source = (
        example("berghut-murdoku-3.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    paragraph = next(
        paragraph
        for paragraph in murdoku_story.explain(source, numbered=numbered).paragraphs
        if route in paragraph
    )
    assert candidates in paragraph
    assert other in paragraph
    assert ("r6k3" if language == "nl" else "r6c3") in paragraph


def test_area_distance_does_not_claim_distant_alternatives_are_adjacent():
    text = example("berghut-murdoku-3.txt").read_text()
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    fired = []
    Solver(compilation.model.clone()).solve(on_step=lambda rule, steps: fired.append((rule, steps)))
    moves = [move for rule, steps in fired if (move := Move.of(rule, steps)) is not None]
    moves = generic_story.thin(compilation.model, moves)
    _, groups = episodes(compilation.model, moves)
    inference = next(
        inference
        for group in groups
        for inference in (group.pattern, *group.consequences)
        if inference.move and inference.move.sources == ("clue 9",)
    )
    relation = next(item for item in compilation.model.relations if item.name == "clue 9")
    domains = [
        [(variable, inference.before.value_of(lit)) for lit in inference.before.options(variable)]
        for variable in relation.variables
    ]
    pair = next(
        (left, right)
        for left in domains[0]
        for right in domains[1]
        if relation.holds(left[1], right[1])
    )
    narrator = murdoku_story._Narrator(text, board, compilation, numbered=True)
    assert narrator._area_pair_reason(inference, domains, pair)
    other_area = board.region_of(domains[1][0][1])
    winning_area = board.region_of(pair[0][1])
    extra = next(
        square
        for square in board.free
        if board.region_of(square) not in {other_area, winning_area}
        and not board.regions_touch(board.region_of(square), other_area)
    )
    replace_index = next(index for index, value in enumerate(domains[0]) if value != pair[0])
    domains[0][replace_index] = (domains[0][0][0], extra)
    assert narrator._area_pair_reason(inference, domains, pair) is None


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "beginning", "areas"),
    [
        (
            "nl",
            "Reinhart zit niet",
            "in Kamer Noord, in Kamer Zuid, in het drooghok, in de gang, "
            "in het schoenenhok, in de stube of op het terras",
        ),
        (
            "en",
            "Reinhart is not",
            "in Kamer Noord, in Kamer Zuid, in het drooghok, in de gang, "
            "in het schoenenhok, in de stube or op het terras",
        ),
    ],
)
def test_shared_area_exclusions_are_grouped_without_losing_regions(
    numbered, language, beginning, areas
):
    source = (
        example("berghut-murdoku-3.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    paragraph = next(
        paragraph
        for paragraph in murdoku_story.explain(source, numbered=numbered).paragraphs
        if beginning in paragraph
    )
    assert paragraph.count(beginning) == 1
    assert areas in paragraph


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "clue", "empty", "bound"),
    [
        (
            "nl",
            "Haru staat niet naast de torii",
            "niemand is in Okinawa",
            "voor Haru blijven alleen de kolommen 2 t/m 4 over",
        ),
        (
            "en",
            "Haru is not beside de torii",
            "nobody is in Okinawa",
            "only columns 2 to 4 are available to Haru",
        ),
    ],
)
def test_direction_boundary_includes_prior_exclusions(numbered, language, clue, empty, bound):
    source = (
        example("japan-2-samen-onderweg.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    paragraphs = murdoku_story.explain(source, numbered=numbered).paragraphs
    direction = next(paragraph for paragraph in paragraphs if bound in paragraph)
    assert clue in direction
    assert empty in direction
    assert ("r1k1" if language == "nl" else "r1c1") in direction
    assert ("r3k1" if language == "nl" else "r3c1") in direction


def test_direction_boundary_candidate_bounds_are_lowercase_after_prefix():
    text = murdoku_story.explain(example("japan-2-samen-onderweg.txt").read_text()).markdown()
    assert "Met de eerdere beperkingen geldt: **voor Haru blijven alleen de rijen" in text
    assert "Met de eerdere beperkingen geldt: **voor Haru blijven alleen de kolommen" in text


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "known", "consequence"),
    [
        ("nl", "Nu is bekend: Jun op r3k1", "Haru zit niet in Osaka"),
        ("en", "With Jun on r3c1 already established", "Haru is not in Osaka"),
    ],
)
def test_relation_deduction_names_earlier_placement(numbered, language, known, consequence):
    source = (
        example("japan-2-samen-onderweg.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    paragraphs = murdoku_story.explain(source, numbered=numbered).paragraphs
    deduction = next(paragraph for paragraph in paragraphs if consequence in paragraph)
    assert known in deduction
    assert paragraphs.index(deduction) > next(
        index
        for index, paragraph in enumerate(paragraphs)
        if "**Jun op r3k1**" in paragraph or "**Jun on r3c1**" in paragraph
    )


def test_line_overlap_candidate_bounds_are_lowercase_after_so():
    text = murdoku_story.explain(example("berghut-murdoku-3.txt").read_text()).markdown()
    assert "dus **voor Brunhild, Hannelore en Gerhard blijven alleen de kolommen" in text


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "reason", "remaining"),
    [
        (
            "nl",
            "In rij 5 past maar één persoon, dus voor Hannelore vallen r5k3 en r5k5 af",
            "**Hannelore zit op r5k4, r7k5 of r7k7**",
        ),
        (
            "en",
            "Only one person can be in row 5, so r5c3 and r5c5 are unavailable to Hannelore",
            "**Hannelore is on r5c4, r7c5 or r7c7**",
        ),
    ],
)
def test_line_overlap_names_removed_candidates_before_remaining(
    numbered, language, reason, remaining
):
    source = (
        example("berghut-murdoku-2.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    text = murdoku_story.explain(source, numbered=numbered).markdown()
    assert reason in text and remaining in text
    assert text.index(reason) < text.index(remaining)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("nl", "voor Hannelore valt r5k5 af"),
        ("en", "r5c5 is unavailable to Hannelore"),
    ],
)
def test_line_overlap_names_a_single_removed_candidate(language, expected):
    text = (
        example("berghut-murdoku-2.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    fired = []
    Solver(compilation.model.clone()).solve(on_step=lambda rule, steps: fired.append((rule, steps)))
    moves = [move for rule, steps in fired if (move := Move.of(rule, steps)) is not None]
    moves = generic_story.thin(compilation.model, moves)
    _, groups = episodes(compilation.model, moves)
    inference = next(
        inference
        for group in groups
        for inference in (group.pattern, *group.consequences)
        if inference.move and inference.move.sources == ("col 4 holds one person",)
    )
    previous = inference.before.clone()
    previous.eliminate(previous.literal("Hannelore", Square(4, 2)), "test", "earlier exclusion")
    inference = replace(
        inference,
        before=previous,
        steps=tuple(
            step
            for step in inference.steps
            if (step.var, step.value) != ("Hannelore", Square(4, 2))
        ),
    )
    narrator = murdoku_story._Narrator(text, board, compilation, numbered=True)
    paragraph = narrator._line_overlap(inference, "remaining candidates")
    assert paragraph is not None and expected in paragraph


@pytest.mark.parametrize("numbered", [True, False])
def test_line_reservation_cites_prior_clue_exclusions(numbered):
    text = murdoku_story.explain(
        example("berghut-murdoku-2.txt").read_text(), numbered=numbered
    ).markdown()
    paragraph = next(p for p in text.split("\n\n") if "alleen Gunter kan in kolom 3" in p)
    assert "sluit r4k3, r5k3, r7k3 en r8k3 voor Gerhard uit" in paragraph
    assert "sluit r1k3, r2k3, r4k3, r7k3 en r8k3 voor Hannelore uit" in paragraph


def test_exact_line_single_names_its_only_remaining_candidate():
    text = murdoku_story.explain(example("japan-2-samen-onderweg.txt").read_text()).markdown()

    assert (
        "In kolom 1 is alleen **Jun op r3k1** over; omdat daar precies één persoon moet staan, "
        "moet die persoon daar staan."
    ) in text


def test_exact_line_single_connects_a_direct_clue_to_the_removed_square():
    text = murdoku_story.explain(example("japan-2-samen-onderweg.txt").read_text()).markdown()

    assert (
        "*aanwijzing 7: Haru staat niet naast de torii* sluit r2k2 voor Haru uit; "
        "daardoor is in kolom 2 alleen **Haru op r1k2** over"
    ) in text


def test_zoo_line_single_includes_the_caretaker_exclusion_and_no_duplicate_pair():
    text = murdoku_story.explain(example("zoo-murdoku-1.txt").read_text()).markdown()

    assert (
        "*regel 3: De verzorger deelt een verblijf met precies één dier* "
        "sluit r4k4 en r5k4 voor de verzorger uit"
    ) in text
    assert "de leeuw: in de savanne; de makaak: in de bergen" in text
    assert "de berggorilla: in de bergen; de kameel: in de woestijn" in text
    assert "kolom 4 alleen **de leeuw op r1k4**" in text
    assert text.count("de kameel op r4k2") == 1
    assert "met de kameel bezet" not in text


def test_hut_seat_and_role_deductions_name_candidates():
    text = murdoku_story.explain(example("berghut-murdoku-2.txt").read_text()).markdown()

    assert "**Brunhild zit op een bikkelstoel**" in text
    assert "**Waltraud zit op een bikkelstoel**" in text
    assert (
        "Brunhild en Waltraud kunnen ieder alleen nog op r2k5, r3k8, r4k7 en r4k8 staan; "
        "geen daarvan voldoet, dus geen van hen kan de schuldige zijn"
    ) in text
    assert "**Brunhild op r2k5**" in text
    assert "Tussen r2k5 en de kachel ligt een gebiedsgrens; naast vereist hetzelfde gebied" in text
    assert "Gerhard alleen nog in het drooghok, in Kamer Zuid of in het washok kan staan" in text
    assert "alleen Gunter kan in kolom 3 staan (r7k3 of r8k3)" in text
    assert "sluit r5k4 voor Gerhard uit" in text
    assert text.index("**Brunhild op r2k5**") < text.index("**Waltraud op r4k8**")
    reservation = next(p for p in text.split("\n\n") if "Greta moet in rij 1 staan" in p)
    assert reservation.index("Hannelore blijven alleen de rijen 1, 5 en 7 over") < (
        reservation.index("Greta moet in rij 1 staan")
    )
    assert "in de Kamer Noord" not in text
    assert "de resterende vakjes van Greta liggen allemaal in rij 1" not in text
    unnumbered = murdoku_story.explain(
        example("berghut-murdoku-2.txt").read_text(), numbered=False
    ).markdown()
    assert "regel 4 zegt" not in unnumbered.casefold()
    assert "De schuldige zat naast de kachel." in unnumbered
    assert "Brunhild en Waltraud kunnen ieder alleen nog" in unnumbered
    assert "geen van hen kan de schuldige zijn" in unnumbered


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "grouped", "boundary"),
    [
        ("nl", "Brunhild en Waltraud kunnen ieder alleen nog", "gebiedsgrens"),
        ("en", "Brunhild and Waltraud each have only", "area boundary"),
    ],
)
def test_shared_role_exclusion_names_each_person_and_the_common_reason(
    numbered, language, grouped, boundary
):
    source = (
        example("berghut-murdoku-2.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    text = murdoku_story.explain(source, numbered=numbered).markdown()
    paragraph = next(paragraph for paragraph in text.split("\n\n") if grouped in paragraph)
    assert boundary in paragraph
    assert paragraph.count(boundary) == 1


def test_role_exclusions_with_different_candidates_are_not_grouped():
    source = (
        example("berghut-murdoku-2.txt")
        .read_text()
        .replace("Clues:\n", "Clues:\nnot (Brunhild in rows:4)\n")
    )
    text = murdoku_story.explain(source).markdown()
    assert "Brunhild kan alleen nog op r2k5 en r3k8 staan" in text
    assert "Waltraud kan alleen nog op r2k5, r3k8, r4k7 en r4k8 staan" in text
    assert "Brunhild en Waltraud kunnen ieder alleen nog" not in text


def test_hut_line_overlaps_are_explained_before_they_are_used():
    text = murdoku_story.explain(example("berghut-murdoku-1.txt").read_text()).markdown()

    assert "kan alleen Waltraud op r2k4, r2k6 en r3k5 staan" in text
    row_five = "De enige overgebleven plaats in rij 5 is r5k3, in kolom 3"
    row_four = "De enige overgebleven plaats in kolom 5 is r4k5, in rij 4"
    assert text.index(row_five) < text.index("Hannelore en Gerhard alleen nog")
    assert text.index(row_four) < text.index("**Waltraud op r2k4**")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("berghut-murdoku-1.txt", "Waltraud Greta Gerhard Hannelore Ute Siegfried"),
        ("berghut-murdoku-2.txt", "Ute Reinhart Greta Hannelore Gunter Brunhild Waltraud Gerhard"),
        (
            "berghut-murdoku-3.txt",
            "Gunter Sepp Reinhart Gerhard Hannelore Siegfried Greta Brunhild Waltraud Ute",
        ),
    ],
)
def test_berghut_placements_remain_in_baseline_order(name, expected):
    text = murdoku_story.explain(example(name).read_text()).markdown()
    people = expected.split()
    placements = [
        person
        for bold in re.findall(r"\*\*(.*?)\*\*", text)
        for person in re.findall(r"\b(\w+) op r\d+k\d+", bold)
        if person in people
    ]
    assert placements == people


def test_person_single_is_located_by_the_intersecting_lines():
    text = murdoku_story.explain(example("halloween-museum-1.txt").read_text()).markdown()

    assert "The only remaining place for row 1 is r1c5" in text
    assert "**Alba on r1c5**" in text


def test_line_bound_explanation_names_the_remaining_person_squares():
    text = murdoku_story.explain(example("murder-hotel-3.txt").read_text()).markdown()

    assert (
        "Beatrice is on r1c10 or r2c10; Beatrice must occupy column 10; "
        "the one-person-per-line rule excludes everyone else"
    ) in text
    assert (
        "Marcella is on a staircase (6): **in column 5**, so **cross out the other two open "
        "squares in that column: r1c5 and r2c5**."
    ) in text


def test_line_overlap_explains_why_the_only_headstone_square_is_excluded():
    text = murdoku_story.explain(example("halloween-museum-1.txt").read_text()).markdown()

    reservation = "Fernando's remaining squares are all in column 2"
    row_single = "The only remaining place for row 1 is r1c5"
    assert reservation in text and row_single in text
    assert text.index(reservation) < text.index(row_single)
    assert (
        "The only remaining place for row 1 is r1c5, in column 5; since row 1 must be occupied, "
        "column 5 is already occupied"
    ) in text


def test_unique_role_in_area_names_the_candidates_and_their_exclusions():
    text = murdoku_story.explain(example("halloween-museum-1.txt").read_text()).markdown()

    assert "Alba's remaining squares are all in the Goya room" in text
    assert (
        "Fernando's remaining squares are all in column 2, so Elena cannot use r3c2 and r5c2"
        in text
    )
    assert "Elena is not beside the scarab case" in text
    assert "Rule 1: the murderer is in the Egyptian hall" in text
    assert "Carmen is the murderer" in text


@pytest.mark.parametrize("numbered", [True, False])
@pytest.mark.parametrize(
    ("language", "area_end", "next_reason", "conclusion"),
    [
        ("en", "Goya room. *", "r5c1. Fernando", "**Carmen is the murderer**."),
        ("nl", "Goya room. *", "r5k1. Fernando", "**Carmen is de murderer**."),
    ],
)
def test_role_area_reasons_are_separate_complete_sentences(
    numbered, language, area_end, next_reason, conclusion
):
    source = (
        example("halloween-museum-1.txt")
        .read_text()
        .replace("Language: en", f"Language: {language}")
    )
    paragraph = next(
        p for p in murdoku_story.explain(source, numbered=numbered).paragraphs if conclusion in p
    )
    assert area_end in paragraph
    assert next_reason in paragraph
    assert paragraph.endswith(conclusion)


def test_numbered_explanation_ends_with_the_authored_reveal():
    result = murdoku_story.explain(example("berghut-murdoku-3.txt").read_text())

    assert result.complete
    assert result.paragraphs[-1] == (
        "**Antwoord.** Ute haalde de top, maar zat niet op een bikkelkruk: Greta, Siegfried en "
        "Waltraud waren de drie echte bikkels."
    )


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
    assert conclusion == (
        "**Ada is not in row 2; Ada must occupy row 1; "
        "the one-person-per-line rule excludes everyone else**"
    )


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            "**Ada occupies row 1 and column 1; at most one person can use each row or column, so "
            "no one else can use those lines**",
        ),
        (
            "nl",
            "**Ada bezet rij 1 en kolom 1; per rij en kolom kan hoogstens één persoon staan, dus "
            "niemand anders kan die lijnen gebruiken**",
        ),
    ],
)
def test_occupied_rows_and_columns_are_explained_once_for_all_people(language, expected):
    board = Board(
        size=3,
        regions=[["a"] * 3 for _ in range(3)],
        region_names={"a": "hall"},
        objects=[],
        people=["Ada", "Ben"],
    )
    compilation = compile_statements_with_origins(board, [])
    narrator = murdoku_story._Narrator(
        f"Language: {language}\n" + TEXT, board, compilation, numbered=True
    )
    narrator.conclusion([Step("Ada", Square(0, 0), True, "single", "")])

    text = narrator.conclusion(
        [
            Step("Ben", Square(0, 1), False, "single", ""),
            Step("Ben", Square(1, 0), False, "single", ""),
        ]
    )
    assert text == expected

    assert narrator.conclusion([Step("Ben", Square(0, 2), False, "single", "")]) is None


def test_later_line_exclusions_do_not_repeat_the_board_rule():
    board = Board(
        size=3,
        regions=[["a"] * 3 for _ in range(3)],
        region_names={"a": "hall"},
        objects=[],
        people=["Ada", "Ben", "Cal"],
    )
    compilation = compile_statements_with_origins(board, [])
    narrator = murdoku_story._Narrator(TEXT, board, compilation, numbered=True)
    narrator.conclusion([Step("Ada", Square(0, 0), True, "single", "")])
    first = narrator.conclusion(
        [
            Step("Ben", Square(0, 1), False, "single", ""),
            Step("Ben", Square(1, 0), False, "single", ""),
        ]
    )
    narrator.conclusion([Step("Ben", Square(1, 1), True, "single", "")])
    second = narrator.conclusion(
        [
            Step("Cal", Square(1, 2), False, "single", ""),
            Step("Cal", Square(2, 1), False, "single", ""),
        ]
    )
    assert first is not None and "exactly one person occupies each row and column" in first
    assert second == (
        "**Ben occupies row 2 and column 2; the one-person-per-line rule excludes everyone else**"
    )


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            "**Ada occupies row 1 and column 1; exactly one person occupies each row and column, "
            "so no one else can use those lines**",
        ),
        (
            "nl",
            "**Ada bezet rij 1 en kolom 1; elke rij en kolom heeft precies één persoon, dus "
            "niemand anders kan die lijnen gebruiken**",
        ),
    ],
)
def test_full_board_line_reservations_state_exact_occupancy(language, expected):
    board = Board(
        size=2,
        regions=[["a"] * 2 for _ in range(2)],
        region_names={"a": "hall"},
        objects=[],
        people=["Ada", "Ben"],
    )
    compilation = compile_statements_with_origins(board, [])
    narrator = murdoku_story._Narrator(
        f"Language: {language}\n" + TEXT, board, compilation, numbered=True
    )
    narrator.conclusion([Step("Ada", Square(0, 0), True, "single", "")])

    text = narrator.conclusion(
        [
            Step("Ben", Square(0, 1), False, "single", ""),
            Step("Ben", Square(1, 0), False, "single", ""),
        ]
    )
    assert text == expected


def test_cover_explains_the_row_reservation_before_its_consequences():
    text = example("berghut-murdoku-2.txt").read_text()
    story = murdoku_story.explain(text).markdown()
    reservation = (
        "Brunhild en Waltraud kunnen alleen in de rijen 2 en 4 staan; "
        "ze moeten verschillende rijen bezetten, dus die rijen zijn gereserveerd."
    )
    assert reservation in story
    assert story.index(reservation) < story.index("Greta op r1k1")


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


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "**only Ben and Cleo are eligible for the guard role**"),
        ("nl", "**alleen Ben en Cleo komen in aanmerking voor de rol guard**"),
    ],
)
def test_complete_role_eligibility_exclusions_name_the_remaining_candidates(language, expected):
    board = Board(
        size=4,
        regions=[["a"] * 4 for _ in range(4)],
        region_names={"a": "hall"},
        objects=[],
        people=["Ada", "Ben", "Cleo", "Dex"],
        roles=[RoleSpec("guard", frozenset({1}), eligible_people=frozenset({"Ben", "Cleo"}))],
    )
    compilation = compile_statements_with_origins(board, [])
    narrator = murdoku_story._Narrator(f"Language: {language}", board, compilation, numbered=True)
    conclusion = narrator.conclusion(
        [
            Step(board.role_variable("Ada", "guard"), False, True, "count", ""),
            Step(board.role_variable("Dex", "guard"), False, True, "count", ""),
        ]
    )
    assert conclusion == expected


@pytest.mark.parametrize(("eligible", "show"), [("Ada", False), ("Ada Ben", True)])
def test_unnumbered_story_omits_only_role_facts_given_by_the_figure_list(eligible, show):
    text = TEXT.replace("Rules:", f"RoleEligibility:\nguard: {eligible}\nRules:")
    numbered = murdoku_story.explain(text).markdown()
    unnumbered = murdoku_story.explain(text, numbered=False).markdown()
    assert "Ada has the guard role" in numbered
    assert "Ben does not have the guard role" in numbered
    expected = (
        "only Ada is eligible for the guard role"
        if eligible == "Ada"
        else "only Ada and Ben are eligible for the guard role"
    )
    assert expected in unnumbered
    assert ("Ada has the guard role" in unnumbered) is show
    assert ("Ben does not have the guard role" in unnumbered) is show


@pytest.mark.parametrize(
    ("language", "phrase", "certain", "possible"),
    [
        (
            "en",
            "{who} is a {role}",
            "guard: only these assignments are true: Ada is a guard.",
            "guard: the only possible assignments are: Ada is a guard; Ben is a guard.",
        ),
        (
            "nl",
            "{who} is een {role}",
            "guard: alleen deze toewijzingen zijn waar: Ada is een guard.",
            "guard: dit zijn de enige mogelijke toewijzingen: Ada is een guard; Ben is een guard.",
        ),
    ],
)
@pytest.mark.parametrize("eligible", ["Ada", "Ada Ben"])
def test_unnumbered_story_keeps_eligibility_with_custom_role_words(
    language, phrase, certain, possible, eligible
):
    text = f"Language: {language}\n" + TEXT.replace(
        "Regions:", f"Words:\nrole_has: {phrase}\nRegions:"
    ).replace("Rules:", f"RoleEligibility:\nguard: {eligible}\nRules:")
    unnumbered = murdoku_story.explain(text, numbered=False).markdown()
    assert (certain if eligible == "Ada" else possible) in unnumbered


def test_custom_role_words_state_fixed_eligibility_without_figure_descriptions():
    text = (
        example("zoo-murdoku-1.txt")
        .read_text()
        .replace("Makaak: een aap, nooit alleen", "Makaak: nooit alleen")
        .replace("Berggorilla: een aap, nooit alleen", "Berggorilla: nooit alleen")
    )
    unnumbered = murdoku_story.explain(text, numbered=False).markdown()
    assert (
        "aap: alleen deze toewijzingen zijn waar: de makaak is een aap "
        "en de berggorilla is een aap." in unnumbered
    )


def test_custom_role_eligibility_statements_are_scoped_to_each_role():
    text = (
        TEXT.replace("Regions:", "Words:\nrole_has: {who} is a {role}\nRegions:")
        .replace("Roles:\nguard: 1", "Roles:\nguard: 1\nhelper: 1")
        .replace("Rules:", "RoleEligibility:\nguard: Ada\nhelper: Ben\nRules:")
    )
    unnumbered = murdoku_story.explain(text, numbered=False).markdown()
    assert "guard: only these assignments are true: Ada is a guard." in unnumbered
    assert "helper: only these assignments are true: Ben is a helper." in unnumbered


@pytest.mark.parametrize(
    ("language", "exact_row", "exact_column"),
    [
        ("en", "exactly one person per row", "exactly one person per column"),
        ("nl", "precies één persoon per rij", "precies één persoon per kolom"),
    ],
)
def test_full_board_row_and_column_sources_say_exactly_one(language, exact_row, exact_column):
    text = example("berghut-murdoku-2.txt").read_text()
    board, _, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues)
    localized = text.replace("Language: nl", f"Language: {language}")
    narrator = murdoku_story._Narrator(localized, board, compilation, True)
    row_source = next(name for name, about in narrator.board_sources.items() if about == ("row", 0))
    column_source = next(
        name for name, about in narrator.board_sources.items() if about == ("col", 0)
    )
    assert narrator.source_words[row_source] == exact_row
    assert narrator.source_words[column_source] == exact_column


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            "Keiko's remaining squares are all in column 5, so Keiko must be there; "
            "exactly one person per column leaves no other person in that line",
        ),
        (
            "nl",
            "De resterende vakjes van Keiko liggen allemaal in kolom 5, dus Keiko moet daar staan; "
            "precies één persoon per kolom sluit iedereen anders in die lijn uit",
        ),
    ],
)
def test_line_reservation_names_the_persons_shared_column(language, expected):
    text = (
        example("japan-2-samen-onderweg.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
    )
    story = murdoku_story.explain(text).markdown()
    assert expected in story


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
        "japan-2-samen-onderweg.txt",
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
    found.update(
        {
            person: (int(row) - 1, int(column) - 1)
            for person, row, column in re.findall(
                r"\*\*(\w+) (?:occupies row|bezet rij) (\d+) (?:and|en) "
                r"(?:column|kolom) (\d+);",
                words,
            )
        }
    )
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
            "**in column 1**, so **cross out the other two open squares in that column: "
            "r1c1 and r4c1**.",
            "**in row 1**, so **cross out the other open square in that row**.",
        ),
        (
            "nl",
            "**in kolom 1**, dus **streep de twee andere nog open vakjes in die kolom weg: "
            "r1k1 en r4k1**.",
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
        "**cross out the other two open squares in that row: r2c1 and r2c4**."
    ) in opening


EXPRESSION_PROSE = {
    "food-murdoku-1.txt": (
        "Jos shares an area with exactly one other person, and that person is a food.",
    ),
    "food-murdoku-2.txt": (
        "Jos shares an area with exactly one other person, and that person is a food.",
    ),
    "zoo-murdoku-3.txt": (
        "De verzorger deelt een gebied met precies één ander persoon, en dat is een dier.",
        "In het gebied van iedere aap staan minstens twee personen.",
    ),
    "japan-1-samen-in-de-blauwe-bladeren.txt": (
        "Gebied Hiroshima en gebied Okinawa hebben evenveel personen.",
        "Gebied Okinawa heeft minder personen dan elk gebied met een vrij vakje "
        "behalve gebied Hiroshima.",
    ),
    "wie-doet-het-met-wie-1.txt": ("Wouter deelt een gebied met precies één ander persoon.",),
    "wie-doet-het-met-wie-2.txt": ("Wouter deelt een gebied met precies één ander persoon.",),
    "wie-doet-het-met-wie-4.txt": ("Wouter deelt een gebied met precies één ander persoon.",),
    "menu-murdoku-1.txt": ("Vla deelt een gebied met precies twee andere personen.",),
    "berghut-murdoku-2.txt": (
        "Ute en Gerhard staan minstens drie rijen óf minstens drie kolommen van elkaar af.",
        "Het grootste verschil tussen Hannelore en Brunhild is precies drie rijen of kolommen.",
    ),
    # Existing authored overrides and readable idioms must keep working.
    "food-murdoku-3.txt": ("Jos shares an area with exactly two other dishes.",),
    "wie-doet-het-met-wie-3.txt": ("Wouter deelt een kamer met precies één andere gast.",),
    "wie-doet-het-met-wie-5.txt": (
        "Wouter wordt als laatste geplaatst en is alleen in een gebied met degene "
        "met wie hij het doet: iemand in een badjas.",
    ),
    "menu-murdoku-2.txt": ("De vla deelt haar dag met precies twee andere gerechten.",),
    "menu-murdoku-3.txt": ("De vla deelt haar dag met precies twee andere gerechten.",),
}
FORBIDDEN_PROSE = (
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
)


def _player_text(name: str) -> str:
    entries = story.figure_clues(example(name).read_text())
    lines = [clue.text for figure in entries.figures for clue in figure.clues]
    return "\n".join([*lines, *(clue.text for clue in entries.other)])


@pytest.mark.parametrize("name", sorted(EXPRESSION_PROSE))
def test_expression_rules_read_as_player_prose(name):
    text = _player_text(name)
    for fragment in EXPRESSION_PROSE[name]:
        assert fragment in text, (name, fragment)
    for forbidden in FORBIDDEN_PROSE:
        assert forbidden not in text, (name, forbidden)


def test_samen_onderweg_solution_explains_relative_row_bounds():
    paragraphs = murdoku_story.explain(example("japan-2-samen-onderweg.txt").read_text()).paragraphs
    deduction = next(
        paragraph
        for paragraph in paragraphs
        if "Haru staat boven Jun (5)" in paragraph
        and "voor haru blijven alleen de rijen 1 t/m 4 over" in paragraph.casefold()
        and "voor jun blijven alleen de rijen 2 t/m 5 over" in paragraph.casefold()
    )
    assert deduction
    assert any(
        "Haru staat boven Jun (5)" in paragraph
        and "voor haru blijven alleen de rijen 1 en 2 over" in paragraph.casefold()
        for paragraph in paragraphs
    )


def test_role_separation_sources_keep_the_puzzles_thematic_wording():
    words = murdoku_story.explain(example("menu-murdoku-1.txt").read_text()).markdown()
    assert "er staat nooit meer dan één zetmeel op dezelfde dag" in words
    assert "in different regions" not in words


def test_role_reveal_keeps_both_rules_when_each_is_needed():
    not_alone = "every ?p in role:guard: count (people in area of ?p) >= 2"
    crime_scene = "some role:guard in tag:crime"
    text = f"""Size: 5
Regions:
a: hall
b: lounge
c: garden
Grid:
a a a a a
a a a a a
b b b b b
c c c c c
c c c c c
AreaTags:
crime: hall lounge
People:
Ada
Ben
Carmen
Dora
Evan
Attributes:
eligible: Ada Carmen Dora
Roles:
guard: 1
RoleEligibility:
guard: attribute:eligible
Rules:
{not_alone}
{crime_scene}
Clues:
Ada in rows:1 and Ada in columns:1
Ben in rows:2 and Ben in columns:2
Carmen in rows:3 and Carmen in columns:3
Dora in rows:4 and Dora in columns:4
Evan in rows:5 and Evan in columns:5
"""
    assert len(solutions(text, "murdoku", limit=2)) == 1
    for rule in (not_alone, crime_scene):
        assert len(solutions(text.replace(rule, ""), "murdoku", limit=2)) == 2
    result = murdoku_story.explain(text)
    assert result.complete
    words = result.markdown()
    assert "Ada has the guard role" in words
    assert "rule 1:" in words
    assert "rule 2:" in words
    assert "__" not in words


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
        example("japan-2-samen-onderweg.txt")
        .read_text()
        .replace("Language: nl", f"Language: {language}")
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
    text = example("japan-2-samen-onderweg.txt").read_text().replace("Language: nl", "Language: en")
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
        example("japan-1-samen-in-de-blauwe-bladeren.txt")
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
        example("japan-1-samen-in-de-blauwe-bladeren.txt")
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
    text = example("japan-1-samen-in-de-blauwe-bladeren.txt").read_text()
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
