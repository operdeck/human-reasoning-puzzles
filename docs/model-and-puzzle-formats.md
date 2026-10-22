# Model and Puzzle File Formats

This guide describes the solver's generic model, the rule ladder, and the file formats accepted by each puzzle family. For the visual and graded examples, see [Puzzle Examples](examples.md).

## Generic model

The engine in [`src/csp/core.py`](../src/csp/core.py) knows only literals, constraints, relations, and generic deduction rules. A puzzle module parses its family format and compiles it to these primitives. No puzzle-family logic belongs in `core.py`.

- **Literal:** a named variable takes a value, such as `r3c4=7`, `a=r1c1`, or `r2c3=True`.
- **Variable:** a domain represented by an `EXACTLY_ONE` constraint. The solver reports the selected value when known.
- **`EXACTLY_ONE`:** exactly one listed literal is true.
- **`AT_MOST_ONE`:** zero or one listed literal is true. It never forces one to be true.
- **`COUNT`:** the number of true literals belongs to `allowed_counts`; a reifier is true exactly when the count is allowed.
- **Relation:** a predicate over the values of two or more named variables. Relations are checked by generalized arc consistency.

The distinction between `EXACTLY_ONE` and `AT_MOST_ONE` is essential: sparse boards leave cells empty. The solver records every deduction with its rule and supporting constraints or relations; proof replay and narration use that record without adding family knowledge to the engine.

## Deduction rules

The solver applies these rules cheapest-first and restarts at the first rule that changes the model:

| Rule | Meaning |
|---|---|
| `single` | Force the last option in an `EXACTLY_ONE` constraint, or the only literal forced by a `COUNT` with one feasible total. |
| `count` | Propagate allowed count totals, including bounds, gaps, parity, and reified counts. |
| `relations` | Generalized arc consistency: remove a value if no combination of the other variables' values supports it. |
| `subsumption` | Use the remaining capacity of an outer constraint when an inner constraint requires another true literal. |
| `cover2`, `cover3` | Combine disjoint inner constraints whose guaranteed demand fills an outer constraint's remaining capacity. |
| `chains` | Follow strong/weak links from counts and two-variable relations; a contradiction or paired weak links can eliminate a value. |
| `what_if` | On a model copy, assume a value and run only `single`, `count`, `relations`, and `subsumption`; a contradiction proves the assumption false. |

`--grade` reports the hardest rule actually used, or `unsolved` if the deduction ladder stalls. It is a measure of this solver's deductions, not a universal human difficulty rating.

## Family mappings

| Family | Variables | Generic constraints and relations |
|---|---|---|
| Sudoku | Cell | One digit per cell; each digit exactly once per row, column, box, and extra house. Optional variants add generic relations or at-most-one peer pairs. |
| Calcudoku | Cell | Sudoku rows/columns plus one arithmetic relation per cage. |
| Futoshiki | Cell | Latin-square rows/columns plus one order relation per sign. |
| Murdoku | Person | One square per person; at most one person per square, row, and column; clue predicates are relations/counts. |
| Queens-style | Region | One cell per region; exactly one queen per row/column; at most one per 2×2 window. |
| Tectonic / Suguru | Cell | Domain 1 through the size of its region; each value exactly once per region; equal values at most once in every eight-neighbor pair. |
| Star Battle | Cell | Boolean star/empty; exact star counts per row, column, and region; at most one star in each 2×2 window. |
| Zebra logic grid | Item | Each item chooses one position; each category has exactly one item per position; pair clues are relations. |
| Binairo / Tango | Cell | Boolean cell; half of each value per row/column; no three equal in a window; all rows and columns differ. Tango adds equal/different relations. |
| Tents and Trees | Cell | Boolean tent/empty; row/column counts; exactly one orthogonal tent neighbor per tree; tents do not touch, including diagonally. |
| Minesweeper-style | Cell | Boolean mine/safe; each numbered cell counts mines in its eight-neighbor set; optional total mine count. |
| Light Up / Akari | Cell | Boolean bulb/empty; visibility counts, numbered-wall counts, and at-most-one bulb per line of sight. |
| Kakurasu | Cell | Boolean filled/empty; weighted row and column sums encoded as generic relations over the line cells. |
| Battleships, counts only | Cell | Boolean occupied/empty with row and column counts. Ship shapes, fleet composition, and connectivity are not represented. |

