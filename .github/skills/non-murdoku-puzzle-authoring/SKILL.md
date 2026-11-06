---
name: non-murdoku-puzzle-authoring
description: "Create, rate, and find original non-Murdoku puzzles with repository-native tools. Use for example generation, tiered puzzle sets, puzzle quality review, or non-Murdoku authoring."
argument-hint: "Specify puzzle family, easy/medium/hard target, constraints, theme, or seed example"
---

# Non-Murdoku Puzzle Authoring

Use the repository's puzzle tools to create and check examples. Do not design
or rate a puzzle from agent reasoning alone. This skill covers every supported
family except Murdoku; Murdoku keeps its own skill and tools.

## Workflow

1. Read `docs/model-and-puzzle-formats.md` for the exact family syntax and
   `docs/puzzle-collection.md` for grading notes and the
   [web index](https://operdeck.github.io/human-reasoning-puzzles/) for the
   existing visual collection. Preserve displayed aliases:
   Binairo and Tango retain separate names because Tango adds relation signs.
   Queens is the one-star presentation of canonical `Family: starbattle`.
   New one-star files use `Stars: 1`; keep `queens_*` filenames and the
   separate Queens display group, queen icon, and Queens rule wording.
   `Family: queens` remains a compatibility alias. Presentation must match
   the star count.
   `tests/test_example_quality.py` enforces this.
2. Use an existing original example as a seed, or create an original seed in
   the family format. Never transcribe published puzzles unless the user has
   permission and explicitly asks for transcription.
3. Generate a candidate with a fixed seed so it can be reproduced. For a new
   example, prefer `puzzle-lab fresh`: it builds a brand-new solution and
   layout (Binairo, Tango, Suguru, Minesweeper, Akari, Sudoku, Futoshiki,
   Calcudoku, Star Battle, Tents, Battleships, Towers, Mosaic, Dominosa,
   Rectangles, Magnets, Undead, Pattern, Map), so the example does not share
   a solution with the rest of the gallery. Before choosing seeds, ask
   `puzzle-lab sweep` what a builder reaches: it rates one fresh board per seed
   and counts the tiers and grades, and `--save DIR` keeps each board named by
   size, tier, grade and seed, so the pick is made from measured boards:

   ```bash
   uv run puzzle-lab sweep towers --size 5 --open-share 0.3 --seed 1100 --count 15 \
     --save /tmp/towers
   ```

   ```bash
   uv run puzzle-lab fresh tango --size 8 --tier medium --open-share 0.6 \
     --seed 26 --output /tmp/candidate.txt --comment "Tango 8x8: medium, ..."
   uv run puzzle-lab fresh akari --size 6 --tier medium \
     --seed 122 --output /tmp/akari.txt --comment "Akari 6x6: medium, ..."
   uv run puzzle-lab fresh starbattle --size 7 --stars 1 --tier easy \
     --seed 13804 --output /tmp/queens.txt --comment "Queens 7x7: easy, ..."
   uv run puzzle-lab fresh battleships --size 6 --tier medium \
     --seed 136 --output /tmp/fleet.txt --comment "Original Battleships fleet"
   ```

   `--open-share` sets the share of empty Binairo/Tango cells; more open
   cells usually means harder. For Minesweeper, it sets the share of unknown
   cells, including mines, on the fresh board. Star Battle grows connected
   regions around its solution; `--stars 1` makes a Queens board, with one
   explicit starter on easy boards.
   Suguru drops givens while the solution stays unique. Akari builds a fresh wall layout and
   derives numbered-wall clues from a valid bulb placement. Sudoku and
   Futoshiki start from a random Latin square and use `--open-share` for the
   share of empty cells; Futoshiki also drops redundant signs. Calcudoku cuts a
   random square into cages, Star Battle grows random regions (adding `Givens`
   only when needed for uniqueness), and Tents places random tent/tree pairs;
   all three retry until the board has one solution. Large Suguru boards can
   take many minutes.
   Battleships supports 4x4, 6x6, 8x8 and 10x10: it places a fresh non-touching
   fleet, derives line totals and removes shaped givens while independent
   connected-component search still finds exactly one solution.
   The newer builders share one pattern: pick a random solution (a Latin square,
   a domino tiling, a colouring), state every clue, then drop clues or givens in
   random order while `fresh.is_unique` holds (`fresh.thin`). `--open-share`
   then sets the floor of clues kept (Towers, Magnets and Undead keep
   `1 - open_share` of the border clues, Mosaic of the cells, Map of the
   regions), and a harder board comes from a lower floor. Dominosa and Pattern have
   no clues to drop: they redraw random boards until one is unique. Rectangles
   moves each number about inside its piece to leave more candidate rectangles.
   Towers stays at 6x6 or smaller, Pattern at 15 cells a line and Magnets at an
   even side, because relation-checked lines cost time exponential in length.
   `puzzle-lab generate` only re-masks or mutates a seed and keeps its
   solution, so use it for variations, never to fill a gallery tier with
   copies of one board. Use `--as-family` only for compatible aliases. Do not
   use it to disguise a puzzle from another rule family.
4. Rate before adding or describing a candidate:

   ```bash
   uv run puzzle-lab rate /tmp/candidate.txt --json
   ```

   Only unique, deductively solved, nontrivial candidates qualify. Preserve the
   reported family, grade, tier, and uniqueness status; never promote an
   unrated or invalid candidate by hand.
   When preserving technique coverage, pass optional `--grade` to `fresh`
   or `generate` as well as `--tier`, for example `--tier hard --grade cover3`.
   A tier alone cannot distinguish the different hard deduction rules.
5. Search the gallery to find coverage gaps and verify a new file is indexed
   under the intended display family:

   ```bash
   uv run puzzle-lab search examples --family tango --tier hard --json
   ```

6. Place approved original examples under `examples/` as
   `<family>_<n>_<size>[_<variant>].txt`, where `n` is the board's place in its
   gallery section from easiest to hardest (for example `sudoku_16_4x4_kropki_consecutive_thermometers`).
   Leave tier words such as `easy` or `hard` out of the name: the number carries
   the order and `docs/puzzle-collection.md` shows the tier. When a new board lands in
   the middle, renumber the later files (with their `docs/images` pictures) and
   update every reference. Give each a short comment, and update the tier table
   in `docs/puzzle-collection.md`.
   Re-export the web collection and check its puzzle links and group preview.
   The index shows one representative unsolved `static` SVG per `section`,
   alongside one or two compact link columns, not an image per puzzle.
   It shares the booklet's numbering and sections (including separate Binairo
   and Tango groups), not a separate manual gallery.
   Then audit the whole collection:

   ```bash
   uv run puzzle-lab audit examples
   ```

   It fails when two examples share a solution or a layout (compared up to
   rotation, reflection and renamed regions; for Queens, Star Battle and
   Murdoku a solution counts together with its region map), or when a gallery
   section is not listed from easier to harder (tier, then grade). Fix a
   collision with `puzzle-lab fresh` or a new seed, never by turning or
   relabelling a copy. Give every new example its own seed: the same family,
   size and seed rebuild the same solution, and older generators used the same
   random grids, so a common seed such as 1 can recreate an existing example.
   `tests/test_example_quality.py` fails on any shared solution or layout.
   Run the repository example tests after adding files.
