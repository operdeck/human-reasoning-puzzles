"""Reading a puzzle out of a photograph or scan of a printed page.

`picture` draws puzzles; this module reads them back. It exists because a
transcription starts with a scan, and measuring the scan is the only reliable
half of the job: OCR reads the cards and legends, and grid detection plus
template matching find the cells. What measurement cannot do is *name* an icon —
see the "Reading a scan" section of the Murdoku authoring skill.

Needs the `scan` extra for the image work (`uv sync --extra scan`); `numpy` is a
hard dependency because the tiles are numpy arrays.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

    Image = NDArray[np.uint8]
    Cell = tuple[int, int]

CELL_TILE = 280
"""Side of a normalised cell tile: resizing is what makes cells comparable."""


class ScanError(RuntimeError):
    """A scan cannot be read, or the library that would read it is missing."""


@dataclass(frozen=True)
class Grid:
    """The cell boundaries of a square board, in the scan's pixels."""

    x: tuple[int, ...]
    y: tuple[int, ...]

    @property
    def size(self) -> int:
        """Cells per side."""
        return len(self.x) - 1

    def cells(self) -> list[Cell]:
        """Every (row, col), one-based, top-left first."""
        return [(row + 1, col + 1) for row in range(self.size) for col in range(self.size)]

    def centre(self, cell: Cell) -> tuple[float, float]:
        """Pixel centre of a one-based cell, as (x, y)."""
        row, col = cell
        return ((self.x[col - 1] + self.x[col]) / 2, (self.y[row - 1] + self.y[row]) / 2)


def _cv2() -> Any:
    try:
        import cv2
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on the install
        raise ScanError("reading scans needs opencv: uv sync --extra scan") from exc
    return cv2


def load(path: Path | str) -> Image:
    """The scan as a BGR colour array."""
    cv2 = _cv2()
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ScanError(f"cannot read an image from {path}")
    return np.asarray(image, dtype=np.uint8)


def find_grid(image: Image, size: int = 10, kernel: int = 90) -> Grid:
    """The `size + 1` cell boundaries on each axis.

    A photographed page is not uniform: rows near the spine can be ten per cent
    wider than rows near the edge, so one assumed pitch drifts by a whole cell
    over ten columns. The lines are detected instead of assumed: long dark runs
    are isolated by morphology, clustered, and then the candidate nearest each
    expected position is kept, which stops a wall or an icon from standing in for
    a grid line.
    """
    cv2 = _cv2()
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        grey, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 12
    )
    vertical = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel))
    )
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (kernel, 1))
    )

    def axis_lines(profile: NDArray[np.float64], axis: str) -> tuple[int, ...]:
        best = float(profile.max())
        if best <= 0:
            raise ScanError(f"no {axis} lines found; is this a board scan?")
        candidates = [index for index, value in enumerate(profile) if value > best * 0.18]
        if len(candidates) < size + 1:
            raise ScanError(f"found {len(candidates)} {axis} line pixels, need {size + 1} lines")
        groups: list[list[int]] = []
        for position in candidates:
            if groups and position - groups[-1][-1] <= 25:
                groups[-1].append(position)
            else:
                groups.append([position])
        centres = [round(float(np.mean(group))) for group in groups]
        if len(centres) == size + 1:
            return tuple(centres)

        # A spread carries other long lines: the frame of a sketchpad, a page rule.
        # Follow the board's own rhythm instead of spanning everything: the typical
        # gap between detected lines is the cell pitch, and only a run whose gaps
        # all match it belongs to one grid.
        gaps = [b - a for a, b in pairwise(centres)]
        pitch = float(np.median(gaps))
        runs: list[list[int]] = [[centres[0]]]
        for previous, centre in pairwise(centres):
            if abs((centre - previous) - pitch) <= pitch * 0.35:
                runs[-1].append(centre)
            else:
                runs.append([centre])
        usable = [run for run in runs if len(run) >= size + 1]
        if not usable:
            return tuple(centres[: size + 1])
        chosen_run = max(
            usable,
            key=lambda run: (sum(float(profile[value]) for value in run), len(run)),
        )
        first, last = chosen_run[0], chosen_run[-1]
        pitch = (last - first) / size
        chosen: list[int] = []
        for step in range(size + 1):
            expected = first + step * pitch
            near = [value for value in chosen_run if abs(value - expected) <= pitch * 0.35]
            chosen.append(
                min(near, key=lambda value: abs(value - expected)) if near else round(expected)
            )
        gaps = [b - a for a, b in pairwise(chosen)]
        if min(gaps) <= 0 or max(gaps) > min(gaps) * 1.6:
            raise ScanError(
                f"the {axis} lines are not evenly spaced ({gaps}); crop the board out of the "
                "page and scan the board alone, then try again"
            )
        return tuple(chosen)

    x_profile = np.asarray(vertical.sum(axis=0) / 255, dtype=np.float64)
    y_profile = np.asarray(horizontal.sum(axis=1) / 255, dtype=np.float64)
    x = axis_lines(x_profile, "vertical")
    y = axis_lines(y_profile, "horizontal")
    return Grid(x, y)


