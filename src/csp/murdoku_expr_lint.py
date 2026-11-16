"""Lint checks for expression-language Murdoku clues."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING

from . import murdoku_lang as lang
from .murdoku import Board
from .murdoku_lower import _static_cells, occupied_cell_pair_scopes
from .murdoku_typecheck import Sort, infer_operand

if TYPE_CHECKING:
    from .murdoku_lower import ExpressionCompilation


def _negated_relations(formula: lang.Formula, negated: bool = False) -> Iterator[lang.Atom]:
    if isinstance(formula, lang.Negation):
        yield from _negated_relations(formula.formula, not negated)
    elif isinstance(formula, lang.Atom):
        no = formula.determiner is not None and formula.determiner.text == "no"
        if negated != no and formula.operator.text != "is":
            yield formula
    elif isinstance(formula, lang.Binary):
        if formula.operator.text in {"and", "or"}:
            yield from _negated_relations(formula.left, negated)
            yield from _negated_relations(formula.right, negated)
        else:
            yield from _negated_relations(formula.left)
            yield from _negated_relations(formula.right)
    elif isinstance(formula, lang.Quantified):
        if formula.quantifier.text in {"every", "some"}:
            yield from _negated_relations(formula.body, negated)
        else:
            yield from _negated_relations(formula.body)
    elif isinstance(formula, lang.Choice):
        for choice in formula.choices:
            yield from _negated_relations(choice)


def role_negation_warnings(board: Board, statements: Sequence[lang.Statement]) -> list[str]:
    """Warn when a negative relation does not rule out the subject holding its target role."""
    warnings = []
    for statement in statements:
        for atom in _negated_relations(statement.formula):
            if not isinstance(atom.subject, lang.Name):
                continue
            person = atom.subject.token.text
            if person not in board.people:
                continue
            items = atom.target.items if isinstance(atom.target, lang.Union) else (atom.target,)
            first = items[0]
            namespace = (
                first.token.text.partition(":")[0]
                if isinstance(first, lang.Name) and ":" in first.token.text
                else ""
            )
            for item in items:
                if not isinstance(item, lang.Name):
                    continue
                text = item.token.text
                if ":" not in text and namespace == "role" and text not in board.people:
                    text = f"role:{text}"
                kind, separator, name = text.partition(":")
                if kind != "role" or not separator:
                    continue
                role = next((role for role in board.roles if role.name == name), None)
                if role is None or max(role.allowed_counts) == 0:
                    continue
                if role.eligible_people is not None and person not in role.eligible_people:
                    continue
                token = atom.operator
                warnings.append(
                    f"line {token.line}, column {token.column}: {person} may still be role:{name}; "
                    f"add `not {person} is role:{name}` if non-membership is intended"
                )
    return warnings


def _required_atoms(formula: lang.Formula) -> Iterator[lang.Atom]:
    if isinstance(formula, lang.Atom):
        yield formula
    elif isinstance(formula, lang.Binary) and formula.operator.text == "and":
        yield from _required_atoms(formula.left)
        yield from _required_atoms(formula.right)


def _required_adjectives(formula: lang.Formula) -> Iterator[lang.AdjectiveAtom]:
    if isinstance(formula, lang.AdjectiveAtom):
        yield formula
    elif isinstance(formula, lang.Binary) and formula.operator.text == "and":
        yield from _required_adjectives(formula.left)
        yield from _required_adjectives(formula.right)


def vacuous_errors(board: Board, statements: Sequence[lang.Statement]) -> list[str]:
    """Report required relations forbidden by the board rules."""
    errors = []
    for statement in statements:
        for adjective_atom in _required_adjectives(statement.formula):
            determiner = adjective_atom.determiner.text if adjective_atom.determiner else ""
            if adjective_atom.adjective.text != "occupied" or determiner == "no":
                continue
            subject_shape = infer_operand(board, adjective_atom.subject)
            if determiner == "every" and subject_shape.minimum == 0:
                continue
            cells = _static_cells(board, adjective_atom.subject)
            if cells is not None and not cells.intersection(board.free):
                token = adjective_atom.adjective
                errors.append(
                    f"line {token.line}, column {token.column}: "
                    "this target cannot be occupied; its footprint contains no free cells"
                )
        for atom in _required_atoms(statement.formula):
            scopes = occupied_cell_pair_scopes(board, atom)
            if scopes is not None:
                first, second, direction = scopes
                free = set(board.free)
                if not any(
                    left.row != right.row and left.col != right.col and direction(left, right)
                    for left in first & free
                    for right in second & free
                ):
                    token = atom.operator
                    errors.append(
                        f"line {token.line}, column {token.column}: no two people can satisfy "
                        f"{token.text} in these occupancy scopes"
                    )
                continue
            if atom.operator.text in {"in", "on"} and (
                atom.determiner is None or atom.determiner.text != "no"
            ):
                named_person = isinstance(atom.subject, lang.Name) and (
                    atom.subject.token.text in board.people
                )
                determiner = atom.determiner.text if atom.determiner else ""
                shape = (
                    infer_operand(board, atom.subject) if determiner in {"some", "every"} else None
                )
                impossible_set = (
                    shape is not None
                    and shape.sort == Sort.PERSON
                    and (determiner == "some" or shape.minimum > 0)
                )
                cells = (
                    _static_cells(board, atom.target) if named_person or impossible_set else None
                )
                if cells is not None and not cells.intersection(board.free):
                    token = atom.operator
                    subject = (
                        atom.subject.token.text
                        if isinstance(atom.subject, lang.Name) and named_person
                        else "a person"
                    )
                    errors.append(
                        f"line {token.line}, column {token.column}: {subject} cannot be "
                        f"{token.text} this target; "
                        "its footprint contains no free cells"
                    )
                    continue
            if (
                atom.operator.text.startswith("dir:")
                and (atom.determiner is None or atom.determiner.text != "no")
                and isinstance(atom.subject, lang.Name)
                and isinstance(atom.target, lang.Name)
                and atom.subject.token.text == atom.target.token.text
                and atom.subject.token.text in board.people
            ):
                token = atom.operator
                errors.append(
                    f"line {token.line}, column {token.column}: a person cannot be "
                    f"{token.text} themselves; directional relations require distinct entities"
                )
                continue
            if (
                atom.operator.text in {"dir:rows", "dir:cols"}
                and (atom.determiner is None or atom.determiner.text != "no")
                and isinstance(atom.subject, lang.Name)
                and isinstance(atom.target, lang.Name)
                and atom.subject.token.text in board.people
                and atom.target.token.text in board.people
                and atom.measure is not None
                and atom.measure.comparison.text in {"=", "<="}
                and int(atom.measure.value.text) == 0
            ):
                token = atom.operator
                errors.append(
                    f"line {token.line}, column {token.column}: people cannot share a row or column"
                )
                continue
            if (
                atom.operator.text not in {"beside", "touches"}
                or (atom.determiner is not None and atom.determiner.text == "no")
                or not isinstance(atom.subject, lang.Name)
                or not isinstance(atom.target, lang.Name)
                or atom.subject.token.text not in board.people
                or atom.target.token.text not in board.people
            ):
                continue
            token = atom.operator
            errors.append(
                f"line {token.line}, column {token.column}: people cannot "
                f"{token.text} each other; "
                "they occupy different rows and columns"
            )
    return errors


def _tokens(value: object) -> Iterator[lang.Token]:
    if isinstance(value, lang.Token):
        yield value
    elif isinstance(value, tuple):
        for item in value:
            yield from _tokens(item)
    elif is_dataclass(value):
        for item in fields(value):
            yield from _tokens(getattr(value, item.name))


def size_budget_warnings(
    board: Board, compilation: ExpressionCompilation, *, budget: int = 3
) -> list[str]:
    """Warn when an emitted relation exceeds the position/role variable budget."""
    if budget < 1:
        raise ValueError("relation size budget must be positive")
    variables = set(board.people) | {
        board.role_variable(person, role.name) for person in board.people for role in board.roles
    }
    sizes: dict[int, int] = {}
    for index, sources in compilation.relation_origins.items():
        relation = compilation.model.relations[index]
        size = len(set(relation.variables) & variables)
        if size > budget:
            for origin in sources:
                position = compilation.origins.index(origin)
                sizes[position] = max(size, sizes.get(position, 0))
    warnings = []
    for index, size in sorted(sizes.items()):
        origin = compilation.origins[index]
        token = min(_tokens(origin.statement.formula), key=lambda token: (token.line, token.column))
        warnings.append(
            f"line {token.line}, column {token.column}: {origin.label} grounds to "
            f"a relation over {size} position/role variables (budget {budget}); "
            "consider splitting the statement"
        )
    return warnings
