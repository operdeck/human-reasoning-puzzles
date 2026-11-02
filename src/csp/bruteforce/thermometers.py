"""Thermometers by plain search over how far each thermometer is filled.

A thermometer's state is a fill level, 0 to its length; the filled cells are its first
`level` cells from the bulb. Line counts prune the search as thermometers are decided.
"""

from ..thermometers import Cell, cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    n = puzzle.size
    row_have, col_have = [0] * n, [0] * n
    # Cells not yet decided, per line, so a count can still be reached.
    row_room, col_room = [n] * n, [n] * n
    filled: dict[Cell, bool] = {}
    found: list[dict[str, bool]] = []
    order = sorted(puzzle.paths, key=len, reverse=True)

    def fits() -> bool:
        return all(
            row_have[i] <= puzzle.rows[i] <= row_have[i] + row_room[i]
            and col_have[i] <= puzzle.columns[i] <= col_have[i] + col_room[i]
            for i in range(n)
        )

    def search(index: int) -> None:
        if index == len(order):
            found.append({cell_name(cell): filled[cell] for cell in sorted(filled)})
            return
        path = order[index]
        for level in range(len(path) + 1):
            states = [i < level for i in range(len(path))]
            if any(
                puzzle.givens[r][c] >= 0 and bool(puzzle.givens[r][c]) != state
                for (r, c), state in zip(path, states, strict=True)
            ):
                continue
            for (r, c), state in zip(path, states, strict=True):
                filled[(r, c)] = state
                row_room[r] -= 1
                col_room[c] -= 1
                row_have[r] += state
                col_have[c] += state
            if fits():
                search(index + 1)
            for (r, c), state in zip(path, states, strict=True):
                del filled[(r, c)]
                row_room[r] += 1
                col_room[c] += 1
                row_have[r] -= state
                col_have[c] -= state
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found
