# Release Notes

## Unreleased
**Bug Fix(es)**
* Name-vs-appearance consistency
    * `examples/murdoku_sparse_mystery.txt`: "Blue hall" is now blue instead of grey; all other examples audited, no other mismatches.
    * Added a test that colour words in region names match their background colour, plus guidance in the Murdoku skill and `AGENT.md`.
* Murdoku PNG: the English `carpet` (and `rug`) object now draws the hand-made rug icon instead of the literal word, as `tapijt` already did.
    * `src/csp/icons.py`: added the `oven` icon, which `murdoku_house.txt` lacked.
    * `src/csp/picture.py`: shared `CARPET_NAMES`/`WELL_NAMES` drive both drawing and the missing-icon check; `tests/test_picture.py` checks every object in the Murdoku examples has an icon.
* [#26 Handle empty domains in --show-model](https://github.com/operdeck/human-reasoning-puzzles/issues/26)
    * `src/csp/report.py`: `--show-model` no longer crashes with `IndexError` when contradictory clues empty a variable's domain; it reports an "Invalid model: contradiction" section listing the affected variables.

**New Feature(s)**
* New Murdoku example puzzles
    * `examples/food-murdoku-1.txt`, `-2.txt`, `-3.txt`: Japanese food and cities (5x5 to 7x7).
    * `examples/tamagotchi-murdoku-6x6.txt`, `-9x9.txt` (stream and bridge), `-12x12.txt`: "where is the devil?" late-reveal puzzles; new `bridge` icon.
    * `tests/test_picture.py`: the icon check covers every example with a `People:` section.
* [#12 Murdoku: Migrate the format and verify feature composition](https://github.com/operdeck/human-reasoning-puzzles/issues/12)
    * `src/csp`: Added Murdoku lint and forward-only checks, optional default PNG paths, and 16x16 count/chain benchmark coverage.
    * Added a neutral combined-format example with brute-force uniqueness and per-step soundness coverage.

## 0.4.0
**New Feature(s)**
* [#19 Murdoku: Global clues](https://github.com/operdeck/human-reasoning-puzzles/issues/19)
    * `src/csp`: Added whole-board counts over people, roles, attributes, object/area/cell sets, empty areas, and empty cells using the generic `COUNT` primitive; integrated count explanations, step status, PNG scopes, brute-force checks, and size benchmarks.
    * Example: `count empty areas in tag:inside = 1` requires exactly one logical region in the tagged set to be unoccupied.

## 0.3.0
**New Feature(s)**
* [#11 Murdoku: Add person attributes and quantified clue targets](https://github.com/operdeck/human-reasoning-puzzles/issues/11)
    * `src/csp`: Added fixed person attributes and pronoun forms, typed targets, bounded quantified clues, new row/column/area-corner and region-adjacency predicates, bilingual explanations, and brute-force verification.
    * Example: `unique_attribute engineer Ada Ben Cal` requires exactly one selected person to have the engineer attribute.

## 0.2.0
**New Feature(s)**
* [#10 Murdoku: Add generic roles and role constraints](https://github.com/operdeck/human-reasoning-puzzles/issues/10)
    * `src/csp`: Added data-driven role membership, cardinality, eligibility, area policies, object/mark bindings, role relationships, occupant effects, independent brute-force verification, and role output in text, story, PNG, and model reports.
    * Example: `Roles: engineer: 2` requires exactly two people to have the engineer role; roles can overlap unless constrained.
* [#9 Murdoku: Add optional cell marks and occupant conditions](https://github.com/operdeck/human-reasoning-puzzles/issues/9)
    * `src/csp`: Added overlapping named cell sets and conditional `alone`/`not_alone` area occupancy rules, such as `quiet: r2c3 ; alone`.
    * Example: `quiet: r2c3 ; alone` applies only when someone occupies r2c3.
* [#8 Murdoku: Add general counting constraints to the core](https://github.com/operdeck/human-reasoning-puzzles/issues/8)
    * `src/csp/core.py`: Added allowed-count constraints and reified counts for exact, ranged, and other count-based rules.
    * Example: `exactly 2 in_region Ada kitchen ; in_region Ben kitchen ; in_region Cal kitchen` requires exactly two of those clues to hold.
* [#7 Murdoku: Model edge items and corner-anchored objects](https://github.com/operdeck/human-reasoning-puzzles/issues/7)
    * `src/csp`: Added doors, windows, and corner objects as touched-cell sets, enabling clues to refer to boundaries without occupying cells.
    * Example: `gate: door r2c3 r2c4` lets `at Ada gate` match either cell touched by the door.
* [#6 Murdoku: Add tagged and overlay-area semantics](https://github.com/operdeck/human-reasoning-puzzles/issues/6)
    * `src/csp`: Added reusable area tags that can overlap or span disconnected regions for location clues and area policies.
    * Example: `inside: kitchen hall` lets `in_tagged Ada inside` target either region.
* [#5 Murdoku: Declare object kinds and footprints explicitly](https://github.com/operdeck/human-reasoning-puzzles/issues/5)
    * `src/csp`: Required each object footprint to declare `blocking` or `standable` and validated connected, non-overlapping cells.
    * Example: `wall: blocking r1c1` and `bench: standable r2c2 r2c3` distinguish an obstacle from a surface people can occupy.
