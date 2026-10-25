import json

import pytest

from csp.puzzle_lab import family_of, main, rate
from tests.examples import example


def test_rating_preserves_display_names_and_rejects_murdoku():
    dog = example("dogdoku_5x5.txt").read_text()
    tango = example("tango_4x4.txt").read_text()
    assert family_of(dog) == "dogdoku"
    assert family_of(tango) == "tango"
    assert rate(dog).family == "dogdoku"
    assert rate(tango).family == "tango"
    with pytest.raises(ValueError, match="Murdoku"):
        rate(example("murdoku_intro.txt").read_text())


def test_rating_requires_a_deductive_unique_nontrivial_puzzle():
    result = rate(example("dogdoku_5x5.txt").read_text())
    assert result.solved
    assert result.solutions == "unique"
    assert result.tier == "easy"
    assert result.initial_open > 1
    assert result.placements > 0


def test_search_filters_by_display_family_and_tier(capsys):
    assert main(["search", "examples", "--family", "dogdoku", "--tier", "easy", "--json"]) == 0
    matches = json.loads(capsys.readouterr().out)
    assert [item["family"] for item in matches] == ["dogdoku"]
    assert [item["tier"] for item in matches] == ["easy"]


def test_generate_is_repeatable_and_writes_only_a_valid_candidate(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    source = "examples/tents_8x8.txt"
    args = [
        "generate",
        source,
        "--tier",
        "medium",
        "--seed",
        "933",
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
                str(example("murdoku_intro.txt")),
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
