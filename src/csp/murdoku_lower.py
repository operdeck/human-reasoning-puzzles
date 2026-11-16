"""Incremental lowering of Murdoku expression statements to model constraints."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from . import murdoku_lang as lang
from .core import Kind, Model
from .murdoku import Board, Square, _direction_test, _hidden_boolean, compile_puzzle
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
        direction = _direction(board, op, atom.measure)
        if direction is None:
            return False

        def directed(left: Square, right: Square) -> bool:
            return not same and direction(left, right)

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


def compile_statements(board: Board, statements: Sequence[lang.Statement]) -> Model:
    """Compile the currently supported expression patterns for a board."""
    if board.rules:
        raise ValueError("board rules must be migrated to expression statements first")
    for statement in statements:
        check_formula(board, statement.formula)
    model = compile_puzzle(board, [])
    for index, statement in enumerate(statements, 1):
        label = f"clue {index}"
        if not any(
            lower(model, board, statement, label)
            for lower in (
                try_lower_location,
                try_lower_membership,
                try_lower_person_pair,
                try_lower_count,
            )
        ):
            raise NotImplementedError(f"{label}: expression lowering is not implemented")
    return model
