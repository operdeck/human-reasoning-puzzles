"""Battleships counts-only by independent row-pattern search."""

from itertools import combinations

from ..battleships import cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    patterns = [
        [
            pattern
            for pattern in combinations(range(puzzle.size), count)
            if all(puzzle.givens[row][col] < 0 or puzzle.givens[row][col] == 1 for col in pattern)
            and all(
                puzzle.givens[row][col] < 0 or puzzle.givens[row][col] == 0
                for col in range(puzzle.size)
                if col not in pattern
            )
        ]
        for row, count in enumerate(puzzle.row_counts)
    ]
    column_counts = [0] * puzzle.size
    grid = [[False] * puzzle.size for _ in range(puzzle.size)]
    found: list[dict[str, bool]] = []

    def search(row: int) -> None:
        if row == puzzle.size:
            if column_counts == puzzle.column_counts:
                found.append(
                    {
                        cell_name((r, c)): grid[r][c]
                        for r in range(puzzle.size)
                        for c in range(puzzle.size)
                    }
                )
            return
        remaining = puzzle.size - row - 1
        for pattern in patterns[row]:
            for col in pattern:
                column_counts[col] += 1
                grid[row][col] = True
            if all(
                current <= target <= current + remaining
                for current, target in zip(column_counts, puzzle.column_counts, strict=True)
            ):
                search(row + 1)
            for col in pattern:
                column_counts[col] -= 1
                grid[row][col] = False
            if len(found) >= limit:
                return

    search(0)
    return found
