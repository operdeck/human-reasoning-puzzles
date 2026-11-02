import pytest

from csp.puzzlefile import KINDS, detect


@pytest.mark.parametrize(
    "family, kind",
    [
        ("queens", "starbattle"),
        ("suguru", "suguru"),
        ("tectonic", "suguru"),
        ("logicgrid", "logicgrid"),
        ("starbattle", "starbattle"),
        ("binairo", "binairo"),
        ("tango", "binairo"),
        ("tents", "tents"),
        ("minesweeper", "minesweeper"),
        ("akari", "akari"),
        ("lightup", "akari"),
        ("kakurasu", "kakurasu"),
        ("battleships", "battleships"),
        ("towers", "towers"),
        ("skyscrapers", "towers"),
        ("mosaic", "mosaic"),
        ("dominosa", "dominosa"),
        ("rectangles", "rectangles"),
        ("shikaku", "rectangles"),
        ("magnets", "magnets"),
        ("undead", "undead"),
        ("pattern", "pattern"),
        ("nonogram", "pattern"),
        ("picross", "pattern"),
        ("map", "map"),
        ("fourcolour", "map"),
        ("thermometers", "thermometers"),
    ],
)
def test_family_detector_maps_canonical_names_and_aliases(family, kind):
    assert detect(f"Family: {family}\n") == kind
    assert kind in KINDS
