# Human Reasoning Puzzles

**An explainable constraint solver for many kinds of logic puzzles.**

Murdoku, Sudoku, Calcudoku/KenKen, Futoshiki, Queens-style, Tectonic/Suguru, Star Battle, Zebra logic grids, binary puzzles, and count-based grids all compile to one generic constraint engine.

## Quick start

Requires Python 3.12+. Run directly with `uv`:

```bash
uv run csp examples/sudoku_4x4.txt
uv run csp examples/murdoku_intro.txt --explain
uv run csp examples/queens_4x4.txt --show-model
uv run csp examples/logicgrid_3x3.txt --brute-force
uv run csp examples/akari_2x2.txt --png akari.png
```

`--grade` reports the hardest deduction used. `--show-model` explains the compiled constraints. `--brute-force` checks uniqueness. `--explain` currently writes Murdoku narratives; `--png` needs Pillow (`uv sync --extra png`). `--docx [FILE]` writes an editable Word booklet for one puzzle of any family, or for a glob such as `"examples/*.txt"` (puzzles first, then their solutions with the solved board and solving steps; needs `uv sync --extra docx`).

For the full [example index and grade notes](docs/examples.md), or the [model rules and file formats](docs/model-and-puzzle-formats.md), see the detail guides.

## A first Murdoku case

Four people on a 4 × 4 floor plan with three rooms. Everyone stands in a
different row and column. Trees, bushes, tables, and cabinets block cells;
chairs and the bed are standable.

<table>
<tr><td><img src="docs/images/murdoku_intro.png" width="230" alt="Murdoku first case"></td><td>

**Clues**

1. Ingrid is on a chair.
2. Joost is next to the tree.
3. Lotte is on the bed.

**Wouter**, the victim, takes the last free square and is alone with the
murderer.

</td></tr>
</table>

For links to every example file, see [Puzzle examples](docs/examples.md). For
the complete syntax and supported rules, see [Model and puzzle formats](docs/model-and-puzzle-formats.md).

<details>
<summary>Show the worked solution</summary>

Joost is at r1c1. Lotte is at r4c2, so Ingrid can only be at r3c4. Wouter is
at r2c3. Wouter and Ingrid share the sitting room, so **Ingrid did it**.

<img src="docs/images/murdoku_intro-solution.png" width="230" alt="Murdoku solution">
</details>

## Puzzle overview

Each cell links to a representative example. The image shows the puzzle or its solution, whichever makes the rule easiest to see.

