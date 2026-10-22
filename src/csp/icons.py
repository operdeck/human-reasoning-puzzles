"""The icon registry: one place that says how every puzzle symbol looks.

Families refer to semantic names ("star", "queen", "tent", "mine", ...), never
to glyphs. Each `Icon` gives

- the drawing used on boards: either a small SVG drawing kept here (geometric
  icons, which take the given/solved colour through `currentColor`) or a
  picture vendored from Google's Noto Emoji (pictorial icons),
- a Unicode fallback for text output and the Word booklets, chosen from
  symbols that print in ordinary fonts rather than as emoji where possible,
- a label for legends and accessibility.

Murdoku objects use the same pictures: `CATALOGUE` maps the object names used
in puzzles (Dutch, plus English synonyms) to Noto Emoji code points. The
pictures are vendored under `assets/emoji` (see the NOTICE there and
scripts/vendor_emoji.py), so rendering never needs the network.
"""

import math
import re
from dataclasses import dataclass

from . import svg

NOTO_COMMIT = "e20cbc2bbec1926686be9f9bee7d1d2cfa1fea0e"

type Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Icon:
    name: str
    unicode: str
    label: str
    emoji: str | None = None  # code point of a vendored Noto Emoji picture
    markup: str | None = None  # SVG drawing in `view` units
    view: Box = (0, 0, 100, 100)


def _star() -> str:
    points = []
    for k in range(10):
        radius = 47 if k % 2 == 0 else 19
        angle = math.pi * (k / 5 - 0.5)
        points.append(f"{50 + radius * math.cos(angle):.1f},{54 + radius * math.sin(angle):.1f}")
    return f'<polygon points="{" ".join(points)}" fill="currentColor"/>'


CROWN = (
    '<g fill="currentColor"><polygon points="20,75 10,25 33.3,50 50,12.5 66.7,50 90,25 80,75"/>'
    '<rect x="20" y="75" width="60" height="6"/><rect x="25" y="83.3" width="50" height="7.7"/>'
    '<circle cx="10" cy="25" r="5.6"/><circle cx="50" cy="12.5" r="5.6"/>'
    '<circle cx="90" cy="25" r="5.6"/></g>'
)
TONGUE = "#e86a7e"
# A dog has pointed, upright ears; a puppy a rounder head, floppy ears and a tongue.
DOG = (
    '<g fill="currentColor"><polygon points="42,34 30,8 19,40"/>'
    '<polygon points="58,34 70,8 81,40"/>'
    '<ellipse cx="50" cy="56" rx="26" ry="25"/></g>'
    '<ellipse cx="50" cy="70" rx="14" ry="10" fill="#fff"/>'
    '<ellipse cx="50" cy="65" rx="6" ry="4" fill="currentColor"/>'
    '<g fill="#fff"><circle cx="38" cy="50" r="4.5"/><circle cx="62" cy="50" r="4.5"/></g>'
    '<g fill="currentColor"><circle cx="38" cy="50" r="2.25"/>'
    '<circle cx="62" cy="50" r="2.25"/></g>'
)
PUPPY = (
    '<g fill="currentColor"><ellipse cx="20" cy="45" rx="10" ry="21"/>'
    '<ellipse cx="80" cy="45" rx="10" ry="21"/><circle cx="50" cy="52" r="27"/></g>'
    '<ellipse cx="50" cy="70" rx="15" ry="11" fill="#fff"/>'
    f'<ellipse cx="50" cy="82" rx="5" ry="7.5" fill="{TONGUE}"/>'
    '<ellipse cx="50" cy="66" rx="5.5" ry="4" fill="currentColor"/>'
    '<g fill="#fff"><circle cx="37" cy="46" r="5"/><circle cx="63" cy="46" r="5"/></g>'
    '<g fill="currentColor"><circle cx="37" cy="46" r="2.5"/><circle cx="63" cy="46" r="2.5"/></g>'
)
# A patterned rug and a stone well, drawn here because Noto Emoji has neither.
CARPET = (
    '<rect x="10" y="10" width="101" height="101" rx="10" fill="#9c3a2d"/>'
    '<rect x="12.5" y="12.5" width="96" height="96" rx="7.5" fill="none" stroke="#4f2d2b"'
    ' stroke-width="5"/>'
    '<rect x="17.5" y="17.5" width="86" height="86" fill="none" stroke="#e7be59" stroke-width="5"/>'
    '<polygon points="60.5,36.5 84.5,60.5 60.5,84.5 36.5,60.5" fill="#e7be59" stroke="#4f2d2b"/>'
    '<circle cx="60.5" cy="60.5" r="8.5" fill="#9c3a2d"/>'
)
WELL = (
    '<ellipse cx="60.5" cy="85.5" rx="48" ry="23" fill="#898b84" stroke="#373937"'
    ' stroke-width="5"/>'
    '<ellipse cx="60.5" cy="85.5" rx="25" ry="7" fill="#2d4146" stroke="#373937"'
    ' stroke-width="3"/>'
    '<g fill="#6f4830" stroke="#373937" stroke-width="2">'
    '<rect x="31" y="16" width="9" height="64"/><rect x="81" y="16" width="9" height="64"/>'
    '<rect x="26" y="21" width="69" height="9"/></g>'
    '<line x1="60.5" y1="31" x2="60.5" y2="92.5" stroke="#e1cf9b" stroke-width="3"/>'
)
# An ornamental onion (allium): a purple ball of florets on a long stem.
ALLIUM = (
    '<path d="M50 60V96" stroke="#4c8c3a" stroke-width="5" stroke-linecap="round"/>'
    '<path d="M50 92Q30 84 24 66Q40 72 50 86Z" fill="#6aa84f"/>'
    '<circle cx="50" cy="36" r="27" fill="#7d3c98"/>'
    '<g fill="#c39bd3">'
    + "".join(
        f'<circle cx="{50 + r * math.cos(a):.1f}" cy="{36 + r * math.sin(a):.1f}" r="3.6"/>'
        for r, n, turn in ((0, 1, 0), (9, 6, 0.3), (18, 11, 0.6))
        for a in (turn + 2 * math.pi * k / n for k in range(n))
    )
    + "</g>"
)
LINE = 'fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"'

