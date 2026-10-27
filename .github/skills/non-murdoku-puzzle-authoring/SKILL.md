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
   `docs/examples.md` for the existing gallery. Preserve displayed aliases:
   Queens and DogDoku are separate names, as are Binairo and Tango. The file
   name, `Family:`, comment and pieces must agree: a `queens_*` file uses
   `Family: queens` and the queen piece; dog or puppy pieces belong only in
   `Family: dogdoku` files named `dogdoku_*`. `tests/test_example_quality.py`
   enforces this.
2. Use an existing original example as a seed, or create an original seed in
   the family format. Never transcribe published puzzles unless the user has
   permission and explicitly asks for transcription.
3. Generate a candidate with a fixed seed so it can be reproduced. For a new
   example, prefer `puzzle-lab fresh`: it builds a brand-new solution and
   layout (Binairo, Tango, Queens, DogDoku, Suguru, Minesweeper, Akari), so the
   example does not share a solution with the rest of the gallery:

   ```bash
   uv run puzzle-lab fresh tango --size 8 --tier medium --open-share 0.6 \
     --seed 26 --output /tmp/candidate.txt --comment "Tango 8x8: medium, ..."
   uv run puzzle-lab fresh akari --size 6 --tier medium \
     --seed 122 --output /tmp/akari.txt --comment "Akari 6x6: medium, ..."
   ```

   `--open-share` sets the share of empty Binairo/Tango cells; more open
   cells usually means harder. For Minesweeper, it sets the share of unknown
   cells, including mines, on the fresh board. Queens and Suguru drop givens
   while the solution stays unique. Akari builds a fresh wall layout and
   derives numbered-wall clues from a valid bulb placement. Large Suguru boards
   can take many minutes.
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
5. Search the gallery to find coverage gaps and verify a new file is indexed
   under the intended display family:

   ```bash
   uv run puzzle-lab search examples --family tango --tier hard --json
   ```

6. Place approved original examples under `examples/`, give each a descriptive
   filename and short comment, and update the tier table in `docs/examples.md`.
   Run the repository example tests after adding files.
7. If the generator cannot find a candidate in its attempt budget, report that
   honestly. Improve the family-specific generator or choose another seed;
   do not loosen uniqueness checks, relabel a trivial puzzle, or fall back to
   brute-force-only solving.

## Difficulty and validation

`puzzle-lab rate` reports the hardest solver rule used and a tier derived from
that rule, with limited family-aware calibration for small relational and
count-only puzzles. These are repository-specific estimates, not universal
human difficulty ratings. A tier is not enough by itself: inspect the actual
deductions and puzzle presentation, confirm that the puzzle is not simply
prefilled, and report any limitation of the solver's grading ladder. A board
with under a quarter of its cells open (`PREFILLED_OPEN_SHARE`) rates
`trivial`, whatever rule its last cells need. `tests/test_example_quality.py`
rejects trivial or non-unique gallery examples. Known exceptions there must
link to an open issue.

For Murdoku, stop here and use `.github/skills/murdoku-puzzle-generator/` and
its own workflow. Do not change Murdoku examples, skills, tools, or behavior
while authoring non-Murdoku puzzles.
