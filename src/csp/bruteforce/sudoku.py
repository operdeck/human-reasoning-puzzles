"""Sudoku by plain search: fill the cell with fewest candidates, backtrack.

Shares only `sudoku.Puzzle.houses()`, the definition of what a Sudoku
requires, with the engine's compiler.
"""

from ..sudoku import Cell, Link, cell_name, parse

type Grid = list[list[int]]
type Peers = dict[Cell, list[Cell]]


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    grid = [list(row) for row in puzzle.grid]
    peers: Peers = {}
    for _, _, cells in puzzle.houses():
        for cell in cells:
            peers.setdefault(cell, []).extend(other for other in cells if other != cell)
    for first, second, _ in puzzle.anti_peers():
        peers.setdefault(first, []).append(second)
        peers.setdefault(second, []).append(first)
    if not _givens_consistent(grid, peers, puzzle.links):
        return []
    found: list[dict[str, int]] = []
    _search(grid, peers, puzzle.links, found, limit)
    return found


def _candidates(grid: Grid, peers: Peers, r: int, c: int) -> list[int]:
    used = {grid[pr][pc] for pr, pc in peers[r, c]}
    return [d for d in range(1, len(grid) + 1) if d not in used]


def _givens_consistent(grid: Grid, peers: Peers, links: tuple[Link, ...]) -> bool:
    for r in range(len(grid)):
        for c in range(len(grid)):
            if given := grid[r][c]:
                grid[r][c] = 0
                ok = given in _candidates(grid, peers, r, c)
                grid[r][c] = given
                if not ok:
                    return False
    return _links_consistent(grid, links)


def _links_consistent(grid: Grid, links: tuple[Link, ...]) -> bool:
    return all(
        not grid[first[0]][first[1]]
        or not grid[second[0]][second[1]]
        or link.holds(grid[first[0]][first[1]], grid[second[0]][second[1]])
        for link in links
        for first, second in ((link.first, link.second),)
    )


def _search(
    grid: Grid, peers: Peers, links: tuple[Link, ...], found: list[dict[str, int]], limit: int
) -> None:
    size = len(grid)
    best: tuple[int, int, list[int]] | None = None
    for r in range(size):
        for c in range(size):
            if grid[r][c] == 0:
                options = _candidates(grid, peers, r, c)
                if best is None or len(options) < len(best[2]):
                    best = (r, c, options)
    if best is None:
        found.append({cell_name(r, c): grid[r][c] for r in range(size) for c in range(size)})
        return
    r, c, options = best
    for d in options:
        grid[r][c] = d
        if _links_consistent(grid, links):
            _search(grid, peers, links, found, limit)
        grid[r][c] = 0
        if len(found) >= limit:
            return