FILL = 'fill="currentColor"'
SHAPES = {
    "wall": f'<rect width="100" height="100" {FILL}/>',
    "filled": f'<rect x="14" y="14" width="72" height="72" rx="4" {FILL}/>',
    "water": f'<path d="M14 50q9-12 18 0t18 0t18 0t18 0" {LINE} stroke-width="7"/>',
    "disc_black": f'<circle cx="50" cy="50" r="34" {FILL}/>',
    "disc_white": '<circle cx="50" cy="50" r="31" fill="#fff" stroke="currentColor"'
    ' stroke-width="6"/>',
    "equal": f'<g {FILL}><rect x="24" y="33" width="52" height="10"/>'
    '<rect x="24" y="57" width="52" height="10"/></g>',
    "different": f'<path d="M28 28L72 72M72 28L28 72" {LINE} stroke-width="10"/>',
    "less": f'<polyline points="68,14 32,50 68,86" {LINE} stroke-width="13"/>',
    "dot_white": '<circle cx="50" cy="50" r="42" fill="#fff" stroke="currentColor"'
    ' stroke-width="10"/>',
    "dot_black": f'<circle cx="50" cy="50" r="47" {FILL}/>',
    "check": f'<polyline points="18,52 40,74 82,28" {LINE} stroke-width="12"/>',
    "cross": f'<path d="M24 24L76 76M76 24L24 76" {LINE} stroke-width="12"/>',
}

