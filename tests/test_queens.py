import pytest

from csp import bruteforce, cli, starbattle
from tests.examples import example


def test_legacy_queens_family_is_a_one_star_starbattle_alias():
    text = example("queens_1_4x4.txt").read_text()
    legacy = (
        text.replace("Family: starbattle", "Family: queens")
        .replace("Stars: 1\n", "")
        .replace(
            "? ? ? ?\n* ? ? ?\n? ? ? ?\n? ? ? ?",
            "b r2c1",
        )
    )

    puzzle = starbattle.parse(legacy)
    assert puzzle.stars == 1
    assert puzzle.icon == "queen"
    assert cli.detect(legacy) == "starbattle"
    assert cli.load(legacy, "queens").kind == "starbattle"
    assert len(bruteforce.solutions(legacy, "queens")) == 1
    assert len(bruteforce.solutions(legacy)) == 1


def test_queens_alias_does_not_accept_a_multi_star_count():
    text = (
        example("queens_1_4x4.txt")
        .read_text()
        .replace("Family: starbattle", "Family: queens")
        .replace("Stars: 1", "Stars: 2")
    )

    with pytest.raises(ValueError, match="alias for Star Battle with Stars: 1"):
        starbattle.parse(text)


@pytest.mark.parametrize("icon", ("queen", "dog", "puppy"))
def test_legacy_queens_alias_preserves_piece_icons(icon):
    text = (
        example("queens_1_4x4.txt")
        .read_text()
        .replace("Family: starbattle", f"Family: queens\nIcon: {icon}")
    )

    assert starbattle.parse(text).icon == icon
