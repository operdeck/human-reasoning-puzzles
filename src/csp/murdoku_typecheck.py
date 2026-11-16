"""Board-dependent type checking for the planned Murdoku clue language."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from . import murdoku_lang as lang

if TYPE_CHECKING:
    from .murdoku import Board


class Sort(Enum):
    PERSON = "person"
    AREA = "area"
    ROW = "row"
    COLUMN = "column"
    CELL = "cell"
    FEATURE = "feature"
    ROLE = "role"


@dataclass(frozen=True)
class Shape:
    sort: Sort
    maximum: int
    minimum: int = 0


def _error(token: lang.Token, message: str) -> ValueError:
    return ValueError(f"line {token.line}, column {token.column}: {message}")


def _location(operand: lang.Operand) -> lang.Token:
    match operand:
        case lang.Name(token=token):
            return token
        case lang.Union(items=items):
            return _location(items[0])
        case lang.Difference(left=left):
            return _location(left)
        case lang.Qualified(adjective=token) | lang.Projection(kind=token):
            return token
        case lang.Filter(source=source) | lang.AdjectiveFilter(source=source):
            return _location(source)
        case lang.Comprehension(variable=token):
            return token


def _line_count(token: lang.Token, value: str, size: int) -> int:
    first, separator, last = value.partition("-")

    def index(text: str) -> int:
        if text == "last":
            return size
        if text.isdecimal():
            return int(text)
        raise _error(token, f"invalid line selector {value!r}")

    start = index(first)
    end = index(last) if separator else start
    if not 1 <= start <= end <= size:
        raise _error(token, f"line selector {value!r} must be between 1 and {size}")
    return end - start + 1


def _name(
    board: Board,
    token: lang.Token,
    bindings: dict[str, Shape],
    namespace: str | None = None,
) -> Shape:
    text = token.text
    if text.startswith("?"):
        if text not in bindings:
            raise _error(token, f"unbound variable {text!r}")
        return bindings[text]
    universes = {
        "people": (Sort.PERSON, len(board.people)),
        "areas": (Sort.AREA, len(board.region_names)),
        "rows": (Sort.ROW, board.size),
        "columns": (Sort.COLUMN, board.size),
        "cells": (Sort.CELL, board.size**2),
        "objects": (Sort.FEATURE, len(board.objects)),
        "roles": (Sort.ROLE, len(board.roles)),
    }
    if text in board.people:
        return Shape(Sort.PERSON, 1, 1)
    if text in universes:
        sort, count = universes[text]
        return Shape(sort, count, count)
    if ":" not in text and namespace:
        text = f"{namespace}:{text}"
    kind, separator, value = text.partition(":")
    if not separator:
        raise _error(token, f"unknown person or set {text!r}")
    if kind == "area":
        if value not in board.region_names.values():
            raise _error(token, f"unknown area {value!r}")
        return Shape(Sort.AREA, 1, 1)
    if kind == "tag":
        if value not in board.area_tags:
            raise _error(token, f"unknown area tag {value!r}")
        count = len(set(board.area_tags[value]))
        return Shape(Sort.AREA, count, count)
    if kind == "attribute":
        if value not in board.attributes:
            raise _error(token, f"unknown attribute {value!r}")
        count = len(board.attributes[value])
        return Shape(Sort.PERSON, count, count)
    if kind == "role":
        for role in board.roles:
            if role.name == value:
                return Shape(
                    Sort.PERSON,
                    min(max(role.allowed_counts), len(board.people)),
                    min(role.allowed_counts),
                )
        raise _error(token, f"unknown role {value!r}")
    if kind in {"rows", "columns"}:
        sort = Sort.ROW if kind == "rows" else Sort.COLUMN
        count = _line_count(token, value, board.size)
        return Shape(sort, count, count)
    if kind == "corner" and value == "board":
        count = min(4, board.size**2)
        return Shape(Sort.CELL, count, count)
    if kind == "object_kind":
        if value not in {"standable", "blocking"}:
            raise _error(token, f"unknown object kind {value!r}")
        count = sum(obj.kind == value for obj in board.objects)
        return Shape(Sort.FEATURE, count, count)
    features = {
        "object": [item.name for item in board.objects],
        "edge_item": [item.name for item in board.edge_items],
        "point_object": [item.name for item in board.point_objects],
        "mark": [item.name for item in board.marks],
    }
    if kind in features:
        count = features[kind].count(value)
        if not count:
            raise _error(token, f"unknown {kind} {value!r}")
        return Shape(Sort.FEATURE, count, count)
    raise _error(token, f"unknown namespace {kind!r}")


def _universe(board: Board, sort: Sort) -> int:
    return {
        Sort.PERSON: len(board.people),
        Sort.AREA: len(board.region_names),
        Sort.ROW: board.size,
        Sort.COLUMN: board.size,
        Sort.CELL: board.size**2,
        Sort.FEATURE: len(board.objects)
        + len(board.edge_items)
        + len(board.point_objects)
        + len(board.marks),
        Sort.ROLE: len(board.roles),
    }[sort]


def _same_sort(left: Shape, right: Shape, token: lang.Token) -> None:
    if left.sort != right.sort:
        raise _error(token, f"mixed sorts: {left.sort.value} and {right.sort.value}")


def _adjective(shape: Shape, adjective: lang.Token) -> None:
    permitted = (
        {Sort.CELL}
        if adjective.text == "free"
        else {
            Sort.CELL,
            Sort.ROW,
            Sort.COLUMN,
            Sort.AREA,
            Sort.FEATURE,
        }
    )
    if shape.sort not in permitted:
        raise _error(adjective, f"{adjective.text!r} cannot qualify {shape.sort.value}")


def _relation(subject: Shape, operator: lang.Token, target: Shape) -> None:
    if operator.text == "is":
        if subject.sort == Sort.PERSON and target.sort == Sort.ROLE:
            return
        _same_sort(subject, target, operator)
    elif subject.sort == Sort.ROLE or target.sort == Sort.ROLE:
        raise _error(operator, f"{operator.text!r} requires entities with footprints")
    if operator.text.startswith(("dir:nearest", "dir:furthest")) and subject.sort != Sort.PERSON:
        raise _error(operator, "a superlative requires a person on the left")


def infer_operand(
    board: Board, operand: lang.Operand, bindings: dict[str, Shape] | None = None
) -> Shape:
    """Infer an operand's entity sort and a conservative upper cardinality."""
    variables = {} if bindings is None else bindings
    match operand:
        case lang.Name(token=token):
            return _name(board, token, variables)
        case lang.Union(items=items):
            first = infer_operand(board, items[0], variables)
            maximum = first.maximum
            minimum = first.minimum
            namespace = None
            if isinstance(items[0], lang.Name):
                namespace = items[0].token.text.partition(":")[0] or None
                if ":" not in items[0].token.text:
                    namespace = None
            seen = {items[0].token.text} if isinstance(items[0], lang.Name) else set()
            for item in items[1:]:
                if isinstance(item, lang.Name):
                    token = item.token
                    shape = _name(board, token, variables, namespace)
                    key = (
                        token.text
                        if ":" in token.text or token.text in board.people
                        else (f"{namespace}:{token.text}")
                    )
                    if key not in seen:
                        maximum += shape.maximum
                        seen.add(key)
                else:
                    shape = infer_operand(board, item, variables)
                    maximum += shape.maximum
                _same_sort(first, shape, _location(item))
                minimum = max(minimum, shape.minimum)
            return Shape(first.sort, min(maximum, _universe(board, first.sort)), minimum)
        case lang.Difference(left=left, right=right):
            left_shape = infer_operand(board, left, variables)
            _same_sort(left_shape, infer_operand(board, right, variables), _location(right))
            return Shape(left_shape.sort, left_shape.maximum)
        case lang.Qualified(adjective=adjective, operand=inner):
            shape = infer_operand(board, inner, variables)
            _adjective(shape, adjective)
            return Shape(shape.sort, shape.maximum)
        case lang.Projection(kind=kind, operand=inner):
            source = infer_operand(board, inner, variables)
            if source.sort == Sort.ROLE:
                raise _error(kind, "a projection requires an entity with a footprint")
            sort = {
                "area": Sort.AREA,
                "row": Sort.ROW,
                "column": Sort.COLUMN,
                "cell": Sort.CELL,
            }[kind.text]
            maximum = (
                source.maximum
                if source.sort in {Sort.PERSON, Sort.CELL} or source.sort == sort
                else _universe(board, sort)
            )
            return Shape(sort, min(maximum, _universe(board, sort)), int(source.minimum > 0))
        case lang.Filter(source=source, operator=operator, target=target, measure=measure):
            shape = infer_operand(board, source, variables)
            _relation(shape, operator, infer_operand(board, target, variables))
            _measure(operator, measure)
            return Shape(shape.sort, shape.maximum)
        case lang.AdjectiveFilter(source=source, adjective=adjective):
            shape = infer_operand(board, source, variables)
            _adjective(shape, adjective)
            return Shape(shape.sort, shape.maximum)
        case lang.Comprehension(variable=variable, source=source, condition=condition):
            shape = infer_operand(board, source, variables)
            check_formula(board, condition, variables | {variable.text: Shape(shape.sort, 1, 1)})
            return Shape(shape.sort, shape.maximum)


