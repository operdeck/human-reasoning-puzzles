"""Independent search for Murdoku boards with expression-language statements."""

from collections.abc import Iterator, Sequence
from dataclasses import fields, is_dataclass
from itertools import combinations

from ..murdoku import Board, Square
from ..murdoku_declarations import statements as declaration_statements
from ..murdoku_eval import grounded_dependencies, holds_grounded
from ..murdoku_lang import Name, Statement, holds
from ..murdoku_typecheck import check_formula


def _mentions_roles(value: object) -> bool:
    if isinstance(value, Name):
        return value.token.text == "roles" or value.token.text.startswith("role:")
    if isinstance(value, tuple):
        return any(_mentions_roles(item) for item in value)
    if is_dataclass(value):
        return any(_mentions_roles(getattr(value, item.name)) for item in fields(value))
    return False


def _placements(board: Board, checks: Sequence[Statement]) -> Iterator[dict[str, Square]]:
    placed: dict[str, Square] = {}
    grounded = [
        (statement, dependencies)
        for statement in checks
        if (dependencies := grounded_dependencies(board, statement)) is not None
    ]

    def search(index: int, rows: set[int], columns: set[int]) -> Iterator[dict[str, Square]]:
        if index == len(board.people):
            yield dict(placed)
            return
        person = board.people[index]
        for square in board.free:
            if square.row not in rows and square.col not in columns:
                placed[person] = square
                if all(
                    holds_grounded(statement, board, placed)
                    for statement, dependencies in grounded
                    if person in dependencies and dependencies <= placed.keys()
                ):
                    yield from search(index + 1, rows | {square.row}, columns | {square.col})
                del placed[person]

    yield from search(0, set(), set())


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
    board: Board,
    statements: Sequence[Statement],
    limit: int = 2,
    *,
    rules: Sequence[Statement] = (),
) -> list[dict[str, Square | bool]]:
    """Return up to `limit` solutions, evaluating statements only via `holds`."""
    if limit < 1:
        raise ValueError("solution limit must be positive")
    if board.rules:
        raise ValueError("board rules must be migrated to expression statements first")
    checks = [*declaration_statements(board), *rules, *statements]
    for statement in checks:
        check_formula(board, statement.formula)
    placement_checks = [statement for statement in checks if not _mentions_roles(statement.formula)]
    role_checks = [statement for statement in checks if _mentions_roles(statement.formula)]
    # Role-independent checks cannot observe this complete placeholder assignment.
    placeholder_roles = {
        (person, role.name): False for role in board.roles for person in board.people
    }
    found: list[dict[str, Square | bool]] = []
    for placed in _placements(board, checks):
        if not all(
            holds(statement, board, placed, placeholder_roles) for statement in placement_checks
        ):
            continue
        for roles in _roles(board, placed):
            if all(holds(statement, board, placed, roles) for statement in role_checks):
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