7. If the generator cannot find a candidate in its attempt budget, report that
   honestly. Improve the family-specific generator or choose another seed;
   do not loosen uniqueness checks, relabel a trivial puzzle, or fall back to
   brute-force-only solving.

## Difficulty and validation

Calcudoku cages must contain at least two cells in published examples and
fresh or seed-based authoring. Excluding size one from the requested cage
sizes is insufficient: growth can still strand a single cell. Merge each
singleton into a touching cage and rederive that cage's target and operation
from the solution; keep unaffected clues valid. Never generate easier
variants by splitting cages into one-cell hints. The shared builder handles
both fresh layouts and seed variations, with deterministic seeds and
connectivity/solution checks.

Keep valid legacy singleton syntax readable. Compiler-fixed values are not
necessarily authored givens: Calcudoku targets are arithmetic clues, and the
web player should let the user enter their digits. Test that every playable
cell is editable or visibly prefilled, and that Check requires editable clue
cells before reporting solved. Keep this policy in the exporter, not as
family-specific UI code. Rework affected examples without losing measured
technique coverage, audit uniqueness/order, and refresh puzzle and solution
images as well as web/booklet exports.

When a puzzle has a global total that local clues cannot determine (for example,
a total mine count), disclose it in the shared player-facing rules and every
relevant output, including web bundles and booklets. Test both languages and
the behavior when the optional total is absent; do not make a correct placement
look unexplained because a required global constraint is hidden.

One-star Queens regions must contain at least two cells in published examples
and freshly authored boards. Single-cell regions give away a placement,
regardless of the puzzle's final grade. The shared Star Battle builder first
gives each region a neighbour, then grows the rest, and rejects any remaining
singleton. Easy one-star boards use one explicit starter queen instead. When expanding an
existing singleton, recheck the donor region's connectivity and uniqueness:
expansion adds alternative placements, so a visible given may be necessary.
Re-rate the result, audit it against the rest of the gallery and regenerate
both puzzle and solution pictures. Do not ban valid singleton syntax from
the parser: this is an authoring-quality rule.
When tests mutate a gallery seed, assert that the text actually changes;
regenerated layouts can turn literal replacements into silent no-ops.

