"""Minesweeper-style boards by independent Boolean constraint search."""

from ..minesweeper import Cell, cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    mines: dict[Cell, bool] = {}
    for row in range(puzzle.size):
        for col in range(puzzle.size):
            if puzzle.clues[row][col] is not None:
                mines[row, col] = False
    found: list[dict[str, bool]] = []

    def feasible() -> bool:
        for row in range(puzzle.size):
            for col in range(puzzle.size):
                clue = puzzle.clues[row][col]
                if clue is None:
                    continue
                neighbors = puzzle.neighbors((row, col))
                known = sum(mines.get(cell) is True for cell in neighbors)
                open_cells = sum(cell not in mines for cell in neighbors)
                if not known <= clue <= known + open_cells:
                    return False
        if puzzle.total_mines is not None:
            known = sum(mines.get(cell) is True for cell in puzzle.unknown)
            remaining = sum(cell not in mines for cell in puzzle.unknown)
            if not known <= puzzle.total_mines <= known + remaining:
                return False
        return True

    def search() -> None:
        if len(mines) == puzzle.size * puzzle.size:
            found.append({cell_name(cell): value for cell, value in mines.items()})
            return
        best: Cell | None = None
        best_pressure = -1
        for cell in puzzle.unknown:
            if cell in mines:
                continue
            pressure = sum(
                puzzle.clues[row][col] is not None
                for row in range(puzzle.size)
                for col in range(puzzle.size)
                if cell in puzzle.neighbors((row, col))
            )
            if pressure > best_pressure:
                best, best_pressure = cell, pressure
        assert best is not None
        for value in (False, True):
            mines[best] = value
            if feasible():
                search()
            del mines[best]
            if len(found) >= limit:
                return

    if feasible():
        search()
    return found
