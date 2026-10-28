"""Tests for the SVG pictures, their PNG rasters and the icon registry. No network needed."""

import socket
from io import BytesIO

import pytest

PIL = pytest.importorskip("PIL")
pytest.importorskip("resvg_py")
from PIL import Image  # noqa: E402

from csp import bruteforce, cli, icons, svg  # noqa: E402
from csp import picture as drawing  # noqa: E402
from csp.murdoku import Board, BoardObject, EdgeItem, PointObject, RoleSpec, Square  # noqa: E402
from csp.puzzlefile import load_board, load_presentation  # noqa: E402
from tests.examples import all_examples, example  # noqa: E402

CELL = 100


def _raster(canvas: svg.Canvas) -> Image.Image:
    return Image.open(BytesIO(canvas.to_png())).convert("RGB")


class _Rasterised:
    """`picture`, but each `*_picture` call gives the PNG raster as a Pillow image."""

    def __getattr__(self, name):
        value = getattr(drawing, name)
        if name.endswith("_picture"):
            return lambda *args, **kwargs: _raster(value(*args, **kwargs))
        return value


picture = _Rasterised()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Rendering never touches the network: every icon is vendored."""

    def refuse(*args, **kwargs):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def fake_emoji(monkeypatch):
    """Swap a vendored picture for a plain block of colour, to find it in the raster."""
    fakes: dict[str, str] = {}
    markup, bounds = svg.emoji_markup, svg.emoji_bounds
    monkeypatch.setattr(svg, "emoji_markup", lambda code: fakes.get(code) or markup(code))
    monkeypatch.setattr(
        svg, "emoji_bounds", lambda: {**bounds(), **dict.fromkeys(fakes, (0, 0, 128, 128))}
    )

    def add(code: str, rgb: tuple[int, int, int]) -> None:
        fakes[code] = f'<rect width="128" height="128" fill="rgb{rgb}"/>'

    return add


def _bluish(pixel):
    """A standable object is drawn faint, so pure blue blends with the region colour."""
    return pixel[2] > pixel[0] + 40 and pixel[2] > pixel[1] + 40


def _centre(image, board, r, c, coordinates=True):
    margin = CELL // 2 if coordinates else CELL // 6
    return image.getpixel((margin + c * CELL + CELL // 2, margin + r * CELL + CELL // 4))


def test_icon_names_map_to_code_points():
    assert icons.code_for("koffer") == icons.code_for("Suitcase") == "1f9f3"
    assert icons.code_for("boom2") == icons.code_for("boom") == "1f333"
    assert icons.code_for("kruik") == "1f3fa"
    assert icons.code_for("paard") == "1f40e"
    assert icons.code_for("ton") == icons.code_for("barrel") == "1f6e2"
    assert icons.code_for("stoel") == icons.code_for("chair")
    assert icons.code_for("window") == "1fa9f"
    assert icons.code_for("zeppelin") is None
    assert len(icons.NOTO_COMMIT) == 40


def test_every_catalogue_picture_is_vendored():
    missing = sorted(
        name for name, code in icons.CATALOGUE.items() if svg.emoji_markup(code) is None
    )
    assert missing == []
    assert set(svg.emoji_bounds()) >= set(icons.CATALOGUE.values())


def test_object_names_keep_their_catalogue_meaning():
    # The family registry's "tree" (Tents) is a fir; a Murdoku tree stays deciduous.
    assert icons.lookup("tree").emoji == "1f332"
    assert icons.object_icon("tree").emoji == "1f333"
    assert icons.object_icon("rug2").name == "carpet"
    assert icons.object_icon("bedieningspaneel").name == "control_panel"
    assert icons.object_icon("kruk").name == "stool"
    assert icons.object_icon("table").name == "table"
    assert icons.object_icon("reception_counter").name == "counter"
    assert icons.object_icon("staircase").name == "staircase"
    assert icons.object_icon("elevator_car").name == "elevator"
    assert icons.object_icon("wall").name == "wall"
    assert icons.object_icon("tweepersoonsbed").name == "double_bed"
    assert icons.object_icon("badjas").name == "bathrobe"
    assert icons.object_icon("sloffen").name == "slippers"
    assert icons.object_icon("zeppelin") is None


def test_double_bed_uses_a_single_top_down_icon_across_its_footprint(monkeypatch):
    bed = BoardObject(
        "tweepersoonsbed",
        "standable",
        (Square(0, 0), Square(0, 1), Square(1, 0), Square(1, 1)),
    )
    board = Board(2, [["a", "a"], ["a", "a"]], {"a": "room"}, [bed], ["A", "B"])
    calls = []

    def capture(canvas, name, area, cell, **kwargs):
        calls.append((name, area, kwargs))

    monkeypatch.setattr(drawing, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False, legend=False)

    margin = CELL // 6
    assert len(calls) == 1
    name, area, options = calls[0]
    assert name == "tweepersoonsbed"
    assert area == (margin, margin, margin + 2 * CELL, margin + 2 * CELL)
    assert options["stretch"] is True
    assert icons.object_icon(name).markup == icons.DOUBLE_BED


def test_attribute_icons_and_holders_appear_in_the_legend(monkeypatch):
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "room"},
        [],
        ["Ada", "Ben"],
        attributes={"badjas": frozenset({"Ada"}), "sloffen": frozenset({"Ben"})},
    )
    calls = []
    original = drawing._icon

    def capture(canvas, name, area, cell, **kwargs):
        calls.append(name)
        original(canvas, name, area, cell, **kwargs)

    monkeypatch.setattr(drawing, "_icon", capture)
    image = drawing.murdoku_picture(board, cell=CELL)

    assert calls == ["badjas", "sloffen"]
    markup = image.to_svg()
    assert "Badjas: Ada" in markup
    assert "Sloffen: Ben" in markup


def test_an_attribute_without_a_picture_is_named_only_once_in_the_legend():
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "room"},
        [],
        ["Ada", "Ben"],
        attributes={"guest_in_costume": frozenset({"Ada"})},
    )

    markup = drawing.murdoku_picture(board, cell=CELL).to_svg()

    assert "Guest in costume: Ada" in markup
    assert 'aria-label="guest_"' not in markup


def test_the_area_tag_legend_keeps_the_case_of_region_names():
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "El_Greco_room"},
        [],
        ["Ada", "Ben"],
        area_tags={"crime_scene": ["El_Greco_room"]},
    )

    markup = drawing.murdoku_picture(board, cell=CELL).to_svg()

    assert "Crime scene: El Greco room" in markup


@pytest.mark.parametrize(
    ("name", "panel_row", "window_row"),
    [
        ("murdoku_orient_express.txt", 4, 3),
        ("murdoku_orient_express_2.txt", 5, 4),
        ("murdoku_orient_express_3.txt", 4, 4),
    ],
)
def test_vertical_control_panel_rotates_to_match_its_footprint(
    monkeypatch, name, panel_row, window_row
):
    board, _ = load_board(example(name).read_text())
    calls = []
    original = drawing._icon

    def capture(canvas, name, area, cell, **kwargs):
        if name == "bedieningspaneel":
            calls.append((area, kwargs.get("rotate", 0)))
        original(canvas, name, area, cell, **kwargs)

    monkeypatch.setattr(drawing, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, legend=False)

    stool = next(obj for obj in board.objects if obj.name == "kruk")
    assert stool.kind == "standable" and stool.squares == (Square(4, 1),)
    row = panel_row - 1
    expected_area = (
        CELL // 2,
        CELL // 2 + row * CELL,
        CELL // 2 + CELL,
        CELL // 2 + (row + 2) * CELL,
    )
    assert calls == [(expected_area, 90)]
    front_windows = {
        item.cells[0].row + 1
        for item in board.edge_items
        if item.kind == "window" and item.side == "left" and item.cells[0].col == 0
    }
    assert front_windows == set(range(window_row, window_row + 4))


@pytest.mark.parametrize("name", sorted(icons.REGISTRY))
def test_every_registry_icon_renders(name):
    icon = icons.REGISTRY[name]
    assert icon.unicode and icons.symbol(name) == icon.unicode
    image = Image.open(BytesIO(icons.png(name, 48))).convert("RGBA")
    assert image.size == (48, 48)
    assert image.getchannel("A").getbbox() is not None


def test_registry_icons_take_a_tint():
    red = icons.to_svg("star", 32, tint=(200, 0, 0))
    assert red is not None and 'color="#c80000"' in red
    colours = Image.open(BytesIO(svg.rasterise(red))).convert("RGBA").getcolors(32 * 32)
    assert any(r > 150 and g < 60 and b < 60 and a == 255 for _, (r, g, b, a) in colours)


def test_text_is_drawn_as_paths_from_the_bundled_font():
    from csp import sudoku

    canvas = drawing.sudoku_picture(sudoku.parse((example("sudoku_1_4x4.txt")).read_text()))
    text = canvas.to_svg()
    assert "<text" not in text and "aria-label" in text


def test_every_character_in_the_example_pictures_is_in_the_bundled_font():
    # Missing glyphs would print as empty boxes; svg.SUBSTITUTES covers signs
    # such as the minus that Noto Sans lacks.
    import html
    import re

    from csp.puzzlefile import detect

    font = svg.font()
    for path in all_examples():
        text = path.read_text()
        markup = cli.make_image(detect(text), text).to_svg()
        for label in re.findall(r'aria-label="([^"]*)"', markup):
            missing = {c for c in html.unescape(label) if font.glyph(c) == ".notdef"}
            assert not missing, (path.name, label, missing)
    assert font.glyph("\u2212") != ".notdef"


def test_interactive_variant_has_cell_ids_and_no_solution():
    from csp import sudoku

    text = (example("sudoku_1_4x4.txt")).read_text()
    grid = sudoku.parse(text)
    (solution,) = bruteforce.solutions(text)
    interactive = drawing.sudoku_picture(grid, solution, interactive=True)
    blank = drawing.sudoku_picture(grid)
    cells = {f"r{r}c{c}" for r in range(1, 5) for c in range(1, 5)}
    assert cells <= set(svg.ids(interactive.to_svg()))
    assert _raster(interactive).tobytes() == _raster(blank).tobytes()


def test_interactive_murdoku_has_cell_ids_and_the_blank_board():
    text = (example("tamagotchi-murdoku-9x9.txt")).read_text()
    board, _ = load_board(text)
    canvas = drawing.murdoku_picture(board, legend=False, interactive=True)
    assert "r1c1" in svg.ids(canvas.to_svg())
    blank = drawing.murdoku_picture(board, legend=False)
    assert _raster(canvas).tobytes() == _raster(blank).tobytes()


def test_two_square_standable_object_is_stretched_across_both_squares(fake_emoji):
    fake_emoji("1f6cf", (0, 0, 255))  # a blue block
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [BoardObject("bed", "standable", (Square(1, 0), Square(1, 1)))],
        ["A", "B"],
    )  # fmt: skip
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False, labels=False)
    margin = CELL // 6
    row = margin + CELL + CELL // 2
    blue = [x for x in range(image.width) if _bluish(image.getpixel((x, row)))]
    assert blue[0] < margin + CELL // 4 and blue[-1] > margin + 2 * CELL - CELL // 4


def test_two_square_bench_keeps_its_proportions_and_is_not_stretched(fake_emoji):
    fake_emoji("1f6cb", (0, 0, 255))  # a blue block
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [BoardObject("bank", "standable", (Square(1, 0), Square(1, 1)))],
        ["A", "B"],
    )  # fmt: skip
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False, labels=False)
    margin = CELL // 6
    row = margin + CELL + CELL // 2
    blue = [x for x in range(image.width) if _bluish(image.getpixel((x, row)))]
    # A square icon keeps its shape: about one square wide, not stretched across both.
    assert blue and blue[-1] - blue[0] < CELL


def test_two_square_blocking_object_uses_one_spanning_icon(monkeypatch):
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [BoardObject("crate", "blocking", (Square(0, 0), Square(0, 1)))],
        ["A", "B"],
    )
    calls = []

    def capture(canvas, name, area, cell, **kwargs):
        calls.append((name, area, kwargs))

    monkeypatch.setattr(drawing, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False)

    assert len(calls) == 1
    name, area, options = calls[0]
    assert name == "crate" and area[2] - area[0] == 2 * CELL
    assert options["stretch"] is True


def test_adjacent_chairs_render_as_separate_single_cell_icons(monkeypatch):
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [
            BoardObject("stoel", "standable", (Square(0, 0),)),
            BoardObject("stoel", "standable", (Square(1, 0),)),
        ],
        ["A", "B"],
    )  # fmt: skip
    calls = []

    def capture(canvas, name, area, cell, **kwargs):
        calls.append((name, area, kwargs))

    monkeypatch.setattr(drawing, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert len(calls) == 2
    assert all(name == "stoel" and area[2] - area[0] == CELL for name, area, _ in calls)
    assert all(area[3] - area[1] == CELL for _, area, _ in calls)


def test_edge_items_and_point_objects_render_at_their_anchors(monkeypatch):
    board = Board(
        3,
        [["west", "east", "east"], ["west", "east", "east"], ["west", "east", "east"]],
        {"west": "west", "east": "east"},
        [],
        ["A", "B"],
        edge_items=[
            EdgeItem("gate", "door", (Square(0, 0), Square(0, 1))),
            EdgeItem("window", "window", (Square(2, 2),)),
        ],
        point_objects=[PointObject.at("fountain", (3, 3), 3)],
    )
    calls = []

    def capture(canvas, name, area, cell, **kwargs):
        calls.append((name, area))

    monkeypatch.setattr(drawing, "_icon", capture)
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False, legend=False)
    margin = CELL // 6

    assert image.getpixel((margin + CELL, margin + CELL // 2)) == (117, 75, 47)
    assert calls == [
        ("window", (margin + 2 * CELL, margin + 2 * CELL, margin + 3 * CELL, margin + 3 * CELL)),
        (
            "fountain",
            (
                margin + CELL - CELL // 3,
                margin + CELL - CELL // 3,
                margin + CELL + CELL // 3,
                margin + CELL + CELL // 3,
            ),
        ),
    ]
    with_legend = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert with_legend.height > image.height
    assert picture.unknown_object_icons(board) == []
    assert len(board.free) == 9


def _point_board(*points):
    return Board(
        3,
        [["west", "east", "east"], ["west", "east", "east"], ["west", "east", "east"]],
        {"west": "west", "east": "east"},
        [],
        ["A"],
        point_objects=[PointObject.at(name, anchor, 3) for name, anchor in points],
    )


@pytest.mark.parametrize("coordinates", [False, True])
def test_point_objects_on_the_board_edge_are_centred_and_not_clipped(monkeypatch, coordinates):
    board = _point_board(("mouse1", (1, 4)), ("mouse2", (7, 1)), ("cheese", (7, 4)))
    calls = []

    def capture(canvas, name, area, cell, **kwargs):
        calls.append((name, area, kwargs.get("scale", 0.72)))

    monkeypatch.setattr(drawing, "_icon", capture)
    image = picture.murdoku_picture(board, cell=CELL, coordinates=coordinates, legend=False)
    margin = (image.width - 3 * CELL) // 2
    anchors = {"mouse1": (margin + 3 * CELL // 2, margin), "mouse2": (margin, margin + 3 * CELL),
               "cheese": (margin + 3 * CELL // 2, margin + 3 * CELL)}  # fmt: skip

    assert {name for name, _, _ in calls} == set(anchors)
    for name, (x0, y0, x1, y1), scale in calls:
        assert ((x0 + x1) / 2, (y0 + y1) / 2) == anchors[name]
        reach = (x1 - x0) * scale / 2
        assert reach < CELL // 2  # smaller than an in-cell object
        assert x0 + (x1 - x0) / 2 - reach >= 0 and y1 - (y1 - y0) / 2 + reach <= image.width
        if coordinates and y0 < margin:
            assert margin - reach > margin / 2 + CELL // 10  # clear of the column numbers
    assert picture.unknown_object_icons(board) == []


def test_interior_point_objects_keep_the_plain_margin():
    plain = picture.murdoku_picture(_point_board(), cell=CELL, coordinates=False, legend=False)
    inner = picture.murdoku_picture(
        _point_board(("fountain", (3, 3))), cell=CELL, coordinates=False, legend=False
    )
    assert inner.width == plain.width == 3 * CELL + 2 * (CELL // 6)


def test_point_object_without_an_icon_renders_a_badge(monkeypatch):
    board = _point_board(("zorblax", (1, 1)))
    texts = []
    original = drawing._centred_text

    def capture(canvas, text, area, size, colour, max_width=None):
        texts.append((text, size))
        original(canvas, text, area, size, colour, max_width=max_width)

    monkeypatch.setattr(drawing, "_centred_text", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False, legend=False)

    assert ("zor", max(8, CELL // 8)) in texts
    assert picture.unknown_object_icons(board) == ["zorblax"]


def test_overlapping_marks_render_badges_and_condition_labels():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Marks:
quiet: r1c1 ; alone
social: r1c1 ; not_alone
"""
    board, _ = load_board(text)
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    margin = CELL // 6
    pad = max(3, CELL // 24)
    assert image.getpixel((margin + pad + 5, margin + pad + 5)) == picture.MARK_FILL
    assert picture._Legend(board, CELL).mark_names == ["quiet", "social"]
    assert image.height > 2 * CELL + 2 * margin


def test_png_legend_lists_role_membership_states():
    board = Board(
        3,
        [["a"] * 3 for _ in range(3)],
        {"a": "room"},
        [],
        ["A", "B", "C"],
        roles=[RoleSpec("bandit", frozenset({1}))],
    )
    states = {("A", "bandit"): True, ("B", "bandit"): False, ("C", "bandit"): None}
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False, role_statuses=states)
    legend = picture._Legend(board, CELL, states)

    assert legend.role_names == ["bandit"]
    assert image.height > 3 * CELL + CELL // 3


