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
        ("en", "Ada is not in area hall", "either Ada is in area hall"),
        ("nl", "Ada is niet in gebied hall", "of Ada is in gebied hall"),
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
        "the keeper is next to an object named bed"
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
        "de bewaker is vlak naast een voorwerp met de naam bed"
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
        ("nl", "point_object:lamp", "Ada is op een vakje dat de lamp raakt"),
        ("nl", "edge_item:window", "Ada is op een vakje dat een raam raakt"),
        ("nl", "mark:red", "Ada is op een vakje met de markering red"),
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
        ("en", "in the hall", "Ada is in area hall"),
        ("nl", "in de hal", "Ada is in gebied hal"),
    ],
)
def test_area_names_accept_existing_location_wordings(board, language, display, expected):
    words = ExpressionWords(board, language, names={"hall": display})
    assert words.statement(parse_statement("Ada in area:hall")) == expected


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
    ("language", "same", "distance", "distinct"),
    [
        ("en", "in the same area as", "area distance", "distinct from the subject"),
        ("nl", "in hetzelfde gebied als", "gebiedsafstand", "verschillend van het onderwerp"),
    ],
)
def test_zero_area_distance_has_an_idiomatic_relation(board, language, same, distance, distinct):
    words = ExpressionWords(board, language)
    assert same in words.statement(parse_statement("Ada dir:areas Ben = 0"))
    assert same in words.statement(parse_statement("count (people dir:areas Ada = 0) = 1"))
    assert distinct in words.statement(parse_statement("Ada dir:areas role:guard = 0"))
    assert distance not in words.statement(parse_statement("Ada dir:areas Ben = 0"))
    assert distance in words.statement(parse_statement("Ada dir:areas Ben >= 0"))
    assert distance in words.statement(parse_statement("Ada dir:areas Ben = 1"))


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
