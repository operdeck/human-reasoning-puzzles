"""Tests for the PNG pictures and the icon references. No network needed."""

from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from csp import bruteforce, cli, icons, picture  # noqa: E402
from csp.murdoku import Board, BoardObject, CornerObject, EdgeItem, RoleSpec, Square  # noqa: E402
from csp.puzzlefile import load_board  # noqa: E402

EXAMPLES = Path(__file__).parent.parent / "examples"
CELL = 100


@pytest.fixture(autouse=True)
def offline_icons(tmp_path, monkeypatch):
    """An empty icon cache, and no downloads: icons fall back to text labels."""
    monkeypatch.setenv("CSP_ICON_CACHE", str(tmp_path / "icons"))

    def no_network(*args, **kwargs):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(icons.urllib.request, "urlopen", no_network)


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
    assert icons.NOTO_COMMIT in icons.SOURCE


def test_cached_icon_is_used_without_downloading():
    path = icons.cache_dir() / "1f333.png"
    path.parent.mkdir(parents=True)
    Image.new("RGBA", (8, 8), (0, 128, 0, 255)).save(path)
    assert icons.icon("boom") == path
    assert icons.icon("koffer") is None  # not cached, and the download fails


def _cache_icon(code: str, image: Image.Image) -> None:
    path = icons.cache_dir() / f"{code}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def test_two_square_standable_object_is_stretched_across_both_squares():
    _cache_icon("1f37d", Image.new("RGBA", (40, 40), (0, 0, 255, 255)))  # a blue block
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [BoardObject("table", "standable", (Square(1, 0), Square(1, 1)))],
        ["A", "B"],
    )  # fmt: skip
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    margin = CELL // 6
    row = margin + CELL + CELL // 2
    blue = [x for x in range(image.width) if image.getpixel((x, row)) == (0, 0, 255)]
    assert blue[0] < margin + CELL // 4 and blue[-1] > margin + 2 * CELL - CELL // 4


