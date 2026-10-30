import pytest

from csp.puzzlefile import KINDS, detect


@pytest.mark.parametrize(
    "family, kind",
    [
        ("queens", "queens"),
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
    ],
)
def test_family_detector_maps_canonical_names_and_aliases(family, kind):
    assert detect(f"Family: {family}\n") == kind
    assert kind in KINDS
