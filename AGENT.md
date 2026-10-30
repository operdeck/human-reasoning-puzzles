`COUNT` constraints list allowed totals of true literals. Their optional
`reified_by` literal is true exactly when the total is allowed. Keep count
propagation sound for gaps and parity as well as interval bounds; a count
constraint creates a strong link only when both-false support is impossible.
# Notes for agents working on this repo

Read `README.md` first for the model and how the puzzles map onto it.
This file covers intent, invariants, and the things that are easy to get
wrong.

## Intent

A single constraint engine that solves many puzzle families **the way a person
would** — by named deduction rules that can explain themselves — rather than
by search. Adding a puzzle should mean writing a compiler, not touching the
solver.

Explainability is a goal, not a side effect: every deduction lands in
`model.log` with a rule name and a human-readable reason, which is what
`--verbose` and `--step` print.

## Invariants — do not break these

**`AT_MOST_ONE` must never force a value.** It forbids a second truth; it does
not require a first. `EXACTLY_ONE` forces its final option; `COUNT` forces a
literal only when its allowed totals leave one feasible completion. An earlier
version of this code had one `Group` type doing both
jobs, which is sound for Sudoku (9 cells, 9 digits, each used once) and
unsound for Murdoku (7 people, 43 squares, most empty). It concluded things
like "square 37 only fits Vladimir, so Vladimir is there". There is a
regression test for this: `test_at_most_one_does_not_force`.

**Rules return `True` only if they changed something**, and the solver
restarts the ladder on any success. A rule that reports change without
changing state loops forever.

**`core.py` imports nothing from puzzle modules.** Progress is reported via
the `on_step` callback so the engine never learns how to draw a board. If you
find yourself importing a renderer into core, the callback is what you want.

**Every rule must be sound for any model**, not just the puzzles in
`examples/`. Prove it before adding it. `rule_subsumption` carries its proof
in the docstring; follow that pattern.

**Only `core` touches model internals.** Puzzle modules, the CLI and the
tests use the public `Model` API (`literal`, `constrain`, `relate`, the
inspection methods, `assign`/`eliminate`). Renderers learn what changed from
`Step.var`/`Step.value`, never by parsing strings.

**Solving, explaining and drawing are separate layers.** `core` records
*why* each step happened as structure on `Step` (`sources`, `scope`,
`placing`, `trail`), never as wording. `proof` shortens a solve using only
that and the public API. `murdoku` owns the board and what clues mean, and
`board_rules()` is the structured meaning of its constraints — look names
up there, never parse them. Wording (`Language:`, `Words:`, phrasebooks)
lives only in `story`; pictures only in `picture`. Explanation concerns
never go on `Board` or into `core`. `test_modules_only_import_their_own_layer`
enforces the import graph.

## Interfaces

| Boundary | Contract |
|---|---|
| puzzle module -> engine | `compile_puzzle(...) -> Model` |
| engine -> rules | `Rule(name, apply)`, `apply(model) -> bool`; log every deduction under `name` |
| engine -> caller | `Solver(model, rules).solve(on_step) -> Result` |
| progress | `on_step(rule_name, steps)` after each rule that fires |
| CLI -> puzzle | `cli.load(text, kind) -> Puzzle(kind, model, draw)` |
| explanation | `report.describe(model, rules) -> str`, public `Model` API only |
| proof | `Move.of(rule, steps)`, `shortest(start, moves)`, `replay(start, moves, on_step)`, `essential(model, history, step)` |
| worked solution | `story.explain(text) -> str`; Murdoku only, reads `proof` and `murdoku` |
| brute force | `bruteforce.solutions(text, kind, limit) -> list[dict]`; never imports `core` |

Label every constraint with `family=` when compiling a new puzzle type;
`--show-model` groups by it and falls back to the name with digits masked.
The first paragraph of each rule's docstring is what `--show-model` prints
as that rule's summary, so keep it to one plain sentence.

## Committing and publishing

The repo is **public** (`origin` = `github.com/operdeck/human-reasoning-puzzles`).

- **Branch, check, merge.** Work on a feature branch in small,
  single-purpose commits. Before merging into `main` (fast-forward only), all
  of these must pass: `uvx ruff check src tests benchmark`, `uvx ruff format --check
  src tests benchmark`, `uv run mypy src`, `uv run pytest -q`. CI runs the same
  on every push to `main` (`.github/workflows/tests.yml`).
