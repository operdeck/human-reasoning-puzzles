---
name: murdoku-puzzle-generator
description: "Use when transcribing a user-provided Murdoku photo or scan into solver text, or creating an original Murdoku puzzle from loose clues and constraints. Covers board reconstruction, clue mapping, theming, file validation, uniqueness, and deductive grade."
argument-hint: "Attach a puzzle image or specify a theme, size, clues, constraints, language, target grade, or output path"
---

# Murdoku Puzzle Assistant

You prepare the file; the solver verifies it. Never call a puzzle verified on
reasoning alone. Follow `AGENT.md` (branching, originality) and never overwrite an
existing file. This skill is Murdoku-only; for other families use
`docs/model-and-puzzle-formats.md` and never approximate them as Murdoku.

**Let the repo do the searching.** Placements, uniqueness, clue thinning and
grades come from repo tools (`uv run csp ...`, `csp.clue_search`), not from
reasoning in the conversation or throwaway scripts.

Clue and rule syntax: [Murdoku clue grammar](../../../docs/murdoku-grammar.md).
File sections: [Model and puzzle formats](../../../docs/model-and-puzzle-formats.md#murdoku).
Load these only when needed:
[Reading a scan](references/reading-a-scan.md),
[Fair clues and mysteries](references/fair-clues.md),
[Clue recipes](references/clue-recipes.md),
[Theme and pictures](references/theme-and-pictures.md),
[Booklet and review](references/booklet-and-review.md).

## Workflows

Detailed steps and traps: [workflow notes](references/workflow.md); file placement and full validation: [where files go](references/where-files-go.md), [validation notes](references/validation.md).

**Transcribe an image** (photo or scan of an existing puzzle):

1. Establish that the user may reproduce it; a supplied image or ignored folder is
   not permission. If unclear, stop and ask.
2. Read the actual image at full resolution and record size, regions, objects with
   their printed kinds, people, rules and clues in printed order; follow
   [Reading a scan](references/reading-a-scan.md).
3. Map every clue without changing its meaning. Compose it from the
   [clue recipes](references/clue-recipes.md) and the grammar reference before
   deciding it is unsupported; if it truly is, ask and label the file incomplete.
   Never approximate.
4. Ask about unclear cells, names or words. Solver results may hint at a misread
   but must not silently choose; do not alter clues to force uniqueness or a grade.
5. Keep the transcription and source images in git-ignored `proprietary puzzles/`,
   never in `examples/`, docs or commits.
6. Cross-check a printed solution against the clues and report disagreements. A
   person on an object proves it standable; an empty icon proves nothing.

**Build from constraints** (original puzzle):

1. Split hard constraints (people, board facts, clue meanings, size, features) from
   choices (theme, wording, grade); state the defaults you chose and ask only when
   ambiguity blocks you.
2. Use `N` people on an `N`×`N` board so every row and column holds exactly one. If
   the board needs fewer people, say in `Intro:` which lines stay empty and why.
3. Design the intended assignment, then the board, then the clues. Use
   `csp.clue_search suggest`/`thin` and `uv run puzzle-lab murdoku-board SPEC`
   (`--avoid examples`, `--suggest`); follow
   [Fair clues and mysteries](references/fair-clues.md) and
   [Theme and pictures](references/theme-and-pictures.md).
4. Render the puzzle and solution PNGs and get an independent image critique; see
   [Booklet and review](references/booklet-and-review.md).
5. Add the booklet text last, then run [Validation](#validation) and the
   [completion checklist](#completion-checklist).
6. Never copy a published board, clue set, story or solution.
7. If requirements conflict, explain instead of dropping one.

When both an image and a request are given, transcribe first, then build a
separate derived puzzle.

## Repo tools first

| Need | Tool |
|---|---|
| parse, solutions, grade, issues | `uv run csp FILE --show-model`, `--brute-force`, `--grade`, `--lint` |
| worked solution, reveal order | `uv run csp FILE --explain` |
| a person's live squares | `uv run csp FILE --track-person P` |
| clues that make a placement unique | `uv run python -m csp.clue_search suggest FILE --solution "..."` (`--needs N`, `--needs-mark quiet`, `--cover`) |
| object squares the allowed placements use | `uv run python -m csp.clue_search occupancy FILE` |
| drop or report redundant clues | `uv run python -m csp.clue_search thin FILE --max-grade G`; `report FILE` |
| draft boards from a spec | `uv run puzzle-lab murdoku-board SPEC` (`--avoid examples`, `--suggest`) |
| pictures, booklet | `--png`, `--docx` (`--nosolution` skips solving) |
| read a scan | `uv run python -m csp.scan PAGE --size N --tiles DIR --sheet FILE --seed r3c5 --ocr` |
| new emoji | `uv run python scripts/vendor_emoji.py U+XXXX` |

- Do not solve or test clue subsets by hand or with one-off `/tmp` code. Add a
  reusable, tested repo option instead, document it here, and ship it separately.
- Run tools with a timeout and read saved output rather than re-running a long
  command; prefer `tail`/`grep`.
- Fix engine or wording problems in `src/csp/` with a test, not in the puzzle.
- `suggest` only proposes simple named-person location, line and direction
  templates. Author unions, projections, counts, quantifiers and set comparisons
  from the [clue recipes](references/clue-recipes.md), then lint and brute-force.

## Where files go

- `examples/<category>/` for played puzzles; the folder is the category in the web
  player and booklet. Use an existing category or add one; `demo/` holds showcase
  boards.
- `tests/puzzles/` for test-only puzzles; new examples need unique names because
  tests look them up by file name.
- Write new examples and their size/grade into `docs/puzzle-collection.md`;
  re-export the web collection and check its category, number and link.
- One canonical file per puzzle; never commit generated `.png` or `.docx` files.
- Keep a puzzle PR focused; engine, icon and wording fixes may come along with
  tests, but unrelated refactors and skill rewrites go in their own PR.

## Validation

Run from the repo root, one option at a time:

```bash
uv run csp FILE --show-model   # parses and compiles
uv run csp FILE --brute-force  # 0, 1 or many; generated puzzles need 1, in < 5 s
uv run csp FILE --grade        # hardest rule used, or "unsolved"
uv run csp FILE --lint         # declarations, expressions, icons, roles, redundancy
uv run csp FILE --png /tmp/x.png   # look at the puzzle and -solution picture
```

- Give each uniqueness or grading solve a hard timeout of a few seconds; a timeout
  is "not good enough", never wait minutes.
- Uniqueness is relative to clue semantics; it proves neither a correct
  transcription nor faithful wording. `--brute-force` uses the reference evaluator,
  independently of the lowering the solver uses; a disagreement is a compiler bug:
  fix `murdoku_lower` with a test, not the puzzle.
- Grades are this solver's ladder (`single` < `count` < `relations` <
  `subsumption` < `cover2` < `cover3` < `chains` < `what_if`).
  `--require-forward` forbids `what_if`.
- `--lint` reports unknown names, mixed-sort unions, bad modes or measures,
  infeasible counts, impossible relations and legacy forms with line and column.
  Fix the expression; never add a second reader.
- For a transcription, report `--brute-force` and `--grade` as diagnostics and
  compare with the image; never change clues to force a result.

### Completion checklist

For a finished Murdoku under `examples/`, before reporting done:

- `--brute-force`: exactly one solution; `--grade`: the target (or the actual
  grade, reported as such); `--lint`: no issues.
- Clues thinned; few exact-number clues; no giveaway.
- For a mystery, `--explain` reveals the answer by the rules, late.
- `--png` looked at and independently critiqued; `--docx` page check read.
- Legend and rules show no engine syntax; authored wording in the solution is
  faithful and does not reveal the answer.
- The key clue is necessary, series order follows `--grade`, and
  `docs/puzzle-collection.md` is updated; `uv run pytest -q` and `ruff` pass.
- Report the path, solution, grade and open doubts.
