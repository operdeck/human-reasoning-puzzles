"""Independent search for Murdoku boards with expression-language statements."""

from collections.abc import Iterator, Sequence
from itertools import combinations

from ..murdoku import Board, Square
from ..murdoku_lang import Statement, holds
from ..murdoku_typecheck import check_formula


def _placements(board: Board) -> Iterator[dict[str, Square]]:
    placed: dict[str, Square] = {}

    def search(index: int, rows: set[int], columns: set[int]) -> Iterator[dict[str, Square]]:
        if index == len(board.people):
            yield dict(placed)
            return
        person = board.people[index]
        for square in board.free:
            if square.row not in rows and square.col not in columns:
                placed[person] = square
                yield from search(index + 1, rows | {square.row}, columns | {square.col})
                del placed[person]

    yield from search(0, set(), set())


def _marks_hold(board: Board, placed: dict[str, Square]) -> bool:
    for mark in board.marks:
        if mark.occupant_condition is None:
            continue
        for square in placed.values():
            if square in mark.cells:
                occupants = sum(
                    board.region_of(other) == board.region_of(square) for other in placed.values()
                )
                if mark.occupant_condition == "alone" and occupants != 1:
                    return False
                if mark.occupant_condition == "not_alone" and occupants < 2:
                    return False
    return True


def _roles(board: Board, placed: dict[str, Square]) -> Iterator[dict[tuple[str, str], bool]]:
    selected: dict[tuple[str, str], bool] = {}

    def search(index: int) -> Iterator[dict[tuple[str, str], bool]]:
        if index == len(board.roles):
            yield dict(selected)
            return
        role = board.roles[index]
        eligible = sorted(board.people if role.eligible_people is None else role.eligible_people)
        for count in sorted(role.allowed_counts):
            for holders_tuple in combinations(eligible, count):
                holders = set(holders_tuple)
                if (
                    role.different_regions
                    and len({board.region_of(placed[person]) for person in holders}) != count
                ):
                    continue
                for person in board.people:
                    selected[person, role.name] = person in holders
                yield from search(index + 1)

    yield from search(0)


def solutions(
    board: Board, statements: Sequence[Statement], limit: int = 2
) -> list[dict[str, Square | bool]]:
    """Return up to `limit` solutions, evaluating statements only via `holds`."""
    if limit < 1:
        raise ValueError("solution limit must be positive")
    if board.rules:
        raise ValueError("board rules must be migrated to expression statements first")
    for statement in statements:
        check_formula(board, statement.formula)
    found: list[dict[str, Square | bool]] = []
    for placed in _placements(board):
        if not _marks_hold(board, placed):
            continue
        for roles in _roles(board, placed):
            if all(holds(statement, board, placed, roles) for statement in statements):
                result: dict[str, Square | bool] = dict(placed)
                result.update(
                    {
                        board.role_variable(person, role): value
                        for (person, role), value in roles.items()
                    }
                )
                found.append(result)
                if len(found) >= limit:
                    return found
    return found
