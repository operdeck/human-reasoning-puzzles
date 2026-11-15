"""Reading a scan: grid detection, cell tiling and icon matching on a drawn board."""

import numpy as np
import pytest

pytest.importorskip("cv2")

import cv2

from csp import scan

SIZE = 10
PITCH = 180
MARGIN = 90
ICON_CELLS = [(2, 3), (5, 5), (7, 8), (9, 1)]


def draw_board(path) -> None:
    """A 10x10 board with a pastel floor, darker area borders and four discs."""
    side = MARGIN * 2 + PITCH * SIZE
    image = np.full((side, side, 3), 250, np.uint8)
    for index in range(SIZE + 1):
        position = MARGIN + index * PITCH
        cv2.line(image, (position, MARGIN), (position, side - MARGIN), (60, 60, 60), 2)
        cv2.line(image, (MARGIN, position), (side - MARGIN, position), (60, 60, 60), 2)
    for row in range(SIZE):
        for col in range(SIZE):
            top = MARGIN + row * PITCH + 2
            left = MARGIN + col * PITCH + 2
            colour = (200, 230, 245) if col < 4 else (235, 235, 205)
            cv2.rectangle(image, (left, top), (left + PITCH - 4, top + PITCH - 4), colour, -1)
    # One thick area border, drawn like the printed boards.
    cv2.line(
        image,
        (MARGIN + 4 * PITCH, MARGIN),
        (MARGIN + 4 * PITCH, side - MARGIN),
        (40, 40, 40),
        6,
    )
    for row, col in ICON_CELLS:
        centre = (MARGIN + (col - 1) * PITCH + PITCH // 2, MARGIN + (row - 1) * PITCH + PITCH // 2)
        cv2.circle(image, centre, 26, (60, 60, 170), -1)
    cv2.imwrite(str(path), image)


def test_find_grid_reads_every_line_of_a_drawn_board(tmp_path):
    source = tmp_path / "board.png"
    draw_board(source)
    grid = scan.find_grid(scan.load(source), size=SIZE)
    assert grid.size == SIZE
    expected = [MARGIN + index * PITCH for index in range(SIZE + 1)]
    assert all(abs(found - want) <= 6 for found, want in zip(grid.x, expected, strict=True))
    assert all(abs(found - want) <= 6 for found, want in zip(grid.y, expected, strict=True))
    assert grid.centre((2, 3)) == pytest.approx(
        (MARGIN + 2 * PITCH + PITCH / 2, MARGIN + 1 * PITCH + PITCH / 2)
    )


def test_find_grid_follows_the_board_when_a_decoy_line_sits_below(tmp_path):
    """A spread carries more long lines than the board's: a sketchpad frame, a page rule."""
    source = tmp_path / "spread.png"
    draw_board(source)
    image = scan.load(source)
    side = MARGIN * 2 + PITCH * SIZE
    taller = np.full((side + 2 * PITCH, side, 3), 250, np.uint8)
    taller[:side] = image
    # One and a half pitches below the board, so it cannot belong to the rhythm.
    decoy = side + PITCH + PITCH // 2
    cv2.line(taller, (0, decoy), (side, decoy), (60, 60, 60), 2)
    spread = tmp_path / "spread.png"
    cv2.imwrite(str(spread), taller)

    grid = scan.find_grid(scan.load(spread), size=SIZE)
    expected = [MARGIN + index * PITCH for index in range(SIZE + 1)]
    assert all(abs(found - want) <= 6 for found, want in zip(grid.y, expected, strict=True))

    source = tmp_path / "board.png"
    draw_board(source)
    tiles = scan.tiles(scan.load(source), scan.find_grid(scan.load(source), size=SIZE))
    assert len(tiles) == SIZE * SIZE
    assert all(tile.shape == (scan.CELL_TILE, scan.CELL_TILE, 3) for tile in tiles.values())


def test_rank_cells_finds_every_copy_of_the_seed_icon(tmp_path):
    source = tmp_path / "board.png"
    draw_board(source)
    image = scan.load(source)
    tiles = scan.tiles(image, scan.find_grid(image, size=SIZE))
    ranked = scan.rank_cells(tiles, seed=ICON_CELLS[0])
    assert [cell for cell, _ in ranked[: len(ICON_CELLS)]] == sorted(
        ICON_CELLS, key=lambda cell: ranked.index(next(pair for pair in ranked if pair[0] == cell))
    )
    found = {cell for cell, _ in ranked[: len(ICON_CELLS)]}
    assert found == set(ICON_CELLS)
    scores = [score for _, score in ranked[: len(ICON_CELLS)]]
    assert max(scores) < ranked[len(ICON_CELLS)][1] / 4


def test_icon_mask_follows_the_icon_and_rejects_an_empty_cell(tmp_path):
    source = tmp_path / "board.png"
    draw_board(source)
    image = scan.load(source)
    tiles = scan.tiles(image, scan.find_grid(image, size=SIZE))
    mask = scan.icon_mask(tiles[ICON_CELLS[0]][56:-56, 56:-56])
    assert 0.02 < mask.mean() < 0.5
    with pytest.raises(scan.ScanError):
        scan.icon_mask(tiles[(1, 1)][56:-56, 56:-56])


def test_contact_sheet_names_every_cell(tmp_path):
    source = tmp_path / "board.png"
    draw_board(source)
    image = scan.load(source)
    tiles = scan.tiles(image, scan.find_grid(image, size=SIZE))
    sheet = tmp_path / "sheet.png"
    scan.contact_sheet(tiles, sheet)
    written = cv2.imread(str(sheet))
    assert written is not None
    assert written.shape[0] >= SIZE * 110 and written.shape[1] >= SIZE * 110


def test_find_grid_ignores_a_frame_around_the_board(tmp_path):
    """A page frame or card border outside the board must not become a grid line."""
    image = np.full((MARGIN * 2 + PITCH * SIZE, MARGIN * 2 + PITCH * SIZE, 3), 250, np.uint8)
    for index in range(SIZE + 1):
        position = MARGIN + index * PITCH
        cv2.line(image, (position, MARGIN), (position, MARGIN + PITCH * SIZE), (60, 60, 60), 2)
        cv2.line(image, (MARGIN, position), (MARGIN + PITCH * SIZE, position), (60, 60, 60), 2)
    cv2.rectangle(image, (10, 10), (image.shape[1] - 10, image.shape[0] - 10), (30, 30, 30), 4)
    path = tmp_path / "framed.png"
    cv2.imwrite(str(path), image)

    grid = scan.find_grid(scan.load(path), size=SIZE)
    expected = [MARGIN + index * PITCH for index in range(SIZE + 1)]
    assert all(abs(found - want) <= 6 for found, want in zip(grid.x, expected, strict=True))
    assert all(abs(found - want) <= 6 for found, want in zip(grid.y, expected, strict=True))


def test_rank_cells_rejects_a_seed_that_is_not_on_the_board(tmp_path):
    source = tmp_path / "board.png"
    draw_board(source)
    board = scan.tiles(scan.load(source), scan.find_grid(scan.load(source), size=SIZE))
    with pytest.raises(scan.ScanError, match="not on this board"):
        scan.rank_cells(board, seed=(99, 99))


def test_cli_reports_the_grid_and_can_write_tiles(tmp_path, capsys):
    source = tmp_path / "board.png"
    draw_board(source)
    tiles_dir = tmp_path / "cells"
    assert scan.main([str(source), "--size", str(SIZE), "--tiles", str(tiles_dir)]) == 0
    output = capsys.readouterr().out
    assert "x lines:" in output and "pitches:" in output
    assert len(list(tiles_dir.glob("r*c*.png"))) == SIZE * SIZE


def test_the_solver_does_not_need_numpy_but_the_scan_reader_says_how_to_get_it(
    tmp_path, monkeypatch
):
    """numpy stays out of the solver's dependencies; only `csp.scan` needs it."""
    import sys

    monkeypatch.setitem(sys.modules, "numpy", None)
    monkeypatch.setattr(scan, "_NUMPY", None)
    with pytest.raises(scan.ScanError, match="uv sync --extra scan"):
        scan.load(tmp_path / "anything.png")


def test_ocr_explains_which_backend_is_missing(tmp_path, monkeypatch):
    """Both backends are blocked, so this cannot pass by accident on one platform."""
    import sys

    monkeypatch.setitem(sys.modules, "csp.scan_vision", None)
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    with pytest.raises(scan.ScanError, match="macOS Vision"):
        scan.ocr(tmp_path / "nothing.png")


def test_find_grid_refuses_a_page_whose_lines_are_not_evenly_spaced(tmp_path):
    """A dense spread gives long runs everywhere; refusing beats returning a guess."""
    path = tmp_path / "busy.png"
    image = np.full((600, 600, 3), 250, np.uint8)
    rng = np.random.default_rng(7)
    for _ in range(60):
        x0, y0 = rng.integers(0, 560, 2)
        cv2.rectangle(
            image,
            (int(x0), int(y0)),
            (int(x0) + int(rng.integers(10, 60)), int(y0) + int(rng.integers(10, 60))),
            (30, 30, 30),
            -1,
        )
    cv2.imwrite(str(path), image)
    with pytest.raises(
        scan.ScanError, match=r"tilted|not evenly spaced|line clusters|no grid lines"
    ):
        scan.find_grid(scan.load(path), size=8)