- **`proprietary puzzles/` never leaves this machine.** It holds the private source
  documents; it is gitignored and was removed from all history. Stage files
  by explicit path, never `git add -A`. Before every push, this must print
  `0`: `git rev-list --objects --all | grep -ciE '\.(docx|pdf)$|proprietary puzzles/'`.
- **Push as `operdeck`, without prompts:** `GIT_TERMINAL_PROMPT=0 git push
  origin main`. The repo's local git config gets the token from
  `gh auth token --user operdeck`; do not switch the global `gh` account, and
  do not rely on the global credential helpers (they hang on a hidden prompt).
- **Never force-push** or rewrite history that is on `origin`.
- **Published puzzles are not copied.** `prrrdoku1-3.txt` are the owner's
  own puzzles. Anything taken from a book or newspaper gets new names or is
  generated instead, as `wie-doet-het-met-wie-2.txt` and the graded Sudokus and
  Calcudokus are.
- **README pictures and solutions are generated**, never hand-edited: redraw
  `docs/images/*.png` with `--png` (rasterised from the SVG renderer) and re-run `--explain` whenever drawing or
  wording changes, and keep the README in step. In the README, "Prrrdoku"
  appears only as the example file names, not as a general term.

## Adding a rule

Write `rule_x(model) -> bool` in `core.py`, add `Rule("x", rule_x)` to
`DEFAULT_RULES` in cost order, and add a unit test that exercises it on a
hand-built model of a few literals (see
`test_subsumption_prunes_the_wider_constraint`).
`test_every_step_is_logged_under_its_rule_name` fails if the name passed to
`assign`/`eliminate` does not match the `Rule` name.

Candidates, roughly in order of value:

- ~~Naked / hidden subsets, Fish~~ — done as `rule_cover(k)`, the
  *k*-constraint generalisation of subsumption. One rule covers all four
  Sudoku patterns; only connected groups of anchors are searched. *k*=4
  (quads, Jellyfish) is not in the ladder: no example needs it.
- **Chains** — done as `rule_chains`: alternating strong/weak links,
  shortest chain first, with weak links also from two-variable relations.
  Each logged step carries the chain (`Step.chain`) and why each link holds
  (`Step.sources`, one per link), so `proof` can replay it and `story` can
  tell it. Since chains, `what_if` fires only on `prrrdoku3.txt` and the
  fiendish Calcudoku. Next: weak links from relations over three or more
  variables, and keeping links between runs (chains are the slow rung).
- ~~Bounded what-if~~ — done as `rule_what_if`, using `Model.clone()`. It
  runs only `single`/`count`/`relations`/`subsumption` on the copy, never itself,
  so it stays one level deep. Within the first variable (fewest options)
  that has a refutable value, it keeps the refutation with the shortest
  trail. Searching *all* variables for the globally shortest one was tried
  and reverted: the fiendish Calcudoku went from 3 what-ifs in 0.15 s to 27
  in 10 s.
- ~~Counting constraints~~ — `Kind.COUNT` accepts an allowed set of true
  counts and an optional `reified_by` literal. `rule_count` handles bounds and
  gaps, while `single`, `cover2`/`cover3`, and support-checked chain links
  generalize the existing deductions. Proof replay, story narration, and
  model reports include count deductions.

A new rule also needs: a case in `proof.Move` so `--explain` can replay it,
wording in `story`, and a place in `proof.HARDEST_FIRST`.
`test_no_step_ever_contradicts_the_brute_force_solution` checks every step
it logs on every example.

Keep the ladder honest: if a rule never fires on any example, say so rather
than listing it as working.

## Murdoku format and occupancy

The reader accepts the final sectioned format only. `Regions:` defines logical
areas; repeated IDs may be disconnected. `AreaTags:` defines separate,
overlapping sets of areas. Legacy `Groups:`, `Furniture:`, and `Doors:`
sections, and object declarations without an explicit kind, are rejected.

Every object footprint declares `blocking` or `standable`, is connected, and
does not overlap another footprint. Blocking cells are unavailable; standable
cells remain occupiable. A person occupies exactly one free square, with at
most one person in any square, row, or column. On an `N` by `N` board with `N`
people, every row and column is occupied; otherwise, lines and free squares
may remain empty. Edge items and corner objects touch cells without occupying
them. Marks may overlap and do not change cell occupancy. Roles overlap unless
the puzzle explicitly constrains them; attributes are fixed person facts.

