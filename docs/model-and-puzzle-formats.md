# Model and Puzzle File Formats

This guide describes the solver's generic model, the rule ladder, and the file formats accepted by each puzzle family. Browse the [visual puzzle index](https://operdeck.github.io/human-reasoning-puzzles/) or read the [collection and grading notes](puzzle-collection.md).

## Generic model

The engine in [`src/csp/core.py`](../src/csp/core.py) knows only literals, constraints, relations, and generic deduction rules. A puzzle module parses its family format and compiles it to these primitives. No puzzle-family logic belongs in `core.py`.

- **Literal:** a named variable takes a value, such as `r3c4=7`, `a=r1c1`, or `r2c3=True`.
- **Variable:** a domain represented by an `EXACTLY_ONE` constraint. The solver reports the selected value when known.
- **`EXACTLY_ONE`:** exactly one listed literal is true.
- **`AT_MOST_ONE`:** zero or one listed literal is true. It never forces one to be true.
- **`COUNT`:** the number of true literals belongs to `allowed_counts`; a reifier is true exactly when the count is allowed.
- **Relation:** a predicate over the values of two or more named variables. Relations are checked by generalized arc consistency.

The distinction between `EXACTLY_ONE` and `AT_MOST_ONE` is essential: sparse boards leave cells empty. The solver records every deduction with its rule and supporting constraints or relations; proof replay and narration use that record without adding family knowledge to the engine.

## Deduction rules

The solver applies these rules cheapest-first and restarts at the first rule that changes the model:

