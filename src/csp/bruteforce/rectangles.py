"""Rectangles by plain search: give each number a rectangle in turn on an occupancy grid."""

from ..rectangles import Cell, cell_name, cells_of, parse, rect_name


def solutions(text: str, limit: int = 2) -> list[dict[str, str]]:
    puzzle = parse(text)
    numbered = puzzle.numbered
    options = {cell: puzzle.candidates(cell) for cell in numbered}
    # Fewest candidates first keeps the search small.
    order = sorted(numbered, key=lambda cell: len(options[cell]))
    taken: set[Cell] = set()
    chosen: dict[str, str] = {}
    found: list[dict[str, str]] = []

    def search(index: int) -> None:
        if index == len(order):
            if len(taken) == puzzle.rows * puzzle.cols:
                found.append({cell_name(cell): chosen[cell_name(cell)] for cell in numbered})
            return
        cell = order[index]
        for rect in options[cell]:
            covered = set(cells_of(rect))
            if covered & taken:
                continue
            taken.update(covered)
            chosen[cell_name(cell)] = rect_name(rect)
            search(index + 1)
            del chosen[cell_name(cell)]
            taken.difference_update(covered)
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found
