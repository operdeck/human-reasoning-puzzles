Read this when writing, reviewing or easing clues, or designing a mystery.

## Fair clues

Clues should read like a detective's notes, not like arithmetic.

- **Prefer areas, objects and simple relations:** `P in area:name`,
  `P beside object:bench` / `not P beside object:bench`,
  `P on object:chair`, `A dir:areas B = 0`, and `A dir:left B`.
- **Use exact numbers sparingly**: at most one or two directional distances,
  line/area counts, or other numeric clues per puzzle, and only when they read
  naturally. `A dir:manhattan B ...` counts row-plus-column steps; `dir:euclidean`
  is straight-line distance. The [grammar reference](../../../../docs/murdoku-grammar.md)
  defines every mode and comparison.
- Never hand out a square outright (`P in rows:2` + `P in columns:3`, or a first clue
  that pins someone) unless an easy puzzle is wanted.
- **Multi-square objects:** someone on one selected cell may also be `beside`
  another cell of that footprint. Check generated wording against that meaning;
  use `on` when occupancy itself is intended. Keep explicit `| wording`
  overrides authoritative.
- **Read every generated clue as a player would** (`clue_paragraphs`, `--docx`)
  and ask whether another reading of the sentence allows other squares. If it
  does, fix the generated expression wording with a test; do not
  redesign the board or swap a multi-square object for single squares.
- **Features and their occupants are different operands.** `object:bench`
  names the feature even when blocking; `(people on object:bench)` names its
  occupants. `not P dir:king object:bench <= 1` excludes its footprint and all eight neighboring
  squares, including diagonals and neighbors across area borders. Keep that
  distinction explicit in generated clues.
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

- **No direct giveaways.** No `P is role:murderer` clue about the answer, and
  the answer person appears in no clue (`suggest --exclude P`). Only `Rules:`
  speak about them.
- **Encode the story as rules**, not as a hint. For example: the murderer is a
  woman (`Attributes:` + `RoleEligibility: moordenaar: attribute:vrouw`), was at
  the crime scene (`AreaTags: plaats_delict: coupe_2` +
  `every ?a in tag:plaats_delict: some role:moordenaar in ?a`)
  and was not alone there
  (`every ?a in (area of role:moordenaar): count (people in ?a) >= 2`).
  Mention these rules in the `Intro:`.
  For the classic victim pattern use
  `count (people in area of P) = 1 + 1 and every ((people except P) in area of P) is role:moordenaar`:
  exactly one other person shares P's area and that person holds the role. A bare
  `count (people in area of P) = 2` only says P is not alone; it does not identify
  the murderer. When the victim is itself a role holder,
  `(people in area of role:victim) = role:victim, role:moordenaar` also works, but
  the named-person form is the safe default.
- **Exactly one answer must follow.** Check with `--brute-force` (one
  solution, one role holder) and read `--explain`: the answer should become
  known by elimination ("De moordenaar was op de plaats delict, dus …") as late
  as possible, ideally with the last placements. Until then the person keeps
  ≥ 2 live squares and ≥ 2 companion candidates (`--track-person P`).
- **Hide the answer in pictures.** The puzzle legend never names the holder:
  when the open candidates share an attribute it says so ("Moordenaar: een
  vrouw"); only the solution picture names them. Check with `--png`. Figure
  descriptions must not hint at the role.
- **"Who wears it?" is the same shape.** A standable garment with no clue of its
  own answers it: put the garment on the square of the person with no clues and
  check with `--explain` that this person is placed last, so the `Reveal:`
  ("Sora heeft de jumpsuit aan.") is the final deduction. A
  `count people on object:<garment> = 1` rule tells the solver the square is
  occupied and pins the wearer early, so leave it out and let the `Intro:` say
  that standing on the garment means wearing it.
- **Population clues need squares that can change area.** Comparisons between
  area populations and `count (people in area:Tokyo)` constrain which *squares* are
  used, not who stands on them, so a puzzle whose people are each anchored to a
  square implies them and `report` calls them removable. Two people swapping
  two squares never changes a count: leave a row/column whose cells straddle an
  area border (a staircase border is ideal) and re-run `report`, which must say
  "several" for each population clue you want load-bearing.
  "Busiest" and "quietest" area are not keywords: state the tie and compare
  every other area with counts, for example
  `every ?b in (areas except area:Tokyo): count (people in ?b) < count (people in area:Tokyo)`.
