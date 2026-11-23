from string import Formatter

import pytest

from csp.murdoku import Board, BoardObject, CellMark, EdgeItem, PointObject, RoleSpec, Square
from csp.murdoku_expression_words import PHRASES, ExpressionWords
from csp.murdoku_lang import parse_statement


@pytest.fixture
def board():
    return Board(
        size=3,
        regions=[["a", "a", "a"], ["b", "b", "b"], ["b", "b", "b"]],
        region_names={"a": "hall", "b": "garden"},
        objects=[
            BoardObject("bed", "standable", (Square(0, 0),)),
            BoardObject("bed", "standable", (Square(1, 1),)),
        ],
        people=["Ada", "Ben"],
        marks=[CellMark("red", (Square(0, 0),)), CellMark("blue", (Square(1, 1),))],
        roles=[RoleSpec("guard", frozenset({0, 1, 2}))],
        attributes={"trained": frozenset({"Ada"})},
    )


def test_languages_offer_the_same_keys_and_placeholders():
    assert PHRASES["en"].keys() == PHRASES["nl"].keys()

    def fields(template):
        return {name for _, name, _, _ in Formatter().parse(template) if name}

    for key in PHRASES["en"]:
        assert fields(PHRASES["en"][key]) == fields(PHRASES["nl"][key]), key


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Ada is in a board corner"), ("nl", "Ada is in een rasterhoek")],
)
def test_board_corner_target_is_singular_without_overriding_authored_names(
    board, language, expected
):
    statement = parse_statement("Ada in corner:board")
    assert ExpressionWords(board, language).statement(statement) == expected
    words = ExpressionWords(board, language, phrases={"name.corner": "CUSTOM CORNERS"})
    assert "CUSTOM CORNERS" in words.statement(statement)
    counted = ExpressionWords(board, language).statement(
        parse_statement("count (people in corner:board) = 2")
    )
    assert ("in a board corner" if language == "en" else "in een rasterhoek") not in counted


def test_person_verb_and_single_line_idioms_keep_explicit_phrase_overrides(board):
    words = ExpressionWords(
        board,
        "nl",
        phrases={
            "atom.one": "{subject} bevindt zich {relation} {target}",
            "atom.not": "{subject} bevindt zich niet {relation} {target}",
            "name.rows": "de rij met nummer {name}",
        },
    )
    assert words.statement(parse_statement("Ada beside object:bed")).startswith(
        "Ada bevindt zich naast"
    )
    assert words.statement(parse_statement("not Ada on object:bed")).startswith(
        "Ada bevindt zich niet op"
    )
    assert words.statement(parse_statement("Ada in rows:1")) == (
        "Ada bevindt zich in de rij met nummer 1"
    )


@pytest.mark.parametrize("language", ["en", "nl"])
def test_king_neighbourhood_preserves_union_scope_and_author_templates(board, language):
    board.objects.append(BoardObject("chair", "standable", (Square(2, 2),)))
    source = "not Ada dir:king object:bed,chair <= 1"
    words = ExpressionWords(board, language)
    sentence = words.statement(parse_statement(source))
    assert (
        "not on or directly next to" if language == "en" else "niet op of direct naast"
    ) in sentence
    assert (
        "a square of a bed or a square of the chair"
        if language == "en"
        else "een vakje van een bed of een vakje van de chair"
    ) in sentence
    assert ("across area boundaries" if language == "en" else "over gebiedsgrenzen") in sentence
    assert "distance" not in sentence
    override = ExpressionWords(board, language, phrases={"rel.dir.king": "NEAR"})
    assert "NEAR" in override.statement(parse_statement(source))
    assert (
        override.statement(parse_statement(source + " | Keep this sentence."))
        == "Keep this sentence."
    )


@pytest.mark.parametrize("comparison", ["= 1", "<= 2", ">= 1"])
def test_other_king_distances_are_not_rewritten_as_on_or_adjacent(board, comparison):
    sentence = ExpressionWords(board).statement(
        parse_statement(f"Ada dir:king object:bed {comparison}")
    )
    assert "king-step distance" in sentence
    assert "directly next to" not in sentence


