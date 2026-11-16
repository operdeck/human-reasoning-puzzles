"""Incremental lowering of Murdoku expression statements to model constraints."""

from __future__ import annotations

from collections.abc import Callable

from . import murdoku_lang as lang
from .core import Kind, Model
from .murdoku import Board, Square, _direction_test
from .murdoku_typecheck import check_formula


def _static_cells(
    board: Board, target: lang.Operand, namespace: str | None = None
) -> set[Square] | None:
    if isinstance(target, lang.Union):
        first_item = target.items[0]
        inherited = (
            first_item.token.text.partition(":")[0]
            if isinstance(first_item, lang.Name) and ":" in first_item.token.text
            else None
        )
        cells: set[Square] = set()
        for item in target.items:
            part = _static_cells(board, item, inherited)
            if part is None:
                return None
            cells.update(part)
        return cells
    if not isinstance(target, lang.Name):
        return None
    text = target.token.text
    if text in {"areas", "rows", "columns", "cells"}:
        return set(board.free)
    if text == "objects":
        return {square for obj in board.objects for square in obj.squares} & set(board.free)
    if ":" not in text and namespace:
        text = f"{namespace}:{text}"
    kind, separator, value = text.partition(":")
    if not separator:
        return None
    if kind == "area":
        region = board.region_id(value)
        return {square for square in board.free if board.region_of(square) == region}
    if kind == "tag":
        regions = board.tagged_region_ids([value])
        return {square for square in board.free if board.region_of(square) in regions}
    if kind == "mark":
        return board.mark_cells([value]) & set(board.free)
    if kind == "object":
        return board.squares_of([value]) & set(board.free)
    if kind == "edge_item":
        return board.edge_item_cells([value]) & set(board.free)
    if kind == "point_object":
        return board.point_object_cells([value]) & set(board.free)
    if kind == "object_kind":
        return {
            square
            for obj in board.objects
            if obj.kind == value
            for square in obj.squares
            if square in board.free
        }
    if kind in {"rows", "columns"}:
        first, has_end, last = value.partition("-")
        start = board.size if first == "last" else int(first)
        end = (board.size if last == "last" else int(last)) if has_end else start
        return {
            square
            for square in board.free
            if start <= (square.row if kind == "rows" else square.col) + 1 <= end
        }
    if kind == "corner" and value == "board":
        edge = {0, board.size - 1}
        return {square for square in board.free if square.row in edge and square.col in edge}
    return None


def _counted_keys(board: Board, operand: lang.Operand) -> list[tuple[str, Square | bool]] | None:
    if isinstance(operand, lang.Name) and operand.token.text.startswith("role:"):
        role = operand.token.text.removeprefix("role:")
        return [(board.role_variable(person, role), True) for person in board.people]
    if (
        isinstance(operand, lang.Filter)
        and isinstance(operand.source, lang.Name)
        and operand.source.token.text == "people"
        and operand.operator.text in {"in", "on"}
    ):
        cells = _static_cells(board, operand.target)
        if cells is not None:
            return [(person, square) for person in board.people for square in sorted(cells)]
    return None


def try_lower_location(model: Model, board: Board, statement: lang.Statement, name: str) -> bool:
    """Lower a named person's static containment or overlap as domain eliminations."""
    formula = statement.formula
    negated = isinstance(formula, lang.Negation)
    atom = formula.formula if isinstance(formula, lang.Negation) else formula
    if not (
        isinstance(atom, lang.Atom)
        and isinstance(atom.subject, lang.Name)
        and atom.subject.token.text in board.people
        and atom.operator.text in {"in", "on"}
    ):
        return False
    check_formula(board, formula)
    cells = _static_cells(board, atom.target)
    if cells is None:
        return False
    person = atom.subject.token.text
    if person not in model.all_variables:
        raise ValueError(f"model lacks declared variable: {person}")
    exclude = negated ^ (atom.determiner is not None and atom.determiner.text == "no")
    for square in board.free:
        if (square in cells) == exclude:
            model.eliminate(model.literal(person, square), "clue", name, sources=(name,))
    return True


