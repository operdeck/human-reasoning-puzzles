"""Suguru by independent backtracking over region-sized number domains."""

from ..suguru import Cell, cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    grid = [list(row) for row in puzzle.givens]
    used: dict[str, set[int]] = {region: set() for region in puzzle.cells_by_region}
    for row, values in enumerate(grid):
        for col, value in enumerate(values):
            if not value:
                continue
            cell = (row, col)
            region = puzzle.region_of[row][col]
            if value in used[region] or any(
                grid[nr][nc] == value for nr, nc in puzzle.neighbors(cell)
            ):
                return []
            used[region].add(value)

    found: list[dict[str, int]] = []

    def candidates(cell: Cell) -> list[int]:
        row, col = cell
        region = puzzle.region_of[row][col]
        neighbor_values = {grid[nr][nc] for nr, nc in puzzle.neighbors(cell) if grid[nr][nc]}
        return [
            value
            for value in range(1, puzzle.domain_size[cell] + 1)
            if value not in used[region] and value not in neighbor_values
        ]

    def search() -> None:
        best: tuple[Cell, list[int]] | None = None
        for row in range(puzzle.size):
            for col in range(puzzle.size):
                if grid[row][col]:
                    continue
                cell = (row, col)
                options = candidates(cell)
                if not options:
                    return
                if best is None or len(options) < len(best[1]):
                    best = cell, options
        if best is None:
            found.append(
                {
                    cell_name((row, col)): grid[row][col]
                    for row in range(puzzle.size)
                    for col in range(puzzle.size)
                }
            )
            return
        cell, options = best
        row, col = cell
        region = puzzle.region_of[row][col]
        for value in options:
            grid[row][col] = value
            used[region].add(value)
            search()
            used[region].remove(value)
            grid[row][col] = 0
            if len(found) >= limit:
                return

    search()
    return found
