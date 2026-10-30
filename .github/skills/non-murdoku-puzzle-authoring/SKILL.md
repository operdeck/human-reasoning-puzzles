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
   Cosmetic changes alone never create a family: Queens remains
   `Family: queens` even with a custom piece. Published `queens_*` examples
   use queens; the file name, family, comment and pieces must agree.
   `tests/test_example_quality.py` enforces this.
2. Use an existing original example as a seed, or create an original seed in
   the family format. Never transcribe published puzzles unless the user has
   permission and explicitly asks for transcription.
3. Generate a candidate with a fixed seed so it can be reproduced. For a new
   example, prefer `puzzle-lab fresh`: it builds a brand-new solution and
   layout (Binairo, Tango, Queens, Suguru, Minesweeper, Akari, Sudoku,
   Futoshiki, Calcudoku, Star Battle, Tents, Battleships), so the example does not share a solution with the rest of the gallery:

   ```bash
   uv run puzzle-lab fresh tango --size 8 --tier medium --open-share 0.6 \
     --seed 26 --output /tmp/candidate.txt --comment "Tango 8x8: medium, ..."
   uv run puzzle-lab fresh akari --size 6 --tier medium \
     --seed 122 --output /tmp/akari.txt --comment "Akari 6x6: medium, ..."
   uv run puzzle-lab fresh battleships --size 6 --tier medium \
     --seed 136 --output /tmp/fleet.txt --comment "Original Battleships fleet"
   ```

   `--open-share` sets the share of empty Binairo/Tango cells; more open
   cells usually means harder. For Minesweeper, it sets the share of unknown
   cells, including mines, on the fresh board. Queens grows connected regions
   of at least two cells and uses one explicit starter for easy boards.
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
   gallery section from easiest to hardest (for example `sudoku_9_4x4_kropki_consecutive_thermometers`).
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

Queens regions must contain at least two cells in published examples and
freshly authored boards. Single-cell regions give away a placement, regardless
of the puzzle's final grade. The fresh builder first gives each region a
neighbour, then grows the rest, and rejects any remaining singleton. Easy
Queens boards use one explicit starter queen instead. When expanding an
existing singleton, recheck the donor region's connectivity and uniqueness:
expansion adds alternative placements, so a visible given may be necessary.
Re-rate the result, audit it against the rest of the gallery and regenerate
both puzzle and solution pictures. Do not ban valid singleton syntax from
the parser: this is an authoring-quality rule, not a change to Queens rules.
When tests mutate a gallery seed, assert that the text actually changes;
regenerated layouts can turn literal replacements into silent no-ops.

When consolidating cosmetic families, compare the actual rules, sizes, region
layouts and measured deductions, not just names or icons. Keep distinct technique
coverage rather than near-duplicate boards at the same size, renumber by measured
difficulty, and regenerate pictures with the canonical piece. Update every
collection, booklet, web, benchmark and documentation reference together.
Preserve an icon option only as presentation; it must not change family identity
or region colouring. Recheck comments against current grades instead of carrying
old difficulty claims forward.

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
human difficulty ratings. Reserve `what_if`, the final fallback rule, for only
the very hardest puzzles; ordinary hard examples should be solved by the other
deduction rules. A tier is not enough by itself: inspect the actual deductions
and puzzle presentation, confirm that the puzzle is not simply prefilled, and
report any limitation of the solver's grading ladder. A board with under a
quarter of its cells open (`PREFILLED_OPEN_SHARE`) rates `trivial`, whatever
rule its last cells need. `tests/test_example_quality.py` rejects trivial or
non-unique gallery examples. Known exceptions there must link to an open issue.

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