def try_lower_person_pair(model: Model, board: Board, statement: lang.Statement, name: str) -> bool:
    """Lower a supported relation between named people to a binary relation."""
    formula = statement.formula
    negated = isinstance(formula, lang.Negation)
    atom = formula.formula if isinstance(formula, lang.Negation) else formula
    if not (
        isinstance(atom, lang.Atom)
        and isinstance(atom.subject, lang.Name)
        and isinstance(atom.target, lang.Name)
        and atom.subject.token.text in board.people
        and atom.target.token.text in board.people
    ):
        return False
    check_formula(board, formula)
    first, second = atom.subject.token.text, atom.target.token.text
    missing = {first, second} - set(model.all_variables)
    if missing:
        raise ValueError(f"model lacks declared variables: {', '.join(sorted(missing))}")
    op = atom.operator.text
    same = first == second
    test: Callable[[Square, Square], bool]
    if op == "is":

        def identity(_first: Square, _second: Square) -> bool:
            return same

        test = identity
    elif op in {"in", "on"}:

        def overlaps(left: Square, right: Square) -> bool:
            return left == right

        test = overlaps
    elif op in {"beside", "touches"}:

        def touching(left: Square, right: Square) -> bool:
            return (
                not same
                and abs(left.row - right.row) + abs(left.col - right.col) == 1
                and (op == "touches" or board.region_of(left) == board.region_of(right))
            )

        test = touching
    elif op.startswith("dir:"):
        mode = op.removeprefix("dir:")
        simple_directions = {"up", "down", "left", "right"}
        metrics = {"rows", "cols", "manhattan", "king", "euclidean", "areas", "knight"}
        directions = mode.split("+")
        if mode not in simple_directions | metrics | {"diagonal"} and not all(
            direction in simple_directions for direction in directions
        ):
            return False
        comparison = atom.measure.comparison.text if atom.measure else None
        distance = int(atom.measure.value.text) if atom.measure else None
        direction = _direction_test(board, mode, comparison, distance) if mode in metrics else None

        def matches(value: int) -> bool:
            if distance is None:
                return True
            if comparison == "=":
                return value == distance
            if comparison == "<=":
                return value <= distance
            return value >= distance

        def directed(left: Square, right: Square) -> bool:
            if same:
                return False
            if direction is not None:
                return direction(left, right)
            if mode == "diagonal":
                gap = abs(left.row - right.row)
                return gap > 0 and gap == abs(left.col - right.col) and matches(gap)
            gaps = {
                "up": right.row - left.row,
                "down": left.row - right.row,
                "left": right.col - left.col,
                "right": left.col - right.col,
            }
            return all(gaps[component] > 0 and matches(gaps[component]) for component in directions)

        test = directed
    else:
        return False
    invert = negated ^ (atom.determiner is not None and atom.determiner.text == "no")
    if same:
        model.relate(name, (first,), lambda square: test(square, square) != invert)
    else:
        model.relate(name, (first, second), lambda left, right: test(left, right) != invert)
    return True


def try_lower_count(model: Model, board: Board, statement: lang.Statement, name: str) -> bool:
    """Lower supported top-level counts; return false without changes for other shapes."""
    formula = statement.formula
    predicate: Callable[[int], bool]
    match formula:
        case lang.NumberComparison(
            left=lang.Count(operand=operand), operator=operator, right=lang.Integer(value=value)
        ):
            expected = int(value.text)
            predicate = {
                "=": lambda actual: actual == expected,
                "!=": lambda actual: actual != expected,
                "<": lambda actual: actual < expected,
                "<=": lambda actual: actual <= expected,
                ">": lambda actual: actual > expected,
                ">=": lambda actual: actual >= expected,
            }[operator.text]
            location = operator
        case lang.Parity(number=lang.Count(operand=operand), parity=parity):
            remainder = int(parity.text == "odd")

            def parity_matches(actual: int) -> bool:
                return actual % 2 == remainder

            predicate = parity_matches
            location = parity
        case lang.NumberRange(number=lang.Count(operand=operand), lower=lower, upper=upper):
            start, end = int(lower.text), int(upper.text)

            def range_matches(actual: int) -> bool:
                return start <= actual <= end

            predicate = range_matches
            location = lower
        case _:
            return False
    check_formula(board, formula)
    keys = _counted_keys(board, operand)
    if keys is None:
        return False
    missing = {variable for variable, _ in keys} - set(model.all_variables)
    if missing:
        raise ValueError(f"model lacks declared variables: {', '.join(sorted(missing))}")
    permitted = {
        value for value in range(min(len(keys), len(board.people)) + 1) if predicate(value)
    }
    if not permitted:
        raise ValueError(
            f"line {location.line}, column {location.column}: "
            "comparison has no feasible value on this board"
        )
    model.constrain(
        name,
        Kind.COUNT,
        [model.literal(variable, value) for variable, value in keys],
        allowed_counts=permitted,
        family="Murdoku expression",
    )
    return True
