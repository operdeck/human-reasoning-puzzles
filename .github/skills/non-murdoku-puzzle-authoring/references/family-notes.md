Read this when generating or reviewing a board from the newer families.

## Bridges

`fresh bridges` grows a connected network with one or two non-crossing bridges
per neighbouring island pair, derives the island numbers, and checks uniqueness
independently. `--open-share` controls extra network links, not clue removal.
Use sweeps to select a range of techniques, with distinct island layouts and
seeds. Local counts, `cut`, patterns, chains and `closure` can all be reached
without the `what_if` fallback.

Two counted Boolean units represent a pair's multiplicity. State their ordering
explicitly: a second bridge requires a first. A neighbour numbered one cannot
take a double bridge. These generic count and exclusion constraints expose
obvious deductions without introducing weighted or puzzle-specific core rules.
The connected graph uses only the first unit; loops are allowed.

## Towers, Mosaic, Dominosa, Rectangles, Magnets, Undead, Pattern and Map

These eight families share one authoring loop, and its lessons apply to any new
family:

1. Run `puzzle-lab sweep FAMILY --size N --open-share X --seed S --count K --save DIR`
   for a few sizes and floors. The summary line is the honest answer to "which
   tiers can this builder reach?"; pick examples from the saved files, whose
   names carry size, tier, grade and seed, then copy them into `examples/` as
   `<family>_<n>_<rows>x<cols>.txt` with a one-line comment that matches the
   grade you measured.
2. If the sweeps never reach a tier, first ask whether the ladder can: a grade
   needs a rule with something to combine (Map's pairwise `AT_MOST_ONE` rules
   give `subsumption` and `cover2` nothing, so it has no medium rung). If it can,
   add a difficulty search to `csp.climb` instead of picking seeds by hand: it
   mutates a unique board (`climb.rectangles` moves numbers, merges and splits
   pieces) and keeps only unique, ladder-solved boards until the grade lands in
   the tier; `puzzle-lab fresh ... --tier hard` and `sweep --tier hard` call it.
   If it cannot, the tier stays an em dash in `docs/puzzle-collection.md` with the
   reason. Do not hand-edit a board, and do not relabel a neighbouring tier.
3. A hard board that only `what_if` closes is allowed, but it joins the
   beyond-deduction frontier: add it to `BEYOND_DEDUCTION` in `tests/test_web.py`
   and update both numbers of the "N of the M published" sentences in
   `docs/puzzle-collection.md` and `RELEASE_NOTES.md`
   (`test_the_documented_example_count_matches_the_collection` checks them).
4. Relation-only families (Towers, Magnets, Undead, Pattern, like Kakurasu and
   Tango) rate `relations` whatever their size, so `puzzle-lab` calls a board
   with 16 or fewer variables easy and the bigger ones medium. Their hard tier
   needs `chains`, `cover3` or `what_if`, which only a few of the sweeps reach.
5. Compile pitfalls: assign givens after every constraint exists (see
   `AGENT.md`), keep an auxiliary relation's variables distinct (a Undead sight
   line may cross a cell twice, so its relation lists each cell once and keeps
   the visits separately), and cap relation arity (Towers lines of 7 and Pattern
   lines of 15 are the practical limits).
6. Visual pitfalls: draw the number a player must read on a tile they can
   cover inside `canvas.above()`; give each family cell-level palette items
   (`web.ITEMS`, or `CELL_SOLUTIONS` plus `svg.swatch` when the solver's
   variables are not cells); and use `--png` on one board per family for the
   README. Preview the web player (`web/`, `npm run dev` with exported bundles
   in `web/public/puzzles`, which is not committed) and look at the palette, a
   placed tile and the clue labels before calling the UI done.
7. Families that are a variant of an existing one (the Sudoku variants) are
   `Family:` aliases of the base kind with their own label, so the collection
   gets a section per variant and nothing is renumbered. Add a family to
   `puzzle_lab.SMALL_RELATION_FAMILIES` when all its clues are relations, so a
   board of at most 16 variables rates easy rather than medium. Pick examples
   with different seeds per family; with very small boards the audit still finds
   shared solutions (only 288 4 × 4 Sudoku grids), and the fix is another
   candidate from the same `sweep --save` folder.
8. When a family cannot reach a tier on this engine (Kakuro has no hard board,
   Map no medium one, Sandwich and Skyscraper Sudoku stop at 6 × 6), say so in
   `docs/puzzle-collection.md` with the reason and link the issue that would
   change it (`#46`, `#50`, `#178`), instead of shipping a board of another tier.