@pytest.mark.parametrize(
    ("language", "comparison", "expected"),
    [
        (
            "en",
            ">= 3",
            "Ada and Ben are at least three rows apart or at least three columns apart",
        ),
        (
            "en",
            "<= 3",
            "Ada and Ben are at most three rows apart and at most three columns apart",
        ),
        ("en", "= 3", "The largest gap between Ada and Ben is exactly three rows or columns"),
        (
            "nl",
            ">= 3",
            "Ada en Ben staan minstens drie rijen óf minstens drie kolommen van elkaar af",
        ),
        (
            "nl",
            "<= 3",
            "Ada en Ben staan hoogstens drie rijen én hoogstens drie kolommen van elkaar af",
        ),
        ("nl", "= 3", "Het grootste verschil tussen Ada en Ben is precies drie rijen of kolommen"),
    ],
)
def test_king_distance_between_people_reads_in_rows_and_columns(
    board, language, comparison, expected
):
    formula = parse_statement(f"Ada dir:king Ben {comparison}")
    assert ExpressionWords(board, language).statement(formula) == expected


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        ("en", "Ada dir:up Ben = 1", "Ada is exactly one row above Ben"),
        ("nl", "Ada dir:right Ben = 2", "Ada staat precies twee kolommen rechts van Ben"),
        ("en", "not Ada dir:down Ben = 1", "Ada is not exactly one row below Ben"),
    ],
)
def test_exact_person_directions_name_the_distance_units(board, language, source, expected):
    assert ExpressionWords(board, language).statement(parse_statement(source)) == expected


def test_exact_direction_idiom_retains_phrase_overrides_and_spatial_distance_semantics(board):
    words = ExpressionWords(board, phrases={"rel.dir.up.exact": "ABOVE"})
    assert "ABOVE" in words.statement(parse_statement("Ada dir:up Ben = 1"))
    assert "exactly one row" not in ExpressionWords(board).statement(
        parse_statement("area:hall dir:up area:garden = 1")
    )


@pytest.mark.parametrize("counts", [{0}, {0, 1}, {1}, {2}])
def test_only_an_exactly_one_role_gets_a_definite_singular_caption(board, counts):
    board.roles = [RoleSpec("guard", frozenset(counts))]
    source = parse_statement("Ada dir:up role:guard")
    caption = ExpressionWords(board).statement(source)
    assert ("the guard" in caption) == (counts == {1})
    words = ExpressionWords(board, phrases={"name.role": "the candidates for {name}"})
    assert "the candidates for guard" in words.statement(source)


def test_area_union_keeps_each_preposition_and_negates_the_whole_alternative(board):
    words = ExpressionWords(board, names={"hall": "on Monday", "garden": "in Paris"})
    source = "Ada in area:hall,garden"
    sentence = "Ada is on Monday or Ada is in Paris"
    assert words.statement(parse_statement(source)) == sentence
    assert words.statement(parse_statement("not " + source)) == (
        f"it is not true that ({sentence})"
    )
    override = ExpressionWords(board, phrases={"op.union": "{left} PLUS {right}"})
    assert "PLUS" in override.statement(parse_statement(source))


@pytest.mark.parametrize("counts", [{0}, {0, 1}, {1}, {2}])
def test_role_area_quantifier_reads_without_a_bound_variable(board, counts):
    board.roles = [RoleSpec("guard", frozenset(counts))]
    source = parse_statement("every ?p in role:guard: count people in area of ?p >= 2")
    sentence = ExpressionWords(board).statement(source)
    if counts == {1}:
        assert sentence == "at least two people are in the area of the guard"
    else:
        assert sentence == "Every guard has at least two people in their area"
        assert ExpressionWords(board, "nl").statement(source) == (
            "In het gebied van iedere guard staan minstens twee personen"
        )
    override = ExpressionWords(
        board, phrases={"quant.every": "FOR {variables} FROM {source}: {body}"}
    )
    assert override.statement(source).startswith("FOR")


@pytest.mark.parametrize(
    ("language", "count", "expected"),
    [
        ("en", "1 + 1", "Ada shares an area with exactly one other person"),
        ("en", "2 + 1", "Ada shares an area with exactly two other people"),
        ("nl", "1 + 1", "Ada deelt een gebied met precies één ander persoon"),
        ("nl", "2 + 1", "Ada deelt een gebied met precies twee andere personen"),
    ],
)
def test_shared_area_count_idiom_counts_the_others(board, language, count, expected):
    board.people = ["Ada", "Ben", "Cid"]
    formula = parse_statement(f"count (people in area of Ada) = {count}")
    assert ExpressionWords(board, language).statement(formula) == expected


