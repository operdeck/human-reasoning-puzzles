---
name: non-murdoku-puzzle-authoring
description: "Create, rate, and find original non-Murdoku puzzles with repository-native tools. Use for example generation, tiered puzzle sets, puzzle quality review, or non-Murdoku authoring."
argument-hint: "Specify puzzle family, easy/medium/hard target, constraints, theme, or seed example"
---

# Non-Murdoku Puzzle Authoring

Use the repository's puzzle tools to create and check examples. Do not design or
rate a puzzle from agent reasoning alone. This skill covers every supported family
except Murdoku; Murdoku keeps its own skill and tools.

Syntax: [Model and puzzle formats](../../../docs/model-and-puzzle-formats.md).
Commands and grading: [CLI options](../../../docs/cli.md). Rating commands and
coverage gaps: [grading and auditing](../../../docs/puzzle-collection.md); the
grades themselves are on the
[web index](https://operdeck.github.io/human-reasoning-puzzles/). Read
[family notes](references/family-notes.md) for the newer families and
[difficulty and validation](references/difficulty-and-validation.md) when rating,
naming or auditing.

## Workflow

Full workflow, options and traps: [workflow notes](references/workflow.md).

1. Read the family syntax and the [coverage gaps](../../../docs/puzzle-collection.md).
   Preserve display aliases: Binairo and Tango stay separate (Tango adds relation
   signs); Queens is the one-star presentation of `Family: starbattle` (`Stars: 1`,
   `queens_*` files and wording); `Family: queens` remains a compatibility alias.
   `tests/test_example_quality.py` enforces this.
2. Use an existing original example as a seed, or create an original seed. Never
   transcribe a published puzzle unless the user has permission and asks.
3. Prefer `puzzle-lab fresh` for a new board: it builds a new solution and layout,
   so the example does not share a solution. Ask `puzzle-lab sweep` what a builder
   reaches, then choose a seed:
   ```bash
   uv run puzzle-lab sweep towers --size 5 --open-share 0.3 --seed 1100 --count 15 --save /tmp/towers
   uv run puzzle-lab fresh tango --size 8 --tier medium --open-share 0.6 --seed 26 --output /tmp/candidate.txt
   uv run puzzle-lab rate /tmp/candidate.txt --json
   ```
   `--open-share` sets empty (Binairo/Tango) or unknown (Minesweeper) cells;
   `--stars 1` makes a Queens board; `--grade` adds exact technique coverage to a
   tier. Bridges has a `fresh` builder: it grows a non-crossing connected network,
   derives island numbers, and rejects non-unique boards. Its `--open-share`
   controls the density of extra links, not hidden island numbers.
   `generate` only re-masks/mutates a seed, so use it for variations, never to
   fill a tier with copies; `--as-family` is only for compatible aliases. Keep
   Towers at 6×6 or smaller, Pattern at 15 cells a line and Magnets at even sides.
   Rooms puzzles have their own lab tools: give the plan a `Solution:` line and no
   clues, then `uv run puzzle-lab rooms-clues plan.txt --clues 10 --kinds
   in,dir,beside,empty --last Ada --output puzzle.txt` searches for a set that is
   unique, needs every clue, pins nobody on a single clue, uses only those kinds
   (emptiness only as empty or not empty) and leaves the named person last;
   `rooms-check` verifies a finished file against the same brief.
   * A fact that holds for the whole puzzle — "the garden is empty or holds two",
     a pair that always shares — is a `Rules:` line, not a clue: it uses the same
     grammar, is compiled as an always-on constraint and is left out of the
     numbering. Put the author's brief in the puzzle file's comments, and keep the
     clues to one plain kind each (a room or group, a compass direction, beside,
     empty or not empty, together or alone). Age clues are their own kind: give
     the puzzle an `Ages:` block with one age per person and compare an area's
     total with the sum of two or three named people, as in
     `sum (ages in area:A) < sum (ages of X, Y)`; avoid `=` in age clues. The
     picture and the booklet print the ages. No other counts and no king or
     knight distances: that is a house style for authored house puzzles, not a
     limit of the family.
   * Use each room and group alias in at most one clue, and each person alias in
     at most one clue; reuse across the puzzles of one set is what makes a set feel
     samey. A person left without a clue is fine when a rule or the other clues
     force their seat — that is a late discovery, and `--last` measures the last
     person *a clue* settles.
   * The published `rooms_*` examples are the family's showcase: they use counts
     and single-room aliases on purpose, so `rooms-check` reports house-style
     deviations there. Do not "fix" them into the house style.
4. Rate before adding or describing a candidate. Only unique, deductively solved,
   nontrivial boards qualify; preserve family, grade, tier and uniqueness. Check
   structural triviality too (Puzzle Lab marks it). Never promote an unrated board.
5. Search for coverage gaps and confirm the display family:
   `uv run puzzle-lab search examples --family tango --tier hard --json`.
6. Place approved originals as `<family>_<n>_<size>[_<variant>].txt`, numbered from
   easiest to hardest; leave tier words out of names. Renumber later files and
   pictures when inserting, record any unreachable tier under coverage gaps in
   [grading and auditing](../../../docs/puzzle-collection.md), and re-export the web
   collection. Run `uv run puzzle-lab audit examples`: fix a shared solution or
   layout with a fresh board or new seed, never by turning or relabelling a copy.
   Give every example its own seed. Run `uv run pytest -q
   tests/test_example_quality.py` after adding files.
7. If no candidate fits the budget, report it honestly and improve the generator or
   try another seed; never loosen uniqueness or relabel a trivial board.
8. For Murdoku, stop and use `.github/skills/murdoku-puzzle-generator/`; never
   change Murdoku examples, skills, tools or behavior here.

## Feeding lessons back

When authoring uncovers a general pitfall or missing capability, improve the repo
tool (`puzzle-lab`, a generator or the renderer) with a test and record the lesson
in this skill in the same PR. Order a series by measured difficulty, never reuse a
layout or solution across examples, and reject fully or almost fully prefilled
boards. Keep account names, tokens and machine-local setup out of the repository.
