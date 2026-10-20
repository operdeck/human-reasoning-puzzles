"""Vendor Noto Emoji SVGs into src/csp/assets/emoji (a developer tool; needs network).

    uv run python scripts/vendor_emoji.py [U+1F35C ...]

Fetches every code point in `csp.icons.CATALOGUE` and the registry, every
picture already vendored and any code points given, from the pinned Noto Emoji
commit. Each file is
cleaned (comments and editor attributes dropped, ids prefixed so several
pictures can share one SVG document), per-picture fixes are applied, and the
visible bounds of each picture are written to `bounds.json` so the renderer can
crop without rasterising at render time. Rendering never touches the network.
"""

import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from csp import icons  # noqa: E402

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
SOURCE = (
    f"https://raw.githubusercontent.com/googlefonts/noto-emoji/{icons.NOTO_COMMIT}"
    "/2D/svg/emoji_u{code}.svg"
)
TARGET = ROOT / "src" / "csp" / "assets" / "emoji"

# Noto's U+1F6CB is 'couch and lamp': keep the couch, drop the floor lamp
# (its yellow shade, the shade's rim and the gradient-filled pole).
DROP_FILLS = {"1f6cb": {"#FFD600", "#FFFF8D", "url(#SVGID_1_)"}}


def _fill(element: ET.Element) -> str | None:
    match = re.search(r"fill:([^;]+)", element.get("style", ""))
    return match[1].strip() if match else element.get("fill")


def clean(code: str, data: bytes) -> str:
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    root = ET.fromstring(data)
    drop = DROP_FILLS.get(code, set())
    for parent in list(root.iter()):
        for child in list(parent):
            if _fill(child) in drop or (
                child.tag.endswith("Gradient") and f"url(#{child.get('id')})" in drop
            ):
                parent.remove(child)
    for parent in list(root.iter()):
        for child in list(parent):
            if not child.tag.startswith(f"{{{SVG_NS}}}"):
                parent.remove(child)  # editor metadata such as Illustrator's i:pgf
    for element in root.iter():
        for attribute in list(element.attrib):
            if attribute.startswith("{") and not attribute.startswith(f"{{{XLINK_NS}}}"):
                del element.attrib[attribute]  # editor attributes such as i:extraneous
    for attribute in list(root.attrib):
        if attribute != "viewBox":
            del root.attrib[attribute]
    prefix = f"u{code}-"
    for element in root.iter():
        for name, value in list(element.attrib.items()):
            if name == "id":
                value = prefix + value
            value = re.sub(r"url\(#([^)]+)\)", rf"url(#{prefix}\1)", value)
            if name in ("href", f"{{{XLINK_NS}}}href") and value.startswith("#"):
                value = "#" + prefix + value[1:]
            element.set(name, value)
        if element.text and not element.text.strip():
            element.text = None
        if element.tail and not element.tail.strip():
            element.tail = None
    text = ET.tostring(root, encoding="unicode")
    return re.sub(r"\s+", " ", text) + "\n"


def bounds(svg: str) -> list[float]:
    """The visible box of a 128x128 picture, in its own units."""
    import resvg_py
    from PIL import Image

    png = resvg_py.svg_to_bytes(svg_string=svg, width=512, height=512)
    box = Image.open(io.BytesIO(bytes(png))).getchannel("A").getbbox()
    assert box is not None
    return [round(v / 4, 2) for v in box]


def main(extra: list[str]) -> None:
    codes = set(icons.CATALOGUE.values())
    codes |= {icon.emoji for icon in icons.REGISTRY.values() if icon.emoji}
    codes |= {path.stem.removeprefix("emoji_u") for path in TARGET.glob("emoji_u*.svg")}
    for literal in extra:
        code = icons.code_for(literal)
        if code is None:
            raise SystemExit(f"not a code point or catalogue name: {literal}")
        codes.add(code)
    TARGET.mkdir(parents=True, exist_ok=True)
    found: dict[str, list[float]] = {}
    for code in sorted(codes):
        with urllib.request.urlopen(SOURCE.format(code=code), timeout=30) as response:
            svg = clean(code, response.read())
        (TARGET / f"emoji_u{code}.svg").write_text(svg)
        found[code] = bounds(svg)
    lines = [f"  {json.dumps(code)}: {json.dumps(box)}" for code, box in sorted(found.items())]
    (TARGET / "bounds.json").write_text("{\n" + ",\n".join(lines) + "\n}\n")
    print(f"vendored {len(found)} pictures into {TARGET}")


if __name__ == "__main__":
    main(sys.argv[1:])