@pytest.mark.parametrize(
    ("language", "count", "expected"),
    [
        (
            "en",
            "1 + 1",
            "Ada shares an area with exactly one other person, and that person is a helper",
        ),
        (
            "en",
            "2 + 1",
            "Ada shares an area with exactly two other people, and each of them is a helper",
        ),
        ("nl", "1 + 1", "Ada deelt een gebied met precies één ander persoon, en dat is een helper"),
    ],
)
def test_shared_area_attribute_idiom_names_every_companion(board, language, count, expected):
    board.people = ["Ada", "Ben", "Cid"]
    formula = (
        f"count (people in area of Ada) = {count} "
        "and every ((people except Ada) in area of Ada) is attribute:trained"
    )
    words = ExpressionWords(board, language, names={"trained": "helper"})
    assert words.statement(parse_statement(formula)) == expected


@pytest.mark.parametrize(
    ("language", "operator", "expected"),
    [
        ("en", "=", "area hall and area garden have the same number of people"),
        ("en", ">", "area hall has more people than area garden"),
        ("en", "<", "area hall has fewer people than area garden"),
        ("nl", "=", "gebied hall en gebied garden hebben evenveel personen"),
        ("nl", ">", "gebied hall heeft meer personen dan gebied garden"),
        ("nl", "<", "gebied hall heeft minder personen dan gebied garden"),
    ],
)
def test_area_population_comparisons_read_as_ties_and_sentences(
    board, language, operator, expected
):
    formula = f"count (people in area:hall) {operator} count (people in area:garden)"
    assert ExpressionWords(board, language).statement(parse_statement(formula)) == expected


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "area hall has fewer people than every area other than area garden"),
        ("nl", "gebied hall heeft minder personen dan elk gebied behalve gebied garden"),
    ],
)
def test_population_comparison_excluding_another_area_keeps_the_scope(board, language, expected):
    formula = (
        "every ?a in (areas except area:hall, area:garden): "
        "count (people in ?a) > count (people in area:hall)"
    )
    assert ExpressionWords(board, language).statement(parse_statement(formula)) == expected


@pytest.mark.parametrize(
    "formula",
    [
        "(people in area of Ada) = (Ada, attribute:trained)",
        "(attribute:trained, Ada) = (people in area of Ada)",
    ],
)
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Ada shares an area with every helper and nobody else"),
        ("nl", "Ada deelt een gebied met iedere helper en met niemand anders"),
    ],
)
def test_shared_area_set_equality_names_the_companion_kind(board, formula, language, expected):
    words = ExpressionWords(board, language, names={"trained": "helper"})
    assert words.statement(parse_statement(formula)) == expected


@pytest.mark.parametrize("language", ["en", "nl"])
@pytest.mark.parametrize(
    "formula",
    [
        "(people in area of Ada) = (Ada, attribute:trained, Ben)",
        "(Ada, attribute:trained, role:guard) = (people in area of Ada)",
        "(people in area of Ada) = (Ada, attribute:trained, attribute:swift)",
    ],
)
def test_shared_area_set_equality_keeps_extra_union_members(board, language, formula):
    board.attributes["swift"] = frozenset({"Ben"})
    statement = parse_statement(formula)
    words = ExpressionWords(board, language)
    compositional = ExpressionWords(
        board, language, phrases={"set.equal": PHRASES[language]["set.equal"]}
    )
    assert words.statement(statement) == compositional.statement(statement)


def test_constant_arithmetic_in_a_count_reads_as_its_value(board):
    sentence = ExpressionWords(board).statement(parse_statement("count people = 1 + 1"))
    assert "plus" not in sentence
    assert "2" in sentence


def test_unique_holder_in_a_single_tag_uses_the_authored_place_caption(board):
    board.roles = [RoleSpec("guard", frozenset({1}))]
    board.area_tags["scene"] = ["hall"]
    words = ExpressionWords(board, names={"scene": "at the crime scene"})
    assert words.statement(parse_statement("every ?a in tag:scene: some role:guard in ?a")) == (
        "the guard is at the crime scene"
    )
    words = ExpressionWords(board)
    assert words.statement(parse_statement("every ?a in tag:scene: some role:guard in ?a")) == (
        "the guard is in the hall"
    )


@pytest.mark.parametrize(
    ("language", "formula", "expected"),
    [
        ("en", "count people on object:bed = 1", "exactly one person is on a bed"),
        ("en", "count people in area:hall >= 2", "at least two people are in the hall"),
        ("en", "count people in area:hall <= 0", "at most zero people are in the hall"),
        ("en", "count people on mark:red = 1", "exactly one person is on the squares marked red"),
        ("nl", "count people on object:bed = 2", "precies twee mensen staan op een bed"),
        ("nl", "count people on object:bed = 1", "precies één persoon staat op een bed"),
        (
            "nl",
            "count people on mark:red = 1",
            "precies één persoon staat op de vakjes met markering red",
        ),
    ],
)
def test_person_count_idiom_preserves_bounds_number_and_footprint(
    board, language, formula, expected
):
    words = ExpressionWords(board, language)
    assert words.statement(parse_statement(formula)) == expected


