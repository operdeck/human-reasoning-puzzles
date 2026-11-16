"""Expand Murdoku board declarations into expression-language statements."""

from __future__ import annotations

from . import murdoku_lang as lang
from .murdoku import Board


def statements(board: Board) -> list[lang.Statement]:
    """Return the role and mark declarations as reference-language statements."""

    def token(text: str) -> lang.Token:
        return lang.Token(text, 1, 1)

    def name(text: str) -> lang.Name:
        return lang.Name(token(text))

    def count(operand: lang.Operand, operator: str, value: int) -> lang.NumberComparison:
        return lang.NumberComparison(
            lang.Count(operand), token(operator), lang.Integer(token(str(value)))
        )

    result: list[lang.Statement] = []
    for role in board.roles:
        holders = name(f"role:{role.name}")
        allowed = [count(holders, "=", value) for value in sorted(role.allowed_counts)]
        counts: lang.Formula = allowed[0]
        for allowed_count in allowed[1:]:
            counts = lang.Binary(counts, token("or"), allowed_count)
        result.append(lang.Statement(counts))
        if role.different_regions:
            people = (token("?p"), token("?q"))
            distinct_areas = lang.Atom(
                name("?p"),
                token("dir:areas"),
                name("?q"),
                measure=lang.Measure(token(">="), token("1")),
            )
            result.append(
                lang.Statement(
                    lang.Quantified(token("every"), None, people, holders, distinct_areas)
                )
            )
        if role.eligible_people is not None:
            eligible = sorted(role.eligible_people)
            if eligible:
                options = tuple(name(person) for person in eligible)
                target: lang.Operand = options[0] if len(options) == 1 else lang.Union(options)
                eligibility = lang.Atom(holders, token("is"), target, token("every"))
            else:
                eligibility = lang.Atom(holders, token("is"), name("people"), token("no"))
            result.append(lang.Statement(eligibility))

    for mark in board.marks:
        if mark.occupant_condition is None:
            continue
        if mark.occupant_condition == "not_alone" and len(board.people) == 1:
            result.append(
                lang.Statement(
                    lang.Atom(name("people"), token("on"), name(f"mark:{mark.name}"), token("no"))
                )
            )
            continue
        occupants = lang.Filter(name("people"), token("on"), name(f"mark:{mark.name}"))
        area = lang.Projection(token("area"), name("?p"))
        people_in_area = lang.Filter(name("people"), token("in"), area)
        operator, value = ("=", 1) if mark.occupant_condition == "alone" else (">=", 2)
        body = count(people_in_area, operator, value)
        result.append(
            lang.Statement(lang.Quantified(token("every"), None, (token("?p"),), occupants, body))
        )
    return result
