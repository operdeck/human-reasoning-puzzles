"""Murdoku by plain search: place people one at a time, most restricted first.

Each person takes a free square in an unused row and column; a clue is
tested as soon as everyone it mentions has been placed. Role holder sets are
enumerated independently after each person placement.
"""

from collections.abc import Sequence
from itertools import combinations
from typing import Any

from ..murdoku import (
    Board,
    Condition,
    GlobalCountCondition,
    QuantifiedCondition,
    RoleCondition,
    Square,
    conditions,
    global_count_conditions,
    quantified_conditions,
    role_conditions,
)
from ..puzzlefile import load_board


def solutions(text: str, limit: int = 2) -> list[dict[str, Any]]:
    board, clues = load_board(text)
    checks = conditions(board, clues)
    role_checks = role_conditions(board, clues)
    target_checks = quantified_conditions(board, clues)
    global_checks = global_count_conditions(board, clues)
    allowed = {
        person: [
            sq for sq in board.free if all(c.test(sq) for c in checks if c.people == (person,))
        ]
        for person in board.people
    }
    order = sorted(board.people, key=lambda p: len(allowed[p]))
    later = {person: i for i, person in enumerate(order)}
    # Test each multi-person condition when the last person it names is placed.
    due: dict[str, list[Condition]] = {p: [] for p in board.people}
    for check in checks:
        if len(check.people) > 1:
            due[max(check.people, key=later.__getitem__)].append(check)

    found: list[dict[str, Any]] = []
    _search(board, order, allowed, due, role_checks, target_checks, global_checks, {}, found, limit)
    return found


def _search(
    board: Board,
    order: list[str],
    allowed: dict[str, list[Square]],
    due: dict[str, list[Condition]],
    role_checks: list[RoleCondition],
    target_checks: list[QuantifiedCondition],
    global_checks: list[GlobalCountCondition],
    placed: dict[str, Square],
    found: list[dict[str, Any]],
    limit: int,
) -> None:
    if len(placed) == len(order):
        for roles in _role_assignments(
            board, role_checks, target_checks, global_checks, placed, limit - len(found)
        ):
            found.append({**placed, **roles})
            if len(found) >= limit:
                return
        return
    person = order[len(placed)]
    rows = {sq.row for sq in placed.values()}
    cols = {sq.col for sq in placed.values()}
    for sq in allowed[person]:
        if sq.row in rows or sq.col in cols:
            continue
        placed[person] = sq
        if all(
            check.test(*(placed[p] for p in check.people)) for check in due[person]
        ) and _global_counts_possible(board, global_checks, placed, len(order) - len(placed)):
            _search(
                board,
                order,
                allowed,
                due,
                role_checks,
                target_checks,
                global_checks,
                placed,
                found,
                limit,
            )
        del placed[person]
        if len(found) >= limit:
            return


def _global_counts_possible(
    board: Board,
    conditions: Sequence[GlobalCountCondition],
    placed: dict[str, Square],
    remaining: int,
) -> bool:
    for condition in conditions:
        if (
            condition.kind == "people_with"
            and condition.selector is not None
            and condition.selector.kind == "role"
        ):
            continue
        current = condition.count(board, placed, {})
        if condition.kind in ("people_on", "people_in"):
            minimum, maximum = current, min(condition.maximum(board), current + remaining)
        elif condition.kind in ("empty_areas", "empty_cells"):
            minimum, maximum = max(0, current - remaining), current
        else:
            minimum = maximum = current
        if not any(minimum <= count <= maximum for count in condition.allowed_counts):
            return False
    return True


def _role_assignments(
    board: Board,
    rules: Sequence[RoleCondition],
    target_checks: Sequence[QuantifiedCondition],
    global_checks: Sequence[GlobalCountCondition],
    placed: dict[str, Square],
    limit: int,
) -> list[dict[str, bool]]:
    """Enumerate role holder sets independently of the deduction model."""
    selected: dict[tuple[str, str], bool] = {}
    found: list[dict[str, bool]] = []

    def search(index: int) -> None:
        if len(found) >= limit:
            return
        if index == len(board.roles):
            if (
                _role_rules_hold(board, rules, placed, selected)
                and all(check.holds(board, placed, selected) for check in target_checks)
                and all(
                    check.count(board, placed, selected) in check.allowed_counts
                    for check in global_checks
                )
            ):
                found.append(
                    {
                        board.role_variable(person, role.name): selected[person, role.name]
                        for role in board.roles
                        for person in board.people
                    }
                )
            return

        role = board.roles[index]
        eligible = sorted(board.people if role.eligible_people is None else role.eligible_people)
        for count in sorted(role.allowed_counts):
            if count > len(eligible):
                continue
            for chosen in combinations(eligible, count):
                holders = set(chosen)
                if (
                    role.different_regions
                    and len({board.region_of(placed[person]) for person in holders}) != count
                ):
                    continue
                for person in board.people:
                    selected[person, role.name] = person in holders
                search(index + 1)
                if len(found) >= limit:
                    return

    search(0)
    return found


