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

`npm run build` prerenders pages for search engines and visitors without
JavaScript. See [discoverability](discoverability.md) for the generated pages,
repository topics, site verification and sitemap submission.

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
  exported rule when available, without consulting the solution. Clearing
  the board preserves the setting.
- **Progress** is saved in the browser.
- **Solution steps:** the last tab of the side panel holds the worked solution, the
  same text as `--explain` and the booklet, behind a spoiler warning. The panel
  is always tabbed, so the steps never show until that tab is chosen; reading
  them changes nothing on the board. Incomplete steps say so, and a bundle
  without steps shows that none are available.
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
- **Grades:** puzzle entries show a player-facing label instead of the solver's
  internal rule name (`single`, `relations`, …), and a “Difficulty ratings”
  glossary beside the list defines each label and the “beyond deduction”
  badge. Each puzzle page shows the same label in small letters under its
  title. Labels, definitions and glossary copy live in `web/src/grades.mjs`,
  which `scripts/prerender.mjs` imports as well, so the static pages, the puzzle
  descriptions and the player agree; `index.json` keeps the raw grade for
  tooling. A new rung on the solver's ladder needs an entry there, and an
  unknown grade stays visible under its raw name.
- **Family anchors:** every index section has an id from `web/src/sections.mjs`
  (`#family-` plus the section label in lowercase words, e.g.
  `#family-tents-and-trees`), in both the prerendered and the live index. The
  router opens the index at such a hash instead of treating it as a puzzle id;
  the README gallery links to these anchors.

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
  the manifest, the icons and every `puzzles/*.json|svg` bundle, so all puzzles
  are playable offline after the first load/install.
  Assets and bundles are cache-first; navigations are network-first and fall back
  to the cached shell, whose path-based route (`puzzleIdFromPath`) loads the
  cached bundle. A visited `/p/<id>/` page is also cached on the fly. A new build
  changes the version, so `activate` deletes the old cache. `web/index.html`
  intentionally has no registration (dev); the prerendered pages register
  `${root}sw.js` from `head()`.

Test on an iPhone with Safari → Share → Add to Home Screen. iOS caches the icon:
remove and re-add the shortcut after changing it. Locally, `npm run build`
followed by `npx vite preview` shows the prerendered pages and the manifest.

## Export bundles

`--export DIR` writes an interactive `<stem>.svg` and `<stem>.json` per puzzle,
plus `index.json`. The index carries `schema`, `license` and entries with
`id`, `number`, `section`, `title`, `family`, `familyLabel`, `size`, `grade`,
`deductive` and `playable`;
`collection.arrange` supplies the booklet's numbering and sections.

Bundles include:

- `size`, `palette`, `placement`, `givens` and `solution`: board dimensions,
  available items, placement limits and cell or segment values.
- `autoMark`, `regions`, `peers` and `notes`: generic interaction metadata.
  Peer groups derive from model constraints and may include a localized rule
  `description` for warnings; they do not depend on the solution.
- `rules`, `clues`, `key`, `question`, `reveal`, `headings`, `attributes`,
  `roles`, `language` and `license`: the player-facing text.
- `solutionSteps`: worked-solution paragraphs with limited Markdown emphasis,
  and `complete`, indicating whether they reach the solution. The index omits
  these steps.

For published solved puzzles, `deductive: false` marks those graded `what_if`:
this solver needs its trial rule. Unsupported families have `playable: false`
and an `unsupported` reason. The TypeScript bundle and link types are defined
in `web/src/game.ts`.

Bridges exports a generic `links` interaction: numbered `nodes` and `segments`
with endpoints, allowed values, SVG drawings, hit targets and mutually exclusive
segments. Click a corridor to cycle zero, one and two bridges; the controls also
offer explicit single/double choices. Progress, undo, checking and hints refer
to segment ids rather than water cells. The TypeScript player reads that
metadata without implementing Bridges rules. Number totals and crossing
feedback use the player's links, not the stored solution.

Each Murdoku `key` entry also includes the corresponding board symbol as `svg`. If windows with one name use both wall panes and separate icons, the key shows both.

## Pictures and icons

Every family has one renderer in `picture.py`; SVG, PNG, the booklet and the
player derive from it. Text is converted to paths from the bundled Noto Sans
subset, so output does not depend on installed fonts. Pieces come from
`icons.py`; Murdoku objects and figure icons use `icons.CATALOGUE`. All artwork
is vendored under `src/csp/assets/` with its licences (`NOTICE.md`); rendering
never uses the network. Unknown or unvendored icons fall back to a text label
and `--lint` warns. Add an icon to `CATALOGUE`, run
`uv run python scripts/vendor_emoji.py U+<code>`, and rebuild the font subset with
`scripts/subset_font.py`.
