"""Zebra-style logic grids by independent position-assignment search."""

from ..logicgrid import parse


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    positions: dict[str, int] = {}
    used: dict[str, set[int]] = {category: set() for category in puzzle.categories}
    found: list[dict[str, int]] = []

    def candidates(item: str) -> list[int]:
        category = puzzle.category_of[item]
        options = [
            position for position in range(1, puzzle.size + 1) if position not in used[category]
        ]
        out = []
        for position in options:
            positions[item] = position
            valid = all(
                clue.holds(positions[clue.first], positions[clue.second])
                for clue in puzzle.clues
                if clue.first in positions and clue.second in positions
            )
            del positions[item]
            if valid:
                out.append(position)
        return out

    def search() -> None:
        if len(positions) == sum(map(len, puzzle.categories.values())):
            found.append(dict(positions))
            return
        best_item: str | None = None
        best_options: list[int] = []
        for items in puzzle.categories.values():
            for item in items:
                if item in positions:
                    continue
                options = candidates(item)
                if not options:
                    return
                if best_item is None or len(options) < len(best_options):
                    best_item, best_options = item, options
        assert best_item is not None
        category = puzzle.category_of[best_item]
        for position in best_options:
            positions[best_item] = position
            used[category].add(position)
            search()
            used[category].remove(position)
            del positions[best_item]
            if len(found) >= limit:
                return

    search()
    return found
