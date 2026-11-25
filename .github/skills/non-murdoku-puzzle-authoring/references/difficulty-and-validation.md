Read this when rating, validating, naming or auditing non-Murdoku examples.

Bridges counts individual bridges, not neighbours: two parallel bridges add
two to each endpoint. Connectivity matters even when every island's total is
correct; loops are allowed. Publish only unique boards whose solution forms
one network, and inspect both single and double bridges in the picture and
player. Rate with the ordinary ladder: `cut` is medium and `closure` hard.
Fixed islands mean `reach` normally checks disconnection rather than making a
placement; test that rejection directly rather than claiming a firing.
Fresh generation creates a new layout and derives numbers from a non-crossing
connected network, then rejects non-unique candidates. Do not supply bridges
as givens to manufacture a difficulty tier.

## Difficulty and validation

Calcudoku cages must contain at least two cells in published examples and
fresh or seed-based authoring. Excluding size one from the requested cage
sizes is insufficient: growth can still strand a single cell. Merge each
singleton into a touching cage and rederive that cage's target and operation
from the solution; keep unaffected clues valid. Never generate easier
variants by splitting cages into one-cell hints. The shared builder handles
both fresh layouts and seed variations, with deterministic seeds and
connectivity/solution checks.

Keep valid legacy singleton syntax readable. Compiler-fixed values are not
necessarily authored givens: Calcudoku targets are arithmetic clues, and the
web player should let the user enter their digits. Test that every playable
cell is editable or visibly prefilled, and that Check requires editable clue
cells before reporting solved. Keep this policy in the exporter, not as
family-specific UI code. Rework affected examples without losing measured
technique coverage, audit uniqueness/order, and refresh puzzle and solution
images as well as web/booklet exports.

When a puzzle has a global total that local clues cannot determine (for example,
a total mine count), disclose it in the shared player-facing rules and every
relevant output, including web bundles and booklets. Test both languages and
the behavior when the optional total is absent; do not make a correct placement
look unexplained because a required global constraint is hidden.

One-star Queens regions must contain at least two cells in published examples
and freshly authored boards. Single-cell regions give away a placement,
regardless of the puzzle's final grade. The shared Star Battle builder first
gives each region a neighbour, then grows the rest, and rejects any remaining
singleton. Easy one-star boards use one explicit starter queen instead. When expanding an
existing singleton, recheck the donor region's connectivity and uniqueness:
expansion adds alternative placements, so a visible given may be necessary.
Re-rate the result, audit it against the rest of the gallery and regenerate
both puzzle and solution pictures. Do not ban valid singleton syntax from
the parser: this is an authoring-quality rule.
When tests mutate a gallery seed, assert that the text actually changes;
regenerated layouts can turn literal replacements into silent no-ops.

When consolidating overlapping puzzle families, compare actual rules, sizes,
region layouts and measured deductions, not just names or icons. Share one
parser, solver and fresh generator when the rules are identical, while keeping
distinct display names, icons and collection sections when they help players.
For Queens and Star Battle, `Stars: 1` is Queens; higher counts are Star Battle.
Keep technique coverage rather than near-duplicate boards at the same size,
renumber by measured difficulty, and regenerate pictures with the canonical
piece. Update every collection, booklet, web, benchmark and documentation
reference together. Presentation must not change family identity, solver
semantics or region colouring. Recheck comments against current grades instead
of carrying old difficulty claims forward.

For Battleships examples, use a real `Fleet:` and explain its composition,
straight ships, no-touching (including diagonals), line totals, and shaped
givens in the shared web/booklet rules. Keep counts-only compatibility explicit;
never present it as full Battleships. Reject full staircase totals, and verify
that removing the fleet permits other answers, so the genre's rules really
matter. Do not permute independent rows/columns when mutating a fleet board:
that bends ships and changes their adjacency. Use the fleet-aware builder.
Hidden ship-position variables are compiler auxiliaries, not playable cells.
Validate ship shapes with independent component search, not the same placement
enumeration used by the compiler.

Do not let clue thinning erase the visual vocabulary promised by the rules.
For symbol-rich Battleships examples, retain explicit water (`0`, drawn as
waves), unspecified occupied cells (`1`, drawn as `?`), singles (`O`), ends
(`N/S/E/W`), and middles (`M`). Choose water outside zero-total lines so it
is not merely decorative. Add only solution-consistent clues to an original
fresh board, then re-rate: added givens can reduce its grade. Keep at least
three quarters of the playable grid unknown, preserve independent uniqueness,
verify fleet rules still matter, and avoid `what_if` for ordinary hard boards.
Inspect the unsolved web and booklet diagrams, not just solved pictures;
test the actual exported water/ship givens and rendered symbols.

For Sudoku variants, name every active variant in the file name and `Title:`.
Check both web and booklet rules against the parsed constraints, including extra
houses and combined variants. Never assume a player's familiarity with the
symbols: explain the dot colors, consecutive bars, thermometer direction, and
whether unmarked pairs carry restrictions. These explanations come from shared
rendering code, not copied puzzle introductions.
Keep the web player family-agnostic: export localized explanations with semantic
peer groups rather than reimplementing chess moves or other puzzle rules in UI
code. Conflict feedback must use visible givens and placements, not the solution.
Give automatic conflict feedback its own player toggle, enabled by default and
saved with progress independently of auto-mark; players can choose less help.

`puzzle-lab rate` reports the hardest solver rule used and a tier derived from
that rule, with limited family-aware calibration for small relational and
count-only puzzles. These are repository-specific estimates, not universal
human difficulty ratings. It also reports `deductive`: `false` means the ladder
closes the puzzle only with `what_if`, so no deduction path exists. Read that
field rather than parsing the grade, and use
`puzzle-lab search --tier hard --deductive` to list the hard puzzles that need
no fallback. Reserve `what_if`, the final fallback rule, for only
the very hardest puzzles; ordinary hard examples should be solved by the other
deduction rules. A tier is not enough by itself: inspect the actual deductions
and puzzle presentation, confirm that the puzzle is not simply prefilled, and
report any limitation of the solver's grading ladder. A board with under a
quarter of its cells open (`PREFILLED_OPEN_SHARE`) rates `trivial`, whatever
rule its last cells need. `tests/test_example_quality.py` rejects trivial or
non-unique gallery examples. Known exceptions there must link to an open issue.

The `count` rule also uses variables whose remaining options all lie inside a
counted set, and reserves capacity across disjoint scopes of one family.
Re-rate a board after such engine changes instead of relabelling it or adding
givens to hide a deduction the ladder now makes; keep the measured grade even
when it drops.