The new-family formats below currently use `COUNT`, `AT_MOST_ONE`, `EXACTLY_ONE`, and generic relations. Binairo/Tango row and column uniqueness uses bounded-arity auxiliary relations; performance on larger boards is part of the example and benchmark checks. Kakurasu's weighted equations currently use generic relations rather than a new weighted core constraint.

## Sudoku and variants

Plain Sudoku accepts a 4×4 or 9×9 grid; `.` and `0` are blanks, and visual `|`/`-` separators are ignored. A sectioned puzzle puts the grid under `Givens:` and may add `Boxes:` and `Extra:`:

```text
Givens:
. . . .
. . . .
. . . .
. . . .
Boxes:       # optional jigsaw region ID per cell
 a a b b
 a c b b
 c c d d
 c c d d
Extra:       # optional extra-house IDs per cell; '.' means none
 x . . y
 . x y .
 . y x .
 y . . x
```

A jigsaw requires N boxes of N cells. Each extra house has N cells. `Extra:` expresses X-Sudoku diagonals, NRC boxes, and other overlapping houses.

Optional relation/peer sections are:

```text
Kropki:
white r1c1 r1c2
black r1c2 r2c2
Consecutive:
r2c1 r2c2
Thermometers:
r1c1 r2c1 r2c2
AntiKnight:
AntiKing:
```

- White Kropki dots require a difference of one; black dots require one value to be twice the other. Consecutive pairs require a difference of one.
- Thermometer paths list cells from bulb to tip. Consecutive cells in the path are orthogonal neighbors, and values strictly increase along the path.
- `AntiKnight:` and `AntiKing:` are enabled by section presence. Equal digits are forbidden for cells a knight move apart or a king move apart, respectively; overlaps with existing houses do not create duplicate constraints.

## Region-grid formats

Queens, Suguru/Tectonic, and Star Battle share the basic region-grid shape:

```text
Family: queens
Size: 4
Regions:
a: amber
b: blue
c: coral
d: green
Grid:
a a a b
a b b b
c c c c
d d d d
```

`Grid:` contains one declared region ID per cell. The family validates its own region count and size requirements. Examples in `examples/` are the executable specifications.

### Queens-style

There must be N regions on an N×N board; each is one connected area of any size from one cell up (a one-cell region fixes its queen at once). The solver places one queen in every region, row, and column, with at most one queen in every 2×2 window. Optional `Givens:` lines are `region rNcN`, for example `a r1c2`. A queen in any of the eight neighboring cells counts as touching. Unlike a chess queen, nothing reaches further than one step: only the eight neighbors are off limits.

**DogDoku.** `Family: dogdoku` is the same puzzle with dogs. An optional `Icon:` section (`queen`, `dog` or `puppy`) picks the piece in the picture and the text board; `dogdoku` defaults to `dog` and `queens` to `queen`. The icon never changes the rules. Dog puzzles are drawn with a different colour for every zone, so zone names can be colour words. A one-cell zone fixes its dog at once; the examples `dogdoku_5x5.txt`, `dogdoku_7x7.txt` and `dogdoku_9x9.txt` are built backwards from a solving order and need only eliminations (`single`, `subsumption`, `cover2`), never `chains` or `what_if`.

### Tectonic / Suguru

`Family:` is `suguru` or the alias `tectonic`. Add an optional N×N `Givens:` section of `.` or values. A cell's domain is 1 through the size of its region; each value appears once in that region, and equal values may not occupy cells that touch by side or corner.

### Star Battle

`Family: starbattle` requires one integer in `Stars:`. That many stars must appear in every row, column, and region; stars may not touch, including diagonally. Optional `Givens:` uses `?` for unknown, `.` for known empty, and `*` for a star. There must be N regions on an N×N board; each is one connected area with at least as many cells as `Stars:`, and sizes may differ. A board needs at least 8×8 for two stars and 12×12 for three, because stars may not touch.

## Zebra-style logic grids

