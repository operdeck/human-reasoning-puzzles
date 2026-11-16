"""Incremental lowering of Murdoku expression statements to model constraints."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from itertools import permutations

from . import murdoku_lang as lang
from .core import Kind, Model
from .murdoku import (
    Board,
    Square,
    _area_distances,
    _auxiliary_variable,
    _direction_test,
    _hidden_boolean,
    compile_puzzle,
)
from .murdoku_typecheck import Shape, Sort, check_formula, infer_operand


@dataclass(frozen=True)
class _RoleBinding:
    name: str


@dataclass(frozen=True)
class _AreaBinding:
    region: str


@dataclass(frozen=True)
class _LineBinding:
    selector: str


@dataclass(frozen=True)
class _SpatialBinding:
    sort: Sort
    key: str


type _Bindings = dict[str, str | _RoleBinding | _AreaBinding | _LineBinding | _SpatialBinding]


def _operand_sort(board: Board, operand: lang.Operand, bindings: _Bindings) -> Sort:
    entities = _static_spatial_entities(board, operand)
    if entities:
        return next(iter(entities))[0]
    if entities is not None:
        if isinstance(operand, lang.Difference):
            return _operand_sort(board, operand.left, bindings)
        if isinstance(operand, lang.Union):
            return _operand_sort(board, operand.items[0], bindings)
        if isinstance(operand, (lang.Filter, lang.AdjectiveFilter)):
            return _operand_sort(board, operand.source, bindings)
        if isinstance(operand, lang.Qualified):
            return _operand_sort(board, operand.operand, bindings)
        if isinstance(operand, lang.Projection):
            return {
                "area": Sort.AREA,
                "row": Sort.ROW,
                "column": Sort.COLUMN,
                "cell": Sort.CELL,
            }[operand.kind.text]
    shapes = {
        variable: Shape(
            Sort.ROLE
            if isinstance(value, _RoleBinding)
            else Sort.AREA
            if isinstance(value, _AreaBinding)
            else Sort.ROW
            if isinstance(value, _LineBinding) and value.selector.startswith("rows:")
            else Sort.COLUMN
            if isinstance(value, _LineBinding)
            else value.sort
            if isinstance(value, _SpatialBinding)
            else Sort.PERSON,
            1,
            1,
        )
        for variable, value in bindings.items()
    }
    return infer_operand(board, operand, shapes).sort


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
        entities = _static_spatial_entities(board, target)
        if entities is None:
            return None
        return {square for footprint in entities.values() for square in footprint}
    text = target.token.text
    if text.startswith("__entity:"):
        entities = _static_spatial_entities(board, target)
        assert entities is not None
        return {square for footprint in entities.values() for square in footprint}
    all_cells = {Square(row, col) for row in range(board.size) for col in range(board.size)}
    if text in {"areas", "rows", "columns", "cells"}:
        return all_cells
    if text == "objects":
        return {square for obj in board.objects for square in obj.squares}
    if ":" not in text and namespace:
        text = f"{namespace}:{text}"
    kind, separator, value = text.partition(":")
    if not separator:
        return None
    if kind == "area":
        region = board.region_id(value)
        return {square for square in all_cells if board.region_of(square) == region}
    if kind == "tag":
        regions = board.tagged_region_ids([value])
        return {square for square in all_cells if board.region_of(square) in regions}
    if kind == "mark":
        return board.mark_cells([value])
    if kind == "object":
        return board.squares_of([value])
    if kind == "edge_item":
        return board.edge_item_cells([value])
    if kind == "point_object":
        return board.point_object_cells([value])
    if kind == "object_kind":
        return {square for obj in board.objects if obj.kind == value for square in obj.squares}
    if kind in {"rows", "columns"}:
        first, has_end, last = value.partition("-")
        start = board.size if first == "last" else int(first)
        end = (board.size if last == "last" else int(last)) if has_end else start
        return {
            square
            for square in all_cells
            if start <= (square.row if kind == "rows" else square.col) + 1 <= end
        }
    if kind == "corner" and value == "board":
        edge = {0, board.size - 1}
        return {Square(row, col) for row in edge for col in edge}
    return None


def _direction(
    board: Board, operator: str, measure: lang.Measure | None
) -> Callable[[Square, Square], bool] | None:
    mode = operator.removeprefix("dir:")
    simple = {"up", "down", "left", "right"}
    metrics = {"rows", "cols", "manhattan", "king", "euclidean", "areas", "knight"}
    directions = mode.split("+")
    if mode not in simple | metrics | {"diagonal"} and not all(
        direction in simple for direction in directions
    ):
        return None
    comparison = measure.comparison.text if measure else None
    distance = int(measure.value.text) if measure else None
    if mode in metrics:
        return _direction_test(board, mode, comparison, distance)

    def matches(value: int) -> bool:
        if distance is None:
            return True
        if comparison == "=":
            return value == distance
        if comparison == "<=":
            return value <= distance
        return value >= distance

    def directed(left: Square, right: Square) -> bool:
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

    return directed


def _position_matches(
    board: Board,
    square: Square,
    operator: str,
    cells: set[Square],
    direction: Callable[[Square, Square], bool] | None,
) -> bool:
    if operator in {"in", "on"}:
        return square in cells
    if direction is not None:
        return any(direction(square, cell) for cell in cells)
    return any(
        abs(square.row - cell.row) + abs(square.col - cell.col) == 1
        and (operator == "touches" or board.region_of(square) == board.region_of(cell))
        for cell in cells
    )


def _static_people(
    board: Board, operand: lang.Operand, namespace: str | None = None
) -> set[str] | None:
    if isinstance(operand, lang.Union):
        first = operand.items[0]
        inherited = (
            first.token.text.partition(":")[0]
            if isinstance(first, lang.Name) and ":" in first.token.text
            else None
        )
        people: set[str] = set()
        for item in operand.items:
            part = _static_people(board, item, inherited)
            if part is None:
                return None
            people.update(part)
        return people
    if isinstance(operand, lang.Difference):
        left, right = _static_people(board, operand.left), _static_people(board, operand.right)
        return left - right if left is not None and right is not None else None
    if isinstance(operand, lang.Filter) and operand.operator.text == "is":
        source, target = (
            _static_people(board, operand.source),
            _static_people(board, operand.target),
        )
        return source & target if source is not None and target is not None else None
    if not isinstance(operand, lang.Name):
        return None
    text = operand.token.text
    if text in board.people:
        return {text}
    if text == "people":
        return set(board.people)
    if ":" not in text and namespace:
        text = f"{namespace}:{text}"
    kind, separator, value = text.partition(":")
    if separator and kind == "attribute":
        return set(board.attributes[value])
    return None


def _counted_keys(board: Board, operand: lang.Operand) -> list[tuple[str, Square | bool]] | None:
    if isinstance(operand, lang.Name) and operand.token.text.startswith("role:"):
        role = operand.token.text.removeprefix("role:")
        return [(board.role_variable(person, role), True) for person in board.people]
    people = _static_people(board, operand)
    if people is not None:
        return [
            (person, square) for person in board.people if person in people for square in board.free
        ]
    if isinstance(operand, lang.Filter):
        people = _static_people(board, operand.source)
        if people is None:
            return None
        operator = operand.operator.text
        if operator not in {"in", "on", "beside", "touches"} and not operator.startswith("dir:"):
            return None
        cells = _static_cells(board, operand.target)
        if cells is None:
            return None
        direction = (
            _direction(board, operator, operand.measure) if operator.startswith("dir:") else None
        )
        if operator.startswith("dir:") and direction is None:
            return None
        squares = [
            square
            for square in board.free
            if _position_matches(board, square, operator, cells, direction)
        ]
        return [
            (person, square) for person in board.people if person in people for square in squares
        ]
    return None


def _role_scope(board: Board, operand: lang.Operand) -> tuple[str, set[Square]] | None:
    if not (
        isinstance(operand, lang.Filter)
        and isinstance(operand.source, lang.Name)
        and operand.source.token.text.startswith("role:")
    ):
        return None
    operator = operand.operator.text
    if operator not in {"in", "on", "beside", "touches"} and not operator.startswith("dir:"):
        return None
    cells = _static_cells(board, operand.target)
    if cells is None:
        return None
    direction = (
        _direction(board, operator, operand.measure) if operator.startswith("dir:") else None
    )
    if operator.startswith("dir:") and direction is None:
        return None
    squares = {
        square
        for square in board.free
        if _position_matches(board, square, operator, cells, direction)
    }
    return operand.source.token.text.removeprefix("role:"), squares


def _role_selection_literals(
    model: Model, board: Board, role: str, squares: set[Square], name: str
) -> list[int]:
    literals = []
    for person in board.people:
        variable, selected, _ = _hidden_boolean(
            model, "expression_role_scope", f"{name} {person} selected", "Murdoku expression"
        )
        model.relate(
            f"{name} {person} selection",
            (person, board.role_variable(person, role), variable),
            lambda square, has_role, selected, squares=squares: (
                selected == (has_role and square in squares)
            ),
        )
        literals.append(selected)
    return literals


def try_lower_location(model: Model, board: Board, statement: lang.Statement, name: str) -> bool:
    """Lower a named person's static spatial relation as domain eliminations."""
    formula = statement.formula
    negated = isinstance(formula, lang.Negation)
    atom = formula.formula if isinstance(formula, lang.Negation) else formula
    if not (
        isinstance(atom, lang.Atom)
        and isinstance(atom.subject, lang.Name)
        and atom.subject.token.text in board.people
        and (
            atom.operator.text in {"in", "on", "beside", "touches"}
            or atom.operator.text.startswith("dir:")
        )
    ):
        return False
    check_formula(board, formula)
    cells = _static_cells(board, atom.target)
    if cells is None:
        return False
    direction = (
        _direction(board, atom.operator.text, atom.measure)
        if atom.operator.text.startswith("dir:")
        else None
    )
    if atom.operator.text.startswith("dir:") and direction is None:
        return False
    person = atom.subject.token.text
    if person not in model.all_variables:
        raise ValueError(f"model lacks declared variable: {person}")
    exclude = negated ^ (atom.determiner is not None and atom.determiner.text == "no")
    for square in board.free:
        matches = _position_matches(board, square, atom.operator.text, cells, direction)
        if matches == exclude:
            model.eliminate(model.literal(person, square), "clue", name, sources=(name,))
    return True


