"""A small SVG canvas: the one renderer behind every puzzle picture.

Drawing calls follow Pillow's `ImageDraw` conventions (coordinates are pixel
indices, boxes are inclusive, outlines are drawn inside the box), so a canvas
rasterised at zoom 1 lines up pixel for pixel with the old Pillow pictures.

Text is converted to paths from the bundled Noto Sans subset, and icons are
embedded as `<symbol>`-like groups, so the SVG looks the same in every viewer
and nothing is fetched at render time. `to_png` rasterises with resvg
(`uv sync --extra png`); building the SVG itself needs only fontTools.
"""

import json
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import cache
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

ASSETS = Path(__file__).parent / "assets"
FONT = ASSETS / "fonts" / "NotoSans-Regular.ttf"
EMOJI = ASSETS / "emoji"

type Colour = tuple[int, int, int] | str
type Point = tuple[float, float]
type Box = tuple[float, float, float, float]


def colour(value: Colour) -> str:
    if isinstance(value, str):
        return value
    return "#{:02x}{:02x}{:02x}".format(*value)


def _n(value: float) -> str:
    """A compact number for SVG attributes."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


# Signs the bundled font lacks, drawn with a look-alike glyph it has.
SUBSTITUTES = {"\u2212": "\u2013"}


class _Font:
    """Glyph outlines and metrics from the bundled font, for text as paths."""

    def __init__(self, path: Path) -> None:
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.ttLib import TTFont

        font = TTFont(path)
        self.units = font["head"].unitsPerEm
        self.ascent = font["hhea"].ascent
        self.descent = font["hhea"].descent
        self.cmap: dict[int, str] = font.getBestCmap()
        self.advance = {name: width for name, (width, _) in font["hmtx"].metrics.items()}
        glyphs = font.getGlyphSet()
        self.paths: dict[str, str] = {}
        for name in set(self.cmap.values()) | {".notdef"}:
            pen = SVGPathPen(glyphs)
            glyphs[name].draw(pen)
            self.paths[name] = pen.getCommands()
        self.ids = {name: f"g{index}" for index, name in enumerate(font.getGlyphOrder())}

    def glyph(self, char: str) -> str:
        char = SUBSTITUTES.get(char, char)
        return self.cmap.get(ord(char), ".notdef")

    def width(self, text: str, size: float) -> float:
        return float(sum(self.advance[self.glyph(c)] for c in text) * size / self.units)


@cache
def font() -> _Font:
    return _Font(FONT)


@cache
def emoji_bounds() -> dict[str, tuple[float, float, float, float]]:
    """The visible box of every vendored picture, in its 128x128 units."""
    data = json.loads((EMOJI / "bounds.json").read_text())
    return {code: (box[0], box[1], box[2], box[3]) for code, box in data.items()}


@cache
def emoji_markup(code: str) -> str | None:
    """The drawing inside a vendored picture's <svg>, or None if not vendored."""
    path = EMOJI / f"emoji_u{code}.svg"
    if not path.exists():
        return None
    text = path.read_text()
    return text[text.index(">") + 1 : text.rindex("</svg>")]


def textlength(text: str, size: float) -> float:
    return font().width(text, size)


