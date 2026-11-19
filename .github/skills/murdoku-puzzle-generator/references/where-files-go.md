Read this when deciding where an example, test, picture or collection entry belongs.

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

- Give each uniqueness check and grading solve (also in clue-thinning loops)
  a separate hard timeout of a few seconds; treat a timeout as "not good
  enough", never wait minutes.
- Uniqueness is relative to the implemented clue semantics; it proves neither a
  correct transcription nor faithful wording. Grades are this solver's ladder
  (`single` < `count` < `relations` < `subsumption` < `cover2` < `cover3` <
  `chains` < `what_if`), not universal difficulty. `--require-forward` forbids
  `what_if`.
- `--track-person P` shows a person's live squares and companion candidates.
- `count` also uses whole variables confined to a counted area and reserves the
  shared capacity of disjoint areas in one family. A puzzle like