def test_person_count_idiom_respects_numeric_templates_and_keeps_other_counts_compositional(board):
    words = ExpressionWords(board, phrases={"number.compare": "{left}: {comparison} {right}"})
    assert words.statement(parse_statement("count people in area:hall = 1")).startswith(
        "the number of"
    )
    assert (
        ExpressionWords(board)
        .statement(parse_statement("count empty cells = 1"))
        .startswith("the number of")
    )
    targets = ExpressionWords(board, phrases={"target.mark": "the square labelled {name}"})
    assert targets.statement(parse_statement("count people on mark:red = 1")) == (
        "exactly one person is on the square labelled red"
    )


@pytest.mark.parametrize("language", ["en", "nl"])
def test_mark_count_scope_keeps_authored_names_and_templates(board, language):
    statement = parse_statement("count people on mark:red = 1")
    named = ExpressionWords(board, language, names={"red": "CUSTOM SQUARES"})
    assert named.statement(statement).endswith("CUSTOM SQUARES")
    phrased = ExpressionWords(board, language, phrases={"count.mark": "SQUARES {name}"})
    assert phrased.statement(statement).endswith("SQUARES red")


@pytest.mark.parametrize("language", ["en", "nl"])
@pytest.mark.parametrize(
    "source",
    [
        "Ada in area:hall",
        "some role:guard on object:bed",
        "every Ada, Ben is attribute:trained",
        "no (people on mark:red) dir:up Ben = 1",
        "Ada dir:up+right Ben >= 1",
        "Ada dir:nearest:king Ben",
        "count (people on mark:red,blue) 0..2",
        "count (people in area:hall) odd",
        "count people - count role:guard >= 0",
        "area:hall is empty",
        "some empty areas touches area:hall",
        "(people on object:bed) != Ada",
        "if Ada in area:hall then Ben in area:garden",
        "not (Ada in area:hall or Ben in area:garden)",
        "exactly 1 of (Ada in area:hall; Ben in area:garden)",
        "every ?p in people: ?p is role:guard",
        "at most 1 ?r in roles: Ada is ?r",
        "every ?a, ?b in areas: ?a on ?b",
        "count (?p in people where ?p on object:bed) >= 1",
        "count (area of object:bed) >= 1",
        "count (areas is empty) >= 1",
    ],
)
def test_every_construct_has_compositional_wording(board, language, source):
    assert ExpressionWords(board, language).statement(parse_statement(source))


@pytest.mark.parametrize(
    ("language", "reference", "source_phrase"),
    [
        ("en", "that area", "areas where"),
        ("nl", "dat gebied", "gebieden waarvoor geldt:"),
    ],
)
def test_comprehension_filter_uses_a_natural_bound_variable_reference(
    board, language, reference, source_phrase
):
    statement = parse_statement("count (?a in areas where count (people in ?a) = 2) = 1")
    wording = ExpressionWords(board, language).statement(statement)
    assert "?a" not in wording
    assert reference in wording
    assert source_phrase in wording


@pytest.mark.parametrize(
    ("language", "alone", "only"),
    [
        ("en", "Ada is alone in their area", "Ada is the only person on"),
        ("nl", "Ada is alleen in het eigen gebied", "Ada is de enige persoon op"),
    ],
)
def test_common_shapes_have_idiomatic_wording(board, language, alone, only):
    words = ExpressionWords(board, language)
    assert words.statement(parse_statement("count (people in area of Ada) = 1")) == alone
    assert words.statement(parse_statement("(people on object:bed) = Ada")).startswith(only)


@pytest.mark.parametrize(
    ("language", "negative", "either"),
    [
        ("en", "Ada is not in the hall", "either Ada is in the hall"),
        ("nl", "Ada is niet in de hall", "of Ada is in de hall"),
    ],
)
def test_simple_negations_and_exclusive_alternatives_read_as_sentences(
    board, language, negative, either
):
    words = ExpressionWords(board, language)
    assert words.statement(parse_statement("not Ada in area:hall")) == negative
    result = words.statement(parse_statement("exactly 1 of (Ada in area:hall; Ben in area:garden)"))
    assert result.startswith(either)
    assert ("but not both" if language == "en" else "maar niet allebei") in result