def try_lower_membership(model: Model, board: Board, statement: lang.Statement, name: str) -> bool:
    """Lower a named person's role or fixed-set membership."""
    formula = statement.formula
    negated = isinstance(formula, lang.Negation)
    atom = formula.formula if isinstance(formula, lang.Negation) else formula
    if not (
        isinstance(atom, lang.Atom)
        and isinstance(atom.subject, lang.Name)
        and atom.subject.token.text in board.people
        and atom.operator.text == "is"
    ):
        return False
    check_formula(board, formula)
    person = atom.subject.token.text
    invert = negated ^ (atom.determiner is not None and atom.determiner.text == "no")
    if isinstance(atom.target, lang.Name) and atom.target.token.text.startswith("role:"):
        role = atom.target.token.text.removeprefix("role:")
        variable = board.role_variable(person, role)
        if variable not in model.all_variables:
            raise ValueError(f"model lacks declared variable: {variable}")
        model.assign(model.literal(variable, not invert), "clue", name, sources=(name,))
        return True
    people = _static_people(board, atom.target)
    if people is None:
        return False
    if person not in model.all_variables:
        raise ValueError(f"model lacks declared variable: {person}")
    accepted = (person in people) != invert
    model.relate(name, (person,), lambda _square: accepted)
    return True


def try_lower_role_atom(model: Model, board: Board, statement: lang.Statement, name: str) -> bool:
    """Lower a role-holder determiner over a fixed spatial or person set."""
    formula = statement.formula
    negated = isinstance(formula, lang.Negation)
    atom = formula.formula if isinstance(formula, lang.Negation) else formula
    if not (
        isinstance(atom, lang.Atom)
        and isinstance(atom.subject, lang.Name)
        and atom.subject.token.text.startswith("role:")
    ):
        return False
    check_formula(board, formula)
    role = atom.subject.token.text.removeprefix("role:")
    determiner = atom.determiner.text if atom.determiner else "some"
    counterexamples = determiner == "every"
    require_zero = (determiner in {"no", "every"}) != negated
    variables = {board.role_variable(person, role) for person in board.people}
    if atom.operator.text == "is":
        if isinstance(atom.target, lang.Name) and atom.target.token.text.startswith("role:"):
            target_role = atom.target.token.text.removeprefix("role:")
            variables.update(board.role_variable(person, target_role) for person in board.people)
            missing = variables - set(model.all_variables)
            if missing:
                raise ValueError(f"model lacks declared variables: {', '.join(sorted(missing))}")
            if target_role == role:
                literals = (
                    []
                    if counterexamples
                    else [
                        model.literal(board.role_variable(person, role), True)
                        for person in board.people
                    ]
                )
            else:
                literals = []
                for person in board.people:
                    variable, selected, _ = _hidden_boolean(
                        model,
                        "expression_role_pair",
                        f"{name} {person} selected",
                        "Murdoku expression",
                    )
                    model.relate(
                        f"{name} {person} selection",
                        (
                            board.role_variable(person, role),
                            board.role_variable(person, target_role),
                            variable,
                        ),
                        lambda source, target, result, opposite=counterexamples: (
                            result == (source and (target != opposite))
                        ),
                    )
                    literals.append(selected)
        else:
            people = _static_people(board, atom.target)
            if people is None:
                return False
            selected_people = set(board.people) - people if counterexamples else people
            missing = variables - set(model.all_variables)
            if missing:
                raise ValueError(f"model lacks declared variables: {', '.join(sorted(missing))}")
            literals = [
                model.literal(board.role_variable(person, role), True)
                for person in board.people
                if person in selected_people
            ]
    else:
        scope = _role_scope(
            board, lang.Filter(atom.subject, atom.operator, atom.target, atom.measure)
        )
        if scope is None:
            return False
        _, squares = scope
        if counterexamples:
            squares = set(board.free) - squares
        variables.update(board.people)
        missing = variables - set(model.all_variables)
        if missing:
            raise ValueError(f"model lacks declared variables: {', '.join(sorted(missing))}")
        literals = _role_selection_literals(model, board, role, squares, name)
    allowed = {0} if require_zero else set(range(1, len(literals) + 1))
    if not allowed:
        model.relate(name, (board.people[0],), lambda _square: False)
    else:
        model.constrain(
            name, Kind.COUNT, literals, allowed_counts=allowed, family="Murdoku expression"
        )
    return True


def _person_relation(
    board: Board, atom: lang.Atom, *, same: bool
) -> Callable[[Square, Square], bool] | None:
    op = atom.operator.text
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
        direction = _direction(board, op, atom.measure)
        if direction is None:
            return None

        def directed(left: Square, right: Square) -> bool:
            return not same and direction(left, right)

        test = directed
    else:
        return None
    return test


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
    same = first == second
    test = _person_relation(board, atom, same=same)
    if test is None:
        return False
    invert = negated ^ (atom.determiner is not None and atom.determiner.text == "no")
    if same:
        model.relate(name, (first,), lambda square: test(square, square) != invert)
    else:
        model.relate(name, (first, second), lambda left, right: test(left, right) != invert)
    return True


def try_lower_role_target(model: Model, board: Board, statement: lang.Statement, name: str) -> bool:
    """Lower a named person's spatial relation to an existential role-holder set."""
    formula = statement.formula
    negated = isinstance(formula, lang.Negation)
    atom = formula.formula if isinstance(formula, lang.Negation) else formula
    if not (
        isinstance(atom, lang.Atom)
        and isinstance(atom.subject, lang.Name)
        and atom.subject.token.text in board.people
        and isinstance(atom.target, lang.Name)
        and atom.target.token.text.startswith("role:")
        and atom.operator.text != "is"
    ):
        return False
    check_formula(board, formula)
    person = atom.subject.token.text
    role = atom.target.token.text.removeprefix("role:")
    different = _person_relation(board, atom, same=False)
    if different is None:
        return False
    variables = set(board.people) | {board.role_variable(holder, role) for holder in board.people}
    missing = variables - set(model.all_variables)
    if missing:
        raise ValueError(f"model lacks declared variables: {', '.join(sorted(missing))}")
    literals = []
    for holder in board.people:
        if holder == person:
            if atom.operator.text in {"in", "on"}:
                literals.append(model.literal(board.role_variable(holder, role), True))
            continue
        variable, selected, _ = _hidden_boolean(
            model, "expression_role_target", f"{name} {holder} selected", "Murdoku expression"
        )
        model.relate(
            f"{name} {holder} selection",
            (person, holder, board.role_variable(holder, role), variable),
            lambda left, right, has_role, selected, test=different: (
                selected == (has_role and test(left, right))
            ),
        )
        literals.append(selected)
    exclude = negated ^ (atom.determiner is not None and atom.determiner.text == "no")
    allowed = {0} if exclude else set(range(1, len(literals) + 1))
    if not allowed:
        model.relate(name, (person,), lambda _square: False)
    else:
        model.constrain(
            name, Kind.COUNT, literals, allowed_counts=allowed, family="Murdoku expression"
        )
    return True


def _count_predicate(
    formula: lang.Formula,
) -> tuple[lang.Operand, Callable[[int], bool], lang.Token] | None:
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
            return None
    return operand, predicate, location


def try_lower_count(model: Model, board: Board, statement: lang.Statement, name: str) -> bool:
    """Lower supported top-level counts; return false without changes for other shapes."""
    formula = statement.formula
    count = _count_predicate(formula)
    if count is None:
        return False
    operand, predicate, location = count
    check_formula(board, formula)
    role_scope = _role_scope(board, operand)
    keys = _counted_keys(board, operand) if role_scope is None else None
    if keys is None and role_scope is None:
        return False
    if role_scope is not None:
        role, _ = role_scope
        variables = set(board.people) | {
            board.role_variable(person, role) for person in board.people
        }
        maximum = len(board.people)
    else:
        assert keys is not None
        variables = {variable for variable, _ in keys}
        maximum = min(len(keys), len(board.people))
    missing = variables - set(model.all_variables)
    if missing:
        raise ValueError(f"model lacks declared variables: {', '.join(sorted(missing))}")
    permitted = {value for value in range(maximum + 1) if predicate(value)}
    if not permitted:
        raise ValueError(
            f"line {location.line}, column {location.column}: "
            "comparison has no feasible value on this board"
        )
    if role_scope is not None:
        role, squares = role_scope
        literals = _role_selection_literals(model, board, role, squares, name)
    else:
        assert keys is not None
        literals = [model.literal(variable, value) for variable, value in keys]
    model.constrain(
        name,
        Kind.COUNT,
        literals,
        allowed_counts=permitted,
        family="Murdoku expression",
    )
    return True


def _opposite(model: Model, literal: int) -> int:
    value = model.value_of(literal)
    if not isinstance(value, bool):
        raise ValueError("a reified expression must use a Boolean literal")
    return model.literal(model.var_of(literal), not value)


def _constant_boolean(model: Model, value: bool, name: str) -> int:
    _, yes, no = _hidden_boolean(model, "expression", name, "Murdoku expression")
    model.assign(yes if value else no, "clue", name, sources=(f"{name} state",))
    return yes


def _static_roles(board: Board, operand: lang.Operand, bindings: _Bindings) -> set[str] | None:
    if isinstance(operand, lang.Name):
        bound = bindings.get(operand.token.text)
        if isinstance(bound, _RoleBinding):
            return {bound.name}
        if operand.token.text == "roles":
            return {role.name for role in board.roles}
    if isinstance(operand, lang.Union):
        result: set[str] = set()
        for item in operand.items:
            roles = _static_roles(board, item, bindings)
            if roles is None:
                return None
            result.update(roles)
        return result
    if isinstance(operand, lang.Difference):
        left, right = (
            _static_roles(board, operand.left, bindings),
            _static_roles(board, operand.right, bindings),
        )
        return left - right if left is not None and right is not None else None
    return None


def _role_selected(
    model: Model,
    board: Board,
    role: str,
    operand: lang.Operand,
    name: str,
    empty_scopes: dict[Square | str, int],
    bindings: _Bindings,
) -> int:
    static = _static_roles(board, operand, bindings)
    if static is not None:
        return _constant_boolean(model, role in static, name)
    if isinstance(operand, lang.Union):
        members = [
            _role_selected(model, board, role, item, f"{name} {index}", empty_scopes, bindings)
            for index, item in enumerate(operand.items, 1)
        ]
        return _reify_cardinality(model, members, set(range(1, len(members) + 1)), name)
    if isinstance(operand, lang.Difference):
        left = _role_selected(
            model, board, role, operand.left, f"{name} left", empty_scopes, bindings
        )
        right = _role_selected(
            model, board, role, operand.right, f"{name} right", empty_scopes, bindings
        )
        return _reify_cardinality(model, [left, _opposite(model, right)], {2}, name)
    if isinstance(operand, lang.Filter) and operand.operator.text == "is":
        source = _role_selected(
            model, board, role, operand.source, f"{name} source", empty_scopes, bindings
        )
        target = _role_selected(
            model, board, role, operand.target, f"{name} target", empty_scopes, bindings
        )
        return _reify_cardinality(model, [source, target], {2}, name)
    if isinstance(operand, lang.Comprehension):
        selected = _role_selected(
            model, board, role, operand.source, f"{name} source", empty_scopes, bindings
        )
        matches = _reify_formula(
            model,
            board,
            operand.condition,
            f"{name} condition",
            bindings | {operand.variable.text: _RoleBinding(role)},
            empty_scopes,
        )
        return _reify_cardinality(model, [selected, matches], {2}, name)
    raise NotImplementedError(f"{name}: role set lowering is not implemented")


