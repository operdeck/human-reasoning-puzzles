"""PNG pictures of puzzles, drawn from the puzzle itself.

Murdoku follows the style of the printed puzzles: region fills (darker where
an object stands), optional diagonal hatching, thick dark lines between
regions and thin white lines inside them, an icon per object, name tags for
people, and a legend. Icons come from `csp.icons`;
an object without one gets its name written in the square.

Sudoku and Calcudoku share the look: thick lines around boxes or cages, thin
ones inside, givens in black and solved numbers in blue. Calcudoku cages get
pastel fills, no two touching cages alike, and their target in the corner.

Needs Pillow (`uv sync --extra png`).
"""

import textwrap
from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import icons
from .calcudoku import Puzzle as Calcudoku
from .calcudoku import cell_name as calcudoku_cell
from .futoshiki import Puzzle as Futoshiki
from .futoshiki import cell_name as futoshiki_cell
from .murdoku import Board, GlobalCountCondition, Square
from .queens import Cell as QueensCell
from .queens import Puzzle as Queens
from .sudoku import Puzzle as Sudoku
from .sudoku import box_size
from .sudoku import cell_name as sudoku_cell

INK = (26, 26, 26)
WHITE = (255, 255, 255)
SOLVED = (33, 90, 200)  # numbers the solver filled in
EXTRA = (214, 214, 214)  # extra houses, grey as NRC prints them
THIN = (190, 190, 190)
MARK_FILL = (246, 249, 229)
MARK_INK = (57, 89, 66)
COUNT_SCOPE = (45, 110, 155)
# Used for regions the puzzle file gives no colour.
PALETTE = ["#F3C8C0", "#FADFB5", "#CBE6B9", "#D8D2F0", "#C4DCF2", "#BEE5D6", "#F3EDA2",
           "#DCDCDC", "#E0A79C", "#A9D6F0"]  # fmt: skip

type RGB = tuple[int, int, int]
type Box = tuple[int, int, int, int]
type Cell = tuple[int, int]