def test_negated_quantified_or_potentially_empty_subjects_keep_their_scope(board):
    board.roles = [RoleSpec("guard", frozenset({0, 1}))]
    words = ExpressionWords(board, "en")
    for source in (
        "not some role:guard in area:hall",
        "not every role:guard in area:hall",
        "not role:guard in area:hall",
    ):
        assert words.statement(parse_statement(source)).startswith("it is not true that")


def test_idioms_do_not_replace_explicit_boolean_or_choice_phrase_overrides(board):
    words = ExpressionWords(
        board,
        "en",
        phrases={
            "bool.not": "NOT ({formula})",
            "choice.exactly": "CHOOSE {count}: {choices}",
        },
    )
    assert words.statement(parse_statement("not Ada in area:hall")).startswith("NOT (")
    assert words.statement(
        parse_statement("exactly 1 of (Ada in area:hall; Ben in area:garden)")
    ).startswith("CHOOSE 1:")


@pytest.mark.parametrize(
    "source",
    [
        "at least 1 of (Ada in area:hall; Ben in area:garden)",
        "exactly 0 of (Ada in area:hall; Ben in area:garden)",
        "exactly 1 of (Ada in area:hall; Ben in area:garden; Ada on object:bed)",
    ],
)
def test_other_choices_are_not_worded_as_an_exclusive_pair(board, source):
    assert "either" not in ExpressionWords(board, "en").statement(parse_statement(source))


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Each of the areas contains someone from people holding role guard"),
        ("nl", "In elk van de gebieden is minstens één van de personen met rol guard"),
    ],
)
def test_each_area_role_rule_has_idiomatic_wording_without_a_bound_variable(
    board, language, expected
):
    words = ExpressionWords(board, language)
    statement = parse_statement("every ?a in areas: some role:guard in ?a")
    assert words.statement(statement) == expected


def test_area_containment_does_not_get_a_person_occupancy_idiom(board):
    words = ExpressionWords(board, "en")
    statement = parse_statement("every ?a in areas: some area:hall in ?a")
    assert "someone" not in words.statement(statement)


@pytest.mark.parametrize(
    ("language", "scope"),
    [
        ("en", "any of the objects named bed"),
        ("nl", "een van de voorwerpen met de naam bed"),
    ],
)
def test_only_on_idiom_covers_the_entire_object_set(board, language, scope):
    words = ExpressionWords(board, language)
    assert scope in words.statement(parse_statement("(people on object:bed) = Ada"))


@pytest.mark.parametrize(
    ("language", "operator", "expected"),
    [
        ("en", "<", "area hall has more people than every other area"),
        ("en", ">", "area hall has fewer people than every other area"),
        ("nl", "<", "gebied hall heeft meer personen dan ieder ander gebied"),
        ("nl", ">", "gebied hall heeft minder personen dan ieder ander gebied"),
    ],
)
def test_strict_area_population_comparison_has_an_idiom(board, language, operator, expected):
    source = (
        "every ?a in (areas except area:hall): "
        f"count (people in ?a) {operator} count (people in area:hall)"
    )
    assert ExpressionWords(board, language).statement(parse_statement(source)) == expected


def test_population_idiom_does_not_hide_ties_or_a_different_comparison_target(board):
    words = ExpressionWords(board)
    tied = (
        "every ?a in (areas except area:hall): count (people in ?a) <= count (people in area:hall)"
    )
    different = tied.replace("<=", "<").replace("count (people in area:hall)", "count people")
    assert "every ?a" in words.statement(parse_statement(tied))
    assert "every ?a" in words.statement(parse_statement(different))


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "area hall has fewer people than every other area containing a free cell"),
        ("nl", "gebied hall heeft minder personen dan ieder ander gebied met een vrij vakje"),
    ],
)
def test_population_idiom_preserves_the_free_area_scope(board, language, expected):
    source = (
        "every ?a in (area of free cells except area:hall): "
        "count (people in ?a) > count (people in area:hall)"
    )
    assert ExpressionWords(board, language).statement(parse_statement(source)) == expected


def test_wording_overrides_and_names_are_used(board):
    words = ExpressionWords(
        board,
        "en",
        names={"Ada": "the keeper"},
        phrases={"rel.beside": "next to"},
    )
    assert words.statement(parse_statement("Ada beside object:bed")) == (
        "the keeper is next to a bed"
    )
    assert words.statement(parse_statement("Ada in area:hall | A custom clue.")) == "A custom clue."


