Read this for the full non-Murdoku generate, rate, name and audit workflow.

## Workflow

1. Read `../../../docs/model-and-puzzle-formats.md` for the exact family syntax and
   `../../../docs/puzzle-collection.md` for rating commands and coverage gaps, and the
   [web index](https://operdeck.github.io/human-reasoning-puzzles/) for the
   existing collection and its grades. Preserve displayed aliases:
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
   Calcudoku, Kakurasu, Star Battle, Tents, Battleships, Towers, Mosaic,
   Dominosa, Rectangles, Magnets, Undead, Pattern, Map, Bridges), so the example does
   not share a solution with the rest of the gallery. Before choosing seeds, ask
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
   Check for structural triviality too: Puzzle Lab marks Kakurasu trivial when
   every row and column sum independently fixes its line, and Binairo trivial
   when all rows or all columns can be completed independently from their
   givens. A solving grade and uniqueness do not by themselves make a puzzle
   interesting.
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
   the order and the web index shows the grade. When a new board lands in
   the middle, renumber the later files (with their `docs/images` pictures) and
   update every reference. Give each a short comment, and record any tier the
   family still cannot reach under coverage gaps in
   `../../../docs/puzzle-collection.md`.
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