A logic grid has no spatial board. Each category lists N distinct items; every item chooses one position from 1 through N, and each category uses every position exactly once:

```text
Family: logicgrid
Size: 3
Categories:
resident: Ada Ben Cal
color: red blue green
pet: cat dog fox
Clues:
same Ada red
left_of dog green
next_to Ben fox
```

Supported relation words are `same`, `different`, `left_of`, `before`, and `next_to`. `left_of`/`before` mean an earlier position; `next_to` means consecutive positions. Every clue names items from different or the same declared categories, as allowed by the relation.

## Binary grids

Binairo/Takuzu and Tango use an even board size from 4 through 16. `Givens:` is an N×N grid of `.`, `0`, and `1`. Each row and column has equal numbers of 0 and 1, contains no run of three equal values, and is distinct from every other row/column. Tango adds neighboring-cell signs:

```text
Family: tango
Size: 4
Givens:
. . . .
. . . .
. . . .
. . . .
Equal:
r1c1 r1c2
Different:
r2c2 r3c2
```

Sign cell pairs must be orthogonal neighbors. The unique-line encoding uses existing generic relations; larger examples benchmark its cost.

## Count and placement grids

### Tents and Trees

`Trees:` is an N×N grid of `.` and `T`. `RowCounts:` and `ColumnCounts:` each contain N non-negative counts, whose totals must equal the tree count. Every tree has exactly one orthogonally adjacent tent; tents are not on trees and may not touch each other, including diagonally. A tent is eligible only if it is orthogonally adjacent to exactly one tree, making tree pairing one-to-one.

### Minesweeper-style

`Clues:` is an N×N grid; `.` is a hidden cell and `0`–`8` is a safe numbered cell. The number counts mines in all in-bounds neighbors, including diagonals. Optional `TotalMines:` gives the total mine count.

### Light Up / Akari

`Family:` is `akari` or the alias `lightup`. `Grid:` uses `.` for floor, `W` for an unnumbered wall, and `0`–`4` for a numbered wall. Bulbs light every floor cell along its row/column until a wall; bulbs cannot see one another. Numbered walls count orthogonally adjacent bulbs.

### Kakurasu

`RowSums:` and `ColumnSums:` each contain N weighted totals. A filled cell in column c contributes c to its row sum; a filled cell in row r contributes r to its column sum. Optional `Givens:` uses `.`, `0`, and `1`. The current compiler expresses weighted line equations as generic relations; it does not add weighted propagation to `core.py`.

### Battleships, counts only

`RowCounts:` and `ColumnCounts:` each contain N occupied-cell counts; optional `Givens:` uses `.`, `0`, and `1`. This format intentionally models only row/column counts. It does not model ship shapes, fleet composition, adjacency rules, or connectivity, so it is not full Battleships.

## Murdoku

Murdoku uses named sections: `Size:`, `Regions:`, `Grid:`, and `People:` are required. Optional sections include `Rules:`, numbered `Clues:`, `AreaTags:`, `Objects:`, `EdgeItems:`, `PointObjects:`, `Marks:`, `Roles:`, `RoleEligibility:`, `Attributes:`, `Pronouns:`, `Hatched:`, and `Words:`. See [`examples/murdoku_composition.txt`](../examples/murdoku_composition.txt) for a neutral composition and the [`Murdoku authoring skill`](../.github/skills/murdoku-puzzle-generator/SKILL.md) for the complete clue vocabulary.

Every object footprint must be declared `blocking` or `standable`; its name/icon never determines occupancy. Doors list two side-sharing cells in different areas. Windows list one inside cell. Point objects sit on a grid point given as a half-step anchor such as `fountain: r2.5c2.5`: whole numbers are cell centres and `.5` values grid lines, with `0.5` and `N+0.5` the outer edges. An interior vertex touches four cells, a vertex on the outer edge or the middle of an inner cell side two, and a board corner or the middle of an outer cell side one. A cell centre or a point off the board is an error. See [`examples/murdoku_point_objects.txt`](../examples/murdoku_point_objects.txt). Marks overlap freely and do not occupy cells. Roles overlap unless explicitly constrained. Attributes are fixed person facts.