def _bind_operand(operand: lang.Operand, bindings: _Bindings) -> lang.Operand:
    if isinstance(operand, lang.Name):
        value = bindings.get(operand.token.text)
        if isinstance(value, _RoleBinding):
            raise NotImplementedError("bound role entity is supported only as the target of is")
        if isinstance(value, _AreaBinding):
            value = f"__entity:area:{value.region}"
        if isinstance(value, _LineBinding):
            value = value.selector
        if isinstance(value, _SpatialBinding):
            value = f"__entity:{value.sort.value}:{value.key}"
        return replace(operand, token=replace(operand.token, text=value)) if value else operand
    if isinstance(operand, lang.Union):
        return replace(
            operand, items=tuple(_bind_operand(item, bindings) for item in operand.items)
        )
    if isinstance(operand, lang.Difference):
        return replace(
            operand,
            left=_bind_operand(operand.left, bindings),
            right=_bind_operand(operand.right, bindings),
        )
    if isinstance(operand, lang.Filter):
        return replace(
            operand,
            source=_bind_operand(operand.source, bindings),
            target=_bind_operand(operand.target, bindings),
        )
    if isinstance(operand, (lang.Qualified, lang.Projection)):
        return replace(operand, operand=_bind_operand(operand.operand, bindings))
    if isinstance(operand, lang.AdjectiveFilter):
        return replace(operand, source=_bind_operand(operand.source, bindings))
    if isinstance(operand, lang.Comprehension):
        return replace(operand, source=_bind_operand(operand.source, bindings))
    raise AssertionError("unknown operand")


def _reify_cardinality(model: Model, literals: list[int], allowed: set[int], name: str) -> int:
    _, yes, no = _hidden_boolean(model, "expression", name, "Murdoku expression")
    if not allowed:
        model.assign(no, "clue", name, sources=(f"{name} state",))
    else:
        seen: set[int] = set()
        distinct = []
        for index, literal in enumerate(literals, 1):
            if literal in seen:
                variable, alias, _ = _hidden_boolean(
                    model, "expression", f"{name} duplicate {index}", "Murdoku expression"
                )
                value = model.value_of(literal)
                model.relate(
                    f"{name} duplicate {index}",
                    (model.var_of(literal), variable),
                    lambda original, selected, value=value: selected == (original == value),
                )
                distinct.append(alias)
            else:
                seen.add(literal)
                distinct.append(literal)
        model.constrain(
            name,
            Kind.COUNT,
            distinct,
            allowed_counts=allowed,
            reified_by=yes,
            family="Murdoku expression",
        )
    return yes


def _reify_atom(model: Model, board: Board, atom: lang.Atom, name: str) -> int:
    if not isinstance(atom.subject, lang.Name) or atom.subject.token.text not in board.people:
        raise NotImplementedError(f"{name}: expression lowering is not implemented")
    person = atom.subject.token.text
    invert = atom.determiner is not None and atom.determiner.text == "no"
    variable, yes, no = _hidden_boolean(model, "expression", name, "Murdoku expression")
    if atom.operator.text == "is":
        if isinstance(atom.target, lang.Name) and atom.target.token.text.startswith("role:"):
            role = atom.target.token.text.removeprefix("role:")
            model.relate(
                name,
                (board.role_variable(person, role), variable),
                lambda present, result: result == present,
            )
        else:
            people = _static_people(board, atom.target)
            if people is None:
                raise NotImplementedError(f"{name}: expression lowering is not implemented")
            model.assign(yes if person in people else no, "clue", name, sources=(f"{name} state",))
    elif (
        isinstance(atom.target, lang.Projection)
        and isinstance(atom.target.operand, lang.Name)
        and atom.target.operand.token.text in board.people
    ):
        other = atom.target.operand.token.text
        kind = atom.target.kind.text
        direction = (
            _direction(board, atom.operator.text, atom.measure)
            if atom.operator.text.startswith("dir:")
            else None
        )
        if (
            atom.operator.text not in {"in", "on", "beside", "touches"} and direction is None
        ) or kind not in {"area", "row", "column", "cell"}:
            raise NotImplementedError(f"{name}: expression lowering is not implemented")
        all_cells = {Square(row, col) for row in range(board.size) for col in range(board.size)}

        def footprint(reference: Square) -> set[Square]:
            if kind == "area":
                return {
                    cell
                    for cell in all_cells
                    if board.region_of(cell) == board.region_of(reference)
                }
            if kind == "row":
                return {cell for cell in all_cells if cell.row == reference.row}
            if kind == "column":
                return {cell for cell in all_cells if cell.col == reference.col}
            return {reference}

        footprints = {reference: footprint(reference) for reference in board.free}

        def matches(square: Square, reference: Square) -> bool:
            return _position_matches(
                board, square, atom.operator.text, footprints[reference], direction
            )

        if person == other:
            model.relate(
                name,
                (person, variable),
                lambda square, result: result == matches(square, square),
            )
        else:
            model.relate(
                name,
                (person, other, variable),
                lambda square, reference, result: result == matches(square, reference),
            )
    elif isinstance(atom.target, lang.Name) and atom.target.token.text in board.people:
        other = atom.target.token.text
        same = person == other
        test = _person_relation(board, atom, same=same)
        if test is None:
            raise NotImplementedError(f"{name}: expression lowering is not implemented")
        if same:
            model.relate(
                name, (person, variable), lambda square, result: result == test(square, square)
            )
        else:
            model.relate(
                name,
                (person, other, variable),
                lambda left, right, result: result == test(left, right),
            )
    else:
        cells = _static_cells(board, atom.target)
        if cells is None or (
            atom.operator.text not in {"in", "on", "beside", "touches"}
            and not atom.operator.text.startswith("dir:")
        ):
            raise NotImplementedError(f"{name}: expression lowering is not implemented")
        direction = (
            _direction(board, atom.operator.text, atom.measure)
            if atom.operator.text.startswith("dir:")
            else None
        )
        if atom.operator.text.startswith("dir:") and direction is None:
            raise NotImplementedError(f"{name}: expression lowering is not implemented")
        model.relate(
            name,
            (person, variable),
            lambda square, result: (
                result == _position_matches(board, square, atom.operator.text, cells, direction)
            ),
        )
    return no if invert else yes


def _person_selected(
    model: Model,
    board: Board,
    person: str,
    operand: lang.Operand,
    name: str,
    empty_scopes: dict[Square | str, int],
    bindings: _Bindings,
) -> int:
    people = _static_people(board, operand)
    if people is not None:
        _, yes, no = _hidden_boolean(model, "expression", name, "Murdoku expression")
        model.assign(yes if person in people else no, "clue", name, sources=(f"{name} state",))
        return yes
    if isinstance(operand, lang.Name) and operand.token.text.startswith("role:"):
        role = operand.token.text.removeprefix("role:")
        variable, yes, _ = _hidden_boolean(model, "expression", name, "Murdoku expression")
        model.relate(
            name,
            (board.role_variable(person, role), variable),
            lambda selected, result: selected == result,
        )
        return yes
    if isinstance(operand, lang.Union):
        first_item = operand.items[0]
        namespace = (
            first_item.token.text.partition(":")[0]
            if isinstance(first_item, lang.Name) and ":" in first_item.token.text
            else None
        )
        members = []
        for index, item in enumerate(operand.items, 1):
            if (
                namespace
                and isinstance(item, lang.Name)
                and ":" not in item.token.text
                and item.token.text not in board.people
                and item.token.text != "people"
            ):
                item = replace(
                    item, token=replace(item.token, text=f"{namespace}:{item.token.text}")
                )
            members.append(
                _person_selected(
                    model, board, person, item, f"{name} item {index}", empty_scopes, bindings
                )
            )
        return _reify_cardinality(model, members, set(range(1, len(members) + 1)), name)
    if isinstance(operand, lang.Difference):
        left = _person_selected(
            model, board, person, operand.left, f"{name} left", empty_scopes, bindings
        )
        right = _person_selected(
            model, board, person, operand.right, f"{name} right", empty_scopes, bindings
        )
        return _reify_cardinality(model, [left, _opposite(model, right)], {2}, name)
    if isinstance(operand, lang.Filter):
        selected = _person_selected(
            model, board, person, operand.source, f"{name} source", empty_scopes, bindings
        )
        atom = lang.Atom(
            lang.Name(replace(operand.operator, text=person)),
            operand.operator,
            operand.target,
            measure=operand.measure,
        )
        matches = _reify_formula(model, board, atom, f"{name} matches", bindings, empty_scopes)
        return _reify_cardinality(model, [selected, matches], {2}, name)
    if isinstance(operand, lang.Comprehension):
        selected = _person_selected(
            model, board, person, operand.source, f"{name} source", empty_scopes, bindings
        )
        matches = _reify_formula(
            model,
            board,
            operand.condition,
            f"{name} condition",
            bindings | {operand.variable.text: person},
            empty_scopes,
        )
        return _reify_cardinality(model, [selected, matches], {2}, name)
    raise NotImplementedError(f"{name}: person set lowering is not implemented")


def _cell_empty_literal(
    model: Model, board: Board, square: Square, name: str, empty_scopes: dict[Square | str, int]
) -> int:
    if square not in empty_scopes:
        occupants = (
            [model.literal(person, square) for person in board.people]
            if square in board.free
            else []
        )
        empty_scopes[square] = _reify_cardinality(model, occupants, {0}, name)
    return empty_scopes[square]


def _static_area_ids(board: Board, operand: lang.Operand) -> set[str] | None:
    if isinstance(operand, lang.Name):
        text = operand.token.text
        if text == "areas":
            return set(board.region_names)
        if text.startswith("__entity:area:"):
            return {text.removeprefix("__entity:area:")}
        if text.startswith("area:"):
            return {board.region_id(text.removeprefix("area:"))}
        if text.startswith("tag:"):
            return board.tagged_region_ids([text.removeprefix("tag:")])
    if isinstance(operand, lang.Union):
        first = operand.items[0]
        namespace = (
            first.token.text.partition(":")[0]
            if isinstance(first, lang.Name) and ":" in first.token.text
            else None
        )
        result: set[str] = set()
        for item in operand.items:
            if (
                namespace
                and isinstance(item, lang.Name)
                and ":" not in item.token.text
                and item.token.text != "areas"
            ):
                item = replace(
                    item, token=replace(item.token, text=f"{namespace}:{item.token.text}")
                )
            regions = _static_area_ids(board, item)
            if regions is None:
                return None
            result.update(regions)
        return result
    if isinstance(operand, lang.Difference):
        left, right = _static_area_ids(board, operand.left), _static_area_ids(board, operand.right)
        return left - right if left is not None and right is not None else None
    return None


