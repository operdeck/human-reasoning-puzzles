"""Tents and Trees by row-pattern backtracking, independent of the engine."""

from itertools import combinations, pairwise

from ..tents import cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    patterns = [
        tuple(cols)
        for row, count in enumerate(puzzle.row_counts)
        for cols in combinations(
            [col for col in range(puzzle.size) if (row, col) in puzzle.tent_candidates], count
        )
        if all(second - first > 1 for first, second in pairwise(cols))
    ]
    patterns_by_row = {
        row: [
            pattern
            for pattern in patterns
            if pattern and (row, pattern[0]) in puzzle.tent_candidates
        ]
        for row in range(puzzle.size)
    }
    patterns_by_row = {
        row: [
            pattern
            for pattern in combinations(
                [col for col in range(puzzle.size) if (row, col) in puzzle.tent_candidates],
                puzzle.row_counts[row],
            )
            if all(second - first > 1 for first, second in pairwise(pattern))
        ]
        for row in range(puzzle.size)
    }
    col_counts = [0] * puzzle.size
    tree_counts = {tree: 0 for tree in puzzle.trees}
    grid = [[False] * puzzle.size for _ in range(puzzle.size)]
    found: list[dict[str, bool]] = []

    def search(row: int, previous: tuple[int, ...]) -> None:
        if row == puzzle.size:
            if col_counts != puzzle.column_counts or any(
                count != 1 for count in tree_counts.values()
            ):
                return
            found.append(
                {
                    cell_name((r, c)): grid[r][c]
                    for r in range(puzzle.size)
                    for c in range(puzzle.size)
                }
            )
            return
        for pattern in patterns_by_row[row]:
            if any(abs(col - old_col) <= 1 for col in pattern for old_col in previous):
                continue
            if any(col_counts[col] >= puzzle.column_counts[col] for col in pattern):
                continue
            cells = [(row, col) for col in pattern]
            if any(len(puzzle.adjacent_trees(cell)) != 1 for cell in cells):
                continue
            for cell in cells:
                grid[cell[0]][cell[1]] = True
                col_counts[cell[1]] += 1
                tree_counts[puzzle.adjacent_trees(cell)[0]] += 1
            remaining = puzzle.size - row - 1
            if all(
                count + remaining >= target
                for count, target in zip(col_counts, puzzle.column_counts, strict=True)
            ):
                search(row + 1, pattern)
            for cell in cells:
                grid[cell[0]][cell[1]] = False
                col_counts[cell[1]] -= 1
                tree_counts[puzzle.adjacent_trees(cell)[0]] -= 1
            if len(found) >= limit:
                return

    search(0, ())
    return found
