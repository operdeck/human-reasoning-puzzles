"""Reading a puzzle out of a photograph or scan of a printed page.

`picture` draws puzzles; this module reads them back. It exists because a
transcription starts with a scan, and measuring the scan is the only reliable
half of the job: OCR reads the cards and legends, and grid detection plus
template matching find the cells. What measurement cannot do is *name* an icon —
see the "Reading a scan" section of the Murdoku authoring skill.

Neither numpy nor opencv is a dependency of the solver: both are imported on
first use and the error says which extra installs them (`uv sync --extra scan`).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    import numpy as np
    from numpy.typing import NDArray

    Image = NDArray[np.uint8]
    Cell = tuple[int, int]

CELL_TILE = 280
"""Side of a normalised cell tile: resizing is what makes cells comparable."""

_MAX_SKEW_DEGREES = 2.0
"""Past this the lines are no longer horizontal or vertical, and a grid would drift."""


class ScanError(RuntimeError):
    """A scan cannot be read, or the library that would read it is missing."""


_NUMPY: Any = None
_CV2: Any = None


def _np() -> Any:
    global _NUMPY
    if _NUMPY is None:
        try:
            import numpy
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on the install
            raise ScanError("reading scans needs numpy: uv sync --extra scan") from exc
        _NUMPY = numpy
    return _NUMPY


def _cv2() -> Any:
    global _CV2
    if _CV2 is None:
        try:
            import cv2
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on the install
            raise ScanError("reading scans needs opencv: uv sync --extra scan") from exc
        _CV2 = cv2
    return _CV2


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


def load(path: Path | str) -> Image:
    """The scan as a BGR colour array."""
    np = _np()
    cv2 = _cv2()
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ScanError(f"cannot read an image from {path}")
    return np.asarray(image, dtype=np.uint8)  # type: ignore[no-any-return]


def _clusters(
    profile: NDArray[np.float64], share: float = 0.18, gap: int = 25
) -> list[tuple[int, float]]:
    """Line candidates as (position, strength), one per cluster of dark pixels."""
    np = _np()
    best = float(profile.max())
    if best <= 0:
        raise ScanError("no grid lines found; is this a board scan?")
    candidates = [index for index, value in enumerate(profile) if value > best * share]
    groups: list[list[int]] = []
    for position in candidates:
        if groups and position - groups[-1][-1] <= gap:
            groups[-1].append(position)
        else:
            groups.append([position])
    return [
        (round(float(np.mean(group))), float(profile[group[len(group) // 2]])) for group in groups
    ]


def _fit_grid(candidates: list[tuple[int, float]], size: int, axis: str) -> tuple[int, ...]:
    """The `size + 1` lines that fit one regular grid best.

    A page carries other long dark runs — a frame, a card border, a sketchpad, the
    spine shadow — and a busy board adds its own (area walls, furniture edges), so
    neither the first and last candidate nor any run of consecutive candidates is
    necessarily the board's grid. Instead every pair of candidates proposes a pitch,
    and each pitch whose `size + 1` expected positions match real candidates is
    checked for even spacing. If several grids fit, their lines alone do not say
    which one is the board, so refuse rather than silently choose the wrong one.
    """
    np = _np()
    if len(candidates) < size + 1:
        raise ScanError(
            f"found {len(candidates)} {axis} line clusters, need {size + 1}; "
            "crop the board out of the page and try again"
        )
    positions = [position for position, _ in candidates]
    fits: set[tuple[int, ...]] = set()
    for first_index, start in enumerate(positions):
        for last_index in range(first_index + size, len(positions)):
            pitch = (positions[last_index] - start) / size
            if pitch <= 0:
                continue
            chosen: list[int] = []
            for step in range(size + 1):
                expected = start + step * pitch
                near = [
                    position for position in positions if abs(position - expected) <= pitch * 0.30
                ]
                if not near:
                    chosen = []
                    break
                chosen.append(min(near, key=lambda position: abs(position - expected)))
            if not chosen:
                continue
            gaps = [b - a for a, b in pairwise(chosen)]
            spread = float(np.std(gaps)) / float(np.mean(gaps))
            if min(gaps) > 0 and spread <= 0.18:
                fits.add(tuple(chosen))
    if not fits:
        raise ScanError(
            f"no set of {size + 1} {axis} lines fits one grid; crop the board out of the "
            "page, scan it alone, and try again"
        )
    if len(fits) > 1:
        raise ScanError(
            f"multiple grids fit the {axis} lines; crop the board out of the page, "
            "scan it alone, and try again"
        )
    return next(iter(fits))


def _skew_degrees(vertical: NDArray[np.uint8], horizontal: NDArray[np.uint8]) -> float:
    """How far the detected lines sit off the axes, in degrees."""
    np = _np()
    cv2 = _cv2()
    lines = np.asarray(vertical, dtype=np.uint8) * 255
    lines = np.maximum(lines, np.asarray(horizontal, dtype=np.uint8) * 255)
    points = cv2.findNonZero(lines)
    if points is None or len(points) < 100:
        return 0.0
    angle = float(cv2.minAreaRect(points)[-1])
    return min(angle % 90.0, 90.0 - angle % 90.0)


def find_grid(image: Image, size: int = 10, kernel: int = 90) -> Grid:
    """The `size + 1` cell boundaries on each axis.

    A photographed page is not uniform: rows near the spine can be ten per cent
    wider than rows near the edge, so one assumed pitch drifts by a whole cell over
    ten columns. The lines are detected instead of assumed — long dark runs are
    isolated by morphology and clustered. Competing plausible grids are refused;
    inspect the detected lines before using them. `kernel` is the shortest run
    (in raw scan pixels) that counts as a line: around 90 suits a board of a few
    hundred pixels per cell, which is what a page scan gives.
    """
    np = _np()
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

    skew = _skew_degrees(vertical, horizontal)
    if skew > _MAX_SKEW_DEGREES:
        raise ScanError(
            f"the board is tilted by about {skew:.1f} degrees; rotate the crop until the "
            "lines are upright (find_grid does not deskew), then try again"
        )

    x_profile = np.asarray(vertical.sum(axis=0) / 255, dtype=np.float64)
    y_profile = np.asarray(horizontal.sum(axis=1) / 255, dtype=np.float64)
    x = _fit_grid(_clusters(x_profile), size, "vertical")
    y = _fit_grid(_clusters(y_profile), size, "horizontal")
    return Grid(x, y)


def tiles(image: Image, grid: Grid, side: int = CELL_TILE) -> dict[Cell, Image]:
    """One square tile per cell, resized to `side` pixels."""
    np = _np()
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
    np = _np()
    ring = np.concatenate(
        [
            tile[0:6].reshape(-1, 3),
            tile[-6:].reshape(-1, 3),
            tile[:, 0:6].reshape(-1, 3),
            tile[:, -6:].reshape(-1, 3),
        ]
    )
    codes, counts = np.unique((ring // 12).astype(np.int32), axis=0, return_counts=True)
    return codes[int(counts.argmax())] * 12 + 6  # type: ignore[no-any-return]


def icon_mask(template: Image, distance: float = 70.0) -> NDArray[np.bool_]:
    """Pixels of a cell tile that belong to the icon rather than to its floor.

    Matching whole tiles would rank cells by their floor: two tables on different
    floors would score worse than a table and a chair on the same floor.
    """
    np = _np()
    cv2 = _cv2()
    floor = floor_colour(template)
    mask = np.linalg.norm(template.astype(np.float64) - floor, axis=2) > distance
    grown = np.asarray(
        cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool), dtype=bool
    )
    if grown.sum() < 40:
        raise ScanError("the seed cell looks empty: pick a cell that holds the icon")
    return grown  # type: ignore[no-any-return]


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
    np = _np()
    if seed not in tiles_by_cell:
        raise ScanError(f"the seed cell r{seed[0]}c{seed[1]} is not on this board")
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


def _write_image(path: Path | str, image: Image) -> None:
    cv2 = _cv2()
    try:
        written = cv2.imwrite(str(path), image)
    except cv2.error as exc:
        raise ScanError(f"cannot write image to {path}: {exc}") from exc
    if not written:
        raise ScanError(f"cannot write image to {path}")


def contact_sheet(tiles_by_cell: dict[Cell, Image], path: Path | str, thumb: int = 110) -> None:
    """Write every tile with its cell name: the sheet a person reads and corrects."""
    np = _np()
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
    _write_image(path, sheet)


def ocr(
    path: Path | str, *, language: str | None = None
) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Text lines of a page with normalised boxes, origin at the bottom left.

    macOS Vision is used where its pyobjc bindings are installed; elsewhere
    `pytesseract` needs the tesseract binary, and its words are grouped back into
    lines so both backends return the same thing. `language` may be "nl", "en",
    or "nl+en" (the matching tesseract language data must be installed). Without
    it, Vision uses Dutch and English and tesseract uses its default language.
    Neither backend can describe a picture, so icons still need a person.
    """
    supported = {"nl": ("nl-NL", "nld"), "en": ("en-US", "eng")}
    codes = language.split("+") if language is not None else []
    if any(code not in supported for code in codes):
        raise ScanError(f"unknown OCR language {language!r}; use nl, en, or nl+en")
    try:  # pragma: no cover - depends on the platform
        from .scan_vision import recognise

        return recognise(str(path), languages=[supported[code][0] for code in codes] or None)
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
    options = {"lang": "+".join(supported[code][1] for code in codes)} if codes else {}
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, **options)
    grouped: dict[tuple[int, int, int], list[int]] = {}
    for index, text in enumerate(data["text"]):
        if not str(text).strip():
            continue
        block, paragraph, line = (
            data["block_num"][index],
            data["par_num"][index],
            data["line_num"][index],
        )
        grouped.setdefault((block, paragraph, line), []).append(index)
    lines: list[tuple[str, tuple[float, float, float, float]]] = []
    for indices in grouped.values():
        words = [str(data["text"][index]).strip() for index in indices]
        left = min(data["left"][index] for index in indices)
        top = min(data["top"][index] for index in indices)
        right = max(data["left"][index] + data["width"][index] for index in indices)
        bottom = max(data["top"][index] + data["height"][index] for index in indices)
        box = (left / width, 1 - bottom / height, right / width, 1 - top / height)
        lines.append((" ".join(words), box))
    return lines