def _measure(operator: lang.Token, measure: lang.Measure | None) -> None:
    if not operator.text.startswith("dir:"):
        return
    mode = operator.text.removeprefix("dir:")
    directions = {"left", "right", "up", "down"}
    metrics = {"rows", "cols", "manhattan", "king", "euclidean", "areas"}
    if "+" in mode:
        parts = mode.split("+")
        valid = (
            len(parts) == 2
            and all(part in directions for part in parts)
            and len(set(parts) & {"up", "down"}) == 1
            and len(set(parts) & {"left", "right"}) == 1
        )
    elif mode.startswith(("nearest", "furthest")):
        word, separator, metric = mode.partition(":")
        valid = word in {"nearest", "furthest"} and (not separator or metric in metrics)
    else:
        valid = mode in directions | metrics | {"diagonal", "knight"}
    if not valid:
        raise _error(operator, f"unknown direction mode {mode!r}")
    if measure and (mode == "knight" or mode.startswith(("nearest", "furthest"))):
        raise _error(measure.comparison, f"{mode!r} does not take a measure")
    if mode in metrics and measure is None:
        raise _error(operator, f"{mode!r} requires a measure")
    if (
        measure
        and (mode in directions or "+" in mode or mode == "diagonal")
        and measure.comparison.text in {"=", "<="}
        and int(measure.value.text) == 0
    ):
        raise _error(measure.value, "directional comparison has no feasible value")


