# Release Notes

## Unreleased

## 0.3.0
**New Feature(s)**
* [#11 Murdoku: Add person attributes and quantified clue targets](https://github.com/operdeck/prrrove/issues/11)
    * `src/csp`: Added fixed person attributes and pronoun forms, typed targets, bounded quantified clues, new row/column/area-corner and region-adjacency predicates, bilingual explanations, and brute-force verification.

## 0.2.0
**New Feature(s)**
* [#10 Murdoku: Add generic roles and role constraints](https://github.com/operdeck/prrrove/issues/10)
    * `src/csp`: Added data-driven role membership, cardinality, eligibility, area policies, object/mark bindings, role relationships, occupant effects, independent brute-force verification, and role output in text, story, PNG, and model reports.
    * Example: `Roles: engineer: 2` requires exactly two people to have the engineer role; roles can overlap unless constrained.
* [#9 Murdoku: Add optional cell marks and occupant conditions](https://github.com/operdeck/prrrove/issues/9)
    * `src/csp`: Added overlapping named cell sets and conditional `alone`/`not_alone` area occupancy rules, such as `quiet: r2c3 ; alone`.
* [#8 Murdoku: Add general counting constraints to the core](https://github.com/operdeck/prrrove/issues/8)
    * `src/csp/core.py`: Added allowed-count constraints and reified counts for exact, ranged, and other count-based rules.
* [#7 Murdoku: Model edge items and corner-anchored objects](https://github.com/operdeck/prrrove/issues/7)
    * `src/csp`: Added doors, windows, and corner objects as touched-cell sets, enabling clues to refer to boundaries without occupying cells.
* [#6 Murdoku: Add tagged and overlay-area semantics](https://github.com/operdeck/prrrove/issues/6)
    * `src/csp`: Added reusable area tags that can overlap or span disconnected regions for location clues and area policies.
* [#5 Murdoku: Declare object kinds and footprints explicitly](https://github.com/operdeck/prrrove/issues/5)
    * `src/csp`: Required each object footprint to declare `blocking` or `standable` and validated connected, non-overlapping cells.