def test_cli_initial_png_receives_compile_time_role_states(tmp_path, monkeypatch):
    from csp import cli

    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Roles:
bandit: any
Rules:
has_role A bandit
not_role B bandit
"""
    puzzle = tmp_path / "roles.txt"
    target = tmp_path / "roles.png"
    puzzle.write_text(text)
    seen = []
    original = drawing.murdoku_picture

    def capture(board, placed=None, **kwargs):
        seen.append(kwargs.get("role_statuses"))
        return original(board, placed, **kwargs)

    monkeypatch.setattr(drawing, "murdoku_picture", capture)
    cli.main([str(puzzle), "--png", str(target)])

    assert seen
    assert seen[0] == {("A", "bandit"): True, ("B", "bandit"): False}
    assert target.exists()


def test_png_global_count_legend_highlights_scope_and_cli_passes_counts(tmp_path, monkeypatch):
    from csp import cli, murdoku

    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
Objects:
bed: standable r1c1
People:
Ada
Ben
Clues:
count people on object:bed = 1
"""
    board, clues = load_board(text)
    (condition,) = murdoku.global_count_conditions(board, clues)
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False, global_counts=[condition])
    tiny = picture.murdoku_picture(board, cell=12, coordinates=False, global_counts=[condition])
    plain = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    margin = CELL // 6
    assert image.height > plain.height
    assert tiny.width > 0 and tiny.height > 0
    assert image.getpixel((margin + 1, margin + 1)) == picture.COUNT_SCOPE

    puzzle = tmp_path / "global-count.txt"
    target = tmp_path / "global-count.png"
    puzzle.write_text(text)
    seen = []
    original = drawing.murdoku_picture

    def capture(board, placed=None, **kwargs):
        seen.append(kwargs.get("global_counts"))
        return original(board, placed, **kwargs)

    monkeypatch.setattr(drawing, "murdoku_picture", capture)
    cli.main([str(puzzle), "--png", str(target)])

    assert seen and seen[0]
    assert target.exists()


