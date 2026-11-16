"""Lint checks for expression-language Murdoku clues."""

from collections.abc import Iterator, Sequence

from . import murdoku_lang as lang
from .murdoku import Board


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


def vacuous_errors(board: Board, statements: Sequence[lang.Statement]) -> list[str]:
    """Report required named-person relations forbidden by the board rules."""
    errors = []
    for statement in statements:
        for atom in _required_atoms(statement.formula):
            if (
                atom.operator.text != "beside"
                or (atom.determiner is not None and atom.determiner.text == "no")
                or not isinstance(atom.subject, lang.Name)
                or not isinstance(atom.target, lang.Name)
                or atom.subject.token.text not in board.people
                or atom.target.token.text not in board.people
            ):
                continue
            token = atom.operator
            errors.append(
                f"line {token.line}, column {token.column}: people cannot be beside each other; "
                "they occupy different rows and columns"
            )
    return errors