def test_invalid_language_and_phrase_key_fail_explicitly(board):
    with pytest.raises(ValueError, match="unknown expression language"):
        ExpressionWords(board, "fr")
    with pytest.raises(ValueError, match="unknown expression phrase keys"):
        ExpressionWords(board, phrases={"rel.unknown": "???"})
    with pytest.raises(ValueError, match=r"unknown placeholders.*subject"):
        ExpressionWords(board, phrases={"rel.beside": "near {subject}"})
    with pytest.raises(ValueError, match=r"missing placeholders.*relation.*target"):
        ExpressionWords(board, phrases={"atom.one": "{subject} is somewhere"})
    for template in ("{}", "{subject:{width}}"):
        with pytest.raises(ValueError, match="unsupported placeholder"):
            ExpressionWords(board, phrases={"det.every": template})


def test_read_language_display_names_and_compositional_overrides(board):
    words = ExpressionWords.read(
        board,
        "Language: nl\nWords:\nAda: de bewaker\nrel.beside: vlak naast\n",
    )
    assert words.statement(parse_statement("Ada beside object:bed")) == (
        "de bewaker staat vlak naast een bed"
    )


def test_object_target_wording_uses_names_without_changing_set_wording(board):
    words = ExpressionWords(board, names={"bed": "a bed"})
    assert words.statement(parse_statement("Ada on object:bed")) == "Ada is on a bed"
    assert "the number of objects referred to as a bed" in words.statement(
        parse_statement("count object:bed = 2")
    )
    overridden = ExpressionWords(
        board, names={"bed": "a bed"}, phrases={"target.object": "exactly {name}"}
    )
    assert overridden.statement(parse_statement("Ada on object:bed")) == "Ada is on exactly a bed"


@pytest.mark.parametrize(
    ("language", "namespace", "expected"),
    [
        ("en", "point_object:lamp", "Ada is on a cell touching the lamp"),
        ("en", "edge_item:window", "Ada is on a cell touching a window"),
        ("en", "mark:red", "Ada is on a cell marked red"),
        ("nl", "point_object:lamp", "Ada zit op een vakje dat de lamp raakt"),
        ("nl", "edge_item:window", "Ada zit op een vakje dat een raam raakt"),
        ("nl", "mark:red", "Ada zit op een vakje met de markering red"),
    ],
)
def test_person_locations_describe_feature_footprints_and_repeated_instances(
    board, language, namespace, expected
):
    board.point_objects = [PointObject.at("lamp", (1, 2), board.size)]
    board.edge_items = [
        EdgeItem("window", "window", (Square(0, 0),)),
        EdgeItem("window", "window", (Square(0, 1),)),
    ]
    words = ExpressionWords(
        board,
        language,
        names={"window": "the window" if language == "en" else "het raam"},
    )
    assert words.statement(parse_statement(f"Ada on {namespace}")) == expected


def test_adjacent_objects_remain_separate_instances_when_naming_one_of_them(board):
    board.objects = [
        BoardObject("apple", "standable", (Square(0, 0),)),
        BoardObject("apple", "standable", (Square(0, 1),)),
    ]
    from csp.story import Places, Wording

    words = ExpressionWords(board, names={"apple": "the apple"})
    assert words.statement(parse_statement("Ada on object:apple")) == "Ada is on an apple"
    assert Places(board, Wording(words={"apple": "the apple"})).thing("apple") == "an apple"


def test_non_person_targets_keep_entity_wording_not_person_location_templates(board):
    words = ExpressionWords(board, names={"red": "red"})
    result = words.statement(parse_statement("some object:bed on mark:red"))
    assert "cell marked" not in result
    assert "mark" in result


@pytest.mark.parametrize(
    ("language", "display", "expected"),
    [
        ("en", "in the hall", "Ada is in the hall"),
        ("nl", "in de hal", "Ada is in de hal"),
    ],
)
def test_area_names_accept_existing_location_wordings(board, language, display, expected):
    words = ExpressionWords(board, language, names={"hall": display})
    assert words.statement(parse_statement("Ada in area:hall")) == expected


def test_area_location_keeps_its_authored_preposition_and_explicit_relation_override(board):
    names = {"hall": "on Monday"}
    words = ExpressionWords(board, names=names)
    assert words.statement(parse_statement("Ada in area:hall")) == "Ada is on Monday"
    words = ExpressionWords(board, names=names, phrases={"rel.in": "scheduled for"})
    assert words.statement(parse_statement("Ada in area:hall")) == "Ada is scheduled for Monday"


