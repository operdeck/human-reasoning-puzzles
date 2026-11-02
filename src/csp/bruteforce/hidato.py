"""Hidato and Numbrix by plain search: grow the path from 1, one touching cell at a time."""

from ..hidato import Cell, cell_name, number_name, parse, touching


def solutions(text: str, limit: int = 2) -> list[dict[str, str]]:
    puzzle = parse(text)
    cells = set(puzzle.cells)
    given_at = {cell: k for k, cell in puzzle.givens.items()}
    where = puzzle.givens
    path: dict[int, Cell] = {}
    used: set[Cell] = set()
    found: list[dict[str, str]] = []

    def place(k: int, options: list[Cell]) -> None:
        for cell in options:
            if cell in used or given_at.get(cell, k) != k:
                continue
            path[k] = cell
            used.add(cell)
            search(k + 1)
            used.discard(cell)
            del path[k]
            if len(found) >= limit:
                return

    def search(k: int) -> None:
        if k > puzzle.count:
            found.append({number_name(n): cell_name(cell) for n, cell in path.items()})
            return
        if k in where:
            options = [where[k]]
        elif k == 1:
            options = sorted(cells)
        else:
            options = [c for c in sorted(cells) if touching(path[k - 1], c, puzzle.diagonal)]
        # The next given must still be reachable in the steps that remain.
        future = [n for n in where if n > k]
        if future:
            n = min(future)
            options = [c for c in options if _reach(c, where[n], n - k, puzzle.diagonal)]
        place(k, options)

    if limit > 0:
        search(1)
    return found


def _reach(start: Cell, goal: Cell, steps: int, diagonal: bool) -> bool:
    """Whether `goal` is within `steps` moves of `start` on an open board (a lower bound)."""
    dr, dc = abs(start[0] - goal[0]), abs(start[1] - goal[1])
    return (max(dr, dc) if diagonal else dr + dc) <= steps
