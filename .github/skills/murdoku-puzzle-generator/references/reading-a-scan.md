Read this when a puzzle must be transcribed from a photo or scan.

## Reading a scan

Transcribing starts with pixels, and the pixels are the hard part. `csp.scan`
(`uv sync --extra scan`; the solver itself needs neither numpy nor opencv) does
the measuring; this is the order to do it in, and the traps that each cost a day
when you meet them alone.

Start with the CLI rather than with code:

```bash
# grid, pitches, tiles and a labelled contact sheet
uv run python -m csp.scan PAGE.png --size 10 --tiles /tmp/cells --sheet /tmp/sheet.png
# which cells repeat one example, and what the page says
uv run python -m csp.scan PAGE.png --seed r3c5 --top 12
uv run python -m csp.scan PAGE.png --ocr --ocr-language nl+en
```

1. **Text first, and OCR is not optional.** `scan.ocr(path)` returns `(text, box)`
   lines with normalised boxes (origin bottom-left) through macOS Vision (pyobjc)
   or pytesseract elsewhere (its words are grouped back into lines, so both
   backends answer the same thing). Pass `language="nl+en"` to `ocr` or
   `--ocr-language nl+en` to the CLI to select Dutch and English; tesseract needs
   the corresponding `nld` and `eng` language data installed. Without a language,
   Vision uses both while tesseract uses its default (typically English).
   Whole-page OCR reads the big labels; the small
   hand script on the figure cards needs a **2–5x zoom crop per band or per
   column**, or it hands back fragments ("as nog een" for "Was nog een"). Crop with
   a rectangle in the same normalised coordinates and OCR the crop.
2. **A photographed page is not a uniform grid, and it is not axis-aligned.** Pitch
   varies by ten per cent across one spread (260 px to 320 px measured), so an
   assumed pitch drifts a whole cell over ten columns. Detect the lines instead:
   `scan.find_grid` thresholds, isolates long dark runs by morphology, clusters
   them, and fits `size + 1` candidates to each axis. It **refuses** (with advice)
   when no grid fits, several grids fit, or the page is tilted by more than two
   degrees. It does not deskew, so crop and rotate the board upright first. The
   detection is heuristic: compare `Grid.x`/`Grid.y` and their differences against
   the original image before trusting anything downstream.
3. **Normalise before comparing.** `scan.tiles` resizes each cell to
   `scan.CELL_TILE`; the printed icon scales with its cell, so raw crops never
   compare across the board.
4. **Match icons; do not try to classify them.** `scan.rank_cells(tiles, seed)`
   ranks all cells against one example, masked to the icon by `scan.icon_mask` and
   searched over a few pixels of offset. Unmasked correlation ranks *floors*: two
   tables on different floors score worse than a table and a chair sharing one
   floor. Repeated stamps (board symbols, identical icons) rank cleanly at the top;
   hand-varied drawings (a carpet spanning five cells, a chair drawn at two angles)
   do not — say so rather than guessing.
5. **Measurement cannot name a shape.** Colour histograms, connected components and
   template matching tell you *which cells repeat*, never *what a shape is*. Ask for
   one example cell per kind, or for the lists of object and mark cells. Never
   invent a cell so that the clues parse: a placeholder board labelled as such in
   the header is acceptable, a silent guess is not. A placeholder board can
   leave `--brute-force` with several solutions; report that as a board limit,
   never edit clues to hide it.
   A printed board that is not square still needs `Size: N` (the longer side):
   declare the cells outside it as one blocking object and record that in the
   header. Do not silently pad the board with usable squares.
6. **Hand a person a contact sheet.** `scan.contact_sheet(tiles, path)` writes every
   tile with its cell name — the fastest review loop with the user ("r5c3 is a
   chair, r7c2 is not").
7. **Watch the page edges.** Book scans are cropped at the gutter as often as not:
   the first letters of a card and the start of a global clue go missing. Report
   which words are missing instead of reconstructing them, and record it in the
   file header.
8. **Never commit a scan.** Scans, crops and contact sheets stay in the git-ignored
   `proprietary puzzles/`. Tests for this module draw their own board
   (`tests/test_scan.py`); no proprietary pixel enters the repository.