For ordinary objects, `next_to` means one orthogonal step (up, down, left, or right) within the same logical area; diagonal cells do not count. Door and point-object touched cells satisfy `next_to` across region boundaries. A window is a target for `at`, not `next_to`. `adjacent_regions` means two regions share a side.

### Booklet text (`--docx`)

In the booklet the clues of each person are folded into one paragraph ("Makaak is in de Bergen en zit niet naast de struik of de bank."), in the order of the people, with clues about no single person last; paragraphs are numbered, and the board sits beside the figure list (70/30). Board notes explain the marks and area tags used by the clues, and the attributes and roles are listed under the figures. `Words:` lines whose name is a phrase key (see `PHRASES` in `story.py`) reword that phrase for the puzzle, e.g. `target.attribute: a {name}` ("... and that is a friend"), or `role_has: {who} is een {role}` / `role_not: {who} is geen {role}` when roles are really kinds such as species. A `lint` warning flags a clue already implied by another (a person put in one region and also "not in" another).

`--docx [FILE]` writes one editable Word document: the puzzle page(s) first, then a solutions section with the solved board and worked solution of each. Optional sections (all ignored by solving, lint and PNG; `lint` only checks them for typos):

* `Title:`, `Intro:` (one paragraph per line, `**bold**` allowed), `Question:`, `Reveal:` (answer text, solution file only).
* A clue line may end in `| wording` (e.g. `above Otto Tjitske 1 | Otto zit precies één rij boven Tjitske.`); that text replaces the generated sentence and the solver ignores it. Without it every clue is worded by `story` (en/nl), e.g. `at_least Ramen Tempura 5` → "Ramen is at least five squares from Tempura."
* `Figures:` lines `Name: description [; image=path] [; icon=name]`. A figure gets a small thumbnail from, in order: the `image=` file (relative to the puzzle file); a file named after the person (`Name.png`/`.jpg`) in `<puzzle>-figures/` or `figures/` beside the puzzle; or the built-in emoji `icon=` (a catalogue name or `U+1F35C` whose picture is vendored in `src/csp/assets/emoji/`; `--lint` warns otherwise). Without any of these it is text only. Put licensed artwork in the figures folder; the only bundled third-party images are the vendored Noto Emoji (see `src/csp/assets/NOTICE.md`).

Pass a glob (quoted) such as `"examples/prrrdoku*.txt"` to put every matching Murdoku puzzle in one booklet (`booklet.docx` beside the pattern by default), each on its own page, ordered alphabetically by file name, after a clickable table of contents.

Puzzles of other families (sudoku, queens, tents, …) are included generically: title (`Title:` or the file name), a one-line rule for the family, the board, and on a separate solution page the solved board with the solver's placement steps. A mixed glob such as `"examples/*.txt"` therefore works.

Needs `uv sync --extra docx` (python-docx, plus fonttools and resvg for the pictures).

In the Murdoku picture, blocked squares are shaded clearly darker than their region (standable objects keep the region colour), and area tags (for example `noble_areas`) are named in the legend.

## Other existing formats

- **Calcudoku:** `Size:`, `Grid:` cage IDs, and `Cages:` arithmetic targets/operators. Cages must be connected; subtraction and division are two-cell cages.
- **Futoshiki:** `Grid:` givens/dots plus `Signs:` lines such as `r1c4 < r2c4`; signs join orthogonally adjacent cells.
- **Sudoku:** see the earlier section. Plain format is a grid; variants use sectioned `Givens:`, `Boxes:`, and `Extra:`.

## CLI and validation

The type is detected from the file's sections; `--type` overrides it. `--show-model`, `--verbose`, `--step`, `--grade`, `--brute-force`, `--svg`, and `--png` use the same generic engine for every family. `--explain`, `--track-person`, `--lint`, and `--require-forward` are Murdoku-specific; other families have no clue narrative unless documented by that module.

```bash
uv run csp examples/<family-example>.txt --show-model
uv run csp examples/<family-example>.txt --brute-force
uv run csp examples/<family-example>.txt --grade
uv run csp examples/<family-example>.txt --svg board.svg
uv run csp examples/<family-example>.txt --png board.png
```

