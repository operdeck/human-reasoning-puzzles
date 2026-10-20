# Third-party assets

The pictures are drawn from these bundled files only; rendering never fetches
anything from the network.

## Noto Emoji (`emoji/`)

The `emoji_u<code>.svg` files are from
[googlefonts/noto-emoji](https://github.com/googlefonts/noto-emoji) at commit
`e20cbc2bbec1926686be9f9bee7d1d2cfa1fea0e` (`2D/svg/`), copyright 2013 Google LLC.
The repository's README states that the emoji images are under the Apache
License 2.0, and its `LICENSE` file is the SIL Open Font License 1.1; both
texts are included (`emoji/LICENSE-Apache-2.0.txt`, `emoji/LICENSE-OFL.txt`).

Changes, made by `scripts/vendor_emoji.py`:

- comments, editor metadata and foreign-namespace attributes are removed, and
  ids are prefixed so several pictures can share one SVG document;
- `emoji_u1f6cb.svg` ("couch and lamp") has its floor lamp removed, leaving
  the couch;
- `bounds.json` records the visible box of each picture (derived data).

## Noto Sans (`fonts/`)

`fonts/NotoSans-Regular.ttf` is a subset (Latin-1, Latin Extended-A, general
punctuation and the euro sign) of Noto Sans Regular from
[googlefonts/noto-fonts](https://github.com/googlefonts/noto-fonts) at commit
`ffebf8c1ee449e544955a7e813c54f9b73848eac`, made by `scripts/subset_font.py`.
Copyright 2018 The Noto Project Authors, under the SIL Open Font License 1.1
(`fonts/OFL.txt`). Text in pictures is drawn as paths from its glyph outlines.

## Original drawings

The star, crown, dog, carpet, well and other shapes defined in
`csp/icons.py` are original to this project.
