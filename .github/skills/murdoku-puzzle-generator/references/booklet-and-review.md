Read this when writing booklet text or reviewing a puzzle, booklet or solution.

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

## Booklet text

Presentation only; the solver ignores it. Add it last, in the puzzle's
`Language:` (`en`/`nl`), after `Clues:`:

The DOCX/PDF booklet and web player automatically remind players that only the
stated rules and clues determine what is possible; a kind or trait matters only
when a rule or clue explicitly uses it. Do not duplicate this note in each
puzzle's `Intro:`.

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
  The booklet combines portraits, bold names, descriptions and unnumbered clues
  under "The figures and their clues" / "De figuren en hun aanwijzingen".
  Everyone appears, even without clues; global and loose clues follow under
  "Other clues" / "Overige aanwijzingen". Ownership comes from clue semantics,
  never from the wording, so a custom wording need not start with the owner's
  name. A numbered clue is shown with a figure when it anchors exactly one
  person:
  - an atom whose subject is that person (`P in ...`, `P touches ...`,
    `P dir:...`);
  - `count (people in area of P) = 1` (alone) or `(people on object:x) = P` (the
    only occupant);
  - any other compound whose formulas anchor one person through a location-atom
    subject, an `area of` / `row of` / `column of` / `cell of` projection, or a
    `dir:` target.

  Two or more named people, or none, leave the clue under "Other clues"; a
  person merely named on the right of a set comparison such as
  `(people on object:chair) != Ada` is not an anchor. `| wording` changes the
  sentence, never the owner. A card that splits into a person clue and a global
  half (for example the top/bottom-row recipe) must word the global half
  self-containedly, because it is printed under "Other clues" without the
  figure heading. Puzzle-specific `Rules:` statements join these
  entries too, under their semantic subject or the sole named figure anywhere in
  a compound rule; otherwise they join "Other clues". Keep `Intro:` as written.
  The web and mobile player show it above the puzzle, and the booklet prints it
  before the reference rules; do not repeat it in the game-rules panel. That
  panel adds semantic clarifications and the disclaimer, not another list of
  puzzle-specific statements. Standard no-own-clues notes are hidden when a
  figure has a displayed rule or clue, preserving the rest of the description.
- `clue | wording` overrides one generated sentence; it must mean exactly the
  clue. Use it only where the generated text reads badly or for flavour. A
  `Rules:` line takes `| wording` too; it is then listed with the figure's
  clues (or "Other clues") in the booklet and web player and used in the picture
  legend. The expression narrator uses the same override in worked solutions
  (it never infers clue meaning from the prose), so keep the sentence faithful
  and do not let it give the answer away. The solver always uses the typed
  expression.
- `Words:` fixes phrasing: region phrases (`moeras: in het moeras`,
  `kantoor: op kantoor`), object nouns with their article (`gras: het gras`,
  `bed: het bed`; the Dutch default is "de"), and `role_has`, `role_not`,
  `target.attribute` so roles that are really kinds read naturally
  ("Makaak is een aap"). Dutch region phrases are lower case. Give people that
  are things or animals a display name with article (`Leeuw: de leeuw`). The key
  is the identifier used in expressions (`Graanschuur_A`), not the spaced display
  text. A key that overrides a phrase template (for example `rel.dir.areas`) must
  keep every `{placeholder}` of the original; dropping one hides part of the clue
  and is rejected. Plain place and object keys are captions, not templates.
- Keep descriptions useful and concise; avoid repeating clues, roles or rules.
  Preserve supplied information, especially meaningful late-reveal descriptions,
  when changing presentation. A `Reveal:` names the answer, checked against the solve
  (e.g. the late-reveal companion); never point to text that is not printed.
- A series (same folder) shares one title pattern; each puzzle gets its own
  subtitle and its own `Reveal:`.
- Optional presentation sections: `Pronouns: Name: she her hers` fixes a
  person's pronouns in worked-solution prose, and `Hatched:` lists region
  identifiers drawn with hatching in the picture. Neither changes the solve.
- Mystery questions and reveals must identify the requested role explicitly
  ("Who is the murderer?", "Carmen is the murderer"), not rely on an action
  such as "struck with" that can confuse attacker and victim. Explain the
  answer using the encoded trait and crime-scene rules. Never infer a named
  victim from room-sharing alone: name one only when the puzzle explicitly
  establishes that identity. Review the whole series for the same ambiguity
  and check the wording reaches both the web verdict and booklet solution.
- Check `uv run csp FILE --docx /tmp/check.docx` (needs `uv sync --extra docx`):
  one page per puzzle and solution, correct Dutch de/het, legible board. Add
  `--nosolution` to read only the puzzle pages of a puzzle the rules do not
  close yet. Never commit `.docx` files. Format details: `docs/model-and-puzzle-formats.md`.

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
Check portrait rows as well: no cast member or supplied description is lost,
clues sit with their semantic owner, a split card's global half is
self-contained under "Other clues", ordinary sentences do not repeat the name
heading, and global clues are printed exactly once. Inspect rendered short and
dense pages, including long descriptions and figures without clues; fitting
estimates and DOCX text checks alone are not a visual page review.

Watch the articles in particular. An object, window, door or point object that
occurs more than once should be named indefinitely ("een treinbank", "a bench"; "het perronbankje" is
ambiguous when there are two). English picks "a"/"an" from the first letter,
so "hour" gets "a" and "unicorn" gets "an", both wrong. When the pattern is general, fix
it in `story.py` with a test; for a single odd word, use a `Words:` alias or a
`| wording` override.
