"""Kakuro by plain search: digits cell by cell, a run checked as its last cell is filled."""

from ..kakuro import Cell, cell_name, parse, run_holds


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    cells = puzzle.whites
    order = {cell: i for i, cell in enumerate(cells)}
    runs_at: dict[int, list[tuple[tuple[Cell, ...], int]]] = {}
    for run in puzzle.runs:
        runs_at.setdefault(max(order[c] for c in run.cells), []).append((run.cells, run.total))
    every_run = [(run.cells, run.total) for run in puzzle.runs]
    value: dict[Cell, int] = {}
    found: list[dict[str, int]] = []

    def feasible(cell: Cell) -> bool:
        """Distinct digits so far, and the partial sums can still reach the total."""
        for cells, total in every_run:
            if cell not in cells:
                continue
            filled = [value[c] for c in cells if c in value]
            if len(set(filled)) != len(filled) or sum(filled) > total:
                return False
            left = len(cells) - len(filled)
            if left == 0:
                if sum(filled) != total:
                    return False
            elif sum(filled) + left > total or sum(filled) + 9 * left < total:
                return False
        return True

    def search(index: int) -> None:
        if index == len(cells):
            found.append({cell_name(c): value[c] for c in cells})
            return
        cell = cells[index]
        for digit in range(1, 10):
            value[cell] = digit
            if feasible(cell) and all(
                run_holds([value[c] for c in cs], total) for cs, total in runs_at.get(index, [])
            ):
                search(index + 1)
            del value[cell]
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found
