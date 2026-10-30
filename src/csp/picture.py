"""Pictures of puzzles, drawn as SVG from the puzzle itself.

This is the one renderer: every family draws on an `svg.Canvas`, and PNG
(`--png`, README images) and the Word booklets are rasterised from that SVG.
Symbols come from the icon registry in `csp.icons`.

Every picture function takes the puzzle and an optional solution, and draws
one of three variants:

- blank: the puzzle only (no solution given),
- solution: the solved board, solved items in blue,
- interactive (`interactive=True`): the puzzle only, every cell a transparent
  element with an id such as `r3c4`.

Murdoku follows the style of the printed puzzles: region fills (darker where
an object stands), optional diagonal hatching, thick dark lines between
regions and thin white lines inside them, an icon per object, name tags for
people, and a legend. An object without an icon gets its name written in
the square.

Sudoku and Calcudoku share the look: thick lines around boxes or cages, thin
ones inside, givens in black and solved numbers in blue. Calcudoku cages get
pastel fills, no two touching cages alike, and their target in the corner.
"""

import math
import textwrap
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import icons
from .akari import Puzzle as Akari
from .akari import cell_name as akari_cell
from .battleships import Puzzle as Battleships
from .binairo import Puzzle as Binairo
from .binairo import cell_name as binairo_cell
from .calcudoku import Puzzle as Calcudoku
from .calcudoku import cell_name as calcudoku_cell
from .futoshiki import Puzzle as Futoshiki
from .futoshiki import cell_name as futoshiki_cell
from .kakurasu import Puzzle as Kakurasu
from .logicgrid import Puzzle as LogicGrid
from .minesweeper import Puzzle as Minesweeper
from .minesweeper import cell_name as minesweeper_cell
from .murdoku import Board, GlobalCountCondition, Square
from .queens import Cell as QueensCell
from .queens import Puzzle as Queens
from .starbattle import Puzzle as StarBattle
from .starbattle import cell_name as starbattle_cell
from .sudoku import Puzzle as Sudoku
from .sudoku import box_size
from .sudoku import cell_name as sudoku_cell
from .suguru import Puzzle as Suguru
from .suguru import cell_name as suguru_cell
from .svg import Canvas
from .tents import Puzzle as Tents

INK = (26, 26, 26)
WHITE = (255, 255, 255)
SOLVED = (33, 90, 200)  # numbers the solver filled in
EXTRA = (214, 214, 214)  # extra houses, grey as NRC prints them
THIN = (190, 190, 190)
MARK_FILL = (246, 249, 229)
MARK_INK = (57, 89, 66)
COUNT_SCOPE = (45, 110, 155)
TONGUE = (232, 106, 126)  # the puppy's tongue, see icons.PUPPY
# Used for regions the puzzle file gives no colour.
PALETTE = ["#F3C8C0", "#FADFB5", "#CBE6B9", "#D8D2F0", "#C4DCF2", "#BEE5D6", "#F3EDA2",
           "#DCDCDC", "#E0A79C", "#A9D6F0"]  # fmt: skip

type RGB = tuple[int, int, int]
type Box = tuple[int, int, int, int]
type Cell = tuple[int, int]


@dataclass(frozen=True)
class Mark:
    """A registry icon to draw in a cell, taking `scale` of the cell."""

    name: str
    scale: float = 0.72


type Value = str | int | Mark | None


def _upper_first(text: str) -> str:
    """Capitalise the first letter only, keeping names such as "El Greco"."""
    return text[:1].upper() + text[1:]


def cell_id(row: int, col: int) -> str:
    """The id of a cell in the interactive variant, as in the solver: r1c1 is top left."""
    return f"r{row + 1}c{col + 1}"


