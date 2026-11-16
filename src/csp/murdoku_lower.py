"""Incremental lowering of Murdoku expression statements to model constraints."""

from __future__ import annotations

from . import murdoku_lang as lang
from .core import Kind, Model
from .murdoku import Board, Square
from .murdoku_typecheck import check_formula


def _static_cells(board: Board, target: lang.Operand) -> set[Square] | None:
    if not isinstance(target, lang.Name):
        return None
    kind, separator, value = target.token.text.partition(":")
    if not separator:
        return None
    if kind == "area":
        region = board.region_id(value)
        return {square for square in board.free if board.region_of(square) == region}
    if kind == "mark":
        return board.mark_cells([value]) & set(board.free)
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
    if not (
        isinstance(formula, lang.NumberComparison)
        and isinstance(formula.left, lang.Count)
        and isinstance(formula.right, lang.Integer)
    ):
        return False
    check_formula(board, formula)
    keys = _counted_keys(board, formula.left.operand)
    if keys is None:
        return False
    missing = {variable for variable, _ in keys} - set(model.all_variables)
    if missing:
        raise ValueError(f"model lacks declared variables: {', '.join(sorted(missing))}")
    expected = int(formula.right.value.text)
    comparisons = {
        "=": lambda value: value == expected,
        "!=": lambda value: value != expected,
        "<": lambda value: value < expected,
        "<=": lambda value: value <= expected,
        ">": lambda value: value > expected,
        ">=": lambda value: value >= expected,
    }
    permitted = {
        value
        for value in range(min(len(keys), len(board.people)) + 1)
        if comparisons[formula.operator.text](value)
    }
    if not permitted:
        raise ValueError(
            f"line {formula.operator.line}, column {formula.operator.column}: "
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
