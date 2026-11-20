# Murdoku clue grammar

The reference for Murdoku clue and rule expressions, their wording, and
the diagnostics that enforce them. Board declarations and booklet
sections are in [Model and puzzle formats](model-and-puzzle-formats.md#murdoku).

The expression language in [#244](https://github.com/operdeck/human-reasoning-puzzles/issues/244)
is the only Murdoku clue grammar used by the CLI, web exporter, booklet and authoring tools.
`load_expression_board` returns the fixed layout, rule statements and clue
statements separately. `load_board_layout` reads only declarations;
`compile_board` compiles those declarations, while `murdoku_lower.compile_statements`
adds the typed expressions. The independent search evaluates those same
expressions through the reference evaluator. There is no legacy reader,
predicate compiler or alternate search path.
In this language, `in` is reflexive footprint containment and `on` is reflexive overlap;
other spatial operators require distinct entities. An `empty` cell has no
person even if blocked; migrate the current empty-cell counts using
`empty free cells` to retain their free-cell-only behavior. A person `is` a
bound role entity means membership in that role.

For expression wording, `| wording` replaces one complete
statement and `Words:` may replace an expression phrase template. Phrase
overrides must retain all placeholders of the original template; otherwise
they could hide a subject, target, comparison, or other part of the clue.
Legacy `clue.*` phrase keys are rejected: move a puzzle-specific sentence to
that statement's `| wording`. The role declaration's distinct-area rule can be
worded with `rule.role_separation`, retaining `{a}`, `{b}` and `{role}`.
Generated person clues describe window and point-object footprints as cells
touching the feature, and marks as marked cells. Place captions may retain their
preposition (`hall: on Monday` in `Words:` changes the wording, not containment).
Clues belonging to one figure share a paragraph and retain all source numbers;
authored sentences keep their wording rather than being shortened into predicates.
Single numbered rows and columns use singular names. Dutch person-location
sentences use `staat` for directions and adjacency, and `zit` for `on`;
explicit `atom.one` and `atom.not` templates still take precedence.
A named person's `dir:king object:… <= 1` reads as "on or directly next to
a square of …", explicitly including diagonals and area boundaries; negation
covers the whole union of target footprints. A target such as
`people on object:…` instead names a person on the object. Exact distances
such as `= 1` retain their metric wording, as do other bounds.
Exact person-to-person cardinal directions name their row or column distance.
For two named people, positive `dir:rows` and `dir:cols` bounds say how many
rows or columns apart they are, without implying a direction or alignment.
A role with exactly one holder may use a singular name such as "the murderer";
optional or multiple-holder roles retain set wording. Worked solutions announce
a last candidate once, cite a single clue directly, and group remaining role
exclusions only after every other person's role state is known.
Alternative areas retain their own prepositions, with negation covering the
whole alternative. A quantified person is named directly only when exactly one
must exist; optional and multiple-holder domains keep their quantifiers.
Newly reserved rows and columns are stated explicitly. Counterfactuals cite
mark occupancy rules and their possible companions, never internal gate names.
Placements on conditional marks state the resulting solitude or company. Once
one marked square is occupied and an exact-one count applies, the story also
explains why the other squares carrying that mark are empty.
Chains cite the row, column, clue or rule that justifies each link; unnumbered
booklets state the premise instead of referring to an absent clue number.
Simple counts of people on or in a footprint read as "exactly", "at least" or
"at most" that many people. Other counts and arithmetic remain compositional;
an explicit `number.compare` template overrides this idiom.

## Expression clue language

The reader, reference evaluator and compiler can also be used independently.
`python -m csp.clue_search report FILE`, `thin FILE` and `ease FILE` measure
expression puzzles with the independent search and compiler.
`suggest FILE --solution "Ada=r1c1 ..."` uses named-person location, line and
direction templates. Its suggestion vocabulary remains limited: it does not
generate arbitrary expressions or distinguish solutions differing only in roles.
The suggestion templates exclude unions, differences,
adjective-qualified and projected sets, filters and comprehensions; occupancy
assertions and set comparisons; compound Boolean formulas; numeric, parity and
range comparisons; quantifiers and choices. Its AST inventory is guarded
against additions to the language.
For a draft board with expression `key_clue:` entries, use
`puzzle-lab murdoku-board SPEC --suggest`; expressions are the default. It uses the same
limited suggestion templates and reports drafts it cannot close.
`python -m csp FILE --show-model` shows the compiled model grouped by source
expressions. Console solving, `--grade`, `--brute-force`, `--verbose`, `--step`,
expression-native `--explain`, `--svg`/`--png`, `--export`, `--docx`/`--pdf`,
`--nosolution`, `--interactive` and `--track-person` use the same expression model.
`--lint` reports board and expression diagnostics, including
impossible required relations, role-negation and relation-size warnings;
`--require-forward` adds a forward-only solve check. `--expressions` remains a
compatibility flag; Murdoku always uses the expression grammar.

An operand is a set of entities of one sort. Sorts are people, cells, rows,
columns, logical areas, features and roles. A person's footprint is their
square; a feature's footprint is its object cells, the cells touched by an
edge or point item, or the cells of a mark. A role entity has no footprint.
Attributes are fixed sets of people and tags are fixed sets of areas. Two
separately declared objects remain distinct even if named alike.

| Expression | Meaning |
|---|---|
| `Ada`, `people`, `areas`, `rows`, `columns`, `cells`, `objects`, `roles` | A person or a complete universe. |
| `area:hall`, `tag:outside`, `object:bed`, `object_kind:standable` | One area, tagged areas, named object instances, or objects of a kind. |
| `edge_item:door`, `point_object:fountain`, `mark:red` | Named feature instances. |
| `role:guard`, `attribute:staff` | People holding a role or having an attribute. |
| `rows:1,3-5`, `columns:last`, `corner:board` | Selected lines or board-corner cells. |
| `area of S`, `row of S`, `column of S`, `cell of S` | Areas, lines or cells intersecting the footprints in `S`. |
| `S, T`, `S except T` | Same-sort union and difference. `object:bed,chair` repeats the first namespace. |
| `empty S`, `occupied S`, `free S` | Elements with the named property. |
| `(S on T)`, `(S touches T)` | Elements of `S` related to at least one element of `T`. |
| `(?x in S where formula)` | Elements of `S` for which the formula holds. |

`empty` and `occupied` test whether any person is on a spatial footprint;
`free` applies to cells and means not blocked by an object. Thus an empty
blocked cell is still empty. Use `empty free cells` to preserve the old
empty-cell count, which counts only free squares.

Atoms have the form `[some|every|no] S operator T`. The right side is
existential. A determiner may be omitted only when the left side can contain
at most one entity. `in` means footprint containment,
`on` means footprint overlap, `beside` means a shared side in the same area,
and `touches` means a shared side regardless of area. `is` tests membership
or identity; a person `is` a bound role entity when they hold that role.
Containment and overlap are reflexive; adjacency and directional operators
exclude the same entity. Distinct entities remain distinct even when their
footprints coincide.
`S = T` and `S != T` compare sets of the same sort.

Directional operators are `dir:left`, `dir:right`, `dir:up`, `dir:down`,
their vertical-plus-horizontal combinations, `dir:diagonal`, `dir:rows`,
`dir:cols`, `dir:manhattan`, `dir:king`, `dir:euclidean`, `dir:areas`,
`dir:knight`, `dir:nearest` and `dir:furthest`. An optional `= n`, `<= n`
or `>= n` measures the gap where supported; a compound direction applies
the measure to each axis of the same cell pair. Nearest and furthest use
strict comparisons against other people outside the target set, so a tie
does not satisfy the clue. Their optional metric suffix, for example
`dir:nearest:king`, changes the distance measure.

`count S` is the cardinality of `S`; comparisons accept integer arithmetic,
`odd`, `even`, and inclusive ranges such as `1..3`. Formulas compose with
`not`, `and`, `or`, `iff`, and `if ... then`, in that precedence order.
Quantifiers bind `?` variables, as in `every ?p in role:guard: ?p in
area:hall`; multiple variables bind ordered, distinct entities. Choices use
`exactly 1 of (formula; formula)` or `at least` / `at most`. Union uses
commas, never Boolean `and` or `or`.

Area isolation can be written
`every ?a in occupied areas: count (occupied areas touches ?a) = 0`.
To scope the rule, replace the domain with
`(occupied areas in tag:villages)`; occupied neighbors outside the tag still
count. `touches` excludes an area from touching itself.

The reference evaluator defines clue meaning. Expression lowering emits
generic constraints outside `core.py`; it must agree with the evaluator and
preserve the existing tuned patterns and grades. `Key:` entries in the new
reader match expression structure rather than wording or source positions.

### Grammar and scope

The following grammar uses `N` for a non-negative integer literal, `name`
for a person, universe or namespaced operand from the table above, and `var`
for an identifier prefixed with `?`. Parentheses group either operands,
formulas or arithmetic, according to the surrounding context.

```ebnf
statement   = formula [ "|" wording ] ;
formula     = "if" formula "then" formula | quantified | equivalence ;
equivalence = disjunction { "iff" disjunction } [ "iff" quantified ] ;
disjunction = conjunction { "or" conjunction } [ "or" quantified ] ;
conjunction = negated { "and" negated } [ "and" quantified ] ;
negated     = "not" (negated | quantified) | "(" formula ")" | atom | setcompare
            | comparison | choice ;
quantified  = quant var { "," var } "in" operand ":" formula ;
quant       = det | ("exactly" | "at least" | "at most") N ;
det         = "some" | "every" | "no" ;
choice      = ("exactly" | "at least" | "at most") N "of"
              "(" formula { ";" formula } ")" ;
atom        = [ det ] operand spatial operand
            | [ det ] operand direction operand [ measure ]
            | [ det ] operand "is" (operand | adjective) ;
setcompare  = operand ("=" | "!=") operand ;
operand     = union { "except" union } ;
union       = primary { "," (primary | range) } ;
primary     = name | var | adjective primary | projection "of" primary
            | "(" filtered ")" | "(" var "in" operand "where" formula ")" ;
filtered    = operand { spatial union | direction union [ measure ]
                     | "is" (union | adjective) } ;
spatial     = "in" | "on" | "beside" | "touches" ;
direction   = "dir:" mode ;
adjective   = "empty" | "occupied" | "free" ;
projection  = "area" | "row" | "column" | "cell" ;
measure     = ("=" | "<=" | ">=") N ;
number      = number_atom { ("+" | "-") number_atom } ;
number_atom = N | "count" filtered | "(" number ")" ;
comparison  = number ("=" | "!=" | "<" | "<=" | ">" | ">=") number
            | number ("odd" | "even") | number N ".." N ;
range       = N | N "-" N ;
```

Quantifiers can also occur after a Boolean connective; their body extends to
the end of the enclosing formula. Write parentheses to narrow that body:
`(some ?p in people: ?p in area:hall) and Ada in area:garden`.
Multiple variables in one quantifier range over ordered tuples of distinct
entities; a quantified count counts those tuples, not unordered groups.
Bindings are local. Unknown, free, unused or clashing variables are errors.

Use a space after the quantifier colon to distinguish it clearly from a
namespace: `every ?p in role:guard: ?p in area:hall`. Keywords and namespaces
are lowercase and case-sensitive. Person names are case-sensitive too and
must not be reserved keywords.

A filter keeps an element if at least one target satisfies its relation.
Consecutive filters intersect their conditions. A measured direction inside
a counted filter must be parenthesised, as in
`count (people dir:up Ada = 2) >= 1`, so its measure is not mistaken for the
count comparison. Arithmetic is left-associative; use parentheses for grouping.
A numeric left operand selects a numeric comparison; an entity-set left
operand selects set equality or inequality.

For an empty left set, `some` is false and `every` and `no` are true.
Without a determiner, a singleton atom asserts that its one member has a
matching target; an empty optional role therefore does not satisfy it.
`not some role:guard in area:hall` excludes every matching guard, whereas
`some role:guard in area:hall` requires at least one.

### Spatial operators and measures

People, cells, rows, columns, areas and features have footprints. Rows,
columns and areas include their blocked cells; projections do not implicitly
select occupied or free cells. `cell of S` is the union of the footprints in
`S`; the other projections select the corresponding areas or lines that
intersect them. Projection results are sets, so repeated results count once.
`free` applies only to cells; `empty` and `occupied` apply to any footprinted
sort except people.

Spatial operators accept any two footprinted sorts. A witness is a pair of
cells from their footprints, not their centres or bounding boxes. `in`
requires containment of the complete left footprint in the right footprint;
`on` requires a nonempty overlap. `beside` and `touches` require side-neighbour
cells, with `beside` additionally requiring those cells to share a logical
area. Thus a person on a multi-cell object can be beside another cell of that
object. An area and a tag can contain the same area, but two distinct areas
with matching footprints do not become the same entity.

`is` requires matching entity sorts and tests identity/membership, not
footprint equality. Its explicit typing exception is a person on the left
and a role entity on the right, such as a `?r` bound from `roles`: this means
the person holds that role. The operand `role:guard`, in contrast, is a set
of people. Roles themselves have no footprint and cannot take part in
spatial relations.

| Mode after `dir:` | Meaning |
|---|---|
| `left`, `right`, `up`, `down` | A strictly directed gap on that axis; optional `= n`, `<= n` or `>= n`. |
| One vertical plus one horizontal direction, e.g. `up+right` | Both directions hold for the same cell pair; a measure applies to both axes. |
| `diagonal` | Both axis gaps are equal and positive; an optional measure applies to both. |
| `rows`, `cols` | Absolute row or column separation, independent of direction. |
| `manhattan` | The sum of the two absolute axis gaps. |
| `king` | The greater of the two absolute axis gaps. |
| `euclidean` | Straight-line distance; compare squared distances with `n²`, without rounding. |
| `areas` | Shortest side-sharing border distance between logical areas; the same area has distance zero. |
| `knight` | One chess-knight move, with no measure. |
| `nearest`, `furthest` | Strict person superlatives, with no measure; default metric `manhattan`. |

The six numeric modes require a measure. Superlatives accept any of those
six modes as a metric suffix, for example `dir:furthest:rows`.
Area distance uses the existing border graph, not a general path or
connectivity predicate.
`= 0` and `<= 0` are infeasible for strictly directed or diagonal gaps.
Numeric distances can otherwise be zero where distinct entities overlap.
A negative relation to a role does not itself forbid role membership:
same-entity exclusion still applies inside that relation.

### Counts, declarations and diagnostics

Counts do not implicitly restrict the people or spatial scope. Use a filter
or comprehension to state that restriction:

```text
count role:guard = 2
count (role:guard in area:hall) >= 1
count (occupied areas in tag:villages) = 2
count ((empty areas touches area:river) except area:river) >= 1
count (people in (areas touches area:river)) = 3
count (empty free cells on mark:quiet) = 1
count (?r in roles where Ada is ?r) <= 1
```

Empty-area counts include areas without free cells; occupied-area counts
cannot include them. `touches` already excludes a logical area from touching
itself, while `except` can explicitly remove an entire source tag. Boolean
connectives combine formulas, never operand lists; use comma unions,
`except`, filters or comprehensions for sets.

Declarations remain data, with the following equivalent statements:

| Declaration | Equivalent meaning |
|---|---|
| `Roles:` entry `guard: 3` | `count role:guard = 3` |
| `guard: any` (or `guard: *`, or no count) | Any holder count from zero through the full cast. |
| `guard: 3 different_regions` | The exact count and `every ?p, ?q in role:guard: ?p dir:areas ?q >= 1`. |
| `RoleEligibility:` entry `guard: attribute:staff` | `every role:guard is attribute:staff`. Named eligible people and attributes form one union. |
| `Marks:` entry `quiet: ... ; alone` | `every ?p in (people on mark:quiet): count (people in area of ?p) = 1` |
| `Marks:` entry `social: ... ; not_alone` | The same per-occupant quantifier with count `>= 2`. |

Role eligibility never requires an eligible person to hold the role. Mark
conditions apply separately in the area of each occupied marked cell;
unoccupied marks do not force anyone into an area. Attributes are fixed
facts, not assignments that the solver may change.

Reader/type errors include unknown names or namespaces, mixed-sort unions
or set comparisons, footprintless spatial operands, invalid variables,
missing determiners, invalid modes/measures and infeasible count comparisons.
Diagnostics identify the source line and column. `--lint` additionally
rejects board-vacuous requirements, such as two people sharing a side under
the distinct-row/column rules. It warns about an emitted relation involving
more than three position/role variables, suggesting a split, and about
negated role relations that may be mistaken for non-membership. Board lint
also checks declarations, icons, reachable areas and unused roles.
