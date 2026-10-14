"""Binairo/Tango by independent row-pattern backtracking."""

from itertools import product

from ..binairo import cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    size, half = puzzle.size, puzzle.size // 2

    def has_no_triples(pattern: tuple[bool, ...]) -> bool:
        return all(
            not (pattern[index] == pattern[index + 1] == pattern[index + 2])
            for index in range(size - 2)
        )

    patterns = [
        pattern
        for pattern in product((False, True), repeat=size)
        if sum(pattern) == half and has_no_triples(pattern)
    ]
    row_patterns = [
        [
            pattern
            for pattern in patterns
            if all(
                puzzle.givens[row][col] < 0 or bool(puzzle.givens[row][col]) == pattern[col]
                for col in range(size)
            )
        ]
        for row in range(size)
    ]
    grid: list[tuple[bool, ...]] = []
    found: list[dict[str, bool]] = []

    def links_hold() -> bool:
        values = {(row, col): grid[row][col] for row in range(len(grid)) for col in range(size)}
        return all(
            sign.holds(values[sign.first], values[sign.second])
            for sign in puzzle.signs
            if sign.first in values and sign.second in values
        )

    def search() -> None:
        row = len(grid)
        if row == size:
            columns = [tuple(grid[r][col] for r in range(size)) for col in range(size)]
            if len(set(columns)) != size:
                return
            if any(
                columns[col][r] == columns[col][r + 1] == columns[col][r + 2]
                for col in range(size)
                for r in range(size - 2)
            ):
                return
            if links_hold():
                found.append(
                    {cell_name((r, c)): grid[r][c] for r in range(size) for c in range(size)}
                )
            return

        for pattern in row_patterns[row]:
            if pattern in grid:
                continue
            if row >= 2 and any(
                grid[row - 1][col] == grid[row - 2][col] == pattern[col] for col in range(size)
            ):
                continue
            if not all(
                sign.holds(
                    pattern[sign.first[1]],
                    pattern[sign.second[1]],
                )
                for sign in puzzle.signs
                if sign.first[0] == sign.second[0] == row
            ):
                continue
            grid.append(pattern)
            if links_hold():
                search()
            grid.pop()
            if len(found) >= limit:
                return

    search()
    return found