# name, Unicode fallback, label, and either a vendored emoji or the drawing.
REGISTRY: dict[str, Icon] = {
    icon.name: icon
    for icon in (
        Icon("star", "\u2605", "star", markup=_star()),
        Icon("queen", "\u265b", "queen", markup=CROWN),
        Icon("dog", "\U0001f415", "dog", markup=DOG),
        Icon("puppy", "\U0001f436", "puppy", markup=PUPPY),
        Icon("tent", "\u25b2", "tent", emoji="26fa"),
        Icon("tree", "\u2663", "tree", emoji="1f332"),
        Icon("mine", "\u2731", "mine", emoji="1f4a3"),
        Icon("flag", "\u2691", "flag", emoji="1f6a9"),
        Icon("bulb", "\u25cf", "bulb", emoji="1f4a1"),
        Icon("wall", "\u25a0", "wall", markup=SHAPES["wall"]),
        Icon("filled", "\u25a0", "filled", markup=SHAPES["filled"]),
        Icon("water", "\u00b7", "water", markup=SHAPES["water"]),
        Icon("disc_black", "\u25cf", "one", markup=SHAPES["disc_black"]),
        Icon("disc_white", "\u25cb", "zero", markup=SHAPES["disc_white"]),
        Icon("equal", "=", "equal", markup=SHAPES["equal"]),
        Icon("different", "\u00d7", "different", markup=SHAPES["different"]),
        Icon("less", "<", "smaller than", markup=SHAPES["less"]),
        Icon("dot_white", "\u25cb", "white dot", markup=SHAPES["dot_white"]),
        Icon("dot_black", "\u25cf", "black dot", markup=SHAPES["dot_black"]),
        Icon("check", "\u2713", "yes", markup=SHAPES["check"]),
        Icon("cross", "\u2717", "no", markup=SHAPES["cross"]),
        Icon("carpet", "\u25a6", "carpet", markup=CARPET, view=(0, 0, 121, 121)),
        Icon("well", "\u25ce", "well", markup=WELL, view=(0, 0, 121, 121)),
        Icon("allium", "\u273f", "allium", markup=ALLIUM),
    )
}

# Murdoku object names drawn with a registry icon rather than an emoji.
OBJECT_ICONS = {"tapijt": "carpet", "carpet": "carpet", "rug": "carpet", "tatami": "carpet",
                "waterput": "well", "well": "well",
                "sierui": "allium", "allium": "allium"}  # fmt: skip

# Dutch names as used in the puzzles, plus English synonyms.
CATALOGUE: dict[str, str] = {
    # outdoors
    "boom": "1f333", "tree": "1f333",
    "struik": "1f33f", "bush": "1f33f",
    "bloem": "1f337", "flower": "1f337", "tulp": "1f337", "tulip": "1f337",
    "zonnebloem": "1f33b", "sunflower": "1f33b",
    "roos": "1f339", "rose": "1f339",
    "madeliefje": "1f33c", "daisy": "1f33c",
    "hibiscus": "1f33a",
    "paddenstoel": "1f344", "mushroom": "1f344",
    "boulder": "1faa8", "rots": "1faa8", "rock": "1faa8",
    "paard": "1f40e", "horse": "1f40e",
    "muis": "1f401", "mouse": "1f401",
    "vuurtje": "1f525", "kampvuur": "1f525", "campfire": "1f525", "fire": "1f525",
    "tent": "26fa",
    "parasol": "26f1", "umbrella": "26f1",
    "fontein": "26f2", "fountain": "26f2",
    "vijver": "1fab7", "pond": "1fab7",
    "ton": "1f6e2", "barrel": "1f6e2",
    "standbeeld": "1f5ff", "statue": "1f5ff",
    "glijbaan": "1f6dd", "slide": "1f6dd",
    "klimwand": "1f9d7", "climbing_wall": "1f9d7",
    "kas": "1fab4", "plant": "1fab4", "greenhouse": "1fab4",
    "lantaarn": "1f3ee", "lantern": "1f3ee",
    "fiets": "1f6b2", "bicycle": "1f6b2",
    "auto": "1f697", "car": "1f697",
    "boot": "26f5", "boat": "26f5",
    "brug": "1f309", "bridge": "1f309",
    # Japanese
    "sakura": "1f338", "cherry_blossom": "1f338",
    "shrine": "26e9", "torii": "26e9",
    "castle": "1f3ef", "fuji": "1f5fb",
    "taiko": "1f941", "drum": "1f941",
    "carp": "1f38f", "koinobori": "1f38f",
    "bonsai": "1f38d", "tanabata": "1f38b",
    "tea": "1f375", "sake": "1f376",
    "scroll": "1f4dc", "hanafuda": "1f3b4",
    # indoors
    "bank": "1f6cb", "bankje": "1f6cb", "couch": "1f6cb", "sofa": "1f6cb", "bench": "1f6cb",
    "stoel": "1fa91", "chair": "1fa91",
    "window": "1fa9f",
    "bed": "1f6cf",
    "bad": "1f6c1", "bathtub": "1f6c1",
    "douche": "1f6bf", "shower": "1f6bf",
    "toilet": "1f6bd",
    "kast": "1f5c4", "cabinet": "1f5c4",
    "boekenkast": "1f4da", "boeken": "1f4da", "books": "1f4da",
    "tv": "1f4fa", "televisie": "1f4fa",
    "piano": "1f3b9",
    "gitaar": "1f3b8", "guitar": "1f3b8",
    "lamp": "1f4a1",
    "klok": "1f570", "clock": "1f570",
    "schilderij": "1f5bc", "painting": "1f5bc",
    "spiegel": "1fa9e", "mirror": "1fa9e",
    "ladder": "1fa9c",
    "tafel": "1f37d", "table": "1f37d",
    "bento": "1f371", "lunchbox": "1f371",
    "kaas": "1f9c0", "cheese": "1f9c0",
    "bureau": "1f5a5", "desk": "1f5a5", "computer": "1f5a5",
    "kookeiland": "1f373", "fornuis": "1f373", "stove": "1f373", "oven": "1f373",
    "kombuis": "1f372", "galley": "1f372",
    "koffer": "1f9f3", "suitcase": "1f9f3",
    "kruik": "1f3fa", "amphora": "1f3fa", "vase": "1f3fa",
}  # fmt: skip