| Rule | Meaning |
|---|---|
| `single` | Force the last option in an `EXACTLY_ONE` constraint, or the only literal forced by a `COUNT` with one feasible total. |
| `count` | Propagate allowed count totals, including bounds, gaps, parity, reified counts, whole variables confined to the counted literals, and shared capacity between disjoint scopes of one family. |
| `relations` | Generalized arc consistency: remove a value if no combination of the other variables' values supports it. |
| `subsumption` | Use the remaining capacity of an outer constraint when an inner constraint requires another true literal. |
| `cover2`, `cover3` | Combine disjoint inner constraints whose guaranteed demand fills an outer constraint's remaining capacity. |
| `chains` | Follow strong/weak links from counts and two-variable relations; a contradiction or paired weak links can eliminate a value. |
| `wing` | A three-option pivot and two two-option helpers force their shared value into one of them, so any option linked "not both true" to all three is false (Sudoku's XYZ-Wing). |
| `what_if` | On a model copy, assume a value and run only `single`, `count`, `relations`, and `subsumption`; a contradiction proves the assumption false. |

`--grade` reports the hardest rule actually used, or `unsolved` if the deduction ladder stalls. It is a measure of this solver's deductions, not a universal human difficulty rating. Because `what_if` is the ladder's last rung, a grade below it also proves that rung never fired: the same ladder without it finishes the puzzle. `report.beyond_deduction` and the `deductive` field that `puzzle-lab` and the web export carry are that distinction, `false` exactly for puzzles no deduction path closes — the collection's beyond-deduction frontier.

## Family mappings

| Family | Variables | Generic constraints and relations |
|---|---|---|
| Sudoku | Cell | One digit per cell; each digit exactly once per row, column, box, and extra house. Optional variants add generic relations or at-most-one peer pairs. |
| Calcudoku | Cell | Sudoku rows/columns plus one arithmetic relation per cage. |
| Futoshiki | Cell | Latin-square rows/columns plus one order relation per sign. |
| Murdoku | Person | One square per person; at most one person per square, row, and column; clue predicates are relations/counts. |
| Tectonic / Suguru | Cell | Domain 1 through the size of its region; each value exactly once per region; equal values at most once in every eight-neighbor pair. |
| Queens / Star Battle | Region for one star; cell for multiple stars | One star: one cell per region, row, and column, with at most one queen per 2×2 window. Multiple stars: Boolean star/empty cells, exact counts per row, column, and region, and at most one star per 2×2 window. One star uses the Queens name and queen piece. |
| Zebra logic grid | Item | Each item chooses one position; each category has exactly one item per position; pair clues are relations. |
| Binairo / Tango | Cell | Boolean cell; half of each value per row/column; no three equal in a window; all rows and columns differ. Tango adds equal/different relations. |
| Tents and Trees | Cell | Boolean tent/empty; row/column counts; exactly one orthogonal tent neighbor per tree; tents do not touch, including diagonally. |
| Minesweeper-style | Cell | Boolean mine/safe; each numbered cell counts mines in its eight-neighbor set; optional total mine count. |
| Light Up / Akari | Cell | Boolean bulb/empty; visibility counts, numbered-wall counts, and at-most-one bulb per line of sight. |
| Kakurasu | Cell | Boolean filled/empty; weighted row and column sums encoded as generic relations over the line cells. |
| Battleships | Cell, hidden ship positions | Occupied-cell row/column counts, a fleet count per length, water-or-one-straight-ship coverage, and no touching between ships (including diagonals). |
| Towers | Cell | Latin-square rows/columns plus one relation per edge clue over its line in view order (`visible(heights) == clue`). |
| Mosaic | Cell | Boolean black/white; one `COUNT` per numbered cell over its 3×3 window, the cell itself included. |
| Dominosa | Domino type | One variable per domino, whose values are the edges with matching numbers; exactly one edge per type and exactly one covering literal per cell. |
| Rectangles | Numbered cell | One variable per number, whose values are the rectangles of that area containing it and no other number; exactly one covering literal per cell. |
| Magnets | Cell | Three values (`+`, `-`, `0`); a legal-pair relation per domino, `COUNT` per line and pole, `AT_MOST_ONE` for touching equal poles of different dominoes. |
| Undead | Empty cell | Three values (ghost, vampire, zombie); a `COUNT` per monster kind and one relation per border clue over the cells of its mirrored sight line. |
| Pattern | Cell | Boolean filled/empty; one relation per row and column comparing its runs to the clue. |
| Map | Region | Four colours per region; `AT_MOST_ONE` per border and colour. |
| Thermometers | Cell | Boolean filled/empty; a filled-prefix relation per thermometer and a `COUNT` per row and column. |
| Kakuro | White cell | Digits 1 to 9; one relation per run: distinct digits that add up to the clue. |
| Hidato / Numbrix | Number | One variable per number, whose values are the open cells; exactly one cell per number and one number per cell; consecutive numbers are a two-variable adjacency relation (corners count for Hidato only). |
| Killer, Arrow, Even/Odd, Sandwich and Skyscraper Sudoku | Cell | Sudoku exact cover plus one relation per variant rule over its cells (`sudoku.Rule`): a cage's distinct sum, an arrow's sum, a digit's parity, the digits between the 1 and the top digit, or how many digits are seen from an edge. |

The new-family formats below currently use `COUNT`, `AT_MOST_ONE`, `EXACTLY_ONE`, and generic relations. Binairo/Tango row and column uniqueness uses bounded-arity auxiliary relations; performance on larger boards is part of the example and benchmark checks. Kakurasu's weighted equations currently use generic relations rather than a new weighted core constraint.

## Sudoku and variants

Plain Sudoku accepts a 4×4 or 9×9 grid; `.` and `0` are blanks, and visual `|`/`-` separators are ignored. A sectioned puzzle puts the grid under `Givens:` and may add `Boxes:` and `Extra:`:

```text
Givens:
. . . .
. . . .
. . . .
. . . .
Boxes:       # optional jigsaw region ID per cell
 a a b b
 a c b b
 c c d d
 c c d d
Extra:       # optional extra-house IDs per cell; '.' means none
 x . . y
 . x y .
 . y x .
 y . . x
```

A jigsaw requires N boxes of N cells. Each extra house has N cells. `Extra:` expresses X-Sudoku diagonals, NRC boxes, and other overlapping houses.

The booklet (`--docx`/`--pdf`) and web rules panel describe every active Sudoku
variant from the parsed puzzle, in its `Language:` (`en` by default, or `nl`).
This includes nonstandard boxes, extra houses, anti-knight/anti-king rules,
Kropki dots, consecutive-pair bars, and thermometers. Missing Kropki dots impose
no restriction: only drawn dots constrain pairs. Name all active variants in the
example's file name and `Title:` so players can identify the rules before playing.

`--explain` groups singles and describes recognized locked candidates, naked
and hidden sets, and row/column patterns in English or Dutch. It shortens and
replays the proof before wording it. When a step such as a chain or variant
relation has no pattern narrative, it stops explicitly with a nonzero exit
status; `--verbose` still shows the technical trace.

Optional relation/peer sections are:

```text
Kropki:
white r1c1 r1c2
black r1c2 r2c2
Consecutive:
r2c1 r2c2
Thermometers:
r1c1 r2c1 r2c2
AntiKnight:
AntiKing:
```

- White Kropki dots require a difference of one; black dots require one value to be twice the other. Consecutive pairs require a difference of one.
- Thermometer paths list cells from bulb to tip. Consecutive cells in the path are orthogonal neighbors, and values strictly increase along the path.
- `AntiKnight:` and `AntiKing:` are enabled by section presence. Equal digits are forbidden for cells a knight move apart or a king move apart, respectively; overlaps with existing houses do not create duplicate constraints.

## Region-grid formats

Queens and Star Battle share one region-grid family and format; Suguru/Tectonic uses the same basic region-grid shape:

```text
Family: starbattle
Size: 4
Stars: 1
Regions:
a: amber
b: blue
c: coral
d: green
Grid:
a a a b
a b b b
c c c c
d d d d
```

`Grid:` contains one declared region ID per cell. The family validates its own region count and size requirements. Examples in `examples/` are the executable specifications.

### Queens and Star Battle

`Family: starbattle` is the canonical family and requires `Stars:` to state how many pieces go in each row, column, and region. With `Stars: 1`, the puzzle is presented as **Queens**, with a queen icon and the rule text "Place one queen in every row, column and region; queens may not touch, not even diagonally." With `Stars: 2` or more it is presented as **Star Battle**, with a star icon. Pieces may not touch, including diagonally; unlike a chess queen, nothing reaches further than one step.

`Family: queens` remains a compatibility alias for `Family: starbattle` with one star. Old Queens givens written as `region rNcN` are accepted; new files use the `Stars:` count and matrix `Givens:` (`?` unknown, `.` empty, `*` a piece). There must be N connected regions on an N×N board, each large enough to hold its star count. Region colours are shared by both displays.

Published and freshly generated one-star Queens boards have at least two
cells per region: a one-cell region gives away its queen. The easy boards and
the 9x9 use one explicit given queen each; the 7x7, 8x8 and hard 4x4 have no
givens. `puzzle-lab fresh starbattle --stars 1 --tier easy` makes one-star
Queens; the compatibility command `fresh queens` uses the same generator.
The hard board needs chains, not the `what_if` step formerly stated in its
comment. All examples are independently unique; the collection audit compares
solutions together with their region maps.

### Tectonic / Suguru

`Family:` is `suguru` or the alias `tectonic`. Add an optional N×N `Givens:` section of `.` or values. A cell's domain is 1 through the size of its region; each value appears once in that region, and equal values may not occupy cells that touch by side or corner.

## Zebra-style logic grids

A logic grid has no spatial board. Each category lists N distinct items; every item chooses one position from 1 through N, and each category uses every position exactly once:

```text
Family: logicgrid
Size: 3
Categories:
resident: Ada Ben Cal
color: red blue green
pet: cat dog fox
Clues:
same Ada red
left_of dog green
next_to Ben fox
```

Supported relation words are `same`, `different`, `left_of`, `before`, and `next_to`. `left_of`/`before` mean an earlier position; `next_to` means consecutive positions. Every clue names items from different or the same declared categories, as allowed by the relation.

## Binary grids

Binairo/Takuzu and Tango use an even board size from 4 through 16. `Givens:` is an N×N grid of `.`, `0`, and `1`. Each row and column has equal numbers of 0 and 1, contains no run of three equal values, and is distinct from every other row/column. Tango adds neighboring-cell signs:

```text
Family: tango
Size: 4
Givens:
. . . .
. . . .
. . . .
. . . .
Equal:
r1c1 r1c2
Different:
r2c2 r3c2
```

Sign cell pairs must be orthogonal neighbors. The unique-line encoding uses existing generic relations; larger examples benchmark its cost.

## Count and placement grids

### Tents and Trees

`Trees:` is an N×N grid of `.` and `T`. `RowCounts:` and `ColumnCounts:` each contain N non-negative counts, whose totals must equal the tree count. Every tree has exactly one orthogonally adjacent tent; tents are not on trees and may not touch each other, including diagonally. A tent is eligible only if it is orthogonally adjacent to exactly one tree, making tree pairing one-to-one.

### Minesweeper-style

`Clues:` is an N×N grid; `.` is a hidden cell and `0`–`8` is a safe numbered cell. The number counts mines in all in-bounds neighbors, including diagonals. Optional `TotalMines:` gives the total mine count.

### Light Up / Akari

`Family:` is `akari` or the alias `lightup`. `Grid:` uses `.` for floor, `W` for an unnumbered wall, and `0`–`4` for a numbered wall. Bulbs light every floor cell along its row/column until a wall; bulbs cannot see one another. Numbered walls count orthogonally adjacent bulbs.

### Kakurasu

`RowSums:` and `ColumnSums:` each contain N weighted totals. A filled cell in column c contributes c to its row sum; a filled cell in row r contributes r to its column sum. Optional `Givens:` uses `.`, `0`, and `1`. The current compiler expresses weighted line equations as generic relations; it does not add weighted propagation to `core.py`. For original boards, use `puzzle-lab fresh kakurasu --size 8 --tier medium --seed 226 --output /tmp/kakurasu.txt`. Reject puzzles where each row and column sum independently fixes its line: those need no interaction between clues.

### Battleships

`RowCounts:` and `ColumnCounts:` each contain N occupied-cell counts. `Fleet:`
lists one length per ship, including repeats (for example `3 2 2 1 1 1` on
6x6). The fleet's total must match both line totals. Ships are straight,
horizontal or vertical, and different ships may not touch, even diagonally.
The compiler uses hidden Boolean ship positions, generic fleet counts,
water-or-one-ship coverage, and at-most-one constraints for each ship's water
border; no family-specific deduction is added to the engine.

Optional `Givens:` is an NxN grid: `.` unknown, `0` water, `1` unspecified
occupied segment, `O` a single-cell ship, `N`/`S`/`E`/`W` the end pointing
towards water in that compass direction, and `M` an interior segment with
ship cells on two opposite sides. An unspecified `1` is drawn as a question mark,
so it cannot be confused with a middle segment. Shaped givens require a fleet. Puzzle and
solution images show the fleet below the board and use rounded ship ends.
English/Dutch rules for both web and DOCX/PDF are derived from the parsed fleet.
`--explain` tells the solution by the puzzle rules that drive each step. Brute force checks connected components independently of the compiler.

Files without `Fleet:` remain supported as explicitly counts-only puzzles,
using only `.`, `0`, `1`; no ship shapes or no-touching rules are implied.
The gallery uses full-fleet puzzles. Its tests reject full staircase totals,
require a unique nontrivial solution, and check that fleet rules affect the answer.

### Towers (Skyscrapers)

`Family:` is `towers` or the alias `skyscrapers`. `Size:` is 3 to 7. `Top:`, `Bottom:`, `Left:` and `Right:` each hold N numbers, one per column (top, bottom) or row (left, right), `.` for no clue: how many towers are visible looking along that line, where a taller tower hides every shorter one behind it. Optional `Givens:` is an N×N grid of heights and `.`. The relation of a clue lists its cells in the order the viewer sees them. Relations are checked by enumerating combinations of a line's options, which is cheap up to 6×6 and slow at 7×7, so the gallery stays at 6×6 or smaller.

```text
Family: towers
Size: 4
Top:
1 2 4 2
Bottom:
4 2 1 2
Left:
1 2 3 .
Right:
2 3 1 2
```

### Mosaic

`Size:` is 3 to 15 and `Clues:` is an N×N grid of digits 0–9 and `.`. A number counts the black cells in the 3×3 window around it, including its own cell; the numbered cell itself may be black or white. Boards are square.

### Dominosa

`Numbers:` is a grid of N+1 rows and N+2 columns of numbers 0..N, N from 1 to 6 (no `Size:`). Cover the grid with dominoes so every pair {0-0, 0-1, …, N-N} is used exactly once. Only the numbers are given; the compiler builds one variable per domino type. Pictures print each number as that many pips on a 3×3 lattice, the way a domino stone does, so a 0 is a blank half; the pips sit above the solution's ivory stones, so a solved board looks like real dominoes. In the web player each cell is marked as the left, right, top or bottom half of its domino.

### Rectangles (Shikaku)

`Family:` is `rectangles` or `shikaku`. `Clues:` is a rectangular grid (2 to 16 on a side) of numbers and `.`. The numbers must add up to the number of cells. Each rectangle holds exactly one number, equal to its area. In the web player each number has its own coloured tile, and a cell is painted with the tile of the rectangle that contains it.

### Magnets

`Size:` is even, 4 to 10. `Dominoes:` is an N×N grid of ids, each appearing exactly twice in two touching cells (the board is pre-divided into dominoes). `PlusTop:` and `PlusLeft:` give the number of `+` cells in each column and row, `MinusBottom:` and `MinusRight:` the number of `-` cells, `.` for no clue. A domino is a magnet (one `+`, one `-`) or neutral (two `0`), and touching cells of different dominoes never share a pole. Optional `Givens:` uses `+`, `-`, `0` and `.`.

### Undead

`Grid:` is a rectangular grid (2 to 8 on a side) of `.` (a monster), `/` and `\` (mirrors). `Counts:` gives the number of ghosts, vampires and zombies, which must add up to the number of `.` cells. `Top:`, `Bottom:`, `Left:` and `Right:` give, for each border cell, how many monsters are seen looking into the grid along that row or column, the line bending at every mirror. Zombies are always seen, vampires only before the line meets a mirror and ghosts only after it has. A line that crosses a cell twice counts it each time. The visibility rule is `undead.seen`, called by both the compiler and the brute force, which walk the mirrors separately.

### Pattern (nonogram)

`Family:` is `pattern` or the aliases `nonogram` and `picross`. `Rows:` has one line per row and `Columns:` one per column, each a list of run lengths (`0` for an empty line). The board may be rectangular, up to 15 on a side, because the run relation costs time exponential in the line length.

### Map (four colouring)

`Regions:` is a rectangular grid of region ids (2 to 12 on a side); each id forms one connected area, and regions touch where cells share a side (corners do not count). `Givens:` lines have the form `<region> <colour>` with the colours `red`, `yellow`, `green` and `blue`. Colours are labelled, so a unique answer needs enough givens to fix the colour symmetry. The module is `mapcolour`, so it never shadows the builtin `map`.

### Thermometers

`Size:` is 3 to 10. `Thermometers:` has one line per thermometer, a path of touching cells with its bulb first (`r1c1 r2c1 r3c1`); together they cover every cell exactly once. `Rows:` and `Columns:` give how many cells of each line are filled. Mercury rises from the bulb without gaps, so a thermometer's filled cells are a prefix of its path. Optional `Givens:` uses `.`, `0` and `1`. Not to be confused with the thermometers of Sudoku (see below), which only order digits.

### Kakuro

`Grid:` is a rectangle of tokens: `.` is a white cell, `X` a black cell without clues, and `down\across` a clue cell with either number left out (`16\`, `\7`, `4\6`). A clue covers the run of white cells below it (down) or to its right (across), up to the next non-white cell. Runs are 2 to 5 cells, every white cell must lie in a run, and a run holds distinct digits that add up to its sum. Runs are relations over their cells, so long runs are slow; the gallery stays at four cells or fewer per run.

### Hidato and Numbrix

`Family:` is `hidato` (neighbours touch along a side or at a corner) or `numbrix` (along a side only). `Grid:` is a rectangle of `.` (open), `X` (blocked, because a leading `#` would read as a comment) and given numbers. The open cells are numbered 1 to K so that every number touches the next; the compiler's variables are the numbers, and the web player offers the numbers 1 to K as its palette.

### Killer, Arrow, Even/Odd, Sandwich and Skyscraper Sudoku

These are Sudoku files (`Givens:`, optionally `Boxes:` for a 6×6 jigsaw) with one more family name and the variant's sections; they have their own sections in the web index and booklet but share the Sudoku parser, compiler and brute force. Each section becomes `sudoku.Rule`s, written once and read by compiler, brute force and pictures.

| `Family:` | Sections | Rule |
|---|---|---|
| `killer` | `Killer:` lines `13: r1c1 r1c2 r2c1` | A cage of 2 to 4 cells holds different digits adding up to the number. |
| `arrow` | `Arrows:` lines `r1c1 r1c2 r2c3` | The first cell (the circle) equals the sum of the 2 or 3 cells that follow, a path of touching cells. |
| `evenodd` | `Parity:` grid of `e`, `o`, `.` | The digit in a marked cell is even or odd. |
| `sandwich` | `SandwichRows:`, `SandwichColumns:` | The digits between the 1 and the highest digit of the line add up to the clue. |
| `skyscrapersudoku` | `SkyscraperTop:`, `SkyscraperBottom:`, `SkyscraperLeft:`, `SkyscraperRight:` | The clue counts the digits seen from that edge, a taller digit hiding every shorter one behind it. |

`.` means no clue in the clue lines. Sandwich and Skyscraper lines are relations over a whole row or column, which is only practical up to 6×6, so larger grids with those sections are rejected. The others also work on 9×9.

## Murdoku

Murdoku uses named sections: `Size:`, `Regions:`, `Grid:`, and `People:` are required. Optional sections include `Rules:`, numbered `Clues:`, `AreaTags:`, `Objects:`, `EdgeItems:`, `PointObjects:`, `Marks:`, `Roles:`, `RoleEligibility:`, `Attributes:`, `Pronouns:`, `Hatched:`, `Backdrop:`, and `Words:`. `Backdrop:` names one icon (a catalogue name or `U+XXXX`) drawn large and faint behind the board, reaching a little past it; it is decoration only and never changes the puzzle. Original backdrops such as `lapjeskat` (a tortoiseshell cat), `ramen_bowl` and `tamagotchi` stick out above the board (ears, steam, a key ring); the picture grows to make room. On a booklet page too full for it the backdrop is left out. `Decorations:` lines such as `bat: r0.5c3.5 r6.5c1` draw small icons at point-object anchors (half steps, also on the board edge); unlike `PointObjects:` they are pictures only: no clue can name them and the legend and object lists leave them out. See [`tests/puzzles/murdoku_composition.txt`](../tests/puzzles/murdoku_composition.txt) for a neutral composition and the grammar specification below.

Every object footprint must be declared `blocking` or `standable`; its name/icon never determines occupancy. Doors list two side-sharing cells in different areas. Windows list one inside cell. Point objects sit on a grid point given as a half-step anchor such as `fountain: r2.5c2.5`: whole numbers are cell centres and `.5` values grid lines, with `0.5` and `N+0.5` the outer edges. An interior vertex touches four cells, a vertex on the outer edge or the middle of an inner cell side two, and a board corner or the middle of an outer cell side one. A cell centre or a point off the board is an error. See [`examples/demo/murdoku_2_point_objects.txt`](../examples/demo/murdoku_2_point_objects.txt). Marks overlap freely and do not occupy cells. Roles overlap unless explicitly constrained. Attributes are fixed person facts.

### Clue grammar specification for #238

This section specifies the canonical grammar. The reader accepts canonical
forms only; the migration table below documents how legacy forms were mapped
and is not an alternate accepted syntax. `Rules:` and `Clues:` use the same
predicates.

#### Selectors and predicate shape

A bare name is a person from `People:`. Every other target has an explicit
namespace. A list of same-kind selectors means their union for location
predicates and counts where a list is accepted. Unknown names, namespaces,
and incompatible selector types are errors.

| Selector | Selects |
|---|---|
| `person:name`, `people:name1,name2`, `people:any` | One named person, a named set of people, or everyone. |
| `attribute:name`, `role:name` | People with the fixed attribute or assigned role. |
| `people_on:location-selector` | People occupying cells selected by a location selector, e.g. `people_on:object:bench`; use this when a relation must compare occupants rather than cells. |
| `area:name`, `tag:name` | Cells or logical areas in one named region / one area tag. |
| `object:name`, `object_kind:blocking\|standable` | Cells of named objects or all objects of one occupancy kind. |
| `edge_item:name`, `point_object:name`, `mark:name` | Cells touched by an edge item, point object, or named mark. |
| `rows:1,3-5`, `columns:2-4` | The listed one-based rows or columns. |
| `corner:board`, `corner:area:name` | Board corners or right-angle corners of the named logical area. |
| `adjacent_to:name`, `adjacent_to:tag:name` | Logical areas sharing a side with the named area or any area in the named tag. The source area/set is excluded; corner contact does not count. |

Use `in`, `on`, `beside`, and `touches` for location predicates. `in` tests
membership in a region, tag, line, or selected cell set; `on` tests whether a
person occupies a selected cell. `beside` means sharing a side within the same
logical area. `touches` means sharing a side regardless of area boundary,
including within one area. Neither adjacency predicate includes diagonals.
Because an object's selected cells form one target set, a person on one cell
of a multi-cell object can be beside another cell of that object. `not`
negates one predicate, as in `not in Ada area:river` or
`not touches Ada mark:water`. `same Ada Ben` means both occupy the same
logical area; `not same` negates it. `only Ada on object:bench` means Ada
occupies one of the selected cells and no other person occupies any of them.

Pair relations use `dir A B <mode> [comparison]`. Person selectors
(`person:`, `people:`, `attribute:`, `role:`, and `people_on:`) select people;
location selectors (`area:`, `tag:`, `object:`, `object_kind:`, `edge_item:`,
`point_object:`, `mark:`, `rows:`, `columns:`, `corner:`, and `adjacent_to:`)
select cells. A person selector is compared by the selected people's
positions; if both endpoints select people, the relation is existential over
distinct people. A location selector is compared directly by its selected
cells. Thus a named person can be compared with a location, and two locations
can be compared without implying that anyone occupies them. Use
`people_on:<location-selector>` when a relation concerns the people standing
on selected cells. Each mode succeeds when a selected endpoint pair meets it.
The `areas` mode compares the logical areas of the selected positions or
cells. Role and attribute selectors are valid at either endpoint.
The accepted modes and bounds are:

| Mode | Meaning and accepted comparison |
|---|---|
| `left`, `right`, `up`, `down` | Unbounded direction, or an exact positive gap: `= n`, `n >= 1`. |
| `rows`, `cols` | Absolute row/column difference with `= n`, `<= n`, or `>= n`; `n >= 1`. `rows_apart` / `columns_apart` map to `>=`; `within_rows` / `within_columns` map to `<=`. These are per-axis bounds, not an either-axis disjunction. |
| `manhattan` | Manhattan distance with `= n`, `<= n`, or `>= n`; `n >= 0`. |
| `euclidean` | Straight-line distance between cell centres ("as the crow flies"; Dutch: "in vogelvlucht") with `= n`, `<= n`, or `>= n`; `n >= 0` is an integer threshold. Compare squared distances to `n²`, without rounding. |
| `king` | Chebyshev distance with `= n`, `<= n`, or `>= n`; `n >= 0`. `king >= 2` excludes the same, side-adjacent, and diagonal-adjacent cells. |
| `areas` | Shortest side-sharing border distance between logical areas with `= n`, `<= n`, or `>= n`; `n >= 0`. Same area is distance 0. |
| `knight` | Exactly one chess-knight move; no comparison. |
| `furthest` | For person endpoints only, the first is strictly farther from the second than every other person is by Manhattan distance; no comparison. |

For `euclidean`, positions four columns and three rows apart have distance
exactly 5. Non-integer distances are not rounded; an equality with an integer
matches only when the straight-line distance is that integer. The `areas`
mode is limited to shortest border distance between Murdoku's logical areas;
it does not add general path or connectivity clues.

Examples:

```text
in Ada area:gang
on Ada object:bench
beside Ada object:bench
touches Ada mark:water
dir Ada Ben left
dir Ada Ben left = 2
not dir Ada Ben left
dir Ada Ben rows >= 3
dir Ada Ben cols <= 2
dir Ada Ben manhattan >= 4
dir Ada Ben euclidean = 5
dir Ada Ben king >= 2
dir Ada Ben areas = 1
dir role:thief Ada up
dir people_on:object:robe people_on:object:slippers up = 1
dir Ada Ben knight
dir Ada Ben furthest
```

#### Counts, occupancy, and role constraints

Count comparisons are `= n`, `<= n`, `>= n`, `odd`, `even`, or inclusive
`low..high`; integers are non-negative and a comparison with no feasible
value for its selector is an error. `count people on` counts occupants of
object, object-kind, edge-item, point-object, or mark cells. `count people in`
counts people in a location selector's cells, optionally narrowed by a
`role:` or `attribute:` selector. `count people with` counts people with one
role or attribute, and `count people from` restricts the count to an explicit
person set. Scope selectors after `in` can be intersected with `and`, for
example a tag and an `adjacent_to:` selector. Empty-cell counts include only
free cells. The canonical forms are:

```text
count people on object:coat = 2
count people in area:library = 2
count people with role:guard = 1
count people in area:library with role:guard >= 1
count people from people:Ada,Ben with attribute:trained = 1
count roles of Ada <= 1
count empty areas all = 2
count occupied areas all >= 3
count occupied areas in tag:villages >= 3
count empty areas in adjacent_to:river >= 1
count occupied areas in adjacent_to:tag:square = 2
count people in adjacent_to:river = 3
count empty areas in tag:north_bank and adjacent_to:river >= 1
count people in tag:north_bank and adjacent_to:river = 3
count empty cells in mark:quiet = 1
no_adjacent_occupied areas
no_adjacent_occupied areas in tag:villages
```

`count empty areas` retains the current behavior of counting areas with no
free cells as empty. `count occupied areas` never counts an area with no free
cells. `adjacent_to:` scopes include all distinct areas that share a side with
the source area or tag, not the source itself. The unqualified
`adjacent_to:name` form names an area; use `adjacent_to:tag:name` for a tag.
When combined with `in area:` or `in tag:`, the resulting area set is their
intersection.
`no_adjacent_occupied areas` applies to every pair of side-sharing areas in
scope: at most one area in each pair may contain people. Any number of people
may share one area; areas with no free cells are not occupied. `all` is the
default scope; with `in area:name` or `in tag:name`, check every border that
touches at least one scoped area, even when the neighboring area is outside
the scope.

Area-scoped occupancy has both area-wide and person-relative forms:

```text
alone in area:library
alone Ada in area:library
with role:guard in area:library
with Ada role:guard in area:library
with Ada role:guard in area:library exactly 2
```

`alone in area:X` requires exactly one occupant. `alone Ada in area:X`
requires Ada to occupy X and no other person to occupy X. Area-wide
`with role:Y in area:X` requires a role-Y occupant and at least one distinct
co-occupant. Person-relative `with Ada role:Y in area:X exactly n` requires
exactly `n` other occupants of X, all matching the selector; Ada must also
occupy X. `in same area` is the unscoped form. Role implications use one
conditional form, `if <atomic condition> then <atomic condition>`, rather
than a separate positional verb for every role:

```text
if has Ada role:guard then in Ada tag:villages
if has Ada role:guard then beside Ada object:gate
```

`subset selector-A selector-B` means every person matching A also matches B.
`for each area in tag:name, count people in that area with role:name >= n`
applies the minimum separately to every logical area in the tag. A role
occupancy condition is scoped to each area with a matching role holder, for
example:

```text
for each area in all occupied by role:guard, count people in that area = 1
for each area in all occupied by role:guard, count people in that area >= 2
```

A role cardinality is expressed as `count roles of Ada <comparison>`.
Conditional forms are one level deep; arbitrary nested Boolean expressions
are not part of this grammar.

`most_populated area:A [area:B ...]` and
`least_populated area:A [area:B ...]` require the named areas to tie at the
maximum or minimum. Every other usable area must be strictly less populated
or more populated, respectively. Areas with no free cells are ignored and
cannot be named.

`exactly n <atomic clue> ; <atomic clue> ...` counts how many listed atomic
clues hold. It remains bounded to three distinct people and does not accept
quantified pair relations, `only`, `with`, or another count as an operand.
Mark declarations may still end in `; alone` or `; not_alone`: when someone
occupies a marked cell, the condition applies to the logical area containing
that cell. This is a conditional occupancy property, not a clue predicate.

#### Legacy-to-canonical mapping

The migration must preserve each board's meaning, including cases where one
legacy word had different semantics for different target kinds.

| Legacy form | Canonical form |
|---|---|
| `in_region P area...`, `outside P area...` | `in P area:...`, `not in P area:...` |
| `in_tagged`, `only_in_tagged P tag...`; `not_in_tagged P tag...` | `in P tag:...`, `not in P tag:...`. `only_in_tagged` has the same membership meaning as `in_tagged`. |
| `on`, `not_on P object...` | `on P object:...`, `not on P object:...`. |
| `at P edge_item...` | `on P edge_item:...`. |
| `on_mark`, `not_on_mark P mark...` | `on P mark:...`, `not on P mark:...`. |
| `next_to`, `not_next_to P target...` | For `object`/`object_kind`, `beside` / `not beside`; for `mark`, `touches` / `not touches`; for `edge_item`/`point_object`, `on` / `not on` their touched cells. Migration resolves the old target type explicitly. |
| `away_from P target...` | `dir P target king >= 2`. |
| `knight_from P target...` | `dir P target knight`. |
| `in_corner P`, `in_area_corner P area...` | `in P corner:board`, `in P corner:area:name`. |
| `in_row` / `not_in_row`, `in_column` / `not_in_column P n` | `in P rows:n` / `not in P rows:n`, `in P columns:n` / `not in P columns:n`. |
| `same_region`, `different_region A B` | `same A B`, `not same A B`. |
| `adjacent_regions`, `apart A B` | `dir A B areas = 1`, `dir A B areas >= 2`. |
| `left_of`, `above A B [n]` | `dir A B left [= n]`, `dir A B up [= n]`. |
| `within`, `at_least A B n` | `dir A B manhattan <= n`, `dir A B manhattan >= n`. |
| `furthest A B` | `dir A B furthest`. |
| `alone P`, `alone_with P [selector] [n]` | `alone P`; `with P selector in same area exactly n`. An omitted selector becomes `people:any`; an omitted count defaults to 1. |
| `has_attribute` / `not_attribute P attribute`, `has_role` / `not_role P role` | `has P attribute:...` / `not has P attribute:...`; likewise for `role:`. |
| `unique_attribute attribute P...` | `count people from people:P... with attribute:... = 1`. |
| `some_role P`, `roleless P`, `at_most_one_role P` | `count roles of P >= 1`, `= 0`, `<= 1`. |
| `role_subset A B` | `subset selector-A selector-B`. |
| `role_in_tagged` / `role_not_in_tagged P role tag`; `role_on`, `role_not_on`, `role_next_to P role target...` | `if has P role:... then in` / `not in`, `on` / `not on`, or target-kind-specific `beside`, `touches`, or `on`. |
| `role_below P role [n]` | `dir P role:... down [= n]`. |
| `min_role_in_tagged role tag n` | `for each area in tag:..., count people in that area with role:... >= n`. |
| `sole_role_companion P role` | `with P role:... in same area exactly 1`. |
| `role_occupant role alone` / `not_alone` | For each area occupied by a holder of `role:...`, require respectively `count people in that area = 1` / `>= 2`. |
| `only_on P object...` | `only P on object:...`. |
| `busiest_area area...` / `quietest_area area...` | `most_populated area...` / `least_populated area...`. |
| `count people on|in|with ...`, `count empty areas ...`, `count empty cells ...` | Keep `count`, using the corresponding typed selectors and unified comparisons above. |
| `exactly n clue ; clue ...` | Keep the bounded `exactly` form; update each operand to the canonical atomic predicate. |
| Legacy target aliases `cells:`, `cellset:`, `row:`, `column:` | `mark:`, `rows:`, `columns:`. Bare known person names remain people; no other bare target names are accepted. |
| Bare non-person targets in location clues | Add the matching namespace, such as `area:`, `tag:`, `object:`, `mark:`, `edge_item:`, `point_object:`, `role:`, or `attribute:`. |

A relation with a selector on both sides, such as legacy
`above object:robe object:slippers 1`, becomes
`dir people_on:object:robe people_on:object:slippers up = 1` and remains
existential over distinct matching people. Unlike the legacy compiler, a role
selector is valid on either endpoint.

Legacy `Words:` overrides for `doc.clue_next_to_door`,
`doc.clue_next_to_point`, and `doc.clue_next_to_border` must be migrated to
predicate-specific wording for `on`, `beside`, or `touches`. The `| wording`
override syntax itself remains unchanged, and the final phrasebook must not
keep aliases that blur those predicates.

A window line may end with the wall it sits against, `top`, `bottom`, `left`
or `right` (for example `raam: window r3c4 top`); the picture then draws a
shallow pane along that wall instead of an icon in the middle of the square.
An object line may end with a side in the same way
(`trein_bank: standable r3c8 r4c8 r5c8 right`): a seat or bed is then drawn
with its back against that wall. These suffixes only change the picture. An
area may consist of blocking squares only, such as a strip of rails; nobody
can stand there, and `--lint` reports it.

### Booklet text (`--docx`)

In the booklet the board sits above **The figures and their clues** (Dutch:
**De figuren en hun aanwijzingen**). Every cast member appears in file order,
including figures without clues, with their portrait if available, bold name,
optional description and unnumbered clues together. Ordinary clue predicates
do not repeat the figure's heading; joint subjects and custom wording retain
names when needed. Descriptions sit in parentheses beside the name so ordinary
clues can continue on the same line. Descriptions supplied in `Figures:` are preserved, including
late-reveal information. Clues are attached by their semantic subject, not by
guessing from their wording. Loose and global clues follow under **Other clues**
(Dutch: **Overige aanwijzingen**), only when needed. Board notes explain the
marks and area tags used by the clues; attributes, roles and objects remain
separate under the board. The layout reserves space for wrapped descriptions,
clueless figures and portraits, shrinking the board or omitting its backdrop
on crowded pages. Worked solutions do not refer to clue numbers.
Booklets use A4 pages, matching the dimensions used by the page-fit estimates.
`Words:` lines whose name is a phrase key (see `PHRASES` in `story.py`) reword that phrase for the puzzle, e.g. `target.attribute: a {name}` ("... and that is a friend"), or `role_has: {who} is een {role}` / `role_not: {who} is geen {role}` when roles are really kinds such as species. A `lint` warning flags a clue already implied by another (a person put in one region and also "not in" another).

Every Murdoku booklet puzzle page and web player rules panel also reminds players
that only stated rules and clues determine what is possible: a kind or trait
matters only when a rule or clue explicitly uses it. The renderer provides this
reminder; do not repeat it in each puzzle's `Intro:`.

`--docx [FILE]` writes one editable Word document: the puzzle page(s) first, then a solutions section with the solved board and worked solution of each. Optional sections (all ignored by solving, lint and PNG; `lint` only checks them for typos):

* `Title:`, `Intro:` (blank lines separate paragraphs; wrapped lines are joined, and `**bold**` is allowed), `Question:`, `Reveal:` (answer text, solution file only). Before the first section block, `Intro: text` also works as a single paragraph.
* A clue line may end in `| wording` (e.g. `above Otto Tjitske 1 | Otto zit precies één rij boven Tjitske.`); that text replaces the generated sentence and the solver ignores it. Without it every clue is worded by `story` (en/nl), e.g. `at_least Ramen Tempura 5` → "Ramen is at least five squares from Tempura." A `Rules:` line may end in `| wording` as well; that sentence is listed with the rules (booklet, web player) and in the picture legend. Worked solutions never use author wordings.
* `Figures:` lines `Name: description [; image=path] [; icon=name]`. A figure gets a small thumbnail from, in order: the `image=` file (relative to the puzzle file); a file named after the person (`Name.png`/`.jpg`) in `<puzzle>-figures/` or `figures/` beside the puzzle; or the built-in emoji `icon=` (a catalogue name or `U+1F35C` whose picture is vendored in `src/csp/assets/emoji/`; `--lint` warns otherwise). Without any of these it is text only. Put licensed artwork in the figures folder; the only bundled third-party images are the vendored Noto Emoji (see `src/csp/assets/NOTICE.md`).

Pass a glob (quoted) such as `"examples/**/*.txt"` to put every matching puzzle in one booklet (`booklet.docx` beside the pattern by default), each on its own numbered page, after a clickable table of contents. The order comes from `collection.arrange`: Murdoku first, grouped by category — the folder below the matched files' common folder, so `examples/japanese-food/` is "Japanese food" and `demo` leads — then the other families; within a group files sort naturally (`6x6` before `12x12`). The web player's index uses the same numbers and sections.

Puzzles of other families (sudoku, starbattle, tents, …) are included generically: title (`Title:` or the file name), the family rules (including every active Sudoku variant), the board, and on a separate solution page the solved board with solving steps. Sudoku uses the pattern narrative when it can explain the entire solution; otherwise it labels the capped technical placement trace as a fallback. A mixed glob such as `"examples/**/*.txt"` therefore works.

Needs `uv sync --extra docx` (python-docx, plus fonttools and resvg for the pictures).

`--nosolution` with `--docx` or `--pdf` writes the puzzle pages only: it skips the
solver, so a booklet can be proof-read quickly, or made from a puzzle whose rules
do not close, without the solutions section and without the solved board. The
same flag skips solving for console, PNG and SVG output, including interactive
SVGs. It does not delete any previously written solution file. `--show-model`
and `--lint` remain available; solving options and `--export` cannot be combined
with `--nosolution`, because web bundles contain the answer for checking.

In the Murdoku picture, blocked squares are shaded clearly darker than their region (standable objects keep the region colour), and area tags (for example `noble_areas`) are named in the legend. Objects that a global `count` clue counts get one faded blue dashed ring each; the ring is drawn only for object counts, not for whole-area, line or empty-area counts, and it is not repeated in a static key.

## Other existing formats

- **Calcudoku:** `Size:`, `Grid:` cage IDs, and `Cages:` arithmetic targets/operators. Cages must be connected; subtraction and division are two-cell cages.
  Single-cell cages remain valid input, but their targets are clues, not hidden
  prefilled digits: the web player lets the user enter their values normally.
  Every cell must be filled for Check to report a solved puzzle.
  Published examples and Puzzle Lab generation use cages of at least two
  cells. Fresh generation merges stranded single cells into touching cages
  and derives new arithmetic targets from the solution. Seed variations do
  the same and may change operations, never add one-cell hint cages.
- **Futoshiki:** `Grid:` givens/dots plus `Signs:` lines such as `r1c4 < r2c4`; signs join orthogonally adjacent cells.
- **Sudoku:** see the earlier section. Plain format is a grid; variants use sectioned `Givens:`, `Boxes:`, and `Extra:`.

## CLI and validation

The type is detected from the file's sections; `--type` overrides it. `--show-model`, `--verbose`, `--step`, `--grade`, `--brute-force`, `--svg`, and `--png` use the same generic engine for every family. `--explain` supports every family (Murdoku and Sudoku have their own narrators, the rest use `generic_story`); `--track-person`, `--lint`, and `--require-forward` are Murdoku-specific.

```bash
uv run csp examples/<family-example>.txt --show-model
uv run csp examples/<family-example>.txt --brute-force
uv run csp examples/<family-example>.txt --grade
uv run csp examples/<family-example>.txt --svg board.svg
uv run csp examples/<family-example>.txt --png board.png
uv run puzzle-lab rate examples/<family-example>.txt --json
uv run puzzle-lab search examples --family tango --tier hard
uv run puzzle-lab search examples --tier hard --deductive
uv run puzzle-lab audit examples
uv run puzzle-lab generate examples/tents_1_8x8.txt --tier medium \
  --seed 42 --attempts 100 --output /tmp/tents-medium.txt
uv run puzzle-lab fresh tango --size 8 --tier medium --open-share 0.6 \
  --seed 26 --output /tmp/tango-medium.txt
```

`puzzle-lab` is the repository-native non-Murdoku authoring tool. It rates a
puzzle only when the deductive solver completes it and independent search
confirms a unique solution; `search` applies the same checks across files.
`generate` searches reproducible family-aware variants and refuses to write a
candidate that misses the requested tier; it keeps the seed's solution.
Both `generate` and `fresh` accept optional `--grade` for exact technique
coverage as well as a tier, for example `--tier hard --grade cover3`.
If no candidate matches both requirements, they fail without writing a file.
`search` reports every rated puzzle's `deductive` field — whether the ladder
closes it without `what_if` — and `--deductive` keeps only the ones it does.
`fresh` builds a brand-new board and solution for Binairo, Tango, Suguru,
Minesweeper, Akari, Sudoku, Futoshiki, Calcudoku, Kakurasu, Star Battle
(including the one-star Queens presentation), and Tents, then removes givens
while the solution stays unique. Battleships
builds a non-touching fleet on 4x4, 6x6, 8x8 or 10x10, derives its line totals,
and removes shaped givens while the answer stays unique.
Use `--stars 1` for the Queens presentation, or `--stars 2` (the default on
boards of size 8 and larger) for a multi-star Star Battle.
Boards with under a quarter of their cells open rate `trivial`. `audit`
reports examples that share a solution or a layout (up to rotation,
reflection and renamed regions) and gallery sections that are not listed from
easier to harder. Tiers are estimates tied to this
solver's rule ladder, not universal human-difficulty guarantees. Report gaps
where a family's current solver cannot support a trustworthy tier. Murdoku
continues to use its separate tools and skill.

For a new family, add a parser/compiler, an independent backtracker in `src/csp/bruteforce/`, CLI and kind registration, a renderer (pieces as `icons.REGISTRY` entries) and picture test, small and larger unique examples, example soundness coverage, README/AGENT/skill documentation, and a line in the module-layer test. Use existing generic primitives; a new engine constraint requires a separate design issue.

## Source layout

```text
src/csp/
	core.py        generic literals, constraints, relations, rules, and solver
	puzzlefile.py  section reader and automatic family detection
	regiongrid.py  shared named-region grid reader
	<family>.py    one parser/compiler/text renderer per family
	bruteforce/    independent search implementation per family
	svg.py         SVG canvas, text as paths, PNG rasterising (resvg)
	icons.py       icon registry, Murdoku object catalogue, Unicode fallbacks
	picture.py     SVG pictures for every family
	assets/        vendored Noto Emoji SVGs and Noto Sans subset (NOTICE.md)
	docx_export.py Word booklet pages for Murdoku (optional python-docx)
	cli.py         family dispatch and shared solver options
tests/           engine, family, soundness, layering, and picture tests
examples/        small and larger unique examples for each family
benchmark/       seeded, external-corpus and cross-family benchmark programs
```

The project verification commands are:

```bash
uv run pytest -q
uvx ruff check src tests benchmark
uvx ruff format --check src tests benchmark
uv run mypy src
```

Continuous integration runs the same gates on Python 3.12 and 3.13. The tests check brute-force uniqueness for every example, engine agreement, and every logged placement/elimination against the independent solution. An unsupported narrative, such as a Sudoku chain explanation, does not imply the solver is incorrect.

Pictures have one renderer: `picture.py` draws every family on an `svg.Canvas`, and every other format derives from it. `--svg [FILE]` writes it (needs `uv sync --extra svg` for fonttools, which turns text into paths from the bundled Noto Sans subset, so output does not depend on installed fonts); `--png [FILE]` rasterises it with resvg (`uv sync --extra png`, no system libraries); `--docx` embeds the PNG. Each has three variants: blank, solution (the `-solution` file), and with `--svg --interactive` the blank board with a transparent `<rect id="r<row>c<col>" class="cell">` over every cell (r1c1 top left) for an app to fill in; the interactive variant never writes a solution picture.

### Web bundles (`--export`)

Peer groups may include a localized `description` of the rule they implement.
The generic player uses these groups to explain conflicting placements or pencil
marks by naming the other occupied cell, without consulting the hidden solution.
It still allows mistakes; this feedback does not reject or correct placements.
Players can disable this feedback with the Warnings toggle beside Auto-mark.
Warnings default to on, including for previously saved games; each puzzle saves
the choice independently of auto-mark, and clearing the board preserves it.

`--export DIR` writes, per puzzle, `<stem>.svg` (the interactive board) and `<stem>.json`, plus `DIR/index.json` (`schema`, `license`, and one entry per puzzle with `id`, `number`, `section`, `title`, `family`, `familyLabel`, `size`, `grade`, `deductive`, `playable`, in reading order). `number` and `section` (bundles carry them too) come from `collection.arrange`, as in the booklet. A bundle holds `size` `[rows, cols]`; `palette` (items with `id`, `label`, `symbol`, optional `svg` and `description`); `placement` (`perItem` or `perCell`, and `blocked` cells); `autoMark` (`default`, `mark` — `cross` or, for Akari, `light` — and `onPlace` scopes: `row`, `col`, `region`, `neighbors4`, `neighbors8`, `king`, `knight`, `peers`, each optionally `whenFull: n`); `regions` when a scope needs them; `peers`, the groups of cells that hold a palette item at most once (each `cells`, plus `items` when it binds only some items), read by `web.peers()` from the model's at-most-one and exactly-one constraints, so the player needs no family rules for them; `notes: true` when the player offers pencil marks (digit families); `givens` and `solution` (cell id to palette id); and the reading text: `rules`, `clues`, `key` (`name`, `text`: the door/window/point symbols), `question`, `reveal` (the booklet's `Reveal:` text, which the player shows after "Solved!" or "Opgelost!"), `headings`, `attributes`, `roles`, `language`, `license`. `deductive` is `false` exactly for the puzzles no deduction path closes — the ones graded `what_if` — so an app can flag the beyond-deduction frontier. Families the player cannot yet play have `playable: false` and an `unsupported` reason. Murdoku `key` lists only the board symbols whose meaning is not in the rules; marks, roles, attributes, area tags and the dashed count ring are stated in the rules, listed separately or drawn on the board, and the picture legend underneath a booklet board is the same compact key. The player draws the same grey cross over a palette item that `placement.perItem: 1` shows as already on the board, but only while auto-mark is on; items that may appear more than once (`placement.perCell` boards such as Minesweeper or Star Battle) are never crossed.