def _role_rules_hold(
    board: Board,
    rules: Sequence[RoleCondition],
    placed: dict[str, Square],
    roles: dict[tuple[str, str], bool],
) -> bool:
    def has(person: str, role: str) -> bool:
        return roles.get((person, role), False)

    for rule in rules:
        kind, args = rule.kind, rule.args
        if kind == "has_role" and not has(args[0], args[1]):
            return False
        if kind == "not_role" and has(args[0], args[1]):
            return False
        if kind == "some_role" and not any(has(args[0], role.name) for role in board.roles):
            return False
        if kind == "roleless" and any(has(args[0], role.name) for role in board.roles):
            return False
        if kind == "at_most_one_role" and sum(has(args[0], role.name) for role in board.roles) > 1:
            return False
        if kind == "role_subset" and any(
            _membership_matches(board, args[0], person, roles)
            and not _membership_matches(board, args[1], person, roles)
            for person in board.people
        ):
            return False
        if kind in ("role_in_tagged", "role_not_in_tagged") and has(args[0], args[1]):
            inside = board.region_of(placed[args[0]]) in board.tagged_region_ids([args[2]])
            if inside != (kind == "role_in_tagged"):
                return False
        if kind == "min_role_in_tagged":
            role, tag, minimum = args[0], args[1], int(args[2])
            for region in board.tagged_region_ids([tag]):
                count = sum(
                    has(person, role) and board.region_of(placed[person]) == region
                    for person in board.people
                )
                if count < minimum:
                    return False
        if kind in ("role_on", "role_not_on") and has(args[0], args[1]):
            targets = _target_cells(board, args[2:])
            on_target = placed[args[0]] in targets
            if on_target != (kind == "role_on"):
                return False
        if (
            kind == "role_next_to"
            and has(args[0], args[1])
            and not _next_to(board, placed[args[0]], args[2:])
        ):
            return False
        if kind == "role_below":
            person, role, *gap_arg = args
            gap = int(gap_arg[0]) if gap_arg else None
            square = placed[person]
            if not any(
                other != person
                and has(other, role)
                and placed[other].row < square.row
                and (gap is None or square.row - placed[other].row == gap)
                for other in board.people
            ):
                return False
        if kind == "sole_role_companion":
            person, role = args
            companions = [
                other
                for other in board.people
                if other != person
                and board.region_of(placed[other]) == board.region_of(placed[person])
            ]
            if len(companions) != 1 or not has(companions[0], role):
                return False
        if kind == "role_occupant":
            role, condition = args
            allowed = (0, 1) if condition == "alone" else range(2, len(board.people) + 1)
            for region in {board.region_of(square) for square in placed.values()}:
                triggered = any(
                    has(person, role) and board.region_of(placed[person]) == region
                    for person in board.people
                )
                occupants = sum(board.region_of(square) == region for square in placed.values())
                if triggered and occupants not in allowed:
                    return False
    return True


def _target_cells(board: Board, names: Sequence[str]) -> set[Square]:
    """Resolve role bindings independently from the engine's compiler."""
    cells: set[Square] = set()
    for name in names:
        if name in ("blocking", "standable"):
            cells.update(
                square for obj in board.objects if obj.kind == name for square in obj.squares
            )
        elif name in board.mark_names:
            cells.update(board.mark_cells([name]))
        elif name in board.object_names:
            cells.update(board.squares_of([name]))
        elif name in board.edge_item_names:
            cells.update(board.edge_item_cells([name]))
        elif name in board.point_object_names:
            cells.update(board.point_object_cells([name]))
    return cells


def _membership_matches(
    board: Board, selector: str, person: str, roles: dict[tuple[str, str], bool]
) -> bool:
    kind, separator, name = selector.partition(":")
    if not separator:
        kind, name = "role", selector
    if kind == "role":
        return roles.get((person, name), False)
    if kind == "attribute":
        return board.has_attribute(person, name)
    if kind == "person":
        return person == name
    raise ValueError(f"invalid membership selector {selector!r}")


def _next_to(board: Board, square: Square, names: Sequence[str]) -> bool:
    for name in names:
        if name in board.edge_item_names and square in board.edge_item_cells([name]):
            return True
        if name in board.point_object_names and square in board.point_object_cells([name]):
            return True
        if any(
            abs(square.row - target.row) + abs(square.col - target.col) == 1
            and board.region_of(square) == board.region_of(target)
            for target in _target_cells(board, [name])
        ):
            return True
    return False
