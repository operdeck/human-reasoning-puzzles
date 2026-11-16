"""Compositional wording for Murdoku expression statements."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from string import Formatter
from typing import assert_never

from . import murdoku_lang as lang
from .murdoku import Board
from .murdoku_typecheck import Shape, Sort, check_formula, infer_operand
from .puzzlefile import read_sections

PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "set.people": "people",
        "set.areas": "areas",
        "set.rows": "rows",
        "set.columns": "columns",
        "set.cells": "cells",
        "set.objects": "objects",
        "set.roles": "roles",
        "name.area": "area {name}",
        "name.tag": "areas tagged {name}",
        "name.object": "objects named {name}",
        "name.object_kind": "{name} objects",
        "name.edge_item": "edge items named {name}",
        "name.point_object": "point objects named {name}",
        "name.mark": "marks named {name}",
        "name.role": "people holding role {name}",
        "name.attribute": "people with attribute {name}",
        "name.rows": "rows {name}",
        "name.columns": "columns {name}",
        "name.corner": "board corners",
        "op.union": "{left}, {right}",
        "op.except": "{left} except {right}",
        "op.filter": "{source} that are {relation} {target}",
        "op.adjective_filter": "{source} that are {adjective}",
        "op.comprehension": "{variable} in {source} where {condition}",
        "op.projection": "{kind} overlapping {operand}",
        "projection.area": "areas",
        "projection.row": "rows",
        "projection.column": "columns",
        "projection.cell": "cells",
        "adj.empty": "empty",
        "adj.occupied": "occupied",
        "adj.free": "free",
        "rel.in": "in",
        "rel.on": "on",
        "rel.in.spatial": "entirely contained in",
        "rel.on.spatial": "overlapping",
        "rel.beside": "beside",
        "rel.touches": "touching",
        "rel.is.person": "a member of",
        "rel.is.same_person": "the same person as",
        "rel.is.spatial": "the same entity as",
        "rel.dir.up": "above",
        "rel.dir.down": "below",
        "rel.dir.left": "left of",
        "rel.dir.right": "right of",
        "rel.dir.diagonal": "diagonally aligned with",
        "rel.dir.up.exact": "above",
        "rel.dir.down.exact": "below",
        "rel.dir.left.exact": "left of",
        "rel.dir.right.exact": "right of",
        "rel.dir.diagonal.exact": "diagonally aligned with",
        "rel.dir.up_right": "above and right of",
        "rel.dir.up_left": "above and left of",
        "rel.dir.down_right": "below and right of",
        "rel.dir.down_left": "below and left of",
        "rel.dir.knight": "a knight's move from",
        "rel.dir.rows": "at a row distance from",
        "rel.dir.cols": "at a column distance from",
        "rel.dir.manhattan": "at a side-step distance from",
        "rel.dir.king": "at a king-step distance from",
        "rel.dir.euclidean": "at a straight-line distance from",
        "rel.dir.areas": "at an area distance from",
        "rel.dir.areas.same": "in the same area as",
        "rel.dir.nearest": "closer than every other person outside the target set to",
        "rel.dir.furthest": "farther than every other person outside the target set from",
        "rel.metric": "{relation} (measured by {metric})",
        "metric.rows": "row distance",
        "metric.cols": "column distance",
        "metric.manhattan": "side-step distance",
        "metric.king": "king-step distance",
        "metric.euclidean": "straight-line distance",
        "metric.areas": "area distance",
        "rel.measure": "{target} (distance {comparison} {value})",
        "rel.measure.axes": "{target} (each axis distance {comparison} {value})",
        "rel.any_target": "at least one of {target}",
        "rel.distinct_target": "{target} (distinct from the subject)",
        "target.object": "{name}",
        "target.object.named": "an object named {name}",
        "cmp.=": "equal to",
        "cmp.!=": "not equal to",
        "cmp.<": "less than",
        "cmp.<=": "at most",
        "cmp.>": "greater than",
        "cmp.>=": "at least",
        "atom.one": "{subject} is {relation} {target}",
        "adjective.one": "{subject} is {adjective}",
        "det.some": "at least one of {subject}",
        "det.every": "every member of {subject}",
        "det.no": "no member of {subject}",
        "set.equal": "{left} and {right} are the same set",
        "set.not_equal": "{left} and {right} are different sets",
        "number.count": "the number of {operand}",
        "number.add": "({left} plus {right})",
        "number.subtract": "({left} minus {right})",
        "number.compare": "{left} is {comparison} {right}",
        "number.parity": "{number} is {parity}",
        "number.range": "{number} is between {lower} and {upper}, inclusive",
        "parity.odd": "odd",
        "parity.even": "even",
        "bool.not": "it is not true that ({formula})",
        "bool.and": "({left}) and ({right})",
        "bool.or": "({left}) or ({right})",
        "bool.if": "if ({left}), then ({right})",
        "bool.iff": "({left}) if and only if ({right})",
        "quant.some": "for at least one {variables} from {source}: {body}",
        "quant.every": "for every {variables} from {source}: {body}",
        "quant.no": "for no {variables} from {source}: {body}",
        "quant.exactly": "for exactly {count} {variables} from {source}: {body}",
        "quant.at least": "for at least {count} {variables} from {source}: {body}",
        "quant.at most": "for at most {count} {variables} from {source}: {body}",
        "quant.distinct": "ordered tuples of distinct {variables}",
        "choice.exactly": "exactly {count} of ({choices}) hold",
        "choice.at least": "at least {count} of ({choices}) hold",
        "choice.at most": "at most {count} of ({choices}) hold",
        "idiom.alone": "{person} is alone in their area",
        "idiom.only_on": "{person} is the only person on {target}",
    },
    "nl": {
        "set.people": "personen",
        "set.areas": "gebieden",
        "set.rows": "rijen",
        "set.columns": "kolommen",
        "set.cells": "vakjes",
        "set.objects": "voorwerpen",
        "set.roles": "rollen",
        "name.area": "gebied {name}",
        "name.tag": "gebieden met tag {name}",
        "name.object": "voorwerpen met de naam {name}",
        "name.object_kind": "{name} voorwerpen",
        "name.edge_item": "randvoorwerpen met de naam {name}",
        "name.point_object": "puntvoorwerpen met de naam {name}",
        "name.mark": "markeringen met de naam {name}",
        "name.role": "personen met rol {name}",
        "name.attribute": "personen met eigenschap {name}",
        "name.rows": "rijen {name}",
        "name.columns": "kolommen {name}",
        "name.corner": "bordhoeken",
        "op.union": "{left}, {right}",
        "op.except": "{left} behalve {right}",
        "op.filter": "{source} die {relation} {target} zijn",
        "op.adjective_filter": "{source} die {adjective} zijn",
        "op.comprehension": "{variable} in {source} waarvoor {condition}",
        "op.projection": "{kind} die {operand} overlappen",
        "projection.area": "gebieden",
        "projection.row": "rijen",
        "projection.column": "kolommen",
        "projection.cell": "vakjes",
        "adj.empty": "leeg",
        "adj.occupied": "bezet",
        "adj.free": "vrij",
        "rel.in": "in",
        "rel.on": "op",
        "rel.in.spatial": "volledig binnen",
        "rel.on.spatial": "overlappend met",
        "rel.beside": "naast",
        "rel.touches": "rakend aan",
        "rel.is.person": "een lid van",
        "rel.is.same_person": "dezelfde persoon als",
        "rel.is.spatial": "hetzelfde als",
        "rel.dir.up": "boven",
        "rel.dir.down": "onder",
        "rel.dir.left": "links van",
        "rel.dir.right": "rechts van",
        "rel.dir.diagonal": "diagonaal uitgelijnd met",
        "rel.dir.up.exact": "boven",
        "rel.dir.down.exact": "onder",
        "rel.dir.left.exact": "links van",
        "rel.dir.right.exact": "rechts van",
        "rel.dir.diagonal.exact": "diagonaal uitgelijnd met",
        "rel.dir.up_right": "boven en rechts van",
        "rel.dir.up_left": "boven en links van",
        "rel.dir.down_right": "onder en rechts van",
        "rel.dir.down_left": "onder en links van",
        "rel.dir.knight": "een paardensprong verwijderd van",
        "rel.dir.rows": "op een rijafstand van",
        "rel.dir.cols": "op een kolomafstand van",
        "rel.dir.manhattan": "op een zijstapafstand van",
        "rel.dir.king": "op een koningsstapafstand van",
        "rel.dir.euclidean": "op een rechte afstand van",
        "rel.dir.areas": "op een gebiedsafstand van",
        "rel.dir.areas.same": "in hetzelfde gebied als",
        "rel.dir.nearest": "dichter dan iedere andere persoon buiten de doelverzameling bij",
        "rel.dir.furthest": "verder dan iedere andere persoon buiten de doelverzameling van",
        "rel.metric": "{relation} (gemeten met {metric})",
        "metric.rows": "rijafstand",
        "metric.cols": "kolomafstand",
        "metric.manhattan": "zijstapafstand",
        "metric.king": "koningsstapafstand",
        "metric.euclidean": "rechte afstand",
        "metric.areas": "gebiedsafstand",
        "rel.measure": "{target} (afstand {comparison} {value})",
        "rel.measure.axes": "{target} (afstand op elke as {comparison} {value})",
        "rel.any_target": "minstens een van {target}",
        "rel.distinct_target": "{target} (verschillend van het onderwerp)",
        "target.object": "{name}",
        "target.object.named": "een voorwerp met de naam {name}",
        "cmp.=": "gelijk aan",
        "cmp.!=": "niet gelijk aan",
        "cmp.<": "kleiner dan",
        "cmp.<=": "hoogstens",
        "cmp.>": "groter dan",
        "cmp.>=": "minstens",
        "atom.one": "{subject} is {relation} {target}",
        "adjective.one": "{subject} is {adjective}",
        "det.some": "minstens een van {subject}",
        "det.every": "ieder lid van {subject}",
        "det.no": "geen lid van {subject}",
        "set.equal": "{left} en {right} zijn dezelfde verzameling",
        "set.not_equal": "{left} en {right} zijn verschillende verzamelingen",
        "number.count": "het aantal {operand}",
        "number.add": "({left} plus {right})",
        "number.subtract": "({left} min {right})",
        "number.compare": "{left} is {comparison} {right}",
        "number.parity": "{number} is {parity}",
        "number.range": "{number} ligt tussen {lower} en {upper}, inclusief",
        "parity.odd": "oneven",
        "parity.even": "even",
        "bool.not": "het is niet waar dat ({formula})",
        "bool.and": "({left}) en ({right})",
        "bool.or": "({left}) of ({right})",
        "bool.if": "als ({left}), dan ({right})",
        "bool.iff": "({left}) dan en slechts dan als ({right})",
        "quant.some": "voor minstens een {variables} uit {source}: {body}",
        "quant.every": "voor iedere {variables} uit {source}: {body}",
        "quant.no": "voor geen {variables} uit {source}: {body}",
        "quant.exactly": "voor precies {count} {variables} uit {source}: {body}",
        "quant.at least": "voor minstens {count} {variables} uit {source}: {body}",
        "quant.at most": "voor hoogstens {count} {variables} uit {source}: {body}",
        "quant.distinct": "geordende combinaties van verschillende {variables}",
        "choice.exactly": "precies {count} van ({choices}) gelden",
        "choice.at least": "minstens {count} van ({choices}) gelden",
        "choice.at most": "hoogstens {count} van ({choices}) gelden",
        "idiom.alone": "{person} is alleen in het eigen gebied",
        "idiom.only_on": "{person} is de enige persoon op {target}",
    },
}

LEGACY_CLUE_PHRASES = {
    "clue.alone": "idiom.alone",
    "clue.only_on": "idiom.only_on",
    "clue.in": "rel.in",
    "clue.on": "rel.on",
    "clue.beside": "rel.beside",
    "clue.dir_exact": "rel.dir.<direction>.exact",
    "target.attribute": "name.attribute",
}
EXPRESSION_PHRASE_PREFIXES = tuple(
    f"{namespace}." for namespace in {key.partition(".")[0] for key in PHRASES["en"]}
)


@dataclass
class ExpressionWords:
    """Word typed expressions using one language and optional phrase overrides."""

    board: Board
    language: str = "en"
    names: Mapping[str, str] = field(default_factory=dict)
    phrases: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.language not in PHRASES:
            raise ValueError(f"unknown expression language {self.language!r}")
        unknown = set(self.phrases) - set(PHRASES[self.language])
        if unknown:
            raise ValueError(f"unknown expression phrase keys: {', '.join(sorted(unknown))}")
        formatter = Formatter()
        for key, template in self.phrases.items():
            allowed = {
                name for _, name, _, _ in formatter.parse(PHRASES[self.language][key]) if name
            }
            supplied = set()
            for _, name, specification, _ in formatter.parse(template):
                if name is None:
                    continue
                if not name or "{" in (specification or "") or "}" in (specification or ""):
                    raise ValueError(f"Words: phrase {key!r} has an unsupported placeholder")
                supplied.add(name)
            invalid = supplied - allowed
            if invalid:
                raise ValueError(
                    f"Words: phrase {key!r} has unknown placeholders: {', '.join(sorted(invalid))}"
                )

    @classmethod
    def read(cls, board: Board, text: str) -> "ExpressionWords":
        """Read language, display names and expression phrase overrides from a puzzle."""
        sections = read_sections(text)
        language = (sections.get("Language") or ["en"])[0]
        if language not in PHRASES:
            raise ValueError(f"unknown expression language {language!r}")
        names: dict[str, str] = {}
        phrases: dict[str, str] = {}
        for line in sections.get("Words", []):
            name, separator, phrase = line.partition(":")
            if not separator or not name.strip() or not phrase.strip():
                raise ValueError(f"Words: {line!r} is not like 'name: wording'")
            key = name.strip()
            if key in LEGACY_CLUE_PHRASES or key.startswith("clue."):
                replacement = LEGACY_CLUE_PHRASES.get(key, "an expression phrase key or | wording")
                raise ValueError(f"Words: key {key!r} is legacy; use {replacement}")
            if key.startswith(EXPRESSION_PHRASE_PREFIXES) and key not in PHRASES[language]:
                raise ValueError(f"Words: unknown expression phrase key {key!r}")
            (phrases if key in PHRASES[language] else names)[key] = phrase.strip()
        return cls(board, language, names, phrases)

    def _phrase(self, key: str, **values: str) -> str:
        return self.phrases.get(key, PHRASES[self.language][key]).format(**values)

    def _name(self, token: lang.Token, namespace: str | None = None) -> str:
        text = token.text
        if text in self.board.people or text.startswith("?"):
            return self.names.get(text, text)
        if text in {"people", "areas", "rows", "columns", "cells", "objects", "roles"}:
            return self._phrase(f"set.{text}")
        if ":" not in text and namespace:
            text = f"{namespace}:{text}"
        kind, _, name = text.partition(":")
        return self._phrase(f"name.{kind}", name=self.names.get(name, name))

    def _relation(
        self,
        operator: lang.Token,
        subject: lang.Operand,
        target: lang.Operand,
        bindings: dict[str, Shape],
        measure: lang.Measure | None,
    ) -> str:
        mode = operator.text
        if mode == "is":
            sort = infer_operand(self.board, subject, bindings).sort
            if sort != Sort.PERSON:
                key = "rel.is.spatial"
            elif isinstance(target, lang.Name) and (
                target.token.text in self.board.people
                or (
                    target.token.text.startswith("?")
                    and infer_operand(self.board, target, bindings).sort == Sort.PERSON
                )
            ):
                key = "rel.is.same_person"
            else:
                key = "rel.is.person"
            relation = self._phrase(key)
        elif (
            mode in {"in", "on"}
            and infer_operand(self.board, subject, bindings).sort != Sort.PERSON
        ):
            relation = self._phrase(f"rel.{mode}.spatial")
        elif mode.startswith("dir:"):
            mode = mode.removeprefix("dir:")
            direction, _, metric = mode.partition(":")
            parts = direction.split("+")
            if len(parts) == 2:
                vertical = next(part for part in parts if part in {"up", "down"})
                horizontal = next(part for part in parts if part in {"left", "right"})
                key = f"rel.dir.{vertical}_{horizontal}"
            else:
                key = f"rel.dir.{direction}"
                if direction == "areas" and self._same_area(measure):
                    key += ".same"
                elif measure and measure.comparison.text == "=" and f"{key}.exact" in PHRASES["en"]:
                    key += ".exact"
            relation = self._phrase(key)
            if metric:
                relation = self._phrase(
                    "rel.metric", relation=relation, metric=self._phrase(f"metric.{metric}")
                )
        else:
            relation = self._phrase(f"rel.{mode}")
        return relation

    def _target(
        self,
        target: lang.Operand,
        measure: lang.Measure | None,
        bindings: dict[str, Shape],
        operator: lang.Token | None = None,
    ) -> str:
        if isinstance(target, lang.Name) and target.token.text.startswith("object:"):
            name = target.token.text.partition(":")[2]
            key = "target.object" if name in self.names else "target.object.named"
            rendered = self._phrase(key, name=self.names.get(name, name))
        else:
            rendered = self._operand(target, bindings)
            if infer_operand(self.board, target, bindings).maximum > 1:
                rendered = self._phrase("rel.any_target", target=rendered)
        if operator and operator.text == "dir:areas":
            rendered = self._phrase("rel.distinct_target", target=rendered)
        if measure and not (operator and operator.text == "dir:areas" and self._same_area(measure)):
            rendered = self._phrase(
                "rel.measure.axes"
                if operator and ("+" in operator.text or operator.text == "dir:diagonal")
                else "rel.measure",
                target=rendered,
                comparison=self._phrase(f"cmp.{measure.comparison.text}"),
                value=measure.value.text,
            )
        return rendered

    @staticmethod
    def _same_area(measure: lang.Measure | None) -> bool:
        return bool(measure and measure.comparison.text == "=" and int(measure.value.text) == 0)

    def _operand(
        self, value: lang.Operand, bindings: dict[str, Shape], namespace: str | None = None
    ) -> str:
        match value:
            case lang.Name(token=token):
                return self._name(token, namespace)
            case lang.Union(items=items):
                first = items[0]
                inherited = (
                    first.token.text.partition(":")[0]
                    if isinstance(first, lang.Name) and ":" in first.token.text
                    else None
                )
                result = self._operand(first, bindings)
                for item in items[1:]:
                    result = self._phrase(
                        "op.union", left=result, right=self._operand(item, bindings, inherited)
                    )
                return result
            case lang.Difference(left=left, right=right):
                return self._phrase(
                    "op.except",
                    left=self._operand(left, bindings),
                    right=self._operand(right, bindings),
                )
            case lang.Qualified(adjective=adjective, operand=operand):
                return f"{self._phrase(f'adj.{adjective.text}')} {self._operand(operand, bindings)}"
            case lang.Projection(kind=kind, operand=operand):
                return self._phrase(
                    "op.projection",
                    kind=self._phrase(f"projection.{kind.text}"),
                    operand=self._operand(operand, bindings),
                )
            case lang.Filter(source=source, operator=op, target=target, measure=measure):
                return self._phrase(
                    "op.filter",
                    source=self._operand(source, bindings),
                    relation=self._relation(op, source, target, bindings, measure),
                    target=self._target(target, measure, bindings, op),
                )
            case lang.AdjectiveFilter(source=source, adjective=adjective):
                return self._phrase(
                    "op.adjective_filter",
                    source=self._operand(source, bindings),
                    adjective=self._phrase(f"adj.{adjective.text}"),
                )
            case lang.Comprehension(variable=variable, source=source, condition=condition):
                shape = infer_operand(self.board, source, bindings)
                scoped = {**bindings, variable.text: Shape(shape.sort, 1, 1)}
                return self._phrase(
                    "op.comprehension",
                    variable=variable.text,
                    source=self._operand(source, bindings),
                    condition=self._formula(condition, scoped),
                )
            case _:
                assert_never(value)

    def _number(self, value: lang.Number, bindings: dict[str, Shape]) -> str:
        match value:
            case lang.Integer(value=token):
                return token.text
            case lang.Count(operand=operand):
                return self._phrase("number.count", operand=self._operand(operand, bindings))
            case lang.Arithmetic(left=left, operator=operator, right=right):
                return self._phrase(
                    "number.add" if operator.text == "+" else "number.subtract",
                    left=self._number(left, bindings),
                    right=self._number(right, bindings),
                )
            case _:
                assert_never(value)

    def _determined(
        self, subject: lang.Operand, determiner: lang.Token | None, bindings: dict[str, Shape]
    ) -> str:
        rendered = self._operand(subject, bindings)
        return self._phrase(f"det.{determiner.text}", subject=rendered) if determiner else rendered

    def _formula(self, value: lang.Formula, bindings: dict[str, Shape]) -> str:
        match value:
            case lang.Atom(subject=subject, operator=op, target=target, determiner=det):
                return self._phrase(
                    "atom.one",
                    subject=self._determined(subject, det, bindings),
                    relation=self._relation(op, subject, target, bindings, value.measure),
                    target=self._target(target, value.measure, bindings, op),
                )
            case lang.AdjectiveAtom(subject=subject, adjective=adjective, determiner=det):
                return self._phrase(
                    "adjective.one",
                    subject=self._determined(subject, det, bindings),
                    adjective=self._phrase(f"adj.{adjective.text}"),
                )
            case lang.SetComparison(left=left, operator=op, right=right):
                return self._phrase(
                    "set.equal" if op.text == "=" else "set.not_equal",
                    left=self._operand(left, bindings),
                    right=self._operand(right, bindings),
                )
            case lang.Negation(formula=formula):
                return self._phrase("bool.not", formula=self._formula(formula, bindings))
            case lang.Binary(left=left, operator=operator, right=right):
                return self._phrase(
                    f"bool.{operator.text}",
                    left=self._formula(left, bindings),
                    right=self._formula(right, bindings),
                )
            case lang.NumberComparison(left=left, operator=op, right=right):
                return self._phrase(
                    "number.compare",
                    left=self._number(left, bindings),
                    comparison=self._phrase(f"cmp.{op.text}"),
                    right=self._number(right, bindings),
                )
            case lang.Parity(number=number, parity=parity):
                return self._phrase(
                    "number.parity",
                    number=self._number(number, bindings),
                    parity=self._phrase(f"parity.{parity.text}"),
                )
            case lang.NumberRange(number=number, lower=lower, upper=upper):
                return self._phrase(
                    "number.range",
                    number=self._number(number, bindings),
                    lower=lower.text,
                    upper=upper.text,
                )
            case lang.Quantified(
                quantifier=quantifier, count=count, variables=variables, source=source, body=body
            ):
                shape = infer_operand(self.board, source, bindings)
                scoped = {**bindings, **{v.text: Shape(shape.sort, 1, 1) for v in variables}}
                names = ", ".join(variable.text for variable in variables)
                if len(variables) > 1:
                    names = self._phrase("quant.distinct", variables=names)
                return self._phrase(
                    f"quant.{' '.join(quantifier.text.split())}",
                    variables=names,
                    count=count.text if count else "",
                    source=self._operand(source, bindings),
                    body=self._formula(body, scoped),
                )
            case lang.Choice(quantifier=quantifier, count=count, choices=choices):
                return self._phrase(
                    f"choice.{' '.join(quantifier.text.split())}",
                    count=count.text,
                    choices="; ".join(self._formula(choice, bindings) for choice in choices),
                )
            case _:
                assert_never(value)

    def statement(self, statement: lang.Statement) -> str:
        """Return the author override or a composition of typed phrase keys."""
        check_formula(self.board, statement.formula)
        if statement.wording is not None:
            return statement.wording
        formula = statement.formula
        if isinstance(formula, lang.NumberComparison) and formula.operator.text == "=":
            for counted, number in ((formula.left, formula.right), (formula.right, formula.left)):
                if (
                    isinstance(number, lang.Integer)
                    and number.value.text == "1"
                    and isinstance(counted, lang.Count)
                    and isinstance(counted.operand, lang.Filter)
                    and isinstance(counted.operand.source, lang.Name)
                    and counted.operand.source.token.text == "people"
                    and counted.operand.operator.text == "in"
                    and isinstance(counted.operand.target, lang.Projection)
                    and counted.operand.target.kind.text == "area"
                    and isinstance(counted.operand.target.operand, lang.Name)
                    and counted.operand.target.operand.token.text in self.board.people
                ):
                    return self._phrase(
                        "idiom.alone",
                        person=self._name(counted.operand.target.operand.token),
                    )
        if isinstance(formula, lang.SetComparison) and formula.operator.text == "=":
            for occupants, person in ((formula.left, formula.right), (formula.right, formula.left)):
                if (
                    isinstance(occupants, lang.Filter)
                    and isinstance(occupants.source, lang.Name)
                    and occupants.source.token.text == "people"
                    and occupants.operator.text == "on"
                    and isinstance(person, lang.Name)
                    and person.token.text in self.board.people
                ):
                    return self._phrase(
                        "idiom.only_on",
                        person=self._name(person.token),
                        target=self._target(occupants.target, None, {}),
                    )
        return self._formula(statement.formula, {})
