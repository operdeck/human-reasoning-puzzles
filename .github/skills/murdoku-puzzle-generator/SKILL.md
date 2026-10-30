---
name: murdoku-puzzle-generator
description: "Use when transcribing a user-provided Murdoku photo or scan into solver text, or creating an original Murdoku puzzle from loose clues and constraints. Covers board reconstruction, clue mapping, theming, file validation, uniqueness, and deductive grade."
argument-hint: "Attach a puzzle image or specify a theme, size, clues, constraints, language, target grade, or output path"
---

# Murdoku Puzzle Assistant

You prepare the file; the solver verifies it. Never call a puzzle verified on
reasoning alone. Follow `AGENT.md` (branching, originality) and never overwrite
an existing file. This skill is Murdoku-only: for other families use
`docs/model-and-puzzle-formats.md` and never approximate them as Murdoku.

**Let the repo do the searching.** Placements, uniqueness, clue thinning and
grades are computed by repo tools (`uv run csp ...`, `csp.clue_search`), not by
reasoning in the conversation or by throwaway scripts; see
[Repo tools first](#repo-tools-first).

## Workflows

**Transcribe an image** (photo or scan of an existing puzzle):

1. First establish the user may reproduce it; a supplied image or ignored folder
   is not permission. If unclear, stop and ask.
2. Read the actual image at full resolution (zoom or crop; not OCR alone; never
   fetch another version). Record size, regions, object footprints with their
   **printed** kinds, people, board-wide rules and clues in printed order.
3. Map each clue without changing its meaning. If one is not expressible, say
   so and ask; a partial file must be labelled incomplete. Never approximate.
4. Ask about unclear cells, names or words. Solver results may hint at a misread
   but must not silently pick between readings. Do not alter clues to force
   uniqueness or a grade; report what `--brute-force`/`--grade` say.
5. Default path: git-ignored `proprietary puzzles/`. Keep transcriptions and
   source images out of `examples/`, docs and commits.
6. If the source shows a solution, cross-check it against the clues; report
   disagreements instead of editing. A person on an object proves it standable;
   an empty icon proves nothing.

**Build from constraints** (original puzzle):

1. Split the request into hard constraints (people, board facts, clue meanings,
   size, features) and choices (theme, wording, grade); state the defaults you
   chose. Accept plain-language clues; ask only when ambiguity blocks you.
2. Use `N` people on an `N`×`N` board so every row and column holds exactly
   one person. If a board must have fewer people, say in the `Intro:` which
   lines stay empty and why; never leave it unexplained.
3. Design the intended assignment first, then the board (areas, objects,
   doors) around it, then the clues: let `csp.clue_search suggest` propose
   them and `thin` remove the unneeded ones (see [Repo tools first](#repo-tools-first)).
   Follow [Fair clues](#fair-clues) and, for a mystery,
   [Late-reveal mysteries](#late-reveal-mysteries).
4. Render the puzzle and solution PNGs and get an independent, image-based
   critique from another LLM (see [Independent visual critique](#independent-visual-critique)).
   Review the suggestions against the user's constraints; incorporate useful
   changes and rerender.
5. Add the booklet text ([Booklet text](#booklet-text)) once the clues are final,
   then run [Validation](#validation) and the [completion checklist](#completion-checklist).
6. Never copy a published board, clue set, story or solution.
7. If requirements conflict, explain instead of dropping one.

When both are given, transcribe first, then build a separate derived puzzle.

## Repo tools first

Agent tokens are expensive and the solver is fast. Search with the repo, read
its short output, and decide:

| Need | Tool |
|---|---|
| parse, solution count, grade, issues | `uv run csp FILE --show-model`, `--brute-force`, `--grade`, `--lint` |
| worked solution, reveal order | `uv run csp FILE --explain` |
| a person's live squares while solving | `uv run csp FILE --track-person P` |
| clues that make an intended placement unique | `uv run python -m csp.clue_search suggest FILE --solution "..."` |
| ... while clue N (the theme's key clue) stays necessary | add `--needs N` to `suggest` (several numbers: each stays necessary) |
| which object squares the allowed placements use | `uv run python -m csp.clue_search occupancy FILE` |
| drop unneeded clues within a grade | `uv run python -m csp.clue_search thin FILE --max-grade G` |
| which clues are redundant | `uv run python -m csp.clue_search report FILE` |
| pictures, booklet | `--png`, `--docx` |
| new emoji | `uv run python scripts/vendor_emoji.py U+XXXX` |

- Do not solve, enumerate placements or test clue subsets by hand or with
  one-off code in `/tmp`. If a search you need is missing, add it to the repo
  as a reusable, tested option (for example in `src/csp/clue_search.py` or the
  `csp` CLI), document it here, and ship it in its own commit or PR.
- Run tools with a timeout and do not re-run a long command to see more output;
  read its saved output instead. Prefer `tail`/`grep` over whole outputs.
- When a tool reveals an engine problem (a crash, English engine words in Dutch
  prose, an awkward generated sentence), fix it in `src/csp/` with a test
  rather than working around it in the puzzle.

## Fair clues

Clues should read like a detective's notes, not like arithmetic.

- **Prefer areas, objects and simple relations:** `in_region`, `outside`,
  `next_to`/`not_next_to` an object, `on` a bench, `same_region`,
  `different_region`, and `left_of`/`above` **without** a number.
- **Use exact numbers sparingly**: at most one or two of `left_of A B n`,
  `above A B n`, `within`, `at_least`, `in_row`/`in_column`, `knight_from` and
  `count` per puzzle, and only when they read naturally. `within`/`at_least`
  count Manhattan steps (rows plus columns); say so in the wording if you use
  them.
- Never hand out a square outright (`in_row` + `in_column`, or a first clue
  that pins someone) unless an easy puzzle is wanted.
- **Multi-square objects:** standing on a bench of several squares also counts
  as `next_to` it, and `not_next_to` keeps the person off it. The generated
  sentence says so ("zit niet op of naast een treinbank"); never override it
  with a `| wording` that drops the "op of"/"on or". If you mean only *on* or
  only *beside*, use `on`/`not_on`, or combine `next_to` with `not_on`; for the
  same multi-square object, that combination means "beside it but not on it".
  Keep explicit `| wording` overrides authoritative, and leave single-cell
  object wording unchanged.
- **Read every generated clue as a player would** (`clue_paragraphs`, `--docx`)
  and ask whether another reading of the sentence allows other squares. If it
  does, fix the generated text in `src/csp/story.py` with a test; do not
  redesign the board or swap a multi-square object for single squares.
- Every clue must be needed: `thin` and `report` show which are not; `--lint`
  flags implied and redundant clues.
- **The theme's key clue must do work.** Global counts and greedy suggestions
  easily make a themed clue (the bathrobe/slippers clue, a stated trait)
  redundant. Check it with `report`; if it is removable, rebuild the other
  clues with `suggest --needs N`, or drop clues that `report` shows are fully
  redundant until the themed fact is needed. A fact stated in the intro must
  be needed too.
- **Decoys raise the grade.** Extra items let a key clue fit more than one
  pair of squares; even an impossible pair (both squares in one column) can
  force `what_if`. For an easy puzzle, place decoys so the key clue fits
  exactly one pair, and read `--explain` to see which step is hard.
- Do not name the answer of a "who wears it?" puzzle in a clue: leave `on`
  out of `suggest --kinds` when it would hand out the item's owner.
- **Decoys must be usable.** A decoy on a square no allowed placement can use
  changes nothing, and the key clue is then redundant from the start. Take the
  decoy squares from another legal placement of the people (solve the board
  without items and clues), then confirm with `occupancy` that every item
  square is sometimes used. Also check that some placement breaks the key
  clue; a clue that every item pairing satisfies can never matter.
- **Easing a garment puzzle:** deciding which of two identical items is worn
  is case analysis (`what_if`). Name one wearer directly ("Daan heeft een
  zonnebril op") or pair a person with an item ("Noor staat rechts van de gast
  met de badjas") to bring the grade down while the key clue stays needed.
- **A rule can be the key fact.** To keep a board rule necessary (Wouter's
  partner wears a bathrobe), move it into the clues while searching, run
  `suggest --needs` on it, then move it back to `Rules:`.
- **Declutter.** Standable objects no clue mentions never change the
  solution, and many blocking objects are interchangeable; remove clutter that
  is not part of the theme, re-checking uniqueness, grade and key clues after
  each removal. Keep the objects that carry the series' story.
- Every person except the late-reveal one gets at least one clue.
- Ground clues in the board's story: the clock on the platform, the bench in
  the coupé, the window of the locomotive.

## Late-reveal mysteries

In a mystery the answer (murderer, victim, eater, carer) is the **last
candidate**, deduced from board-wide rules, never told.

- **No direct giveaways.** No `has_role`/`not_role` clue about the answer, and
  the answer person appears in no clue (`suggest --exclude P`). Only `Rules:`
  speak about them.
- **Encode the story as rules**, not as a hint. For example: the murderer is a
  woman (`Attributes:` + `RoleEligibility: moordenaar: attribute:vrouw`), was at
  the crime scene (`AreaTags: plaats_delict: coupe_2` +
  `min_role_in_tagged moordenaar plaats_delict 1`) and was not alone there
  (`role_occupant moordenaar not_alone`). Mention these rules in the `Intro:`.
  For the classic victim pattern use `alone_with P [selector] [n]`.
- **Exactly one answer must follow.** Check with `--brute-force` (one
  solution, one role holder) and read `--explain`: the answer should become
  known by elimination ("De moordenaar was op de plaats delict, dus …") as late
  as possible, ideally with the last placements. Until then the person keeps
  ≥ 2 live squares and ≥ 2 companion candidates (`--track-person P`).
- **Hide the answer in pictures.** The puzzle legend never names the holder:
  when the open candidates share an attribute it says so ("Moordenaar: een
  vrouw"); only the solution picture names them. Check with `--png`. Figure
  descriptions must not hint at the role.

## Where files go

- `examples/<category>/` for played puzzles. The folder is the category shown
  in the web player and the `--docx` booklet (kebab-case, e.g. `japanese-food`,
  `dierentuin`). Pick an existing category or add one; `demo/` holds small
  showcase boards. `--docx "examples/**/*.txt"` numbers puzzles in a fixed order.
- `tests/puzzles/` for test-only puzzles that are not meant to be played.
- New examples need `uv run pytest -q` to pass (tests look them up with
  `tests/examples.py` `example(name)`, so file names must be unique).
- Keep tests quick: run `pytest --durations=10` after adding one. Tests of the
  search tools (`suggest`, `thin`, `report`) use the smallest puzzle that shows
  the behaviour and a small `sample`; build the whole booklet in one test only.
  When a test is slow, profile before trimming it: the cause may be a hot spot
  in shared code (as with recomputed count cells in brute force).
- One canonical file per puzzle: never leave a second copy elsewhere, and
  never commit generated `.png` or `.docx` files.
- List new examples in `docs/puzzle-collection.md` (Murdoku overview, with size
  and grade). Re-export the web collection and check its category, number, and
  puzzle link. The index shows one representative thumbnail per Murdoku
  category/series, not an image per puzzle or one for all Murdoku. Each row
  pairs that unsolved `static` SVG with compact links in one or two columns;
  do not add a separate manual gallery or a solution preview.
- Keep a puzzle PR focused: engine, icon and wording changes the puzzle needs
  may come along (with tests); unrelated refactors and skill rewrites go in
  their own PR.

## Validation

Run from the repo root, one option at a time:

```bash
uv run csp FILE --show-model   # parses and compiles
uv run csp FILE --brute-force  # 0, 1 or many solutions; generated puzzles need exactly 1, in < 5 s
uv run csp FILE --grade        # hardest deduction rule used, or "unsolved"
uv run csp FILE --lint         # missing icons, unknown figures, implied/redundant clues, unused roles
uv run csp FILE --png /tmp/x.png   # look at puzzle and -solution picture
```

- Give every trial (also in clue-thinning loops) a hard timeout of a few seconds
  and kill it; treat a timeout as "not good enough", never wait minutes.
- Uniqueness is relative to the implemented clue semantics; it proves neither a
  correct transcription nor faithful wording. Grades are this solver's ladder
  (`single` < `count` < `relations` < `subsumption` < `cover2` < `cover3` <
  `chains` < `what_if`), not universal difficulty. `--require-forward` forbids
  `what_if`.
- `--track-person P` shows a person's live squares and companion candidates.
- `--brute-force` must finish in < 5 s for a generated puzzle; if not, add
  clues or shrink the board. `clue_search` runs every solve with `--timeout`.
- For a transcription, `--brute-force` and `--grade` are diagnostics: report
  them and compare with the image; never change clues to force a result.
- Report path, parse result, solution count, actual grade, intended solution and
  open doubts. Do not claim a grade `--grade` did not print. Never weaken
  checks or change clue semantics to make a puzzle pass; engine fixes come
  with a test (see [Repo tools first](#repo-tools-first)).

### Completion checklist

For a finished Murdoku under `examples/`, before reporting done:

- `--brute-force`: exactly one solution; `--grade`: the target (or the actual
  grade, reported as such); `--lint`: no issues.
- Clues thinned (`clue_search thin`); few exact-number clues; no giveaway.
- For a mystery: `--explain` reveals the answer by the rules, late.
- `--png` looked at (puzzle and solution), independently critiqued, and useful
  visual suggestions considered; `--docx` page check for booklet text. Look at
  the pages themselves: `--pdf FILE` (via Word) and `pdftoppm -png` give images.
- The picture legend and booklet rules show no engine syntax (`count people
  on object:...`); author wordings appear on player pages, never in solutions.
- The themed key clue is necessary (`report`), and the series order follows
  `--grade`; report any conflict with the requested order instead of hiding it.
- An independent clue review used only player-facing material; each clue was
  restated as a constraint, alternate readings were checked, and solvability
  findings were verified against the source and rendered clue count.
- `docs/puzzle-collection.md` updated; `uv run pytest -q` and `ruff` pass.
- Report path, solution, grade and any open doubts.

## Theme, objects and pictures

- **Objects fit the theme and their region.** A savanne has acacias, baobabs and
  grass; mountains have rocks, a hut, a waterfall; a Japanese restaurant has
  tatami, zaisu and plates; a garden has a park bench. Check every object
  against the region it sits in.
- **Region colours mean something and stay consistent** across a series
  (desert sandy yellow, swamp green-brown, mountains grey-white, water blue,
  forest green). Keep neighbours distinguishable. Use plain region names
  ("Garden", not "Green garden"); a name that does mention a colour must match
  its background (`tests/test_solver.py` checks this).
- **Order a numbered series by measured difficulty.** Run `--grade` on every
  candidate and place simpler puzzles before harder ones, numbering the files
  in that order (`zoo-murdoku-1`, `-2`, ...; unnumbered series such as `demo`
  use `murdoku_1_first_case`). Update all numbered links, tests, pictures,
  booklet references and story titles ("the first case") when inserting or
  swapping a puzzle. Compare solved
  boards across the series too: avoid repeating the same placement pattern or
  a trivially rotated/reflected layout. `uv run puzzle-lab audit examples`
  checks both for the whole collection. A series whose order the author fixed
  for its story (listed in `FIXED_ORDER` in `src/csp/audit.py`) keeps that
  order; only add a series there when the user asks for it.
- **Items whose owner must be deduced lie on the board.** When the puzzle is
  "who wears the bathrobe?", draw the items as standable objects at fixed
  squares (more items than wearers) and state the totals as `Rules:` counts
  (`count people on object:badjas = 2`). Standing on the square means wearing
  it. Use `Attributes:` only for traits the player is told up front; the
  legend then lists the holders with the trait's icon.
- Avoid duplicate category lines in the legend: when a fixed role has the same
  name and exactly the same members as an attribute, show the role line only.
  Keep the attribute line when roles are hidden or the membership is not
  provably identical.
- **Selectors on both sides** of a relation clue say "somebody X ... somebody
  Y": `above object:badjas object:sloffen 1` is "one bathrobe wearer is
  exactly one row above the slippers wearer". When both selectors name cells
  the engine reasons over squares, as a person would.
- **Backdrops and decorations** are cosmetic (`Backdrop:` one icon behind the
  board, `Decorations:` icons at anchors); they never change the solution.
  Give a series one backdrop. Only a thin ring around the board shows, so pick
  pictures recognisable by their outline: fork and knife at the sides, a
  locomotive's smoke and wheels, a lion's mane. Faces, logos, box contents and
  plain convex shapes (egg, bento, a white bathrobe) read as blobs. When no
  emoji works, draw an original SVG with `bounds` (the part behind the board)
  so ears, steam or a key ring stick out above it (see `TORTIE_CAT`). Keep
  eyes and stems off the coordinate line, and get an independent visual review
  of the whole set.
- If a visualization or authoring step is useful beyond one puzzle, prefer a
  shared renderer, helper, `clue_search` option or skill improvement over a
  puzzle-specific workaround.
- The picture labels each region with its name and draws standable objects
  faint; blocking squares are shaded darker. The booklet and web player list
  the puzzle's objects with icon and standable/blocking. You need not add these.
- **Icons:** every object, point object, edge item and figure needs a real
  picture; `--lint` reports "missing icon"/"unknown icon".
  1. Reuse a `CATALOGUE` name in `src/csp/icons.py`, or add the Dutch name and
     English synonyms there. Figures may use `icon=U+XXXX`.
  2. Vendor new emoji only with `uv run python scripts/vendor_emoji.py U+XXXX`
     (pinned Noto commit; commit the SVG and `bounds.json`). No third-party art.
  3. If no emoji fits, draw an original SVG in `icons.py`, register it in
     `REGISTRY` and map names in `OBJECT_ICONS` (see `tatami`, `bench`).
  4. Render and look: the icon must read at cell size and on dark shading.
     Multi-square objects are stretched across the footprint; names in
     `picture.SEAT_NAMES` (benches) keep proportions instead.

## Independent visual critique

For every newly authored board or substantial layout/theme change, ask a
second, image-capable LLM to inspect the rendered puzzle and solution PNGs.
Provide the actual images (not only the puzzle text or file paths) and the
user's hard layout constraints. Ask for actionable feedback on circulation,
area boundaries, floor/room coherence, object-to-area fit, icon legibility,
and consistency across a series.

Treat this critique as suggestions, not authority. Check each point against
the requested design and puzzle rules before changing anything; for example,
do not add lift stops on guest-room floors if the user specified otherwise.
Apply useful suggestions, rerender, and inspect the revised images yourself.
If no independent image-capable reviewer is available, state that limitation
instead of presenting a text-only review as visual feedback.

## Independent clue review

For every newly authored puzzle, ask a fresh, independent LLM/session to review
only the player-facing puzzle. Give it the intro, legend, numbered rendered
clues, question, and either the player-facing web puzzle or puzzle-only DOCX
pages. Do not provide the puzzle definition, source file, solution, solution
image, answer, or author solving notes; omit a `Reveal:` that names the answer.
The reviewer must restate each clue as a constraint, flag plausible alternate
readings, and assess whether and how the puzzle can be solved from the supplied
material. Ask it to identify missing or ambiguous clues without guessing at
hidden source details.

Treat review findings as hypotheses. If the reviewer reports a missing clue or
an unsolvable puzzle, verify the source clue list and count the rendered clue
lines before accepting the finding, then check it against the solver. Route
wording fixes through `src/csp/story.py` with regression tests. If an
independent reviewer is unavailable, state that limitation rather than
claiming a review was completed.

## Board rules

- `Size: N`, an `N`×`N` `Grid:` of region IDs, each declared in `Regions:` as
  `id: name #RRGGBB`; 1..`N` people, at most one per row, column and square.
  Repeated IDs are one logical area even if disconnected. Required sections:
  `Size`, `Regions`, `Grid`, `People`. Use one-token IDs; display text goes in
  `Words:`.
- `Objects:` lines are `name: blocking|standable cells...`, one connected
  footprint per line (repeat the name for more). The kind is always explicit,
  never inferred from the name. Usually chairs, beds, mats and benches are
  standable; tables, trees and rocks blocking. Footprints may not overlap and
  rarely cross region borders (note it in the header if they do). A seat or
  bed may end with the wall its back is against (`bank: standable r3c8 r4c8
  right`); like a window side it only turns the picture.
- `EdgeItems:` doors (`gate: door r4c5 r4c6`, two neighbouring cells in
  different areas) and windows (`window: window r2c3`); they occupy nothing.
  A window may name the wall it sits against (`raam: window r3c4 top`, also
  `bottom`, `left`, `right`): the pane is drawn along that wall. The side only
  affects the picture; put it on a wall the window really touches (the board
  edge or an area border without a door).
- `PointObjects:` on grid points by half-step anchors: `fountain: r3.5c3.5`
  touches four cells, `r0.5c4.5` two on the top edge, `r5.5c0.5` one corner,
  `r3.5c5` a side midpoint. Names must differ from objects (`mouse1`, `mouse2`).
- `Marks:` named cell sets, optional `; alone|not_alone` for whoever stands there.
- `Attributes:` fixed traits (`aap: Makaak Gibbon`). `Roles:` with a count and
  optional `different_regions`; `RoleEligibility:` with `person:`/`attribute:`
  selectors. Never make a role only one person can hold (lint warns); state it
  of that person instead (`alone Leeuw`).
- `AreaTags:` tag regions (overlap allowed); `Hatched:` takes regions or tags.
  `Pronouns:` e.g. `Ada: she her her` (default they/them/their).
- `Rules:` are unnumbered board-wide facts (`only_in_tagged`, `alone_with`,
  `role_occupant`, `min_role_in_tagged`); `Clues:` are the numbered clues. See
  [Late-reveal mysteries](#late-reveal-mysteries).
- Non-standable strips (rails, water) are blocking objects; split them into
  connected footprints and give each line a standable crossing (a gangplank,
  a bridge) where its person must stand. Doors must lie on an area border. An
  area made only of blocking squares is allowed (lint warns) but nobody can be
  there.

## Supported clues

Arguments are one-token names; `[n]` is optional.

| Form | Meaning |
|---|---|
| `in_region` / `outside P region...` | in one of / none of the regions |
| `in_tagged` / `not_in_tagged` / `only_in_tagged P tag...` | in / not in tagged regions; `only_` is for `Rules:` |
| `next_to` / `not_next_to P thing...` | shares a side with an object cell **in the same area**; doors and point objects count across borders; no diagonals. On a multi-square standable object you are also next to it (text: "on or next to") |
| `on` / `not_on` / `only_on P standable...` | on one / none; `only_on` also keeps everyone else off them |
| `at P edge-item...` | on a door or window cell |
| `on_mark` / `not_on_mark P mark...` | on / off marked cells |
| `knight_from P thing...` | a knight's move from a thing |
| `in_corner P`, `in_area_corner P [area...]` | board corner; right-angle corner of an area |
| `in_row` / `not_in_row` / `in_column` / `not_in_column P k` | 1-based line |
| `same_region` / `different_region A B` | same / different area |
| `apart A B`, `adjacent_regions A B` | different non-touching / touching areas |
| `left_of A B [n]`, `above A B [n]` | anywhere left/above, or exactly `n` lines |
| `within A B n`, `at_least A B n` | Manhattan distance ≤ / ≥ `n` |
| `furthest A B` | A strictly farthest of all from B |
| `alone P`, `alone_with P [selector] [n]` | nobody else in P's area; exactly `n` (default 1) others, all matching |
| `has_attribute` / `not_attribute P attr`, `unique_attribute attr P...` | fixed traits |
| `has_role` / `not_role P role`, `some_role P`, `roleless P`, `at_most_one_role P` | role membership |
| `role_subset selA selB` | everyone matching A matches B |
| `role_in_tagged` / `role_not_in_tagged P role tag` | if P has the role, inside/outside the tag |
| `min_role_in_tagged role tag n` | ≥ `n` holders in each tagged area |
| `role_on` / `role_not_on` / `role_next_to P role target...`, `role_below P role [n]` | conditions that apply only if P has the role |
| `sole_role_companion P role`, `role_occupant role alone\|not_alone` | companion/occupancy conditions on role holders |
| `<relation> P selector [args]` | quantified pair clue, e.g. `above Ada role:bandit` |
| `exactly n clue ; clue ...` | exactly `n` of the simple clues hold (≤ 3 people; no quantified targets, `only_on`, `alone_with`) |
| `count people on\|in\|with selector cmp` | occupants of objects, areas/lines/marks, or holders of a role/attribute |
| `count empty areas all\|in area cmp`, `count empty cells in selector cmp` | empty logical areas or free cells |

`cmp` is `= n`, `<= n`, `>= n`, `odd`, `even` or `lo..hi`. Selectors:
`person:`, `attribute:`, `role:`, `area:` (region or tag), `tag:`, `object:`,
`object_kind:blocking|standable`, `mark:`, `edge_item:`, `point_object:`,
`rows:1,3`, `columns:2-4`. Attribute counts check but never locate; `people`
counts everyone in `People:`. People cannot be adjacent (one per row and column),
so there is no person-to-person `next_to`.

## Booklet text

Presentation only; the solver ignores it. Add it last, in the puzzle's
`Language:` (`en`/`nl`), after `Clues:`:

The DOCX/PDF booklet and web player automatically show a general note that
character kinds and descriptions are story details, not clues. Do not duplicate
this note in each puzzle's `Intro:`; players should use only explicit rules and
numbered clues to determine what is possible.

```
Title:
Japanese Food Murdoku 6x6: Five dishes, one wolverine
Intro:
2-3 lines of story and rules (puzzle and solution must each fit one page).
Figures:
Name: meaningful description ; icon=U+1F35C
Question:
One sentence; the late-reveal person is asked about here, never in Clues:.
Reveal:
One or two lines, true for the verified solution (check against --explain).
```

- No numbers like "0" in titles; the booklet numbers puzzles.
- Figures: give everyone an icon. Leave the description empty (`Name: ; icon=...`)
  rather than a role-only filler like "a suspect", "the victim" or "een dier".
- `clue | wording` overrides one generated sentence; it must mean exactly the
  clue. Use it only where the generated text reads badly or for flavour. A
  `Rules:` line takes `| wording` too; it is then listed with the rules in the
  booklet and web player and used in the picture legend. Author wordings are
  for players only: worked solutions always keep the generated text.
- `Words:` fixes phrasing: region phrases (`moeras: in het moeras`,
  `kantoor: op kantoor`), object nouns with their article (`gras: het gras`,
  `bed: het bed`; the Dutch default is "de"), and `role_has`, `role_not`,
  `target.attribute` so roles that are really kinds read naturally
  ("Makaak is een aap"). Dutch region phrases are lower case. Give people that
  are things or animals a display name with article (`Leeuw: de leeuw`).
- Figure descriptions must not repeat clues, roles or rules ("placed last",
  "a Japanese dish"). A `Reveal:` names the answer, checked against the solve
  (e.g. the late-reveal companion); never point to text that is not printed.
- A series (same folder) shares one title pattern; each puzzle gets its own
  subtitle and its own `Reveal:`.
- Check `uv run csp FILE --docx /tmp/check.docx` (needs `uv sync --extra docx`):
  one page per puzzle and solution, correct Dutch de/het, legible board. Never
  commit `.docx` files. Format details: `docs/model-and-puzzle-formats.md`.

### Feeding lessons back

When an authoring session uncovers something general (a pitfall, a missing
tool option, a wording rule), add it to this skill and, if it applies to all
families, to the non-Murdoku skill, in the same PR. Fix the cause in code with
a test (`clue_search`, `story.py`, `picture.py`) rather than working around it
in one puzzle. Keep account names, tokens and other machine-local setup out of
the repository.

### Booklet review

After significant changes (new puzzles, a series, `story.py` wording), build the
whole booklet, `uv run csp "examples/*/*.txt" --docx /tmp/booklet.docx`, extract
its text (python-docx, including table cells) and read all of it as a player
would. Do not solve; check presentation: spelling and de/het, capitals, names
with articles, consistent titles and subtitles, reveals present and correct,
no repeated or empty sentences ("…, ."), no raw clue numbers in solutions, no
facts already given by the figure list. Fix generic prose in `src/csp/story.py`
(with a test) and one-off wording in the puzzle file (`Words:`, `| wording`).

Watch the articles in particular. An object, window, door or point object that
occurs more than once should be named indefinitely ("een treinbank", "a bench"; "het perronbankje" is
ambiguous when there are two). English picks "a"/"an" from the first letter,
so "hour" gets "a" and "unicorn" gets "an", both wrong. When the pattern is general, fix
it in `story.py` with a test; for a single odd word, use a `Words:` alias or a
`| wording` override.
