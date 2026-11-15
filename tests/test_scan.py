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


def test_tiles_are_square_and_one_per_cell(tmp_path):
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


def test_ocr_explains_which_backend_is_missing(tmp_path, monkeypatch):
    def unavailable(name: str, *args, **kwargs):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", unavailable)
    monkeypatch.setitem(__import__("sys").modules, "csp.scan_vision", None)
    with pytest.raises(scan.ScanError, match="macOS Vision"):
        scan.ocr(tmp_path / "nothing.png")
