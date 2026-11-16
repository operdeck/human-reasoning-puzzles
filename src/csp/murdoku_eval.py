"""Reference semantics for the planned Murdoku expression language."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import permutations
from typing import assert_never

from . import murdoku_lang as lang
from .murdoku import Board, Square
from .murdoku_typecheck import Sort, check_formula


@dataclass(frozen=True)
class Entity:
    sort: Sort
    key: str | int | Square | tuple[str, int]
    footprint: frozenset[Square]


class _Evaluation:
    def __init__(
        self,
        board: Board,
        placed: Mapping[str, Square],
        roles: Mapping[tuple[str, str], bool],
    ) -> None:
        if set(placed) != set(board.people):
            raise ValueError("placement must name every person exactly once")
        if any(
            not (0 <= sq.row < board.size and 0 <= sq.col < board.size) for sq in placed.values()
        ):
            raise ValueError("placement contains a square outside the board")
        role_keys = {(person, role.name) for person in board.people for role in board.roles}
        if set(roles) != role_keys or any(not isinstance(value, bool) for value in roles.values()):
            raise ValueError("role assignments must contain a Boolean for every person and role")
        self.board = board
        self.placed = placed
        self.roles = roles
        self.cells = {
            square: Entity(Sort.CELL, square, frozenset({square}))
            for square in (
                Square(row, col) for row in range(board.size) for col in range(board.size)
            )
        }
        self.people = {
            name: Entity(Sort.PERSON, name, frozenset({placed[name]})) for name in board.people
        }
        self.rows = {
            row: Entity(
                Sort.ROW,
                row,
                frozenset(Square(row, col) for col in range(board.size)),
            )
            for row in range(board.size)
        }
        self.columns = {
            col: Entity(
                Sort.COLUMN,
                col,
                frozenset(Square(row, col) for row in range(board.size)),
            )
            for col in range(board.size)
        }
        self.areas = {
            region: Entity(
                Sort.AREA,
                region,
                frozenset(square for square in self.cells if board.region_of(square) == region),
            )
            for region in board.region_names
        }
        self.role_entities = {
            role.name: Entity(Sort.ROLE, role.name, frozenset()) for role in board.roles
        }
        self.features: dict[str, list[tuple[str, Entity]]] = {}
        for kind, entries in (
            ("object", [(obj.name, obj.squares) for obj in board.objects]),
            ("edge_item", [(item.name, item.cells) for item in board.edge_items]),
            ("point_object", [(item.name, item.cells) for item in board.point_objects]),
            ("mark", [(item.name, item.cells) for item in board.marks]),
        ):
            self.features[kind] = [
                (name, Entity(Sort.FEATURE, (kind, index), frozenset(cells)))
                for index, (name, cells) in enumerate(entries)
            ]

    def name(
        self, token: lang.Token, variables: Mapping[str, Entity], namespace: str | None = None
    ) -> set[Entity]:
        name = token.text
        if name.startswith("?"):
            return {variables[name]}
        if name in self.people:
            return {self.people[name]}
        universes = {
            "people": set(self.people.values()),
            "areas": set(self.areas.values()),
            "rows": set(self.rows.values()),
            "columns": set(self.columns.values()),
            "cells": set(self.cells.values()),
            "objects": {entity for _, entity in self.features["object"]},
            "roles": set(self.role_entities.values()),
        }
        if name in universes:
            return universes[name]
        if ":" not in name and namespace:
            name = f"{namespace}:{name}"
        kind, separator, value = name.partition(":")
        if not separator:
            raise ValueError(f"unknown person or set {name!r}")
        if kind == "area":
            return {self.areas[self.board.region_id(value)]}
        if kind == "tag":
            return {self.areas[area] for area in self.board.tagged_region_ids([value])}
        if kind == "attribute":
            return {self.people[person] for person in self.board.attributes[value]}
        if kind == "role":
            return {entity for person, entity in self.people.items() if self.roles[(person, value)]}
        if kind in {"rows", "columns"}:
            first, separator, last = value.partition("-")

            def index(text: str) -> int:
                return self.board.size if text == "last" else int(text)

            start = index(first)
            end = index(last) if separator else start
            lines = self.rows if kind == "rows" else self.columns
            return {lines[number - 1] for number in range(start, end + 1)}
        if kind == "corner" and value == "board":
            last_index = self.board.size - 1
            return {
                self.cells[Square(row, col)] for row in (0, last_index) for col in (0, last_index)
            }
        if kind == "object_kind":
            return {
                entity
                for index, obj in enumerate(self.board.objects)
                if obj.kind == value
                for _, entity in (self.features["object"][index],)
            }
        if kind in self.features:
            return {entity for item, entity in self.features[kind] if item == value}
        raise ValueError(f"unknown namespace {kind!r}")

    def adjective(self, entity: Entity, adjective: str) -> bool:
        if adjective == "free":
            return entity.sort == Sort.CELL and not (entity.footprint & self.board.blocked)
        occupied = any(person.footprint & entity.footprint for person in self.people.values())
        if adjective == "empty":
            return not occupied
        if adjective == "occupied":
            return occupied
        raise ValueError(f"unknown adjective {adjective!r}")

    def operand(self, operand: lang.Operand, variables: Mapping[str, Entity]) -> set[Entity]:
        match operand:
            case lang.Name(token=token):
                return self.name(token, variables)
            case lang.Union(items=items):
                result: set[Entity] = set()
                namespace = None
                if isinstance(items[0], lang.Name) and ":" in items[0].token.text:
                    namespace = items[0].token.text.partition(":")[0]
                for index, item in enumerate(items):
                    if index and isinstance(item, lang.Name):
                        result.update(self.name(item.token, variables, namespace))
                    else:
                        result.update(self.operand(item, variables))
                return result
            case lang.Difference(left=left, right=right):
                return self.operand(left, variables) - self.operand(right, variables)
            case lang.Qualified(adjective=adjective, operand=inner):
                return {
                    item
                    for item in self.operand(inner, variables)
                    if self.adjective(item, adjective.text)
                }
            case lang.AdjectiveFilter(source=source, adjective=adjective):
                return {
                    item
                    for item in self.operand(source, variables)
                    if self.adjective(item, adjective.text)
                }
            case lang.Projection(kind=kind, operand=inner):
                cells = {
                    square for item in self.operand(inner, variables) for square in item.footprint
                }
                if kind.text == "cell":
                    return {self.cells[square] for square in cells}
                if kind.text == "row":
                    return {self.rows[square.row] for square in cells}
                if kind.text == "column":
                    return {self.columns[square.col] for square in cells}
                if kind.text == "area":
                    return {self.areas[self.board.region_of(square)] for square in cells}
                raise ValueError(f"unknown projection {kind.text!r}")
            case lang.Filter(source=source, operator=operator, target=target, measure=measure):
                targets = self.operand(target, variables)
                return {
                    item
                    for item in self.operand(source, variables)
                    if self.related(item, operator.text, targets, measure)
                }
            case lang.Comprehension(variable=variable, source=source, condition=condition):
                return {
                    item
                    for item in self.operand(source, variables)
                    if self.formula(condition, dict(variables) | {variable.text: item})
                }
            case _:
                assert_never(operand)

    def area_distance(self, first: Square, second: Square) -> int:
        start = self.board.region_of(first)
        end = self.board.region_of(second)
        pending = deque([(start, 0)])
        seen = {start}
        while pending:
            area, distance = pending.popleft()
            if area == end:
                return distance
            for border in self.board.borders:
                if area in border:
                    for neighbor in border - {area}:
                        if neighbor not in seen:
                            seen.add(neighbor)
                            pending.append((neighbor, distance + 1))
        raise ValueError(f"no area path from {start!r} to {end!r}")

    def distance(self, metric: str, first: Square, second: Square) -> int:
        rows = abs(first.row - second.row)
        cols = abs(first.col - second.col)
        match metric:
            case "rows":
                return rows
            case "cols":
                return cols
            case "manhattan":
                return rows + cols
            case "king":
                return max(rows, cols)
            case "euclidean":
                return rows * rows + cols * cols
            case "areas":
                return self.area_distance(first, second)
            case _:
                raise ValueError(f"unknown distance metric {metric!r}")

    @staticmethod
    def compare(value: int, measure: lang.Measure, *, squared: bool = False) -> bool:
        target = int(measure.value.text)
        if squared:
            target *= target
        match measure.comparison.text:
            case "=":
                return value == target
            case "<=":
                return value <= target
            case ">=":
                return value >= target
            case _:
                raise ValueError(f"unknown direction comparison {measure.comparison.text!r}")

    def directional_pair(
        self, mode: str, first: Square, second: Square, measure: lang.Measure | None
    ) -> bool:
        gaps = {
            "up": second.row - first.row,
            "down": first.row - second.row,
            "left": second.col - first.col,
            "right": first.col - second.col,
        }
        directions = mode.split("+")
        if all(direction in gaps for direction in directions):
            return all(
                gaps[direction] > 0 and (measure is None or self.compare(gaps[direction], measure))
                for direction in directions
            )
        if mode == "diagonal":
            gap = abs(first.row - second.row)
            return (
                gap > 0
                and gap == abs(first.col - second.col)
                and (measure is None or self.compare(gap, measure))
            )
        if mode == "knight":
            return {abs(first.row - second.row), abs(first.col - second.col)} == {1, 2}
        if measure is None:
            raise ValueError(f"direction mode {mode!r} requires a measure")
        return self.compare(
            self.distance(mode, first, second), measure, squared=mode == "euclidean"
        )

    def pair(
        self, subject: Entity, operator: str, target: Entity, measure: lang.Measure | None
    ) -> bool:
        if operator == "is":
            if subject.sort == Sort.PERSON and target.sort == Sort.ROLE:
                assert isinstance(subject.key, str) and isinstance(target.key, str)
                return self.roles[(subject.key, target.key)]
            return subject == target
        if operator == "in":
            return subject.footprint <= target.footprint
        if operator == "on":
            return bool(subject.footprint & target.footprint)
        if subject == target:
            return False
        if operator in {"beside", "touches"}:
            return any(
                abs(a.row - b.row) + abs(a.col - b.col) == 1
                and (operator == "touches" or self.board.region_of(a) == self.board.region_of(b))
                for a in subject.footprint
                for b in target.footprint
            )
        if operator.startswith("dir:"):
            mode = operator.removeprefix("dir:")
            return any(
                self.directional_pair(mode, a, b, measure)
                for a in subject.footprint
                for b in target.footprint
            )
        raise ValueError(f"unknown relation {operator!r}")

    def related(
        self, subject: Entity, operator: str, targets: set[Entity], measure: lang.Measure | None
    ) -> bool:
        mode = operator.removeprefix("dir:")
        if operator.startswith("dir:") and mode.split(":")[0] in {"nearest", "furthest"}:
            order, separator, metric = mode.partition(":")
            metric = metric if separator else "manhattan"
            others = set(self.people.values()) - targets - {subject}
            for target in targets - {subject}:
                own_distance = self.closest_distance(metric, subject, target)
                if all(
                    (
                        own_distance < self.closest_distance(metric, other, target)
                        if order == "nearest"
                        else own_distance > self.closest_distance(metric, other, target)
                    )
                    for other in others
                ):
                    return True
            return False
        return any(self.pair(subject, operator, target, measure) for target in targets)

    def closest_distance(self, metric: str, person: Entity, target: Entity) -> int:
        return min(self.distance(metric, a, b) for a in person.footprint for b in target.footprint)

    def number(self, expression: lang.Number, variables: Mapping[str, Entity]) -> int:
        match expression:
            case lang.Integer(value=value):
                return int(value.text)
            case lang.Count(operand=operand):
                return len(self.operand(operand, variables))
            case lang.Arithmetic(left=left, operator=operator, right=right):
                first = self.number(left, variables)
                second = self.number(right, variables)
                return first + second if operator.text == "+" else first - second

    def formula(self, formula: lang.Formula, variables: Mapping[str, Entity]) -> bool:
        match formula:
            case lang.Atom(
                subject=subject,
                operator=operator,
                target=target,
                determiner=determiner,
                measure=measure,
            ):
                targets = self.operand(target, variables)
                results = [
                    self.related(person, operator.text, targets, measure)
                    for person in self.operand(subject, variables)
                ]
                if determiner is None or determiner.text == "some":
                    return any(results)
                if determiner.text == "every":
                    return all(results)
                if determiner.text == "no":
                    return not any(results)
                raise ValueError(f"unknown determiner {determiner.text!r}")
            case lang.AdjectiveAtom(subject=subject, adjective=adjective, determiner=determiner):
                results = [
                    self.adjective(item, adjective.text)
                    for item in self.operand(subject, variables)
                ]
                if determiner is None or determiner.text == "some":
                    return any(results)
                if determiner.text == "every":
                    return all(results)
                if determiner.text == "no":
                    return not any(results)
                raise ValueError(f"unknown determiner {determiner.text!r}")
            case lang.SetComparison(left=left, operator=operator, right=right):
                equal = self.operand(left, variables) == self.operand(right, variables)
                return equal if operator.text == "=" else not equal
            case lang.Negation(formula=inner):
                return not self.formula(inner, variables)
            case lang.Binary(left=left, operator=operator, right=right):
                if operator.text == "and":
                    return self.formula(left, variables) and self.formula(right, variables)
                if operator.text == "or":
                    return self.formula(left, variables) or self.formula(right, variables)
                if operator.text == "if":
                    return not self.formula(left, variables) or self.formula(right, variables)
                if operator.text == "iff":
                    return self.formula(left, variables) == self.formula(right, variables)
                raise ValueError(f"unknown connective {operator.text!r}")
            case lang.NumberComparison(left=left, operator=operator, right=right):
                first, second = self.number(left, variables), self.number(right, variables)
                return {
                    "=": first == second,
                    "!=": first != second,
                    "<": first < second,
                    "<=": first <= second,
                    ">": first > second,
                    ">=": first >= second,
                }[operator.text]
            case lang.Parity(number=number, parity=parity):
                return self.number(number, variables) % 2 == int(parity.text == "odd")
            case lang.NumberRange(number=number, lower=lower, upper=upper):
                return int(lower.text) <= self.number(number, variables) <= int(upper.text)
            case lang.Quantified(
                quantifier=quantifier, count=count, variables=names, source=source, body=body
            ):
                domain = sorted(
                    self.operand(source, variables),
                    key=lambda item: (item.sort.value, str(item.key)),
                )
                results = [
                    self.formula(
                        body,
                        dict(variables)
                        | dict(zip((name.text for name in names), values, strict=True)),
                    )
                    for values in permutations(domain, len(names))
                ]
                kind = " ".join(quantifier.text.split())
                if kind == "some":
                    return any(results)
                if kind == "every":
                    return all(results)
                if kind == "no":
                    return not any(results)
                assert count is not None
                return self.count_matches(kind, int(count.text), sum(results))
            case lang.Choice(quantifier=quantifier, count=count, choices=choices):
                true_count = sum(self.formula(choice, variables) for choice in choices)
                return self.count_matches(
                    " ".join(quantifier.text.split()), int(count.text), true_count
                )
            case _:
                assert_never(formula)

    @staticmethod
    def count_matches(kind: str, target: int, actual: int) -> bool:
        match kind:
            case "exactly":
                return actual == target
            case "at least":
                return actual >= target
            case "at most":
                return actual <= target
            case _:
                raise ValueError(f"unknown quantifier {kind!r}")


def holds(
    statement: lang.Statement,
    board: Board,
    placed: Mapping[str, Square],
    roles: Mapping[tuple[str, str], bool],
) -> bool:
    """Evaluate one checked statement over a complete placement and role assignment."""
    check_formula(board, statement.formula)
    return _Evaluation(board, placed, roles).formula(statement.formula, {})
