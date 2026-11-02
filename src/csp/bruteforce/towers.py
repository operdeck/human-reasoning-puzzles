"""Towers by plain search: whole rows of distinct heights, columns pruned as they fill.

It shares the reader and the definition of "visible" with the compiler, nothing else.
"""

from itertools import permutations

from ..towers import Puzzle, cell_name, parse, visible


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    n = puzzle.size
    left, right = puzzle.clues["Left"], puzzle.clues["Right"]
    top, bottom = puzzle.clues["Top"], puzzle.clues["Bottom"]
    rows = []
    for r in range(n):
        rows.append(
            [
                row
                for row in permutations(range(1, n + 1))
                if all(not g or g == row[c] for c, g in enumerate(puzzle.grid[r]))
                and (not left[r] or visible(row) == left[r])
                and (not right[r] or visible(row[::-1]) == right[r])
            ]
        )
    found: list[dict[str, int]] = []
    grid: list[tuple[int, ...]] = []

    def column_ok(col: int, full: bool) -> bool:
        heights = [row[col] for row in grid]
        if len(set(heights)) != len(heights):
            return False
        if not full:
            return True
        return (not top[col] or visible(heights) == top[col]) and (
            not bottom[col] or visible(heights[::-1]) == bottom[col]
        )

    def search(r: int) -> None:
        if len(found) >= limit:
            return
        for row in rows[r]:
            grid.append(row)
            if all(column_ok(c, r == n - 1) for c in range(n)):
                if r == n - 1:
                    found.append(_assignment(puzzle, grid))
                else:
                    search(r + 1)
            grid.pop()
            if len(found) >= limit:
                return

    search(0)
    return found


def _assignment(puzzle: Puzzle, grid: list[tuple[int, ...]]) -> dict[str, int]:
    return {cell_name((r, c)): grid[r][c] for r in range(puzzle.size) for c in range(puzzle.size)}
