---
name: murdoku-puzzle-generator
description: "Use when transcribing a user-provided Murdoku photo or scan into solver text, or creating an original Murdoku puzzle from loose clues and constraints. Covers board reconstruction, clue mapping, file validation, uniqueness, and deductive grade."
argument-hint: "Attach a puzzle image or specify a theme, size, clues, constraints, language, target grade, or output path"
---

# Murdoku Puzzle Assistant

Handle either a faithful transcription of a supplied puzzle image or an
original puzzle built from the user's loose clues and constraints. The agent
prepares the file; the solver validates it. Do not call a puzzle verified
based only on reasoning or a plausible-looking solution.

## Choose a Workflow

- If the user supplies a photo or scan of an existing puzzle, use
  [Transcribe an Image](#transcribe-an-image).
- If the user describes a new puzzle, theme, clues, or constraints, use
  [Build from Constraints](#build-from-constraints).
- If both are supplied, transcribe the image first, then treat the user's
  requested changes as explicit constraints on a separate derived puzzle.

Before persistent edits, follow `AGENT.md`, including the branch and
originality requirements. Honor a requested output path, but never overwrite
an existing file.

Before transcribing a third-party puzzle, establish that the user has
permission to reproduce its board, clues, and solution. A user-provided image
or a git-ignored destination does not itself grant that permission. If the
source is unlicensed or permission is unclear, stop before creating a
transcription and ask; a non-reproductive inventory of the source files is
still possible.

This skill's transcription and generation procedures are specific to Murdoku.
For other families, use the file format and model mapping in
`docs/model-and-puzzle-formats.md`, and consult the generated examples in
`docs/examples.md`. Do not encode another family by approximating it as
Murdoku. New family examples must be original or generated, and must be checked
by the family's independent brute-force solver.

## Transcribe an Image

1. Inspect the actual user-supplied image. Use visual inspection at full
resolution and zoom or crop when useful; do not rely on OCR alone for grid
lines, region boundaries, colors, or small clue text. Do not search the web
for a source image or substitute another version.
2. Record the board size and coordinates, each region's name and cells, object
footprints and their explicit kinds, people, board-wide rules, and numbered
clues in their printed order. Never infer an object's kind from its name or icon.
3. Map each clue to the supported syntax below without changing its meaning.
   If a clue is not expressible by this solver, explain the gap and ask whether
  the user wants a partial transcription or a separate solver enhancement.
  A partial file must be labeled incomplete and must not be presented as a
  faithful, complete conversion. Never silently approximate the clue.
4. Do not guess at unclear cells, names, colors, or clue words. Ask focused
   questions about ambiguities that affect the file. A solver result may help
   identify a possible transcription error, but must not be used to silently
   choose between competing readings.
5. Save the transcription at the requested path, or by default under the
  gitignored `proprietary puzzles/` directory with a descriptive new filename. Keep
   transcriptions of existing or potentially published puzzles out of tracked
   `examples/`, documentation, and commits. Do not reproduce the source image
   in the repository.
6. Validate parser acceptance with `uv run csp <file.txt> --show-model`.
   Then run the solution-count and grade checks under [Validation](#validation).
   For transcription, report those results faithfully; do not alter the
   transcribed clues just to force uniqueness or a desired grade.
7. Add booklet text per [Booklet Metadata](#booklet-metadata): the source's title,
   introduction and question, and its own clue wording as `| wording` after each
   clue line, so the booklet reads like the original. Do not pad the puzzle with
   clues another clue already implies (`lint` warns). If roles or attributes are
   really kinds (species, foods), reword them in `Words:` (`role_has`, `role_not`,
   `target.attribute`) instead of "has the role tiger". Never make a role that only
   one character can hold (`lint` warns): say it about that person instead, for
   example `alone <person>` rather than `role_occupant <role> alone`.

### Paired Solution Evidence

When a source includes a solved board or walkthrough, record its placements
and stated answer separately from the puzzle clues. Cross-check those claims
against row/column occupancy, areas, object kinds, and the playable source when
available. If the screenshot, walkthrough, or live interaction disagree,
preserve the discrepancy and report it; do not change clues or object kinds to
force agreement. A coherent person-on-object placement is positive evidence
that the object is standable, but an unoccupied icon does not prove it is
blocking. If a kind remains unclear, ask rather than silently defaulting.

## Build from Constraints

1. Separate the user's requirements into hard constraints and preferences.
   Treat specified people, board facts, clue meanings, size, and required
   features as hard constraints. Treat unspecified theme, wording, and grade
   as choices; make sensible defaults and state them in the result. Ask a
  focused question only when an ambiguity blocks a faithful puzzle. Accept
  clues in ordinary language; do not require the user to know the file format
  or solver syntax.
2. Translate requested clues into the supported syntax below. Preserve their
   meaning. If a requested clue is unsupported or ambiguous, explain that and
   ask before replacing it with a different rule.
3. Design an intended assignment first: each person occupies one free square,
   with at most one person in every row and column. If the board has `N` people
   and is `N` by `N`, every row and column is occupied. Build an original board
   and clue set around it. Check each user-specified clue against the
   assignment, then add only the clues needed to meet the requested
   uniqueness and solver-grade goals.
4. Write a new file at the requested path; otherwise use a new descriptive
   filename under `examples/`. Never copy a published puzzle's board, clue
   set, story, or solution. Consult the `Puzzle files` section of `README.md`
   or `src/csp/murdoku.py` if clue semantics are unclear.
5. Add the optional booklet text described in [Booklet Metadata](#booklet-metadata)
   once the puzzle is final (title, intro, figures, question, and `| wording`
   where useful).
6. Run [Validation](#validation). If uniqueness or the requested grade is not
   achieved, revise the board or added clues without weakening hard
   constraints, then rerun the checks. If the requirements cannot be met
  together, explain the conflict instead of quietly dropping one. When adding
  the puzzle under tracked `examples/`, also run `uv run pytest -q` before
  reporting it complete.

## Validation

Run commands from the repository root. The options below are mutually
exclusive, so run each separately:

```bash
uv run csp <file.txt> --show-model
uv run csp <file.txt> --brute-force
uv run csp <file.txt> --grade
uv run csp <file.txt> --lint
```

- `--show-model` must parse and compile the file. This establishes format/model
  acceptance, not that an image was transcribed correctly.
- `--brute-force` reports whether the encoded puzzle has zero, one, or multiple
  solutions. For a newly generated puzzle, require exactly one. For a
  transcription, treat the result as a diagnostic and report it; compare
  unexpected results with the image rather than changing the source puzzle.
- A generated puzzle's `--brute-force` check must finish within 5 seconds. If it
  takes longer, add clues or shrink the board rather than accepting a slow check.
- Never wait on a solve or brute-force run: give every trial (also each one of a
  clue-thinning loop) a limit of a few seconds, for example `signal.alarm(5)`, and
  kill the process when it is exceeded. Treat a timeout as "not unique/solvable
  with this clue set" and keep the clue; do not let a loop run for minutes.
- `--grade` reports the hardest rule this solver used, or `unsolved`. For a
  generated puzzle, require a solved grade and compare it with the user's
  target. For a transcription, `unsolved` means this solver's deduction rules
  did not finish it; it does not mean the text file is malformed.
- `--lint` reports missing icons (fix them as in
  [Icons and Pictures](#icons-and-pictures)), unreachable areas, and unused roles; malformed
  declarations are errors. `--require-forward` also runs lint and requires a
  solve without the `what_if` rule when forward-only solving is required.
- `--docx [FILE]` (also a glob) writes the booklet; see
  [Booklet Metadata](#booklet-metadata). It needs `uv sync --extra docx`.
- `--track-person` is for a normal Murdoku solve. For a late-reveal puzzle,
  check that the tracked person has multiple live squares and multiple
  region-overlap companion candidates until everyone else is placed, then
  one square and one companion.
- `--explain` can produce a worked solution when requested. Review it against
  the intended assignment and clue meanings. Use `--svg` (or `--png`, which needs
  `uv sync --extra png`) to write `<puzzle-stem>.svg` beside the input, or
  `--svg <file.svg>` to choose an explicit path; the solved image adds `-solution`
  before the extension.

Report the file path, parser result, solution count, actual grade, and any
remaining uncertainties. For generated puzzles, include the intended
solution. Do not claim a requested grade was reached unless `--grade` confirms
it.

## Icons and Pictures

Every object, window, point object and figure must show a fitting picture, not
a text fallback. Do this for each new name before reporting the puzzle:

1. Run `uv run csp <file.txt> --lint`. "missing icon for X" (objects) or
   "unknown icon X" (figures) means the name has no vendored picture.
2. Pick an emoji that shows what the name says (a "tree" is a deciduous tree, a
   "carpet" a carpet). Prefer reusing an existing `icons.CATALOGUE` entry by
   naming the object after it; otherwise add the Dutch name and the English
   synonyms to `CATALOGUE` in `src/csp/icons.py`, grouped with similar objects.
   Figures may use `icon=U+<code>` directly.
3. If its picture is not yet in `src/csp/assets/emoji/`, vendor it (this is the
   only step that needs network; rendering never fetches anything):
   `uv run python scripts/vendor_emoji.py U+<code>`. Commit the new
   `emoji_u<code>.svg` and the updated `bounds.json`. Only vendor from the
   pinned Noto Emoji commit; never add artwork from other sources. If no emoji
   fits, draw an original shape in `icons.REGISTRY` (like `carpet` and `well`)
   and map the name in `OBJECT_ICONS`.
4. Rerun `--lint` until it reports no icon warnings, then render with
   `--svg` (or `--png`) and look at the picture: the icon must read clearly at
   cell size and, for blocking objects, on the darker shading. Fix a picture
   that crops oddly by choosing another emoji rather than editing coordinates.
5. For a committed example, `uv run pytest tests/test_picture.py -k vendored_icon`
   checks every object and figure in `examples/` has a vendored icon.

## Murdoku Invariants

- For a board of size `N`, provide between 1 and `N` people and an `N` by `N`
  region grid. At most one person may occupy each row, column, and square; if
  there are `N` people, every row and column is occupied. Squares may remain
  empty. Repeated region IDs denote one logical area even when disconnected;
  overlay areas use a different ID.
- A `blocking` object's cells are unavailable; `standable` objects remain
  occupiable. The declared kind is required and never inferred from the object
  name or icon. Edge items and point objects touch cells without occupying
  them; marks select cells without changing occupancy.
- Names and appearance must agree. A region named for a colour ("Blue hall")
  gets a background of that colour, and a colour-neutral name never implies
  one; the same holds for icons and other visuals (a "carpet" shows a carpet).
  When transcribing or generating, check every name against its colour and
  icon, and rename or recolour on mismatch. Keep neighbouring regions
  distinguishable. `tests/test_solver.py` checks colour words in region names.
- Every region ID in `Grid:` must be declared in `Regions:`. Use single-token
  identifiers for people, regions, area tags, and object types; use `Words:`
  for display wording where needed.
- `Objects:` declares each footprint as `name: blocking|standable square...`.
  The kind is required and independent of the name and icon. Each line is one
  connected footprint; repeat a name on another line for another instance of
  that type. Footprints may not overlap, and all cells must be on the board.
  Standable objects are valid `on`, `not_on`, and `only_on` targets.
- Furniture footprints: prefer one line per square. Chairs and tables are
  1x1, with chairs standable and tables blocking. Benches (and beds) are
  standable; write each square as its own `bench: standable` line unless a
  multi-square bench is needed. The picture renderer stretches a multi-square
  object into one icon across its whole footprint, which is an acceptable
  fallback but can look odd, so check the picture before keeping it. Footprints
  may cross region boundaries (connectivity is the only parser rule), but that
  is unusual and should be noted in the file header.
  Blocking squares are shaded darker than their region, so a blocking object
  needs an icon that still reads clearly on the darker shade.
- `EdgeItems:` declares named doors and windows without occupying cells.
  A simple door lists two orthogonally neighboring cells in different areas,
  for example `gate: door r4c5 r4c6`; repeat the name for each door in a wider
  opening. A window lists exactly one inside cell, for example
  `window: window r2c3`.
- `PointObjects:` declares an object on a grid point by a half-step anchor,
  for example `fountain: r3.5c3.5` (interior vertex, four cells),
  `mouse1: r0.5c4.5` (top edge between c4 and c5, two cells),
  `mouse2: r5.5c0.5` (bottom-left board corner, one cell), `cheese: r3.5c5`
  (middle of the side between r3c5 and r4c5) or `lantern: r5.5c4` (middle of
  the bottom side of r5c4). Whole numbers are cell centres, `.5` values grid
  lines, `0.5` and `N+0.5` the outer edges; a cell centre is rejected. The
  touched cells are the cells whose square contains the point; they are
  touched, not occupied. A point object name may not repeat an object or edge
  item name, so `mouse1` and `mouse2` (digits are ignored for the icon).
- `Marks:` declares named cell sets independently of areas and objects, for
  example `quiet: r2c3 r2c4 ; alone`. Mark sets may overlap and never occupy
  or block cells. An optional `alone` or `not_alone` condition applies only
  when a marked cell is occupied, then counts people in that cell's logical
  area; `alone` allows one occupant and `not_alone` requires at least two.
- `Roles:` declares theme-neutral roles with an optional exact count, such as
  `bandit: 4 different_regions`; use `any` for an unconstrained count.
  `different_regions` requires holders to occupy distinct logical areas.
  `RoleEligibility:` optionally lists eligible people, including typed
  `person:name` and `attribute:name` selectors.
  Roles overlap by default; use `at_most_one_role <person>` only when needed.
- `Attributes:` declares fixed traits as `attribute: person ...`; unlisted
  people do not have that trait. `Pronouns:` optionally provides one-token
  subject, object, and possessive forms, for example `Ada: she her her`; the
  default is `they them their`.
- `AreaTags:` maps a tag to one or more named regions. Tags may overlap and may
  cover disconnected regions. `Hatched:` accepts either region names or tags.
- Put board-wide, unnumbered clues in `Rules:` and numbered puzzle clues in
   `Clues:`. Required sections are `Size:`, `Regions:`, `Grid:`, and `People:`.
  `Clues:`, `Language:`, `Words:`, `AreaTags:`, `Hatched:`, `Objects:`,
  `EdgeItems:`, `PointObjects:`, `Marks:`, `Roles:`, `RoleEligibility:`,
  `Attributes:`, `Pronouns:`, and `Rules:` are optional.
- Keep clues concise and non-duplicative. Avoid clues that directly reveal
  every person's square unless the user requests a very easy puzzle.
- Use `only_in_tagged <person> <tag>` and `not_in_tagged <person> <tag>` in
  `Rules:` for required-inside and forbidden-inside per-person policies. A
  person with neither policy is unrestricted. `in_tagged` and `not_in_tagged`
  are also available as numbered clues.
- **Last-candidate rule:** in a puzzle with a final character (the victim, the
  eater, a zoo carer, and so on), that character has no clues of their own and is
  named in no other character's clue. The only statement about them is the
  general rule that they are alone with exactly one other character, for example
  `alone_with <person> <selector>` in `Rules:`. The puzzle must be built so that
  they are found last: until everyone else is placed, keep at least two live
  squares and at least two region-overlap companion candidates for them. Build
  the clue pool without that character, and check the result with
  `--track-person <person>`; grep the `Clues:` section for their name as well.
- **Late-reveal mystery rule:** when the question asks who shares a region with
  a named mystery person, keep that person's square
  open to at least two candidates until every other person is placed. Keep at
  least two region-overlap companion candidates until that final placement,
  then leave exactly one companion. Use `--track-person <person>` to inspect
  the live solve trace. Its companion list is a conservative domain-overlap
  check, not a proof of joint feasibility; confirm the final placement and
  companion in the completed solve.

## Supported Clues

Use the spellings and argument order below. Names refer to one-token IDs.

| Form | Meaning |
|---|---|
| `in_region <person> <region>...` | Person is in one of the named regions. |
| `outside <person> <region>...` | Person is in none of the named regions. |
| `in_tagged <person> <tag>...` | Person is in a region carrying any named tag. |
| `not_in_tagged <person> <tag>...` | Person is in no region carrying any named tag. |
| `only_in_tagged <person> <tag>...` | Person is restricted to regions carrying any named tag; intended for `Rules:`. |
| `next_to <person> <object-or-edge-item-or-point-object>...` | For ordinary objects, the person's cell must share a side with an object cell in the same logical area; diagonals do not count. Door and point-object touched cells count, including across an area boundary. |
| `not_next_to <person> <object-or-edge-item-or-point-object>...` | Person is not next to any named thing. |
| `at <person> <edge-item>...` | Person occupies a cell listed by any named door or window. |
| `on_mark <person> <mark>...` | Person occupies one of the cells carrying any named mark. |
| `not_on_mark <person> <mark>...` | Person occupies none of the cells carrying any named mark. |
| `has_attribute <person> <attribute>` / `not_attribute <person> <attribute>` | Check a declared fixed person trait. |
| `unique_attribute <attribute> <person>...` | Exactly one selected person has the declared trait. |
| `has_role <person> <role>` / `not_role <person> <role>` | Assert membership in or explicit absence from a role. |
| `some_role <person>` / `roleless <person>` | Require at least one role or no roles. |
| `at_most_one_role <person>` | Limit the person to at most one role. |
| `role_subset <selector-a> <selector-b>` | Every person matching A must also match B; use bare role names or typed role, attribute, and person selectors. |
| `role_in_tagged <person> <role> <tag>` / `role_not_in_tagged <person> <role> <tag>` | If the person has the role, require them inside or outside the tagged areas. |
| `min_role_in_tagged <role> <tag> <n>` | Require at least `n` holders in each logical region carrying the tag. |
| `role_on`, `role_not_on`, `role_next_to` `<person> <role> <target>...` | Apply the cell/object/mark condition only when that person has the role. |
| `role_below <person> <role> [n]` | Person is below a holder of the role; with `n`, exactly `n` rows below. |
| `sole_role_companion <person> <role>` | Person has exactly one same-area companion, and that person has the role. |
| `role_occupant <role> alone|not_alone` | Apply the occupant condition in each area containing a holder of the role. |
| `knight_from <person> <object>...` | Person is a chess-knight move from any named thing; region boundaries do not matter. |
| `on <person> <standable-object>...` | Person occupies one of the named standable-object squares. |
| `not_on <person> <standable-object>...` | Person occupies none of the named standable-object squares. |
| `only_on <person> <standable-object>...` | Person occupies one of the named standable-object squares, and nobody else occupies any of them. |
| `in_corner <person>` | Person occupies one of the board's four corner squares. |
| `in_row`, `not_in_row`, `in_column`, `not_in_column` `<person> <1-based line>` | Restrict the person to or exclude one numbered row or column. |
| `in_area_corner <person> [area-or-tag...]` | Person occupies a cell at a right-angle corner of a named area; without names, any area corner. |
| `same_region <person-a> <person-b>` | Both people are in the same region. |
| `different_region <person-a> <person-b>` | People are in different regions. |
| `apart <person-a> <person-b>` | People are in different, non-touching regions. |
| `adjacent_regions <person-a> <person-b>` | People are in different regions that share a side. |
| `alone_with <person> <target-selector>` | Exactly one other person shares the subject's region, and that companion matches the selector. |
| `<relation> <person> <target-selector> [relation arguments]` | Quantify pairwise relations such as `above Ada role:bandit` or `within Ben tag:inside 3` over matching people. |
| `left_of <person-a> <person-b> [n]` | A is left of B; with `n`, exactly `n` columns left. |
| `above <person-a> <person-b> [n]` | A is above B; with `n`, exactly `n` rows above. |
| `within <person-a> <person-b> <n>` | Manhattan distance is at most `n`. |
| `at_least <person-a> <person-b> <n>` | Manhattan distance is at least `n`. |
| `alone <person>` | Nobody else is in that person's region. |
| `furthest <person-a> <person-b>` | A is strictly farther from B than every other person. |
| `exactly <n> <clue> ; <clue> ...` | Exactly `n` of the listed simple, named-person clues hold. At most three distinct people may be named across them; quantified targets and `only_on` cannot be nested here. |
| `count people on <object-selector> <comparison>` | Count occupants of a declared object type or occupancy kind. |
| `count people in <area-or-cell-selector> <comparison>` | Count people in an area, tag, row/column list or range, object, or mark. |
| `count people with <membership-selector> <comparison>` | Count holders of a role or people with a declared attribute. |
| `count empty areas all <comparison>` / `count empty areas in <area-or-tag> <comparison>` | Count unoccupied logical regions, deduplicating overlaps. |
| `count empty cells in <cell-selector> <comparison>` | Count unoccupied, non-blocked cells in a selected set. |
| `<comparison>` | `= n`, `<= n`, `>= n`, `odd`, `even`, or inclusive `low..high`. |

Global count semantics and authoring checks:

- `people` counts every entry in `People:`, including a victim if listed; there
  is no implicit suspects-only subset. `object:name` selects that declared
  object type; `object_kind:blocking` and `object_kind:standable` select all
  objects by occupancy kind.
- `rows:` and `columns:` use 1-based lists/ranges, such as `rows:1,3` or
  `columns:2-4`. Cell-set selectors such as `mark:name` count only free cells.
- Empty areas are logical regions. `all` means every declared region; a tag
  selects the regions carrying that tag, with each region counted once even if
  tags overlap. Sparse boards may leave areas empty; full boards may imply some
  row/column counts from the placement rules.
- Attributes in `Attributes:` are fixed facts. A people-with-attribute count
  checks consistency but cannot deduce a location; do not claim it makes a
  puzzle unique. Role counts can constrain membership and role-bound locations.
- Global clues compile to the generic `COUNT` primitive, not a new engine rule.
  Empty-area and empty-cell counts use reified zero-occupancy indicators. Keep
  authored examples small and verify uniqueness plus per-step soundness; never
  copy a published puzzle.
- Record 12x12 and 16x16 timings with
  `uv run python benchmark/murdoku_global_counts.py --runs 3`. The text board
  and `--step` show true/open totals, how many more are needed, and feasible
  totals; `--show-model` lists each set and its allowed counts.

Typed target selectors are `person:name`, `attribute:name`, `role:name`,
`area:name`, `tag:name`, `object_kind:blocking|standable`, `object:name`,
`mark:name`, `edge_item:name`, and `point_object:name`. `area:name` accepts a
region name or tag; `tag:name` requires an area tag. A bare known person is
also accepted. `not_on_mark` with several names excludes their union.

Keep quantified relations bounded: the compiler tests one possible companion
at a time and creates at most one relation per other person plus a count
constraint. A location-only target uses three variables; a role target adds
role membership for a maximum relation arity of four. Do not expand a clue to
one relation over all people; quantified targets and `alone_with` are not
supported inside `exactly`.

For ordinary objects, `next_to` means one orthogonal step (up, down, left, or
right) from an object cell in the same logical area. Diagonal cells do not
count. A door lists two orthogonally neighboring cells in different areas;
either cell satisfies `next_to` or `at`, including across the boundary. Wider
openings are multiple simple doors with the same name. A window lists one cell
for `at`; a point object touches the one, two or four cells around its anchor for
`next_to`, across area boundaries. These items do not occupy or block cells. Direction, distance, and `knight_from`
may cross region boundaries. There is no person-to-person adjacency clue: at
most one person per row and column makes it impossible for two people to
share a side.

## Verification Notes

`--brute-force` searches independently of the deduction engine, but shares
the puzzle reader and Murdoku clue definitions. Uniqueness means unique under
the implemented clue semantics; it does not prove that an image was read
correctly or that natural-language clue intent was represented faithfully.
Check the source image or user constraints yourself. `--grade` measures the
hardest rule in this solver's deduction ladder, not a universal human
difficulty rating.

If validation fails, inspect the error and correct only what the selected
workflow permits: a transcription must stay faithful to its source, while a
generated puzzle may change as long as all hard constraints remain satisfied.
Do not weaken verification or change solver code unless the user separately
asks for a solver change.

## Booklet Metadata

Every new or transcribed puzzle file should carry booklet text so that
`uv run csp <file.txt> --docx` (or a quoted glob such as
`--docx "examples/*.txt"` for a multi-puzzle booklet: all puzzles, one per page,
then all solutions) produces a nice document with no further editing. These
sections are presentation only: the solver, `--lint`, `--brute-force` and
`--png` ignore them, so they never change the puzzle. Append them after
`Clues:`, in the puzzle's `Language:` (en or nl):

```
Title:
Short puzzle title, e.g. "Tamagotchi Murdoku 6x6: Where is the devil?"

Intro:
One line per paragraph: the story and who is on the board. Keep it to 2-3 lines;
a puzzle and its solution must each fit on one page. Omit to get the default
rules paragraph.

Figures:
Name: one-line description of the character ; icon=U+1F35C ; image=optional/relative.png

Question:
What the player must find out, in one sentence. The late-reveal person is
usually asked about here, never in `Clues:`.

Reveal:
Optional one- or two-line answer text, shown only in the solutions section.
```

Also, after a clue line, `| wording` replaces its generated sentence:
`above Otto Tjitske 1 | Otto zit precies één rij boven Tjitske.`

Rules when adding metadata:

- Do this as a final step, after the puzzle is unique and graded, and rerun
  `--lint`: it warns about unknown `Figures:` names. `Reveal:` must be true for
  the verified solution; check it against `--explain`.
- Do not write a `Reveal:` that gives away the answer unless it is consistent with the
  solver's solution; do not invent clues in the wording that the `Clues:` do not state.
- Generated clue sentences already cover every operator in both languages
  (`at_least Ramen Tempura 5` → "Ramen is at least five squares from
  Tempura."). Add `| wording` only where the generated text reads poorly or the
  story needs flavour, and make sure it means exactly the same as the clue: read
  it back against [Supported Clues](#supported-clues). Never use `|` inside the
  clue itself.
- Give every figure a thumbnail where one exists: `icon=U+<emoji code>` (or a catalogue
  name) for original puzzles, e.g. food, animals; a file named after the person in
  `<puzzle>-figures/` for licensed artwork. Lint warns about unknown or unvendored
  icons; vendor them as in [Icons and Pictures](#icons-and-pictures).
- Figure `image=` paths are relative to the puzzle file and optional (missing
  images fall back to text). Never commit third-party artwork; use original or
  licensed images only.
- Check the result: `uv run csp <file.txt> --docx /tmp/check.docx`, open it (or convert
  it to PDF) and confirm one page per puzzle and per solution, readable clue
  numbering and a legible board. Do not commit generated `.docx` files.
- Document format details live in `docs/model-and-puzzle-formats.md`.