def _static_line_ids(board: Board, operand: lang.Operand) -> tuple[Sort, set[int]] | None:
    if isinstance(operand, lang.Name):
        text = operand.token.text
        if text in {"rows", "columns"}:
            return (Sort.ROW if text == "rows" else Sort.COLUMN), set(range(board.size))
        kind, separator, bounds = text.partition(":")
        if separator and kind in {"rows", "columns"}:
            first, has_last, last = bounds.partition("-")
            start = board.size if first == "last" else int(first)
            end = (board.size if last == "last" else int(last)) if has_last else start
            return (Sort.ROW if kind == "rows" else Sort.COLUMN), set(range(start - 1, end))
    if isinstance(operand, lang.Difference):
        left, right = _static_line_ids(board, operand.left), _static_line_ids(board, operand.right)
        if left is not None and right is not None and left[0] == right[0]:
            return left[0], left[1] - right[1]
    if isinstance(operand, lang.Union):
        first_item = operand.items[0]
        namespace = (
            first_item.token.text.partition(":")[0]
            if isinstance(first_item, lang.Name) and ":" in first_item.token.text
            else None
        )
        sort: Sort | None = None
        indices: set[int] = set()
        for item in operand.items:
            if (
                namespace
                and isinstance(item, lang.Name)
                and ":" not in item.token.text
                and item.token.text not in {"rows", "columns"}
            ):
                item = replace(
                    item, token=replace(item.token, text=f"{namespace}:{item.token.text}")
                )
            part = _static_line_ids(board, item)
            if part is None or (sort is not None and sort != part[0]):
                return None
            sort = part[0]
            indices.update(part[1])
        if sort is not None:
            return sort, indices
    return None


def _static_spatial_entities(
    board: Board, operand: lang.Operand
) -> dict[tuple[Sort, str], set[Square]] | None:
    if isinstance(operand, lang.Union):
        first = operand.items[0]
        namespace = (
            first.token.text.partition(":")[0]
            if isinstance(first, lang.Name) and ":" in first.token.text
            else None
        )
        result: dict[tuple[Sort, str], set[Square]] = {}
        for item in operand.items:
            if (
                namespace
                and isinstance(item, lang.Name)
                and ":" not in item.token.text
                and item.token.text not in {"areas", "rows", "columns", "cells", "objects"}
            ):
                item = replace(
                    item, token=replace(item.token, text=f"{namespace}:{item.token.text}")
                )
            part = _static_spatial_entities(board, item)
            if part is None:
                return None
            result.update(part)
        return result
    if isinstance(operand, lang.Difference):
        left = _static_spatial_entities(board, operand.left)
        right = _static_spatial_entities(board, operand.right)
        if left is None or right is None:
            return None
        return {key: footprint for key, footprint in left.items() if key not in right}
    if isinstance(operand, lang.Filter):
        source = _static_spatial_entities(board, operand.source)
        targets = _static_spatial_entities(board, operand.target)
        if source is None or targets is None:
            return None
        relation = _static_spatial_relation(board, operand.operator.text, operand.measure)
        if relation is None:
            return None
        return {
            subject: footprint
            for subject, footprint in source.items()
            if any(
                relation(subject, footprint, target, target_footprint)
                for target, target_footprint in targets.items()
            )
        }
    if isinstance(operand, lang.Projection):
        source = _static_spatial_entities(board, operand.operand)
        if source is None:
            return None
        cells = {square for footprint in source.values() for square in footprint}
        if operand.kind.text == "cell":
            return {(Sort.CELL, f"{sq.row},{sq.col}"): {sq} for sq in cells}
        if operand.kind.text == "area":
            regions = {board.region_of(square) for square in cells}
            universe = _static_spatial_entities(
                board, lang.Name(replace(operand.kind, text="areas"))
            )
            assert universe is not None
            return {key: value for key, value in universe.items() if key[1] in regions}
        sort = Sort.ROW if operand.kind.text == "row" else Sort.COLUMN
        indices = {sq.row if sort == Sort.ROW else sq.col for sq in cells}
        return {
            (sort, str(index)): {
                Square(index, other) if sort == Sort.ROW else Square(other, index)
                for other in range(board.size)
            }
            for index in indices
        }
    if isinstance(operand, (lang.Qualified, lang.AdjectiveFilter)):
        if operand.adjective.text != "free":
            return None
        inner = operand.operand if isinstance(operand, lang.Qualified) else operand.source
        entities = _static_spatial_entities(board, inner)
        if entities is None:
            return None
        return {key: cells for key, cells in entities.items() if cells.isdisjoint(board.blocked)}
    areas = _static_area_ids(board, operand)
    if areas is not None:
        return {
            (Sort.AREA, area): {
                Square(row, col)
                for row in range(board.size)
                for col in range(board.size)
                if board.region_of(Square(row, col)) == area
            }
            for area in areas
        }
    lines = _static_line_ids(board, operand)
    if lines is not None:
        sort, indices = lines
        return {
            (sort, str(index)): {
                Square(index, other) if sort == Sort.ROW else Square(other, index)
                for other in range(board.size)
            }
            for index in indices
        }
    if not isinstance(operand, lang.Name):
        return None
    text = operand.token.text
    if text.startswith("__entity:"):
        _, synthetic_sort, key = text.split(":", 2)
        if synthetic_sort == "cell":
            row, col = (int(index) for index in key.split(","))
            return {(Sort.CELL, key): {Square(row, col)}}
        kind, index = key.split(":")
        footprints = {
            "object": [item.squares for item in board.objects],
            "edge_item": [item.cells for item in board.edge_items],
            "point_object": [item.cells for item in board.point_objects],
            "mark": [item.cells for item in board.marks],
        }
        return {(Sort.FEATURE, key): set(footprints[kind][int(index)])}
    if text in {"cells", "corner:board"}:
        squares = {
            Square(row, col)
            for row in range(board.size)
            for col in range(board.size)
            if text == "cells" or (row in {0, board.size - 1} and col in {0, board.size - 1})
        }
        return {(Sort.CELL, f"{sq.row},{sq.col}"): {sq} for sq in squares}
    kind, separator, value = text.partition(":")
    if text == "objects":
        kind, separator, value = "object", ":", ""
    entries = {
        "object": [(item.name, item.squares) for item in board.objects],
        "edge_item": [(item.name, item.cells) for item in board.edge_items],
        "point_object": [(item.name, item.cells) for item in board.point_objects],
        "mark": [(item.name, item.cells) for item in board.marks],
    }
    if kind == "object_kind" and separator:
        return {
            (Sort.FEATURE, f"object:{index}"): set(item.squares)
            for index, item in enumerate(board.objects)
            if item.kind == value
        }
    if separator and kind in entries:
        return {
            (Sort.FEATURE, f"{kind}:{index}"): set(cells)
            for index, (name, cells) in enumerate(entries[kind])
            if not value or name == value
        }
    return None


def _static_spatial_relation(
    board: Board, operator: str, measure: lang.Measure | None
) -> Callable[[tuple[Sort, str], set[Square], tuple[Sort, str], set[Square]], bool] | None:
    direction = _direction(board, operator, measure) if operator.startswith("dir:") else None
    if operator not in {"is", "in", "on", "beside", "touches"} and direction is None:
        return None

    def related(
        subject: tuple[Sort, str], first: set[Square], target: tuple[Sort, str], second: set[Square]
    ) -> bool:
        if operator == "is":
            return subject == target
        if operator == "in":
            return first <= second
        if operator == "on":
            return bool(first & second)
        if subject == target:
            return False
        if direction is not None:
            return any(direction(a, b) for a in first for b in second)
        return any(
            abs(a.row - b.row) + abs(a.col - b.col) == 1
            and (operator == "touches" or board.region_of(a) == board.region_of(b))
            for a in first
            for b in second
        )

    return related


def _static_spatial_atom(board: Board, atom: lang.Atom) -> bool | None:
    subjects = _static_spatial_entities(board, atom.subject)
    targets = _static_spatial_entities(board, atom.target)
    if subjects is None or targets is None:
        return None
    related = _static_spatial_relation(board, atom.operator.text, atom.measure)
    if related is None:
        return None
    matching = {
        subject
        for subject, footprint in subjects.items()
        if any(related(subject, footprint, target, cells) for target, cells in targets.items())
    }
    determiner = atom.determiner.text if atom.determiner else "some"
    return {
        "some": bool(matching),
        "every": matching == set(subjects),
        "no": not matching,
    }[determiner]


def _spatial_universe(board: Board, sort: Sort) -> dict[tuple[Sort, str], set[Square]]:
    if sort == Sort.FEATURE:
        features = {
            "object": [item.squares for item in board.objects],
            "edge_item": [item.cells for item in board.edge_items],
            "point_object": [item.cells for item in board.point_objects],
            "mark": [item.cells for item in board.marks],
        }
        return {
            (Sort.FEATURE, f"{kind}:{index}"): set(cells)
            for kind, entries in features.items()
            for index, cells in enumerate(entries)
        }
    names = {Sort.AREA: "areas", Sort.ROW: "rows", Sort.COLUMN: "columns", Sort.CELL: "cells"}
    entities = _static_spatial_entities(board, lang.Name(lang.Token(names[sort], 1, 1)))
    assert entities is not None
    return entities


def _spatial_binding(entity: tuple[Sort, str]) -> _AreaBinding | _LineBinding | _SpatialBinding:
    sort, key = entity
    if sort == Sort.AREA:
        return _AreaBinding(key)
    elif sort in {Sort.ROW, Sort.COLUMN}:
        prefix = "rows" if sort == Sort.ROW else "columns"
        return _LineBinding(f"{prefix}:{int(key) + 1}")
    return _SpatialBinding(sort, key)


def _spatial_person_matches(
    model: Model,
    board: Board,
    entity: tuple[Sort, str],
    footprint: set[Square],
    operand: lang.Operand,
    relation: Callable[[tuple[Sort, str], set[Square], tuple[Sort, str], set[Square]], bool],
    name: str,
    empty_scopes: dict[Square | str, int],
    bindings: _Bindings,
) -> int:
    matches = []
    for person in board.people:
        selected = _person_selected(
            model, board, person, operand, f"{name} {person} selected", empty_scopes, bindings
        )
        variable, yes, _ = _hidden_boolean(
            model, "expression", f"{name} {person} match", "Murdoku expression"
        )
        model.relate(
            f"{name} {person} match",
            (person, model.var_of(selected), variable),
            lambda square, member, result, person=person: (
                result == (member and relation(entity, footprint, (Sort.PERSON, person), {square}))
            ),
        )
        matches.append(yes)
    return _reify_cardinality(model, matches, set(range(1, len(matches) + 1)), name)