class Canvas:
    """An SVG picture built with Pillow-like drawing calls."""

    def __init__(
        self, width: int, height: int, background: Colour = (255, 255, 255), headroom: int = 0
    ) -> None:
        """`headroom` adds that many pixels above y = 0, for drawings that stick out at the
        top; coordinates stay the same, so the picture's height grows by it."""
        self.width = width
        self.height = height + headroom
        self.headroom = headroom
        self._defs: dict[str, str] = {}
        self._body: list[str] = []
        self._cells: list[str] = []
        self._clips = 0
        self.rectangle((0, -headroom, width - 1, height - 1), fill=background)

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def _add(self, element: str) -> None:
        self._body.append(element)

    # --- shapes ---------------------------------------------------------

    def rectangle(
        self,
        box: Box,
        fill: Colour | None = None,
        outline: Colour | None = None,
        width: float = 1,
        radius: float = 0,
    ) -> None:
        x0, y0, x1, y1 = box
        x1, y1 = x1 + 1, y1 + 1
        corner = f' rx="{_n(radius)}"' if radius else ""
        crisp = "" if radius else ' shape-rendering="crispEdges"'
        if fill is not None:
            self._add(
                f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(x1 - x0)}" height="{_n(y1 - y0)}"'
                f'{corner} fill="{colour(fill)}"{crisp}/>'
            )
        if outline is not None and width > 0:
            h = width / 2
            inner = f' rx="{_n(max(0, radius - h))}"' if radius else ""
            self._add(
                f'<rect x="{_n(x0 + h)}" y="{_n(y0 + h)}" width="{_n(x1 - x0 - width)}"'
                f' height="{_n(y1 - y0 - width)}"{inner} fill="none"'
                f' stroke="{colour(outline)}" stroke-width="{_n(width)}"{crisp}/>'
            )

    def rounded_rectangle(
        self,
        box: Box,
        radius: float,
        fill: Colour | None = None,
        outline: Colour | None = None,
        width: float = 1,
    ) -> None:
        self.rectangle(box, fill=fill, outline=outline, width=width, radius=max(radius, 0.01))

    def ellipse(
        self,
        box: Box,
        fill: Colour | None = None,
        outline: Colour | None = None,
        width: float = 1,
    ) -> None:
        x0, y0, x1, y1 = box
        x1, y1 = x1 + 1, y1 + 1
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        if outline is not None and width > 0:
            h = width / 2
            self._add(
                f'<ellipse cx="{_n(cx)}" cy="{_n(cy)}" rx="{_n(rx - h)}" ry="{_n(ry - h)}"'
                f' fill="{colour(fill) if fill is not None else "none"}"'
                f' stroke="{colour(outline)}" stroke-width="{_n(width)}"/>'
            )
        elif fill is not None:
            self._add(
                f'<ellipse cx="{_n(cx)}" cy="{_n(cy)}" rx="{_n(rx)}" ry="{_n(ry)}"'
                f' fill="{colour(fill)}"/>'
            )

    def line(
        self,
        points: Sequence[Point] | Sequence[float],
        fill: Colour,
        width: float = 1,
        joint: str | None = None,
    ) -> None:
        flat = [float(v) for p in points for v in (p if isinstance(p, tuple) else (p,))]
        pairs = [(flat[i] + 0.5, flat[i + 1] + 0.5) for i in range(0, len(flat), 2)]
        straight = len(pairs) == 2 and (pairs[0][0] == pairs[1][0] or pairs[0][1] == pairs[1][1])
        crisp = ' shape-rendering="crispEdges"' if straight else ""
        join = ' stroke-linejoin="round"' if joint == "curve" else ""
        coords = " ".join(f"{_n(x)},{_n(y)}" for x, y in pairs)
        self._add(
            f'<polyline points="{coords}" fill="none" stroke="{colour(fill)}"'
            f' stroke-width="{_n(width)}"{join}{crisp}/>'
        )

    def polygon(
        self, points: Sequence[Point], fill: Colour | None = None, outline: Colour | None = None
    ) -> None:
        coords = " ".join(f"{_n(x + 0.5)},{_n(y + 0.5)}" for x, y in points)
        stroke = f' stroke="{colour(outline)}"' if outline is not None else ""
        paint = colour(fill) if fill is not None else "none"
        self._add(f'<polygon points="{coords}" fill="{paint}"{stroke}/>')

    # --- text -------------------------------------------------------------

    def textlength(self, text: str, size: float) -> float:
        return textlength(text, size)

    def text(
        self,
        xy: Point,
        text: str,
        fill: Colour,
        size: float,
        anchor: str = "la",
        halo: Colour | None = None,
    ) -> None:
        """Write `text` as glyph paths; `anchor` is Pillow's two-letter anchor.

        `halo` outlines the letters in that colour, to keep them readable on a picture."""
        if not text:
            return
        f = font()
        scale = size / f.units
        x, y = xy
        horizontal, vertical = anchor[0], anchor[1]
        if horizontal == "m":
            x -= f.width(text, size) / 2
        elif horizontal == "r":
            x -= f.width(text, size)
        baseline = {
            "a": f.ascent,
            "t": f.ascent,
            "m": (f.ascent + f.descent) / 2,
            "s": 0,
            "d": f.descent,
        }[vertical]
        y += baseline * scale
        uses = []
        advance = 0
        for char in text:
            name = f.glyph(char)
            gid = f.ids[name]
            if f.paths[name]:
                if gid not in self._defs:
                    self._defs[gid] = f'<path id="{gid}" d="{f.paths[name]}"/>'
                uses.append(f'<use href="#{gid}" x="{advance}"/>')
            advance += f.advance[name]
        label = escape(text, {'"': "&quot;"})
        outline = (
            f' stroke="{colour(halo)}" stroke-width="{_n(size * 0.2 / scale)}"'
            ' stroke-linejoin="round" paint-order="stroke"'
            if halo is not None
            else ""
        )
        self._add(
            f'<g aria-label="{label}" fill="{colour(fill)}"{outline}'
            f' transform="translate({_n(x)} {_n(y)}) scale({scale:.5f} {-scale:.5f})">'
            + "".join(uses)
            + "</g>"
        )

    # --- pictures ---------------------------------------------------------

    def place(
        self,
        ref: str,
        markup: str,
        view: Box,
        box: Box,
        *,
        stretch: bool = False,
        rotate: float = 0,
        tint: Colour | None = None,
        overflow: bool = False,
    ) -> None:
        """Draw the drawing `markup` (in `view` units) into `box`.

        The drawing is defined once and reused. It keeps its aspect ratio and
        is centred unless `stretch`; `rotate` turns it that many degrees
        counter-clockwise first. `tint` sets `currentColor` for drawings that use it.
        `overflow` also shows the parts of the drawing outside `view`.
        """
        if ref not in self._defs:
            self._defs[ref] = f'<g id="{ref}">{markup}</g>'
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = x1 - x0, y1 - y0
        if rotate % 180 == 90:
            w, h = h, w
        vx0, vy0, vx1, vy1 = view
        aspect = "none" if stretch else "xMidYMid meet"
        tinted = f' color="{colour(tint)}"' if tint is not None else ""
        if overflow:
            tinted += ' overflow="visible"'
        element = (
            f'<svg x="{_n(cx - w / 2)}" y="{_n(cy - h / 2)}" width="{_n(w)}" height="{_n(h)}"'
            f' viewBox="{_n(vx0)} {_n(vy0)} {_n(vx1 - vx0)} {_n(vy1 - vy0)}"'
            f' preserveAspectRatio="{aspect}"{tinted}><use href="#{ref}"/></svg>'
        )
        if rotate:
            element = f'<g transform="rotate({_n(-rotate)} {_n(cx)} {_n(cy)})">{element}</g>'
        self._add(element)

    def emoji(
        self, code: str, box: Box, *, crop: bool = False, stretch: bool = False, rotate: float = 0
    ) -> bool:
        """Draw vendored picture `code` into `box`; False if it is not vendored.

        `crop` fits the visible part of the picture rather than its full square.
        """
        markup = emoji_markup(code)
        if markup is None:
            return False
        view = emoji_bounds()[code] if crop or stretch else (0, 0, 128, 128)
        self.place(f"emoji-{code}", markup, view, box, stretch=stretch, rotate=rotate)
        return True

    # --- groups and cells -------------------------------------------------

    @contextmanager
    def group(
        self, opacity: float = 1, clip: Sequence[Box] = (), class_name: str | None = None
    ) -> Iterator[None]:
        """Draw the enclosed calls as one layer, faded and clipped as a whole."""
        attributes = f' opacity="{opacity:.3f}"' if opacity < 1 else ""
        if class_name:
            attributes += f" class={quoteattr(class_name)}"
        if clip:
            self._clips += 1
            clip_id = f"clip{self._clips}"
            rects = "".join(
                f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(x1 - x0 + 1)}"'
                f' height="{_n(y1 - y0 + 1)}"/>'
                for x0, y0, x1, y1 in clip
            )
            self._defs[clip_id] = f'<clipPath id="{clip_id}">{rects}</clipPath>'
            attributes += f' clip-path="url(#{clip_id})"'
        self._add(f"<g{attributes}>")
        try:
            yield
        finally:
            self._add("</g>")

    def cell(self, cell_id: str, box: Box) -> None:
        """A transparent target for one cell, for the interactive variant."""
        x0, y0, x1, y1 = box
        self._cells.append(
            f'<rect id="{cell_id}" class="cell" x="{_n(x0)}" y="{_n(y0)}"'
            f' width="{_n(x1 - x0)}" height="{_n(y1 - y0)}" fill="#fff" fill-opacity="0"/>'
        )

    # --- output -----------------------------------------------------------

    def to_svg(self) -> str:
        defs = "<defs>" + "".join(self._defs.values()) + "</defs>" if self._defs else ""
        cells = '<g class="cells">' + "".join(self._cells) + "</g>" if self._cells else ""
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
            f' width="{self.width}" height="{self.height}"'
            f' viewBox="0 {-self.headroom} {self.width} {self.height}">\n'
            + defs
            + "\n"
            + "\n".join(self._body)
            + "\n"
            + cells
            + "</svg>\n"
        )

    def to_png(self, zoom: float = 1) -> bytes:
        """The picture as PNG bytes, rasterised by resvg."""
        return rasterise(self.to_svg(), zoom)

    def save(self, path: Path | str, zoom: float = 1) -> None:
        """Write the picture as SVG or PNG, by the file's extension."""
        target = Path(path)
        if target.suffix.lower() == ".svg":
            target.write_text(self.to_svg())
        else:
            target.write_bytes(self.to_png(zoom))


def rasterise(svg: str, zoom: float = 1, **options: Any) -> bytes:
    try:
        import resvg_py
    except ImportError as error:
        raise ImportError("PNG output needs resvg: uv sync --extra png") from error
    data = resvg_py.svg_to_bytes(svg_string=svg, zoom=zoom, skip_system_fonts=True, **options)
    return bytes(data)


def ids(svg: str) -> list[str]:
    """The cell ids of an interactive picture, in document order."""
    return re.findall(r'<rect id="([^"]+)" class="cell"', svg)
