"""Pattern by plain search: every row pattern that fits its clue, columns pruned as rows stack."""

from itertools import product

from ..pattern import cell_name, parse, runs


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    rows, cols = puzzle.rows, puzzle.cols
    options = [
        [row for row in product((False, True), repeat=cols) if runs(row) == clue]
        for clue in puzzle.row_clues
    ]
    grid: list[tuple[bool, ...]] = []
    found: list[dict[str, bool]] = []

    def columns_possible(done: int) -> bool:
        """Can every column still reach its clue given the first `done` rows?"""
        for c, clue in enumerate(puzzle.column_clues):
            seen = runs([row[c] for row in grid])
            left = rows - done
            filled = sum(seen)
            if filled > sum(clue) or (sum(clue) - filled) > left:
                return False
            # Every run but the last is closed, so it must match; the last may still grow.
            if len(seen) > len(clue) or any(a != b for a, b in zip(seen[:-1], clue, strict=False)):
                return False
            if seen and seen[-1] > clue[len(seen) - 1]:
                return False
        return True

    def search(r: int) -> None:
        if r == rows:
            if all(
                runs([row[c] for row in grid]) == clue for c, clue in enumerate(puzzle.column_clues)
            ):
                found.append(
                    {cell_name((i, c)): grid[i][c] for i in range(rows) for c in range(cols)}
                )
            return
        for row in options[r]:
            grid.append(row)
            if columns_possible(r + 1):
                search(r + 1)
            grid.pop()
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found