def murdoku_picture(
    board: Board,
    placed: Mapping[str, Square] | None = None,
    *,
    role_statuses: Mapping[tuple[str, str], bool | None] | None = None,
    global_counts: Sequence[GlobalCountCondition] = (),
    cell: int = 120,
    coordinates: bool = True,
    legend: bool = True,
    labels: bool = True,
    show_roles: bool = True,
    interactive: bool = False,
    language: str = "en",
    area_tags: bool = True,
    count_texts: Sequence[str] | None = None,
) -> Canvas:
    """The board, with `placed` people drawn on their squares if given.

    Without `legend` the picture is square, for documents with their own legend.
    With `labels` the board names each region in a small tag, and the legend
    then leaves out the region swatches.
    Without `show_roles` the legend leaves out the solver's role lines; without
    `area_tags` it leaves out the area tags (for documents that state them).
    `language` ("en" or "nl") sets the legend wording; `count_texts` gives
    the plain-language global counts (from `story`), else their clue syntax.
    """
    margin = _murdoku_margin(board, cell, coordinates)
    # Solver assignments also hold role booleans; only squares are people.
    placed = {k: v for k, v in (placed or {}).items() if isinstance(v, Square)}
    if interactive:
        placed = {}
    side = board.size * cell
    key = (
        _Legend(
            board,
            cell,
            role_statuses or {},
            global_counts,
            show_roles,
            language,
            regions=not labels,
            area_tags=area_tags,
            count_texts=count_texts,
        )
        if legend
        else None
    )
    # A backdrop widens the margin; the coordinates stay beside the board.
    reach = int(side * BACKDROP_REACH) if board.backdrop else 0
    height = side + 2 * margin + reach + (key.height if key else 0)
    headroom = _backdrop_headroom(board.backdrop, margin, side) if board.backdrop else 0
    canvas = Canvas(side + 2 * margin, height, headroom=headroom)
    fills = _fills(board)

    def box(sq: Square) -> Box:
        x, y = margin + sq.col * cell, margin + sq.row * cell
        return x, y, x + cell, y + cell

    if board.backdrop:
        _backdrop(canvas, board.backdrop, margin, side)
    blocked = board.blocked
    count_scope = {square for condition in global_counts for square in condition.scope_cells(board)}
    for r in range(board.size):
        for c in range(board.size):
            sq = Square(r, c)
            fill = fills[board.region_of(sq)]
            canvas.rectangle(box(sq), fill=_darker(fill) if sq in blocked else fill)
    _hatch(canvas, board, box, cell)
    _walls(
        canvas,
        board.size,
        margin,
        cell,
        lambda a, b: board.regions[a[0]][a[1]] == board.regions[b[0]][b[1]],
    )
    _draw_edge_item_doors(canvas, board, margin, cell)

    occupied = set(placed.values())
    for obj in board.objects:
        name = obj.name
        piece = obj.squares
        x0, y0, _, _ = box(min(piece))
        _, _, x1, y1 = box(max(piece))
        base = name.rstrip("0123456789").rstrip("_").lower()
        # Seats (bench/bank) keep their shape: a vertical seat is turned, never stretched.
        seat = base in SEAT_NAMES
        stretch = len(piece) > 1 and not seat
        if base in WELL_NAMES:
            icons.draw(canvas, "well", (x0, y0, x1, y1), stretch=True)
        elif base in TILED_NAMES:
            for square in piece:
                icons.draw(canvas, icons.OBJECT_ICONS[base], box(square), stretch=True)
        elif obj.kind == "standable":
            long_vertical = y1 - y0 > x1 - x0
            # The drawings have their back at the top; a side turns the back to that wall.
            if obj.side is not None:
                rotate = BACK_TURN[obj.side]
            else:
                rotate = 90 if (base == "bed" or seat) and long_vertical else 0
            # Standable objects are drawn faint: figures stand on them.
            with canvas.group(opacity=STANDABLE_OPACITY):
                if seat:
                    # Keep the seat's proportions and fit it to the whole footprint.
                    _icon(
                        canvas, name, (x0, y0, x1, y1), cell, scale=0.9, rotate=rotate, fit_box=True
                    )
                elif occupied & set(piece) and not stretch:
                    y1 = y0 + int(cell * 0.62)  # leave room for the name tag below
                    _icon(canvas, name, (x0, y0, x1, y1), cell, scale=0.95, rotate=rotate)
                else:
                    _icon(canvas, name, (x0, y0, x1, y1), cell, stretch=stretch, rotate=rotate)
        else:
            icon = icons.object_icon(name)
            vertical_panel = icon is not None and icon.name == "control_panel" and y1 - y0 > x1 - x0
            rotate = 90 if vertical_panel else 0
            _icon(canvas, name, (x0, y0, x1, y1), cell, stretch=stretch, rotate=rotate)
    for item in board.edge_items:
        if item.kind == "window" and item.side is not None:
            _draw_wall_window(canvas, box(item.cells[0]), item.side, cell)
        elif item.kind == "window":
            _icon(canvas, item.name, box(item.cells[0]), cell, scale=0.42)
    for point in board.point_objects:
        row2, col2 = point.anchor
        x = margin + (col2 - 1) * cell // 2
        y = margin + (row2 - 1) * cell // 2
        radius = cell // 3
        area = (x - radius, y - radius, x + radius, y + radius)
        if icons.object_icon(point.name) is None:
            _badge(canvas, point.name, area, cell)
        else:
            _icon(canvas, point.name, area, cell)
    for name, (row2, col2) in board.decorations:
        x = margin + (col2 - 1) * cell // 2
        y = margin + (row2 - 1) * cell // 2
        radius = cell // 3
        _icon(canvas, name, (x - radius, y - radius, x + radius, y + radius), cell)
    for square in count_scope:
        canvas.rectangle(box(square), outline=COUNT_SCOPE, width=max(2, cell // 40))
    marks_by_cell: dict[Square, list[str]] = {}
    for mark in board.marks:
        for square in mark.cells:
            marks_by_cell.setdefault(square, []).append(mark.name)
    for square, names in marks_by_cell.items():
        x0, y0, _, _ = box(square)
        pad = max(3, cell // 24)
        area = (x0 + pad, y0 + pad, x0 + pad + cell // 3, y0 + pad + cell // 4)
        canvas.rounded_rectangle(
            area,
            radius=max(2, cell // 30),
            fill=MARK_FILL,
            outline=MARK_INK,
            width=max(1, cell // 50),
        )
        initials = "/".join(name[:2].upper() for name in sorted(names))
        _centred_text(canvas, initials, area, max(8, cell // 12), MARK_INK, max_width=cell // 3)
    if labels:
        _region_labels(canvas, board, box, cell, set(placed.values()))
    standable = board.squares_of(obj.name for obj in board.standable_objects)
    for person, sq in placed.items():
        _name_tag(canvas, person, box(sq), cell, low=sq in standable)

    if coordinates:
        _coordinates(canvas, board.size, margin, cell, gap=cell // 4 if reach else None)
    if key:
        key.draw(canvas, margin, margin + side + reach + cell // 3)
    if interactive:
        _cells(canvas, board.size, margin, margin, cell)
    return canvas


STANDABLE_OPACITY = 0.55


def _region_labels(
    canvas: Canvas,
    board: Board,
    box: Callable[[Square], Box],
    cell: int,
    occupied: set[Square] | None = None,
) -> None:
    """A small name tag in each region, at the top of its first free square.

    Squares with an object, a mark, a top-wall window, a point object near their top edge or
    a placed person are passed over when the region has another; a long name may run on
    into the next square of the same region.
    """
    occupied = occupied or set()
    taken = {sq for obj in board.objects for sq in obj.squares}
    taken |= {sq for mark in board.marks for sq in mark.cells}
    crowded = {
        Square(r, c)
        for point in board.point_objects
        for r in range(board.size)
        for c in range(board.size)
        if point.anchor[0] in (2 * r + 1, 2 * r + 2)
        and point.anchor[1] in range(2 * c + 1, 2 * c + 4)
    }
    crowded |= {
        item.cells[0] for item in board.edge_items if item.kind == "window" and item.side == "top"
    }
    fills = _fills(board)
    size = max(8, cell // 7)
    pad = max(2, cell // 24)
    for rid, name in board.region_names.items():
        squares = sorted(
            Square(r, c)
            for r in range(board.size)
            for c in range(board.size)
            if board.region_of(Square(r, c)) == rid
        )
        if not squares:
            continue
        sq = min(
            squares,
            key=lambda s: (s in taken or s in board.blocked, s in crowded, s in occupied, s),
        )
        text = _upper_first(name.replace("_", " "))
        x0, y0, x1, _ = box(sq)
        right = Square(sq.row, sq.col + 1)
        wide = canvas.textlength(text, size) > cell - 4 * pad
        if wide and right in squares and right not in taken and right not in board.blocked:
            x1 = box(right)[2]
        tag = (x0 + pad, y0 + pad, x1 - pad, y0 + pad + int(size * 1.5))
        with canvas.group(opacity=0.9, class_name="area-label"):
            canvas.rounded_rectangle(
                tag,
                radius=max(2, cell // 16),
                fill=WHITE,
                outline=_darker(fills[rid], 0.6),
                width=max(1, cell // 60),
            )
        _centred_text(canvas, text, tag, size, INK, max_width=tag[2] - tag[0] - 2 * pad)


BACKDROP_REACH = 0.08  # how far a backdrop reaches past each board side, in board sides
BACKDROP_OPACITY = 0.85


def _backdrop(canvas: Canvas, name: str, margin: int, side: int) -> None:
    """Draw `name` (an icon name or `U+XXXX`) centred behind the board, reaching
    `BACKDROP_REACH` board sides past it, so the board seems to lie on it."""
    icon = icons.object_icon(name)
    if icon is None:
        return
    reach = int(side * BACKDROP_REACH)
    middle = margin + side // 2
    half = side // 2 + reach
    with canvas.group(opacity=BACKDROP_OPACITY):
        box = (middle - half, middle - half, middle + half, middle + half)
        icons.draw(canvas, icon, box, crop=True, stretch=True)


def _backdrop_headroom(name: str, margin: int, side: int) -> int:
    """Pixels a backdrop sticks out above the picture: a drawing with `bounds`
    (a cat with its ears) may reach past the part that lies behind the board."""
    icon = icons.object_icon(name)
    if icon is None or icon.bounds is None:
        return 0
    reach = int(side * BACKDROP_REACH)
    above = icon.bounds[1] - icon.view[1]
    scale = (side + 2 * reach) / (icon.bounds[3] - icon.bounds[1])
    return max(0, math.ceil(above * scale) - (margin - reach))


def _murdoku_margin(board: Board, cell: int, coordinates: bool) -> int:
    """Room around the board, widened so point objects on the outer edge are not clipped
    and a backdrop shows around the board.

    A point icon reaches `0.72 * cell / 3` (about 0.24 cell) past its anchor.
    Coordinate labels sit halfway into the top and left margins, so a point on
    those edges gets extra room to keep its icon off the labels.
    """
    if board.backdrop:
        return int(board.size * cell * BACKDROP_REACH) + cell // 4
    outer = {1, 2 * board.size + 1}
    anchors = [point.anchor for point in board.point_objects]
    anchors += [anchor for _, anchor in board.decorations]
    if not coordinates:
        on_edge = any(set(anchor) & outer for anchor in anchors)
        return cell // 4 + cell // 20 if on_edge else cell // 6
    top_left = any(1 in anchor for anchor in anchors)
    return cell // 2 + cell // 4 if top_left else cell // 2


def _badge(canvas: Canvas, name: str, area: Box, cell: int) -> None:
    """A small labelled disc for a point object without a picture icon."""
    x0, y0, x1, y1 = area
    pad = (x1 - x0) // 10
    disc = (x0 + pad, y0 + pad, x1 - pad, y1 - pad)
    canvas.ellipse(disc, fill=(255, 255, 255), outline=INK, width=max(1, cell // 60))
    _centred_text(canvas, name[:3], disc, max(8, cell // 8), INK, max_width=x1 - x0 - 4 * pad)


# Objects drawn with the registry's own drawings because Noto Emoji has no suitable picture.
CARPET_NAMES = frozenset(name for name, icon in icons.OBJECT_ICONS.items() if icon == "carpet")
WELL_NAMES = frozenset(name for name, icon in icons.OBJECT_ICONS.items() if icon == "well")
# Objects drawn once per square, so a long stretch of them repeats rather than stretches.
TILED_NAMES = frozenset(name for name, icon in icons.OBJECT_ICONS.items() if icon == "rails")
BACK_TURN = {"top": 0, "left": 90, "bottom": 180, "right": 270}
SEAT_NAMES = frozenset({"bench", "bank", "bankje", "parkbank"}) | frozenset(
    name
    for name, icon in icons.OBJECT_ICONS.items()
    if icon in ("train_bench", "platform_bench", "museum_bench")
)


def unknown_object_icons(board: Board) -> list[str]:
    """Object types that render with a text fallback instead of a picture icon."""
    return sorted(
        {
            name
            for name in (
                {obj.name for obj in board.objects}
                | {item.name for item in board.edge_items if item.kind == "window"}
                | board.point_object_names
            )
            if icons.object_icon(name) is None
        }
    )


def sudoku_picture(
    puzzle: Sudoku,
    solution: Mapping[str, int] | None = None,
    *,
    cell: int = 100,
    interactive: bool = False,
) -> Canvas:
    """The grid with its givens, and the solved numbers in blue if given.

    Square boxes are shaded alternately; jigsaw boxes get a pastel each.
    Extra houses (NRC boxes, X-Sudoku diagonals) are grey. Kropki dots sit on
    the edge between their cells; thermometers are grey bulbs and stems.
    """
    n, grid, boxes = puzzle.size, puzzle.grid, puzzle.boxes
    fills = _group_fills({(r, c): boxes[r][c] for r in range(n) for c in range(n)})
    box = box_size(n)
    extra = {cell for cells in puzzle.extra_houses().values() for cell in cells}
    solution = None if interactive else solution

    def shade(r: int, c: int) -> RGB:
        if (r, c) in extra:
            return EXTRA
        if puzzle.jigsaw:
            return fills[boxes[r][c]]
        if extra:
            return WHITE
        return (238, 242, 250) if (r // box + c // box) % 2 else WHITE

    def number(r: int, c: int) -> tuple[Value, RGB]:
        if grid[r][c]:
            return grid[r][c], INK
        return (solution or {}).get(sudoku_cell(r, c)), SOLVED

    def overlay(canvas: Canvas) -> None:
        margin = cell // 2
        for link in puzzle.links:
            if link.kind == "less":
                continue
            x = margin + (link.first[1] + link.second[1] + 1) * cell // 2
            y = margin + (link.first[0] + link.second[0] + 1) * cell // 2
            radius = max(6, cell // 13)
            dot = "dot_black" if link.kind == "black" else "dot_white"
            icons.draw(
                canvas, dot, (x - radius, y - radius, x + radius + 1, y + radius + 1), tint=INK
            )
        _thermometers(canvas, puzzle, cell)

    return _number_grid(
        n,
        cell,
        shade,
        number,
        lambda a, b: boxes[a[0]][a[1]] == boxes[b[0]][b[1]],
        overlay=overlay,
        interactive=interactive,
    )


def _thermometers(canvas: Canvas, puzzle: Sudoku, cell: int) -> None:
    """Draw each thermometer as a translucent grey bulb and stem."""
    links = [link for link in puzzle.links if link.kind == "less"]
    if not links:
        return
    margin = cell // 2
    grey = (120, 120, 120)
    width = max(6, cell // 7)

    def centre(square: tuple[int, int]) -> tuple[int, int]:
        return margin + square[1] * cell + cell // 2, margin + square[0] * cell + cell // 2

    with canvas.group(opacity=105 / 255):
        for link in links:
            canvas.line((centre(link.first), centre(link.second)), fill=grey, width=width)
        seconds = {link.second for link in links}
        for first in sorted({link.first for link in links} - seconds):
            x, y = centre(first)
            radius = cell // 4
            canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill=grey)


def calcudoku_picture(
    puzzle: Calcudoku,
    solution: Mapping[str, int] | None = None,
    *,
    cell: int = 100,
    interactive: bool = False,
) -> Canvas:
    """The cages with their targets (with printed signs), and the solved numbers if given."""
    fills = _cage_fills(puzzle)
    cage_at = puzzle.cage_at
    solution = None if interactive else solution

    def number(r: int, c: int) -> tuple[Value, RGB]:
        return (solution or {}).get(calcudoku_cell((r, c))), SOLVED

    def overlay(canvas: Canvas) -> None:
        margin = cell // 2
        for cage in puzzle.cages:
            r, c = min(cage.cells)
            corner = (margin + c * cell + cell // 10, margin + r * cell + cell // 14)
            canvas.text(corner, cage.display_label, INK, cell // 5, anchor="la")

    return _number_grid(
        puzzle.size,
        cell,
        lambda r, c: fills[cage_at[r, c]],
        number,
        lambda a, b: cage_at[a] is cage_at[b],
        overlay=overlay,
        interactive=interactive,
    )


def futoshiki_picture(
    puzzle: Futoshiki,
    solution: Mapping[str, int] | None = None,
    *,
    cell: int = 100,
    interactive: bool = False,
) -> Canvas:
    """The grid with its givens and signs, and the solved numbers in blue if given.

    Each sign is a chevron on the edge between its two cells, its point
    towards the smaller number.
    """
    grid = puzzle.grid
    solution = None if interactive else solution

    def number(r: int, c: int) -> tuple[Value, RGB]:
        if grid[r][c]:
            return grid[r][c], INK
        return (solution or {}).get(futoshiki_cell((r, c))), SOLVED

    def overlay(canvas: Canvas) -> None:
        margin, arm = cell // 2, cell // 9
        # The 'less' icon points left; turn it towards the smaller cell.
        turn = {(-1, 0): 0, (0, 1): 90, (1, 0): 180, (0, -1): 270}
        for sign in puzzle.signs:
            (r0, c0), (r1, c1) = sign.smaller, sign.larger
            mx = margin + (c0 + c1 + 1) * cell / 2
            my = margin + (r0 + r1 + 1) * cell / 2
            pad = arm + cell // 25
            canvas.rectangle((mx - pad, my - pad, mx + pad, my + pad), fill=WHITE)
            area = (mx - pad + 0.5, my - pad + 0.5, mx + pad + 0.5, my + pad + 0.5)
            icons.draw(canvas, "less", area, tint=INK, rotate=turn[c0 - c1, r0 - r1])

    return _number_grid(
        puzzle.size,
        cell,
        lambda r, c: WHITE,
        number,
        lambda a, b: True,
        overlay=overlay,
        interactive=interactive,
    )


def queens_picture(
    puzzle: Queens,
    solution: Mapping[str, QueensCell] | None = None,
    *,
    cell: int = 100,
    interactive: bool = False,
) -> Canvas:
    """Draw region colours and the placed queens (or dogs) in blue.

    `puzzle.icon` picks the piece from the registry: a crown, a dog or a puppy.
    """
    n = puzzle.size
    margin = cell // 2
    side = n * cell
    canvas = Canvas(side + 2 * margin, side + 2 * margin)
    region_at = {(r, c): puzzle.grid[r][c] for r in range(n) for c in range(n)}
    fills = _group_fills(region_at)
    if puzzle.icon != "queen" and n <= len(PALETTE):
        # dog puzzles give every zone its own colour, in region order
        fills = {region: _rgb(PALETTE[i]) for i, region in enumerate(puzzle.region_ids)}
    for (row, col), region in region_at.items():
        x, y = margin + col * cell, margin + row * cell
        canvas.rectangle((x, y, x + cell, y + cell), fill=fills[region])
    _walls(canvas, n, margin, cell, lambda a, b: region_at[a] == region_at[b], thin_colour=THIN)

    def piece(queen: QueensCell, colour: RGB) -> None:
        x, y = margin + queen.col * cell, margin + queen.row * cell
        icons.draw(canvas, puzzle.icon, (x, y, x + cell, y + cell), tint=colour, stretch=True)

    given_cells = set(puzzle.givens.values())
    for queen in given_cells:
        piece(queen, INK)
    for queen in ({} if interactive else solution or {}).values():
        if queen not in given_cells:
            piece(queen, SOLVED)
    _coordinates(canvas, n, margin, cell)
    if interactive:
        _cells(canvas, n, margin, margin, cell)
    return canvas


def suguru_picture(
    puzzle: Suguru,
    solution: Mapping[str, int] | None = None,
    *,
    cell: int = 100,
    interactive: bool = False,
) -> Canvas:
    """Draw Suguru regions and values, with solved values in blue."""
    region_at = {
        (r, c): puzzle.areas.cells[r][c] for r in range(puzzle.size) for c in range(puzzle.size)
    }
    fills = _group_fills(region_at)
    solution = None if interactive else solution

    def number(row: int, col: int) -> tuple[Value, RGB]:
        given = puzzle.givens[row][col]
        if given:
            return given, INK
        return (solution or {}).get(suguru_cell((row, col))), SOLVED

    return _number_grid(
        puzzle.size,
        cell,
        lambda row, col: fills[region_at[row, col]],
        number,
        lambda first, second: region_at[first] == region_at[second],
        interactive=interactive,
    )


def starbattle_picture(
    puzzle: StarBattle,
    solution: Mapping[str, bool] | None = None,
    *,
    cell: int = 100,
    interactive: bool = False,
) -> Canvas:
    """Draw Star Battle regions, given stars in ink and solved stars in blue."""
    region_at = {
        (r, c): puzzle.areas.cells[r][c] for r in range(puzzle.size) for c in range(puzzle.size)
    }
    fills = _group_fills(region_at)
    solution = None if interactive else solution
    star = Mark("star", 0.62)

    def mark(row: int, col: int) -> tuple[Value, RGB]:
        if puzzle.givens[row][col] == 1:
            return star, INK
        if solution is not None and solution.get(starbattle_cell((row, col))):
            return star, SOLVED
        return None, INK

    return _number_grid(
        puzzle.size,
        cell,
        lambda row, col: fills[region_at[row, col]],
        mark,
        lambda first, second: region_at[first] == region_at[second],
        interactive=interactive,
    )


def binairo_picture(
    puzzle: Binairo,
    solution: Mapping[str, bool] | None = None,
    *,
    cell: int = 100,
    interactive: bool = False,
) -> Canvas:
    """Draw ones as black discs and zeros as white discs, solved ones in blue.

    Tango signs (equal and different) sit in a badge on the edge between their cells.
    """
    solution = None if interactive else solution

    def disc(one: bool) -> Mark:
        return Mark("disc_black" if one else "disc_white", 0.7)

    def value(row: int, col: int) -> tuple[Value, RGB]:
        given = puzzle.givens[row][col]
        if given >= 0:
            return disc(given == 1), INK
        chosen = (solution or {}).get(binairo_cell((row, col)))
        return (disc(chosen), SOLVED) if chosen is not None else (None, INK)

    def overlay(canvas: Canvas) -> None:
        margin = cell // 2
        radius = max(10, cell // 7)
        for sign in puzzle.signs:
            first_row, first_col = sign.first
            second_row, second_col = sign.second
            if first_row == second_row:
                x = margin + max(first_col, second_col) * cell
                y = margin + first_row * cell + cell // 2
            else:
                x = margin + first_col * cell + cell // 2
                y = margin + max(first_row, second_row) * cell
            canvas.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=WHITE,
                outline=INK,
                width=max(2, cell // 35),
            )
            inner = radius * 0.7
            name = "equal" if sign.kind == "equal" else "different"
            area = (x + 0.5 - inner, y + 0.5 - inner, x + 0.5 + inner, y + 0.5 + inner)
            icons.draw(canvas, name, area, tint=INK)

    return _number_grid(
        puzzle.size,
        cell,
        lambda row, col: WHITE,
        value,
        lambda first, second: True,
        overlay=overlay,
        interactive=interactive,
    )


def tents_picture(
    puzzle: Tents,
    solution: Mapping[str, bool] | None = None,
    *,
    cell: int = 78,
    interactive: bool = False,
) -> Canvas:
    """Draw trees, tent placements and their row/column counts."""
    fixed: dict[Cell, tuple[Value, RGB]] = {tree: (Mark("tree"), INK) for tree in puzzle.trees}
    return _line_count_picture(
        puzzle.size,
        puzzle.row_counts,
        puzzle.column_counts,
        None if interactive else solution,
        cell=cell,
        fixed=fixed,
        solved_mark=Mark("tent"),
        interactive=interactive,
    )


def minesweeper_picture(
    puzzle: Minesweeper,
    solution: Mapping[str, bool] | None = None,
    *,
    cell: int = 78,
    interactive: bool = False,
) -> Canvas:
    """Draw clue numbers in ink and the mines of the solved board."""
    solution = None if interactive else solution

    def value(row: int, col: int) -> tuple[Value, RGB]:
        clue = puzzle.clues[row][col]
        if clue is not None:
            return clue, INK
        if (solution or {}).get(minesweeper_cell((row, col)), False):
            return Mark("mine"), SOLVED
        return None, INK

    return _number_grid(
        puzzle.size,
        cell,
        lambda row, col: WHITE,
        value,
        lambda first, second: True,
        interactive=interactive,
    )


def akari_picture(
    puzzle: Akari,
    solution: Mapping[str, bool] | None = None,
    *,
    cell: int = 78,
    interactive: bool = False,
) -> Canvas:
    """Draw Akari walls (grey, with their numbers) and solved bulbs."""
    solution = None if interactive else solution

    def shade(row: int, col: int) -> RGB:
        return (218, 218, 218) if puzzle.board[row][col] != "." else WHITE

    def value(row: int, col: int) -> tuple[Value, RGB]:
        marker = puzzle.board[row][col]
        if marker != ".":
            return (marker if marker.isdigit() else None), INK
        if (solution or {}).get(akari_cell((row, col)), False):
            return Mark("bulb"), SOLVED
        return None, INK

    return _number_grid(
        puzzle.size, cell, shade, value, lambda first, second: True, interactive=interactive
    )


def kakurasu_picture(
    puzzle: Kakurasu,
    solution: Mapping[str, bool] | None = None,
    *,
    cell: int = 78,
    interactive: bool = False,
) -> Canvas:
    """Draw selected Kakurasu cells and weighted row/column totals."""
    fixed: dict[Cell, tuple[Value, RGB]] = {
        (row, col): (Mark("filled", 0.9), INK)
        for row in range(puzzle.size)
        for col in range(puzzle.size)
        if puzzle.givens[row][col] == 1
    }
    return _line_count_picture(
        puzzle.size,
        puzzle.row_sums,
        puzzle.column_sums,
        None if interactive else solution,
        cell=cell,
        fixed=fixed,
        solved_mark=Mark("filled", 0.9),
        interactive=interactive,
    )


def battleships_picture(
    puzzle: Battleships,
    solution: Mapping[str, bool] | None = None,
    *,
    cell: int = 78,
    interactive: bool = False,
) -> Canvas:
    """Draw line totals, shaped ship givens and the fleet, when present."""
    shapes = {
        "O": "ship_single",
        "N": "ship_north",
        "S": "ship_south",
        "W": "ship_west",
        "E": "ship_east",
        "M": "ship_middle",
    }
    fixed: dict[Cell, tuple[Value, RGB]] = {
        (row, col): (
            (
                "?"
                if puzzle.fleet and puzzle.segments[row][col] == "1"
                else Mark(shapes.get(puzzle.segments[row][col], "filled"), 0.9)
            )
            if puzzle.givens[row][col]
            else Mark("water"),
            INK,
        )
        for row in range(puzzle.size)
        for col in range(puzzle.size)
        if puzzle.givens[row][col] >= 0
    }
    if solution is not None and not interactive and puzzle.fleet:
        cells = {
            (r, c)
            for r in range(puzzle.size)
            for c in range(puzzle.size)
            if solution.get(f"r{r + 1}c{c + 1}")
        }
        for r, c in cells:
            if (r, c) in fixed:
                continue
            neighbors = {(nr - r, nc - c) for nr, nc in cells if abs(nr - r) + abs(nc - c) == 1}
            shape = "ship_single" if not neighbors else "ship_middle"
            if len(neighbors) == 1:
                shape = {
                    (1, 0): "ship_north",
                    (-1, 0): "ship_south",
                    (0, 1): "ship_west",
                    (0, -1): "ship_east",
                }[next(iter(neighbors))]
            fixed[(r, c)] = Mark(shape, 0.9), SOLVED
    return _line_count_picture(
        puzzle.size,
        puzzle.row_counts,
        puzzle.column_counts,
        None if interactive else solution,
        cell=cell,
        fixed=fixed,
        solved_mark=Mark("filled", 0.9),
        interactive=interactive,
        fleet=puzzle.fleet,
    )


def logicgrid_picture(
    puzzle: LogicGrid,
    solution: Mapping[str, int] | None = None,
    *,
    cell: int = 64,
    interactive: bool = False,
) -> Canvas:
    """Draw one item-to-position matrix per logic-grid category.

    In the interactive variant the cell of item i of category k at position p
    has the id `k{k}i{i}p{p}`, all counted from 1.
    """
    left = max(90, max(len(item) for items in puzzle.categories.values() for item in items) * 9)
    top, row_height = cell // 2, max(34, cell // 2)
    width = left + puzzle.size * cell + cell // 2
    clue_lines = [
        line
        for clue in puzzle.clues
        for line in textwrap.wrap(clue.label, width=max(24, (width - 16) // 8))
    ]
    table_height = sum(len(items) + 1 for items in puzzle.categories.values()) * row_height
    height = top + table_height + (len(clue_lines) + 2) * row_height + cell // 2
    canvas = Canvas(width, height)
    size = max(10, cell // 4)
    small = max(9, cell // 5)
    solution = None if interactive else solution
    y = top
    for k, (category, items) in enumerate(puzzle.categories.items(), 1):
        canvas.rectangle((0, y, width, y + row_height), fill=(232, 237, 244))
        canvas.text((8, y + row_height // 2), category, INK, size, anchor="lm")
        for position in range(1, puzzle.size + 1):
            x = left + (position - 1) * cell
            canvas.text((x + cell // 2, y + row_height // 2), str(position), INK, small, "mm")
        y += row_height
        for i, item in enumerate(items, 1):
            canvas.text((8, y + row_height // 2), item, INK, small, anchor="lm")
            canvas.line((left, y, left + puzzle.size * cell, y), fill=THIN, width=1)
            for position in range(1, puzzle.size + 1):
                x = left + (position - 1) * cell
                canvas.rectangle((x, y, x + cell, y + row_height), outline=THIN, width=1)
                if solution and solution.get(item) == position:
                    side = row_height * 0.7
                    cx, cy = x + cell / 2 + 0.5, y + row_height / 2 + 0.5
                    area = (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
                    icons.draw(canvas, "check", area, tint=SOLVED)
                if interactive:
                    canvas.cell(f"k{k}i{i}p{position}", (x, y, x + cell, y + row_height))
            y += row_height
    y += row_height // 2
    canvas.text((8, y), "Clues", INK, size, anchor="lt")
    y += row_height
    for clue_line in clue_lines:
        canvas.text((8, y), clue_line, INK, small, anchor="lt")
        y += row_height
    return canvas


def _line_count_picture(
    n: int,
    row_counts: Sequence[int],
    column_counts: Sequence[int],
    solution: Mapping[str, bool] | None,
    *,
    cell: int,
    fixed: Mapping[Cell, tuple[Value, RGB]] | None = None,
    solved_mark: Value = None,
    interactive: bool = False,
    fleet: Sequence[int] = (),
) -> Canvas:
    margin = cell // 2
    left = margin + cell // 2
    top = margin + cell // 2
    side = n * cell
    canvas = Canvas(left + side + cell // 4, top + side + cell // 4 + (cell if fleet else 0))
    _walls(canvas, n, left, cell, lambda first, second: False)
    size = max(10, cell // 4)
    for row, target in enumerate(row_counts):
        y = top + row * cell + cell // 2
        canvas.text((left - cell // 4, y), str(target), INK, size, anchor="rm")
    for col, target in enumerate(column_counts):
        x = left + col * cell + cell // 2
        canvas.text((x, top - cell // 4), str(target), INK, size, anchor="mm")
    for (row, col), (mark, colour) in (fixed or {}).items():
        _value(canvas, mark, colour, left + col * cell, top + row * cell, cell, max(12, cell // 2))
    for key, occupied in (solution or {}).items():
        if occupied:
            row_text, col_text = key[1:].split("c")
            row, col = int(row_text) - 1, int(col_text) - 1
            if (row, col) in (fixed or {}):
                continue
            x, y = left + col * cell, top + row * cell
            _value(canvas, solved_mark, SOLVED, x, y, cell, max(12, cell // 2))
    if interactive:
        _cells(canvas, n, left, top, cell)
    if fleet:
        mini = min(cell // 3, side // (sum(fleet) + len(fleet)))
        x, y = left, top + side + cell // 4
        for length in fleet:
            for index in range(length):
                icon = (
                    "ship_single"
                    if length == 1
                    else (
                        "ship_west"
                        if index == 0
                        else "ship_east"
                        if index == length - 1
                        else "ship_middle"
                    )
                )
                icons.draw(canvas, icon, (x, y, x + mini, y + mini), tint=INK)
                x += mini
            x += mini
    return canvas


def _value(canvas: Canvas, value: Value, colour: RGB, x: int, y: int, cell: int, size: int) -> None:
    """Draw a number, text or registry icon in the middle of the cell at (x, y)."""
    if value is None:
        return
    if isinstance(value, Mark):
        side = cell * value.scale
        cx, cy = x + cell / 2 + 0.5, y + cell / 2 + 0.5
        icons.draw(canvas, value.name, (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2),
                   tint=colour)  # fmt: skip
    else:
        canvas.text((x + cell / 2, y + cell * 0.56), str(value), colour, size, anchor="mm")


def _number_grid(
    n: int,
    cell: int,
    shade: Callable[[int, int], RGB],
    number: Callable[[int, int], tuple[Value, RGB]],
    together: Callable[[Cell, Cell], bool],
    *,
    overlay: Callable[[Canvas], None] | None = None,
    interactive: bool = False,
) -> Canvas:
    """A square grid of numbers or icons: shaded cells, walls between groups, coordinates.

    `overlay` draws family extras (signs, dots, cage targets) over the grid.
    """
    margin = cell // 2
    side = n * cell
    canvas = Canvas(side + 2 * margin, side + 2 * margin)
    for r in range(n):
        for c in range(n):
            x, y = margin + c * cell, margin + r * cell
            canvas.rectangle((x, y, x + cell, y + cell), fill=shade(r, c))
    _walls(canvas, n, margin, cell, together, thin_colour=THIN)
    for r in range(n):
        for c in range(n):
            value, colour = number(r, c)
            x, y = margin + c * cell, margin + r * cell
            _value(canvas, value, colour, x, y, cell, int(cell * 0.5))
    if overlay:
        overlay(canvas)
    _coordinates(canvas, n, margin, cell)
    if interactive:
        _cells(canvas, n, margin, margin, cell)
    return canvas


def _cells(canvas: Canvas, n: int, left: int, top: int, cell: int) -> None:
    for r in range(n):
        for c in range(n):
            x, y = left + c * cell, top + r * cell
            canvas.cell(cell_id(r, c), (x, y, x + cell, y + cell))


def _cage_fills(puzzle: Calcudoku) -> dict[object, RGB]:
    """A pastel per cage, never the same as a cage it touches."""
    return _group_fills(dict(puzzle.cage_at))


def _group_fills(group_at: Mapping[Cell, Hashable]) -> dict[Any, RGB]:
    """A pastel per group of cells, never the same as a group it touches."""
    colours = [_rgb(p) for p in PALETTE]
    fills: dict[Any, RGB] = {}
    for _, group in sorted(group_at.items()):
        if group in fills:
            continue
        touching = {
            fills.get(group_at[nb])
            for (gr, gc), g in group_at.items()
            if g == group
            for nb in ((gr, gc + 1), (gr + 1, gc), (gr, gc - 1), (gr - 1, gc))
            if nb in group_at and group_at[nb] != group
        }
        fills[group] = next((x for x in colours if x not in touching), colours[0])
    return fills


# --- regions --------------------------------------------------------------


def _fills(board: Board) -> dict[str, RGB]:
    out = {}
    for i, rid in enumerate(board.region_names):
        colour = board.colours.get(rid) or PALETTE[i % len(PALETTE)]
        out[rid] = _rgb(colour)
    return out


def _rgb(hex_colour: str) -> RGB:
    value = hex_colour.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


# Blocked squares (nobody can stand there) are this much darker than their region.
BLOCKED_SHADE = 0.75


def _darker(colour: RGB, factor: float = BLOCKED_SHADE) -> RGB:
    r, g, b = colour
    return round(r * factor), round(g * factor), round(b * factor)


def _hatch(canvas: Canvas, board: Board, box: Callable[[Square], Box], cell: int) -> None:
    """Thin diagonal lines over hatched regions, as on the printed boards.

    Stripes follow one global pattern (constant x + y), so they run on
    unbroken from square to square.
    """
    squares = [
        Square(r, c)
        for r in range(board.size)
        for c in range(board.size)
        if board.region_of(Square(r, c)) in board.hatched
    ]
    if not squares:
        return
    step = max(6, cell // 7)
    width = max(2, cell // 30)
    boxes = [box(sq) for sq in squares]
    top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
    low, high = min(b[0] + b[1] for b in boxes), max(b[2] + b[3] for b in boxes)
    with canvas.group(opacity=60 / 255, clip=boxes):
        for k in range(low // step * step, high + step, step):
            # The line x + y = k.
            canvas.line([(k - top, top), (k - bottom, bottom)], fill=(60, 60, 60), width=width)


def _walls(
    canvas: Canvas,
    n: int,
    margin: int,
    cell: int,
    together: Callable[[Cell, Cell], bool],
    thin_colour: RGB = WHITE,
) -> None:
    """Thin lines between cells that are `together`, thick walls elsewhere."""
    thin = max(2, cell // 40)
    thick = max(5, cell // 22) | 1  # odd, so both directions centre alike
    walls: list[tuple[int, int, int, int]] = []
    for r in range(n):
        for c in range(n):
            x, y = margin + c * cell, margin + r * cell
            if c + 1 < n:
                line = (x + cell, y, x + cell, y + cell)
                same = together((r, c), (r, c + 1))
                (canvas.line(line, fill=thin_colour, width=thin) if same else walls.append(line))
            if r + 1 < n:
                line = (x, y + cell, x + cell, y + cell)
                same = together((r, c), (r + 1, c))
                (canvas.line(line, fill=thin_colour, width=thin) if same else walls.append(line))
    side = n * cell
    low, high = margin, margin + side
    horizontal_ends = {p for x0, y0, x1, y1 in walls if y0 == y1 for p in ((x0, y0), (x1, y1))}
    vertical_ends = {p for x0, y0, x1, y1 in walls if x0 == x1 for p in ((x0, y0), (x1, y1))}
    for x0, y0, x1, y1 in walls:
        # Extend an end by half the width only where a crossing wall meets it, so
        # corners close squarely and no wall pokes into a cell.
        across = vertical_ends if y0 == y1 else horizontal_ends
        grow = [thick // 2 if end in across else 0 for end in ((x0, y0), (x1, y1))]
        if y0 == y1:
            x0, x1 = max(low, x0 - grow[0]), min(high, x1 + grow[1])
        else:
            y0, y1 = max(low, y0 - grow[0]), min(high, y1 + grow[1])
        canvas.line((x0, y0, x1, y1), fill=INK, width=thick)
    canvas.rectangle((low, low, high, high), outline=INK, width=thick)


def _draw_edge_item_doors(canvas: Canvas, board: Board, margin: int, cell: int) -> None:
    """Mark each simple door on the shared edge between its two cells."""
    wood = (117, 75, 47)
    width = max(4, cell // 10)
    for item in board.edge_items:
        if item.kind != "door":
            continue
        first, second = item.cells
        if first.row == second.row:
            x = margin + max(first.col, second.col) * cell
            y = margin + first.row * cell + cell // 2
            canvas.line((x, y - cell // 4, x, y + cell // 4), fill=wood, width=width)
        else:
            x = margin + first.col * cell + cell // 2
            y = margin + max(first.row, second.row) * cell
            canvas.line((x - cell // 4, y, x + cell // 4, y), fill=wood, width=width)


def _draw_wall_window(canvas: Canvas, area: Box, side: str, cell: int) -> None:
    """A shallow window pane as wide as the cell, set against its `side` wall."""
    x0, y0, x1, y1 = area
    depth, inset = max(4, cell // 7), cell // 10
    pane = {
        "top": (x0 + inset, y0, x1 - inset, y0 + depth),
        "bottom": (x0 + inset, y1 - depth, x1 - inset, y1),
        "left": (x0, y0 + inset, x0 + depth, y1 - inset),
        "right": (x1 - depth, y0 + inset, x1, y1 - inset),
    }[side]
    frame = (73, 88, 106)
    canvas.rectangle(pane, fill=(208, 228, 242), outline=frame, width=max(2, cell // 40))
    px0, py0, px1, py1 = pane
    if side in ("top", "bottom"):
        for k in (1, 2):
            x = px0 + (px1 - px0) * k / 3
            canvas.line((x, py0, x, py1), fill=frame, width=max(1, cell // 60))
    else:
        for k in (1, 2):
            y = py0 + (py1 - py0) * k / 3
            canvas.line((px0, y, px1, y), fill=frame, width=max(1, cell // 60))


# --- things on the board --------------------------------------------------


def _icon(
    canvas: Canvas,
    name: str,
    area: Box,
    cell: int,
    scale: float = 0.72,
    stretch: bool = False,
    rotate: float = 0,
    fit_box: bool = False,
) -> None:
    """Draw `name`'s icon centred in `area`; `stretch` fills the area instead.

    `fit_box` keeps the aspect ratio but fits the icon to the whole area, so a
    long seat spanning two squares is drawn long rather than one square big.
    Registry drawings without a picture (carpet, well) always fill the area.
    `rotate` turns the icon counter-clockwise by that many degrees.
    """
    x0, y0, x1, y1 = area
    icon = icons.object_icon(name)
    if icon is None:
        _centred_text(canvas, name[:6], area, cell // 5, INK)
        return
    turn = rotate
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if icon.emoji is None:
        icons.draw(canvas, icon, area, stretch=True, rotate=turn)
    elif stretch:
        pad = cell // 10
        icons.draw(
            canvas, icon, (x0 + pad, y0 + pad, x1 - pad, y1 - pad), stretch=True, rotate=turn
        )
    elif fit_box:
        w, h = (x1 - x0) * scale, (y1 - y0) * scale
        icons.draw(canvas, icon, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), crop=True,
                   rotate=turn)  # fmt: skip
    else:
        side = min(x1 - x0, y1 - y0) * scale
        half = side / 2
        icons.draw(canvas, icon, (cx - half, cy - half, cx + half, cy + half), rotate=turn)


def _name_tag(canvas: Canvas, person: str, area: Box, cell: int, low: bool = False) -> None:
    x0, y0, x1, _ = area
    pad = cell // 10
    top = y0 + int(cell * 0.6) if low else y0 + cell // 3
    tag = (x0 + pad, top, x1 - pad, top + cell // 3)
    canvas.rounded_rectangle(
        tag, radius=cell // 8, fill=WHITE, outline=INK, width=max(2, cell // 40)
    )
    _centred_text(canvas, person, tag, cell // 5, INK, max_width=cell - 3 * pad)


def _centred_text(
    canvas: Canvas,
    text: str,
    area: Box,
    size: int,
    colour: RGB,
    max_width: int | None = None,
) -> None:
    x0, y0, x1, y1 = area
    while max_width and size > 8 and canvas.textlength(text, size) > max_width:
        size -= 1
    canvas.text(((x0 + x1) / 2, (y0 + y1) / 2), text, colour, size, anchor="mm")


def _coordinates(canvas: Canvas, n: int, margin: int, cell: int, gap: float | None = None) -> None:
    """Row and column numbers `gap` pixels (default half the margin) left of and
    above the board; a smaller gap, over a backdrop, gets darker numbers with a
    white halo so they read on any picture."""
    size = cell // 5
    grey = (120, 120, 120) if gap is None else (60, 40, 30)
    halo = None if gap is None else (255, 255, 255)
    gap = margin / 2 if gap is None else gap
    for i in range(n):
        middle = margin + i * cell + cell / 2
        canvas.text((middle, margin - gap), str(i + 1), grey, size, anchor="mm", halo=halo)
        canvas.text((margin - gap, middle), str(i + 1), grey, size, anchor="mm", halo=halo)


# --- legend ---------------------------------------------------------------

LEGEND_WORDS = {
    "en": {"door": "Door", "window": "Window", "point": "Point", "cells": "cells",
           "alone": "alone in area", "not_alone": "shares area", "global": "Global",
           "maybe": "maybe", "apart": "at most one of these per area", "one": "a {name}"},
    "nl": {"door": "Deur", "window": "Raam", "point": "Punt", "cells": "vakjes",
           "alone": "alleen in het gebied", "not_alone": "deelt het gebied",
           "global": "Telling", "maybe": "misschien",
           "apart": "niet meer dan 1 hiervan per gebied", "one": "een {name}"},
}  # fmt: skip


class _Legend:
    """Under the board, two per row: region swatches (unless the board names its regions),
    then doors, windows and point objects; then marks, roles, attributes, area tags and counts."""

    def __init__(
        self,
        board: Board,
        cell: int,
        role_statuses: Mapping[tuple[str, str], bool | None] | None = None,
        global_counts: Sequence[GlobalCountCondition] = (),
        show_roles: bool = True,
        language: str = "en",
        regions: bool = True,
        area_tags: bool = True,
        count_texts: Sequence[str] | None = None,
    ) -> None:
        self.words = LEGEND_WORDS.get(language, LEGEND_WORDS["en"])
        self.board = board
        self.cell = cell
        self.role_statuses = role_statuses or {}
        self.global_counts = tuple(global_counts)
        self.swatch = cell // 3
        self.line = int(self.swatch * 1.6)
        self.region_items = list(board.region_names.items()) if regions else []
        self.rows = (len(self.region_items) + 1) // 2
        self.item_names = sorted(board.edge_item_names | board.point_object_names)
        self.item_rows = (len(self.item_names) + 1) // 2
        self.mark_names = sorted(board.mark_names)
        self.role_names = sorted(board.role_names) if show_roles else []
        self.attribute_names = [
            name
            for name, holders in sorted(board.attributes.items())
            if not any(
                role.name == name
                and role.name in self.role_names
                and role.eligible_people == holders
                and role.allowed_counts == {len(holders)}
                for role in board.roles
            )
        ]
        self.tag_lines = [
            f"{tag.replace('_', ' ').capitalize()}: "
            + ", ".join(
                _upper_first(board.region_names[rid].replace("_", " "))
                for rid in board.region_names
                if rid in board.region_ids(members)
            )
            for tag, members in (board.area_tags.items() if area_tags else ())
        ]
        self.count_size = max(10, cell // 10)
        self.count_line = int(self.count_size * 1.6)
        max_chars = max(18, int(board.size * cell / (self.count_size * 0.55)))
        self.global_count_lines = [
            lines
            for index, condition in enumerate(self.global_counts, 1)
            for lines in [
                textwrap.wrap(
                    f"{self.words['global']} {condition.number or index}: "
                    + (count_texts[index - 1] if count_texts else condition.description),
                    width=max_chars,
                )
            ]
        ]
        self.count_rows = sum(max(1, len(lines)) for lines in self.global_count_lines)
        self.height = (
            (
                self.rows
                + self.item_rows
                + len(self.mark_names)
                + len(self.role_names)
                + len(self.attribute_names)
                + len(self.tag_lines)
            )
            * self.line
            + self.count_rows * self.count_line
            + cell // 6
        )

    def _item_label(self, kind: str, name: str) -> str:
        """'Door: gate', or just 'Door' when the item is simply called that."""
        word, shown = self.words[kind], name.replace("_", " ")
        return word if shown.lower() in (word.lower(), kind) else f"{word}: {shown}"

    def draw(self, canvas: Canvas, x: int, y: int) -> None:
        fills = _fills(self.board)
        size = int(self.swatch * 0.8)
        column = self.board.size * self.cell // 2

        def label(top: int, text: str, font_size: int = size, left: int = x) -> None:
            middle = (left + self.swatch + self.swatch // 2, top + self.swatch / 2)
            canvas.text(middle, text, INK, font_size, anchor="lm")

        for i, (rid, name) in enumerate(self.region_items):
            left = x + (i % 2) * column
            top = y + (i // 2) * self.line
            square = (left, top, left + self.swatch, top + self.swatch)
            canvas.rectangle(square, fill=fills[rid], outline=INK, width=2)
            if rid in self.board.hatched:
                for k in range(0, 2 * self.swatch, max(5, self.swatch // 4)):
                    canvas.line(
                        [(left + max(0, k - self.swatch), top + min(k, self.swatch)),
                         (left + min(k, self.swatch), top + max(0, k - self.swatch))],
                        fill=(110, 110, 110), width=1,
                    )  # fmt: skip
            middle = (left + self.swatch + self.swatch // 2, top + self.swatch / 2)
            canvas.text(middle, name.replace("_", " ").capitalize(), INK, size, anchor="lm")
        for i, name in enumerate(self.item_names):
            left = x + (i % 2) * column
            top = y + (self.rows + i // 2) * self.line
            area = (left, top, left + self.swatch, top + self.swatch)
            if name in self.board.edge_item_names and self.board.edge_item_kind(name) == "door":
                canvas.line(
                    (left, top + self.swatch // 2, left + self.swatch, top + self.swatch // 2),
                    fill=(117, 75, 47),
                    width=max(4, self.swatch // 5),
                )
                label(top, self._item_label("door", name), left=left)
            else:
                _icon(canvas, name, area, self.cell, scale=0.8)
                kind = "window" if name in self.board.edge_item_names else "point"
                label(top, self._item_label(kind, name), left=left)
        for i, name in enumerate(self.mark_names):
            top = y + (self.rows + self.item_rows + i) * self.line
            area = (x, top, x + self.swatch, top + self.swatch)
            canvas.rounded_rectangle(
                area,
                radius=max(2, self.swatch // 8),
                fill=MARK_FILL,
                outline=MARK_INK,
                width=2,
            )
            _centred_text(
                canvas,
                name[:2].upper(),
                area,
                max(8, self.cell // 6),
                MARK_INK,
                max_width=self.swatch - 4,
            )
            mark = next(item for item in self.board.marks if item.name == name)
            condition = mark.occupant_condition or ""
            label(
                top,
                f"{name}: {self.words[condition]}"
                if condition
                else f"{name} {self.words['cells']}",
            )
        role_offset = self.rows + self.item_rows + len(self.mark_names)
        for i, name in enumerate(self.role_names):
            top = y + (role_offset + i) * self.line
            area = (x, top, x + self.swatch, top + self.swatch)
            canvas.rectangle(area, fill=MARK_FILL, outline=MARK_INK, width=2)
            _centred_text(canvas, name[:2].upper(), area, max(8, self.swatch // 2), MARK_INK)
            label(top, self._role_line(name), max(8, self.swatch // 2))
        tag_offset = role_offset + len(self.role_names)
        attribute_offset = tag_offset
        for i, name in enumerate(self.attribute_names):
            top = y + (attribute_offset + i) * self.line
            area = (x, top, x + self.swatch, top + self.swatch)
            if icons.object_icon(name) is not None:
                # Without a picture the swatch stays empty: the label names the trait.
                _icon(canvas, name, area, self.cell, scale=0.8)
            holders = ", ".join(sorted(self.board.attributes[name]))
            label(top, f"{name.replace('_', ' ').capitalize()}: {holders}")
        tag_offset = attribute_offset + len(self.attribute_names)
        for i, line in enumerate(self.tag_lines):
            top = y + (tag_offset + i) * self.line
            canvas.text((x, top + self.swatch / 2), line, INK, size, anchor="lm")
        top = y + (tag_offset + len(self.tag_lines)) * self.line
        for lines in self.global_count_lines:
            for line in lines or [""]:
                middle = (x, top + self.count_line / 2)
                canvas.text(middle, line, COUNT_SCOPE, self.count_size, anchor="lm")
                top += self.count_line

    def _role_line(self, name: str) -> str:
        """Who holds the role, who may, and whether holders are in different areas."""
        role = next(item for item in self.board.roles if item.name == name)
        status = {person: self.role_statuses.get((person, name)) for person in self.board.people}
        if role.eligible_people is not None:
            status = {p: (k if p in role.eligible_people else False) for p, k in status.items()}
        present = [person for person, known in status.items() if known is True]
        unknown = [person for person, known in status.items() if known is None]
        if role.allowed_counts == {len(present) + len(unknown)}:
            # Every candidate must hold the role: it is a fixed category.
            present = [person for person in status if status[person] is not False]
            unknown = []
        parts = [", ".join(present)] if present else []
        group = next(
            (attr for attr, holders in self.board.attributes.items() if holders == set(unknown)),
            None,
        )
        if not present and group is not None and len(unknown) > 1:
            # Say who may hold it by their shared attribute rather than naming every suspect.
            parts.append(self.words["one"].format(name=group.replace("_", " ")))
        elif unknown:
            maybe = ", ".join(unknown)
            parts.append(f"{self.words['maybe']} {maybe}" if present else maybe)
        line = f"{name.replace('_', ' ').capitalize()}: {'; '.join(parts) or '-'}"
        return f"{line} ({self.words['apart']})" if role.different_regions else line