Names must match appearance: an area called "Blue hall" is drawn blue, and
icons and other visuals fit their object's name. A test checks colour words in
region names against `Regions:` colours; review other names by eye.

Every object and figure needs a vendored icon, never a text fallback: add the
name to `icons.CATALOGUE` (or reuse an entry), vendor a missing picture with
`uv run python scripts/vendor_emoji.py U+<code>` (the only step that uses the
network; rendering never does) and commit the SVG and `bounds.json`. A test
fails when any object or figure in `examples/` lacks one; the Murdoku skill's
"Icons and Pictures" section has the full checklist.

`--lint` reports malformed declarations as errors and missing icons,
unreachable areas, or unused roles as warnings. `--require-forward` also
requires a solve without `what_if`. `--svg` or `--png` without a path writes
`<puzzle-stem>.svg`/`.png` beside the input, and the solved image adds `-solution`;
an explicit path overrides the default. `--interactive` (with `--svg`) adds cell
ids for an app and writes no solution picture. `--export DIR` writes a JSON
bundle and interactive board per puzzle, plus `index.json`, for the web player in
`web/` (see `src/csp/web.py`; it fails when any puzzle cannot be exported). The
player in `web/` stays family-agnostic: palettes, scopes, rules and wording come
from the bundle, so new family knowledge belongs in `web.py`, not in TypeScript.
After changing `web/`, run `npx tsc --noEmit` and `npm test` there. `--docx [FILE]` (or a quoted glob) writes
an editable Word booklet, puzzles first and then solutions, one page each, from
`docx_export`; new Murdoku puzzles should carry the optional `Title:`, `Intro:`,
`Figures:`, `Question:`, `Reveal:` and `| wording` booklet text (see the Murdoku
skill) and never commit generated `.docx` files. After significant puzzle or
`story.py` wording changes, do the skill's whole-booklet "Booklet review": read the
generated text for language and consistency, not for solving.

## Murdoku global counts

`count` clues are Murdoku vocabulary, not new engine rules. Compile them to
`Kind.COUNT` constraints using `murdoku.global_count_conditions`, and call the
same semantic tally from the independent brute-force solver. Reified empty
areas/cells must be true exactly when their occupant count is zero; reuse one
empty Boolean per logical area or cell even when tagged selectors overlap.
Count every entry in `People:`; no subset is implicit. Count only unblocked
free cells for empty-cell selectors.
Attributes are fixed puzzle facts: a count over an attribute can reject an
inconsistent clue but cannot force a person's location. Benchmark changes with
`benchmark/murdoku_global_counts.py`; it compares `single`/`count` with
`single`/`count`/`chains` on 12x12 and 16x16 boards. Three-run Python 3.12
medians (parse/compile/count/count+chains, ms): 12x12
0.23/3.62/2.12/15,336.98 (211 constraints, 904 literals); 16x16
0.31/8.19/4.58/187,982.30 (337 constraints, 2096 literals). The synthetic
16x16 chain run takes about 3.1 minutes; keep that cost visible when changing
the chain rule or this workload.
The text board and `--step` show true/open totals, additional demand, and
feasible totals; active location scopes are highlighted without adding
puzzle-specific behavior to `core.py`.

## Adding a puzzle family

1. New module with `compile_puzzle(...) -> Model`.
2. Pick the variables carefully — **this is where the real design work is.**
  Ask what the puzzle's constraints quantify over. Murdoku's "at most one
  figure per row and column" is about people, so people are the variables;
  copying Sudoku's cell-centric shape produced an unsatisfiable model.
  Queens-style uses regions as variables choosing one cell each, with
  exactly-one row/column constraints and at-most-one constraints per 2x2
  window for the no-touching rule.
3. Express every rule as `EXACTLY_ONE` / `AT_MOST_ONE` sets, plus relations
   (over two or more variables) for clues that link people.
4. A `render(..., title, steps) -> str` function. `steps` are the deductions
   just made; show what they changed, including eliminations a person would
   mark on paper (Murdoku crosses out squares nobody can reach).