def _spatial_selected(
    model: Model,
    board: Board,
    entity: tuple[Sort, str],
    footprint: set[Square],
    operand: lang.Operand,
    name: str,
    empty_scopes: dict[Square | str, int],
    bindings: _Bindings,
) -> int:
    static = _static_spatial_entities(board, operand)
    if static is not None:
        return _constant_boolean(model, entity in static, name)
    if isinstance(operand, lang.Projection):
        source_sort = _operand_sort(board, operand.operand, bindings)
        if source_sort != Sort.PERSON:
            if source_sort not in {Sort.AREA, Sort.ROW, Sort.COLUMN, Sort.CELL, Sort.FEATURE}:
                raise NotImplementedError(f"{name}: projection source is not implemented")
            sources = _spatial_universe(board, source_sort)
            members = [
                _spatial_selected(
                    model,
                    board,
                    source,
                    cells,
                    operand.operand,
                    f"{name} {source[1]} member",
                    empty_scopes,
                    bindings,
                )
                for source, cells in sources.items()
                if cells & footprint
            ]
            return _reify_cardinality(model, members, set(range(1, len(members) + 1)), name)
        members = []
        for person in board.people:
            selected = _person_selected(
                model,
                board,
                person,
                operand.operand,
                f"{name} {person} member",
                empty_scopes,
                bindings,
            )
            variable, yes, _ = _hidden_boolean(
                model, "expression", f"{name} {person} projection", "Murdoku expression"
            )
            model.relate(
                f"{name} {person} projection",
                (person, model.var_of(selected), variable),
                lambda square, member, result, footprint=footprint: (
                    result == (member and square in footprint)
                ),
            )
            members.append(yes)
        return _reify_cardinality(model, members, set(range(1, len(members) + 1)), name)
    if isinstance(operand, lang.Difference):
        left = _spatial_selected(
            model, board, entity, footprint, operand.left, f"{name} left", empty_scopes, bindings
        )
        right = _spatial_selected(
            model, board, entity, footprint, operand.right, f"{name} right", empty_scopes, bindings
        )
        return _reify_cardinality(model, [left, _opposite(model, right)], {2}, name)
    if isinstance(operand, lang.Comprehension):
        selected = _spatial_selected(
            model,
            board,
            entity,
            footprint,
            operand.source,
            f"{name} source",
            empty_scopes,
            bindings,
        )
        matches = _reify_formula(
            model,
            board,
            operand.condition,
            f"{name} condition",
            bindings | {operand.variable.text: _spatial_binding(entity)},
            empty_scopes,
        )
        return _reify_cardinality(model, [selected, matches], {2}, name)
    if isinstance(operand, (lang.Qualified, lang.AdjectiveFilter)):
        inner = operand.operand if isinstance(operand, lang.Qualified) else operand.source
        selected = _spatial_selected(
            model, board, entity, footprint, inner, f"{name} source", empty_scopes, bindings
        )
        adjective = operand.adjective.text
        if adjective == "free":
            matches = _constant_boolean(model, footprint.isdisjoint(board.blocked), f"{name} free")
        else:
            if entity[0] == Sort.CELL:
                row, col = (int(index) for index in entity[1].split(","))
                empty = _cell_empty_literal(
                    model, board, Square(row, col), f"{name} empty", empty_scopes
                )
            elif entity[0] == Sort.AREA:
                empty = _area_empty_literal(model, board, entity[1], f"{name} empty", empty_scopes)
            else:
                occupants = [
                    model.literal(person, square)
                    for person in board.people
                    for square in board.free
                    if square in footprint
                ]
                empty = _reify_cardinality(model, occupants, {0}, f"{name} empty")
            matches = empty if adjective == "empty" else _opposite(model, empty)
        return _reify_cardinality(model, [selected, matches], {2}, name)
    if isinstance(operand, lang.Filter):
        source = _spatial_selected(
            model,
            board,
            entity,
            footprint,
            operand.source,
            f"{name} source",
            empty_scopes,
            bindings,
        )
        related = _static_spatial_relation(board, operand.operator.text, operand.measure)
        if related is None:
            raise NotImplementedError(f"{name}: spatial filter lowering is not implemented")
        targets = _static_spatial_entities(board, operand.target)
        if targets is not None:
            matches = _constant_boolean(
                model,
                any(related(entity, footprint, target, cells) for target, cells in targets.items()),
                f"{name} matches",
            )
        else:
            target_sort = _operand_sort(board, operand.target, bindings)
            if target_sort == Sort.PERSON:
                matches = _spatial_person_matches(
                    model,
                    board,
                    entity,
                    footprint,
                    operand.target,
                    related,
                    f"{name} matches",
                    empty_scopes,
                    bindings,
                )
                return _reify_cardinality(model, [source, matches], {2}, name)
            if target_sort not in {Sort.AREA, Sort.ROW, Sort.COLUMN, Sort.CELL, Sort.FEATURE}:
                raise NotImplementedError(f"{name}: spatial filter target is not implemented")
            possible = _spatial_universe(board, target_sort)
            target_members = [
                _spatial_selected(
                    model,
                    board,
                    target,
                    cells,
                    operand.target,
                    f"{name} target {target[1]}",
                    empty_scopes,
                    bindings,
                )
                for target, cells in possible.items()
                if related(entity, footprint, target, cells)
            ]
            matches = _reify_cardinality(
                model, target_members, set(range(1, len(target_members) + 1)), f"{name} matches"
            )
        return _reify_cardinality(model, [source, matches], {2}, name)
    if isinstance(operand, lang.Union):
        first = operand.items[0]
        namespace = (
            first.token.text.partition(":")[0]
            if isinstance(first, lang.Name) and ":" in first.token.text
            else None
        )
        members = []
        for index, item in enumerate(operand.items, 1):
            if (
                namespace
                and isinstance(item, lang.Name)
                and ":" not in item.token.text
                and item.token.text not in {"areas", "rows", "columns", "cells", "objects"}
            ):
                item = replace(
                    item, token=replace(item.token, text=f"{namespace}:{item.token.text}")
                )
            members.append(
                _spatial_selected(
                    model,
                    board,
                    entity,
                    footprint,
                    item,
                    f"{name} item {index}",
                    empty_scopes,
                    bindings,
                )
            )
        return _reify_cardinality(model, members, set(range(1, len(members) + 1)), name)
    raise NotImplementedError(f"{name}: spatial set lowering is not implemented")


def _spatial_selection_literals(
    model: Model,
    board: Board,
    operand: lang.Operand,
    name: str,
    empty_scopes: dict[Square | str, int],
    bindings: _Bindings,
) -> list[int]:
    sort = _operand_sort(board, operand, bindings)
    if sort not in {Sort.AREA, Sort.ROW, Sort.COLUMN, Sort.CELL, Sort.FEATURE}:
        raise NotImplementedError(f"{name}: spatial set lowering is not implemented")
    return [
        _spatial_selected(
            model, board, entity, footprint, operand, f"{name} {entity[1]}", empty_scopes, bindings
        )
        for entity, footprint in _spatial_universe(board, sort).items()
    ]


def _reify_spatial_atom(
    model: Model,
    board: Board,
    atom: lang.Atom,
    name: str,
    empty_scopes: dict[Square | str, int],
    bindings: _Bindings,
) -> int:
    relation = _static_spatial_relation(board, atom.operator.text, atom.measure)
    if relation is None:
        raise NotImplementedError(f"{name}: spatial relation lowering is not implemented")
    subjects = _static_spatial_entities(board, atom.subject)
    if subjects is None:
        sort = _operand_sort(board, atom.subject, bindings)
        if sort not in {Sort.AREA, Sort.ROW, Sort.COLUMN, Sort.CELL, Sort.FEATURE}:
            raise NotImplementedError(f"{name}: spatial subject is not implemented")
        subjects = _spatial_universe(board, sort)
    targets = _static_spatial_entities(board, atom.target)
    target_people = False
    if targets is None:
        sort = _operand_sort(board, atom.target, bindings)
        if sort == Sort.PERSON:
            target_people = True
            targets = {}
        elif sort in {Sort.AREA, Sort.ROW, Sort.COLUMN, Sort.CELL, Sort.FEATURE}:
            targets = _spatial_universe(board, sort)
        else:
            raise NotImplementedError(f"{name}: spatial target is not implemented")
    target_members = {
        target: _spatial_selected(
            model,
            board,
            target,
            cells,
            atom.target,
            f"{name} target {target[1]}",
            empty_scopes,
            bindings,
        )
        for target, cells in targets.items()
    }
    quantifier = atom.determiner.text if atom.determiner else "some"
    results = []
    for subject, footprint in subjects.items():
        selected = _spatial_selected(
            model,
            board,
            subject,
            footprint,
            atom.subject,
            f"{name} subject {subject[1]}",
            empty_scopes,
            bindings,
        )
        if target_people:
            match = _spatial_person_matches(
                model,
                board,
                subject,
                footprint,
                atom.target,
                relation,
                f"{name} {subject[1]} matches",
                empty_scopes,
                bindings,
            )
        else:
            matches = [
                target_members[target]
                for target, cells in targets.items()
                if relation(subject, footprint, target, cells)
            ]
            match = _reify_cardinality(
                model, matches, set(range(1, len(matches) + 1)), f"{name} {subject[1]} matches"
            )
        results.append(
            _reify_cardinality(
                model,
                [selected, _opposite(model, match) if quantifier == "every" else match],
                {2},
                f"{name} {subject[1]} result",
            )
        )
    allowed = {0} if quantifier in {"every", "no"} else set(range(1, len(results) + 1))
    return _reify_cardinality(model, results, allowed, name)


def _reify_person_spatial_target(
    model: Model,
    board: Board,
    person: str,
    atom: lang.Atom,
    name: str,
    empty_scopes: dict[Square | str, int],
    bindings: _Bindings,
) -> int:
    sort = _operand_sort(board, atom.target, bindings)
    if sort not in {Sort.AREA, Sort.ROW, Sort.COLUMN, Sort.CELL, Sort.FEATURE}:
        raise NotImplementedError(f"{name}: spatial target is not implemented")
    direction = (
        _direction(board, atom.operator.text, atom.measure)
        if atom.operator.text.startswith("dir:")
        else None
    )
    if atom.operator.text not in {"in", "on", "beside", "touches"} and direction is None:
        raise NotImplementedError(f"{name}: spatial relation is not implemented")
    results = []
    for entity, footprint in _spatial_universe(board, sort).items():
        selected = _spatial_selected(
            model,
            board,
            entity,
            footprint,
            atom.target,
            f"{name} {entity[1]} selected",
            empty_scopes,
            bindings,
        )
        variable, yes, _ = _hidden_boolean(
            model, "expression", f"{name} {entity[1]} match", "Murdoku expression"
        )
        model.relate(
            f"{name} {entity[1]} match",
            (person, model.var_of(selected), variable),
            lambda square, member, result, footprint=footprint: (
                result
                == (
                    member
                    and _position_matches(board, square, atom.operator.text, footprint, direction)
                )
            ),
        )
        results.append(yes)
    result = _reify_cardinality(model, results, set(range(1, len(results) + 1)), name)
    return (
        _opposite(model, result)
        if atom.determiner is not None and atom.determiner.text == "no"
        else result
    )


def _area_empty_literal(
    model: Model, board: Board, region: str, name: str, empty_scopes: dict[Square | str, int]
) -> int:
    key = f"area:{region}"
    if key not in empty_scopes:
        occupants = [
            model.literal(person, square)
            for person in board.people
            for square in board.free
            if board.region_of(square) == region
        ]
        empty_scopes[key] = _reify_cardinality(model, occupants, {0}, name)
    return empty_scopes[key]


