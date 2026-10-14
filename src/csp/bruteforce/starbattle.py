"""Star Battle by row-pattern backtracking, independent of the engine."""

from itertools import combinations, pairwise

from ..starbattle import cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    size, stars = puzzle.size, puzzle.stars
    patterns = [
        pattern
        for pattern in combinations(range(size), stars)
        if all(second - first > 1 for first, second in pairwise(pattern))
    ]
    region_of = puzzle.areas.cells
    col_counts = [0] * size
    region_counts = {region: 0 for region in puzzle.areas.names}
    grid = [[False] * size for _ in range(size)]
    found: list[dict[str, bool]] = []

    def search(row: int, previous: tuple[int, ...]) -> None:
        if row == size:
            if all(count == stars for count in col_counts) and all(
                count == stars for count in region_counts.values()
            ):
                found.append(
                    {cell_name((r, c)): grid[r][c] for r in range(size) for c in range(size)}
                )
            return
        for pattern in patterns:
            if any(
                puzzle.givens[row][col] >= 0 and bool(puzzle.givens[row][col]) != (col in pattern)
                for col in range(size)
            ):
                continue
            if any(abs(col - old_col) <= 1 for col in pattern for old_col in previous):
                continue
            if any(col_counts[col] >= stars for col in pattern):
                continue
            regions = [region_of[row][col] for col in pattern]
            if any(region_counts[region] >= stars for region in regions):
                continue
            for col in pattern:
                col_counts[col] += 1
                grid[row][col] = True
                region_counts[region_of[row][col]] += 1
            remaining = size - row - 1
            if all(count + remaining >= stars for count in col_counts) and all(
                count + remaining * size >= stars for count in region_counts.values()
            ):
                search(row + 1, pattern)
            for col in pattern:
                col_counts[col] -= 1
                grid[row][col] = False
                region_counts[region_of[row][col]] -= 1
            if len(found) >= limit:
                return

    search(0, ())
    return found
