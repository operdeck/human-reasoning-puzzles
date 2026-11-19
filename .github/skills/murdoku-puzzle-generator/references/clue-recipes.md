Read this when a printed clue does not map straight onto an expression.

## Clue recipe guide

Follow the murdoku.fans transcription method: identify the **subject**, the
**relation**, any **qualifier**, and its **scope**, then write one **yes/no
test**. Compose; do not add a keyword.

1. Decide whether each noun names people, features, cells, lines, areas or roles.
   The person on a horse is `(people on object:horse)`, not the horse itself.
2. Select the operands. Use a union for alternatives, a filter for a restricted
   set, and a projection for its areas, rows or cells.
3. Make quantities explicit. A multi-element left operand needs `some`, `every`
   or `no`; bind `?` variables when the same entity must be reused.
4. Preserve scope. "Not near any dish" negates the whole near relation; saying
   "far from some dish" is weaker. "Exactly these people" needs set equality,
   not merely a total.
5. Test a placement that should satisfy the card and one that should not,
   against the reference evaluator. Then run lint, uniqueness and grade checks.
   A unique answer does not prove a faithful transcription.

These are composition recipes, not additional grammar. `P`, `A`, `B`, `C` and
`J` stand for person names; `?b`, `?p` and `?r` are bound variables.
Projections are `area of S`, `row of S`, `column of S` and `cell of S`: the
areas, lines or cells intersecting the footprint of `S`. A union uses commas
(`(mark:ra, mark:anubis)`), a difference uses `except` (`(attribute:woman except
P)`), and a filter keeps the members of a set that satisfy one relation
(`(people beside object:chest)`).

| Printed card | Statement(s) |
|---|---|
| One row above an empty row | `P dir:up empty rows = 1` |
| In a bed; the other bed is in an empty row | `P on object:bed`; `every ?b in object:bed: P on ?b or ?b in empty rows` |
| Someone one row above her is beside a chest | `some (people beside object:chest) dir:up P = 1` |
| Top or bottom row; the other is empty | `P in rows:1,last`; `count (people in rows:1,last) = 1` |
| Beside a plant | `P beside object:plant` |
| Alone in their area | `count (people in area of P) = 1` |
| Shares the area with exactly one other person, the murderer | `count (people in area of P) = 1 + 1 and every ((people except P) in area of P) is role:moordenaar` |
| Shares the area with a distinct woman / man | `some (attribute:woman except P) in area of P`; equivalently `some attribute:woman dir:areas P = 0` |
| One row below the person on a marked gathering spot | `P dir:down (people on mark:gathering) = 1` |
| Beside a marked square, even across an area border | `P touches mark:anubis` |
| Beside a marked square in the same area only | `P beside mark:anubis` |
| On a Ra or Anubis square | `P on (mark:ra, mark:anubis)` |
| Beside a point object (a cat on a grid point) | `P on point_object:cat`; its footprint is the cells it touches, even across an area border |
| On a door or window | `P on edge_item:door` / `P on edge_item:window` |
| No Roman on any Ra or Anubis square | `no attribute:roman on (mark:ra, mark:anubis)` |
| In a granary or on the field | `P in (area:granary_a, area:granary_b, area:field)` |
| In any area of a tag | `P in tag:villages` |
| South of B; exactly one row south | `P dir:down B`; `P dir:down B = 1` |
| Three columns west of B | `P dir:left B = 3` |
| More than two columns away, either side | `P dir:cols B >= 3`; rows use `dir:rows B >= 3` |
| Northeast of B | `P dir:up+right B` |
| On B's diagonal | `P dir:diagonal B` |
| First column / top row / bottom row / fifth row | `P in columns:1` / `P in rows:1` / `P in rows:last` / `P in rows:5` |
| The only person on a carpet / beside a table | `(people on object:carpet) = P` / `(people beside object:table) = P` |
| At least two people in the dining room | `count (people in area:dining) >= 2` |
| A and C alone together in the changing room | `(people in area:changing) = A, C` |
| Not in water, but beside it | `not P in area:water and P beside area:water` |
| Before or after Hole 5 in playing order | `P on object:hole4,hole6` (the author resolves the order) |
| Not with the outlaw | `not P dir:areas role:outlaw = 0`; add `not P is role:outlaw` only if membership is also excluded |
| P holds role x / P holds at most one role | `P is role:x`; `at most 1 ?r in roles: P is ?r` |
| In a grid corner | `P in corner:board` |
| Exactly two people on an Anubis square / one of them | `count people on mark:anubis = 2`; add `P on mark:anubis` |
| On a bed / not on a bed | `P on object:bed` / `not (P on object:bed)` |
| Not beside a bush | `not (P beside object:bush)` |
| With a man and the only woman on a chair; J is not on a chair | `some attribute:man dir:areas J = 0`; `count (attribute:woman on object:chair) = 1`; `some (attribute:woman on object:chair) dir:areas J = 0`; `not J on object:chair` |
| Nearest the piano | `P dir:nearest object:piano` |
| Between Ada and the statue in one row | `(Ada dir:left P and P dir:left object:statue) or (object:statue dir:left P and P dir:left Ada)`; `P dir:rows Ada = 0 and P dir:rows object:statue = 0` |
| The murderer shares the victim's room, with nobody else | `(people in area of role:victim) = role:murderer, role:victim` |
| Every woman is on a chair | `every attribute:woman on object:chair` |
| Every woman is in a different room | `every ?p, ?q in attribute:woman: ?p dir:areas ?q >= 1` |
| If Ada is in the kitchen, Ben is not | `if Ada in area:kitchen then not Ben in area:kitchen` |
| Cook or Butler is on a rug, but not both | `exactly 1 of (Cook on object:rug; Butler on object:rug)` |
| Two rooms beside the hall are empty | `count (empty areas touches area:hall) = 2` |
| No empty row between occupied rows | `no ?r in empty rows: some occupied rows dir:up ?r and some occupied rows dir:down ?r` |
| Someone west of the whole river | `some ?p in people: every ?c in (cells in area:river): ?p dir:left ?c` |

