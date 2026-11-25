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
Commands and grading: [CLI options](../../../docs/cli.md). Coverage and tiers:
[puzzle collection](../../../docs/puzzle-collection.md). Read
[family notes](references/family-notes.md) for the newer families and
[difficulty and validation](references/difficulty-and-validation.md) when rating,
naming or auditing.

## Workflow

Full workflow, options and traps: [workflow notes](references/workflow.md).

1. Read the family syntax and the [collection](../../../docs/puzzle-collection.md).
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
4. Rate before adding or describing a candidate. Only unique, deductively solved,
   nontrivial boards qualify; preserve family, grade, tier and uniqueness. Check
   structural triviality too (Puzzle Lab marks it). Never promote an unrated board.
5. Search for coverage gaps and confirm the display family:
   `uv run puzzle-lab search examples --family tango --tier hard --json`.
6. Place approved originals as `<family>_<n>_<size>[_<variant>].txt`, numbered from
   easiest to hardest; leave tier words out of names. Renumber later files and
   pictures when inserting, update the tier table in
   [the collection](../../../docs/puzzle-collection.md), and re-export the web
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
