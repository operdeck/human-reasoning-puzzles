# Human Reasoning Puzzles

**Play free logic puzzles online, and build your own with an explainable Python constraint solver.**

[![Play the puzzles](https://img.shields.io/badge/%E2%96%B6%20Play%20the%20puzzles-online-2ea44f?style=for-the-badge)](https://operdeck.github.io/human-reasoning-puzzles/)
[![Play Murdoku online](https://img.shields.io/badge/%F0%9F%94%8E%20Play%20Murdoku-murder%20mysteries-8957e5?style=for-the-badge)](https://operdeck.github.io/human-reasoning-puzzles/murdoku/)

Explore a growing collection of playable and printable puzzles, from Sudoku,
Queens and Star Battle to Zebra grids and custom Murdoku mystery series. An explainable
constraint engine powers the solver, which solves the way a person would, with named
deduction rules rather than search; Puzzle Lab helps create and validate new
puzzles from seeds and specifications, while dedicated Murdoku tools turn loose
clues and board sketches into original mysteries.

**For players:** [Murdoku](https://operdeck.github.io/human-reasoning-puzzles/murdoku/), Sudoku, Queens, Kakuro,
Akari and more run in the browser, with notes and auto-marking. **For developers:** a
Python 3.12 constraint-propagation engine, a puzzle generator and difficulty grader, and a
TypeScript + Vite player, all Apache-2.0.

## Credits

**Murdoku is [Manuel Garand](https://murdoku.com)'s invention, not this project's.** He is
a puzzle maker from Montréal, and his Murdoku books (Lannoo in Dutch, Union Square & Co.
in English) are the real thing: they are better designed and more fun than the cases in
this repository, so buy one and solve it with pen and paper. The Murdoku puzzles here are
the author's own, some of them written with AI help; they are an homage, not a
replacement. Murdoku is a trademark of Digivoid Studios Inc., and this project is not
affiliated with it.

The same line stands under every Murdoku board in the player, on the home page and the
Murdoku landing page, on each Murdoku puzzle's own page, and in front of a generated
`--docx` booklet that contains Murdoku cases. The Sudoku, Queens, Kakuro and other
families get their own puzzles only.

## Quick start

Requires Python 3.12+. Run directly with `uv`:

```bash
uv run csp examples/sudoku_1_4x4.txt
uv run csp examples/demo/murdoku_1_first_case.txt --explain
uv run csp examples/queens_6_4x4.txt --show-model
uv run csp examples/logicgrid_1_3x3.txt --brute-force
uv run csp examples/akari_1_6x6.txt --svg akari.svg
uv run csp examples/battleships_1_6x6_fleet.txt --explain
uv run puzzle-lab rate examples/queens_1_4x4.txt
uv run puzzle-lab search examples --family tango --tier hard
uv run puzzle-lab fresh starbattle --size 7 --stars 1 --tier easy --output /tmp/queens.txt
```

`--grade` reports the hardest deduction used. `--show-model` explains the compiled constraints. `--brute-force` checks uniqueness. `--explain` writes Murdoku narratives or Battleships deductions with named rules and reasons; `--svg [FILE]` draws the puzzle (and, once solved, the solution) as SVG with `uv sync --extra svg`; `--png` rasterises that same picture with `uv sync --extra png`, and `--svg --interactive` writes only the blank board, with cell ids for an app. `--export DIR` writes everything the [web player](#play-in-the-browser) needs: per puzzle a JSON bundle and the interactive board, plus an `index.json` (needs `uv sync --extra svg`; exits non-zero if any puzzle fails). Pictures use bundled icons and font only ([licences](src/csp/assets/NOTICE.md)), never the network. `--docx [FILE]` writes an editable Word booklet for one puzzle of any family, or for a glob such as `"examples/**/*.txt"` (puzzles first, then their solutions with the solved board and solving steps; needs `uv sync --extra docx`). Without puzzle files, `--docx` takes every Murdoku in `examples/` (not the test puzzles) and writes `booklet.docx`. `--pdf [FILE]` works the same way but writes a PDF (default `booklet.pdf` without puzzle files), converting that Word booklet with LibreOffice or, on macOS, Microsoft Word or Pages.

Browse the full [visual puzzle index](https://operdeck.github.io/human-reasoning-puzzles/).
For [collection and grading notes](docs/puzzle-collection.md), or the [model rules and file formats](docs/model-and-puzzle-formats.md), see the detail guides.
Use `puzzle-lab fresh`, `generate`, `rate`, `search`, and `audit` to create and validate non-Murdoku
examples; see the [authoring workflow](.github/skills/non-murdoku-puzzle-authoring/SKILL.md).
Murdoku retains its separate tools and skill.

Calcudoku examples and Puzzle Lab generation avoid single-cell cages. Older
files still work: a single-cell target is a clue whose digit you enter normally.
Use optional `--grade` with `fresh` or `generate` when preserving a specific
deduction technique, such as `--tier hard --grade cover3`.

The [Battleships examples](docs/model-and-puzzle-formats.md#battleships) now use complete fleets:
straight ships, no touching (including diagonals), line totals, and shaped
givens. The collection has five boards: the 6x6 starter and two 8x8 boards are medium
(`count` or `subsumption`), and two more 8x8 boards are hard (`chains`).
*Buoys in the channel*, *Broken radio signals*, and *Fogbound convoy* each show
water waves, unspecified `?` segments, single-cell circles, rounded ends, and
square middles. All five need the fleet rules, not just row and column arithmetic.
Generate another original board with
`uv run puzzle-lab fresh battleships --size 6 --tier medium --seed 136 --output /tmp/fleet.txt`.

## A first Murdoku case

Four people on a 4 × 4 floor plan with three rooms. Everyone stands in a
different row and column. Trees, bushes, tables, and cabinets block cells;
chairs and the bed are standable.

<table>
<tr><td><img src="docs/images/murdoku_1_first_case.png" width="230" alt="Murdoku first case"></td><td>

**Clues**

1. Ingrid is on a chair.
2. Joost is next to the tree.
3. Lotte is on the bed.

**Wouter**, the victim, takes the last free square and is alone with the
murderer.

</td></tr>
</table>

For every playable example, see the [puzzle index](https://operdeck.github.io/human-reasoning-puzzles/). For
the complete syntax and supported rules, see [Model and puzzle formats](docs/model-and-puzzle-formats.md).

<details>
<summary>Show the worked solution</summary>

Joost is at r1c1. Lotte is at r4c2, so Ingrid can only be at r3c4. Wouter is
at r2c3. Wouter and Ingrid share the sitting room, so **Ingrid did it**.

<img src="docs/images/murdoku_1_first_case-solution.png" width="230" alt="Murdoku solution">
</details>

## A few examples

The solver handles very different kinds of logic. Here are a few; [browse and play the full collection](https://operdeck.github.io/human-reasoning-puzzles/) or read the [collection and grading notes](docs/puzzle-collection.md).

<table>
<tr>
<td><strong><a href="examples/queens_3_7x7.txt">Queens</a></strong><br>Star Battle with one queen per row, column, and region; queens may not touch.<br><img src="docs/images/queens_3_7x7-solution.png" width="150" alt="Solved Queens puzzle"></td>
<td><strong><a href="examples/sudoku_16_4x4_kropki_consecutive_thermometers.txt">Kropki Sudoku</a></strong><br>Sudoku with adjacency dots and a thermometer.<br><img src="docs/images/sudoku_16_4x4_kropki_consecutive_thermometers.png" width="150" alt="Kropki Sudoku puzzle"></td>
<td><strong><a href="examples/starbattle_2_8x8.txt">Star Battle</a></strong><br>Place stars by row, column, and region counts without touching.<br><img src="docs/images/starbattle_2_8x8-solution.png" width="150" alt="Solved Star Battle puzzle"></td>
</tr>
<tr>
<td><strong><a href="examples/logicgrid_1_3x3.txt">Zebra logic grid</a></strong><br>Use clues to match items across categories.<br><img src="docs/images/logicgrid_1_3x3-solution.png" width="150" alt="Solved logic grid"></td>
<td><strong><a href="examples/tents_3_4x4.txt">Tents and Trees</a></strong><br>Pair each tree with a tent, while satisfying line counts.<br><img src="docs/images/tents_3_4x4-solution.png" width="150" alt="Solved Tents and Trees puzzle"></td>
<td><strong><a href="examples/akari_1_6x6.txt">Light Up / Akari</a></strong><br>Light every open cell without bulbs seeing each other.<br><img src="docs/images/akari_1_6x6-solution.png" width="150" alt="Solved Akari puzzle"></td>
</tr>
</table>

The newest families come from Simon Tatham's puzzle collection and compile to the same few constraint types, with no change to the engine:

<table>
<tr>
<td><strong><a href="examples/towers_2_5x5.txt">Towers</a></strong><br>Each height once per row and column; an edge clue counts the towers you can see.<br><img src="docs/images/towers_2_5x5-solution.png" width="150" alt="Solved Towers puzzle"></td>
<td><strong><a href="examples/mosaic_2_5x5.txt">Mosaic</a></strong><br>Black or white, so every number counts the black cells around it.<br><img src="docs/images/mosaic_2_5x5-solution.png" width="150" alt="Solved Mosaic puzzle"></td>
<td><strong><a href="examples/dominosa_2_6x7.txt">Dominosa</a></strong><br>Cover the grid with dominoes, each pair of numbers used once; the numbers are pips, as on a stone.<br><img src="docs/images/dominosa_2_6x7-solution.png" width="150" alt="Solved Dominosa puzzle"></td>
</tr>
<tr>
<td><strong><a href="examples/rectangles_3_9x9.txt">Rectangles</a></strong><br>Cut the grid into rectangles, each holding one number equal to its area.<br><img src="docs/images/rectangles_3_9x9-solution.png" width="150" alt="Solved Rectangles puzzle"></td>
<td><strong><a href="examples/magnets_3_6x6.txt">Magnets</a></strong><br>Place plus and minus poles so touching magnets repel and the counts match.<br><img src="docs/images/magnets_3_6x6-solution.png" width="150" alt="Solved Magnets puzzle"></td>
<td><strong><a href="examples/undead_5_5x5.txt">Undead</a></strong><br>Ghosts, vampires and zombies seen along sight lines that bend at mirrors.<br><img src="docs/images/undead_5_5x5-solution.png" width="150" alt="Solved Undead puzzle"></td>
</tr>
<tr>
<td><strong><a href="examples/pattern_2_8x8.txt">Pattern</a></strong><br>A nonogram: fill cells to match the run lengths of each row and column.<br><img src="docs/images/pattern_2_8x8-solution.png" width="150" alt="Solved Pattern puzzle"></td>
<td><strong><a href="examples/map_3_9x9.txt">Map</a></strong><br>Four-colour the regions so no two neighbours share a colour.<br><img src="docs/images/map_3_9x9-solution.png" width="150" alt="Solved Map puzzle"></td>
<td><strong><a href="examples/thermometers_2_5x5.txt">Thermometers</a></strong><br>Fill each thermometer from its bulb so every row and column holds its count.<br><img src="docs/images/thermometers_2_5x5-solution.png" width="150" alt="Solved Thermometers puzzle"></td>
</tr>
<tr>
<td><strong><a href="examples/kakuro_2_5x5.txt">Kakuro</a></strong><br>Digits 1 to 9 in runs that add up to their clue without repeating.<br><img src="docs/images/kakuro_2_5x5-solution.png" width="150" alt="Solved Kakuro puzzle"></td>
<td><strong><a href="examples/hidato_2_5x5.txt">Hidato</a></strong><br>Write 1, 2, 3, … so every number touches the next; Numbrix allows only sides.<br><img src="docs/images/hidato_2_5x5-solution.png" width="150" alt="Solved Hidato puzzle"></td>
<td><strong><a href="examples/killer_2_6x6.txt">Killer Sudoku</a></strong><br>Sudoku with caged sums; Arrow, Even/Odd, Sandwich and Skyscraper variants too.<br><img src="docs/images/killer_2_6x6-solution.png" width="150" alt="Solved Killer Sudoku puzzle"></td>
</tr>
</table>

## Play in the browser

`web/` is a small TypeScript + Vite player for every example, published to [GitHub Pages](https://operdeck.github.io/human-reasoning-puzzles/)
by `.github/workflows/pages.yml` on each push to `main` (repository Settings → Pages →
Source: GitHub Actions). Python stays the single source of truth: the player knows no
puzzle family, it only reads the bundles from `--export`. The index shows one
representative unsolved board preview per puzzle group (including each Murdoku
series), with compact puzzle links in one or two columns beside it. Select a
puzzle title to open its player.
Locally (Node 22.12 or later):

```sh
uv sync --extra svg
cd web && npm install
npm run export   # writes web/public/puzzles
npm run dev      # or: npm test, npm run build
```

`npm run build` also prerenders a static page per puzzle, a Murdoku landing page,
`sitemap.xml` and `robots.txt` over the player, so search engines see real pages
(`web/scripts/prerender.mjs`). The one-time repository topics, site verification and
sitemap submission that go with it are in [discoverability notes](docs/discoverability.md).

Place a piece with a click or tap (or arrow keys and Space, or the piece's number key),
cross off a square with right-click, long-press or the Cross tool, and undo with Ctrl+Z.
Auto-mark crosses the squares a placement rules out (in Akari it lights what a bulb sees),
and crosses out the palette buttons of the pieces already on the board — grey, like the
auto-marked squares. Pieces a board may hold more than once (mines, stars) keep their button.
Digit puzzles take pencil marks: the Notes tool (key N) writes small digits, and auto-mark
hides any that a placed peer rules out. Progress is kept in the browser.
Conflicting placements or notes show the other cell and, when available, the
exported rule name; mistakes remain editable rather than being silently refused.
The Warnings toggle controls this feedback independently of Auto-mark. It is on
by default, and its setting is saved with each puzzle's progress.

## Licence

The code is Apache 2.0 (see `LICENSE`). The puzzles in `examples/` are **not**: they are
© Otto Perdeck, all rights reserved, and may not be copied or reused without the author's
explicit permission (see `examples/LICENSE.md`); playing them on this project's own site is
allowed. Generated `--docx` booklets and the web player carry this notice.