def test_named_person_idioms_keep_generic_scope_and_explicit_phrase_overrides(board):
    words = ExpressionWords(board)
    assert words.statement(parse_statement("Ada dir:furthest Ben")) == (
        "Ada is uniquely farthest from Ben"
    )
    for source in ("Ada dir:furthest role:guard", "Ada dir:furthest:areas Ben"):
        assert "every other person outside the target set" in words.statement(
            parse_statement(source)
        )
    words = ExpressionWords(
        board,
        phrases={
            "rel.dir.areas.same": "together with",
            "rel.dir.furthest": "most distant from",
            "target.object.named": "the feature named {name}",
        },
    )
    assert "together with Ben" in words.statement(parse_statement("Ada dir:areas Ben = 0"))
    assert "most distant from Ben" in words.statement(parse_statement("Ada dir:furthest Ben"))
    assert words.statement(parse_statement("Ada on object:bed")) == (
        "Ada is on the feature named bed"
    )


def test_read_rejects_misspelled_expression_phrase_keys(board):
    with pytest.raises(ValueError, match="unknown expression phrase key"):
        ExpressionWords.read(board, "Words:\nrel.besid: next to\n")


@pytest.mark.parametrize("line", ["unseparated", ": missing name"])
def test_read_rejects_malformed_words(board, line):
    with pytest.raises(ValueError, match="Words:"):
        ExpressionWords.read(board, f"Words:\n{line}\n")


@pytest.mark.parametrize(
    ("legacy", "replacement"),
    [
        ("clue.alone", "idiom.alone"),
        ("clue.only_on", "idiom.only_on"),
        ("target.attribute", "name.attribute"),
        ("clue.with_same_area_n", r"\| wording"),
    ],
)
def test_read_suggests_replacements_for_legacy_clue_phrases(board, legacy, replacement):
    with pytest.raises(ValueError, match=replacement):
        ExpressionWords.read(board, f"Words:\n{legacy}: old wording\n")


def test_role_binding_and_spatial_identity_are_worded_differently(board):
    words = ExpressionWords(board)
    role = words.statement(parse_statement("some ?r in roles: Ada is ?r"))
    identity = words.statement(parse_statement("area:hall is area:garden"))
    assert "Ada is a member of ?r" in role
    assert "the same entity as" in identity


def test_person_identity_and_role_membership_have_distinct_wording(board):
    words = ExpressionWords(board)
    assert words.statement(parse_statement("Ada is Ben")) == "Ada is the same person as Ben"
    assert "Ada is the same person as ?p" in words.statement(
        parse_statement("some ?p in people: Ada is ?p")
    )
    assert "Ada is a member of ?r" in words.statement(
        parse_statement("some ?r in roles: Ada is ?r")
    )


def test_spatial_containment_overlap_and_projection_are_distinct(board):
    words = ExpressionWords(board)
    assert "entirely contained in" in words.statement(
        parse_statement("some object:bed in area:hall")
    )
    assert "overlapping" in words.statement(parse_statement("some object:bed on area:hall"))
    assert "overlapping" in words.statement(parse_statement("count (area of object:bed) >= 1"))


def test_dutch_adjective_modifiers_agree_with_their_operand(board):
    words = ExpressionWords(board, "nl")
    assert "lege gebieden" in words.statement(parse_statement("count empty areas = 1"))
    assert "vrije vakjes" in words.statement(parse_statement("count free cells >= 1"))
    assert "leeg gebied hall" in words.statement(parse_statement("some empty area:hall on rows:1"))
    assert "is leeg" in words.statement(parse_statement("area:hall is empty"))


def test_direction_wording_retains_axis_measure_and_superlative_exclusions(board):
    words = ExpressionWords(board)
    compound = words.statement(parse_statement("Ada dir:up+right Ben = 1"))
    nearest = words.statement(parse_statement("Ada dir:nearest:king Ben"))
    assert "each axis distance equal to 1" in compound
    assert "every other person outside the target set" in nearest
    assert "king-step distance" in nearest


@pytest.mark.parametrize(
    ("language", "same", "pair", "distance", "distinct"),
    [
        (
            "en",
            "in the same area as",
            "Ada and Ben are in the same area",
            "area distance",
            "distinct from the subject",
        ),
        (
            "nl",
            "in hetzelfde gebied als",
            "Ada en Ben staan in hetzelfde gebied",
            "gebiedsafstand",
            "verschillend van het onderwerp",
        ),
    ],
)
def test_zero_area_distance_has_an_idiomatic_relation(
    board, language, same, pair, distance, distinct
):
    words = ExpressionWords(board, language)
    assert words.statement(parse_statement("Ada dir:areas Ben = 0")) == pair
    assert same in words.statement(parse_statement("count (people dir:areas Ada = 0) = 1"))
    assert distinct in words.statement(parse_statement("Ada dir:areas role:guard = 0"))
    assert distinct in words.statement(parse_statement("Ada dir:areas Ada = 0"))
    assert distance not in words.statement(parse_statement("Ada dir:areas Ben = 0"))
    assert distance in words.statement(parse_statement("Ada dir:areas Ben >= 0"))
    assert distinct not in words.statement(parse_statement("Ada dir:areas Ben = 1"))


