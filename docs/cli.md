# Command-line options

Complete reference for `csp` and `puzzle-lab`. Run `uv run csp --help` or
`uv run puzzle-lab <command> --help` for the same text; file syntax is in
[Model and puzzle formats](model-and-puzzle-formats.md) and
[Murdoku clue grammar](murdoku-grammar.md).

## `csp`

`uv run csp [OPTIONS] [PUZZLE ...]`. A puzzle file or a quoted glob; the type is
detected from its sections unless `--type` overrides it.

| Option | Meaning | Needs |
|---|---|---|
| `PUZZLE ...` | Puzzle files or globs (`"examples/**/*.txt"`). `--docx`/`--pdf` combine them. | |
| `-v`, `--verbose` | Narrate every deduction. | |
| `-s`, `--step` | Redraw and pause after each deduction. | |
| `--track-person P` | Murdoku: trace a person's live squares and area companions. | |
| `--type KIND` | Force a family; `--help` lists the current choices, including `bridges`. | |
| `--expressions` | Compatibility flag; Murdoku always uses the expression grammar. | |
| `--show-model` | Print the compiled model and solving algorithm, then stop. | |
| `--brute-force` | Independent search for every solution (uniqueness check). | |
| `--explain` | Worked solution; Murdoku and Sudoku have their own narrators, with a generic fallback for Sudoku. | |
| `--grade` | Print only the hardest rule the solve needed, or `unsolved`. | |
| `--lint` | Murdoku: check declarations, icons, reachable areas, roles and clue expressions. | |
| `--require-forward` | Murdoku: lint and require a solve without `what_if`. | |
| `--png [FILE]` | Puzzle as PNG (default beside the input); solved runs also write `FILE-solution.png`. | `uv sync --extra png` |
| `--svg [FILE]` | Puzzle as SVG; solved runs also write `FILE-solution.svg`. | `uv sync --extra svg` |
| `--interactive` | With `--svg`: blank interactive board with ids for playable cells or link nodes, no solution. | `uv sync --extra svg` |
| `--docx [FILE]` | Word booklet: puzzles then solutions, one page each, grouped and numbered; a glob makes one booklet. | `uv sync --extra docx` |
| `--pdf [FILE]` | The same booklet as PDF (LibreOffice, Word or Pages). | `uv sync --extra docx` |
| `--nosolution` | Write only the puzzle, no solving or solution pages. | |
| `--export DIR` | Per-puzzle JSON bundle and interactive SVG, plus `index.json` for the web player. | `uv sync --extra svg` |

`--show-model`, `--brute-force`, `--explain`, `--grade`, `--lint` and
`--require-forward` are mutually exclusive. `--nosolution` cannot be combined
with solving options or `--export`. `--png` and `--svg` default beside the input;
`--docx` and `--pdf` default beside it (`booklet.docx`/`booklet.pdf` for a glob or
no puzzle files) and without puzzle files include every Murdoku in `examples/`.

## `puzzle-lab`

`puzzle-lab` authors non-Murdoku puzzles; `murdoku-board` drafts Murdoku boards.
`rate` trusts a puzzle only when deduction finishes it and independent search
confirms one solution. Every command accepts `-h/--help`.

### `rate`

| Option | Meaning |
|---|---|
| `PUZZLE` | File to rate and verify. |
| `--json` | Machine-readable result. |

### `search`

| Option | Meaning |
|---|---|
| `PATHS...` | Files or folders to search. |
| `--family F` | Restrict to one family. |
| `--tier {easy,medium,hard}` | Required tier. |
| `--deductive` | Only puzzles the ladder closes without `what_if`. |
| `--json` | Machine-readable result. |

### `generate`

| Option | Meaning |
|---|---|
| `SOURCE` | Seed puzzle whose solution is kept. |
| `--output FILE` | Destination. |
| `--tier {easy,medium,hard}` | Required tier. |
| `--grade G` | Also require this measured rule. |
| `--as-family {queens,binairo,tango}` | Compatible display alias only. |
| `--seed N`, `--attempts N` | Reproducibility and budget. |

### `rooms-clues` and `rooms-check`

`rooms-clues` searches a rooms plan for a clue set that fits an author's brief;
`rooms-check` verifies a finished file against the same brief.

| Option | Meaning |
|---|---|
| `PLAN` / `PUZZLE` | A rooms file with a `Solution: Ada=a Ben=b` line and no clues, or a finished puzzle. |
| `--output FILE` | Where `rooms-clues` writes the puzzle. |
| `--clues N` | The most clues to keep (default 10). |
| `--kinds a,b` | Allowed clue kinds: `in`, `dir`, `beside`, `empty`, `together`, `alone`, `choice`. Emptiness may only be `= 0` or `>= 1`, never another number. |
| `--last PERSON` | The person who must be the final placement (a late discovery). |
| `--seed N`, `--attempts N`, `--seconds S` | Reproducibility and the search budget. |

Both insist that the answer is unique, every clue is needed, no single clue fixes
anyone in one room and no room or group is named twice.

### `fresh`

| Option | Meaning |
|---|---|
| `FAMILY` | Family to build, including `bridges`; `puzzle-lab fresh --help` lists the current choices. |
| `--size N`, `--output FILE` | Board size and destination. |
| `--tier`, `--grade` | Required tier and optional exact rule. |
| `--open-share X` | Empty share for Binairo/Tango, unknown share for Minesweeper. |
| `--stars N` | Stars per row, column and region (Star Battle/Queens). |
| `--comment TEXT`, `--seed N`, `--attempts N` | Header comment, reproducibility and budget. |

### `sweep`

| Option | Meaning |
|---|---|
| `FAMILY` | Family to build boards for. |
| `--size N`, `--count N`, `--seed N` | Size, number of seeds and first seed. |
| `--open-share X`, `--tier` | Open-cell share and optional tier request. |
| `--save DIR` | Keep every board named by size, tier, grade and seed. |

### `audit`

| Option | Meaning |
|---|---|
| `PATHS...` | Files or folders to audit. |
| `--json` | Machine-readable result. |

### `murdoku-board`

| Option | Meaning |
|---|---|
| `SPEC` | Theme spec such as `specs/murdoku/vietnam-6x6.txt`. |
| `--output DIR` | Drafts and contact sheets (default `drafts/murdoku-board/THEME`). |
| `--seed N`, `--candidates N`, `--keep N` | Reproducibility and how many drafts to build/keep. |
| `--template auto\|bands\|blobs\|staircase\|free` | Board layout style. |
| `--expressions` | Expression key clues, rules and suggestions (default). |
| `--key-clue CLUE` | Extra key clue in puzzle syntax; may repeat. |
| `--avoid PATH` | Skip used layouts; may repeat, e.g. `examples`. |
| `--no-pictures` | Skip PNG contact sheets. |
| `--suggest` | Close kept drafts with clues and report count/grade. |

## Extras and checks

`uv sync --extra svg|png|docx|scan` installs fonttools, resvg, python-docx or
the scan toolkit (numpy, opencv, and macOS Vision or tesseract) as needed.
`--export` needs SVG. Scans need `--ocr-language nl+en` for both languages.

Project checks: `uv run pytest -q`; `uvx ruff check src tests benchmark`;
`uvx ruff format --check src tests benchmark`; `uv run mypy src`.

## Grading

See [grading and auditing](puzzle-collection.md) for commands, tiers and
coverage gaps, and the [web puzzle index](https://operdeck.github.io/human-reasoning-puzzles/)
for each puzzle's player-facing rating.
