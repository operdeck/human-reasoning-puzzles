"""Undead by plain search: monsters cell by cell with the totals as budgets.

A sight line is checked the moment its last cell is filled. The visibility rule (`seen`)
is shared with the compiler; walking the mirrors is done here on its own, from the grid.
"""

from ..undead import MONSTERS, Cell, Puzzle, cell_name, parse, seen


def solutions(text: str, limit: int = 2) -> list[dict[str, str]]:
    puzzle = parse(text)
    cells = puzzle.empty
    order = {cell: i for i, cell in enumerate(cells)}
    budget = dict(puzzle.totals)
    placed: dict[Cell, str] = {}
    found: list[dict[str, str]] = []
    due: dict[int, list[tuple[int, list[tuple[Cell, bool]]]]] = {}
    for side, index, count in ((s.side, s.index, s.count) for s in puzzle.sights):
        path = _walk(puzzle, side, index)
        if not path:
            if count != 0:
                return []
            continue
        last = max(order[cell] for cell, _ in path)
        due.setdefault(last, []).append((count, path))

    def search(index: int) -> None:
        if index == len(cells):
            found.append({cell_name(cell): placed[cell] for cell in cells})
            return
        cell = cells[index]
        for monster in MONSTERS:
            if budget[monster] == 0:
                continue
            budget[monster] -= 1
            placed[cell] = monster
            if all(
                sum(seen(placed[c], reflected) for c, reflected in path) == count
                for count, path in due.get(index, [])
            ):
                search(index + 1)
            del placed[cell]
            budget[monster] += 1
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found


def _walk(puzzle: Puzzle, side: str, index: int) -> list[tuple[Cell, bool]]:
    """Follow a sight line from a border cell, bouncing off mirrors, listing the empty cells."""
    rows, cols = puzzle.rows, puzzle.cols
    r, c, dr, dc = {
        "Top": (0, index, 1, 0),
        "Bottom": (rows - 1, index, -1, 0),
        "Left": (index, 0, 0, 1),
        "Right": (index, cols - 1, 0, -1),
    }[side]
    reflected = False
    path: list[tuple[Cell, bool]] = []
    while 0 <= r < rows and 0 <= c < cols:
        here = puzzle.grid[r][c]
        if here == "/":
            dr, dc, reflected = -dc, -dr, True
        elif here == "\\":
            dr, dc, reflected = dc, dr, True
        else:
            path.append(((r, c), reflected))
        r, c = r + dr, c + dc
    return path