def murdoku_picture(
    board: Board,
    placed: Mapping[str, Square] | None = None,
    *,
    role_statuses: Mapping[tuple[str, str], bool | None] | None = None,
    global_counts: Sequence[GlobalCountCondition] = (),
    cell: int = 120,
    coordinates: bool = True,
    legend: bool = True,
) -> Image.Image:
    """The board, with `placed` people drawn on their squares if given.

    Without `legend` the picture is square, for documents with their own legend.
    """
    margin = cell // 2 if coordinates else cell // 6
    side = board.size * cell
    key = _Legend(board, cell, role_statuses or {}, global_counts) if legend else None
    height = side + 2 * margin + (key.height if key else 0)
    image = Image.new("RGB", (side + 2 * margin, height), WHITE)
    draw = ImageDraw.Draw(image)
    fills = _fills(board)

    def box(sq: Square) -> Box:
        x, y = margin + sq.col * cell, margin + sq.row * cell
        return x, y, x + cell, y + cell

    blocked = board.blocked
    count_scope = {square for condition in global_counts for square in condition.scope_cells(board)}
    for r in range(board.size):
        for c in range(board.size):
            sq = Square(r, c)
            fill = fills[board.region_of(sq)]
            draw.rectangle(box(sq), fill=_darker(fill) if sq in blocked else fill)
    _hatch(image, board, box, cell)
    _walls(
        draw,
        board.size,
        margin,
        cell,
        lambda a, b: board.regions[a[0]][a[1]] == board.regions[b[0]][b[1]],
    )
    _draw_edge_item_doors(draw, board, margin, cell)

    occupied = set((placed or {}).values())
    for obj in board.objects:
        name = obj.name
        piece = obj.squares
        x0, y0, _, _ = box(min(piece))
        _, _, x1, y1 = box(max(piece))
        stretch = len(piece) > 1
        if name.rstrip("0123456789").rstrip("_").lower() in {"waterput", "well"}:
            _draw_water_well(draw, (x0, y0, x1, y1))
        elif obj.kind == "standable":
            rotate = name.rstrip("0123456789").rstrip("_").lower() == "bed" and y1 - y0 > x1 - x0
            if occupied & set(piece) and not stretch:
                y1 = y0 + int(cell * 0.62)  # leave room for the name tag below
                _icon(image, draw, name, (x0, y0, x1, y1), cell, scale=0.95, rotate=rotate)
            else:
                _icon(image, draw, name, (x0, y0, x1, y1), cell, stretch=stretch, rotate=rotate)
        else:
            _icon(image, draw, name, (x0, y0, x1, y1), cell, stretch=stretch)
    for item in board.edge_items:
        if item.kind == "window":
            _icon(image, draw, item.name, box(item.cells[0]), cell, scale=0.42)
    for corner in board.corner_objects:
        anchor_row = max(square.row for square in corner.cells)
        anchor_col = max(square.col for square in corner.cells)
        x = margin + anchor_col * cell
        y = margin + anchor_row * cell
        radius = cell // 4
        _icon(
            image,
            draw,
            corner.name,
            (x - radius, y - radius, x + radius, y + radius),
            cell,
        )
    for square in count_scope:
        draw.rectangle(
            box(square),
            outline=COUNT_SCOPE,
            width=max(2, cell // 40),
        )
    marks_by_cell: dict[Square, list[str]] = {}
    for mark in board.marks:
        for square in mark.cells:
            marks_by_cell.setdefault(square, []).append(mark.name)
    for square, names in marks_by_cell.items():
        x0, y0, _, _ = box(square)
        pad = max(3, cell // 24)
        area = (x0 + pad, y0 + pad, x0 + pad + cell // 3, y0 + pad + cell // 4)
        draw.rounded_rectangle(
            area,
            radius=max(2, cell // 30),
            fill=MARK_FILL,
            outline=MARK_INK,
            width=max(1, cell // 50),
        )
        initials = "/".join(name[0].upper() for name in sorted(names))
        _centred_text(draw, initials, area, max(8, cell // 12), MARK_INK, max_width=cell // 3)
    standable = board.squares_of(obj.name for obj in board.standable_objects)
    for person, sq in (placed or {}).items():
        _name_tag(draw, person, box(sq), cell, low=sq in standable)

    if coordinates:
        _coordinates(draw, board.size, margin, cell)
    if key:
        key.draw(image, draw, margin, margin + side + cell // 3)
    return image


def unknown_object_icons(board: Board) -> list[str]:
    """Object types that render with a text fallback instead of a picture icon."""
    custom = {"tapijt", "waterput", "well"}
    return sorted(
        {
            name
            for name in (
                {obj.name for obj in board.objects}
                | {item.name for item in board.edge_items if item.kind == "window"}
                | board.corner_object_names
            )
            if icons.code_for(name) is None
            and name.rstrip("0123456789").rstrip("_").lower() not in custom
        }
    )


def sudoku_picture(
    puzzle: Sudoku, solution: Mapping[str, int] | None = None, *, cell: int = 100
) -> Image.Image:
    """The grid with its givens, and the solved numbers in blue if given.

    Square boxes are shaded alternately; jigsaw boxes get a pastel each.
    Extra houses (NRC boxes, X-Sudoku diagonals) are grey.
    """
    n, grid, boxes = puzzle.size, puzzle.grid, puzzle.boxes
    fills = _group_fills({(r, c): boxes[r][c] for r in range(n) for c in range(n)})
    box = box_size(n)
    extra = {cell for cells in puzzle.extra_houses().values() for cell in cells}

    def shade(r: int, c: int) -> RGB:
        if (r, c) in extra:
            return EXTRA
        if puzzle.jigsaw:
            return fills[boxes[r][c]]
        if extra:
            return WHITE
        return (238, 242, 250) if (r // box + c // box) % 2 else WHITE

    def number(r: int, c: int) -> tuple[int | None, RGB]:
        if grid[r][c]:
            return grid[r][c], INK
        return (solution or {}).get(sudoku_cell(r, c)), SOLVED

    return _number_grid(n, cell, shade, number, lambda a, b: boxes[a[0]][a[1]] == boxes[b[0]][b[1]])


def calcudoku_picture(
    puzzle: Calcudoku, solution: Mapping[str, int] | None = None, *, cell: int = 100
) -> Image.Image:
    """The cages with their targets, and the solved numbers if given."""
    fills = _cage_fills(puzzle)
    cage_at = puzzle.cage_at

    def number(r: int, c: int) -> tuple[int | None, RGB]:
        return (solution or {}).get(calcudoku_cell((r, c))), SOLVED

    image = _number_grid(
        puzzle.size,
        cell,
        lambda r, c: fills[cage_at[r, c]],
        number,
        lambda a, b: cage_at[a] is cage_at[b],
    )
    draw = ImageDraw.Draw(image)
    margin = cell // 2
    font = _font(cell // 5)
    for cage in puzzle.cages:
        r, c = min(cage.cells)
        corner = (margin + c * cell + cell // 10, margin + r * cell + cell // 14)
        draw.text(corner, cage.label, fill=INK, font=font, anchor="la")
    return image


def futoshiki_picture(
    puzzle: Futoshiki, solution: Mapping[str, int] | None = None, *, cell: int = 100
) -> Image.Image:
    """The grid with its givens and signs, and the solved numbers in blue if given.

    Each sign is a chevron on the edge between its two cells, its point
    towards the smaller number.
    """
    grid = puzzle.grid

    def number(r: int, c: int) -> tuple[int | None, RGB]:
        if grid[r][c]:
            return grid[r][c], INK
        return (solution or {}).get(futoshiki_cell((r, c))), SOLVED

    image = _number_grid(puzzle.size, cell, lambda r, c: WHITE, number, lambda a, b: True)
    draw = ImageDraw.Draw(image)
    margin, arm = cell // 2, cell // 9
    for sign in puzzle.signs:
        (r0, c0), (r1, c1) = sign.smaller, sign.larger
        dx, dy = c0 - c1, r0 - r1  # one step towards the smaller cell
        mx = margin + (c0 + c1 + 1) * cell / 2
        my = margin + (r0 + r1 + 1) * cell / 2
        tip = (mx + dx * arm / 2, my + dy * arm / 2)
        back = (mx - dx * arm / 2, my - dy * arm / 2)
        ends = [(back[0] + dy * arm, back[1] + dx * arm), (back[0] - dy * arm, back[1] - dx * arm)]
        pad = arm + cell // 25
        draw.rectangle((mx - pad, my - pad, mx + pad, my + pad), fill=WHITE)
        draw.line([ends[0], tip, ends[1]], fill=INK, width=max(3, cell // 25), joint="curve")
    return image


def queens_picture(
    puzzle: Queens,
    solution: Mapping[str, QueensCell] | None = None,
    *,
    cell: int = 100,
) -> Image.Image:
    """Draw region colours and the placed queens in blue."""
    n = puzzle.size
    margin = cell // 2
    side = n * cell
    image = Image.new("RGB", (side + 2 * margin, side + 2 * margin), WHITE)
    draw = ImageDraw.Draw(image)
    region_at = {(r, c): puzzle.grid[r][c] for r in range(n) for c in range(n)}
    fills = _group_fills(region_at)
    for (row, col), region in region_at.items():
        x, y = margin + col * cell, margin + row * cell
        draw.rectangle((x, y, x + cell, y + cell), fill=fills[region])
    _walls(draw, n, margin, cell, lambda a, b: region_at[a] == region_at[b], thin_colour=THIN)
    for queen in (solution or {}).values():
        x = margin + queen.col * cell
        y = margin + queen.row * cell
        baseline = y + cell * 3 // 4
        crown = [
            (x + cell // 5, baseline),
            (x + cell // 10, y + cell // 4),
            (x + cell // 3, y + cell // 2),
            (x + cell // 2, y + cell // 8),
            (x + cell * 2 // 3, y + cell // 2),
            (x + cell * 9 // 10, y + cell // 4),
            (x + cell * 4 // 5, baseline),
        ]
        draw.polygon(crown, fill=SOLVED)
        draw.rectangle((x + cell // 5, baseline, x + cell * 4 // 5, y + cell * 4 // 5), fill=SOLVED)
        draw.rectangle(
            (x + cell // 4, y + cell * 5 // 6, x + cell * 3 // 4, y + cell * 9 // 10),
            fill=SOLVED,
        )
        radius = max(1, cell // 18)
        for center_x, center_y in (
            (x + cell // 10, y + cell // 4),
            (x + cell // 2, y + cell // 8),
            (x + cell * 9 // 10, y + cell // 4),
        ):
            draw.ellipse(
                (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                fill=SOLVED,
            )
    _coordinates(draw, n, margin, cell)
    return image


def _number_grid(
    n: int,
    cell: int,
    shade: Callable[[int, int], RGB],
    number: Callable[[int, int], tuple[int | None, RGB]],
    together: Callable[[Cell, Cell], bool],
) -> Image.Image:
    """A square grid of numbers: shaded cells, walls between groups, coordinates."""
    margin = cell // 2
    side = n * cell
    image = Image.new("RGB", (side + 2 * margin, side + 2 * margin), WHITE)
    draw = ImageDraw.Draw(image)
    font = _font(int(cell * 0.5))
    for r in range(n):
        for c in range(n):
            x, y = margin + c * cell, margin + r * cell
            draw.rectangle((x, y, x + cell, y + cell), fill=shade(r, c))
    _walls(draw, n, margin, cell, together, thin_colour=THIN)
    for r in range(n):
        for c in range(n):
            value, colour = number(r, c)
            if value:
                middle = (margin + c * cell + cell / 2, margin + r * cell + cell * 0.56)
                draw.text(middle, str(value), fill=colour, font=font, anchor="mm")
    _coordinates(draw, n, margin, cell)
    return image


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


def _darker(colour: RGB, factor: float = 0.9) -> RGB:
    r, g, b = colour
    return round(r * factor), round(g * factor), round(b * factor)


def _hatch(image: Image.Image, board: Board, box: Callable[[Square], Box], cell: int) -> None:
    """Thin diagonal lines over hatched regions, as on the printed boards.

    Stripes follow one global pattern (constant x + y), so they run on
    unbroken from square to square.
    """
    if not board.hatched:
        return
    step = max(6, cell // 7)
    width = max(2, cell // 30)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    for r in range(board.size):
        for c in range(board.size):
            sq = Square(r, c)
            if board.region_of(sq) not in board.hatched:
                continue
            x0, y0, x1, y1 = box(sq)
            tile = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
            stripes = ImageDraw.Draw(tile)
            first = (x0 + y0) // step * step
            for k in range(first, x1 + y1 + step, step):
                # The line x + y = k, in tile coordinates.
                stripes.line([(k - x0 - y0, 0), (k - x0 - y1, y1 - y0)],
                             fill=(60, 60, 60, 60), width=width)  # fmt: skip
            overlay.paste(tile, (x0, y0))
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))


def _walls(
    draw: ImageDraw.ImageDraw,
    n: int,
    margin: int,
    cell: int,
    together: Callable[[Cell, Cell], bool],
    thin_colour: RGB = WHITE,
) -> None:
    """Thin lines between cells that are `together`, thick walls elsewhere."""
    thin = max(2, cell // 40)
    thick = max(5, cell // 22) | 1  # odd, so Pillow centres both directions alike
    walls: list[tuple[int, int, int, int]] = []
    for r in range(n):
        for c in range(n):
            x, y = margin + c * cell, margin + r * cell
            if c + 1 < n:
                line = (x + cell, y, x + cell, y + cell)
                same = together((r, c), (r, c + 1))
                (draw.line(line, fill=thin_colour, width=thin) if same else walls.append(line))
            if r + 1 < n:
                line = (x, y + cell, x + cell, y + cell)
                same = together((r, c), (r + 1, c))
                (draw.line(line, fill=thin_colour, width=thin) if same else walls.append(line))
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
        draw.line((x0, y0, x1, y1), fill=INK, width=thick)
    draw.rectangle((low, low, high, high), outline=INK, width=thick)


def _draw_edge_item_doors(draw: ImageDraw.ImageDraw, board: Board, margin: int, cell: int) -> None:
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
            draw.line((x, y - cell // 4, x, y + cell // 4), fill=wood, width=width)
        else:
            x = margin + first.col * cell + cell // 2
            y = margin + max(first.row, second.row) * cell
            draw.line((x - cell // 4, y, x + cell // 4, y), fill=wood, width=width)


# --- things on the board --------------------------------------------------


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _icon(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    name: str,
    area: Box,
    cell: int,
    scale: float = 0.72,
    stretch: bool = False,
    rotate: bool = False,
) -> None:
    """Draw `name`'s icon centred in `area`; `stretch` fills the area instead."""
    x0, y0, x1, y1 = area
    normalized = name.rstrip("0123456789").rstrip("_").lower()
    if normalized == "tapijt":
        _draw_carpet(draw, area)
        return
    path = icons.icon(name)
    if path is None:
        _centred_text(draw, name[:6], area, cell // 5, INK)
        return
    picture = Image.open(path).convert("RGBA")
    fix = ICON_FIXES.get(icons.code_for(name) or "")
    if fix:
        picture = fix(picture)
    if rotate:
        picture = picture.rotate(90, expand=True)
    if stretch:
        picture = picture.crop(picture.getchannel("A").getbbox())
        pad = cell // 10
        size = (x1 - x0 - 2 * pad, y1 - y0 - 2 * pad)
        picture = picture.resize(size, Image.Resampling.LANCZOS)
    else:
        side = int(min(x1 - x0, y1 - y0) * scale)
        picture.thumbnail((side, side), Image.Resampling.LANCZOS)
    left = x0 + (x1 - x0 - picture.width) // 2
    top = y0 + (y1 - y0 - picture.height) // 2
    image.paste(picture, (left, top), picture)


def _draw_carpet(draw: ImageDraw.ImageDraw, area: Box) -> None:
    """Draw a patterned rug that reads clearly at a single-cell size."""
    x0, y0, x1, y1 = area
    width, height = x1 - x0, y1 - y0
    pad = max(3, min(width, height) // 12)
    bounds = (x0 + pad, y0 + pad, x1 - pad, y1 - pad)
    red, gold, dark = (156, 58, 45), (231, 190, 89), (79, 45, 43)
    draw.rounded_rectangle(bounds, radius=pad, fill=red, outline=dark, width=max(2, pad // 2))
    inner_pad = max(3, pad // 2)
    inner = (
        bounds[0] + inner_pad,
        bounds[1] + inner_pad,
        bounds[2] - inner_pad,
        bounds[3] - inner_pad,
    )
    draw.rectangle(inner, outline=gold, width=max(2, pad // 2))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    diamond = max(3, min(width, height) // 5)
    draw.polygon(
        [(cx, cy - diamond), (cx + diamond, cy), (cx, cy + diamond), (cx - diamond, cy)],
        fill=gold,
        outline=dark,
    )
    center = max(1, diamond // 3)
    draw.ellipse((cx - center, cy - center, cx + center, cy + center), fill=red)


def _draw_water_well(draw: ImageDraw.ImageDraw, area: Box) -> None:
    """Draw a stone well with dark water and a simple timber frame."""
    x0, y0, x1, y1 = area
    width, height = x1 - x0, y1 - y0
    stone, edge, wood, water = (137, 139, 132), (55, 57, 55), (111, 72, 48), (45, 65, 70)
    pad = max(5, min(width, height) // 12)
    rim = (x0 + pad, y0 + height // 2, x1 - pad, y1 - pad)
    draw.ellipse(rim, fill=stone, outline=edge, width=max(3, pad // 2))
    inset_x, inset_y = width // 5, height // 7
    pool = (rim[0] + inset_x, rim[1] + inset_y, rim[2] - inset_x, rim[3] - inset_y)
    draw.ellipse(pool, fill=water, outline=edge, width=max(2, pad // 3))
    post_width = max(4, width // 12)
    post_top, post_bottom = y0 + height // 8, y0 + height * 2 // 3
    left_post = (x0 + width // 4, post_top, x0 + width // 4 + post_width, post_bottom)
    right_post = (x1 - width // 4 - post_width, post_top, x1 - width // 4, post_bottom)
    draw.rectangle(left_post, fill=wood, outline=edge, width=2)
    draw.rectangle(right_post, fill=wood, outline=edge, width=2)
    beam_y = y0 + height // 6
    draw.rectangle(
        (
            left_post[0] - post_width // 2,
            beam_y,
            right_post[2] + post_width // 2,
            beam_y + post_width,
        ),
        fill=wood,
        outline=edge,
        width=2,
    )
    rope_x = x0 + width // 2
    draw.line(
        (rope_x, beam_y + post_width, rope_x, pool[1] + height // 8),
        fill=(225, 207, 155),
        width=max(2, pad // 3),
    )


def _drop_floor_lamp(picture: Image.Image) -> Image.Image:
    """Noto's U+1F6CB is 'couch and lamp': keep the blue couch, drop the lamp.

    The lamp and its pole are yellow and brown and stand above the seat, which
    starts at 47.5% of the height; every couch pixel up there is blue.
    """
    picture = picture.copy()
    red, _, blue, alpha = picture.split()
    blueish = ImageChops.subtract(blue, red).point(lambda v: 255 if v > 0 else 0)
    above_seat = (0, 0, picture.width, int(picture.height * 0.475))
    alpha.paste(ImageChops.multiply(alpha.crop(above_seat), blueish.crop(above_seat)), above_seat)
    picture.putalpha(alpha)
    return picture


# Per-icon touch-ups, by code point.
ICON_FIXES = {"1f6cb": _drop_floor_lamp}


def _name_tag(
    draw: ImageDraw.ImageDraw, person: str, area: Box, cell: int, low: bool = False
) -> None:
    x0, y0, x1, _ = area
    pad = cell // 10
    top = y0 + int(cell * 0.6) if low else y0 + cell // 3
    tag = (x0 + pad, top, x1 - pad, top + cell // 3)
    draw.rounded_rectangle(tag, radius=cell // 8, fill=WHITE, outline=INK, width=max(2, cell // 40))
    _centred_text(draw, person, tag, cell // 5, INK, max_width=cell - 3 * pad)


def _centred_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    area: Box,
    size: int,
    colour: RGB,
    max_width: int | None = None,
) -> None:
    x0, y0, x1, y1 = area
    font = _font(size)
    while max_width and size > 8 and draw.textlength(text, font=font) > max_width:
        size -= 1
        font = _font(size)
    draw.text(((x0 + x1) / 2, (y0 + y1) / 2), text, fill=colour, font=font, anchor="mm")


def _coordinates(draw: ImageDraw.ImageDraw, n: int, margin: int, cell: int) -> None:
    font = _font(cell // 5)
    grey = (120, 120, 120)
    for i in range(n):
        middle = margin + i * cell + cell / 2
        draw.text((middle, margin / 2), str(i + 1), fill=grey, font=font, anchor="mm")
        draw.text((margin / 2, middle), str(i + 1), fill=grey, font=font, anchor="mm")


# --- legend ---------------------------------------------------------------


class _Legend:
    """Region swatches with names, in two columns under the board."""

    def __init__(
        self,
        board: Board,
        cell: int,
        role_statuses: Mapping[tuple[str, str], bool | None] | None = None,
        global_counts: Sequence[GlobalCountCondition] = (),
    ) -> None:
        self.board = board
        self.cell = cell
        self.role_statuses = role_statuses or {}
        self.global_counts = tuple(global_counts)
        self.swatch = cell // 3
        self.line = int(self.swatch * 1.6)
        self.rows = (len(board.region_names) + 1) // 2
        self.item_names = sorted(board.edge_item_names | board.corner_object_names)
        self.mark_names = sorted(board.mark_names)
        self.role_names = sorted(board.role_names)
        self.count_font = _font(max(8, cell // 16))
        max_chars = max(18, int((board.size * cell // 2) / max(1, cell // 24)))
        self.global_count_lines = [
            lines
            for index, condition in enumerate(self.global_counts, 1)
            for lines in [
                textwrap.wrap(
                    f"Global {condition.number or index}: {condition.description}",
                    width=max_chars,
                )
            ]
        ]
        self.count_rows = sum(max(1, len(lines)) for lines in self.global_count_lines)
        self.height = (
            self.rows
            + len(self.item_names)
            + len(self.mark_names)
            + len(self.role_names)
            + self.count_rows
        ) * self.line + cell // 2

    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        fills = _fills(self.board)
        font = _font(int(self.swatch * 0.8))
        column = self.board.size * self.cell // 2
        for i, (rid, name) in enumerate(self.board.region_names.items()):
            left = x + (i // self.rows) * column
            top = y + (i % self.rows) * self.line
            square = (left, top, left + self.swatch, top + self.swatch)
            draw.rectangle(square, fill=fills[rid], outline=INK, width=2)
            if rid in self.board.hatched:
                for k in range(0, 2 * self.swatch, max(5, self.swatch // 4)):
                    draw.line(
                        [(left + max(0, k - self.swatch), top + min(k, self.swatch)),
                         (left + min(k, self.swatch), top + max(0, k - self.swatch))],
                        fill=(110, 110, 110), width=1,
                    )  # fmt: skip
            label = name.replace("_", " ").capitalize()
            draw.text((left + self.swatch + self.swatch // 2, top + self.swatch / 2),
                      label, fill=INK, font=font, anchor="lm")  # fmt: skip
        for i, name in enumerate(self.item_names):
            top = y + (self.rows + i) * self.line
            area = (x, top, x + self.swatch, top + self.swatch)
            if name in self.board.edge_item_names and self.board.edge_item_kind(name) == "door":
                draw.line(
                    (x, top + self.swatch // 2, x + self.swatch, top + self.swatch // 2),
                    fill=(117, 75, 47),
                    width=max(4, self.swatch // 5),
                )
                label = f"Door: {name}"
            else:
                _icon(image, draw, name, area, self.cell, scale=0.8)
                label = (
                    f"Window: {name}" if name in self.board.edge_item_names else f"Corner: {name}"
                )
            draw.text(
                (x + self.swatch + self.swatch // 2, top + self.swatch / 2),
                label,
                fill=INK,
                font=font,
                anchor="lm",
            )
        for i, name in enumerate(self.mark_names):
            top = y + (self.rows + len(self.item_names) + i) * self.line
            area = (x, top, x + self.swatch, top + self.swatch)
            draw.rounded_rectangle(
                area,
                radius=max(2, self.swatch // 8),
                fill=MARK_FILL,
                outline=MARK_INK,
                width=2,
            )
            _centred_text(
                draw,
                name[:2].upper(),
                area,
                max(8, self.cell // 6),
                MARK_INK,
                max_width=self.swatch - 4,
            )
            mark = next(item for item in self.board.marks if item.name == name)
            condition = f" ({mark.occupant_condition})" if mark.occupant_condition else ""
            draw.text(
                (x + self.swatch + self.swatch // 2, top + self.swatch / 2),
                f"Mark: {name}{condition}",
                fill=INK,
                font=font,
                anchor="lm",
            )
        role_offset = self.rows + len(self.item_names) + len(self.mark_names)
        role_font = _font(max(8, self.swatch // 2))
        for i, name in enumerate(self.role_names):
            top = y + (role_offset + i) * self.line
            area = (x, top, x + self.swatch, top + self.swatch)
            draw.rectangle(area, fill=MARK_FILL, outline=MARK_INK, width=2)
            _centred_text(draw, name[:2].upper(), area, max(8, self.swatch // 2), MARK_INK)
            present = [
                person
                for person in self.board.people
                if self.role_statuses.get((person, name)) is True
            ]
            absent = [
                person
                for person in self.board.people
                if self.role_statuses.get((person, name)) is False
            ]
            unknown = [
                person
                for person in self.board.people
                if self.role_statuses.get((person, name)) is None
            ]
            detail = f"+{','.join(present)} -{','.join(absent)} ?{','.join(unknown)}"
            draw.text(
                (x + self.swatch + self.swatch // 2, top + self.swatch / 2),
                f"Role {name}: {detail}",
                fill=INK,
                font=role_font,
                anchor="lm",
            )
        count_row = role_offset + len(self.role_names)
        for lines in self.global_count_lines:
            for line in lines or [""]:
                top = y + count_row * self.line
                draw.text(
                    (x, top + self.line / 2),
                    line,
                    fill=COUNT_SCOPE,
                    font=self.count_font,
                    anchor="lm",
                )
                count_row += 1