def _cell(text: str) -> Cell:
    """`r3c5` -> (3, 5)."""
    row, _, col = text.partition("c")
    if not (row.startswith("r") and row[1:].isdigit() and col.isdigit()):
        raise ScanError(f"bad cell {text!r}; use r3c5")
    return int(row[1:]), int(col)


def main(argv: list[str] | None = None) -> int:
    """`python -m csp.scan PAGE.png` — the measuring a transcription starts with.

    Prints the grid, optionally writes the cell tiles and the contact sheet, ranks
    cells against a seed and prints the OCR lines, so an agent does not have to
    assemble all that from one-off code, which is what this module replaces.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Read a puzzle scan: grid, tiles, matches, text.")
    parser.add_argument("image", metavar="PAGE", help="the scan or photo")
    parser.add_argument("--size", type=int, default=10, help="cells per side (default 10)")
    parser.add_argument("--tiles", metavar="DIR", help="write one PNG per cell to DIR")
    parser.add_argument("--sheet", metavar="FILE", help="write a labelled contact sheet")
    parser.add_argument("--seed", metavar="CELL", help="rank cells against this one, e.g. r3c5")
    parser.add_argument("--top", type=int, default=10, help="how many ranked cells to print")
    parser.add_argument("--ocr", action="store_true", help="print the page's text lines and boxes")
    parser.add_argument("--ocr-language", metavar="LANG", help="OCR language: nl, en, or nl+en")
    arguments = parser.parse_args(argv)
    if arguments.ocr_language and not arguments.ocr:
        parser.error("--ocr-language requires --ocr")

    try:
        image = load(arguments.image)
        grid = find_grid(image, size=arguments.size)
        print("x lines:", grid.x)
        print("y lines:", grid.y)
        print(
            "pitches:",
            [b - a for a, b in pairwise(grid.x)],
            [b - a for a, b in pairwise(grid.y)],
        )
        board = tiles(image, grid)
        if arguments.tiles:
            import pathlib

            folder = pathlib.Path(arguments.tiles)
            folder.mkdir(parents=True, exist_ok=True)
            for (row, col), tile in board.items():
                _write_image(folder / f"r{row:02d}c{col:02d}.png", tile)
            print(f"wrote {len(board)} tiles to {folder}")
        if arguments.sheet:
            contact_sheet(board, arguments.sheet)
            print("wrote", arguments.sheet)
        if arguments.seed:
            for cell, score in rank_cells(board, _cell(arguments.seed))[: arguments.top]:
                print(f"  r{cell[0]:2d}c{cell[1]:2d}  {score:12.0f}")
        if arguments.ocr:
            for text, box in ocr(arguments.image, language=arguments.ocr_language):
                print(f"  {box[0]:.3f} {box[1]:.3f}  {text}")
    except ScanError as error:
        print(f"scan error: {error}")
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by hand
    raise SystemExit(main())