def _number_bounds(
    board: Board, number: lang.Number, bindings: dict[str, Shape]
) -> tuple[int, int]:
    match number:
        case lang.Integer(value=value):
            return int(value.text), int(value.text)
        case lang.Count(operand=operand):
            shape = infer_operand(board, operand, bindings)
            return shape.minimum, shape.maximum
        case lang.Arithmetic(left=left, operator=operator, right=right):
            low, high = _number_bounds(board, left, bindings)
            other_low, other_high = _number_bounds(board, right, bindings)
            if operator.text == "+":
                return low + other_low, high + other_high
            return low - other_high, high - other_low


def _comparison(left: tuple[int, int], operator: lang.Token, right: tuple[int, int]) -> None:
    low, high = left
    other_low, other_high = right
    feasible = {
        "=": low <= other_high and other_low <= high,
        "!=": not (low == high == other_low == other_high),
        "<": low < other_high,
        "<=": low <= other_high,
        ">": high > other_low,
        ">=": high >= other_low,
    }[operator.text]
    if not feasible:
        raise _error(operator, "comparison has no feasible value")


def check_formula(
    board: Board, formula: lang.Formula, bindings: dict[str, Shape] | None = None
) -> None:
    """Check the sorts and conservative cardinalities of a parsed formula."""
    variables = {} if bindings is None else bindings
    match formula:
        case lang.Atom(subject=subject, operator=operator, target=target, determiner=determiner):
            left = infer_operand(board, subject, variables)
            right = infer_operand(board, target, variables)
            _relation(left, operator, right)
            _measure(operator, formula.measure)
            if left.maximum > 1 and determiner is None:
                raise _error(
                    _location(subject),
                    "multi-element left operand needs a determiner: write some, every, or no",
                )
        case lang.AdjectiveAtom(subject=subject, adjective=adjective, determiner=determiner):
            shape = infer_operand(board, subject, variables)
            _adjective(shape, adjective)
            if shape.maximum > 1 and determiner is None:
                raise _error(
                    _location(subject),
                    "multi-element left operand needs a determiner: write some, every, or no",
                )
        case lang.SetComparison(left=left, operator=operator, right=right):
            _same_sort(
                infer_operand(board, left, variables),
                infer_operand(board, right, variables),
                operator,
            )
        case lang.Negation(formula=inner):
            check_formula(board, inner, variables)
        case lang.Binary(left=left, right=right):
            check_formula(board, left, variables)
            check_formula(board, right, variables)
        case lang.NumberComparison(left=left, operator=operator, right=right):
            _comparison(
                _number_bounds(board, left, variables),
                operator,
                _number_bounds(board, right, variables),
            )
        case lang.Parity(number=number, parity=parity):
            low, high = _number_bounds(board, number, variables)
            wanted = int(parity.text == "odd")
            if low + ((wanted - low) % 2) > high:
                raise _error(parity, "comparison has no feasible value")
        case lang.NumberRange(number=number, lower=lower, upper=upper):
            low, high = _number_bounds(board, number, variables)
            if int(lower.text) > int(upper.text) or low > int(upper.text) or high < int(lower.text):
                raise _error(lower, "range has no feasible value")
        case lang.Quantified(
            quantifier=quantifier, count=count, variables=names, source=source, body=body
        ):
            shape = infer_operand(board, source, variables)
            if (
                count
                and " ".join(quantifier.text.split()) in {"exactly", "at least"}
                and int(count.text) > shape.maximum
            ):
                raise _error(count, "quantifier has no feasible value")
            nested = variables | {name.text: Shape(shape.sort, 1, 1) for name in names}
            check_formula(board, body, nested)
        case lang.Choice(quantifier=quantifier, count=count, choices=choices):
            if " ".join(quantifier.text.split()) in {"exactly", "at least"} and int(
                count.text
            ) > len(choices):
                raise _error(count, "choice has no feasible value")
            for choice in choices:
                check_formula(board, choice, variables)
