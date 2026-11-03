import pytest

from csp import bruteforce, sudoku
from csp.core import Kind

VARIANTS = """Givens:
. . . .
. . . .
. . . .
. . . .
Kropki:
white r1c1 r1c2
black r1c2 r2c2
Consecutive:
r2c3 r2c4
Thermometers:
r1c1 r2c1 r2c2
AntiKnight:
AntiKing:
"""


def test_sudoku_variants_parse_and_compile_to_existing_primitives():
    puzzle = sudoku.parse(VARIANTS)
    model, _ = sudoku.compile_puzzle(VARIANTS)

    assert puzzle.anti_knight and puzzle.anti_king
    assert len(puzzle.links) == len(model.relations) == 5
    assert any(kind == "anti-knight" for _, _, kind in puzzle.anti_peers())
    assert any(kind == "anti-king" for _, _, kind in puzzle.anti_peers())
    assert all(
        constraint.kind is Kind.AT_MOST_ONE
        for constraint in model.constraints
        if "anti-" in (constraint.family or "")
    )
    assert puzzle.links[0].holds(1, 2) is True
    assert puzzle.links[0].holds(1, 3) is False


@pytest.mark.parametrize(
    ("language", "fragments"),
    [
        (
            "en",
            ["knight's move", "diagonally", "white Kropki", "twice", "bar", "bulb", "Missing dots"],
        ),
        (
            "nl",
            [
                "paardensprong",
                "diagonaal",
                "witte Kropki",
                "tweemaal",
                "streepje",
                "bolletje",
                "Ontbrekende stippen",
            ],
        ),
    ],
)
def test_variant_rules_describe_every_active_constraint(language, fragments):
    from csp.story import family_rules

    text = VARIANTS + f"\nLanguage:\n{language}\n"
    rules = family_rules(text, "sudoku")
    assert len(rules) == 8
    for fragment in fragments:
        assert any(fragment in rule for rule in rules)


def test_plain_sudoku_does_not_get_inactive_variant_rules():
    from csp.story import family_rules

    assert family_rules(". . . .\n" * 4, "sudoku") == [
        "Fill the grid so every row, column and box contains each digit once."
    ]


@pytest.mark.parametrize(
    ("language", "size", "rule", "expected"),
    [
        (
            "en",
            4,
            "sandwich",
            "A number outside the grid belongs to the row or column beside it. Add the digits "
            "between the 1 and the 4 in that line, in whichever order they appear; do not count "
            "the 1 or the 4. A clue of 0 means the 1 and the 4 are adjacent.",
        ),
        (
            "nl",
            6,
            "sandwich",
            "Een getal buiten het rooster hoort bij de rij of kolom waar het naast staat. Tel "
            "de cijfers op die in die lijn tussen de 1 en de 6 staan, in welke volgorde ze ook "
            "voorkomen; de 1 en de 6 zelf tellen niet mee. Bij een getal 0 staan de 1 en de 6 "
            "direct naast elkaar.",
        ),
        (
            "en",
            4,
            "skyscraper",
            "A number outside the grid says how many digits are visible from that side of its "
            "row or column. Read digits as tower heights: a taller digit hides every shorter "
            "one behind it (for example, 2 4 1 3 shows two towers from the left: 2 and 4).",
        ),
        (
            "nl",
            6,
            "skyscraper",
            "Een getal buiten het rooster geeft aan hoeveel cijfers je vanaf die kant van de "
            "rij of kolom ziet. Lees de cijfers als torenhoogtes: een hoger cijfer verbergt elk "
            "lager cijfer erachter (bijvoorbeeld zie je in 2 4 1 3 van links twee torens: 2 en 4).",
        ),
    ],
)
def test_sandwich_and_skyscraper_rules_are_clear_and_use_the_grid_size(
    language, size, rule, expected
):
    from csp.story import family_rules

    givens = "\n".join([". " * (size - 1) + "." for _ in range(size)])
    clue_line = " ".join(["0"] + ["."] * (size - 1))
    section = "SandwichRows" if rule == "sandwich" else "SkyscraperLeft"
    boxes = ""
    if size == 6:
        boxes = "\nBoxes:\n" + "\n".join(
            " ".join(chr(ord("a") + (row // 3) * 3 + col // 2) for col in range(size))
            for row in range(size)
        )
    text = f"Givens:\n{givens}{boxes}\n{section}:\n{clue_line}\nLanguage:\n{language}\n"
    assert expected in family_rules(text, "sudoku")


def test_anti_king_adds_peers_across_jigsaw_regions():
    text = """Givens:
. . . .
. . . .
. . . .
. . . .
Boxes:
a a b b
a c b d
c c d d
a c b d
AntiKing:
"""
    puzzle = sudoku.parse(text)

    assert ((0, 0), (1, 1), "anti-king") in puzzle.anti_peers()


def test_sudoku_variants_require_orthogonal_links():
    text = VARIANTS.replace("white r1c1 r1c2", "white r1c1 r2c2")

    with pytest.raises(ValueError, match="not between neighbouring cells"):
        sudoku.parse(text)


def test_sudoku_brute_force_honors_links_and_anti_peers():
    text = """Givens:
. . . .
. . . .
. . . .
. . . .
Kropki:
white r1c1 r1c2
AntiKnight:
"""
    puzzle = sudoku.parse(text)
    solutions = bruteforce.solutions(text, limit=20)

    assert solutions
    assert all(abs(solution["r1c1"] - solution["r1c2"]) == 1 for solution in solutions)
    assert all(
        solution[sudoku.cell_name(*first)] != solution[sudoku.cell_name(*second)]
        for solution in solutions
        for first, second, _ in puzzle.anti_peers()
    )