When consolidating overlapping puzzle families, compare actual rules, sizes,
region layouts and measured deductions, not just names or icons. Share one
parser, solver and fresh generator when the rules are identical, while keeping
distinct display names, icons and collection sections when they help players.
For Queens and Star Battle, `Stars: 1` is Queens; higher counts are Star Battle.
Keep technique coverage rather than near-duplicate boards at the same size,
renumber by measured difficulty, and regenerate pictures with the canonical
piece. Update every collection, booklet, web, benchmark and documentation
reference together. Presentation must not change family identity, solver
semantics or region colouring. Recheck comments against current grades instead
of carrying old difficulty claims forward.

For Battleships examples, use a real `Fleet:` and explain its composition,
straight ships, no-touching (including diagonals), line totals, and shaped
givens in the shared web/booklet rules. Keep counts-only compatibility explicit;
never present it as full Battleships. Reject full staircase totals, and verify
that removing the fleet permits other answers, so the genre's rules really
matter. Do not permute independent rows/columns when mutating a fleet board:
that bends ships and changes their adjacency. Use the fleet-aware builder.
Hidden ship-position variables are compiler auxiliaries, not playable cells.
Validate ship shapes with independent component search, not the same placement
enumeration used by the compiler.

Do not let clue thinning erase the visual vocabulary promised by the rules.
For symbol-rich Battleships examples, retain explicit water (`0`, drawn as
waves), unspecified occupied cells (`1`, drawn as `?`), singles (`O`), ends
(`N/S/E/W`), and middles (`M`). Choose water outside zero-total lines so it
is not merely decorative. Add only solution-consistent clues to an original
fresh board, then re-rate: added givens can reduce its grade. Keep at least
three quarters of the playable grid unknown, preserve independent uniqueness,
verify fleet rules still matter, and avoid `what_if` for ordinary hard boards.
Inspect the unsolved web and booklet diagrams, not just solved pictures;
test the actual exported water/ship givens and rendered symbols.

For Sudoku variants, name every active variant in the file name and `Title:`.
Check both web and booklet rules against the parsed constraints, including extra
houses and combined variants. Never assume a player's familiarity with the
symbols: explain the dot colors, consecutive bars, thermometer direction, and
whether unmarked pairs carry restrictions. These explanations come from shared
rendering code, not copied puzzle introductions.
Keep the web player family-agnostic: export localized explanations with semantic
peer groups rather than reimplementing chess moves or other puzzle rules in UI
code. Conflict feedback must use visible givens and placements, not the solution.
Give automatic conflict feedback its own player toggle, enabled by default and
saved with progress independently of auto-mark; players can choose less help.

`puzzle-lab rate` reports the hardest solver rule used and a tier derived from
that rule, with limited family-aware calibration for small relational and
count-only puzzles. These are repository-specific estimates, not universal
human difficulty ratings. It also reports `deductive`: `false` means the ladder
closes the puzzle only with `what_if`, so no deduction path exists. Read that
field rather than parsing the grade, and use
`puzzle-lab search --tier hard --deductive` to list the hard puzzles that need
no fallback. Reserve `what_if`, the final fallback rule, for only
the very hardest puzzles; ordinary hard examples should be solved by the other
deduction rules. A tier is not enough by itself: inspect the actual deductions
and puzzle presentation, confirm that the puzzle is not simply prefilled, and
report any limitation of the solver's grading ladder. A board with under a
quarter of its cells open (`PREFILLED_OPEN_SHARE`) rates `trivial`, whatever
rule its last cells need. `tests/test_example_quality.py` rejects trivial or
non-unique gallery examples. Known exceptions there must link to an open issue.

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

## Feeding lessons back

When authoring uncovers a general pitfall or a missing capability, improve the
repository tool (`puzzle-lab`, a family generator, the renderer) with a test
and record the lesson in this skill in the same PR, rather than solving it
ad hoc for one puzzle. Order puzzles within a series or tier table by measured
difficulty, never reuse a board layout or solution across examples, and
reject candidates that are fully or almost fully prefilled. Keep account
names, tokens and other machine-local setup out of the repository.

For Murdoku, stop here and use `.github/skills/murdoku-puzzle-generator/` and
its own workflow. Do not change Murdoku examples, skills, tools, or behavior
while authoring non-Murdoku puzzles.