@pytest.mark.parametrize(
    ("language", "formula", "expected"),
    [
        ("en", "Ada dir:areas Ben = 1", "Ada and Ben are exactly one area boundary apart"),
        (
            "nl",
            "Ada dir:areas Ben >= 2",
            "Ada en Ben zijn minstens twee gebiedsgrenzen van elkaar verwijderd",
        ),
        (
            "en",
            "Ada dir:manhattan Ben <= 6",
            "Ada and Ben are at most six steps apart",
        ),
        (
            "nl",
            "Ada dir:manhattan Ben >= 10",
            "Ada en Ben zijn minstens tien stappen van elkaar verwijderd",
        ),
        ("en", "Ada dir:rows Ben = 1", "Ada and Ben are exactly one row apart"),
        (
            "nl",
            "Ada dir:cols Ben <= 2",
            "Ada en Ben zijn hoogstens twee kolommen van elkaar verwijderd",
        ),
        (
            "nl",
            "Ada dir:rows Ben >= 3",
            "Ada en Ben zijn minstens drie rijen van elkaar verwijderd",
        ),
    ],
)
def test_named_person_distance_pairs_read_naturally(board, language, formula, expected):
    assert ExpressionWords(board, language).statement(parse_statement(formula)) == expected


@pytest.mark.parametrize(
    ("language", "name", "expected"),
    [
        ("en", "the counter", "Ada is in a square that shares a side with the counter"),
        ("nl", "het aanrecht", "Ada staat op een vakje dat een zijde deelt met het aanrecht"),
    ],
)
def test_one_orthogonal_step_from_an_object_reads_naturally(board, language, name, expected):
    board.objects.append(BoardObject("counter", "blocking", (Square(0, 1), Square(0, 2))))
    statement = parse_statement("Ada dir:manhattan object:counter = 1")
    words = ExpressionWords(board, language, names={"counter": name})
    assert words.statement(statement) == expected
    custom = ExpressionWords(board, language, phrases={"rel.dir.manhattan": "CUSTOM"})
    assert "CUSTOM" in custom.statement(statement)


def test_distance_idiom_preserves_author_relation_templates_and_potential_self_targets(board):
    words = ExpressionWords(board, phrases={"rel.dir.areas": "CUSTOM"})
    assert "CUSTOM" in words.statement(parse_statement("Ada dir:areas Ben >= 2"))
    sentence = ExpressionWords(board).statement(parse_statement("Ada dir:areas role:guard = 1"))
    assert "distinct from the subject" in sentence
    axis_words = ExpressionWords(board, "nl", phrases={"rel.dir.cols": "CUSTOM"})
    assert "CUSTOM" in axis_words.statement(parse_statement("Ada dir:cols Ben <= 2"))


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "nobody except Ada is in the hall"),
        ("nl", "niemand behalve Ada is in de hall"),
    ],
)
def test_no_people_except_preserves_the_exception_without_requiring_its_presence(
    board, language, expected
):
    statement = parse_statement("no (people except Ada) in area:hall")
    assert ExpressionWords(board, language).statement(statement) == expected
    words = ExpressionWords(board, language, phrases={"det.no": "NONE OF {subject}"})
    assert "NONE OF" in words.statement(statement)


@pytest.mark.parametrize("language", ["en", "nl"])
def test_knight_object_union_names_feature_squares_instead_of_raw_object_sets(board, language):
    board.objects.append(BoardObject("chair", "standable", (Square(2, 2),)))
    sentence = ExpressionWords(board, language).statement(
        parse_statement("Ada dir:knight object:bed,chair")
    )
    assert (
        "a square of a bed or a square of the chair"
        if language == "en"
        else "een vakje van een bed of een vakje van de chair"
    ) in sentence


def test_determiner_and_direction_phrase_overrides_compose(board):
    words = ExpressionWords(
        board,
        phrases={
            "det.every": "all of {subject}",
            "rel.dir.up.exact": "directly above",
            "rel.dir.up_right": "northeast of",
        },
    )
    assert "all of people is directly above" in words.statement(
        parse_statement("every people dir:up Ben = 1")
    )
    assert "all of empty areas is empty" in words.statement(
        parse_statement("every empty areas is empty")
    )
    assert "northeast of" in words.statement(parse_statement("Ada dir:right+up Ben"))
