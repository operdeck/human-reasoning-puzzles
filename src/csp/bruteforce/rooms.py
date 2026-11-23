"""Brute force for the room puzzles: people choose rooms, capacities cap them."""

from ..rooms import Puzzle, needs_everyone, parse, people_of


def solutions(text: str, limit: int = 2) -> list[dict[str, str]]:
    """Find up to `limit` placements of people in rooms that satisfy every clue."""
    if limit <= 0:
        return []
    return _walk(parse(text), limit)


def count(text: str) -> int:
    """How many placements satisfy the room capacities and every clue."""
    return len(_walk(parse(text), None))


def _walk(puzzle: Puzzle, limit: int | None) -> list[dict[str, str]]:
    """Depth-first assignment of people to rooms, pruned on capacity and finished clues."""
    found: list[dict[str, str]] = []
    where: dict[str, str] = {}
    used = dict.fromkeys((room.key for room in puzzle.rooms), 0)
    whole = len(puzzle.people)

    def ready(clue) -> bool:
        """Whether the clue can be judged from the people placed so far."""
        if needs_everyone(clue):
            return len(where) == whole
        return people_of(clue) <= where.keys()

    def search() -> None:
        if len(where) == whole:
            found.append(dict(where))
            return
        person = puzzle.people[len(where)]
        for room in puzzle.rooms:
            if used[room.key] >= room.capacity:
                continue
            where[person] = room.key
            used[room.key] += 1
            if all(clue.holds(where, puzzle) for clue in puzzle.clues if ready(clue)):
                search()
            used[room.key] -= 1
            del where[person]
            if limit is not None and len(found) >= limit:
                return

    search()
    return found
