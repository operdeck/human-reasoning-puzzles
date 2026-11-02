# Puzzle collection and grading

Browse and play every published puzzle in the
[web puzzle index](https://operdeck.github.io/human-reasoning-puzzles/).
Its representative group thumbnails, category sections, sizes, and deduction grades
replace the former documentation gallery. This guide keeps the authoring,
collection, and grading notes; the index is the visual inventory.

The checked-in example files are original, generated, or owner-authored. Published Sudoku, newspaper, and book puzzles are not transcribed here. Every tracked example is checked for a unique brute-force solution, engine agreement, and per-step soundness by the test suite.

`puzzle-lab audit` applies difficulty-order checks to every series without
category exemptions. *Wie doet het met wie* currently reports an ordering
conflict: puzzle 1 needs `cover2`, while puzzles 2 and 3 need `subsumption`.
Its existing story numbering is retained; the audit reports the conflict
rather than hiding it. This does not change the shared web/booklet display
order: Murdoku still comes first, with Demo leading its categories.

## Quick commands

```bash
uv run csp examples/sudoku_1_4x4.txt
uv run csp examples/queens_6_4x4.txt --show-model
uv run csp examples/demo/murdoku_1_first_case.txt --explain
uv run csp examples/logicgrid_1_3x3.txt --brute-force
uv run csp examples/akari_1_6x6.txt --png
```

For each family example below, add `--png FILE.png` to write the puzzle image and a solved image named `FILE-solution.png`.

## First Murdoku case

Four people are placed on a 4 × 4 floor plan with three rooms. Trees, bushes, tables, and cabinets block cells; chairs and a bed are standable. The clues put Ingrid on a chair, Joost next to the tree, and Lotte on the bed. Wouter, the victim, occupies the last free square and is alone with Ingrid in the sitting room. The Dutch series also has a distinct 4 × 4 garden-party puzzle: [`wie-doet-het-met-wie-2.txt`](../examples/wie-doet-het-met-wie/wie-doet-het-met-wie-2.txt).

Murdoku examples live in category folders under `examples/` (for example `japanese-food/`, `dierentuin/`, `tamagotchi/`); the folder name is the category shown in the web player and the booklet, which groups and numbers the puzzles in a fixed order. Test-only puzzles live in `tests/puzzles/`. The files [`murdoku_1_first_case.txt`](../examples/demo/murdoku_1_first_case.txt), [`murdoku_3_house.txt`](../examples/demo/murdoku_3_house.txt), [`murdoku_sparse_mystery.txt`](../tests/puzzles/murdoku_sparse_mystery.txt), [`murdoku_global_counts.txt`](../tests/puzzles/murdoku_global_counts.txt), [`murdoku_composition.txt`](../tests/puzzles/murdoku_composition.txt), and [`murdoku_2_point_objects.txt`](../examples/demo/murdoku_2_point_objects.txt) cover the core clue syntax, relation reasoning, roles, global counts, composition of board features, and objects on grid points. The three Tamagotchi puzzles [`tamagotchi-murdoku-6x6.txt`](../examples/tamagotchi/tamagotchi-murdoku-6x6.txt) (simple, grade `relations`), [`tamagotchi-murdoku-9x9.txt`](../examples/tamagotchi/tamagotchi-murdoku-9x9.txt) (medium, grade `cover2`, with a stream and a bridge) and [`tamagotchi-murdoku-12x12.txt`](../examples/tamagotchi/tamagotchi-murdoku-12x12.txt) (hard, needs `what_if`) are original late-reveal cases: the devil Akumatchi has no clues of his own, is placed last, and is alone with exactly one friend. The three Japanese-food puzzles [`food-murdoku-2.txt`](../examples/japanese-food/food-murdoku-2.txt) (5×5, grade `chains`), [`food-murdoku-1.txt`](../examples/japanese-food/food-murdoku-1.txt) (6×6, `subsumption`) and [`food-murdoku-3.txt`](../examples/japanese-food/food-murdoku-3.txt) (7×7, needs `what_if`) use Japanese dishes as suspects and Japanese cities as areas. The three Dutch zoo puzzles [`zoo-murdoku-1.txt`](../examples/dierentuin/zoo-murdoku-1.txt) (5×5, grade `relations`), [`zoo-murdoku-2.txt`](../examples/dierentuin/zoo-murdoku-2.txt) (6×6, `subsumption`) and [`zoo-murdoku-3.txt`](../examples/dierentuin/zoo-murdoku-3.txt) (6×6, `cover2`) put animals in biomes with matching objects and colours. The three Dutch menu puzzles [`menu-murdoku-1.txt`](../examples/weekmenu/menu-murdoku-1.txt) (6×6, grade `relations`), [`menu-murdoku-2.txt`](../examples/weekmenu/menu-murdoku-2.txt) (7×7, `subsumption`) and [`menu-murdoku-3.txt`](../examples/weekmenu/menu-murdoku-3.txt) (8×8, needs `what_if`) put foods on the days of the week, with sunflowers and ornamental onions on grid points; the vla has no clues of its own and shares its day with exactly two other foods (`alone_with Vla 2`). The Dutch series *Wie doet het met wie?* starts with [`wie-doet-het-met-wie-1.txt`](../examples/wie-doet-het-met-wie/wie-doet-het-met-wie-1.txt) (5×5 sleepover, grade `cover2`): three bathrobes and three pairs of slippers lie at fixed squares, global counts say two guests stand on a bathrobe and one on slippers, and the clue "one bathrobe wearer is exactly one row above the slippers wearer" (`above object:badjas object:sloffen 1`) is needed to find who. It continues with [`wie-doet-het-met-wie-2.txt`](../examples/wie-doet-het-met-wie/wie-doet-het-met-wie-2.txt) (4×4 garden party, `subsumption`), [`wie-doet-het-met-wie-3.txt`](../examples/wie-doet-het-met-wie/wie-doet-het-met-wie-3.txt) (5×5 beach with sunglasses, `subsumption`), [`wie-doet-het-met-wie-4.txt`](../examples/wie-doet-het-met-wie/wie-doet-het-met-wie-4.txt) (6×6 house with a standable 2×2 double bed and glasses, `cover2`) and [`wie-doet-het-met-wie-5.txt`](../examples/wie-doet-het-met-wie/wie-doet-het-met-wie-5.txt) (7×7 hotel, `cover2`, where Wouter's partner wears a bathrobe: `alone_with Wouter object:badjas`). Every puzzle in the series puts bathrobes, slippers and (from the beach on) glasses on fixed squares, gives the number of wearers as rules, and needs a garment clue to find who wears what. Wouter has no clues, is placed last and is alone with exactly one other person (`alone_with Wouter`). The owner-authored Dutch puzzles are [`prrrdoku1.txt`](../examples/prrrdoku/prrrdoku1.txt), [`prrrdoku2.txt`](../examples/prrrdoku/prrrdoku2.txt), and [`prrrdoku3.txt`](../examples/prrrdoku/prrrdoku3.txt). The Dutch series *Moord in de Oriënt Express* puts the suspects in a train and on its platforms: [`murdoku_orient_express.txt`](../examples/murder-in-the-orient-express/murdoku_orient_express.txt) (8×8, grade `relations`), [`murdoku_orient_express_2.txt`](../examples/murder-in-the-orient-express/murdoku_orient_express_2.txt) (10×10 with a restaurant car, `subsumption`) and [`murdoku_orient_express_3.txt`](../examples/murder-in-the-orient-express/murdoku_orient_express_3.txt) (10×10, `chains`). On the 10×10 boards a row of rails (nobody can stand there) separates each platform from the train, and gangplanks lead to the doors. No clue names the murderer: the rules fix their sex, the crime scene and whether they were alone there, and the murderer is the last suspect left.

## Murder Hotel

The English Murder Hotel trilogy gives the guests Italian names and moves the mystery through the roof terrace, restaurant, guest rooms, and lobby. Each board has a guest corridor with doors into the room wings, a main staircase connecting the Lobby, guest corridor, and Restaurant, and a one-column lift along the east side that stops only at the Lobby and Restaurant. A street-side vestibule opens into the Lobby. The first two puzzles use a conventional crime-scene mystery; the final puzzle leaves the murderer as a separate role and asks the solver to identify the guest at the deduced position. Its body is at the base of the lift shaft. The 8×8 opener is grade `relations`; the 9×9 and 10×10 puzzles are grade `subsumption`. See [`murder-hotel-1.txt`](../examples/murder-hotel/murder-hotel-1.txt), [`murder-hotel-2.txt`](../examples/murder-hotel/murder-hotel-2.txt), and [`murder-hotel-3.txt`](../examples/murder-hotel/murder-hotel-3.txt).

## Halloween at the Museum

The English Halloween at the Museum series sets three costume-party murders in one museum, with a Spanish cast and painter rooms (Velázquez, Goya, El Greco) next to the armoury, the Egyptian and dinosaur halls and the gift shop. Every puzzle shares one rule: the murderer was in the room where the weapon lies. Each puzzle narrows the suspects with a trait (a woman, a guest in costume, a member of staff), and the murderer appears in no clue. The cursed dagger (6×6) and the crossbow (7×7) are grade `subsumption`; the candlestick (8×8) is grade `cover2`. See [`halloween-museum-1.txt`](../examples/halloween-museum/halloween-museum-1.txt), [`halloween-museum-2.txt`](../examples/halloween-museum/halloween-museum-2.txt), and [`halloween-museum-3.txt`](../examples/halloween-museum/halloween-museum-3.txt).

## Verified non-Murdoku difficulty examples

These tiers come from `puzzle-lab search examples --tier <easy|medium|hard>`.
Every listed file is deductively solved by the repository solver and has a
unique solution under independent search. The tier is an estimate for this
solver, not a universal measure of human difficulty. `—` marks a coverage gap:
the current generator/rule ladder has not produced a trustworthy example for
that family and tier, so no candidate is promoted by hand. Binairo and Tango
are listed separately because Tango adds relation signs. Cosmetic piece
changes do not create another family or gallery section.

| Puzzle type | Easy | Medium | Hard |
|---|---|---|---|
| Sudoku | [`sudoku_5_9x9.txt`](../examples/sudoku_5_9x9.txt) (`single`) | [`sudoku_13_9x9_naked_pair.txt`](../examples/sudoku_13_9x9_naked_pair.txt) (`cover2`) | [`sudoku_17_9x9_chains.txt`](../examples/sudoku_17_9x9_chains.txt) (`chains`) |
| Calcudoku | [`calcudoku_1_4x4.txt`](../examples/calcudoku_1_4x4.txt) (`relations`) | [`calcudoku_3_6x6.txt`](../examples/calcudoku_3_6x6.txt) (`relations`) | [`calcudoku_5_7x7.txt`](../examples/calcudoku_5_7x7.txt) (`cover3`) |
| Futoshiki | [`futoshiki_1_5x5.txt`](../examples/futoshiki_1_5x5.txt) (`single`) | [`futoshiki_2_5x5.txt`](../examples/futoshiki_2_5x5.txt) (`relations`) | [`futoshiki_3_5x5.txt`](../examples/futoshiki_3_5x5.txt) (`chains`) |
| Tectonic / Suguru | [`suguru_1_4x4.txt`](../examples/suguru_1_4x4.txt) (`single`) | — | [`suguru_2_8x8.txt`](../examples/suguru_2_8x8.txt) (`chains`) |
| Queens / Star Battle | Queens: [`queens_1_4x4.txt`](../examples/queens_1_4x4.txt), [`queens_2_5x5.txt`](../examples/queens_2_5x5.txt) (`single`); Star Battle: [`starbattle_1_8x8.txt`](../examples/starbattle_1_8x8.txt) (`count`) | Queens: [`queens_3_7x7.txt`](../examples/queens_3_7x7.txt), [`queens_4_8x8.txt`](../examples/queens_4_8x8.txt) (`subsumption`), [`queens_5_9x9.txt`](../examples/queens_5_9x9.txt) (`cover2`); Star Battle: [`starbattle_2_8x8.txt`](../examples/starbattle_2_8x8.txt) (`cover2`) | Queens: [`queens_6_4x4.txt`](../examples/queens_6_4x4.txt) (`chains`); Star Battle: [`starbattle_3_12x12.txt`](../examples/starbattle_3_12x12.txt) (`cover3`) |
| Zebra logic grid | [`logicgrid_1_3x3.txt`](../examples/logicgrid_1_3x3.txt) (`relations`) | [`logicgrid_2_6x6.txt`](../examples/logicgrid_2_6x6.txt) (`relations`) | — |
| Binairo / Takuzu | [`binairo_1_8x8.txt`](../examples/binairo_1_8x8.txt) (`relations`) | [`binairo_2_8x8.txt`](../examples/binairo_2_8x8.txt) (`subsumption`) | [`binairo_3_4x4.txt`](../examples/binairo_3_4x4.txt) (`what_if`) |
| Tango | [`tango_1_8x8.txt`](../examples/tango_1_8x8.txt) (`relations`) | [`tango_4_8x8.txt`](../examples/tango_4_8x8.txt) (`relations`) | [`tango_5_4x4.txt`](../examples/tango_5_4x4.txt) (`what_if`) |
| Tents and Trees | [`tents_1_8x8.txt`](../examples/tents_1_8x8.txt) (`single`) | [`tents_2_8x8.txt`](../examples/tents_2_8x8.txt) (`cover2`) | [`tents_3_4x4.txt`](../examples/tents_3_4x4.txt) (`what_if`) |
| Minesweeper-style | — | [`minesweeper_1_8x8.txt`](../examples/minesweeper_1_8x8.txt) (`subsumption`) | [`minesweeper_4_8x8.txt`](../examples/minesweeper_4_8x8.txt) (`cover3`) |
| Light Up / Akari | — | [`akari_1_6x6.txt`](../examples/akari_1_6x6.txt) (`subsumption`) | [`akari_2_8x8.txt`](../examples/akari_2_8x8.txt) (`chains`) |
| Kakurasu | [`kakurasu_1_4x4.txt`](../examples/kakurasu_1_4x4.txt) (`relations`) | [`kakurasu_2_8x8.txt`](../examples/kakurasu_2_8x8.txt) (`relations`) | — |
| Battleships | — | [`battleships_1_6x6_fleet.txt`](../examples/battleships_1_6x6_fleet.txt), [`battleships_2_8x8_fleet.txt`](../examples/battleships_2_8x8_fleet.txt) (`count`); [`battleships_3_8x8_fleet.txt`](../examples/battleships_3_8x8_fleet.txt) (`subsumption`) | [`battleships_4_8x8_fleet.txt`](../examples/battleships_4_8x8_fleet.txt), [`battleships_5_8x8_fleet.txt`](../examples/battleships_5_8x8_fleet.txt) (`chains`) |
| Towers | [`towers_1_4x4.txt`](../examples/towers_1_4x4.txt) (`relations`) | [`towers_2_5x5.txt`](../examples/towers_2_5x5.txt), [`towers_3_6x6.txt`](../examples/towers_3_6x6.txt) (`relations`) | [`towers_4_5x5.txt`](../examples/towers_4_5x5.txt) (`chains`) |
| Mosaic | [`mosaic_1_5x5.txt`](../examples/mosaic_1_5x5.txt) (`count`) | [`mosaic_2_5x5.txt`](../examples/mosaic_2_5x5.txt) (`subsumption`), [`mosaic_3_6x6.txt`](../examples/mosaic_3_6x6.txt) (`cover2`) | [`mosaic_4_8x8.txt`](../examples/mosaic_4_8x8.txt) (`cover3`) |
| Dominosa | [`dominosa_1_5x6.txt`](../examples/dominosa_1_5x6.txt) (`single`) | [`dominosa_2_6x7.txt`](../examples/dominosa_2_6x7.txt) (`subsumption`), [`dominosa_3_7x8.txt`](../examples/dominosa_3_7x8.txt) (`cover2`) | [`dominosa_4_6x7.txt`](../examples/dominosa_4_6x7.txt) (`cover3`), [`dominosa_5_7x8.txt`](../examples/dominosa_5_7x8.txt) (`chains`) |
| Rectangles | [`rectangles_1_5x5.txt`](../examples/rectangles_1_5x5.txt), [`rectangles_2_9x9.txt`](../examples/rectangles_2_9x9.txt) (`single`) | [`rectangles_3_9x9.txt`](../examples/rectangles_3_9x9.txt), [`rectangles_4_14x14.txt`](../examples/rectangles_4_14x14.txt) (`subsumption`) | — |
| Magnets | [`magnets_1_4x4.txt`](../examples/magnets_1_4x4.txt) (`relations`) | [`magnets_2_6x6.txt`](../examples/magnets_2_6x6.txt) (`relations`), [`magnets_3_6x6.txt`](../examples/magnets_3_6x6.txt) (`cover2`) | [`magnets_4_6x6.txt`](../examples/magnets_4_6x6.txt) (`cover3`) |
| Undead | [`undead_1_4x4.txt`](../examples/undead_1_4x4.txt) (`relations`) | [`undead_2_5x5.txt`](../examples/undead_2_5x5.txt) (`relations`) | [`undead_3_5x5.txt`](../examples/undead_3_5x5.txt) (`what_if`) |
| Pattern (nonogram) | [`pattern_1_4x4.txt`](../examples/pattern_1_4x4.txt) (`relations`) | [`pattern_2_8x8.txt`](../examples/pattern_2_8x8.txt), [`pattern_3_12x12.txt`](../examples/pattern_3_12x12.txt) (`relations`) | [`pattern_4_10x10.txt`](../examples/pattern_4_10x10.txt) (`what_if`) |
| Map (four colouring) | [`map_1_6x6.txt`](../examples/map_1_6x6.txt), [`map_2_9x9.txt`](../examples/map_2_9x9.txt) (`single`) | — | [`map_3_9x9.txt`](../examples/map_3_9x9.txt), [`map_4_12x12.txt`](../examples/map_4_12x12.txt) (`chains`) |

The most visible gaps are Tectonic/Suguru, counts-only Battleships, Kakurasu,
and logic grids. In particular, the existing 8 × 8 Suguru file is
trivial, and is intentionally excluded. These gaps require stronger
family-specific deduction or generation support before a harder human-like
example can be claimed.

## The newer families: what the ladder reaches

Towers, Mosaic, Dominosa, Rectangles, Magnets, Undead, Pattern and Map were added
without changing `core.py`. Each file shows the rungs its boards exercise; a rule
that never fires on a family's boards is not claimed. Measured with
`puzzle-lab sweep` over several hundred fresh boards per family:

- **Mosaic and Dominosa** reach the whole ladder, from `single` or `count` up to
  `cover3` and `chains`, and so do their hard boards, without `what_if`.
- **Magnets** reaches `cover3` on 6 × 6 boards; larger boards tend to be unique but beyond
  the ladder, so none ship.
- **Towers** is relation-checked: each clue is propagated on its own line, so 4 × 4 boards
  are easy and 5 × 5 and 6 × 6 boards are `relations`. A `chains` board turns up in about
  one of a hundred 5 × 5 boards; the rest of the hard boards close only with `what_if`.
- **Undead and Pattern** have no board between `relations` and `what_if` in the sweeps, so
  their hard boards (`undead_3_5x5`, `pattern_4_10x10`) are beyond deduction and flagged.
- **Rectangles** has no hard board: random partitions of 5 × 5 to 16 × 16 grids reach only
  `single` and `subsumption`, even when the builder moves numbers about to leave more
  candidate rectangles. **Map** has no medium board: its boards need `single` or jump to
  `chains`. These two cells are marked `—` and are not filled by hand.
- Relation-only boards of 16 or fewer variables rate easy, as for Kakurasu and Tango, so
  the 4 × 4 boards of Towers, Magnets, Undead and Pattern are easy even though their grade
  is `relations`.

Every one-star Queens region has at least two cells. The easy 4 × 4 and 5 × 5 and the
medium 9 × 9 have one visible given queen each; the other three boards have
no givens. The starter queens are explicit clues, not single-cell regions
that silently give away a placement.

## Rule-focused examples

The five Battleships boards progress from medium (`count`, then `subsumption`)
to hard (`chains`), without `what_if`. Three 8×8 boards demonstrate every
symbol described by the player rules: *Buoys in the channel* (medium, seed
1510), *Broken radio signals* (medium, seed 1513), and *Fogbound convoy* (hard,
seed 1511). Each includes water waves, an unspecified `?` segment, a single-cell
circle, rounded ends, and square middles. They retain only 7–8 givens on 64
cells, have independently verified unique solutions, and still need fleet
rules. Explicit water includes a cell outside zero-total rows and columns.
Adding these boards renumbered the existing *Open-water search* from
`battleships_2_8x8_fleet.txt` to `battleships_4_8x8_fleet.txt`; its board and
grade are unchanged.

The six Calcudoku examples contain no single-cell cages. All cages are
connected and have at least two cells; each board has one independently
verified solution. The sequence retains two easy 4 × 4s (`relations`),
a medium 6 × 6 (`relations`), a medium 6 × 6 (`cover2`), a hard 7 × 7
(`cover3`) and a fiendish 6 × 6 (`what_if`). The last fallback remains
reserved for that explicitly fiendish example. Legacy files with one-cell
cages remain playable: their target digits must be entered, not silently
locked as invisible givens.

`what_if` is the ladder's fallback, so the examples that need it are exactly the
ones no deduction path closes: this collection's beyond-deduction frontier.
11 of the 128 published puzzles sit there — `binairo_3_4x4`, `tango_5_4x4`,
`tents_3_4x4`, `calcudoku_6_6x6`, `undead_3_5x5`, `pattern_4_10x10`,
`food-murdoku-3`, `menu-murdoku-3`, `prrrdoku2`, `prrrdoku3` and
`tamagotchi-murdoku-12x12`. `puzzle-lab rate`
reports them as `deductive: false`, the web index and puzzle pages badge them,
and a test pins the list, which only moves when the ladder does.

The standard Sudoku set exercises `single`, `subsumption`, `cover2`, `cover3`, and `chains`. The one-star Queens display progresses from `single` through `subsumption` and `cover2` to `chains`; the multi-star Star Battle examples have irregular regions and grade `cover2` (8 × 8, two stars), `chains` (10 × 10, two stars) and `cover3` (12 × 12, three stars), and a two-star board cannot be smaller than 8 × 8, nor a three-star board smaller than 12 × 12; the logic grids and weighted Kakurasu examples exercise `relations`; the count-oriented examples exercise `count`. Run `--grade` for the exact grade of any individual example.

| Family | Small example | Larger example |
|---|---|---|
| Sudoku relations | `sudoku_9_4x4_kropki_consecutive_thermometers.txt` | `sudoku_7_9x9_kropki_consecutive_thermometers.txt` |
| Anti-knight Sudoku | `sudoku_2_4x4_anti_knight.txt` | `sudoku_3_9x9_anti_knight.txt` |
| Anti-king Sudoku | `sudoku_16_6x6_anti_king.txt` | `sudoku_4_9x9_anti_king.txt` |
| Tectonic / Suguru | `suguru_1_4x4.txt` | `suguru_2_8x8.txt` |
| Queens / Star Battle | Queens (`Stars: 1`): `queens_1_4x4.txt`, `queens_2_5x5.txt`, `queens_6_4x4.txt`; Star Battle: `starbattle_2_8x8.txt` | Queens: `queens_3_7x7.txt`, `queens_4_8x8.txt`, `queens_5_9x9.txt`; Star Battle: `starbattle_4_10x10.txt`, `starbattle_3_12x12.txt` |
| Zebra-style logic grids | `logicgrid_1_3x3.txt` | `logicgrid_2_6x6.txt` |
| Binairo / Takuzu | `binairo_3_4x4.txt` | `binairo_2_8x8.txt` |
| Tango | `tango_2_4x4.txt` | `tango_4_8x8.txt` |
| Tents and Trees | `tents_3_4x4.txt` | `tents_1_8x8.txt` |
| Minesweeper-style | `minesweeper_2_5x5.txt` | `minesweeper_3_8x8.txt` |
| Light Up / Akari | `akari_1_6x6.txt` | `akari_2_8x8.txt` |
| Kakurasu | `kakurasu_1_4x4.txt` | `kakurasu_2_8x8.txt` |
| Battleships | `battleships_1_6x6_fleet.txt` | `battleships_2_8x8_fleet.txt`, `battleships_3_8x8_fleet.txt`, `battleships_4_8x8_fleet.txt`, `battleships_5_8x8_fleet.txt` |
| Towers | `towers_1_4x4.txt` | `towers_3_6x6.txt` |
| Mosaic | `mosaic_1_5x5.txt` | `mosaic_4_8x8.txt` |
| Dominosa | `dominosa_1_5x6.txt` | `dominosa_5_7x8.txt` |
| Rectangles | `rectangles_1_5x5.txt` | `rectangles_4_14x14.txt` |
| Magnets | `magnets_1_4x4.txt` | `magnets_4_6x6.txt` |
| Undead | `undead_1_4x4.txt` | `undead_3_5x5.txt` |
| Pattern (nonogram) | `pattern_1_4x4.txt` | `pattern_3_12x12.txt` |
| Map (four colouring) | `map_1_6x6.txt` | `map_4_12x12.txt` |

## Existing families

| Puzzle | Rules | Example coverage |
|---|---|---|
| Sudoku | Every row, column and box holds each digit once (jigsaw, NRC and X variants change the boxes). | `sudoku_1_4x4`, easy, pointing, naked/hidden pairs, X-Wing, Swordfish, chains, Jigsaw, NRC, X-Sudoku |
| Calcudoku | No repeats in a row or column; each cage's digits combine to its target with its operation. | 4×4 easy, 6×6 medium/hard/fiendish, and 7×7 hard |
| Futoshiki | No repeats in a row or column; every inequality sign between neighbouring cells holds. | 5×5 with no givens and eight inequality signs |
| Towers | Each height once per row and column; an edge clue counts the visible towers. | 4×4 to 6×6, `relations` and `chains` |
| Mosaic | Colour cells black or white; a number counts the black cells in its 3×3 window. | 5×5 to 8×8, `count` to `cover3` |
| Dominosa | Cover the grid with dominoes, every pair of numbers used once. | 5×6 to 7×8, `single` to `chains` |
| Rectangles | Divide the grid into rectangles, each with one number equal to its area. | 5×5 to 14×14, `single` and `subsumption` |
| Magnets | Each domino is a magnet or neutral; line counts per pole; touching poles differ. | 4×4 and 6×6, `relations` to `cover3` |
| Undead | Monsters in every empty cell, counted along sight lines that bend at mirrors. | 4×4 and 5×5, `relations` and `what_if` |
| Pattern | Fill cells to match the run lengths of each row and column. | 4×4 to 12×12, `relations` and `what_if` |
| Map | Four-colour the regions so neighbours differ. | 6×6 to 12×12, `single` and `chains` |
| Murdoku | Place each person on a free square, at most one per row and column, so all clues hold; the murderer is alone with the victim. | `murdoku_1_first_case`, `wie-doet-het-met-wie-1/2/3/4/5`, `murdoku_3_house`, `murdoku_sparse_mystery`, `murdoku_global_counts`, `murdoku_composition`, `food-murdoku-2/2/3`, `zoo-murdoku-1/2/3`, `tamagotchi-murdoku-6x6/9x9/12x12`, and owner-authored `prrrdoku1-3` |

The graded Sudoku and Calcudoku examples are generated; newspaper puzzles are not copied. `prrrdoku1-3` are based on the owner's Dutch puzzle documents, with adjustments to preserve the intended solution and late reveal. Private screenshot transcriptions are excluded from this repository.

## External corpora

Published Sudoku collections arrive through `uv run python -m benchmark.fetch
--source all` (or one source by name), which downloads into `benchmark/.cache/`
and samples from there. Puzzle data is test input, never content: the cache is
git-ignored, and only code is committed.

| Source | Puzzles | Solutions | Own rating |
|---|---|---|---|
| `norvig` | 156 (easy50, top95, hardest) | derived with the brute force | no |
| `sudoku-extreme` | 400 000+ (`sapientinc` on Hugging Face) | shipped | yes |

`--count` sets rows per bucket and `--bucket none|group|rating` spreads a sample
over the dataset's own grouping instead of taking whatever comes first. A row is
dropped and counted when its answer contradicts its own givens, or when it has
no answer and the brute force finds no unique one, so a broken row never reads
as a solver failure. `manifest.json` records every URL, byte size, sha256 and
UTC time, and every sample says which file hashes, bucket, size and seed built
it; a sample already on disk is reused until `--force` (proving the hardest of
Norvig's puzzles unique takes the brute force minutes, once).

### Ranking alignment

`sudoku-extreme` rates every puzzle with a backtracking count, median 17 over
its 422 786 rows, 26% of them at rating <= 3. That is where the ladder stops: on
a 500-puzzle sample from the whole source it solves 128 of the 131 puzzles rated
0 to 3, 5 of the 126 rated 4 to 16, and none of the 243 rated 17 or over. Its
grade so tracks the source's rating across the easy block and saturates above
it, and counting every rated row mostly measures how much easy material a sample
happens to hold: +0.69 on that draw, but +0.15 on one spread evenly over the
rating scale (`--bucket rating --count 2`, 482 puzzles, 9 solved). The cap moves
it as well, because `timeout` is the last grade in `grades_for`: that even sample
reports +0.39 at `--timeout 5` and +0.15 at `--timeout 30`, since more puzzles
land in the strongest grade. So `bench.py` correlates over the puzzles it solved
and says how many it left out; on the 133 solved of that 500 that reads grade
+0.90, `iterations` +0.77, ms +0.84, where counting the rest in reads as
`iterations` -0.55 because a puzzle that gives up early spends little.
Validating the grade as a human-scale rater needs puzzles inside the ladder's
own reach, which this corpus mostly is not.

## Cross-family benchmark

`uv run python benchmark/families.py --runs 3 --seed 42` measures parser, CLI load/compile, deduction solve, and independent brute-force times for every listed small/larger family example. The seed shuffles execution order; the checked-in, unique example files are fixed. The benchmark stops if an example is no longer unique or the engine disagrees with brute force.
