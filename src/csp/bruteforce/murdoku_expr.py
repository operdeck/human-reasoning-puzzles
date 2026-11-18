"""Independent minimum-remaining-values search checked by the reference evaluator."""

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


def _placements(
    board: Board,
    checks: Sequence[Statement],
    order: Sequence[str],
    fixed: dict[str, Square],
    budget: list[int] | None,
) -> Iterator[dict[str, Square]]:
    placed: dict[str, Square] = {}
    grounded = [
        (statement, dependencies)
        for statement in checks
        if (dependencies := grounded_dependencies(board, statement)) is not None
    ]

    unary = {
        person: [statement for statement, dependencies in grounded if dependencies == {person}]
        for person in order
    }
    domains = {
        person: [
            square
            for square in ((fixed[person],) if person in fixed else board.free)
            if all(
                holds_grounded(statement, board, {person: square}, frozenset({person}))
                for statement in unary[person]
            )
        ]
        for person in order
    }
    linked = {
        person: [
            (statement, deps) for statement, deps in grounded if person in deps and len(deps) > 1
        ]
        for person in order
    }

    def search(
        remaining: Sequence[str], rows: set[int], columns: set[int]
    ) -> Iterator[dict[str, Square]]:
        if budget is not None:
            budget[0] -= 1
            if budget[0] < 0:
                return
        if not remaining:
            yield dict(placed)
            return
        choices: list[Square] | None = None
        chosen = remaining[0]
        for person in remaining:
            due = [
                (statement, deps)
                for statement, deps in linked[person]
                if deps <= placed.keys() | {person}
            ]
            candidates = []
            for square in domains[person]:
                if square.row in rows or square.col in columns:
                    continue
                placed[person] = square
                if all(
                    holds_grounded(statement, board, placed, dependencies)
                    for statement, dependencies in due
                ):
                    candidates.append(square)
                del placed[person]
            if not candidates:
                return
            if choices is None or len(candidates) < len(choices):
                chosen, choices = person, candidates
        assert choices is not None
        for square in choices:
            placed[chosen] = square
            yield from search(
                [person for person in remaining if person != chosen],
                rows | {square.row},
                columns | {square.col},
            )
            del placed[chosen]

    yield from search(order, set(), set())


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


def _checks(
    board: Board, statements: Sequence[Statement], rules: Sequence[Statement]
) -> list[Statement]:
    checks = [*declaration_statements(board), *rules, *statements]
    for statement in checks:
        check_formula(board, statement.formula)
    return checks


def accepts(
    board: Board,
    statements: Sequence[Statement],
    placed: dict[str, Square],
    *,
    rules: Sequence[Statement] = (),
) -> bool:
    """Whether a placement satisfies the board and expressions for some valid role assignment."""
    checks = _checks(board, statements, rules)
    if set(placed) != set(board.people):
        raise ValueError("placement must name every person exactly once")
    if any(square not in board.free for square in placed.values()):
        return False
    if len({square.row for square in placed.values()}) != len(placed) or len(
        {square.col for square in placed.values()}
    ) != len(placed):
        return False
    return any(
        all(holds(statement, board, placed, roles) for statement in checks)
        for roles in _roles(board, placed)
    )


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
    checks = _checks(board, statements, rules)
    return _solutions(board, checks, limit, board.people, {}, None)


def _solutions(
    board: Board,
    checks: Sequence[Statement],
    limit: int,
    order: Sequence[str],
    fixed: dict[str, Square],
    budget: list[int] | None,
) -> list[dict[str, Square | bool]]:
    placement_checks = [statement for statement in checks if not _mentions_roles(statement.formula)]
    role_checks = [statement for statement in checks if _mentions_roles(statement.formula)]
    # Role-independent checks cannot observe this complete placeholder assignment.
    placeholder_roles = {
        (person, role.name): False for role in board.roles for person in board.people
    }
    found: list[dict[str, Square | bool]] = []
    for placed in _placements(board, checks, order, fixed, budget):
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


def sample(
    board: Board,
    statements: Sequence[Statement],
    limit: int,
    *,
    rules: Sequence[Statement] = (),
) -> list[dict[str, Square | bool]]:
    """Sample distinct solutions across each person's possible starting squares."""
    if limit < 1:
        raise ValueError("solution limit must be positive")
    checks = _checks(board, statements, rules)
    spent = [10**12]
    plain = _solutions(board, checks, limit, board.people, {}, spent)
    branches = len(board.people) * len(board.free)
    nodes = max(200, (10**12 - spent[0]) // max(1, branches))
    each = max(1, -(-limit // max(1, branches)))
    found: set[tuple[tuple[str, Square | bool], ...]] = set()
    groups: list[list[dict[str, Square | bool]]] = []

    def keep(batch: list[dict[str, Square | bool]]) -> None:
        group = []
        for solution in batch:
            key = tuple(sorted(solution.items()))
            if key not in found:
                found.add(key)
                group.append(solution)
        groups.append(group)

    for person in board.people:
        order = [person, *(other for other in board.people if other != person)]
        for square in board.free:
            keep(_solutions(board, checks, each, order, {person: square}, [nodes]))
    keep(plain)
    spread = [
        group[i]
        for i in range(max(map(len, groups), default=0))
        for group in groups
        if i < len(group)
    ]
    return spread[:limit]
