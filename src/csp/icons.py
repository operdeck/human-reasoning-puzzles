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
# A tatami mat with its dark cloth edges, seen from above.
TATAMI = (
    '<rect x="6" y="4" width="88" height="92" rx="3" fill="#d6cf8f" stroke="#8a8450"'
    ' stroke-width="2"/>'
    '<g stroke="#bdb571" stroke-width="1.5">'
    + "".join(f'<line x1="18" y1="{y}" x2="82" y2="{y}"/>' for y in range(12, 92, 8))
    + "</g>"
    '<g fill="#2f3b4c"><rect x="6" y="4" width="10" height="92"/>'
    '<rect x="84" y="4" width="10" height="92"/></g>'
)
# A round Japanese plate with an indigo rim and two pieces of nigiri.
PLATE = (
    '<circle cx="50" cy="52" r="44" fill="#f6f1e7" stroke="#2c4a7a" stroke-width="4"/>'
    '<circle cx="50" cy="52" r="35" fill="none" stroke="#2c4a7a" stroke-width="2"'
    ' stroke-dasharray="5 4"/>'
    '<g fill="#fff" stroke="#a0a0a0" stroke-width="1.5">'
    '<rect x="28" y="34" width="20" height="36" rx="9"/>'
    '<rect x="52" y="34" width="20" height="36" rx="9"/></g>'
    '<g fill="#f08a5d"><rect x="30" y="31" width="16" height="34" rx="7"/>'
    '<rect x="54" y="31" width="16" height="34" rx="7"/></g>'
    '<g stroke="#fde3d5" stroke-width="2">'
    '<path d="M32 42L44 38M32 52L44 48M56 42L68 38M56 52L68 48"/></g>'
)
# A zaisu: the legless Japanese floor chair, with a red cushion.
ZAISU = (
    '<ellipse cx="54" cy="90" rx="38" ry="5" fill="#000" opacity="0.15"/>'
    '<path d="M16 14Q22 10 30 14L36 80H22Z" fill="#8b5a2b"/>'
    '<rect x="20" y="70" width="70" height="16" rx="4" fill="#8b5a2b"/>'
    '<rect x="34" y="58" width="56" height="15" rx="7" fill="#c0392b"/>'
    '<path d="M21 22Q25 19 29 22L32 58H25Z" fill="#c0392b"/>'
)
# Savanna trees: the flat-topped acacia and the thick-trunked baobab.
ACACIA = (
    '<ellipse cx="50" cy="94" rx="22" ry="3.5" fill="#000" opacity="0.15"/>'
    '<path d="M50 94L50 56L34 38M50 62L68 38" stroke="#6b4a2b" stroke-width="6" fill="none"'
    ' stroke-linecap="round" stroke-linejoin="round"/>'
    '<ellipse cx="50" cy="32" rx="45" ry="13" fill="#5f8a22"/>'
    '<ellipse cx="50" cy="26" rx="36" ry="9" fill="#7fa83a"/>'
)
BAOBAB = (
    '<ellipse cx="50" cy="94" rx="22" ry="3.5" fill="#000" opacity="0.15"/>'
    '<path d="M40 40L26 20M50 38V12M60 40L76 20" stroke="#9b7653" stroke-width="7"'
    ' stroke-linecap="round"/>'
    '<path d="M34 94Q28 62 38 36H62Q72 62 66 94Z" fill="#a9825c"/>'
    '<path d="M44 46Q42 70 44 90" stroke="#8a6644" stroke-width="2.5" fill="none"/>'
    '<g fill="#6b8e23"><circle cx="24" cy="18" r="10"/><circle cx="50" cy="11" r="10"/>'
    '<circle cx="78" cy="18" r="10"/></g>'
)
# A waterfall between two grey cliffs, falling into a pool.
WATERFALL = (
    '<rect x="6" y="8" width="32" height="84" rx="6" fill="#8d8f93"/>'
    '<rect x="62" y="8" width="32" height="84" rx="6" fill="#7b7d81"/>'
    '<rect x="36" y="6" width="28" height="80" fill="#5dade2"/>'
    '<g stroke="#d6eaf8" stroke-width="3"><path d="M42 10V82M50 10V82M58 10V82"/></g>'
    '<ellipse cx="50" cy="88" rx="34" ry="8" fill="#aed6f1"/>'
)


