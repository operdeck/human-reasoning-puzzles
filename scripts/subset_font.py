"""Rebuild the bundled Noto Sans subset (a developer tool; needs network).

    uv run python scripts/subset_font.py

Downloads Noto Sans Regular from the pinned googlefonts/noto-fonts commit and
keeps only the characters pictures can write: Latin-1, Latin Extended-A,
general punctuation and the euro sign. Noto Sans has no minus sign (U+2212);
`svg.SUBSTITUTES` draws it with the en dash instead. Text in pictures is drawn
as paths from this font, so rendering never needs a system font or the network.
"""

import io
import sys
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from csp import svg  # noqa: E402

COMMIT = "ffebf8c1ee449e544955a7e813c54f9b73848eac"
SOURCE = (
    f"https://raw.githubusercontent.com/googlefonts/noto-fonts/{COMMIT}"
    "/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
)
UNICODES = [
    *range(0x20, 0x7F),
    *range(0xA0, 0x180),
    *range(0x2010, 0x2040),
    0x20AC,
]


def main() -> None:
    with urllib.request.urlopen(SOURCE) as response:
        font = TTFont(io.BytesIO(response.read()))
    options = subset.Options()
    options.layout_features = ["kern"]
    options.name_IDs = ["*"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=UNICODES)
    subsetter.subset(font)
    font.save(svg.FONT)
    print(f"wrote {svg.FONT} ({len(font.getBestCmap())} characters)")


if __name__ == "__main__":
    main()