For a new family, add a parser/compiler, an independent backtracker in `src/csp/bruteforce/`, CLI and kind registration, a renderer (pieces as `icons.REGISTRY` entries) and picture test, small and larger unique examples, example soundness coverage, README/AGENT/skill documentation, and a line in the module-layer test. Use existing generic primitives; a new engine constraint requires a separate design issue.

## Source layout

```text
src/csp/
	core.py        generic literals, constraints, relations, rules, and solver
	puzzlefile.py  section reader and automatic family detection
	regiongrid.py  shared named-region grid reader
	<family>.py    one parser/compiler/text renderer per family
	bruteforce/    independent search implementation per family
	svg.py         SVG canvas, text as paths, PNG rasterising (resvg)
	icons.py       icon registry, Murdoku object catalogue, Unicode fallbacks
	picture.py     SVG pictures for every family
	assets/        vendored Noto Emoji SVGs and Noto Sans subset (NOTICE.md)
	docx_export.py Word booklet pages for Murdoku (optional python-docx)
	cli.py         family dispatch and shared solver options
tests/           engine, family, soundness, layering, and picture tests
examples/        small and larger unique examples for each family
benchmark/       seeded Sudoku and cross-family benchmark programs
```

The project verification commands are:

```bash
uv run pytest -q
uvx ruff check src tests benchmark
uvx ruff format --check src tests benchmark
uv run mypy src
```

Continuous integration runs the same gates on Python 3.12 and 3.13. The tests check brute-force uniqueness for every example, engine agreement, and every logged placement/elimination against the independent solution. The exception is a documented unsupported narrative, such as non-Murdoku `--explain`, not solver correctness.

Pictures have one renderer: `picture.py` draws every family on an `svg.Canvas`, and every other format derives from it. `--svg [FILE]` writes it (needs `uv sync --extra svg` for fonttools, which turns text into paths from the bundled Noto Sans subset, so output does not depend on installed fonts); `--png [FILE]` rasterises it with resvg (`uv sync --extra png`, no system libraries); `--docx` embeds the PNG. Each has three variants: blank, solution (the `-solution` file), and with `--svg --interactive` the blank board with a transparent `<rect id="r<row>c<col>" class="cell">` over every cell (r1c1 top left) for an app to fill in.

Pieces come from the icon registry in `icons.py`: each `Icon` has a name, a Unicode `symbol` used by the text boards (★ star, ▲ tent, ♣ tree, ✱ mine, ● bulb, ■ wall/shaded, ●/○ Binairo) and either an original vector shape or a vendored Noto Emoji. Murdoku objects and figure `icon=` names are looked up in `icons.CATALOGUE` (Dutch names plus English synonyms, or `U+<code>`); unknown or unvendored icons fall back to a text label and `--lint` warns. All artwork is vendored under `src/csp/assets/` at pinned commits with its licences (`NOTICE.md`); rendering never uses the network. To add a picture, add the name to `CATALOGUE` and run `uv run python scripts/vendor_emoji.py U+<code>`; `scripts/subset_font.py` rebuilds the font subset.

## Further engine work

Some proposed families remain conditional on generic-core design work. Weighted sums may need a generic primitive if relations are not practical; this is tracked separately from Kakurasu. Reusing chain links could improve large-board performance but is an optimization, not a prerequisite for families expressed by existing primitives. Connectivity, path, and run-length puzzles need separate designs for generic constraints.

Other solver/documentation roadmap items are tracked as [DOCX generation #28](https://github.com/operdeck/human-reasoning-puzzles/issues/28), [weighted-sum support #46](https://github.com/operdeck/human-reasoning-puzzles/issues/46), [chain-link reuse #47](https://github.com/operdeck/human-reasoning-puzzles/issues/47), [large Calcudoku cages #50](https://github.com/operdeck/human-reasoning-puzzles/issues/50), [higher-arity weak links #51](https://github.com/operdeck/human-reasoning-puzzles/issues/51), [advanced covers #52](https://github.com/operdeck/human-reasoning-puzzles/issues/52), and [hybrid search #53](https://github.com/operdeck/human-reasoning-puzzles/issues/53). Plain-language clue interpretation remains an authoring-assistant task; the solver does not parse natural-language clues.