def tiles(image: Image, grid: Grid, side: int = CELL_TILE) -> dict[Cell, Image]:
    """One square tile per cell, resized to `side` pixels."""
    cv2 = _cv2()
    out: dict[Cell, Image] = {}
    for cell in grid.cells():
        row, col = cell
        crop = image[grid.y[row - 1] : grid.y[row], grid.x[col - 1] : grid.x[col]]
        if crop.size == 0:
            raise ScanError(f"cell r{row}c{col} lies outside the scan")
        resized = cv2.resize(crop, (side, side), interpolation=cv2.INTER_AREA)
        out[cell] = np.asarray(resized, dtype=np.uint8)
    return out


def floor_colour(tile: Image) -> NDArray[np.int32]:
    """The cell's background colour: the commonest quantised colour of its edge."""
    ring = np.concatenate(
        [
            tile[0:6].reshape(-1, 3),
            tile[-6:].reshape(-1, 3),
            tile[:, 0:6].reshape(-1, 3),
            tile[:, -6:].reshape(-1, 3),
        ]
    )
    codes, counts = np.unique((ring // 12).astype(np.int32), axis=0, return_counts=True)
    return np.asarray(codes[int(counts.argmax())] * 12 + 6, dtype=np.int32)


def icon_mask(template: Image, distance: float = 70.0) -> NDArray[np.bool_]:
    """Pixels of a cell tile that belong to the icon rather than to its floor.

    Matching whole tiles would rank cells by their floor: two tables on different
    floors would score worse than a table and a chair on the same floor.
    """
    cv2 = _cv2()
    floor = floor_colour(template)
    mask = np.linalg.norm(template.astype(np.float64) - floor, axis=2) > distance
    grown = np.asarray(
        cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool), dtype=bool
    )
    if grown.sum() < 40:
        raise ScanError("the seed cell looks empty: pick a cell that holds the icon")
    return grown


def rank_cells(
    tiles_by_cell: dict[Cell, Image],
    seed: Cell,
    inset: float = 0.20,
    search: int = 8,
    step: int = 4,
) -> list[tuple[Cell, float]]:
    """Every cell ranked by how closely it repeats the seed's icon, best first.

    Comparison is a masked squared difference over a small offset search: the
    printed icons are the same artwork each time, but a scan shifts them by a few
    pixels, so a rigid comparison at one offset reports near-misses as misses.
    """
    template = tiles_by_cell[seed]
    edge = int(template.shape[0] * inset)
    patch = template[edge:-edge, edge:-edge]
    mask = icon_mask(patch)
    wanted = patch[mask].astype(np.float64)
    span_y = patch.shape[0]
    span_x = patch.shape[1]

    ranked: list[tuple[Cell, float]] = []
    for cell, tile in tiles_by_cell.items():
        best = float("inf")
        limit = tile.shape[0]
        for dy in range(-search, search + 1, step):
            for dx in range(-search, search + 1, step):
                top, left = edge + dy, edge + dx
                if top < 0 or left < 0 or top + span_y > limit or left + span_x > limit:
                    continue
                window = tile[top : top + span_y, left : left + span_x]
                difference = window[mask].astype(np.float64) - wanted
                best = min(best, float(np.mean(difference * difference)))
        ranked.append((cell, best))
    ranked.sort(key=lambda pair: pair[1])
    return ranked


def contact_sheet(tiles_by_cell: dict[Cell, Image], path: Path | str, thumb: int = 110) -> None:
    """Write every tile with its cell name: the sheet a person reads and corrects."""
    cv2 = _cv2()
    rows = max(row for row, _ in tiles_by_cell)
    cols = max(col for _, col in tiles_by_cell)
    sheet = np.full((rows * (thumb + 18), cols * (thumb + 18), 3), 255, np.uint8)
    for (row, col), tile in tiles_by_cell.items():
        small = cv2.resize(tile, (thumb, thumb), interpolation=cv2.INTER_AREA)
        top, left = (row - 1) * (thumb + 18), (col - 1) * (thumb + 18)
        sheet[top : top + thumb, left : left + thumb] = small
        cv2.putText(
            sheet,
            f"r{row}c{col}",
            (left + 2, top + thumb + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(path), sheet)


def ocr(path: Path | str) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Text lines of a page with normalised boxes, origin at the bottom left.

    macOS Vision is used where its pyobjc bindings are installed; elsewhere
    `pytesseract` needs the tesseract binary. Both read printed cards and legends
    -- neither can describe a picture, which is why icons still need a person.
    """
    try:  # pragma: no cover - depends on the platform
        from .scan_vision import recognise

        return recognise(str(path))
    except ImportError:
        pass
    try:  # pragma: no cover - depends on the platform
        import pytesseract
        from PIL import Image as PILImage
    except ModuleNotFoundError as exc:
        raise ScanError(
            "reading text from a scan needs macOS Vision (pyobjc-framework-Vision) or "
            "pytesseract with the tesseract binary: uv sync --extra scan"
        ) from exc
    image = PILImage.open(path)
    width, height = image.size
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    lines: list[tuple[str, tuple[float, float, float, float]]] = []
    for index, text in enumerate(data["text"]):
        if not str(text).strip():
            continue
        left, top = data["left"][index], data["top"][index]
        right = left + data["width"][index]
        bottom = top + data["height"][index]
        box = (left / width, 1 - bottom / height, right / width, 1 - top / height)
        lines.append((str(text), box))
    return lines