def _base(name: str) -> str:
    return name.lower().rstrip("0123456789").rstrip("_")


def code_for(name: str) -> str | None:
    """The emoji code point for an object name; 'boom2' finds 'boom'.

    A literal code point such as 'U+1F35C' is accepted too.
    """
    literal = re.fullmatch(r"[Uu]\+([0-9a-fA-F]{4,6})", name)
    if literal:
        return literal[1].lower()
    return CATALOGUE.get(_base(name))


def lookup(name: str) -> Icon | None:
    """The registry icon a puzzle family names, such as "star" or "tent"."""
    return REGISTRY.get(name)


def object_icon(name: str) -> Icon | None:
    """The icon for a Murdoku object or a figure's `icon=`, if one is vendored.

    These names mean what the catalogue says ("tree" is a deciduous tree), so
    they are looked up apart from the family registry.
    """
    if _base(name) in OBJECT_ICONS:
        return REGISTRY[OBJECT_ICONS[_base(name)]]
    code = code_for(name)
    if code is None or svg.emoji_markup(code) is None:
        return None
    return Icon(name, chr(int(code, 16)), name.replace("_", " "), emoji=code)


def symbol(name: str) -> str:
    """The Unicode fallback for registry icon `name`."""
    return REGISTRY[name].unicode


def draw(
    canvas: svg.Canvas,
    name: str | Icon,
    box: Box,
    *,
    tint: svg.Colour | None = None,
    crop: bool = False,
    stretch: bool = False,
    rotate: float = 0,
) -> bool:
    """Draw icon `name` (a registry name, or an `Icon`) into `box`; False if there is none.

    `crop` fits a picture's visible part rather than its whole square, `stretch`
    fills the box exactly, and `rotate` turns it counter-clockwise (degrees).
    """
    icon = lookup(name) if isinstance(name, str) else name
    if icon is None:
        return False
    if icon.emoji is not None:
        return canvas.emoji(icon.emoji, box, crop=crop, stretch=stretch, rotate=rotate)
    assert icon.markup is not None
    canvas.place(
        f"icon-{icon.name}", icon.markup, icon.view, box, stretch=stretch, rotate=rotate, tint=tint
    )
    return True


def to_svg(name: str | Icon, size: int = 64, tint: svg.Colour = (26, 26, 26)) -> str | None:
    """A standalone square SVG of icon `name` on a transparent background."""
    canvas = svg.Canvas(size, size, background="none")
    if not draw(canvas, name, (0, 0, size, size), tint=tint):
        return None
    return canvas.to_svg()


def png(name: str | Icon, size: int = 64) -> bytes | None:
    """A square PNG of icon `name`, or None if there is no such icon."""
    picture = to_svg(name, size)
    return None if picture is None else svg.rasterise(picture)