5. Wire into `puzzlefile.detect` and `KINDS`, `cli.load` and
   `cli.write_picture`, `bruteforce.SOLVERS`, `picture.py`, and give the
   module a line in the layering test's `ALLOWED` map (`futoshiki.py` is
   the smallest complete example to copy). Draw every piece (stars, tents,
   bulbs, ships...) through `icons`: add a registry `Icon` with a Unicode
   `symbol` for text output and a shape or vendored emoji for pictures, use
   `icons.symbol(...)` in `render()` and `icons.draw(...)` in `picture.py`;
   the parametrised registry test then checks it renders.
6. Add `bruteforce/<family>.py` with `solutions(text, limit) -> list[dict]`,
   a plain search sharing only the reader and the rule definitions. Keep the
   rule definitions (what a clue or cage *means*) in one place that both the
   compiler and the brute force call, as `murdoku.conditions` does.
   Sudoku's `Puzzle.houses()` is the same idea for groups: Jigsaw boxes and
   extra houses (`Extra:`, for NRC boxes and X-Sudoku diagonals alike) are
   defined once and used by compiler, brute force and
   picture alike.
7. Test against an **independent** source of truth — a published solution,
   the brute force, or a property check (permutation, givens preserved).
   Self-consistency is not verification.

For a new family, include small and materially larger original examples and
check every example for uniqueness and per-step soundness. Add its example and
solution visual to the root README's compact gallery, with file/grade details
in `docs/puzzle-collection.md` and its model/file syntax in
`docs/model-and-puzzle-formats.md`. Update the relevant authoring skill. Use
existing generic primitives; if they are insufficient, open a separate core
design issue instead of adding puzzle-specific code to `core.py`.

For non-Murdoku puzzle authoring, use the repository `puzzle-lab` CLI to
generate, rate, and search examples. Keep difficulty claims tied to its
deductive solving and uniqueness checks; if the current solver cannot support
a tier for a family, document the gap rather than label an unsolved or trivial
puzzle. Follow `.github/skills/non-murdoku-puzzle-authoring/SKILL.md`.
Murdoku has its own generator skill and tools; do not change them for
non-Murdoku work.

The web index is the full visual inventory. Show one representative unsolved
`static` SVG per existing `section`, including each Murdoku series, not one
image per puzzle or one for all Murdoku. Keep the table-like rows compact:
thumbnail first, then puzzle links in one or two columns. Preserve
`collection.arrange` sections and numbering, including separate Binairo and
Tango groups. Keep static paths in index metadata; never use solution pictures
for previews. Check narrow/desktop layouts and puzzle-link navigation.

## Current rule coverage, measured

Numbers from actual runs, not estimates:

| Puzzle | Result | Rules that fired |
|---|---|---|
| `sudoku_1_4x4.txt` | solved, 11 iterations | `single` 10 |
| `sudoku_5_9x9.txt` | solved, 50 iterations | `single` 49 |
| `sudoku_10_9x9_pointing.txt` | solved, 60 iterations | `single` 57, `subsumption` 2 |
| `sudoku_13_9x9_naked_pair.txt` | solved, 65 iterations | `single` 58, `subsumption` 4, `cover2` 2 |
| `sudoku_11_9x9_hidden_pair.txt` | solved, 59 iterations | `single` 56, `cover2` 1, `subsumption` 1 |
| `sudoku_14_9x9_xwing.txt` | solved, 57 iterations | `single` 54, `cover2` 2 |
| `sudoku_15_9x9_swordfish.txt` | solved, 59 iterations | `single` 56, `cover2` 1, `cover3` 1 |
| `sudoku_17_9x9_chains.txt` | solved, 74 iterations | `single` 55, `subsumption` 9, `chains` 6, `cover2` 3 |
| `sudoku_8_9x9_x.txt` | solved, 56 iterations | `single` 55 (two solutions without its diagonals) |
| `sudoku_12_6x6_jigsaw.txt` | solved, 35 iterations | `single` 30, `subsumption` 3, `cover2` 1 |
| `sudoku_6_9x9_nrc.txt` | solved, 54 iterations | `single` 53 (two solutions without its extra boxes) |
| `futoshiki_3_5x5.txt` | solved, 49 iterations | `single` 25, `relations` 12, `chains` 8, `cover2` 3 |
| `wie-doet-het-met-wie-1.txt` | solved, 23 iterations | `single` 10, `relations` 6, `subsumption` 4, `cover2` 2 |
| `murdoku_3_house.txt` | solved, 11 iterations | `single` 5, `relations` 4, `subsumption` 1 |
| `murdoku_sparse_mystery.txt` | solved, 5 iterations | `single` 4 |
| `murdoku_global_counts.txt` | solved, 13 iterations | `single` 9, `count` 3 |
| `murdoku_composition.txt` | solved, 38 iterations | `single` 20, `count` 14, `relations` 3 |
| `prrrdoku1.txt` | solved, 14 iterations | `single` 7, `relations` 4, `subsumption` 2 |
| `prrrdoku2.txt` | solved, 27 iterations | `single` 9, `relations` 14, `chains` 2, `what_if` 1 |
| `prrrdoku3.txt` | solved, 40 iterations | `single` 9, `relations` 18, `subsumption` 5, `cover2` 2, `what_if` 5 |
| `calcudoku_1_4x4.txt` | solved, 22 iterations | `single` 15, `relations` 6 |
| `calcudoku_3_6x6.txt` | solved, 57 iterations | `single` 35, `relations` 21 |
| `calcudoku_4_6x6.txt` | solved, 60 iterations | `single` 36, `relations` 20, `cover2` 3 |
| `calcudoku_6_6x6.txt` | solved, 73 iterations | `single` 35, `relations` 30, `cover2` 4, `what_if` 3 |
| `calcudoku_5_7x7.txt` | solved, 80 iterations | `single` 47, `relations` 26, `cover2` 4, `cover3` 2 |

