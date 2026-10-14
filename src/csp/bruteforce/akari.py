"""Light Up/Akari by independent search over bulb positions."""

from ..akari import Cell, cell_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, bool]]:
    puzzle = parse(text)
    if limit <= 0:
        return []
    bulbs: set[Cell] = set()
    choices: dict[Cell, bool] = {}
    found: list[dict[str, bool]] = []

    def feasible() -> bool:
        if any(len(bulbs.intersection(segment)) > 1 for segment in puzzle.segments):
            return False
        for cell, clue in puzzle.numbered_walls():
            adjacent = puzzle.adjacent_open(cell)
            actual = len(bulbs.intersection(adjacent))
            possible = sum(
                member not in choices
                and not any(
                    member in segment and bulbs.intersection(segment) for segment in puzzle.segments
                )
                for member in adjacent
            )
            if not actual <= clue <= actual + possible:
                return False
        for cell in puzzle.open_cells:
            if cell in bulbs or any(member in bulbs for member in puzzle.visible[cell]):
                continue
            if not any(
                member not in choices
                and not any(
                    member in segment and bulbs.intersection(segment) for segment in puzzle.segments
                )
                for member in puzzle.visible[cell]
            ):
                return False
        return True

    def search(index: int) -> None:
        if index == len(puzzle.open_cells):
            if all(
                any(member in bulbs for member in puzzle.visible[cell])
                for cell in puzzle.open_cells
            ):
                found.append(
                    dict.fromkeys((cell_name(cell) for cell in puzzle.open_cells), False)
                    | {cell_name(cell): True for cell in bulbs}
                )
            return
        cell = puzzle.open_cells[index]
        for value in (False, True):
            choices[cell] = value
            if value:
                bulbs.add(cell)
            if feasible():
                search(index + 1)
            if value:
                bulbs.remove(cell)
            del choices[cell]
            if len(found) >= limit:
                return

    search(0)
    return found
