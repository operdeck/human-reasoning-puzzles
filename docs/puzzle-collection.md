# Grading and auditing puzzles

Reference for puzzle authors and agents. The puzzle list, families and
difficulty ratings live in the
[web puzzle index](https://operdeck.github.io/human-reasoning-puzzles/), which
is generated from `examples/` and explains each rating under *Difficulty
ratings*. This page keeps only the commands that produce and check those
ratings.

Every tracked example is original, generated or owner-authored, with a unique
brute-force solution and engine agreement checked by the tests. Full commands
are in [CLI options](cli.md); syntax is in
[Model and puzzle formats](model-and-puzzle-formats.md).

## Rating and auditing

```bash
uv run puzzle-lab rate examples/bridges_3_7x7.txt
uv run puzzle-lab search examples --tier hard
uv run puzzle-lab audit examples
uv run puzzle-lab sweep bridges --size 7
```

`rate` reports the hardest rule a puzzle needs (its grade), the easy, medium or
hard tier and whether it is `deductive`. These are this solver's estimates,
not universal human difficulty ratings. `search` lists examples by tier;
`sweep` reports what a generator reaches. `audit` checks series order as well
as shared layouts and solutions. Numbered filenames put each series in
nondecreasing measured difficulty in both the web index and the booklet.

## Coverage gaps

The published collection has gaps: Tectonic/Suguru has no medium board, and
Kakuro, Kakurasu and the Zebra logic grid have no hard one; Minesweeper, Light
Up and Battleships have no easy board;
Map has no medium board because its pairwise rules jump from `single` to
`chains`; Undead and Pattern have nothing between `relations` and `what_if`.
Sandwich and Skyscraper Sudoku stop at 6 × 6.

## Beyond deduction

16 of the 205 published puzzles need this solver's *What if* trials
(`what_if`). `puzzle-lab rate` reports them as `deductive: false`, the web index
badges them, and `tests/test_web.py` pins the list.

## External corpora and benchmark

`uv run python -m benchmark.fetch --source all` downloads Sudoku corpora into the
ignored `benchmark/.cache/`; `--count` and `--bucket none|group|rating` sample,
`--force` refetches, and `manifest.json` records hashes and seeds. Puzzle data is
test input, never content. `sudoku-extreme` rates with a backtracking count; this
ladder tracks only the easy block and saturates above, so `bench.py` correlates
over the puzzles it solved and states how many it omitted. See `benchmark/`.
`uv run python benchmark/families.py --runs 3 --seed 42` measures parse, load,
deduction and brute-force times for the listed examples and stops on disagreement.