# A simple wooden train bench with a backrest and legs, keeping the seat short and sturdy.
TRAIN_BENCH = (
    '<g fill="#ce9f67" stroke="#704d2f" stroke-width="2" stroke-linecap="round">'
    '<rect x="10" y="26" width="80" height="12" rx="3"/>'
    '<rect x="15" y="10" width="70" height="16" rx="3"/>'
    '<g fill="none">'
    '<path d="M18 38V82M82 38V82M32 38V83M68 38V83"/>'
    '</g>'
    '</g>'
    '<g fill="none" stroke="#8c633f" stroke-width="2.5">'
    '<line x1="20" y1="38" x2="20" y2="82"/>'
    '<line x1="80" y1="38" x2="80" y2="82"/>'
    '<line x1="35" y1="38" x2="35" y2="83"/>'
    '<line x1="65" y1="38" x2="65" y2="83"/>'
    '</g>'
)
# A simple platform bench with visible slats and a low back, typical for railway stations.
PLATFORM_BENCH = (
    '<g fill="#cfaa75" stroke="#6f4a2d" stroke-width="2" stroke-linecap="round">'
    '<path d="M12 34H88V40H12Z"/>'
    '<path d="M10 52H90V60H10Z"/>'
    '<path d="M10 70H90V78H10Z"/>'
    '<path d="M14 18H86V30H14Z"/>'
    '<path d="M18 78V92M82 78V92M35 78V92M65 78V92" fill="none"/>'
    '</g>'
    '<g fill="none" stroke="#7c5638" stroke-width="2">'
    '<line x1="20" y1="18" x2="20" y2="78"/>'
    '<line x1="80" y1="18" x2="80" y2="78"/>'
    '</g>'
)
# A wooden park bench on cast-iron legs, wider than it is tall.
BENCH = (
    '<g stroke="#3d3d3d" stroke-width="4" stroke-linecap="round" fill="none">'
    '<path d="M14 4V52M86 4V52M8 52L14 34M92 52L86 34"/></g>'
    '<g fill="#b07a43" stroke="#7a5230" stroke-width="1.5">'
    '<rect x="6" y="5" width="88" height="8" rx="2"/>'
    '<rect x="6" y="16" width="88" height="8" rx="2"/>'
    '<rect x="3" y="30" width="94" height="10" rx="2"/></g>'
)
WINDOW = (
    '<g fill="#dfeaf5" stroke="#49586a" stroke-width="2.5">'
    '<rect x="8" y="8" width="84" height="84" rx="6"/>'
    '<path d="M50 8V92M8 50H92" fill="none" stroke="#6d7d8f" stroke-width="2"/>'
    '</g>'
)
CORPSE = (
    '<g fill="#d7d7d7" stroke="#2d2d2d" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M28 84L34 54C40 33 57 28 68 39L78 54L75 90H32Z"/>'
    '<path d="M42 28L50 16L59 28L57 41H44Z" fill="#d6b88d"/>'
    '<circle cx="58" cy="27" r="11" fill="#d7d7d7"/>'
    '<path d="M40 47C48 57 57 60 66 58" fill="none" stroke="#232323" stroke-width="3"/>'
    '<path d="M36 57L47 68M50 61L61 74" fill="none" stroke="#7b1d1d" stroke-width="4"/>'
    '<path d="M62 52L70 56M65 60L74 64M51 77L58 85" fill="none" stroke="#7b1d1d" stroke-width="3"/>'
    '<path d="M26 82L32 74L38 83" fill="none" stroke="#7b1d1d" stroke-width="3"/>'
    '</g>'
)
TRACK = (
    '<g fill="#5a5c62" stroke="#4e5258" stroke-width="2.5">'
    '<rect x="8" y="30" width="84" height="12" rx="2"/>'
    '<rect x="8" y="58" width="84" height="12" rx="2"/>'
    '<path d="M20 22V82M50 18V86M80 22V82" fill="none" stroke="#6c7178" stroke-width="5"/>'
    '</g>'
)
INFO_BOARD = (
    '<g fill="#d9c79a" stroke="#5a3e2a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="18" y="18" width="64" height="58" rx="4"/>'
    '<path d="M24 30H76M24 42H76M24 54H64" fill="none" stroke="#5a3e2a" stroke-width="2"/>'
    '<path d="M30 22V12H70V22" fill="none"/>'
    '<g fill="#c2a46d"><rect x="30" y="66" width="8" height="18"/><rect x="62" y="66" width="8" height="18"/></g>'
    '<g fill="#4d4d4d"><rect x="40" y="24" width="20" height="12"/><rect x="36" y="42" width="28" height="8"/></g>'
    '<g fill="none" stroke="#5a3e2a" stroke-width="2"><path d="M20 82H80"/></g>'
    '</g>'
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
        Icon("bench", "\u2b0c", "park bench", markup=BENCH, view=(0, 0, 100, 56)),
        Icon("train_bench", "\u2b0c", "train bench", markup=TRAIN_BENCH, view=(0, 0, 100, 92)),
        Icon("perron_bank", "\u2b0c", "platform bench", markup=PLATFORM_BENCH, view=(0, 0, 100, 92)),
        Icon("trein_bank", "\u2b0c", "train bench", markup=TRAIN_BENCH, view=(0, 0, 100, 92)),
        Icon("platform_bench", "\u2b0c", "platform bench", markup=PLATFORM_BENCH, view=(0, 0, 100, 92)),
        Icon("track", "\u25a0", "railway track", markup=TRACK, view=(0, 0, 100, 100)),
        Icon("window", "\u25a7", "window", markup=WINDOW, view=(0, 0, 100, 100)),
        Icon("info_board", "\u2139", "information board", markup=INFO_BOARD, view=(0, 0, 100, 100)),
        Icon("corpse", "\u2620", "corpse", markup=CORPSE, view=(0, 0, 100, 100)),
        Icon("tatami", "\u25a5", "tatami mat", markup=TATAMI),
        Icon("plate", "\u25cd", "Japanese plate", markup=PLATE),
        Icon("zaisu", "\u2441", "Japanese chair", markup=ZAISU),
        Icon("acacia", "\u2663", "acacia", markup=ACACIA),
        Icon("baobab", "\u2660", "baobab", markup=BAOBAB),
        Icon("waterfall", "\u2307", "waterfall", markup=WATERFALL),
    )
}