Combine rows for multi-part cards: "alone in a hut" is `P in tag:hut` plus
`count (people in area of P) = 1`; "in a hut with a woman" is `P in tag:hut`
plus `some attribute:woman dir:areas P = 0`; "one of the two people on an
Anubis square, and alone" is `P on mark:anubis` plus
`count people on mark:anubis = 2` plus the mark's `; alone` declaration.

**Worked quantifier transcription.** "Ada lies in a bed; the other bed is in
an empty row" names bed instances, not all bed squares as one anonymous set.
Write `Ada on object:bed`, then
`every ?b in object:bed: Ada on ?b or ?b in empty rows`.
The bound `?b` is reused in both alternatives. Check a layout where Ada uses
one bed and every unused bed lies entirely in an empty row; moving another
person into an unused bed's row must fail. If the card says "the other bed",
first verify the board actually has two bed instances.

**Worked set-equality transcription.** "Ada and Carmen are alone together in
the changing room" is `(people in area:changing) = Ada, Carmen`.
It both requires their presence and excludes everyone else. Check that either
person leaving the room, or a third person entering, makes the statement false.
`count (people in area:changing) = 2` alone would not identify the pair.

For a card meaning the **strict interior of the rectangle** between Ada and a
statue, combine horizontal between-ness with its vertical counterpart:
`((Ada dir:left P and P dir:left object:statue) or (object:statue dir:left P and P dir:left Ada)) and ((Ada dir:up P and P dir:up object:statue) or (object:statue dir:up P and P dir:up Ada))`.
Do not silently substitute this for inclusive edges or an aligned-row reading.

**Names are identifiers, never quoted text.** `area:"Granary A"` is a parse
error. Declare `Granary_A` (letters, digits and `_`) and write
`area:Granary_A`; the booklet and picture render `_` as a space. The same holds
for people, objects, marks, tags, roles, attributes and `Words:` keys, and
`AreaTags:` lists region identifiers rather than display text. Repeated
`Regions:` IDs form one logical area even when disconnected; `AreaTags:` are
separate, overlapping sets. A scan that
prints "Hut 1", "Graanschuur A" or "Westelijke vallei" therefore becomes
`Hut_1`, `Graanschuur_A`, `Westelijke_vallei`; keep the printed sentence in
`Words:` or `| wording`.