def test_two_square_bench_keeps_its_proportions_and_is_not_stretched():
    _cache_icon("1f6cb", Image.new("RGBA", (40, 40), (0, 0, 255, 255)))  # a blue block
    board = Board(
        2,
        [["a", "a"], ["a", "a"]],
        {"a": "here"},
        [BoardObject("bench", "standable", (Square(1, 0), Square(1, 1)))],
        ["A", "B"],
    )  # fmt: skip
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    margin = CELL // 6
    row = margin + CELL + CELL // 2
    blue = [x for x in range(image.width) if image.getpixel((x, row)) == (0, 0, 255)]
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

    def capture(image, draw, name, area, cell, **kwargs):
        calls.append((name, area, kwargs))

    monkeypatch.setattr(picture, "_icon", capture)
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

    def capture(image, draw, name, area, cell, **kwargs):
        calls.append((name, area, kwargs))

    monkeypatch.setattr(picture, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert len(calls) == 2
    assert all(name == "stoel" and area[2] - area[0] == CELL for name, area, _ in calls)
    assert all(area[3] - area[1] == CELL for _, area, _ in calls)


def test_edge_items_and_corner_objects_render_at_their_anchors(monkeypatch):
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
        corner_objects=[
            CornerObject(
                "critter",
                (Square(0, 0), Square(0, 1), Square(1, 0), Square(1, 1)),
            )
        ],
    )
    calls = []

    def capture(image, draw, name, area, cell, **kwargs):
        calls.append((name, area))

    monkeypatch.setattr(picture, "_icon", capture)
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False, legend=False)
    margin = CELL // 6

    assert image.getpixel((margin + CELL, margin + CELL // 2)) == (117, 75, 47)
    assert calls == [
        ("window", (margin + 2 * CELL, margin + 2 * CELL, margin + 3 * CELL, margin + 3 * CELL)),
        (
            "critter",
            (
                margin + CELL - CELL // 4,
                margin + CELL - CELL // 4,
                margin + CELL + CELL // 4,
                margin + CELL + CELL // 4,
            ),
        ),
    ]
    with_legend = picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert with_legend.height > image.height
    assert picture.unknown_object_icons(board) == ["critter"]
    assert len(board.free) == 9


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
    original = picture.murdoku_picture

    def capture(board, placed=None, **kwargs):
        seen.append(kwargs.get("role_statuses"))
        return original(board, placed, **kwargs)

    monkeypatch.setattr(picture, "murdoku_picture", capture)
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
    original = picture.murdoku_picture

    def capture(board, placed=None, **kwargs):
        seen.append(kwargs.get("global_counts"))
        return original(board, placed, **kwargs)

    monkeypatch.setattr(picture, "murdoku_picture", capture)
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

    def capture(image, draw, name, area, cell, **kwargs):
        rotations.append(kwargs.get("rotate", False))

    monkeypatch.setattr(picture, "_icon", capture)
    picture.murdoku_picture(board, cell=CELL, coordinates=False)
    assert rotations == [True]


def test_custom_carpet_and_well_icons_draw_distinct_images():
    carpet = Image.new("RGB", (120, 120), picture.WHITE)
    picture._draw_carpet(ImageDraw.Draw(carpet), (0, 0, 120, 120))
    assert carpet.getpixel((60, 60)) == (156, 58, 45)

    well = Image.new("RGB", (120, 120), picture.WHITE)
    picture._draw_water_well(ImageDraw.Draw(well), (0, 0, 120, 120))
    assert well.getpixel((45, 84)) == (45, 65, 70)


def test_couch_icon_loses_its_floor_lamp():
    couch = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    couch.paste((250, 210, 0, 255), (60, 0, 90, 40))  # yellow lamp, top right
    couch.paste((40, 140, 220, 255), (5, 30, 95, 95))  # blue couch, backrest up to y=30
    cleaned = picture.ICON_FIXES["1f6cb"](couch)
    assert cleaned.getpixel((75, 10))[3] == 0  # lamp gone
    assert cleaned.getpixel((20, 35)) == (40, 140, 220, 255)  # backrest kept
    assert cleaned.getpixel((50, 80)) == (40, 140, 220, 255)  # seat kept


def test_picture_shows_regions_objects_and_borders():
    text = (EXAMPLES / "prrrdoku3.txt").read_text()
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
    board, _ = load_board((EXAMPLES / "prrrdoku3.txt").read_text())
    with_legend = picture.murdoku_picture(board, cell=CELL)
    without = picture.murdoku_picture(board, cell=CELL, legend=False)
    assert without.width == without.height == with_legend.width < with_legend.height


def test_hatching_only_on_hatched_regions():
    board, _ = load_board((EXAMPLES / "prrrdoku3.txt").read_text())
    image = picture.murdoku_picture(board, cell=CELL)
    margin = CELL // 2

    def colours(r, c):
        x0, y0 = margin + c * CELL + 10, margin + r * CELL + 10
        return {image.getpixel((x, y)) for x in range(x0, x0 + 60) for y in range(y0, y0 + 60)}

    assert len(colours(8, 0)) > 1  # water (hatched)
    assert len(colours(5, 7)) == 1  # klimgebied zuid (plain)


def test_solution_picture_puts_name_tags_on_squares():
    text = (EXAMPLES / "prrrdoku3.txt").read_text()
    board, _ = load_board(text)
    (solution,) = bruteforce.solutions(text, "murdoku")
    image = picture.murdoku_picture(board, solution, cell=CELL)
    tim = solution["Tim"]
    margin = CELL // 2
    tag = image.getpixel((margin + tim.col * CELL + 20, margin + tim.row * CELL + CELL // 2))
    assert tag == (255, 255, 255)


def test_default_palette_when_no_colours_given():
    board = Board(2, [["a", "b"], ["a", "b"]], {"a": "here", "b": "there"}, [], ["A", "B"])
    image = picture.murdoku_picture(board, cell=CELL, coordinates=False)
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


def test_cli_png_writes_board_and_solution(tmp_path, capsys):
    from csp import cli

    target = tmp_path / "board.png"
    assert cli.main([str(EXAMPLES / "prrrdoku1.txt"), "--png", str(target)]) == 0
    assert target.exists() and (tmp_path / "board-solution.png").exists()
    for name in ("sudoku_4x4.txt", "calcudoku_4x4_easy.txt"):
        target = tmp_path / f"{name}.png"
        assert cli.main([str(EXAMPLES / name), "--png", str(target)]) == 0
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

    text = (EXAMPLES / "sudoku_4x4.txt").read_text()
    grid = sudoku.parse(text)
    (solution,) = bruteforce.solutions(text)
    image = picture.sudoku_picture(grid, solution, cell=CELL)
    assert image.size == (5 * CELL, 5 * CELL)
    assert _has(image, 0, 2, picture.INK) and not _has(image, 0, 2, picture.SOLVED)
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

    grid = sudoku.parse((EXAMPLES / "sudoku_4x4.txt").read_text())
    image = picture.sudoku_picture(grid, cell=CELL)
    corner = lambda r, c: image.getpixel((CELL // 2 + c * CELL + 8, CELL // 2 + r * CELL + 8))  # noqa: E731
    assert corner(0, 0) == corner(2, 2) == picture.WHITE
    assert corner(0, 2) == corner(2, 0) != picture.WHITE


def _corner(image, r, c):
    return image.getpixel((CELL // 2 + c * CELL + 8, CELL // 2 + r * CELL + 8))


def test_jigsaw_picture_colours_touching_boxes_apart():
    from csp import sudoku

    puzzle = sudoku.parse((EXAMPLES / "sudoku_jigsaw.txt").read_text())
    image = picture.sudoku_picture(puzzle, cell=CELL)
    boxes = puzzle.boxes
    for r in range(6):
        for c in range(5):
            same = boxes[r][c] == boxes[r][c + 1]
            assert (_corner(image, r, c) == _corner(image, r, c + 1)) == same, (r, c)


def test_x_sudoku_picture_greys_the_diagonals():
    from csp import sudoku

    puzzle = sudoku.parse((EXAMPLES / "sudoku_x.txt").read_text())
    image = picture.sudoku_picture(puzzle, cell=CELL)
    assert _corner(image, 0, 0) == _corner(image, 0, 8) == _corner(image, 4, 4) == picture.EXTRA
    assert _corner(image, 0, 1) != picture.EXTRA


def test_nrc_sudoku_picture_greys_the_extra_boxes():
    from csp import sudoku

    puzzle = sudoku.parse((EXAMPLES / "sudoku_nrc.txt").read_text())
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

    text = (EXAMPLES / "queens_4x4.txt").read_text()
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

    puzzle = logicgrid.parse((EXAMPLES / "logicgrid_3x3.txt").read_text())
    image = picture.logicgrid_picture(puzzle, cell=48)
    table_height = sum(len(items) + 1 for items in puzzle.categories.values()) * 24

    assert image.height > table_height
    assert image.getbbox() is not None


def test_starbattle_picture_distinguishes_given_and_solved_stars():
    from csp import starbattle

    base = (EXAMPLES / "starbattle_8x8.txt").read_text()
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
        "sudoku_kropki_4x4.txt",
        "sudoku_anti_4x4.txt",
        "sudoku_antiking_6x6.txt",
        "suguru_4x4.txt",
        "starbattle_8x8.txt",
        "logicgrid_3x3.txt",
        "binairo_4x4.txt",
        "tango_4x4.txt",
        "tents_4x4.txt",
        "minesweeper_3x3.txt",
        "akari_2x2.txt",
        "kakurasu_4x4.txt",
        "battleships_counts_4x4.txt",
    ],
)
def test_family_png_cli_writes_nonblank_solution(name, tmp_path):
    text = (EXAMPLES / name).read_text()
    kind = cli.detect(text)
    (solution,) = bruteforce.solutions(text, kind)
    path = tmp_path / f"{name}.png"

    assert cli.write_picture(kind, text, path, solution)
    image = Image.open(path).convert("RGB")
    assert image.width > 0 and image.height > 0
    assert image.getbbox() is not None


def test_tango_picture_marks_equal_and_different_signs():
    from csp import binairo

    text = (EXAMPLES / "tango_4x4.txt").read_text()
    puzzle = binairo.parse(text)
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

    for name in ("calcudoku_4x4_easy.txt", "calcudoku_7x7_hard.txt"):
        puzzle = calcudoku.parse((EXAMPLES / name).read_text())
        fills = picture._cage_fills(puzzle)
        at = puzzle.cage_at
        for (r, c), cage in at.items():
            for nb in ((r, c + 1), (r + 1, c)):
                if nb in at and at[nb] is not cage:
                    assert fills[at[nb]] != fills[cage], (name, (r, c), nb)


def test_calcudoku_picture_writes_each_cage_target_in_its_first_cell():
    from csp import calcudoku

    puzzle = calcudoku.parse((EXAMPLES / "calcudoku_4x4_easy.txt").read_text())
    image = picture.calcudoku_picture(puzzle, cell=CELL)
    for cage in puzzle.cages:
        r, c = min(cage.cells)
        x, y = CELL // 2 + c * CELL, CELL // 2 + r * CELL
        label = image.crop((x + 8, y + 6, x + CELL // 2, y + CELL // 3))
        assert label.convert("L").getextrema()[0] < 60, cage.label


def test_walls_do_not_poke_into_cells():
    """Where a cage wall ends against a thin line, no ink spills past it."""
    from csp import calcudoku

    puzzle = calcudoku.parse((EXAMPLES / "calcudoku_4x4_easy.txt").read_text())
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


def test_every_object_in_the_examples_has_an_icon():
    checked = 0
    for path in sorted(EXAMPLES.glob("*.txt")):
        text = path.read_text()
        if "People:" not in text:
            continue
        board, _ = load_board(text)
        assert picture.unknown_object_icons(board) == [], path.name
        checked += 1
    assert checked >= 5


def test_blocked_squares_carry_a_red_cross():
    board, _ = load_board((EXAMPLES / "tamagotchi-murdoku-9x9.txt").read_text())
    image = picture.murdoku_picture(board, legend=False).convert("RGB")
    cell, margin = 120, 60
    blocked = sorted(board.blocked)[0]
    x, y = margin + blocked.col * cell, margin + blocked.row * cell
    # a quarter of the way along the diagonal, clear of the centre
    r, g, b = image.getpixel((x + cell // 4, y + cell // 4))
    assert r > g + 40 and r > b + 40


def test_picture_ignores_role_booleans_in_the_assignment(tmp_path):
    out = tmp_path / "c.png"
    assert cli.main([str(EXAMPLES / "murdoku_composition.txt"), "--png", str(out)]) == 0
    assert out.exists()


def test_dog_and_puppy_pieces_are_drawn_instead_of_the_crown():
    from csp import queens

    base = (EXAMPLES / "queens_4x4.txt").read_text()
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

    text = (EXAMPLES / "dogdoku_9x9.txt").read_text()
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
