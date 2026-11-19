Read this for the full validation rules, diagnostics and completion checklist.

`examples/japan/samen-onderweg.txt` needs no `what_if`: Mio on the bank and
  Keiko beside the lantern give Osaka two, the busiest clue gives Tokyo three,
  and five travellers leave Okinawa empty. When a population clue grades
  `what_if`, check whether that capacity argument should close it before adding
  decoys or loosening clues.
- `--brute-force` must finish in < 5 s for a generated puzzle; if not, add
  clues or shrink the board. `clue_search` runs every solve with `--timeout`.
- For a transcription, `--brute-force` and `--grade` are diagnostics: report
  them and compare with the image; never change clues to force a result.
- Report path, parse result, solution count, actual grade, intended solution and
  open doubts. Do not claim a grade `--grade` did not print. Never weaken
  checks or change clue semantics to make a puzzle pass; engine fixes come
  with a test (see [Repo tools first](#repo-tools-first)).

### Completion checklist

For a finished Murdoku under `examples/`, before reporting done:

- `--brute-force`: exactly one solution; `--grade`: the target (or the actual
  grade, reported as such); `--lint`: no issues.
- Clues thinned (`clue_search thin`); few exact-number clues; no giveaway.
- For a mystery: `--explain` reveals the answer by the rules, late.
- `--png` looked at (puzzle and solution), independently critiqued, and useful
  visual suggestions considered; `--docx` page check for booklet text. Look at
  the pages themselves: `--pdf FILE` (via Word) and `pdftoppm -png` give images.
- The picture legend and booklet rules show no engine syntax (`count people
  on object:...`); author wordings appear on player pages, never in solutions.
- The themed key clue is necessary (`report`), and the series order follows
  `--grade`; report any conflict with the requested order instead of hiding it.
- An independent clue review used only player-facing material; each clue was
  restated as a constraint, alternate readings were checked, and solvability
  findings were verified against the source and rendered clue count.
- `docs/puzzle-collection.md` updated; `uv run pytest -q` and `ruff` pass.
- Report path, solution, grade and any open doubts.

## Theme, objects and pictures

- **Objects fit the theme and their region.** A savanne has acacias, baobabs and
  grass; mountains have rocks, a hut, a waterfall; a Japanese restaurant has
  tatami, zaisu and plates; a garden has a park bench. Check every object
  against the region it sits in.
- **Region colours mean something and stay consistent** across a series
  (desert sandy yellow, swamp green-brown, mountains grey-white, water blue,
  forest green). Keep neighbours distinguishable. Use plain region names
  ("Garden", not "Green garden"); a name that does mention a colour must match
  its background (`tests/test_solver.py` checks this).
- **Order a numbered series by measured difficulty.** Run `--grade` on every
  candidate and place simpler puzzles before harder ones, numbering the files
  in that order (`zoo-murdoku-1`, `-2`, ...; unnumbered series such as `demo`
  use `murdoku_1_first_case`). Update all numbered links, tests, pictures,
  booklet references and story titles ("the first case") when inserting or
  swapping a puzzle. Compare solved
  boards across the series too: avoid repeating the same placement pattern or
  a trivially rotated/reflected layout. `uv run puzzle-lab audit examples`
  checks both for the whole collection. Every series gets the same measured
  difficulty-order check; do not hardcode category exemptions. Report a
  story-order conflict rather than silently bypassing the audit or renumbering
  an owner-authored story without approval.
- **Items whose owner must be deduced lie on the board.** When the puzzle is
  "who wears the bathrobe?", draw the items as standable objects at fixed
  squares (more items than wearers) and state the totals as `Rules:` counts
  (`count people on object:badjas = 2`). Standing on the square means wearing
  it. Use `Attributes:` only for traits the player is told up front; the
  legend then lists the holders with the trait's icon.
- Avoid duplicate category lines in the legend: when a fixed role has the same
  name and exactly the same members as an attribute, show the role line only.
  Keep the attribute line when roles are hidden or the membership is not
  provably identical.
