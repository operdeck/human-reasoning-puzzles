"""Queens-style placement by plain backtracking, independent of the engine."""

from ..queens import Cell, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, Cell]]:
    """Return up to `limit` placements, one queen per region, row and column."""
    if limit <= 0:
        return []
    puzzle = parse(text)
    found: list[dict[str, Cell]] = []
    placements: dict[str, Cell] = {}
    rows: set[int] = set()
    columns: set[int] = set()
    for region, cell in puzzle.givens.items():
        if any(
            abs(cell.row - other.row) <= 1 and abs(cell.col - other.col) <= 1
            for other in placements.values()
        ):
            return []
        placements[region] = cell
        rows.add(cell.row)
        columns.add(cell.col)

    def candidates(region: str) -> list[Cell]:
        return [
            cell
            for cell in puzzle.cells_by_region[region]
            if cell.row not in rows
            and cell.col not in columns
            and not any(
                abs(cell.row - other.row) <= 1 and abs(cell.col - other.col) <= 1
                for other in placements.values()
            )
        ]

    def search() -> None:
        if len(placements) == puzzle.size:
            found.append(dict(placements))
            return

        best_region: str | None = None
        best_cells: list[Cell] = []
        for region in puzzle.region_ids:
            if region in placements:
                continue
            cells = candidates(region)
            if not cells:
                return
            if best_region is None or len(cells) < len(best_cells):
                best_region, best_cells = region, cells

        assert best_region is not None
        for cell in best_cells:
            placements[best_region] = cell
            rows.add(cell.row)
            columns.add(cell.col)
            search()
            del placements[best_region]
            rows.remove(cell.row)
            columns.remove(cell.col)
            if len(found) >= limit:
                return

    search()
    return found
