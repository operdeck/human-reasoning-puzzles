"""Map colouring by plain backtracking over regions, widest neighbourhood first."""

from ..mapcolour import COLOURS, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, str]]:
    puzzle = parse(text)
    touching: dict[str, set[str]] = {region: set() for region in puzzle.regions}
    for a, b in puzzle.borders:
        touching[a].add(b)
        touching[b].add(a)
    order = sorted(puzzle.regions, key=lambda region: -len(touching[region]))
    chosen: dict[str, str] = {}
    found: list[dict[str, str]] = []

    def search(index: int) -> None:
        if index == len(order):
            found.append({region: chosen[region] for region in puzzle.regions})
            return
        region = order[index]
        for colour in [puzzle.givens[region]] if region in puzzle.givens else COLOURS:
            if any(chosen.get(near) == colour for near in touching[region]):
                continue
            chosen[region] = colour
            search(index + 1)
            del chosen[region]
            if len(found) >= limit:
                return

    if limit > 0:
        search(0)
    return found
