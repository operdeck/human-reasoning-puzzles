# Web interface

Developer guide for `web/`, the TypeScript + Vite player. Players use the
[puzzle index](https://operdeck.github.io/human-reasoning-puzzles/); puzzle authors
need [Model and puzzle formats](model-and-puzzle-formats.md) and
[Murdoku clue grammar](murdoku-grammar.md).

## Local setup

Node 22.12 or later, and Python 3.12+:

```sh
uv sync --extra svg
cd web && npm install
npm run export   # writes web/public/puzzles from --export bundles
npm run dev      # or: npm test, npm run build
```

`npm run build` also prerenders a static page per puzzle, a Murdoku landing page,
`sitemap.xml` and `robots.txt`, so search engines see real pages
(`web/scripts/prerender.mjs`). The one-time repository topics, site verification
and sitemap submission are in [discoverability notes](discoverability.md).
Opening a puzzle's own page starts the player directly; its static picture and
play link remain available when JavaScript is disabled.

## Ground rules

- **Backdrops:** decoration only, never part of the solution. They are omitted on
  phones and on booklet pages too full for them; desktop boards, booklet pictures
  and landing previews keep them.
- **Controls:** click or tap a cell, or use the arrow keys and Space or the piece's
  number key. Right-click, long-press or the Cross tool crosses a square;
  Ctrl+Z undoes.
- **Auto-mark:** crosses ruled-out squares and used palette buttons (in Akari it
  lights what a bulb sees). Items a board may hold more than once (mines, stars)
  keep their button.
- **Notes:** digit puzzles only, key N. Auto-mark hides notes ruled out by a
  placed peer.
- **Warnings:** independent of auto-mark, on by default, saved per puzzle.
  Mistakes stay editable; conflicting placements show the other cell and the
  exported rule when available.
- **Progress** is saved in the browser.
- **Murdoku:** figure cards replace the figure buttons; select a card to place a
  figure. Hover over a cell, or reach it with the arrow keys, to read its area,
  objects, count rules, marked-cell rules and occupant. The Case details tab keeps
  objects, board symbols, roles and attributes together. References to figures
  are bold. Object tooltips use the object name as a label, keeping any article
  supplied by the puzzle author even when the object occurs in multiple cells.
  The standard `door` and `window` symbols are localized in Dutch tooltips
  unless the author supplies a name in `Words:`.
- **Family boundary:** family knowledge lives in `src/csp/web.py`, not in
  TypeScript. After changing `web/`, run `npx tsc --noEmit` and `npm test`.

## Installable app (PWA)

The published site can be added to an iPhone home screen and opens in standalone
mode (no Safari bars):

- **Icons** live in `web/public/`: `apple-touch-icon.png` (180×180),
  `icon-192.png`, `icon-512.png`. They come from the README's first Murdoku case
  (`docs/images/murdoku_1_first_case.png`), cropped to the board and flattened on
  white so iOS does not paint the transparent parts black. Keep the board inside
  the 10% margin; iOS rounds the corners.
- **Manifest:** `web/public/manifest.json` is the `npm run dev` copy. The build
  (`web/scripts/prerender.mjs`) writes the published `dist/manifest.json` from
  `SITE_URL`, with absolute `start_url`, `scope` and icon paths under
  `/human-reasoning-puzzles/`. Change the site path in one place, not in the
  icons.
- **Head:** every prerendered page (home, `/murdoku/`, `/p/<id>/`) gets the
  manifest, apple-touch-icon, apple-mobile-web-app meta tags and `theme-color`
  from `head()`; the viewport is `viewport-fit=cover`. `web/index.html` carries
  the dev copy with relative paths.
- **Safe areas:** `body` pads with `env(safe-area-inset-*)`; every puzzle page
  has a visible "← All puzzles" link, so standalone mode always has a way back.
- **Offline:** the build writes `dist/sw.js` with a cache version hashed from the
  precached files. It precaches the app shell, the `/murdoku/` page, the CSS/JS,
  the manifest, the icons and every `puzzles/*.json|svg` bundle (419 URLs, about
  13 MB), so all puzzles are playable offline after the first load/install.
  Assets and bundles are cache-first; navigations are network-first and fall back
  to the cached shell, whose path-based route (`puzzleIdFromPath`) loads the
  cached bundle. A visited `/p/<id>/` page is also cached on the fly. A new build
  changes the version, so `activate` deletes the old cache. `web/index.html`
  intentionally has no registration (dev); the prerendered pages register
  `${root}sw.js` from `head()`.

Test on an iPhone with Safari → Share → Add to Home Screen. iOS caches the icon:
remove and re-add the shortcut after changing it. Locally, `npm run build`
followed by `npx vite preview` shows the prerendered pages and the manifest.


Peer groups may include a localized `description` of the rule they implement.
The generic player uses these groups to explain conflicting placements or pencil
marks by naming the other occupied cell, without consulting the hidden solution.
It still allows mistakes; this feedback does not reject or correct placements.
Players can disable this feedback with the Warnings toggle beside Auto-mark.
Warnings default to on, including for previously saved games; each puzzle saves
the choice independently of auto-mark, and clearing the board preserves it.

`--export DIR` writes, per puzzle, `<stem>.svg` (the interactive board) and `<stem>.json`, plus `DIR/index.json` (`schema`, `license`, and one entry per puzzle with `id`, `number`, `section`, `title`, `family`, `familyLabel`, `size`, `grade`, `deductive`, `playable`, in reading order). `number` and `section` (bundles carry them too) come from `collection.arrange`, as in the booklet. A bundle holds `size` `[rows, cols]`; `palette` (items with `id`, `label`, `symbol`, optional `svg` and `description`); `placement` (`perItem` or `perCell`, and `blocked` cells); `autoMark` (`default`, `mark` — `cross` or, for Akari, `light` — and `onPlace` scopes: `row`, `col`, `region`, `neighbors4`, `neighbors8`, `king`, `knight`, `peers`, each optionally `whenFull: n`); `regions` when a scope needs them; `peers`, the groups of cells that hold a palette item at most once (each `cells`, plus `items` when it binds only some items), read by `web.peers()` from the model's at-most-one and exactly-one constraints, so the player needs no family rules for them; `notes: true` when the player offers pencil marks (digit families); `givens` and `solution` (cell id to palette id); and the reading text: `rules`, `clues`, `key` (`name`, `text`: the door/window/point symbols), `question`, `reveal` (the booklet's `Reveal:` text, which the player shows after "Solved!" or "Opgelost!"), `headings`, `attributes`, `roles`, `language`, `license`. `deductive` is `false` exactly for the puzzles no deduction path closes — the ones graded `what_if` — so an app can flag the beyond-deduction frontier. Families the player cannot yet play have `playable: false` and an `unsupported` reason. Murdoku `key` lists only the board symbols whose meaning is not in the rules; marks, roles, attributes, area tags and the dashed count ring are stated in the rules, listed separately or drawn on the board, and the picture legend underneath a booklet board is the same compact key. The player draws the same grey cross over a palette item that `placement.perItem: 1` shows as already on the board, but only while auto-mark is on; items that may appear more than once (`placement.perCell` boards such as Minesweeper or Star Battle) are never crossed.

