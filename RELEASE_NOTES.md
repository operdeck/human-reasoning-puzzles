# Release Notes

## Unreleased
**Licensing**
* The puzzles in `examples/` are all rights reserved (`examples/LICENSE.md`): no copying without the author's written permission. The rest of the repo stays Apache 2.0. Every `--docx` booklet carries this notice in its footer.
**Bug Fix(es)**
* `--png` on a Murdoku puzzle with roles (e.g. `murdoku_composition.txt`) no longer crashes with `AttributeError: 'bool' object has no attribute 'col'`.
* Name-vs-appearance consistency
    * `examples/murdoku_sparse_mystery.txt`: "Blue hall" is now blue instead of grey; all other examples audited, no other mismatches.
    * Added a test that colour words in region names match their background colour, plus guidance in the Murdoku skill and `AGENT.md`.
* Murdoku PNG: the English `carpet` (and `rug`) object now draws the hand-made rug icon instead of the literal word, as `tapijt` already did.
    * `src/csp/icons.py`: added the `oven` icon, which `murdoku_house.txt` lacked.
    * `src/csp/picture.py`: shared `CARPET_NAMES`/`WELL_NAMES` drive both drawing and the missing-icon check; `tests/test_picture.py` checks every object in the Murdoku examples has an icon.
* [#26 Handle empty domains in --show-model](https://github.com/operdeck/human-reasoning-puzzles/issues/26)
    * `src/csp/report.py`: `--show-model` no longer crashes with `IndexError` when contradictory clues empty a variable's domain; it reports an "Invalid model: contradiction" section listing the affected variables.

**New Feature(s)**
* [#83 Murdoku: objects on any grid point](https://github.com/operdeck/human-reasoning-puzzles/issues/83)
    * `CornerObjects:` is renamed `PointObjects:` (no alias; the old name gives an error) and takes a half-step anchor instead of four cells: `fountain: r2.5c2.5`. Point objects may sit on an interior vertex (4 cells), a vertex on the outer edge or the middle of an inner cell side (2 cells), or a board corner or the middle of an outer cell side (1 cell). Any touched cell counts for `next_to`, across area boundaries. The typed selector is now `point_object:name`.
    * Pictures centre the small icon on the point and widen the margin when a point lies on the outer edge, so it is not clipped or drawn over the coordinates; an object without an icon gets a small labelled badge. New `mouse`/`muis` and `cheese`/`kaas` icons.
    * `examples/murdoku_composition.txt` migrated; new example `examples/murdoku_point_objects.txt` (unique, grade `single`).
    * Three Dutch menu puzzles `examples/menu-murdoku-1/2/3.txt` (grades `relations`, `subsumption`, `what_if`): foods on days of the week, sunflowers and ornamental onions on grid points, one starch per day, and the vla is found last.
    * `alone_with <person> [selector] [n]`: the selector is now optional (anyone) and `n` sets how many companions (default 1), e.g. `alone_with Vla 2`.
    * New hand-drawn `sierui`/`allium` icon (purple ornamental onion) and flower/food emoji (zonnebloem, roos, madeliefje, hibiscus, aardappel, rijst, pasta, broccoli, spinazie, wortel, vis, kip, bonen, vla).
    * `--explain` no longer crashes with `KeyError` on a step from a `different_regions` role ("er is hoogstens één zetmeel per gebied").
    * The picture legend follows the puzzle's `Language:` (`Punt`, `Deur`, `Raam`, ...). Role lines are readable: a role whose candidates must all hold it is shown as a category ("Zetmeel: Aardappel, Rijst, Pasta, Noedels (niet meer dan 1 hiervan per gebied)"); otherwise the holders, then "maybe" for the open candidates. Point icons are a third larger.
* [#75 Better icons for the puzzles](https://github.com/operdeck/human-reasoning-puzzles/issues/75)
    * One renderer: `picture.py` now draws every family as SVG (`src/csp/svg.py`); `--png`, the README images and `--docx` booklets are rasterised from it with resvg. New `--svg [FILE]` writes the SVG (blank and `-solution`), and `--svg --interactive` writes the blank board with a transparent `r<row>c<col>` element per cell for an app.
    * Icon registry (`src/csp/icons.py`): stars, tents, trees, mines, bulbs, walls, discs, signs and DogDoku pieces each have a picture and a Unicode fallback used by the text boards (★ ▲ ♣ ✱ ● ■ ○). Calcudoku prints − × ÷.
    * Icons and font are vendored under `src/csp/assets/` (Noto Emoji SVGs and a Noto Sans subset at pinned commits, licences in `NOTICE.md`); rendering never uses the network and text is drawn as paths, so output does not depend on installed fonts. `scripts/vendor_emoji.py` and `scripts/subset_font.py` rebuild them.
    * Extras: `svg` (fonttools), `png` (+ resvg-py, no system libraries; Pillow no longer needed), `docx` (+ python-docx). Without them `--svg`/`--png`/`--docx` print which extra to install.
    * Murdoku: blocked squares are now shown by a clearly darker shade of their region instead of a red cross.
    * `--lint` also warns when a figure `icon=` is a valid code point whose picture is not vendored; tests check every object and figure in `examples/` has a vendored icon and every character in the example pictures is in the bundled font. The Murdoku skill and `AGENT.md` describe how to add icons for new objects and families.
* Star Battle examples now have irregular regions and two or three stars: `starbattle_8x8.txt` and `starbattle_10x10.txt` (two stars) and `starbattle_12x12.txt` (three stars), unique and graded `cover2`, `chains` and `cover3`. They replace `starbattle_4x4.txt` (one star, which is just a Queens puzzle) and the old row-region 8 × 8.
    * Star Battle regions may now have any size from `Stars:` cells up, as long as each is connected (it used to require exactly N cells each).
* DogDoku ([#71](https://github.com/operdeck/human-reasoning-puzzles/issues/71)): `Family: dogdoku` (a Queens puzzle with dogs) and an optional `Icon:` section (`queen`, `dog`, `puppy`) for Queens files, drawn in `--png` and shown in the text board. Dog puzzles colour every zone differently.
    * Queens zones may now have any size from one cell up, as long as each is connected (it used to require exactly N cells each).
    * New examples `dogdoku_5x5.txt`, `dogdoku_7x7.txt`, `dogdoku_9x9.txt`: unique, built backwards from a solving order, and solvable by eliminations only; grades `single`, `subsumption`, `cover2`.
* Booklets list the puzzles alphabetically by file name and, with more than one puzzle, start with a clickable table of contents (page numbers fill in when Word opens it).
* Murdoku PNG: blocked squares are marked so blocking and standable objects are told apart (now a darker shade, see #75).
* Booklet lists attributes and roles beside the board; area tags (e.g. "noble areas") are now named in the PNG legend and the booklet rules.
* Clues thinned in zoo, food-2 and tamagotchi puzzles and sudoku givens in the anti/relations examples (still unique); clearer wording for `furthest`/`alone`; thermometers and mark legends render cleanly; booklet layout follows the Prrrdoku style.
* [#28 Create docx from puzzle description](https://github.com/operdeck/human-reasoning-puzzles/issues/28)
    * `--docx [FILE]` writes one editable Word booklet (per puzzle: title, board picture, figures, numbered human-readable clues, question), followed by the solved boards and worked solutions. Optional extra: `uv sync --extra docx`.
    * Every other puzzle family (sudoku, queens, tents, …) works too: a page with a one-line rule, the board, and the solved board on a separate page; no per-family processing.
    * Booklet boards omit the solver's role/count legend lines and shrink for long clue lists so each puzzle fits one page; `--png` count lines are now readable.
    * Booklet clues are grouped per person in one unnumbered paragraph; "exactly one of" alternatives read as "X is in the same region as either Y or Z" or "either …, or …, but not both"; the alone-with clue and role phrases can be reworded in `Words:` (`target.attribute`, `role_has`, `role_not`); fixed "only in in"; `lint` warns about implied clues, and a role only one person can hold now draws a lint warning (the zoo puzzles use `alone Tijger` instead of a tiger role); the redundant "Makaak is not in the desert" clue was removed from `zoo-murdoku-1`.
    * `--docx` also accepts a quoted glob (e.g. `"examples/prrrdoku*.txt"`) to build one multi-puzzle booklet.
    * New optional puzzle-file sections `Title:`, `Intro:`, `Question:`, `Figures:` (with optional `image=`) and `Reveal:`, plus an optional `| wording` after a clue in `Clues:`; they never affect solving, lint or PNG. Added to the prrrdoku and Tamagotchi examples.
* Tamagotchi Murdoku puzzles now use Japanese objects (shrine, castle, Mount Fuji, sakura, lanterns, taiko, tatami, ...); new icons added to `src/csp/icons.py`, `tatami` draws the rug icon.
* New Murdoku example puzzles
    * `examples/food-murdoku-1.txt`, `-2.txt`, `-3.txt`: Japanese food and cities (5x5 to 7x7).
    * `examples/tamagotchi-murdoku-6x6.txt`, `-9x9.txt` (stream and bridge), `-12x12.txt`: "where is the devil?" late-reveal puzzles; new `bridge` icon.
    * `tests/test_picture.py`: the icon check covers every example with a `People:` section.
* [#12 Murdoku: Migrate the format and verify feature composition](https://github.com/operdeck/human-reasoning-puzzles/issues/12)
    * `src/csp`: Added Murdoku lint and forward-only checks, optional default PNG paths, and 16x16 count/chain benchmark coverage.
    * Added a neutral combined-format example with brute-force uniqueness and per-step soundness coverage.

## 0.4.0
**New Feature(s)**
* [#19 Murdoku: Global clues](https://github.com/operdeck/human-reasoning-puzzles/issues/19)
    * `src/csp`: Added whole-board counts over people, roles, attributes, object/area/cell sets, empty areas, and empty cells using the generic `COUNT` primitive; integrated count explanations, step status, PNG scopes, brute-force checks, and size benchmarks.
    * Example: `count empty areas in tag:inside = 1` requires exactly one logical region in the tagged set to be unoccupied.

## 0.3.0
**New Feature(s)**
* [#11 Murdoku: Add person attributes and quantified clue targets](https://github.com/operdeck/human-reasoning-puzzles/issues/11)
    * `src/csp`: Added fixed person attributes and pronoun forms, typed targets, bounded quantified clues, new row/column/area-corner and region-adjacency predicates, bilingual explanations, and brute-force verification.
    * Example: `unique_attribute engineer Ada Ben Cal` requires exactly one selected person to have the engineer attribute.

## 0.2.0
**New Feature(s)**
* [#10 Murdoku: Add generic roles and role constraints](https://github.com/operdeck/human-reasoning-puzzles/issues/10)
    * `src/csp`: Added data-driven role membership, cardinality, eligibility, area policies, object/mark bindings, role relationships, occupant effects, independent brute-force verification, and role output in text, story, PNG, and model reports.
    * Example: `Roles: engineer: 2` requires exactly two people to have the engineer role; roles can overlap unless constrained.
* [#9 Murdoku: Add optional cell marks and occupant conditions](https://github.com/operdeck/human-reasoning-puzzles/issues/9)
    * `src/csp`: Added overlapping named cell sets and conditional `alone`/`not_alone` area occupancy rules, such as `quiet: r2c3 ; alone`.
    * Example: `quiet: r2c3 ; alone` applies only when someone occupies r2c3.
* [#8 Murdoku: Add general counting constraints to the core](https://github.com/operdeck/human-reasoning-puzzles/issues/8)
    * `src/csp/core.py`: Added allowed-count constraints and reified counts for exact, ranged, and other count-based rules.
    * Example: `exactly 2 in_region Ada kitchen ; in_region Ben kitchen ; in_region Cal kitchen` requires exactly two of those clues to hold.
* [#7 Murdoku: Model edge items and corner-anchored objects](https://github.com/operdeck/human-reasoning-puzzles/issues/7)
    * `src/csp`: Added doors, windows, and corner objects as touched-cell sets, enabling clues to refer to boundaries without occupying cells.
    * Example: `gate: door r2c3 r2c4` lets `at Ada gate` match either cell touched by the door.
* [#6 Murdoku: Add tagged and overlay-area semantics](https://github.com/operdeck/human-reasoning-puzzles/issues/6)
    * `src/csp`: Added reusable area tags that can overlap or span disconnected regions for location clues and area policies.
    * Example: `inside: kitchen hall` lets `in_tagged Ada inside` target either region.
* [#5 Murdoku: Declare object kinds and footprints explicitly](https://github.com/operdeck/human-reasoning-puzzles/issues/5)
    * `src/csp`: Required each object footprint to declare `blocking` or `standable` and validated connected, non-overlapping cells.
    * Example: `wall: blocking r1c1` and `bench: standable r2c2 r2c3` distinguish an obstacle from a surface people can occupy.