**Which axis does `dir:` compare?** `dir:up` and `dir:down` compare rows only,
in any column; `dir:left` and `dir:right` compare columns only, in any row.
"Directly above" is `P dir:up Q = 1 and P dir:cols Q = 0`; "in the same row" is
`P dir:rows Q = 0`. Do not read `dir:up = 1` as same-column. `dir:up+right` and
`dir:diagonal` combine axes on one cell pair.

**Empty versus free.** `empty X` means no person is on X, including blocked
cells; `free` applies to cells and means no object covers them. Use
`count empty free cells in ...` for "unoccupied and standable", and plain
`empty rows` / `empty areas` for openness to people. `occupied` means at least
one person.

**Occupying versus being beside a mark.** `P on mark:x` occupies a marked cell;
`P touches mark:x` shares a side across area borders; `P beside mark:x` shares a
side within the same area. Standing on the marked cell satisfies neither
adjacency relation. Counts of a union use `count people on (mark:a, mark:b)`.
A `Marks:` declaration may end `; alone` or `; not_alone`; that is a board rule
for every occupant of the marked cells, not a numbered clue. A point object's
footprint is the cells it touches; `P on point_object:x` is therefore "P stands
on a cell beside that feature". A door names two side-sharing cells in different
areas (`door: door r2c2 r2c3`), a window names one inside cell
(`window: window r3c4`), and `P on edge_item:x` means P stands on either touched
cell. The same area rule applies to objects and areas:
`beside` is same-area, `touches` crosses a border. Use `touches` when a printed
"next to" must count across an area border and `beside` when it must not.
`in` and `on` are reflexive (an entity contains or overlaps itself), while
`beside`, `touches` and `dir:` require distinct entities; that is why `on`
includes standing on a footprint and `beside` never does.

**Same-named objects are separate instances.** Two `Objects:` lines named
`bed: ...` declare two distinct bed instances; `object:bed` is the set of both,
not one merged footprint. A single line with several cells is one multi-cell
instance. This is what makes "the other bed" expressible:
`every ?b in object:bed: P on ?b or ?b in empty rows`.

**Role sets and role entities.** `role:x` is the set of people holding x, so
`P is role:x` tests membership and `role:x` may be a spatial operand meaning
"some holder" (`P dir:areas role:x = 0`). A role *entity* bound from `roles`
(for example `every ?r in roles`) has no footprint; reach a holder's location
through the holder (`people on ...`, `area of ?p`).

**Migrating a file written in the old predicate syntax.** `--lint` reports
"legacy form is removed". Rewrite subject-first; never add a second reader.
These are the mappings that cover transcribed cards:

| Removed form | Native expression |
|---|---|
| `in P area:x`, `in P rows:2` | `P in area:x`, `P in rows:2` |
| `on P object:x` / `not on P object:x` | `P on object:x` / `not (P on object:x)` |
| `beside P object:x` / `not beside P object:x` | `P beside object:x` / `not (P beside object:x)` |
| `touches P mark:x` | `P touches mark:x` |
| `dir P Q down = 1` | `P dir:down Q = 1` |
| `alone P` | `count (people in area of P) = 1` |
| `with P attribute:woman in same area` | `some (attribute:woman except P) in area of P` |
| `with P role:r in same area exactly 1` | `count (people in area of P) = 1 + 1 and every ((people except P) in area of P) is role:r` |
| `count people with role:x = n` | `count role:x = n` |
| `count people from A, B with attribute:t = n` | `count (A, B is attribute:t) = n` |
| `count people on mark:a and mark:b = n` | `count people on (mark:a, mark:b) = n` |
| `count roles of P <= n` | `at most n ?r in roles: P is ?r` |
| `only P on object:x` | `(people on object:x) = P` |

`count people in ...` and `count people on ...` remain valid; only the `with`
and `from` forms above were removed.