Each Murdoku `key` entry also includes the corresponding board symbol as `svg`. If windows with one name use both wall panes and separate icons, the key shows both.

Pieces come from the icon registry in `icons.py`: each `Icon` has a name, a Unicode `symbol` used by the text boards (★ star, ▲ tent, ♣ tree, ✱ mine, ● bulb, ■ wall/shaded, ●/○ Binairo) and either an original vector shape or a vendored Noto Emoji. Murdoku objects and figure `icon=` names are looked up in `icons.CATALOGUE` (Dutch names plus English synonyms, or `U+<code>`); unknown or unvendored icons fall back to a text label and `--lint` warns. All artwork is vendored under `src/csp/assets/` at pinned commits with its licences (`NOTICE.md`); rendering never uses the network. To add a picture, add the name to `CATALOGUE` and run `uv run python scripts/vendor_emoji.py U+<code>`; `scripts/subset_font.py` rebuilds the font subset.

## Pictures and icons

Every family has one renderer in `picture.py`; SVG, PNG, the booklet and the
player derive from it. Text is converted to paths from the bundled Noto Sans
subset, so output does not depend on installed fonts. Pieces come from
`icons.py`; Murdoku objects and figure icons use `icons.CATALOGUE`. All artwork
is vendored under `src/csp/assets/` with its licences (`NOTICE.md`); rendering
never uses the network. Add an icon to `CATALOGUE`, run
`uv run python scripts/vendor_emoji.py U+<code>`, and rebuild the font subset with
`scripts/subset_font.py`.