The Calcudokus were generated the same way as the graded Sudokus (random
Latin square, random cages, uniqueness checked by brute force) because
newspaper puzzles are copyrighted. `test_every_example_is_unique_and_the_engine_finds_it`
re-checks every example with `csp.bruteforce`. Most random 6x6 Calcudokus need only `relations`; about
one in ten needs `cover2`, and fewer need `what_if`.

The graded Sudokus were generated (random minimal puzzles, uniqueness checked
by backtracking) and picked because each needs its rule: the tests cut the
ladder just before it and assert the puzzle stalls. A single firing can
unlock a whole puzzle, so the counts are small.

The late-reveal Prrrdokus preserve their original assignments while changing
the board or clues so Vladimir is the final placement and her companion stays
ambiguous until then. Puzzle 1 moves r4c2 from kampeerplek to speeltuin.
Puzzle 2 replaces `in_region Jos keukenwinkel` with `above Anna Mao 5` and
retains `at_least Jos Mao 13`; it needs `what_if` and keeps Vladimir last.
Puzzle 3 moves r2c5 from Bankastraat to Helmholtzstraat, moves r1c6 and r2c6
from Bankastraat to Klimgebied Noord to keep Bankastraat connected, and adds
`within Mao Otto 6`. `--track-person Vladimir` traces the live square and
region-overlap companion candidates; regression tests check the final
placement, ambiguity and connected region.

Prrrdoku 3 still needs `what_if` (5 firings, after 34 earlier firings). The
document's own solution argues by cases too ("Waar zit Anna?"). Its key clue,
"Luna is furthest from Mao", is a three-person relation, which gives chains
no weak links yet.

## Known gaps

- The Prrrdoku documents are in `proprietary puzzles/`, one per puzzle. Their boards
  are **images**: extract from `word/media/*.png` and read them; the tables
  are colour legends, useful for matching colours to region names (read
  `w:fill`). Always cross-check a transcription against the candidate lists
  in the document's worked solution, and run `--brute-force` on it.
- Puzzle 3 as first published had no solution under same-region, orthogonal
  "next to" semantics: the koffer on r1c5 sat in Bankastraat. Its board,
  solution picture and worked solution were corrected (r1c5 now in
  Helmholtzstraat); puzzle 1's worked solution listed a cross-region square
  for Tjitske and was corrected too. The answers did not change.
- "Only Luna may stand in the water" is a board rule, written out as one
  `outside` line per other person in the `Rules:` section of
  `prrrdoku3.txt`, so clue numbers still match the document.
- `--explain` follows the solver's own route, shortened. Where the solver
  still needs `what_if` (Prrrdoku 3), the story says "X kan niet op ...:
  dan ..." rather than the document's more insightful case splits.
- `relations` re-scans every relation from scratch on each pass (it prunes
  a whole relation per firing, so there are few passes). Three-way
  relations (`furthest`) make each scan quadratic in domain size. A
  dirty-variable queue would skip relations whose variables did not change.