def _reify_adjective_atom(
    model: Model,
    board: Board,
    atom: lang.AdjectiveAtom,
    name: str,
    empty_scopes: dict[Square | str, int],
) -> int:
    entities = _static_spatial_entities(board, atom.subject)
    if entities is not None and len(entities) == 1:
        sort = next(iter(entities))[0]
        minimum = maximum = 1
    else:
        shape = infer_operand(board, atom.subject)
        sort, minimum, maximum = shape.sort, shape.minimum, shape.maximum
    cells = _static_cells(board, atom.subject)
    if minimum != 1 or maximum != 1 or cells is None:
        raise NotImplementedError(f"{name}: adjective lowering is not implemented")
    if atom.adjective.text == "free":
        _, yes, no = _hidden_boolean(model, "expression", name, "Murdoku expression")
        model.assign(
            yes if cells.isdisjoint(board.blocked) else no,
            "clue",
            name,
            sources=(f"{name} state",),
        )
        result = yes
    elif sort == Sort.CELL and len(cells) == 1:
        empty = _cell_empty_literal(model, board, next(iter(cells)), name, empty_scopes)
        result = empty if atom.adjective.text == "empty" else _opposite(model, empty)
    elif sort == Sort.AREA and (regions := _static_area_ids(board, atom.subject)) is not None:
        if len(regions) != 1:
            raise NotImplementedError(f"{name}: adjective lowering is not implemented")
        empty = _area_empty_literal(model, board, next(iter(regions)), name, empty_scopes)
        result = empty if atom.adjective.text == "empty" else _opposite(model, empty)
    else:
        literals = [
            model.literal(person, square)
            for person in board.people
            for square in board.free
            if square in cells
        ]
        allowed = (
            {0}
            if atom.adjective.text == "empty"
            else set(range(1, min(len(literals), len(board.people)) + 1))
        )
        result = _reify_cardinality(model, literals, allowed, name)
    return (
        _opposite(model, result)
        if atom.determiner is not None and atom.determiner.text == "no"
        else result
    )


def _cell_occupancy_scope(board: Board, operand: lang.Operand) -> tuple[str, list[Square]] | None:
    if isinstance(operand, lang.Filter) and operand.operator.text in {"in", "on"}:
        scope = _cell_occupancy_scope(board, operand.source)
        target = _static_cells(board, operand.target)
        if scope is None or target is None:
            return None
        adjective, squares = scope
        return adjective, [square for square in squares if square in target]
    if not isinstance(operand, (lang.Qualified, lang.AdjectiveFilter)):
        return None
    adjective = operand.adjective.text
    source = operand.operand if isinstance(operand, lang.Qualified) else operand.source
    if adjective not in {"empty", "occupied"}:
        return None
    free_only = False
    if isinstance(source, (lang.Qualified, lang.AdjectiveFilter)):
        if source.adjective.text != "free":
            return None
        free_only = True
        source = source.operand if isinstance(source, lang.Qualified) else source.source
    if not isinstance(source, lang.Name) or source.token.text != "cells":
        return None
    squares = (
        list(board.free)
        if free_only
        else [Square(row, col) for row in range(board.size) for col in range(board.size)]
    )
    return adjective, squares


def _area_occupancy_scope(board: Board, operand: lang.Operand) -> tuple[str, set[str]] | None:
    if isinstance(operand, lang.Filter) and operand.operator.text in {"in", "on"}:
        scope = _area_occupancy_scope(board, operand.source)
        if scope is None:
            return None
        adjective, regions = scope
        targets = _static_area_ids(board, operand.target)
        if targets is not None:
            return adjective, regions & targets
        if operand.operator.text == "on":
            cells = _static_cells(board, operand.target)
            if cells is not None:
                return adjective, regions & {board.region_of(square) for square in cells}
        return None
    if not isinstance(operand, (lang.Qualified, lang.AdjectiveFilter)):
        return None
    adjective = operand.adjective.text
    source = operand.operand if isinstance(operand, lang.Qualified) else operand.source
    selected_regions = _static_area_ids(board, source)
    if adjective not in {"empty", "occupied"} or selected_regions is None:
        return None
    return adjective, selected_regions


def _occupancy_literals(
    model: Model,
    board: Board,
    operand: lang.Operand,
    name: str,
    empty_scopes: dict[Square | str, int],
) -> list[int] | None:
    cell_scope = _cell_occupancy_scope(board, operand)
    if cell_scope is not None:
        adjective, squares = cell_scope
        empty_literals = [
            _cell_empty_literal(model, board, square, f"{name} {square} empty", empty_scopes)
            for square in squares
        ]
    else:
        area_scope = _area_occupancy_scope(board, operand)
        if area_scope is None:
            return None
        adjective, regions = area_scope
        empty_literals = [
            _area_empty_literal(model, board, region, f"{name} {region} empty", empty_scopes)
            for region in sorted(regions)
        ]
    return (
        empty_literals
        if adjective == "empty"
        else [_opposite(model, literal) for literal in empty_literals]
    )


def _number_variable(
    model: Model,
    board: Board,
    number: lang.Number,
    name: str,
    bindings: _Bindings,
    empty_scopes: dict[Square | str, int],
) -> tuple[str, set[int]]:
    selections: list[int] | None = None
    children: tuple[str, str] | None = None
    operator = ""
    if isinstance(number, lang.Integer):
        values = {int(number.value.text)}
    elif isinstance(number, lang.Count):
        roles = _static_roles(board, number.operand, bindings)
        if roles is not None:
            values = {len(roles)}
        elif _operand_sort(board, number.operand, bindings) == Sort.ROLE:
            selections = [
                _role_selected(
                    model,
                    board,
                    role.name,
                    number.operand,
                    f"{name} {role.name}",
                    empty_scopes,
                    bindings,
                )
                for role in board.roles
            ]
            values = set(range(len(selections) + 1))
        else:
            sort = _operand_sort(board, number.operand, bindings)
            operand = _bind_operand(number.operand, bindings)
            entities = _static_spatial_entities(board, operand)
            if entities is not None:
                values = {len(entities)}
            else:
                selections = _occupancy_literals(model, board, operand, name, empty_scopes)
                if selections is None:
                    if sort == Sort.PERSON:
                        selections = [
                            _person_selected(
                                model,
                                board,
                                person,
                                operand,
                                f"{name} {person} member",
                                empty_scopes,
                                bindings,
                            )
                            for person in board.people
                        ]
                    else:
                        selections = _spatial_selection_literals(
                            model, board, operand, name, empty_scopes, bindings
                        )
                values = set(range(len(selections) + 1))
    else:
        left, left_values = _number_variable(
            model, board, number.left, f"{name} left", bindings, empty_scopes
        )
        right, right_values = _number_variable(
            model, board, number.right, f"{name} right", bindings, empty_scopes
        )
        operator = number.operator.text
        values = {
            first + second if operator == "+" else first - second
            for first in left_values
            for second in right_values
        }
        children = left, right
    variable = _auxiliary_variable(model, "expression_number")
    options = {value: model.literal(variable, value) for value in sorted(values)}
    model.constrain(
        f"{name} domain",
        Kind.EXACTLY_ONE,
        options.values(),
        defines=variable,
        hidden=True,
        family="Murdoku expression",
    )
    if selections is not None:
        for value, literal in options.items():
            model.constrain(
                f"{name} count {value}",
                Kind.COUNT,
                selections,
                allowed_counts={value},
                reified_by=literal,
                family="Murdoku expression",
            )
    if children is not None:
        model.relate(
            name,
            (*children, variable),
            lambda left, right, result: (
                result == (left + right if operator == "+" else left - right)
            ),
        )
    return variable, values


def _reify_superlative(
    model: Model,
    board: Board,
    person: str,
    atom: lang.Atom,
    name: str,
    bindings: _Bindings,
    empty_scopes: dict[Square | str, int],
) -> int:
    mode = atom.operator.text.removeprefix("dir:")
    order, separator, metric = mode.partition(":")
    metric = metric if separator else "manhattan"
    areas = _area_distances(board) if metric == "areas" else {}

    def distance(a: Square, b: Square) -> int:
        rows, cols = abs(a.row - b.row), abs(a.col - b.col)
        return {
            "rows": lambda: rows,
            "cols": lambda: cols,
            "manhattan": lambda: rows + cols,
            "king": lambda: max(rows, cols),
            "euclidean": lambda: rows * rows + cols * cols,
            "areas": lambda: areas[board.region_of(a), board.region_of(b)],
        }[metric]()

    def nearer(first: Square, rival: Square, cells: set[Square]) -> bool:
        own = min(distance(first, target) for target in cells)
        other = min(distance(rival, target) for target in cells)
        return own < other if order == "nearest" else own > other

    sort = _operand_sort(board, atom.target, bindings)
    if sort == Sort.PERSON:
        target_members = {
            target: _person_selected(
                model, board, target, atom.target, f"{name} {target} target", empty_scopes, bindings
            )
            for target in board.people
        }
        candidates: list[tuple[str | None, set[Square] | None, int]] = [
            (target, None, member) for target, member in target_members.items() if target != person
        ]
    else:
        target_members = {}
        entities = _static_spatial_entities(board, atom.target)
        if entities is None:
            entities = _spatial_universe(board, sort)
        candidates = [
            (
                None,
                footprint,
                _spatial_selected(
                    model,
                    board,
                    entity,
                    footprint,
                    atom.target,
                    f"{name} {entity[1]} target",
                    empty_scopes,
                    bindings,
                ),
            )
            for entity, footprint in entities.items()
        ]

    alternatives = []
    for index, (target_person, target_cells, selected) in enumerate(candidates, 1):
        witnesses = [selected]
        for rival in board.people:
            if rival in (person, target_person):
                continue
            label = f"{name} target {index} rival {rival}"
            variable, yes, _ = _hidden_boolean(model, "expression", label, "Murdoku expression")
            if target_person is None:
                assert target_cells is not None
                model.relate(
                    label,
                    (person, rival, variable),
                    lambda first, candidate, result, cells=target_cells: (
                        result == nearer(first, candidate, cells)
                    ),
                )
            else:
                model.relate(
                    label,
                    (person, target_person, rival, variable),
                    lambda first, target, candidate, result: (
                        result == nearer(first, candidate, {target})
                    ),
                )
                yes = _reify_cardinality(model, [target_members[rival], yes], {1, 2}, label)
            witnesses.append(yes)
        alternatives.append(
            _reify_cardinality(model, witnesses, {len(witnesses)}, f"{name} {index}")
        )
    result = _reify_cardinality(model, alternatives, set(range(1, len(alternatives) + 1)), name)
    return (
        _opposite(model, result)
        if atom.determiner is not None and atom.determiner.text == "no"
        else result
    )