Each Murdoku `key` entry also includes the corresponding board symbol as `svg`. If windows with one name use both wall panes and separate icons, the key shows both.

Pieces come from the icon registry in `icons.py`: each `Icon` has a name, a Unicode `symbol` used by the text boards (★ star, ▲ tent, ♣ tree, ✱ mine, ● bulb, ■ wall/shaded, ●/○ Binairo) and either an original vector shape or a vendored Noto Emoji. Murdoku objects and figure `icon=` names are looked up in `icons.CATALOGUE` (Dutch names plus English synonyms, or `U+<code>`); unknown or unvendored icons fall back to a text label and `--lint` warns. All artwork is vendored under `src/csp/assets/` at pinned commits with its licences (`NOTICE.md`); rendering never uses the network. To add a picture, add the name to `CATALOGUE` and run `uv run python scripts/vendor_emoji.py U+<code>`; `scripts/subset_font.py` rebuilds the font subset.

## Further engine work

Some proposed families remain conditional on generic-core design work. Weighted sums may need a generic primitive if relations are not practical; this is tracked separately from Kakurasu. Reusing chain links could improve large-board performance but is an optimization, not a prerequisite for families expressed by existing primitives. Connectivity, path, and run-length puzzles need separate designs for generic constraints.

Other solver/documentation roadmap items are tracked as [DOCX generation #28](https://github.com/operdeck/human-reasoning-puzzles/issues/28), [weighted-sum support #46](https://github.com/operdeck/human-reasoning-puzzles/issues/46), [chain-link reuse #47](https://github.com/operdeck/human-reasoning-puzzles/issues/47), [large Calcudoku cages #50](https://github.com/operdeck/human-reasoning-puzzles/issues/50), [higher-arity weak links #51](https://github.com/operdeck/human-reasoning-puzzles/issues/51), [advanced covers #52](https://github.com/operdeck/human-reasoning-puzzles/issues/52), and [hybrid search #53](https://github.com/operdeck/human-reasoning-puzzles/issues/53). Plain-language clue interpretation remains an authoring-assistant task; the solver does not parse natural-language clues.
