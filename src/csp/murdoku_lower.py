"""Incremental lowering of Murdoku expression statements to model constraints."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from itertools import permutations

from . import murdoku_lang as lang
from .core import Kind, Model
from .murdoku import Board, Square, _direction_test, _hidden_boolean, compile_puzzle
from .murdoku_typecheck import Sort, check_formula, infer_operand


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


def _bind_operand(operand: lang.Operand, bindings: dict[str, str]) -> lang.Operand:
    if isinstance(operand, lang.Name):
        value = bindings.get(operand.token.text)
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
    raise NotImplementedError("comprehension binding is not implemented")


def _reify_cardinality(model: Model, literals: list[int], allowed: set[int], name: str) -> int:
    _, yes, no = _hidden_boolean(model, "expression", name, "Murdoku expression")
    if not allowed:
        model.assign(no, "clue", name, sources=(f"{name} state",))
    else:
        model.constrain(
            name,
            Kind.COUNT,
            literals,
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
    cell_empties: dict[Square, int],
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
                and item.token.text not in board.people
                and item.token.text != "people"
            ):
                item = replace(
                    item, token=replace(item.token, text=f"{namespace}:{item.token.text}")
                )
            members.append(
                _person_selected(model, board, person, item, f"{name} item {index}", cell_empties)
            )
        return _reify_cardinality(model, members, set(range(1, len(members) + 1)), name)
    if isinstance(operand, lang.Difference):
        left = _person_selected(model, board, person, operand.left, f"{name} left", cell_empties)
        right = _person_selected(model, board, person, operand.right, f"{name} right", cell_empties)
        return _reify_cardinality(model, [left, _opposite(model, right)], {2}, name)
    if isinstance(operand, lang.Filter):
        selected = _person_selected(
            model, board, person, operand.source, f"{name} source", cell_empties
        )
        atom = lang.Atom(
            lang.Name(replace(operand.operator, text=person)),
            operand.operator,
            operand.target,
            measure=operand.measure,
        )
        matches = _reify_formula(model, board, atom, f"{name} matches", cell_empties=cell_empties)
        return _reify_cardinality(model, [selected, matches], {2}, name)
    raise NotImplementedError(f"{name}: person set lowering is not implemented")


def _cell_empty_literal(
    model: Model, board: Board, square: Square, name: str, cell_empties: dict[Square, int]
) -> int:
    if square not in cell_empties:
        occupants = (
            [model.literal(person, square) for person in board.people]
            if square in board.free
            else []
        )
        cell_empties[square] = _reify_cardinality(model, occupants, {0}, name)
    return cell_empties[square]


def _reify_adjective_atom(
    model: Model,
    board: Board,
    atom: lang.AdjectiveAtom,
    name: str,
    cell_empties: dict[Square, int],
) -> int:
    shape = infer_operand(board, atom.subject)
    cells = _static_cells(board, atom.subject)
    if shape.minimum != 1 or shape.maximum != 1 or cells is None:
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
    elif shape.sort == Sort.CELL and len(cells) == 1:
        empty = _cell_empty_literal(model, board, next(iter(cells)), name, cell_empties)
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


def _reify_formula(
    model: Model,
    board: Board,
    formula: lang.Formula,
    name: str,
    bindings: dict[str, str] | None = None,
    cell_empties: dict[Square, int] | None = None,
) -> int:
    bindings = {} if bindings is None else bindings
    cell_empties = {} if cell_empties is None else cell_empties
    if isinstance(formula, lang.Atom):
        atom = replace(
            formula,
            subject=_bind_operand(formula.subject, bindings),
            target=_bind_operand(formula.target, bindings),
        )
        variable_name = "?_expression"
        while variable_name in bindings:
            variable_name += "_"
        variable = replace(atom.operator, text=variable_name)
        subject_person = (
            atom.subject.token.text
            if isinstance(atom.subject, lang.Name) and atom.subject.token.text in board.people
            else None
        )
        if subject_person is None and infer_operand(board, atom.subject).sort == Sort.PERSON:
            quantified = lang.Quantified(
                atom.determiner or replace(atom.operator, text="some"),
                None,
                (variable,),
                atom.subject,
                replace(atom, subject=lang.Name(variable), determiner=None),
            )
            return _reify_formula(model, board, quantified, name, bindings, cell_empties)
        if (
            subject_person is not None
            and atom.operator.text == "is"
            and infer_operand(board, atom.target).sort == Sort.PERSON
        ):
            result = _person_selected(model, board, subject_person, atom.target, name, cell_empties)
            return (
                _opposite(model, result)
                if atom.determiner is not None and atom.determiner.text == "no"
                else result
            )
        if (
            subject_person is not None
            and atom.operator.text != "is"
            and infer_operand(board, atom.target).sort == Sort.PERSON
            and not (isinstance(atom.target, lang.Name) and atom.target.token.text in board.people)
        ):
            quantified = lang.Quantified(
                replace(atom.operator, text="some"),
                None,
                (variable,),
                atom.target,
                replace(atom, target=lang.Name(variable), determiner=None),
            )
            result = _reify_formula(model, board, quantified, name, bindings, cell_empties)
            return (
                _opposite(model, result)
                if atom.determiner is not None and atom.determiner.text == "no"
                else result
            )
        return _reify_atom(model, board, atom, name)
    if isinstance(formula, lang.AdjectiveAtom):
        adjective_atom = replace(formula, subject=_bind_operand(formula.subject, bindings))
        return _reify_adjective_atom(model, board, adjective_atom, name, cell_empties)
    if isinstance(formula, lang.Negation):
        return _opposite(
            model,
            _reify_formula(model, board, formula.formula, f"{name} not", bindings, cell_empties),
        )
    if isinstance(formula, lang.SetComparison):
        left_set = _bind_operand(formula.left, bindings)
        right_set = _bind_operand(formula.right, bindings)
        if infer_operand(board, left_set).sort != Sort.PERSON:
            raise NotImplementedError(f"{name}: set comparison lowering is not implemented")
        equalities = []
        for person in board.people:
            left_member = _person_selected(
                model, board, person, left_set, f"{name} {person} left", cell_empties
            )
            right_member = _person_selected(
                model, board, person, right_set, f"{name} {person} right", cell_empties
            )
            equalities.append(
                _reify_cardinality(
                    model, [left_member, right_member], {0, 2}, f"{name} {person} equal"
                )
            )
        result = _reify_cardinality(model, equalities, {len(equalities)}, name)
        return _opposite(model, result) if formula.operator.text == "!=" else result
    count = _count_predicate(formula)
    if count is not None:
        operand, predicate, _ = count
        operand = _bind_operand(operand, bindings)
        cell_scope = _cell_occupancy_scope(board, operand)
        if cell_scope is not None:
            adjective, cell_squares = cell_scope
            literals = []
            for square in cell_squares:
                empty = _cell_empty_literal(
                    model, board, square, f"{name} {square} empty", cell_empties
                )
                literals.append(empty if adjective == "empty" else _opposite(model, empty))
            permitted = {value for value in range(len(cell_squares) + 1) if predicate(value)}
            return _reify_cardinality(model, literals, permitted, name)
        role_scope = _role_scope(board, operand)
        keys = _counted_keys(board, operand) if role_scope is None else None
        dynamic = keys is None and role_scope is None
        if dynamic and infer_operand(board, operand).sort != Sort.PERSON:
            raise NotImplementedError(f"{name}: count lowering is not implemented")
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
                    model, board, person, operand, f"{name} {person} member", cell_empties
                )
                for person in board.people
            ]
        else:
            assert keys is not None
            literals = [model.literal(variable, value) for variable, value in keys]
        return _reify_cardinality(model, literals, permitted, name)
    if isinstance(formula, lang.Binary):
        left = _reify_formula(model, board, formula.left, f"{name} left", bindings, cell_empties)
        right = _reify_formula(model, board, formula.right, f"{name} right", bindings, cell_empties)
        operator = formula.operator.text
        if operator == "if":
            left = _opposite(model, left)
            operator = "or"
        allowed = {"and": {2}, "or": {1, 2}, "iff": {0, 2}}[operator]
        return _reify_cardinality(model, [left, right], allowed, name)
    if isinstance(formula, lang.Choice):
        literals = [
            _reify_formula(model, board, choice, f"{name} option {index}", bindings, cell_empties)
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
        source = _bind_operand(formula.source, bindings)
        people = _static_people(board, source)
        dynamic = people is None
        if people is None:
            if infer_operand(board, source).sort != Sort.PERSON:
                raise NotImplementedError(f"{name}: quantifier source lowering is not implemented")
            people = set(board.people)
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
                cell_empties,
            )
            if dynamic:
                selected = [
                    _person_selected(
                        model,
                        board,
                        person,
                        source,
                        f"{binding_name} {person} member",
                        cell_empties,
                    )
                    for person in values
                ]
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


def compile_statements(board: Board, statements: Sequence[lang.Statement]) -> Model:
    """Compile the currently supported expression patterns for a board."""
    if board.rules:
        raise ValueError("board rules must be migrated to expression statements first")
    for statement in statements:
        check_formula(board, statement.formula)
    model = compile_puzzle(board, [])
    cell_empties: dict[Square, int] = {}
    for index, statement in enumerate(statements, 1):
        label = f"clue {index}"
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
                model, board, statement.formula, label, cell_empties=cell_empties
            )
            model.assign(literal, "clue", label)
    return model
