import json

import pytest

from csp.puzzle_lab import family_of, main, rate
from tests.examples import example

pytestmark = pytest.mark.solutions


def test_rating_preserves_display_names_and_rejects_murdoku():
    queens = example("queens_2_5x5.txt").read_text()
    tango = example("tango_2_4x4.txt").read_text()
    assert family_of(queens) == "queens"
    assert family_of(tango) == "tango"
    assert rate(queens).family == "queens"
    assert rate(tango).family == "tango"
    with pytest.raises(ValueError, match="Murdoku"):
        rate(example("wie-doet-het-met-wie-1.txt").read_text())


def test_rating_requires_a_deductive_unique_nontrivial_puzzle():
    result = rate(example("queens_2_5x5.txt").read_text())
    assert result.solved
    assert result.solutions == "unique"
    assert result.tier == "easy"
    assert result.initial_open > 1
    assert result.placements > 0


def test_suguru_small_board_is_not_misrated_by_given_density():
    assert rate(example("suguru_1_4x4.txt").read_text()).tier == "easy"


def test_mostly_prefilled_board_is_trivial():
    import random

    from csp import fresh

    rows = [list(map(str, row)) for row in fresh.binairo_solution(8, random.Random(0))]
    rows[0][3] = rows[7][4] = "."
    text = "Family: binairo\nSize: 8\nGivens:\n" + "\n".join(map(" ".join, rows)) + "\n"
    result = rate(text)
    assert result.initial_open == 2
    assert result.tier == "trivial"


@pytest.mark.parametrize(
    ("filename", "family", "tier"),
    [
        ("binairo_1_8x8.txt", "binairo", "easy"),
        ("binairo_2_8x8.txt", "binairo", "medium"),
        ("queens_6_4x4.txt", "queens", "hard"),
        ("akari_2_8x8.txt", "akari", "hard"),
        ("minesweeper_4_8x8.txt", "minesweeper", "hard"),
        ("minesweeper_3_8x8.txt", "minesweeper", "medium"),
        ("akari_1_6x6.txt", "akari", "medium"),
        ("queens_3_7x7.txt", "queens", "medium"),
        ("tango_5_4x4.txt", "tango", "hard"),
        ("tango_3_4x4.txt", "tango", "medium"),
        ("tango_1_8x8.txt", "tango", "easy"),
        ("tango_4_8x8.txt", "tango", "medium"),
        ("queens_4_8x8.txt", "queens", "medium"),
    ],
)
def test_added_tier_examples_match_repository_ratings(filename, family, tier):
    result = rate(example(filename).read_text())
    assert result.family == family
    assert result.tier == tier
    assert result.solutions == "unique"


def test_search_filters_by_display_family_and_tier(capsys):
    assert main(["search", "examples", "--family", "queens", "--tier", "easy", "--json"]) == 0
    matches = json.loads(capsys.readouterr().out)
    assert [item["family"] for item in matches] == ["queens", "queens"]
    assert {item["path"].split("/")[-1] for item in matches} == {
        "queens_1_4x4.txt",
        "queens_2_5x5.txt",
    }
    assert [item["tier"] for item in matches] == ["easy", "easy"]


def test_rating_says_whether_deduction_alone_closes_the_puzzle():
    """`deductive` separates puzzles the ladder finishes from the what_if frontier."""
    assert rate(example("queens_6_4x4.txt").read_text()).deductive
    fallback = rate(example("tango_5_4x4.txt").read_text())
    assert fallback.grade == "what_if"
    assert not fallback.deductive


def test_rate_command_marks_a_puzzle_that_needs_the_fallback(capsys):
    assert main(["rate", str(example("tango_5_4x4.txt"))]) == 0
    assert "beyond deduction" in capsys.readouterr().out
    assert main(["rate", str(example("queens_6_4x4.txt"))]) == 0
    assert "beyond deduction" not in capsys.readouterr().out