<table>
<tr>
<td><strong>Murdoku</strong><br><a href="examples/murdoku_intro.txt">first case</a><br><img src="docs/images/murdoku_intro.png" width="150" alt="Murdoku first case"></td>
<td><strong>Mini Sudoku</strong><br><a href="examples/sudoku_4x4.txt">4 × 4</a><br><img src="docs/images/sudoku_4x4-solution.png" width="150" alt="Mini Sudoku solution"></td>
<td><strong>Calcudoku</strong><br><a href="examples/calcudoku_4x4_easy.txt">4 × 4</a><br><img src="docs/images/calcudoku_4x4_easy-solution.png" width="150" alt="Calcudoku solution"></td>
<td><strong>Futoshiki</strong><br><a href="examples/futoshiki_5x5.txt">5 × 5</a><br><img src="docs/images/futoshiki_5x5-solution.png" width="150" alt="Futoshiki solution"></td>
</tr>
<tr>
<td><strong>Jigsaw Sudoku</strong><br><a href="examples/sudoku_jigsaw.txt">6 × 6</a><br><img src="docs/images/sudoku_jigsaw.png" width="150" alt="Jigsaw Sudoku"></td>
<td><strong>X-Sudoku</strong><br><a href="examples/sudoku_x.txt">9 × 9</a><br><img src="docs/images/sudoku_x.png" width="150" alt="X-Sudoku"></td>
<td><strong>NRC Sudoku</strong><br><a href="examples/sudoku_nrc.txt">9 × 9</a><br><img src="docs/images/sudoku_nrc.png" width="150" alt="NRC Sudoku"></td>
<td><strong>Queens-style</strong><br><a href="examples/queens_4x4.txt">4 × 4</a> / <a href="examples/queens_8x8.txt">8 × 8</a><br><img src="docs/images/queens_4x4-solution.png" width="150" alt="Queens-style solution"></td>
</tr>
<tr>
<td><strong>Kropki / thermometers</strong><br><a href="examples/sudoku_kropki_4x4.txt">4 × 4</a> / <a href="examples/sudoku_relations_9x9.txt">9 × 9</a><br><img src="docs/images/sudoku_kropki_4x4.png" width="150" alt="Kropki and thermometer Sudoku"></td>
<td><strong>Anti-knight</strong><br><a href="examples/sudoku_anti_4x4.txt">4 × 4</a> / <a href="examples/sudoku_anti_9x9.txt">9 × 9</a><br><img src="docs/images/sudoku_anti_4x4-solution.png" width="150" alt="Anti-knight solution"></td>
<td><strong>Anti-king</strong><br><a href="examples/sudoku_antiking_6x6.txt">6 × 6</a> / <a href="examples/sudoku_antiking_9x9.txt">9 × 9</a><br><img src="docs/images/sudoku_antiking_6x6-solution.png" width="150" alt="Anti-king solution"></td>
<td><strong>Tectonic / Suguru</strong><br><a href="examples/suguru_4x4.txt">4 × 4</a> / <a href="examples/suguru_8x8.txt">8 × 8</a><br><img src="docs/images/suguru_4x4-solution.png" width="150" alt="Suguru solution"></td>
</tr>
<tr>
<td><strong>Star Battle</strong><br><a href="examples/starbattle_4x4.txt">4 × 4</a> / <a href="examples/starbattle_8x8.txt">8 × 8</a><br><img src="docs/images/starbattle_4x4-solution.png" width="150" alt="Star Battle solution"></td>
<td><strong>Zebra logic grid</strong><br><a href="examples/logicgrid_3x3.txt">3 × 3</a> / <a href="examples/logicgrid_6x6.txt">6 × 6</a><br><img src="docs/images/logicgrid_3x3-solution.png" width="150" alt="Logic-grid solution"></td>
<td><strong>Binairo / Takuzu</strong><br><a href="examples/binairo_4x4.txt">4 × 4</a> / <a href="examples/binairo_8x8.txt">8 × 8</a><br><img src="docs/images/binairo_4x4-solution.png" width="150" alt="Binairo solution"></td>
<td><strong>Tango</strong><br><a href="examples/tango_4x4.txt">4 × 4</a> / <a href="examples/tango_8x8.txt">8 × 8</a><br><img src="docs/images/tango_4x4-solution.png" width="150" alt="Tango solution"></td>
</tr>
<tr>
<td><strong>Tents and Trees</strong><br><a href="examples/tents_4x4.txt">4 × 4</a> / <a href="examples/tents_8x8.txt">8 × 8</a><br><img src="docs/images/tents_4x4-solution.png" width="150" alt="Tents and Trees solution"></td>
<td><strong>Minesweeper</strong><br><a href="examples/minesweeper_3x3.txt">3 × 3</a> / <a href="examples/minesweeper_8x8.txt">8 × 8</a><br><img src="docs/images/minesweeper_3x3-solution.png" width="150" alt="Minesweeper solution"></td>
<td><strong>Light Up / Akari</strong><br><a href="examples/akari_2x2.txt">2 × 2</a> / <a href="examples/akari_8x8.txt">8 × 8</a><br><img src="docs/images/akari_2x2-solution.png" width="150" alt="Akari solution"></td>
<td><strong>Kakurasu</strong><br><a href="examples/kakurasu_4x4.txt">4 × 4</a> / <a href="examples/kakurasu_8x8.txt">8 × 8</a><br><img src="docs/images/kakurasu_4x4-solution.png" width="150" alt="Kakurasu solution"></td>
</tr>
<tr>
<td><strong>Battleships, counts only</strong><br><a href="examples/battleships_counts_4x4.txt">4 × 4</a> / <a href="examples/battleships_counts_8x8.txt">8 × 8</a><br><img src="docs/images/battleships_counts_4x4-solution.png" width="150" alt="Counts-only Battleships solution"></td>
<td></td><td></td><td></td>
</tr>
</table>

## Licence

The code is Apache 2.0 (see `LICENSE`). The puzzles in `examples/` are **not**: they are
© Otto Perdeck, all rights reserved, and may not be copied or reused without the author's
explicit permission (see `examples/LICENSE.md`). Generated `--docx` booklets carry this notice
in their footer.