def _reify_formula(
    model: Model,
    board: Board,
    formula: lang.Formula,
    name: str,
    bindings: _Bindings | None = None,
    empty_scopes: dict[Square | str, int] | None = None,
) -> int:
    bindings = {} if bindings is None else bindings
    empty_scopes = {} if empty_scopes is None else empty_scopes
    if isinstance(formula, lang.Atom):
        if formula.operator.text == "is":
            subject_roles = _static_roles(board, formula.subject, bindings)
            target_roles = _static_roles(board, formula.target, bindings)
            if subject_roles is not None and target_roles is not None:
                selected_roles = subject_roles & target_roles
                determiner = formula.determiner.text if formula.determiner else "some"
                matched = {
                    "some": bool(selected_roles),
                    "every": selected_roles == subject_roles,
                    "no": not selected_roles,
                }[determiner]
                return _constant_boolean(model, matched, name)
            if _operand_sort(board, formula.subject, bindings) == Sort.ROLE:
                determiner = formula.determiner.text if formula.determiner else "some"
                matches = []
                for role_spec in board.roles:
                    subject = _role_selected(
                        model,
                        board,
                        role_spec.name,
                        formula.subject,
                        f"{name} {role_spec.name} subject",
                        empty_scopes,
                        bindings,
                    )
                    target = _role_selected(
                        model,
                        board,
                        role_spec.name,
                        formula.target,
                        f"{name} {role_spec.name} target",
                        empty_scopes,
                        bindings,
                    )
                    matches.append(
                        _reify_cardinality(
                            model,
                            [
                                subject,
                                _opposite(model, target) if determiner == "every" else target,
                            ],
                            {2},
                            f"{name} {role_spec.name} match",
                        )
                    )
                allowed = {0} if determiner in {"every", "no"} else set(range(1, len(matches) + 1))
                return _reify_cardinality(model, matches, allowed, name)
            if _operand_sort(board, formula.target, bindings) == Sort.ROLE:
                bound_subject = _bind_operand(formula.subject, bindings)
                if (
                    not isinstance(bound_subject, lang.Name)
                    or bound_subject.token.text not in board.people
                ):
                    variable_name = "?_expression"
                    while variable_name in bindings:
                        variable_name += "_"
                    variable = replace(formula.operator, text=variable_name)
                    quantified = lang.Quantified(
                        formula.determiner or replace(formula.operator, text="some"),
                        None,
                        (variable,),
                        bound_subject,
                        replace(formula, subject=lang.Name(variable), determiner=None),
                    )
                    return _reify_formula(model, board, quantified, name, bindings, empty_scopes)
                person = bound_subject.token.text
                matches = []
                for role_spec in board.roles:
                    role_selection = _role_selected(
                        model,
                        board,
                        role_spec.name,
                        formula.target,
                        f"{name} {role_spec.name}",
                        empty_scopes,
                        bindings,
                    )
                    member = model.literal(board.role_variable(person, role_spec.name), True)
                    matches.append(
                        _reify_cardinality(
                            model, [role_selection, member], {2}, f"{name} {role_spec.name} match"
                        )
                    )
                result = _reify_cardinality(model, matches, set(range(1, len(matches) + 1)), name)
                return (
                    _opposite(model, result)
                    if formula.determiner is not None and formula.determiner.text == "no"
                    else result
                )
        target_operand = formula.target
        if isinstance(target_operand, lang.Name):
            bound = bindings.get(target_operand.token.text)
            if isinstance(bound, _RoleBinding):
                if formula.operator.text != "is":
                    raise NotImplementedError(f"{name}: bound role relation is not implemented")
                target_operand = replace(
                    target_operand, token=replace(target_operand.token, text=f"role:{bound.name}")
                )
        atom = replace(
            formula,
            subject=_bind_operand(formula.subject, bindings),
            target=_bind_operand(target_operand, bindings),
        )
        spatial_match = _static_spatial_atom(board, atom)
        if spatial_match is not None:
            return _constant_boolean(model, spatial_match, name)
        variable_name = "?_expression"
        while variable_name in bindings:
            variable_name += "_"
        variable = replace(atom.operator, text=variable_name)
        subject_person = (
            atom.subject.token.text
            if isinstance(atom.subject, lang.Name) and atom.subject.token.text in board.people
            else None
        )
        subject_sort = _operand_sort(board, atom.subject, bindings)
        if subject_sort != Sort.PERSON:
            return _reify_spatial_atom(model, board, atom, name, empty_scopes, bindings)
        if subject_person is None:
            quantified = lang.Quantified(
                atom.determiner or replace(atom.operator, text="some"),
                None,
                (variable,),
                atom.subject,
                replace(atom, subject=lang.Name(variable), determiner=None),
            )
            return _reify_formula(model, board, quantified, name, bindings, empty_scopes)
        if subject_person is not None and atom.operator.text.startswith(
            ("dir:nearest", "dir:furthest")
        ):
            return _reify_superlative(
                model, board, subject_person, atom, name, bindings, empty_scopes
            )
        if (
            subject_person is not None
            and atom.operator.text == "is"
            and _operand_sort(board, atom.target, bindings) == Sort.PERSON
        ):
            result = _person_selected(
                model, board, subject_person, atom.target, name, empty_scopes, bindings
            )
            return (
                _opposite(model, result)
                if atom.determiner is not None and atom.determiner.text == "no"
                else result
            )
        if (
            subject_person is not None
            and atom.operator.text != "is"
            and _operand_sort(board, atom.target, bindings) == Sort.PERSON
            and not (isinstance(atom.target, lang.Name) and atom.target.token.text in board.people)
        ):
            quantified = lang.Quantified(
                replace(atom.operator, text="some"),
                None,
                (variable,),
                atom.target,
                replace(atom, target=lang.Name(variable), determiner=None),
            )
            result = _reify_formula(model, board, quantified, name, bindings, empty_scopes)
            return (
                _opposite(model, result)
                if atom.determiner is not None and atom.determiner.text == "no"
                else result
            )
        if (
            subject_person is not None
            and atom.operator.text != "is"
            and _operand_sort(board, atom.target, bindings) != Sort.PERSON
            and _static_cells(board, atom.target) is None
            and not (
                isinstance(atom.target, lang.Projection)
                and isinstance(atom.target.operand, lang.Name)
                and atom.target.operand.token.text in board.people
            )
        ):
            return _reify_person_spatial_target(
                model, board, subject_person, atom, name, empty_scopes, bindings
            )
        return _reify_atom(model, board, atom, name)
    if isinstance(formula, lang.AdjectiveAtom):
        adjective_atom = replace(formula, subject=_bind_operand(formula.subject, bindings))
        entities = _static_spatial_entities(board, adjective_atom.subject)
        if entities is not None and len(entities) == 1:
            return _reify_adjective_atom(model, board, adjective_atom, name, empty_scopes)
        variable_name = "?_expression"
        while variable_name in bindings:
            variable_name += "_"
        variable = replace(formula.operator, text=variable_name)
        quantified = lang.Quantified(
            formula.determiner or replace(formula.operator, text="some"),
            None,
            (variable,),
            adjective_atom.subject,
            replace(adjective_atom, subject=lang.Name(variable), determiner=None),
        )
        return _reify_formula(model, board, quantified, name, bindings, empty_scopes)
    if isinstance(formula, lang.Negation):
        return _opposite(
            model,
            _reify_formula(model, board, formula.formula, f"{name} not", bindings, empty_scopes),
        )
    if isinstance(formula, lang.SetComparison):
        left_roles = _static_roles(board, formula.left, bindings)
        right_roles = _static_roles(board, formula.right, bindings)
        if left_roles is not None and right_roles is not None:
            same_roles = left_roles == right_roles
            return _constant_boolean(
                model, same_roles if formula.operator.text == "=" else not same_roles, name
            )
        if _operand_sort(board, formula.left, bindings) == Sort.ROLE:
            equalities = []
            for role_spec in board.roles:
                left = _role_selected(
                    model,
                    board,
                    role_spec.name,
                    formula.left,
                    f"{name} {role_spec.name} left",
                    empty_scopes,
                    bindings,
                )
                right = _role_selected(
                    model,
                    board,
                    role_spec.name,
                    formula.right,
                    f"{name} {role_spec.name} right",
                    empty_scopes,
                    bindings,
                )
                equalities.append(
                    _reify_cardinality(
                        model, [left, right], {0, 2}, f"{name} {role_spec.name} equal"
                    )
                )
            result = _reify_cardinality(model, equalities, {len(equalities)}, name)
            return _opposite(model, result) if formula.operator.text == "!=" else result
        left_set = _bind_operand(formula.left, bindings)
        right_set = _bind_operand(formula.right, bindings)
        left_entities = _static_spatial_entities(board, left_set)
        right_entities = _static_spatial_entities(board, right_set)
        if left_entities is not None and right_entities is not None:
            same_entities = left_entities.keys() == right_entities.keys()
            return _constant_boolean(
                model, same_entities if formula.operator.text == "=" else not same_entities, name
            )
        sort = _operand_sort(board, left_set, bindings)
        equalities = []
        if sort == Sort.PERSON:
            pairs = [
                (
                    _person_selected(
                        model,
                        board,
                        person,
                        left_set,
                        f"{name} {person} left",
                        empty_scopes,
                        bindings,
                    ),
                    _person_selected(
                        model,
                        board,
                        person,
                        right_set,
                        f"{name} {person} right",
                        empty_scopes,
                        bindings,
                    ),
                )
                for person in board.people
            ]
        else:
            left_members = _spatial_selection_literals(
                model, board, left_set, f"{name} left", empty_scopes, bindings
            )
            right_members = _spatial_selection_literals(
                model, board, right_set, f"{name} right", empty_scopes, bindings
            )
            pairs = list(zip(left_members, right_members, strict=True))
        for index, (left_member, right_member) in enumerate(pairs, 1):
            equalities.append(
                _reify_cardinality(
                    model, [left_member, right_member], {0, 2}, f"{name} {index} equal"
                )
            )
        result = _reify_cardinality(model, equalities, {len(equalities)}, name)
        return _opposite(model, result) if formula.operator.text == "!=" else result
    count = _count_predicate(formula)
    if count is not None:
        operand, predicate, _ = count
        roles = _static_roles(board, operand, bindings)
        if roles is not None:
            return _constant_boolean(model, predicate(len(roles)), name)
        if _operand_sort(board, operand, bindings) == Sort.ROLE:
            literals = [
                _role_selected(
                    model, board, role.name, operand, f"{name} {role.name}", empty_scopes, bindings
                )
                for role in board.roles
            ]
            allowed = {value for value in range(len(literals) + 1) if predicate(value)}
            return _reify_cardinality(model, literals, allowed, name)
        operand = _bind_operand(operand, bindings)
        entities = _static_spatial_entities(board, operand)
        if entities is not None:
            return _constant_boolean(model, predicate(len(entities)), name)
        occupancy = _occupancy_literals(model, board, operand, name, empty_scopes)
        if occupancy is not None:
            permitted = {value for value in range(len(occupancy) + 1) if predicate(value)}
            return _reify_cardinality(model, occupancy, permitted, name)
        role_scope = _role_scope(board, operand)
        keys = _counted_keys(board, operand) if role_scope is None else None
        dynamic = keys is None and role_scope is None
        if dynamic and _operand_sort(board, operand, bindings) != Sort.PERSON:
            literals = _spatial_selection_literals(
                model, board, operand, name, empty_scopes, bindings
            )
            permitted = {value for value in range(len(literals) + 1) if predicate(value)}
            return _reify_cardinality(model, literals, permitted, name)
        maximum = (
            len(board.people)
            if role_scope is not None or dynamic
            else min(len(keys or []), len(board.people))
        )
        permitted = {value for value in range(maximum + 1) if predicate(value)}
        if not permitted:
            return _reify_cardinality(model, [], set(), name)
        if role_scope is not None:
            role, squares = role_scope
            literals = _role_selection_literals(model, board, role, squares, name)
        elif dynamic:
            literals = [
                _person_selected(
                    model, board, person, operand, f"{name} {person} member", empty_scopes, bindings
                )
                for person in board.people
            ]
        else:
            assert keys is not None
            literals = [model.literal(variable, value) for variable, value in keys]
        return _reify_cardinality(model, literals, permitted, name)
    if isinstance(formula, (lang.NumberComparison, lang.Parity, lang.NumberRange)):
        if isinstance(formula, lang.NumberComparison):
            left_number, _ = _number_variable(
                model, board, formula.left, f"{name} left", bindings, empty_scopes
            )
            right_number, _ = _number_variable(
                model, board, formula.right, f"{name} right", bindings, empty_scopes
            )
            operator = formula.operator.text
            compare: Callable[[int, int], bool] = {
                "=": lambda a, b: a == b,
                "!=": lambda a, b: a != b,
                "<": lambda a, b: a < b,
                "<=": lambda a, b: a <= b,
                ">": lambda a, b: a > b,
                ">=": lambda a, b: a >= b,
            }[operator]
            output_variable, yes, _ = _hidden_boolean(
                model, "expression", name, "Murdoku expression"
            )
            model.relate(
                name,
                (left_number, right_number, output_variable),
                lambda a, b, result: result == compare(a, b),
            )
            return yes
        number, _ = _number_variable(
            model, board, formula.number, f"{name} number", bindings, empty_scopes
        )
        if isinstance(formula, lang.Parity):
            wanted = int(formula.parity.text == "odd")

            def test(value: int) -> bool:
                return value % 2 == wanted
        else:
            lower, upper = int(formula.lower.text), int(formula.upper.text)

            def test(value: int) -> bool:
                return lower <= value <= upper

        output_variable, yes, _ = _hidden_boolean(model, "expression", name, "Murdoku expression")
        model.relate(name, (number, output_variable), lambda value, result: result == test(value))
        return yes
    if isinstance(formula, lang.Binary):
        left = _reify_formula(model, board, formula.left, f"{name} left", bindings, empty_scopes)
        right = _reify_formula(model, board, formula.right, f"{name} right", bindings, empty_scopes)
        operator = formula.operator.text
        if operator == "if":
            left = _opposite(model, left)
            operator = "or"
        allowed = {"and": {2}, "or": {1, 2}, "iff": {0, 2}}[operator]
        return _reify_cardinality(model, [left, right], allowed, name)
    if isinstance(formula, lang.Choice):
        literals = [
            _reify_formula(model, board, choice, f"{name} option {index}", bindings, empty_scopes)
            for index, choice in enumerate(formula.choices, 1)
        ]
        target = int(formula.count.text)
        kind = " ".join(formula.quantifier.text.split())
        allowed = {
            "exactly": {target} if target <= len(literals) else set(),
            "at least": set(range(target, len(literals) + 1)),
            "at most": set(range(min(target, len(literals)) + 1)),
        }[kind]
        return _reify_cardinality(model, literals, allowed, name)
    if isinstance(formula, lang.Quantified):
        role_domain = _static_roles(board, formula.source, bindings)
        area_adjective: str | None = None
        cell_adjective: str | None = None
        spatial_domain = False
        role_dynamic = (
            role_domain is None and _operand_sort(board, formula.source, bindings) == Sort.ROLE
        )
        if role_domain is not None:
            source = formula.source
            dynamic = False
            domain: list[str | _RoleBinding | _AreaBinding | _LineBinding | _SpatialBinding] = [
                _RoleBinding(role.name) for role in board.roles if role.name in role_domain
            ]
        elif role_dynamic:
            source = formula.source
            dynamic = True
            domain = [_RoleBinding(role.name) for role in board.roles]
        else:
            source = _bind_operand(formula.source, bindings)
            area_domain = _static_area_ids(board, source)
            area_scope = _area_occupancy_scope(board, source)
            if area_domain is None and area_scope is not None:
                area_adjective, area_domain = area_scope
            if area_domain is not None:
                dynamic = area_adjective is not None
                domain = [
                    _AreaBinding(region) for region in board.region_names if region in area_domain
                ]
            else:
                line_domain = _static_line_ids(board, source)
                if line_domain is not None:
                    dynamic = False
                    line_kind, line_indices = line_domain
                    prefix = "rows" if line_kind == Sort.ROW else "columns"
                    domain = [
                        _LineBinding(f"{prefix}:{index + 1}") for index in sorted(line_indices)
                    ]
                else:
                    cell_scope = _cell_occupancy_scope(board, source)
                    entities = _static_spatial_entities(board, source)
                    if cell_scope is not None:
                        cell_adjective, selected_squares = cell_scope
                        dynamic = True
                        domain = [
                            _SpatialBinding(Sort.CELL, f"{square.row},{square.col}")
                            for square in selected_squares
                        ]
                    elif entities is not None:
                        dynamic = False
                        ordered = sorted(entities, key=lambda item: (item[0].value, item[1]))
                        domain = [_spatial_binding(entity) for entity in ordered]
                    else:
                        people = _static_people(board, source)
                        dynamic = people is None
                        if people is None:
                            sort = _operand_sort(board, source, bindings)
                            if sort == Sort.PERSON:
                                people = set(board.people)
                            elif sort in {
                                Sort.AREA,
                                Sort.ROW,
                                Sort.COLUMN,
                                Sort.CELL,
                                Sort.FEATURE,
                            }:
                                spatial_domain = True
                                universe = _spatial_universe(board, sort)
                                domain = [_spatial_binding(entity) for entity in universe]
                            else:
                                raise NotImplementedError(
                                    f"{name}: quantifier source lowering is not implemented"
                                )
                        if people is not None:
                            domain = [person for person in board.people if person in people]
        quantifier = " ".join(formula.quantifier.text.split())
        literals = []
        for index, values in enumerate(permutations(domain, len(formula.variables)), 1):
            binding_name = f"{name} binding {index}"
            body = _reify_formula(
                model,
                board,
                formula.body,
                f"{binding_name} body",
                bindings
                | dict(zip((variable.text for variable in formula.variables), values, strict=True)),
                empty_scopes,
            )
            if dynamic:
                selected = []
                for binding_value in values:
                    if isinstance(binding_value, _RoleBinding) and role_dynamic:
                        selected.append(
                            _role_selected(
                                model,
                                board,
                                binding_value.name,
                                source,
                                binding_name,
                                empty_scopes,
                                bindings,
                            )
                        )
                    elif isinstance(binding_value, _AreaBinding) and area_adjective is not None:
                        region = binding_value.region
                        empty = _area_empty_literal(
                            model,
                            board,
                            region,
                            f"{binding_name} {region} empty",
                            empty_scopes,
                        )
                        selected.append(
                            empty if area_adjective == "empty" else _opposite(model, empty)
                        )
                    elif (
                        isinstance(binding_value, _SpatialBinding)
                        and binding_value.sort == Sort.CELL
                        and cell_adjective is not None
                    ):
                        row, col = (int(index) for index in binding_value.key.split(","))
                        empty = _cell_empty_literal(
                            model,
                            board,
                            Square(row, col),
                            f"{binding_name} {binding_value.key} empty",
                            empty_scopes,
                        )
                        selected.append(
                            empty if cell_adjective == "empty" else _opposite(model, empty)
                        )
                    elif isinstance(binding_value, str):
                        selected.append(
                            _person_selected(
                                model,
                                board,
                                binding_value,
                                source,
                                f"{binding_name} {binding_value} member",
                                empty_scopes,
                                bindings,
                            )
                        )
                    elif spatial_domain and isinstance(
                        binding_value, (_AreaBinding, _LineBinding, _SpatialBinding)
                    ):
                        token = lang.Token("?_spatial_domain", 1, 1)
                        bound_operand = _bind_operand(lang.Name(token), {token.text: binding_value})
                        bound_entities = _static_spatial_entities(board, bound_operand)
                        assert bound_entities is not None and len(bound_entities) == 1
                        entity, footprint = next(iter(bound_entities.items()))
                        selected.append(
                            _spatial_selected(
                                model,
                                board,
                                entity,
                                footprint,
                                source,
                                binding_name,
                                empty_scopes,
                                bindings,
                            )
                        )
                    else:
                        raise ValueError(f"{name}: dynamic domain contains an unsupported entity")
                selected.append(_opposite(model, body) if quantifier == "every" else body)
                body = _reify_cardinality(model, selected, {len(selected)}, binding_name)
            literals.append(body)
        maximum = len(literals)
        target = int(formula.count.text) if formula.count is not None else 0
        allowed = {
            "some": set(range(1, maximum + 1)),
            "every": {0} if dynamic else {maximum},
            "no": {0},
            "exactly": {target} if target <= maximum else set(),
            "at least": set(range(target, maximum + 1)),
            "at most": set(range(min(target, maximum) + 1)),
        }[quantifier]
        return _reify_cardinality(model, literals, allowed, name)
    raise NotImplementedError(f"{name}: expression lowering is not implemented")


def compile_statements(
    board: Board, statements: Sequence[lang.Statement], *, rules: Sequence[lang.Statement] = ()
) -> Model:
    """Compile the currently supported expression patterns for a board."""
    if board.rules:
        raise ValueError("board rules must be migrated to expression statements first")
    for statement in (*rules, *statements):
        check_formula(board, statement.formula)
    model = compile_puzzle(board, [])
    empty_scopes: dict[Square | str, int] = {}
    labelled = [
        *((f"rule {index}", statement) for index, statement in enumerate(rules, 1)),
        *((f"clue {index}", statement) for index, statement in enumerate(statements, 1)),
    ]
    for label, statement in labelled:
        if not any(
            lower(model, board, statement, label)
            for lower in (
                try_lower_location,
                try_lower_membership,
                try_lower_role_atom,
                try_lower_person_pair,
                try_lower_role_target,
                try_lower_count,
            )
        ):
            literal = _reify_formula(
                model, board, statement.formula, label, empty_scopes=empty_scopes
            )
            model.assign(literal, "clue", label)
    return model
