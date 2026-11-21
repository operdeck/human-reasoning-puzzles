Read this for the detailed transcription and build steps and their traps.

**Transcribe an image** (photo or scan of an existing puzzle):

1. First establish the user may reproduce it; a supplied image or ignored folder
   is not permission. If unclear, stop and ask.
2. Read the actual image at full resolution (zoom or crop; not OCR alone; never
   fetch another version). Record size, regions, object footprints with their
   **printed** kinds, people, board-wide rules and clues in printed order.
3. Map each clue without changing its meaning. Before deciding one is not
   expressible, follow the [recipe guide](clue-recipes.md) and the canonical
   expression reference — most alternatives, counts, special-square and victim
   forms compose from the same primitives. If one really is not
   expressible, say so and ask; a partial file must be labelled incomplete.
   Never approximate.
4. Ask about unclear cells, names or words. Solver results may hint at a misread
   but must not silently pick between readings. Do not alter clues to force
   uniqueness or a grade; report what `--brute-force`/`--grade` say.
5. Default path: git-ignored `proprietary puzzles/`. Keep transcriptions and
   source images out of `examples/`, docs and commits.
6. If the source shows a solution, cross-check it against the clues; report
   disagreements instead of editing. A person on an object proves it standable;
   an empty icon proves nothing.

**Build from constraints** (original puzzle):

1. Split the request into hard constraints (people, board facts, clue meanings,
   size, features) and choices (theme, wording, grade); state the defaults you
   chose. Accept plain-language clues; ask only when ambiguity blocks you.
2. Use `N` people on an `N`×`N` board so every row and column holds exactly
   one person. If a board must have fewer people, say in the `Intro:` which
   lines stay empty and why; never leave it unexplained.
3. Design the intended assignment first, then the board (areas, objects,
   doors) around it, then the clues: let `csp.clue_search suggest` propose
   them and `thin` remove the unneeded ones (see [Repo tools first](../SKILL.md#repo-tools-first)).
   Follow [Fair clues](fair-clues.md) and, for a mystery,
   [Late-reveal mysteries](fair-clues.md#late-reveal-mysteries).
   For a fresh board, start from `uv run puzzle-lab murdoku-board SPEC` (see
   `specs/murdoku/vietnam-6x6.txt`): a short spec of size, areas, people, the
   late figure with companions, objects and key clues gives ranked drafts
   with an intended placement, contact sheets and a report of rejections.
   Use `--avoid examples` to skip layouts already in the collection, including
   rotated, mirrored or region-renamed copies. `--suggest` closes each kept
   draft with `clue_search suggest` (late figure excluded, key clues kept
   necessary, every other figure named via `--cover`, and `decor:` objects
   omitted from clue suggestions) and reports clue count, grade and whether the
   late figure is resolved last. Pick a draft that closes at the target grade
   and passes the late-reveal check; a roomy late-figure area often lets a
   companion and the late figure swap and never closes. An object line ending
   in `across` (a tunnel, a bridge) straddles one border between exactly two
   areas. Pick one, then thin and check as above.
4. Render the puzzle and solution PNGs and get an independent, image-based
   critique from another LLM (see [Independent visual critique](booklet-and-review.md#independent-visual-critique)).
   Review the suggestions against the user's constraints; incorporate useful
   changes and rerender.
5. Add the booklet text ([Booklet text](booklet-and-review.md)) once the clues are final,
   then run [Validation](../SKILL.md#validation) and the [completion checklist](../SKILL.md#completion-checklist).
6. Never copy a published board, clue set, story or solution.
7. If requirements conflict, explain instead of dropping one.

When both are given, transcribe first, then build a separate derived puzzle.

## Series traps found while authoring

- **A series needs genuinely different `Grid:` sections.** `audit.layout_key`
  compares the region grid up to rotation, reflection and region renaming, so a
  mirrored or relabelled board still counts as the same layout. Change the room
  plan, not just the objects.
- **Seats in a ring.** `k` people need `k` distinct rows and `k` distinct
  columns. Eight chairs around a one-cell table form a 3x3 ring, so three
  bikkels would fill all three rows and columns; add a ninth chair elsewhere
  (the cold stool in the boot room) to keep the set a deduction rather than a
  line consequence.
- **A series can live around a route.** A hut, train or ship reads better
  when one area is a one-cell-wide corridor from the top row to the bottom
  row, with a door into most rooms (the *In de berghut* series draws it as a
  `gang` area). Keep it free of furniture so it reads as the route, and check
  it: `tests/test_berghut_series.py` asserts the corridor is a simple path
  (two ends, no branch) and that every room is reachable from it through
  doors. Corridor cells count for clues like any other area.
- **`thin --max-grade G` is the grade tool.** Without it, thinning can turn a
  `relations` puzzle into `cover3`; with it, clues stay as long as the puzzle
  remains unique, solved and at or below `G`.
- **Give `clue_search` time.** `outcome` runs two solver workers, so a
  `--timeout 1` reports "timeout" on puzzles the CLI solves in under a second.
  Use five seconds or more for grading and thinning.
- **Quantified filters use natural-language references.** A bound variable
  such as `?a` in `(?a in areas where count (people in ?a) = 2)` is rendered
  as "that area" / "dat gebied", not as parser syntax.

## Reading a scan
