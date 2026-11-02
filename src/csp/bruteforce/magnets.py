"""Magnets by plain search over domino states, pruning on line counts and touching poles."""

from ..magnets import LEGAL_PAIRS, Cell, cell_name, parse, polarity


def solutions(text: str, limit: int = 2) -> list[dict[str, str]]:
    puzzle = parse(text)
    n = puzzle.size
    order = sorted(puzzle.dominoes.values(), key=lambda pair: pair[0])
    pole: dict[Cell, str] = {}
    found: list[dict[str, str]] = []
    pairs = sorted(LEGAL_PAIRS)

    def line_ok() -> bool:
        for clue, index, count in puzzle.clue_lines:
            cells = puzzle.line_cells(clue, index)
            sign = polarity(clue)
            have = sum(pole.get(cell) == sign for cell in cells)
            room = sum(cell not in pole for cell in cells)
            if not have <= count <= have + room:
                return False
        return True

    def touching_ok(cell: Cell) -> bool:
        r, c = cell
        mine = pole[cell]
        if mine == "0":
            return True
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            near = (r + dr, c + dc)
            if (
                near in pole
                and puzzle.ids[near[0]][near[1]] != puzzle.ids[r][c]
                and pole[near] == mine
            ):
                return False
        return True

    def search(index: int) -> None:
        if index == len(order):
            found.append({cell_name((r, c)): pole[r, c] for r in range(n) for c in range(n)})
            return
        first, second = order[index]
        for one, two in pairs:
            if any(
                given not in (".", value)
                for cell, value in ((first, one), (second, two))
                for given in (puzzle.givens[cell[0]][cell[1]],)
            ):
                continue
            pole[first], pole[second] = one, two
            if touching_ok(first) and touching_ok(second) and line_ok():
                search(index + 1)
            del pole[first], pole[second]
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found