# Murdoku object names drawn with a registry icon rather than an emoji.
OBJECT_ICONS = {"bench": "bench", "bankje": "bench", "parkbank": "bench",
                "train_bench": "train_bench", "trein_bank": "trein_bank",
                "platform_bench": "platform_bench", "perron_bank": "perron_bank",
                "tapijt": "carpet", "carpet": "carpet", "rug": "carpet",
                "tatami": "tatami", "plate": "plate", "sara": "plate",
                "zaisu": "zaisu", "japanese_chair": "zaisu",
                "acacia": "acacia", "baobab": "baobab",
                "waterval": "waterfall", "waterfall": "waterfall",
                "waterput": "well", "well": "well",
                "sierui": "allium", "allium": "allium",
                "track": "track", "spoor": "track",
                "raam": "window", "window": "window", "info_bord": "info_board", "informatie_bord": "info_board",
                "lijk": "corpse", "corpse": "corpse"}  # fmt: skip

# Dutch names as used in the puzzles, plus English synonyms.
CATALOGUE: dict[str, str] = {
    # outdoors
    "boom": "1f333", "tree": "1f333",
    "den": "1f332", "dennenboom": "1f332", "pine": "1f332",
    "palm": "1f334", "palmboom": "1f334", "palm_tree": "1f334",
    "cactus": "1f335",
    "gras": "1f33e", "helmgras": "1f33e", "grass": "1f33e", "riet": "1f33e", "reeds": "1f33e",
    "boomstam": "1fab5", "stam": "1fab5", "log": "1fab5",
    "waterlelie": "1fab7", "lotus": "1fab7",
    "hut": "1f6d6", "berghut": "1f6d6",
    "berg": "1f3d4", "mountain": "1f3d4",
    "leeuw": "1f981", "lion": "1f981",
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
    "castle": "1f3ef", "fuji": "1f5fb", "tokyo_tower": "1f5fc",
    "taiko": "1f941", "drum": "1f941",
    "carp": "1f38f", "koinobori": "1f38f",
    "bonsai": "1f38d", "tanabata": "1f38b",
    "tea": "1f375", "sake": "1f376",
    "scroll": "1f4dc", "hanafuda": "1f3b4",
    # indoors
    "bank": "1f6cb", "couch": "1f6cb", "sofa": "1f6cb", "bankstel": "1f6cb",
    "stoel": "1fa91", "chair": "1fa91",
    "window": "1fa9f",
    "bed": "1f6cf", "tweepersoonsbed": "1f6cf", "double_bed": "1f6cf",
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
    "taart": "1f370", "cake": "1f370",
    "mand": "1f9fa", "basket": "1f9fa",
    "schooltas": "1f392", "backpack": "1f392", "schoolbag": "1f392",
    "arcade": "1f579", "joystick": "1f579",
    "microfoon": "1f3a4", "microphone": "1f3a4",
    "knuffel": "1f9f8", "teddy": "1f9f8", "teddy_bear": "1f9f8",
    "bal": "26bd", "ball": "26bd", "voetbal": "26bd", "football": "26bd",
    "emmer": "1faa3", "bucket": "1faa3",
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
