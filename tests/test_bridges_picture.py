"""Bridges rendering and generic segment metadata use the same geometry."""

import json
from io import BytesIO
from xml.etree import ElementTree

import pytest

pytest.importorskip("fontTools")

from csp import bridges, icons, picture, web
from csp.core import Step

RECTANGLE = """Family: bridges
Size: 3 5
Islands:
2 . . . 2
. . . . .
2 . . . 2
"""
CROSSING = """Family: bridges
Size: 5 7
Islands:
. . . 2 . . .
. . . . . . .
2 . . . . . 2
. . . . . . .
. . . 2 . . 2
"""


def test_bridge_decks_and_island_clues_in_rectangular_svg():
    puzzle = bridges.parse(RECTANGLE)
    name = bridges.pair_name(((0, 0), (0, 4)))
    blank = picture.bridges_picture(puzzle)
    single = picture.bridges_picture(puzzle, {name: 1})
    double = picture.bridges_picture(puzzle, {name: 2})
    assert blank.size == (384, 256)
    assert len(single.to_svg()) > len(blank.to_svg())
    assert len(double.to_svg()) > len(single.to_svg())
    root = ElementTree.fromstring(double.to_svg())
    above = root.find("{*}g[@class='above']")
    assert above is not None
    assert len(above.findall("{*}ellipse")) == len(puzzle.islands) * 2
    assert len(above.findall("{*}g[@aria-label='2']")) == 4
    assert picture.bridges_picture(puzzle, {name: 2}, interactive=True).to_svg() == (
        picture.bridges_picture(puzzle, interactive=True).to_svg()
    )


def test_bridge_step_highlights_only_the_changed_corridor():
    puzzle = bridges.parse(RECTANGLE)
    name = bridges.pair_name(puzzle.pairs[0])
    steps = [Step(var=name, value=1, asserted=True, rule="single", reason="test")]
    image = picture.bridges_picture(puzzle, {name: 1}, steps=steps).to_svg()
    assert "#d18a35" in image
    assert "#d18a35" not in picture.bridges_picture(puzzle, {name: 1}).to_svg()


def test_bridge_registry_icons_and_png_show_distinct_decks():
    assert icons.to_svg("bridge_single") != icons.to_svg("bridge_double")
    pytest.importorskip("resvg_py")
    Image = pytest.importorskip("PIL.Image")
    puzzle = bridges.parse(RECTANGLE)
    name = bridges.pair_name(((0, 0), (0, 4)))
    blank = Image.open(BytesIO(picture.bridges_picture(puzzle).to_png())).convert("RGB")
    one = Image.open(BytesIO(picture.bridges_picture(puzzle, {name: 1}).to_png())).convert("RGB")
    two = Image.open(BytesIO(picture.bridges_picture(puzzle, {name: 2}).to_png())).convert("RGB")
    # A plank-free point in the middle of the water: single deck at centre, two separated decks.
    x, y = 179, 64
    assert one.getpixel((x, y)) != blank.getpixel((x, y))
    assert two.getpixel((x, y)) == blank.getpixel((x, y))
    assert two.getpixel((x, y - 7)) != blank.getpixel((x, y - 7))


def test_bridge_export_has_true_rectangular_size_and_no_cell_oracle():
    puzzle = bridges.parse(CROSSING)
    board = picture.bridges_picture(puzzle, interactive=True).to_svg()
    horizontal = "r3c1-r3c7"
    vertical = "r1c4-r5c4"
    model, _ = bridges.compile_puzzle(CROSSING)
    data = json.loads(
        json.dumps(
            web.bundle(
                CROSSING,
                "bridges",
                "crossing",
                model,
                {horizontal: 2, vertical: 0},
                board,
                "count",
                True,
            )
        )
    )
    assert data["size"] == [5, 7]
    assert data["givens"] == {}
    assert data["rules"] and data["links"]["instructions"]
    assert data["solution"] == {horizontal: "2"}
    segments = {entry["id"]: entry for entry in data["links"]["segments"]}
    assert segments[horizontal]["conflicts"] == [vertical]
    assert segments[vertical]["conflicts"] == [horizontal]
    assert segments[horizontal]["endpoints"] == ["r3c1", "r3c7"]
    assert segments[horizontal]["values"] == ["0", "1", "2"]
    assert segments[horizontal]["target"] == [64, 192, 448, 192]
    assert all("solution" not in segment for segment in segments.values())
    assert {node["id"] for node in data["links"]["nodes"]} == set(web.svg.ids(board))


def test_segment_targets_do_not_skip_intermediate_islands():
    text = RECTANGLE.replace("2 . . . 2", "2 . 2 . 2", 1)
    puzzle = bridges.parse(text)
    board = picture.bridges_picture(puzzle, interactive=True).to_svg()
    data = web._bridges(text, {}, board)
    ids = {segment["id"] for segment in data["links"]["segments"]}
    assert "r1c1-r1c5" not in ids
    assert {"r1c1-r1c3", "r1c3-r1c5"} <= ids


@pytest.mark.parametrize("size", [7, 13])
def test_bridge_large_board_has_scalable_viewport(size):
    text = f"Family: bridges\nSize: {size}\nIslands:\n" + "\n".join(
        " ".join(
            "2" if row in (0, size - 1) and col in (0, size - 1) else "." for col in range(size)
        )
        for row in range(size)
    )
    canvas = picture.bridges_picture(bridges.parse(text), interactive=True)
    assert canvas.size == ((size + 1) * 64, (size + 1) * 64)
    assert "data-compact-view-box" in canvas.to_svg()
