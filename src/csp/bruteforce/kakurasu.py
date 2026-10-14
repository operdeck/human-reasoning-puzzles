"""Kakurasu by independent row-pattern search and weighted column totals."""

from itertools import product

from ..kakurasu import cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    size = puzzle.size
    weights = range(1, size + 1)
    row_patterns = []
    for row, target in enumerate(puzzle.row_sums):
        row_patterns.append(
            [
                pattern
                for pattern in product((False, True), repeat=size)
                if sum(weight for value, weight in zip(pattern, weights, strict=True) if value)
                == target
                and all(
                    puzzle.givens[row][col] < 0 or bool(puzzle.givens[row][col]) == pattern[col]
                    for col in range(size)
                )
            ]
        )
    column_sums = [0] * size
    grid: list[tuple[bool, ...]] = []
    found: list[dict[str, bool]] = []

    def search(row: int) -> None:
        if row == size:
            if column_sums == puzzle.column_sums:
                found.append(
                    {cell_name((r, c)): grid[r][c] for r in range(size) for c in range(size)}
                )
            return
        remaining_weight = sum(range(row + 2, size + 1))
        for pattern in row_patterns[row]:
            for col, value in enumerate(pattern):
                if value:
                    column_sums[col] += row + 1
            if all(
                current <= target <= current + remaining_weight
                for current, target in zip(column_sums, puzzle.column_sums, strict=True)
            ):
                grid.append(pattern)
                search(row + 1)
                grid.pop()
            for col, value in enumerate(pattern):
                if value:
                    column_sums[col] -= row + 1
            if len(found) >= limit:
                return

    search(0)
    return found
