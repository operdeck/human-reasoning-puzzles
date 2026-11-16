"""Incremental lowering of Murdoku expression statements to model constraints."""

from __future__ import annotations

from collections.abc import Callable

from . import murdoku_lang as lang
from .core import Kind, Model
from .murdoku import Board, Square
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
