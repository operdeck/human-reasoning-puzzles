Read this when choosing objects, colours, icons, backdrops or series order.

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
  checks both for the whole collection. Every series gets the same measured
  difficulty-order check; do not hardcode category exemptions. Report a
  story-order conflict rather than silently bypassing the audit or renumbering
  an owner-authored story without approval.
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
- **Filtered people on both sides** of a relation say "somebody X ... somebody
  Y": `some (people on object:badjas) dir:up (people on object:sloffen) = 1` is
  "one bathrobe wearer is
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
- **Alpine hut vocabulary** is registered in `CATALOGUE`: `buitendouche`,
  `terrasbank`, `houtstapel`/`hout`, `kachel`, `pan`, `krat`, `rugzak`,
  `bergschoen`, `helm`, `touw` and `stinksokken`, plus a `counter` alias for
  `aanrecht`. Reuse them instead of adding one-off names.
- **Draw the story detail when the emoji is too clean.** `DIRTY_SOCKS` is an
  original SVG (ribbed cuff, brown and green stains, holes, stink curls) mapped
  through `OBJECT_ICONS`; the clean Noto socks read as new. Use one sock per
  cell so two single cells look like a pair on the line.