def test_search_can_require_a_strictly_deductive_solution(capsys):
    paths = [str(example(name)) for name in ("tango_5_4x4.txt", "queens_6_4x4.txt")]
    assert main(["search", *paths, "--tier", "hard", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
    assert main(["search", *paths, "--tier", "hard", "--deductive", "--json"]) == 0
    matches = json.loads(capsys.readouterr().out)
    assert [item["path"].split("/")[-1] for item in matches] == ["queens_6_4x4.txt"]
    assert matches[0]["deductive"] is True


def test_generate_is_repeatable_and_writes_only_a_valid_candidate(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    source = "examples/tents_1_8x8.txt"
    args = [
        "generate",
        source,
        "--tier",
        "medium",
        "--seed",
        "5",
        "--attempts",
        "40",
    ]
    assert main([*args, "--output", str(first)]) == 0
    assert main([*args, "--output", str(second)]) == 0
    assert first.read_text() == second.read_text()
    result = rate(first.read_text())
    assert result.solved and result.solutions == "unique" and result.tier == "medium"


def test_generate_refuses_murdoku(tmp_path, capsys):
    output = tmp_path / "should-not-exist.txt"
    assert (
        main(
            [
                "generate",
                str(example("wie-doet-het-met-wie-1.txt")),
                "--tier",
                "easy",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert "Murdoku" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize(
    ("family", "size", "open_share"),
    [
        ("binairo", 6, 0.5),
        ("tango", 6, 0.5),
        ("queens", 5, 0.5),
        ("suguru", 5, 0.5),
        ("sudoku", 4, 0.6),
        ("futoshiki", 5, 0.7),
        ("calcudoku", 4, 0.0),
        ("starbattle", 6, 0.0),
        ("tents", 6, 0.0),
        ("battleships", 4, 0.0),
        ("towers", 4, 0.5),
        ("mosaic", 5, 0.5),
        ("dominosa", 3, 0.5),
        ("rectangles", 6, 0.5),
        ("magnets", 4, 0.5),
        ("undead", 4, 0.5),
        ("pattern", 5, 0.4),
        ("map", 6, 0.6),
    ],
)
def test_fresh_boards_have_their_own_unique_solution(family, size, open_share):
    import random

    from csp import fresh

    text = fresh.fresh(family, size, random.Random(3), open_share)
    assert text is not None
    result = rate(text)
    assert result.family == ("queens" if family == "starbattle" and size < 8 else family)
    assert result.solutions == "unique"
    assert result.tier != "trivial"


def test_sweep_command_counts_grades_and_saves_each_board(tmp_path, capsys):
    args = ["sweep", "dominosa", "--size", "3", "--seed", "1", "--count", "3"]
    assert main([*args, "--save", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    saved = sorted(path.name for path in tmp_path.glob("*.txt"))
    assert out.count("seed ") == len(saved) == 3
    assert all(name.startswith("dominosa_3_") for name in saved)
    assert "easy/" in out.splitlines()[-1]


def test_fresh_command_writes_a_rated_board(tmp_path, capsys):
    out = tmp_path / "binairo.txt"
    args = ["fresh", "binairo", "--size", "6", "--tier", "easy", "--open-share", "0.4"]
    assert main([*args, "--seed", "1", "--attempts", "20", "--output", str(out)]) == 0
    assert rate(out.read_text()).tier == "easy"
    assert "wrote" in capsys.readouterr().out


@pytest.mark.parametrize(
    "size,tier,seed", [(4, "easy", 13804), (5, "easy", 13805), (4, "medium", 138)]
)
def test_fresh_queens_have_no_single_cell_regions(size, tier, seed):
    import random

    from csp import fresh, starbattle

    text = fresh.fresh("queens", size, random.Random(seed), tier=tier)
    assert text is not None
    puzzle = starbattle.parse(text)
    assert puzzle.stars == 1
    assert "Family: starbattle" in text
    assert min(map(len, puzzle.areas.cells_by_region.values())) >= 2
    assert sum(value == 1 for row in puzzle.givens for value in row) == (1 if tier == "easy" else 0)
    assert fresh.is_unique(text)
    assert text == fresh.fresh("queens", size, random.Random(seed), tier=tier)


def test_fresh_minesweeper_command_writes_a_rated_board(tmp_path, capsys):
    out = tmp_path / "minesweeper.txt"
    args = [
        "fresh",
        "minesweeper",
        "--size",
        "5",
        "--tier",
        "medium",
        "--open-share",
        "0.52",
        "--seed",
        "119",
        "--attempts",
        "60",
        "--output",
        str(out),
    ]
    assert main(args) == 0
    result = rate(out.read_text())
    assert result.family == "minesweeper"
    assert result.solutions == "unique"
    assert result.tier == "medium"
    assert "wrote" in capsys.readouterr().out


def test_fresh_akari_command_writes_a_rated_board(tmp_path, capsys):
    out = tmp_path / "akari.txt"
    args = [
        "fresh",
        "akari",
        "--size",
        "6",
        "--tier",
        "medium",
        "--seed",
        "122",
        "--attempts",
        "100",
        "--output",
        str(out),
    ]
    assert main(args) == 0
    result = rate(out.read_text())
    assert result.family == "akari"
    assert result.solutions == "unique"
    assert result.tier == "medium"
    assert "wrote" in capsys.readouterr().out
