"""Mosaic by plain search in reading order, checking every window the new cell touches."""

from ..mosaic import Cell, cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    n = puzzle.size
    black: dict[Cell, bool] = {}
    found: list[dict[str, bool]] = []

    def feasible(cell: Cell) -> bool:
        for near in puzzle.window(cell):
            clue = puzzle.clues[near[0]][near[1]]
            if clue is None:
                continue
            window = puzzle.window(near)
            known = sum(black.get(other) is True for other in window)
            open_cells = sum(other not in black for other in window)
            if not known <= clue <= known + open_cells:
                return False
        return True

    def search(index: int) -> None:
        if index == n * n:
            found.append({cell_name(cell): value for cell, value in black.items()})
            return
        cell = divmod(index, n)
        for value in (False, True):
            black[cell] = value
            if feasible(cell):
                search(index + 1)
            del black[cell]
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found