def test_vertical_bed_icon_is_rotated(monkeypatch):
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [BoardObject("bed", "standable", (Square(0, 0), Square(1, 0)))],
        ["A", "B"],
    )  # fmt: skip
    rotations = []

    def capture(canvas, name, area, cell, **kwargs):
        rotations.append(kwargs.get("rotate", 0))

    monkeypatch.setattr(drawing, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert rotations == [90]


def test_custom_carpet_and_well_icons_draw_distinct_images():
    carpet = Image.open(BytesIO(icons.png("carpet", 121))).convert("RGB")
    assert carpet.getpixel((60, 60)) == (156, 58, 45)

    well = Image.open(BytesIO(icons.png("well", 121))).convert("RGB")
    assert carpet.tobytes() != well.tobytes()
    assert well.getpixel((45, 84)) == (45, 65, 70)


def test_couch_icon_loses_its_floor_lamp():
    couch = svg.emoji_markup("1f6cb")
    assert couch is not None
    assert "#FFD600" not in couch.upper() and "#FFFF8D" not in couch.upper()
    _, y0, _, _ = svg.emoji_bounds()["1f6cb"]
    assert y0 > 20  # nothing sticks up above the backrest any more


def test_picture_shows_regions_objects_and_borders():
    text = (example("prrrdoku3.txt")).read_text()
    board, _ = load_board(text)
    image = picture.murdoku_picture(board, cell=CELL)
    margin = CELL // 2
    assert image.width == 2 * margin + 9 * CELL

    moestuin = picture._rgb(board.colours["c"])
    assert _centre(image, board, 3, 5)[:3] == moestuin  # r4c6, plain moestuin
    kas = _centre(image, board, 4, 5)  # r5c6 holds the kas: darker shade
    assert sum(kas[:3]) < sum(moestuin)

    def pixel_on_line(x, y):
        return image.getpixel((margin + x, margin + y))

    # r1c4|r1c5 are both Helmholtzstraat now: thin white line. r1c5|r1c6: thick dark.
    assert pixel_on_line(4 * CELL, CELL // 2) == (255, 255, 255)
    assert sum(pixel_on_line(5 * CELL, CELL // 2)) < 100


def test_without_legend_the_picture_is_square():
    board, _ = load_board((example("prrrdoku3.txt")).read_text())
    with_legend = picture.murdoku_picture(board, cell=CELL)
    without = picture.murdoku_picture(board, cell=CELL, legend=False)
    assert without.width == without.height == with_legend.width < with_legend.height


def test_hatching_only_on_hatched_regions():
    board, _ = load_board((example("prrrdoku3.txt")).read_text())
    image = picture.murdoku_picture(board, cell=CELL, labels=False)
    margin = CELL // 2

    def colours(r, c):
        x0, y0 = margin + c * CELL + 10, margin + r * CELL + 10
        return {image.getpixel((x, y)) for x in range(x0, x0 + 60) for y in range(y0, y0 + 60)}

    assert len(colours(8, 0)) > 1  # water (hatched)
    assert len(colours(5, 7)) == 1  # klimgebied zuid (plain)


def test_solution_picture_puts_name_tags_on_squares():
    text = (example("prrrdoku3.txt")).read_text()
    board, _ = load_board(text)
    (solution,) = bruteforce.solutions(text, "murdoku")
    image = picture.murdoku_picture(board, solution, cell=CELL)
    tim = solution["Tim"]
    margin = CELL // 2
    tag = image.getpixel((margin + tim.col * CELL + 20, margin + tim.row * CELL + CELL // 2))
    assert tag == (255, 255, 255)


def test_default_palette_when_no_colours_given():
    board = Board(2, [["a", "b"], ["a", "b"]], {"a": "here", "b": "there"}, [], ["A", "B"])
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False, labels=False)
    assert _centre(image, board, 0, 0, coordinates=False)[:3] == picture._rgb(picture.PALETTE[0])
    assert _centre(image, board, 0, 1, coordinates=False)[:3] == picture._rgb(picture.PALETTE[1])


def test_unknown_object_gets_a_text_label():
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [BoardObject("zeppelin", "blocking", (Square(0, 0),))],
        ["A", "B"],
    )
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    margin = CELL // 6
    square = image.crop((margin, margin, margin + CELL, margin + CELL))
    pixels = square.load()
    dark = sum(1 for x in range(CELL) for y in range(CELL) if sum(pixels[x, y][:3]) < 150)
    assert dark > 20  # the word is drawn
    assert picture.unknown_object_icons(board) == ["zeppelin"]


def test_png_warns_when_an_object_icon_is_missing(tmp_path, capsys):
    from csp import cli

    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
Objects:
zeppelin: blocking r1c1
People:
A
B
"""
    target = tmp_path / "puzzle.png"

    assert cli.write_picture("murdoku", text, target)
    assert target.exists()
    assert "warning: no icon for zeppelin; using text labels" in capsys.readouterr().err


def test_bad_region_colour_is_rejected():
    text = "Size: 2\nRegions:\na: here #12345\nGrid:\na a\na a\nPeople:\nA\nB\n"
    with pytest.raises(ValueError, match="colour"):
        load_board(text)


def test_cli_png_defaults_to_puzzle_stem(tmp_path, capsys):
    from csp import cli

    puzzle = tmp_path / "default.txt"
    puzzle.write_text(
        """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
Ada
Ben
Clues:
in_row Ada 1
in_column Ada 1
in_row Ben 2
in_column Ben 2
"""
    )
    target = tmp_path / "default.png"

    assert cli.main([str(puzzle), "--png"]) == 0
    assert target.exists()
    assert (tmp_path / "default-solution.png").exists()


def test_cli_svg_writes_board_and_solution_beside_the_puzzle(tmp_path):
    puzzle = tmp_path / "tents.txt"
    puzzle.write_text((example("tents_3_4x4.txt")).read_text())
    assert cli.main([str(puzzle), "--svg"]) == 0
    board, solved = tmp_path / "tents.svg", tmp_path / "tents-solution.svg"
    assert board.read_text().startswith("<svg") and solved.read_text().startswith("<svg")
    assert not (tmp_path / "tents.png").exists()


def test_cli_interactive_svg_has_cell_ids_and_no_solution(tmp_path):
    target = tmp_path / "game.svg"
    assert cli.main([str(example("prrrdoku1.txt")), "--svg", str(target), "--interactive"]) == 0
    assert "r1c1" in svg.ids(target.read_text())
    assert [path.name for path in tmp_path.iterdir()] == ["game.svg"]


def test_cli_interactive_needs_svg(tmp_path):
    with pytest.raises(SystemExit):
        cli.main([str(example("tents_3_4x4.txt")), "--interactive"])


def test_cli_png_writes_board_and_solution(tmp_path, capsys):
    from csp import cli

    target = tmp_path / "board.png"
    assert cli.main([str(example("prrrdoku1.txt")), "--png", str(target)]) == 0
    assert target.exists() and (tmp_path / "board-solution.png").exists()
    for name in ("sudoku_1_4x4.txt", "calcudoku_1_4x4.txt"):
        target = tmp_path / f"{name}.png"
        assert cli.main([str(example(name)), "--png", str(target)]) == 0
        assert target.exists() and target.with_stem(f"{target.stem}-solution").exists()


# --- sudoku and calcudoku -------------------------------------------------


def _middle(r, c):
    margin = CELL // 2
    return margin + c * CELL + CELL // 2, margin + r * CELL + int(CELL * 0.56)


def _has(image, r, c, colour):
    """Whether any pixel near the middle of cell (r, c) is close to `colour`."""
    x, y = _middle(r, c)
    return any(
        sum(abs(a - b) for a, b in zip(image.getpixel((x + dx, y + dy)), colour, strict=True)) < 60
        for dx in range(-15, 16)
        for dy in range(-15, 16)
    )


def test_sudoku_picture_shows_givens_in_ink_and_solved_numbers_in_blue():
    from csp import sudoku

    text = (example("sudoku_1_4x4.txt")).read_text()
    grid = sudoku.parse(text)
    (solution,) = bruteforce.solutions(text)
    image = picture.sudoku_picture(grid, solution, cell=CELL)
    assert image.size == (5 * CELL, 5 * CELL)
    assert _has(image, 0, 3, picture.INK) and not _has(image, 0, 3, picture.SOLVED)
    assert _has(image, 0, 0, picture.SOLVED) and not _has(image, 0, 0, picture.INK)
    blank = picture.sudoku_picture(grid, cell=CELL)
    assert not _has(blank, 0, 0, picture.SOLVED)


def test_sudoku_variant_picture_marks_kropki_and_thermometer_links():
    from csp import sudoku

    text = """Givens:
. . . .
. . . .
. . . .
. . . .
Kropki:
black r1c1 r1c2
Thermometers:
r2c1 r2c2
"""
    puzzle = sudoku.parse(text)
    image = picture.sudoku_picture(puzzle, cell=CELL)
    margin = CELL // 2

    assert image.getpixel((margin + CELL, margin + CELL // 2)) == picture.INK
    thermometer = image.getpixel((margin + CELL, margin + CELL + CELL // 2))
    assert thermometer != picture.WHITE and thermometer != picture.INK


def test_sudoku_picture_shades_alternate_boxes():
    from csp import sudoku

    grid = sudoku.parse((example("sudoku_1_4x4.txt")).read_text())
    image = picture.sudoku_picture(grid, cell=CELL)
    corner = lambda r, c: image.getpixel((CELL // 2 + c * CELL + 8, CELL // 2 + r * CELL + 8))  # noqa: E731
    assert corner(0, 0) == corner(2, 2) == picture.WHITE
    assert corner(0, 2) == corner(2, 0) != picture.WHITE


def _corner(image, r, c):
    return image.getpixel((CELL // 2 + c * CELL + 8, CELL // 2 + r * CELL + 8))


def test_jigsaw_picture_colours_touching_boxes_apart():
    from csp import sudoku

    puzzle = sudoku.parse((example("sudoku_12_6x6_jigsaw.txt")).read_text())
    image = picture.sudoku_picture(puzzle, cell=CELL)
    boxes = puzzle.boxes
    for r in range(6):
        for c in range(5):
            same = boxes[r][c] == boxes[r][c + 1]
            assert (_corner(image, r, c) == _corner(image, r, c + 1)) == same, (r, c)


def test_x_sudoku_picture_greys_the_diagonals():
    from csp import sudoku

    puzzle = sudoku.parse((example("sudoku_8_9x9_x.txt")).read_text())
    image = picture.sudoku_picture(puzzle, cell=CELL)
    assert _corner(image, 0, 0) == _corner(image, 0, 8) == _corner(image, 4, 4) == picture.EXTRA
    assert _corner(image, 0, 1) != picture.EXTRA


def test_nrc_sudoku_picture_greys_the_extra_boxes():
    from csp import sudoku

    puzzle = sudoku.parse((example("sudoku_6_9x9_nrc.txt")).read_text())
    image = picture.sudoku_picture(puzzle, cell=CELL)
    assert _corner(image, 1, 1) == _corner(image, 7, 7) == picture.EXTRA
    assert _corner(image, 0, 0) == _corner(image, 4, 4) == picture.WHITE


def test_futoshiki_picture_points_each_sign_at_the_smaller_cell():
    from csp import futoshiki

    puzzle = futoshiki.parse("Grid:\n" + ". . . .\n" * 4 + "Signs:\nr1c2 < r1c1\n")
    image = picture.futoshiki_picture(puzzle, cell=CELL)
    edge, middle = CELL // 2 + CELL, CELL // 2 + CELL // 2
    arm = CELL // 9
    assert image.getpixel((edge + arm // 2, middle)) == picture.INK  # the tip, in r1c2
    assert image.getpixel((edge - arm // 2, middle)) == picture.WHITE  # open towards r1c1


def test_queens_picture_shows_regions_and_solution():
    from csp import queens

    text = (example("queens_4_4x4.txt")).read_text()
    puzzle = queens.parse(text)
    (solution,) = bruteforce.solutions(text)
    image = picture.queens_picture(puzzle, solution, cell=CELL)

    assert image.size == (5 * CELL, 5 * CELL)
    assert _corner(image, 0, 0) == _corner(image, 1, 0)
    assert _corner(image, 0, 2) != _corner(image, 0, 3)
    assert _has(image, 0, 1, picture.SOLVED)
    crown_x = CELL // 2 + CELL + CELL // 2
    crown_y = CELL // 2 + CELL // 8
    assert image.getpixel((crown_x, crown_y)) == picture.SOLVED


def test_logicgrid_unsolved_picture_includes_clues():
    from csp import logicgrid

    puzzle = logicgrid.parse((example("logicgrid_1_3x3.txt")).read_text())
    image = picture.logicgrid_picture(puzzle, cell=48)
    table_height = sum(len(items) + 1 for items in puzzle.categories.values()) * 24

    assert image.height > table_height
    assert image.getbbox() is not None


def test_starbattle_picture_distinguishes_given_and_solved_stars():
    from csp import starbattle

    base = (example("starbattle_2_8x8.txt")).read_text()
    (first,) = bruteforce.solutions(base)
    given = next(name for name, star in first.items() if star)
    size = starbattle.parse(base).size
    rows = [
        " ".join("*" if starbattle.cell_name((row, col)) == given else "?" for col in range(size))
        for row in range(size)
    ]
    text = base + "Givens:\n" + "\n".join(rows) + "\n"
    puzzle = starbattle.parse(text)
    (solution,) = bruteforce.solutions(text)
    image = picture.starbattle_picture(puzzle, solution, cell=CELL)
    given_row, given_col = (int(x) - 1 for x in given[1:].split("c"))
    solved_row, solved_col = next(
        (row, col)
        for row in range(puzzle.size)
        for col in range(puzzle.size)
        if solution[starbattle.cell_name((row, col))] and puzzle.givens[row][col] != 1
    )

    assert _has(image, given_row, given_col, picture.INK)
    assert _has(image, solved_row, solved_col, picture.SOLVED)


@pytest.mark.parametrize(
    "name",
    [
        "sudoku_9_4x4_kropki.txt",
        "sudoku_2_4x4_anti.txt",
        "sudoku_16_6x6_antiking.txt",
        "suguru_1_4x4.txt",
        "starbattle_2_8x8.txt",
        "logicgrid_1_3x3.txt",
        "binairo_3_4x4.txt",
        "tango_2_4x4.txt",
        "tents_3_4x4.txt",
        "minesweeper_2_5x5.txt",
        "akari_1_6x6.txt",
        "kakurasu_1_4x4.txt",
        "battleships_1_4x4_counts.txt",
    ],
)
def test_family_png_cli_writes_nonblank_solution(name, tmp_path):
    text = (example(name)).read_text()
    kind = cli.detect(text)
    (solution,) = bruteforce.solutions(text, kind)
    path = tmp_path / f"{name}.png"

    assert cli.write_picture(kind, text, path, solution)
    image = Image.open(path).convert("RGB")
    assert image.width > 0 and image.height > 0
    assert image.getbbox() is not None


@pytest.mark.parametrize("filename", ["tango_2_4x4.txt", "tango_5_4x4.txt"])
def test_tango_picture_marks_equal_and_different_signs(filename):
    from csp import binairo

    text = example(filename).read_text()
    puzzle = binairo.parse(text)
    assert {sign.kind for sign in puzzle.signs} == {"equal", "different"}
    (solution,) = bruteforce.solutions(text)
    image = picture.binairo_picture(puzzle, solution, cell=CELL)
    margin = CELL // 2

    for sign in puzzle.signs:
        first_row, first_col = sign.first
        second_row, second_col = sign.second
        if first_row == second_row:
            x = margin + max(first_col, second_col) * CELL
            y = margin + first_row * CELL + CELL // 2
        else:
            x = margin + first_col * CELL + CELL // 2
            y = margin + max(first_row, second_row) * CELL
        badge = image.crop((x - 15, y - 15, x + 16, y + 16))
        assert any(
            badge.getpixel((x, y)) == picture.INK
            for x in range(badge.width)
            for y in range(badge.height)
        )


def test_touching_calcudoku_cages_never_share_a_colour():
    from csp import calcudoku

    for name in ("calcudoku_1_4x4.txt", "calcudoku_5_7x7.txt"):
        puzzle = calcudoku.parse((example(name)).read_text())
        fills = picture._cage_fills(puzzle)
        at = puzzle.cage_at
        for (r, c), cage in at.items():
            for nb in ((r, c + 1), (r + 1, c)):
                if nb in at and at[nb] is not cage:
                    assert fills[at[nb]] != fills[cage], (name, (r, c), nb)


def test_calcudoku_picture_writes_each_cage_target_in_its_first_cell():
    from csp import calcudoku

    puzzle = calcudoku.parse((example("calcudoku_1_4x4.txt")).read_text())
    image = picture.calcudoku_picture(puzzle, cell=CELL)
    for cage in puzzle.cages:
        r, c = min(cage.cells)
        x, y = CELL // 2 + c * CELL, CELL // 2 + r * CELL
        label = image.crop((x + 8, y + 6, x + CELL // 2, y + CELL // 3))
        assert label.convert("L").getextrema()[0] < 60, cage.label


def test_walls_do_not_poke_into_cells():
    """Where a cage wall ends against a thin line, no ink spills past it."""
    from csp import calcudoku

    puzzle = calcudoku.parse((example("calcudoku_1_4x4.txt")).read_text())
    image = picture.calcudoku_picture(puzzle, cell=CELL)
    x, y = CELL // 2 + 2 * CELL, CELL // 2 + CELL  # top-left corner of r2c3
    corner = image.crop((x - 10, y - 10, x - 3, y - 3))
    assert corner.convert("L").getextrema()[0] > 60


@pytest.mark.parametrize("name", ["tapijt", "carpet", "rug", "carpet2", "well", "waterput"])
def test_hand_drawn_objects_never_fall_back_to_text(name):
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [BoardObject(name, "standable", (Square(0, 0),))],
        ["A", "B"],
    )
    assert picture.unknown_object_icons(board) == []


def test_every_object_and_figure_in_the_examples_has_a_vendored_icon():
    checked = 0
    for path in all_examples():
        text = path.read_text()
        if "People:" not in text:
            continue
        board, _ = load_board(text)
        assert picture.unknown_object_icons(board) == [], path.name
        for person, figure in load_presentation(text).figures.items():
            if figure.icon:
                assert icons.object_icon(figure.icon) is not None, (path.name, person)
        checked += 1
    assert checked >= 5


def test_blocked_squares_are_shaded_darker_without_a_cross():
    board, _ = load_board((example("tamagotchi-murdoku-9x9.txt")).read_text())
    image = picture.murdoku_picture(board, legend=False).convert("RGB")
    cell, margin = 120, 60
    blocked = sorted(board.blocked)[0]
    x, y = margin + blocked.col * cell, margin + blocked.row * cell
    region = picture._rgb(board.colours[board.region_of(blocked)])
    # A corner of the square, clear of the icon: a plain darker region colour.
    r, g, b = image.getpixel((x + cell // 12, y + cell // 12))
    assert (r, g, b) == tuple(round(v * picture.BLOCKED_SHADE) for v in region)
    assert sum(region) - (r + g + b) > 100


def test_picture_ignores_role_booleans_in_the_assignment(tmp_path):
    out = tmp_path / "c.png"
    assert cli.main([str(example("murdoku_composition.txt")), "--png", str(out)]) == 0
    assert out.exists()


def test_dog_and_puppy_pieces_are_drawn_instead_of_the_crown():
    from csp import queens

    base = (example("queens_4_4x4.txt")).read_text()
    pictures = {}
    for icon in ("queen", "dog", "puppy"):
        text = base.replace("Family: queens", f"Family: queens\nIcon: {icon}")
        (solution,) = bruteforce.solutions(text)
        pictures[icon] = picture.queens_picture(queens.parse(text), solution, cell=CELL)

    assert pictures["dog"].size == pictures["queen"].size
    assert pictures["dog"].tobytes() != pictures["queen"].tobytes()
    assert pictures["dog"].tobytes() != pictures["puppy"].tobytes()
    # the puppy's tongue is the only pink on the board
    assert any(
        pictures["puppy"].getpixel((x, y)) == picture.TONGUE
        for x in range(pictures["puppy"].width)
        for y in range(pictures["puppy"].height)
    )


def test_dog_puzzles_give_every_zone_its_own_colour():
    from csp import queens

    text = (example("dogdoku_3_9x9.txt")).read_text()
    puzzle = queens.parse(text)
    image = picture.queens_picture(puzzle, None, cell=CELL)
    margin = CELL // 2
    colours = {}
    for r, line in enumerate(puzzle.grid):
        for c, region in enumerate(line):
            colours.setdefault(
                region, image.getpixel((margin + c * CELL + 5, margin + r * CELL + 5))
            )
    assert len(set(colours.values())) == puzzle.size


def test_dutch_legend_lists_fixed_role_holders_as_a_category():
    text = example("menu-murdoku-3.txt").read_text()
    board, _ = load_board(text)
    legend = drawing._Legend(board, CELL, language="nl")

    assert legend.words["point"] == "Punt"
    assert legend._role_line("eiwit") == "Eiwit: Vis, Bonen (niet meer dan 1 hiervan per gebied)"


def test_region_names_are_tagged_on_puzzle_and_solution_away_from_people():
    board = Board(2, [["a", "b"], ["a", "b"]], {"a": "here", "b": "there"}, [], ["A", "B"])

    markup = drawing.murdoku_picture(board, cell=CELL).to_svg()
    assert markup.count('class="area-label"') == 2

    def top(**kw):
        return _centre(
            picture.murdoku_picture(board, cell=CELL, coordinates=False, **kw), board, 0, 0, False
        )

    plain = top(labels=False)
    assert top() != plain
    assert top(placed={"A": Square(1, 0), "B": Square(1, 1)}) != plain
    # The tag moves off a square where someone stands.
    assert top(placed={"A": Square(0, 0), "B": Square(1, 1)}) != top()


def test_a_labelled_board_leaves_region_swatches_out_of_the_legend():
    board = Board(2, [["a", "b"], ["a", "b"]], {"a": "here", "b": "there"}, [], ["A", "B"])
    with_swatches = picture.murdoku_picture(board, cell=CELL, labels=False)
    labelled = picture.murdoku_picture(board, cell=CELL)
    assert labelled.height < with_swatches.height


def test_legend_item_label_drops_a_name_that_only_repeats_the_kind():
    board = Board(
        2,
        [["a", "a"], ["b", "b"]],
        {"a": "a", "b": "b"},
        [],
        ["A", "B"],
        edge_items=[
            EdgeItem("deur", "door", (Square(0, 0), Square(1, 0))),
            EdgeItem("achter_deur", "door", (Square(0, 1), Square(1, 1))),
            EdgeItem("raam", "window", (Square(0, 0),)),
        ],
    )
    legend = picture._Legend(board, CELL, language="nl")
    assert legend._item_label("door", "deur") == legend.words["door"]
    assert legend._item_label("window", "raam") == legend.words["window"]
    assert legend._item_label("door", "achter_deur") == f"{legend.words['door']}: achter deur"


def test_role_legend_names_an_attribute_group_instead_of_every_suspect():
    board, _ = load_board(example("murdoku_orient_express.txt").read_text())
    assert drawing._Legend(board, CELL, language="nl")._role_line("moordenaar") == (
        "Moordenaar: een vrouw"
    )
    solved = {(person, "moordenaar"): person == "Svetlana" for person in board.people}
    legend = drawing._Legend(board, CELL, role_statuses=solved, language="nl")
    assert legend._role_line("moordenaar") == "Moordenaar: Svetlana"


def test_a_seat_with_a_side_has_its_back_against_that_wall():
    def board(side):
        bench = BoardObject("trein_bank", "standable", (Square(0, 1), Square(1, 1)), side=side)
        return Board(2, [["a", "a"], ["a", "a"]], {"a": "a"}, [bench], ["A", "B"])

    def darkness(image, x):
        return sum(image.getpixel((x, CELL // 6 + CELL))[:3])

    margin = CELL // 6
    left_x, right_x = margin + CELL + 18, margin + 2 * CELL - 18
    left = picture.murdoku_picture(board(None), cell=CELL, coordinates=False, labels=False)
    right = picture.murdoku_picture(board("right"), cell=CELL, coordinates=False, labels=False)
    # The backrest is the darker band: by default on the left, with `right` on the right.
    assert darkness(left, left_x) < darkness(left, right_x)
    assert darkness(right, right_x) < darkness(right, left_x)


def test_a_window_with_a_side_is_drawn_against_that_wall():
    def board(side):
        return Board(
            2,
            [["a", "a"], ["a", "a"]],
            {"a": "a"},
            [],
            ["A", "B"],
            edge_items=[EdgeItem("raam", "window", (Square(0, 0),), side=side)],
        )

    glass = (208, 228, 242)

    def near_glass(rgb):
        return all(abs(x - y) < 12 for x, y in zip(rgb, glass, strict=True))

    margin = CELL // 6
    top = picture.murdoku_picture(board("top"), cell=CELL, coordinates=False, labels=False)
    assert near_glass(top.getpixel((margin + 20, margin + 6)))
    assert not near_glass(top.getpixel((margin + 50, margin + 50)))
    left = picture.murdoku_picture(board("left"), cell=CELL, coordinates=False, labels=False)
    assert near_glass(left.getpixel((margin + 6, margin + 20)))
    assert not near_glass(left.getpixel((margin + 20, margin + 6)))


def test_count_legend_uses_the_given_plain_language_texts():
    text = example("wie-doet-het-met-wie-1.txt").read_text()
    board, clues = load_board(text)
    from csp import murdoku, story

    counts = murdoku.global_count_conditions(board, clues)
    markup = drawing.murdoku_picture(
        board, global_counts=counts, count_texts=story.global_count_texts(text), language="nl"
    ).to_svg()
    assert "Precies twee mensen dragen een badjas" in markup
    assert "object:badjas" not in markup
