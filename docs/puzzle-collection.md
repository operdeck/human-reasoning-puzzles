# Puzzle collection and grading

Reference for puzzle authors and agents. Players: use the
[web puzzle index](https://operdeck.github.io/human-reasoning-puzzles/).

Every tracked example is original, generated or owner-authored, with a unique
brute-force solution and engine agreement checked by the tests. Full commands
are in [CLI options](cli.md); syntax is in
[Model and puzzle formats](model-and-puzzle-formats.md).

`puzzle-lab audit` checks difficulty order for every series without exemptions.
*Wie doet het met wie* reports a conflict (puzzle 1 needs `cover2`; 2 and 3
`subsumption`), retaining its numbering. Murdoku still leads, Demo first.

## Quick commands

```bash
uv run csp examples/demo/murdoku_1_first_case.txt --explain
uv run csp examples/queens_6_4x4.txt --show-model
uv run csp examples/logicgrid_1_3x3.txt --brute-force
```

## Murdoku

Core syntax and feature cases: `murdoku_1_first_case`, `murdoku_3_house`,
`murdoku_2_point_objects`, `murdoku_sparse_mystery` (roles and one companion),
`murdoku_global_counts` and `murdoku_composition` (all board features); the two
test files live in `tests/puzzles/`, the rest in `examples/demo/`.

- Japanese food: `food-murdoku-2` 5×5 `chains`; `food-murdoku-1` 6×6 `subsumption`; `food-murdoku-3` 7×7 `what_if`.
- Japan: `samen-in-japan` 6×6 `cover2` (busiest, quietest and exact count); `samen-onderweg` and `samen-in-de-blauwe-bladeren` use population arguments too.
- Zoo: `zoo-murdoku-1` 5×5 `relations`; `zoo-murdoku-2` 6×6 `subsumption`; `zoo-murdoku-3` 6×6 `cover2`.
- Menu: `menu-murdoku-1` 6×6 `relations`; `menu-murdoku-2` 7×7 `subsumption`; `menu-murdoku-3` 8×8 `what_if`.
- Vietnam: `vietnam-murdoku-1` 5×5 `relations`; `vietnam-murdoku-2` 6×6 `subsumption`; `vietnam-murdoku-3` 7×7 `cover2`. Each has a tunnel straddling a city border; the dish is placed last.
- Tamagotchi: `tamagotchi-murdoku-6x6` `subsumption`; `-9x9` and `-12x12` `what_if`.
- Murder Hotel: `murder-hotel-1` 8×8 `relations`; `-2` 9×9 and `-3` 10×10 `subsumption`.
- Halloween at the Museum: `-1` 6×6 and `-2` 7×7 `subsumption`; `-3` 8×8 `cover2`.
- Orient Express: `murdoku_orient_express` 8×8 `relations`; `_2` 10×10 `subsumption`; `_3` 10×10 `chains`.
- Wie doet het met wie: `-1` 5×5 `cover2`; `-2` 4×4 and `-3` 5×5 `subsumption`; `-4` 6×6 and `-5` 7×7 `cover2`.
- Owner-authored: `prrrdoku1` and `prrrdoku2`; `prrrdoku3` needs `what_if`.

## Verified non-Murdoku difficulty

Tiers come from `puzzle-lab search examples --tier <easy|medium|hard>`. Every
file is deductively solved with a unique independent solution; tiers are this
solver's estimate. `none` marks a coverage gap, not a hidden board. Binairo and
Tango are separate because Tango adds relation signs and forbids identical rows
and columns. Cosmetic pieces do not create another family.

- Sudoku: easy sudoku_5_9x9 (single); medium sudoku_21_9x9_naked_pair (cover2); hard sudoku_33_9x9_chains (chains).
- Calcudoku: easy calcudoku_1_4x4 (relations); medium calcudoku_3_6x6 (relations); hard calcudoku_5_7x7 (cover3).
- Futoshiki: easy futoshiki_1_5x5 (single); medium futoshiki_2_5x5 (relations); hard futoshiki_3_5x5 (chains).
- Tectonic / Suguru: easy suguru_1_4x4 (single); medium none; hard suguru_2_8x8 (chains).
- Queens / Star Battle: easy Queens: queens_1_4x4, queens_2_5x5 (single); Star Battle: starbattle_1_8x8 (count); medium Queens: queens_3_7x7, queens_4_8x8 (subsumption), queens_5_9x9 (cover2); Star Battle: starbattle_2_8x8 (cover2); hard Queens: queens_6_4x4 (chains); Star Battle: starbattle_3_12x12 (cover3).
- Zebra logic grid: easy logicgrid_1_3x3 (relations); medium logicgrid_2_6x6 (relations); hard none.
- Binairo / Takuzu: easy binairo_1_8x8 (relations); medium binairo_2_8x8 (subsumption); hard binairo_3_4x4 (what_if).
- Tango: easy tango_1_8x8 (relations); medium tango_3_8x8 (relations); hard tango_4_4x4 (what_if).
- Tents and Trees: easy tents_1_8x8 (single); medium tents_2_8x8 (cover2); hard tents_3_4x4 (what_if).
- Minesweeper-style: easy none; medium minesweeper_1_8x8 (subsumption); hard minesweeper_4_8x8 (cover3).
- Light Up / Akari: easy none; medium akari_1_6x6 (subsumption); hard akari_2_8x8 (chains).
- Kakurasu: easy kakurasu_1_4x4 (relations); medium kakurasu_2_8x8 (relations); hard none.
- Battleships: easy none; medium battleships_1_6x6_fleet, battleships_2_8x8_fleet (count); battleships_3_8x8_fleet (subsumption); hard battleships_4_8x8_fleet, battleships_5_8x8_fleet (chains).
- Towers: easy towers_1_4x4 (relations); medium towers_2_5x5, towers_3_6x6 (relations); hard towers_4_5x5 (chains).
- Mosaic: easy mosaic_1_5x5 (count); medium mosaic_2_5x5 (subsumption), mosaic_3_6x6 (cover2); hard mosaic_4_8x8 (cover3).
- Dominosa: easy dominosa_1_5x6 (single); medium dominosa_2_6x7 (subsumption), dominosa_3_7x8 (cover2); hard dominosa_4_6x7 (cover3), dominosa_5_7x8 (chains).
- Rectangles: easy rectangles_1_5x5, rectangles_2_9x9 (single); medium rectangles_3_9x9, rectangles_4_14x14 (subsumption); hard rectangles_5_9x9 (cover3), rectangles_6_9x9 (chains).
- Magnets: easy magnets_1_4x4 (relations); medium magnets_2_6x6 (relations), magnets_3_6x6 (cover2); hard magnets_4_6x6 (cover3).
- Undead: easy undead_1_4x4, undead_2_4x4, undead_3_4x4, undead_4_4x4 (relations); medium undead_5_5x5 (relations); hard undead_6_5x5 (what_if).
- Pattern (nonogram): easy pattern_1_4x4 (relations); medium pattern_2_8x8, pattern_3_12x12 (relations); hard pattern_4_10x10 (what_if).
- Map (four colouring): easy map_1_6x6, map_2_9x9 (single); medium none; hard map_3_9x9, map_4_12x12 (chains).
- Thermometers: easy thermometers_1_4x4 (count); medium thermometers_2_5x5, thermometers_3_8x8 (relations); hard thermometers_4_6x6, thermometers_5_8x8 (chains).
- Kakuro: easy kakuro_1_4x4, kakuro_2_5x5 (relations); medium kakuro_3_7x7 (relations); hard none.
- Hidato: easy hidato_1_4x4 (relations); medium hidato_2_5x5 (relations), hidato_3_6x6 (cover2); hard hidato_4_5x5, hidato_5_7x7 (chains).
- Numbrix: easy numbrix_1_4x4 (relations); medium numbrix_2_5x5, numbrix_3_6x6 (relations); hard numbrix_4_5x5, numbrix_5_6x6 (chains).
- Killer Sudoku: easy killer_1_4x4 (relations); medium killer_2_6x6 (relations), killer_3_4x4 (subsumption), killer_4_6x6 (cover2); hard killer_5_6x6 (what_if).
- Arrow Sudoku: easy arrow_1_4x4 (relations); medium arrow_2_6x6 (relations); hard arrow_3_4x4 (chains), arrow_4_6x6 (what_if).
- Even/Odd Sudoku: easy evenodd_1_4x4 (single), evenodd_2_4x4 (relations); medium evenodd_3_6x6 (relations), evenodd_4_6x6 (cover2); hard evenodd_5_9x9 (cover3).
- Sandwich Sudoku: easy sandwich_1_4x4 (single), sandwich_2_4x4 (relations); medium sandwich_3_6x6 (relations); hard sandwich_4_4x4 (chains).
- Skyscraper Sudoku: easy skyscrapersudoku_1_4x4 (relations); medium skyscrapersudoku_2_6x6 (relations); hard skyscrapersudoku_3_6x6 (what_if).

Most visible gaps: Tectonic/Suguru, counts-only Battleships and logic grids;
Kakurasu has easy and medium but no hard example. The 8×8 Suguru file is
intentionally excluded; a harder example needs stronger deduction or generation.

## Rule-focused examples

- Battleships: five boards, medium `count`/`subsumption` to hard `chains`, never `what_if`; three 8×8 boards exercise every player symbol.
- Calcudoku: six boards with no single-cell cages; two 4×4 `relations`, two 6×6 (`relations`, `cover2`), one 7×7 `cover3`, one 6×6 `what_if`.
- Newer families: Mosaic and Dominosa reach `cover3`/`chains`; Magnets `cover3` on 6×6; Towers mostly `relations`; Rectangles hard boards come from `puzzle-lab fresh rectangles --tier hard`; Undead and Pattern have no board between `relations` and `what_if`; Map has no medium board because its pairwise `AT_MOST_ONE` rules jump from `single` to `chains`. Relation-only boards of 16 or fewer variables rate easy.
- Thermometers reaches `chains`; Kakuro stops at `relations`; Hidato/Numbrix reach `chains`; Even/Odd reaches `cover3`, Killer `cover2`, Arrow and Sandwich `chains`, Skyscraper `relations`.

## Existing families

- Sudoku: Every row, column and box holds each digit once (jigsaw, NRC and X variants change the boxes). Examples: sudoku_1_4x4, easy, pointing, naked/hidden pairs, X-Wing, Swordfish, chains, Jigsaw, NRC, X-Sudoku.
- Calcudoku: No repeats in a row or column; each cage's digits combine to its target with its operation. Examples: 4×4 easy, 6×6 medium/hard/fiendish, and 7×7 hard.
- Futoshiki: No repeats in a row or column; every inequality sign between neighbouring cells holds. Examples: 5×5 with no givens and eight inequality signs.
- Towers: Each height once per row and column; an edge clue counts the visible towers. Examples: 4×4 to 6×6, relations and chains.
- Mosaic: Colour cells black or white; a number counts the black cells in its 3×3 window. Examples: 5×5 to 8×8, count to cover3.
- Dominosa: Cover the grid with dominoes, every pair of numbers used once. Examples: 5×6 to 7×8, single to chains.
- Rectangles: Divide the grid into rectangles, each with one number equal to its area. Examples: 5×5 to 14×14, single to chains.
- Magnets: Each domino is a magnet or neutral; line counts per pole; touching poles differ. Examples: 4×4 and 6×6, relations to cover3.
- Undead: Monsters in every empty cell, counted along sight lines that bend at mirrors. Examples: 4×4 (four boards) and 5×5, relations and what_if.
- Pattern: Fill cells to match the run lengths of each row and column. Examples: 4×4 to 12×12, relations and what_if.
- Map: Four-colour the regions so neighbours differ. Examples: 6×6 to 12×12, single and chains.

The graded Sudoku and Calcudoku examples are generated; newspaper puzzles are
not copied. `prrrdoku1-3` are based on the owner's Dutch documents, adjusted to
preserve the intended solution and late reveal. Private scan transcriptions are
excluded.

## Known gaps and frontier

Known gaps: no medium Map board; hard Undead and Pattern are beyond deduction.
15 of the 194 published puzzles sit there — `binairo_3_4x4`, `tango_4_4x4`,
`tents_3_4x4`, `calcudoku_6_6x6`, `undead_6_5x5`, `pattern_4_10x10`,
`killer_5_6x6`, `arrow_4_6x6`, `skyscrapersudoku_3_6x6`, `food-murdoku-3`,
`menu-murdoku-3`, `prrrdoku2`, `prrrdoku3`, `tamagotchi-murdoku-9x9` and
`tamagotchi-murdoku-12x12`. `puzzle-lab rate` reports them as
`deductive: false`; the web index badges them, and a test pins the list.

## External corpora and benchmark

`uv run python -m benchmark.fetch --source all` downloads Sudoku corpora into the
ignored `benchmark/.cache/`; `--count` and `--bucket none|group|rating` sample,
`--force` refetches, and `manifest.json` records hashes and seeds. Puzzle data is
test input, never content. `sudoku-extreme` rates with a backtracking count; this
ladder tracks only the easy block and saturates above, so `bench.py` correlates
over the puzzles it solved and states how many it omitted. See `benchmark/`.
`uv run python benchmark/families.py --runs 3 --seed 42` measures parse, load,
deduction and brute-force times for the listed examples and stops on disagreement.
