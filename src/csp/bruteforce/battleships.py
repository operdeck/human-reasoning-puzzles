"""Independent row-pattern search, checking connected ship components directly."""

from collections import Counter
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

    def fleet_fits() -> bool:
        remaining = {(r, c) for r in range(puzzle.size) for c in range(puzzle.size) if grid[r][c]}
        lengths = []
        while remaining:
            start = remaining.pop()
            component = {start}
            todo = [start]
            while todo:
                r, c = todo.pop()
                for other in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                    if other in remaining:
                        remaining.remove(other)
                        component.add(other)
                        todo.append(other)
            if len({r for r, _ in component}) > 1 and len({c for _, c in component}) > 1:
                return False
            lengths.append(len(component))
            first, last = min(component), max(component)
            for cell in component:
                expected = (
                    "O"
                    if len(component) == 1
                    else (
                        "M"
                        if cell not in (first, last)
                        else (
                            ("W" if cell == first else "E")
                            if first[0] == last[0]
                            else ("N" if cell == first else "S")
                        )
                    )
                )
                if puzzle.segments[cell[0]][cell[1]] not in {".", "1", expected}:
                    return False
        return Counter(lengths) == Counter(puzzle.fleet)

    def search(row: int) -> None:
        if row == puzzle.size:
            if column_counts == puzzle.column_counts and (not puzzle.fleet or fleet_fits()):
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
            if (
                puzzle.fleet
                and row > 0
                and any(
                    0 <= other < puzzle.size and grid[row - 1][other]
                    for col in pattern
                    for other in (col - 1, col + 1)
                )
            ):
                continue
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
