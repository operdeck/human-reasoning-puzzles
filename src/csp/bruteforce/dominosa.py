"""Dominosa by plain search: cover the first free cell with an unused domino, right or down."""

from ..dominosa import Cell, edge_name, parse, type_name


def solutions(text: str, limit: int = 2) -> list[dict[str, str]]:
    puzzle = parse(text)
    rows, cols = puzzle.rows, puzzle.cols
    covered: set[Cell] = set()
    used: dict[tuple[int, int], str] = {}
    found: list[dict[str, str]] = []

    def search(index: int) -> None:
        while index < rows * cols and divmod(index, cols) in covered:
            index += 1
        if index == rows * cols:
            found.append({type_name(*kind): value for kind, value in sorted(used.items())})
            return
        r, c = divmod(index, cols)
        for partner in ((r, c + 1), (r + 1, c)):
            if partner[0] >= rows or partner[1] >= cols or partner in covered:
                continue
            kind = puzzle.kind_of(((r, c), partner))
            if kind in used:
                continue
            used[kind] = edge_name(((r, c), partner))
            covered.update(((r, c), partner))
            search(index + 1)
            covered.difference_update(((r, c), partner))
            del used[kind]
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found
