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
2. Design the intended assignment first (one person per row/column; with `N`
   people on `N`×`N` every line is used), then the board and clues around it.
   Add only clues needed for uniqueness and the target grade; avoid clues that
   hand out a square outright (`in_row` + `in_column`, or one that pins a
   person on step one) unless an easy puzzle is wanted.
3. Never copy a published board, clue set, story or solution.
4. If requirements conflict, explain instead of dropping one.

When both are given, transcribe first, then build a separate derived puzzle.

## Where files go

- `examples/<category>/` for played puzzles. The folder is the category shown
  in the web player and the `--docx` booklet (kebab-case, e.g. `japanese-food`,
  `dierentuin`). Pick an existing category or add one; `demo/` holds small
  showcase boards. `--docx "examples/**/*.txt"` numbers puzzles in a fixed order.
- `tests/puzzles/` for test-only puzzles that are not meant to be played.
- New examples need `uv run pytest -q` to pass (tests look them up with
  `tests/examples.py` `example(name)`).

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
- Report path, parse result, solution count, actual grade, intended solution and
  open doubts. Do not claim a grade `--grade` did not print. Do not change
  solver code or weaken checks unless asked.

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
  rarely cross region borders (note it in the header if they do).
- `EdgeItems:` doors (`gate: door r4c5 r4c6`, two neighbouring cells in
  different areas) and windows (`window: window r2c3`); they occupy nothing.
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
  `role_occupant`); `Clues:` are the numbered clues.
- **Last-candidate rule:** the final character (victim, eater, carer) has no
  clues and appears in nobody's clue; only a rule like `alone_with P [selector]
  [n]` speaks of them. Until everyone else is placed they keep ≥ 2 live squares
  and ≥ 2 companion candidates; check with `--track-person P` and grep `Clues:`.

## Supported clues

Arguments are one-token names; `[n]` is optional.

| Form | Meaning |
|---|---|
| `in_region` / `outside P region...` | in one of / none of the regions |
| `in_tagged` / `not_in_tagged` / `only_in_tagged P tag...` | in / not in tagged regions; `only_` is for `Rules:` |
| `next_to` / `not_next_to P thing...` | shares a side with an object cell **in the same area**; doors and point objects count across borders; no diagonals |
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
  clue. Use it only where the generated text reads badly or for flavour.
- `Words:` fixes phrasing: region phrases (`moeras: in het moeras`,
  `kantoor: op kantoor`), object nouns with their article (`gras: het gras`,
  `bed: het bed`; the Dutch default is "de"), and `role_has`, `role_not`,
  `target.attribute` so roles that are really kinds read naturally
  ("Makaak is een aap"). Dutch region phrases are lower case.
- Check `uv run csp FILE --docx /tmp/check.docx` (needs `uv sync --extra docx`):
  one page per puzzle and solution, correct Dutch de/het, legible board. Never
  commit `.docx` files. Format details: `docs/model-and-puzzle-formats.md`.
