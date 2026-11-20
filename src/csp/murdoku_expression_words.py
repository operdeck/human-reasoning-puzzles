"""Compositional wording for Murdoku expression statements."""

import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field, replace
from string import Formatter
from typing import assert_never

from . import murdoku_lang as lang
from .murdoku import Board, BoardObject, CellMark, EdgeItem, PointObject
from .murdoku_typecheck import Shape, Sort, check_formula, infer_operand
from .puzzlefile import read_sections

NUMBERS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
           "ten", "eleven", "twelve"],
    "nl": ["nul", "één", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen",
           "tien", "elf", "twaalf"],
}  # fmt: skip

PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "set.people": "people",
        "set.areas": "areas",
        "set.rows": "rows",
        "set.columns": "columns",
        "set.cells": "cells",
        "set.objects": "objects",
        "set.roles": "roles",
        "idiom.every_area_someone": "Each of the {areas} contains someone from {people}",
        "idiom.every_area_person": "{people} is in each of the {areas}",
        "name.area": "area {name}",
        "name.tag": "areas tagged {name}",
        "name.object": "objects named {name}",
        "name.object.display": "objects referred to as {name}",
        "name.object_kind": "{name} objects",
        "name.edge_item": "edge items named {name}",
        "name.point_object": "point objects named {name}",
        "name.mark": "marks named {name}",
        "name.role": "people holding role {name}",
        "name.role.one": "the {name}",
        "name.attribute": "people with attribute {name}",
        "name.rows": "rows {name}",
        "name.columns": "columns {name}",
        "name.row": "row {name}",
        "name.column": "column {name}",
        "name.corner": "board corners",
        "op.union": "{left}, {right}",
        "op.except": "{left} except {right}",
        "op.filter": "{source} that are {relation} {target}",
        "op.adjective_filter": "{source} that are {adjective}",
        "op.comprehension": "{source} where {condition}",
        "variable.person": "that person",
        "variable.area": "that area",
        "variable.row": "that row",
        "variable.column": "that column",
        "variable.cell": "that square",
        "variable.feature": "that feature",
        "variable.role": "that role",
        "op.projection": "{kind} overlapping {operand}",
        "projection.area": "areas",
        "projection.area.person": "the area of {operand}",
        "projection.row": "rows",
        "projection.column": "columns",
        "projection.cell": "cells",
        "adj.empty": "empty",
        "adj.occupied": "occupied",
        "adj.free": "free",
        "adj.empty.modifier": "empty",
        "adj.occupied.modifier": "occupied",
        "adj.free.modifier": "free",
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
        "rel.dir.king.near": "on or directly next to",
        "idiom.king.near": "{clause} (including diagonals and across area boundaries)",
        "idiom.king.not_near": "{clause} (not even diagonally, including across area boundaries)",
        "target.object.cell": "a square of {name}",
        "target.corner": "a board corner",
        "target.person.on": "someone on {target}",
        "target.or": "{left} or {right}",
        "rel.dir.euclidean": "at a straight-line distance from",
        "rel.dir.areas": "at an area distance from",
        "rel.dir.areas.same": "in the same area as",
        "rel.dir.nearest": "closer than every other person outside the target set to",
        "rel.dir.furthest": "farther than every other person outside the target set from",
        "rel.dir.furthest.person": "uniquely farthest from",
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
        "rel.any_scope": "any of the {target}",
        "rel.distinct_target": "{target} (distinct from the subject)",
        "target.object": "{name}",
        "target.object.named": "an object named {name}",
        "target.edge_item": "a cell touching {name}",
        "target.point_object": "a cell touching {name}",
        "target.mark": "a cell marked {name}",
        "count.mark": "the squares marked {name}",
        "noun.the": "the {name}",
        "noun.a": "a {name}",
        "noun.an": "an {name}",
        "cmp.=": "equal to",
        "cmp.!=": "not equal to",
        "cmp.<": "less than",
        "cmp.<=": "at most",
        "cmp.>": "greater than",
        "cmp.>=": "at least",
        "atom.one": "{subject} is {relation} {target}",
        "atom.not": "{subject} is not {relation} {target}",
        "atom.one.standing": "{subject} is {relation} {target}",
        "atom.not.standing": "{subject} is not {relation} {target}",
        "atom.one.sitting": "{subject} is {relation} {target}",
        "atom.not.sitting": "{subject} is not {relation} {target}",
        "adjective.one": "{subject} is {adjective}",
        "det.some": "at least one of {subject}",
        "det.every": "every member of {subject}",
        "det.no": "no member of {subject}",
        "det.no_except": "nobody except {subject}",
        "set.equal": "{left} and {right} are the same set",
        "set.not_equal": "{left} and {right} are different sets",
        "number.count": "the number of {operand}",
        "number.add": "({left} plus {right})",
        "number.subtract": "({left} minus {right})",
        "number.compare": "{left} is {comparison} {right}",
        "count.exactly": "exactly",
        "count.at_least": "at least",
        "count.at_most": "at most",
        "count.people.one": "{quantifier} {count} person is {relation} {target}",
        "count.people.many": "{quantifier} {count} people are {relation} {target}",
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
        "choice.either": "either {left}, or {right}, but not both",
        "idiom.same_area": "{first} and {second} are in the same area",
        "idiom.location.or": "{left} or {right}",
        "idiom.direction": "exactly {count} {unit} {direction}",
        "idiom.distance": "{first} and {second} are {comparison} {count} {unit} apart",
        "unit.areas.one": "area boundary",
        "unit.areas.many": "area boundaries",
        "unit.manhattan.one": "step",
        "unit.manhattan.many": "steps",
        "unit.row.one": "row",
        "unit.row.many": "rows",
        "unit.column.one": "column",
        "unit.column.many": "columns",
        "choice.at least": "at least {count} of ({choices}) hold",
        "choice.at most": "at most {count} of ({choices}) hold",
        "idiom.alone": "{person} is alone in their area",
        "idiom.only_on": "{person} is the only person on {target}",
        "idiom.most_populated": "{area} has more people than every other area",
        "idiom.least_populated": "{area} has fewer people than every other area",
        "idiom.most_populated.free": (
            "{area} has more people than every other area containing a free cell"
        ),
        "idiom.least_populated.free": (
            "{area} has fewer people than every other area containing a free cell"
        ),
    },
    "nl": {
        "idiom.every_area_someone": "In elk van de {areas} is minstens één van de {people}",
        "idiom.every_area_person": "{people} is in elk van de {areas}",
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
        "name.object.display": "voorwerpen aangeduid als {name}",
        "name.object_kind": "{name} voorwerpen",
        "name.edge_item": "randvoorwerpen met de naam {name}",
        "name.point_object": "puntvoorwerpen met de naam {name}",
        "name.mark": "markeringen met de naam {name}",
        "name.role": "personen met rol {name}",
        "name.role.one": "de {name}",
        "name.attribute": "personen met eigenschap {name}",
        "name.rows": "rijen {name}",
        "name.columns": "kolommen {name}",
        "name.row": "rij {name}",
        "name.column": "kolom {name}",
        "name.corner": "bordhoeken",
        "op.union": "{left}, {right}",
        "op.except": "{left} behalve {right}",
        "op.filter": "{source} die {relation} {target} zijn",
        "op.adjective_filter": "{source} die {adjective} zijn",
        "op.comprehension": "{source} waarvoor geldt: {condition}",
        "variable.person": "die persoon",
        "variable.area": "dat gebied",
        "variable.row": "die rij",
        "variable.column": "die kolom",
        "variable.cell": "dat vakje",
        "variable.feature": "dat voorwerp",
        "variable.role": "die rol",
        "op.projection": "{kind} die {operand} overlappen",
        "projection.area": "gebieden",
        "projection.area.person": "het gebied van {operand}",
        "projection.row": "rijen",
        "projection.column": "kolommen",
        "projection.cell": "vakjes",
        "adj.empty": "leeg",
        "adj.occupied": "bezet",
        "adj.free": "vrij",
        "adj.empty.modifier": "lege",
        "adj.occupied.modifier": "bezette",
        "adj.free.modifier": "vrije",
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
        "rel.dir.king.near": "op of direct naast",
        "idiom.king.near": "{clause} (ook schuin, en dit geldt zelfs over gebiedsgrenzen heen)",
        "idiom.king.not_near": (
            "{clause} (ook niet schuin, en dit geldt zelfs over gebiedsgrenzen heen)"
        ),
        "target.object.cell": "een vakje van {name}",
        "target.corner": "een rasterhoek",
        "target.person.on": "iemand op {target}",
        "target.or": "{left} of {right}",
        "rel.dir.euclidean": "op een rechte afstand van",
        "rel.dir.areas": "op een gebiedsafstand van",
        "rel.dir.areas.same": "in hetzelfde gebied als",
        "rel.dir.nearest": "dichter dan iedere andere persoon buiten de doelverzameling bij",
        "rel.dir.furthest": "verder dan iedere andere persoon buiten de doelverzameling van",
        "rel.dir.furthest.person": "als enige van alle figuren het verst van",
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
        "rel.any_scope": "een van de {target}",
        "rel.distinct_target": "{target} (verschillend van het onderwerp)",
        "target.object": "{name}",
        "target.object.named": "een voorwerp met de naam {name}",
        "target.edge_item": "een vakje dat {name} raakt",
        "target.point_object": "een vakje dat {name} raakt",
        "target.mark": "een vakje met de markering {name}",
        "count.mark": "de vakjes met markering {name}",
        "noun.the": "de {name}",
        "noun.a": "een {name}",
        "noun.an": "een {name}",
        "cmp.=": "gelijk aan",
        "cmp.!=": "niet gelijk aan",
        "cmp.<": "kleiner dan",
        "cmp.<=": "hoogstens",
        "cmp.>": "groter dan",
        "cmp.>=": "minstens",
        "atom.one": "{subject} is {relation} {target}",
        "atom.not": "{subject} is niet {relation} {target}",
        "atom.one.standing": "{subject} staat {relation} {target}",
        "atom.not.standing": "{subject} staat niet {relation} {target}",
        "atom.one.sitting": "{subject} zit {relation} {target}",
        "atom.not.sitting": "{subject} zit niet {relation} {target}",
        "adjective.one": "{subject} is {adjective}",
        "det.some": "minstens een van {subject}",
        "det.every": "ieder lid van {subject}",
        "det.no": "geen lid van {subject}",
        "det.no_except": "niemand behalve {subject}",
        "set.equal": "{left} en {right} zijn dezelfde verzameling",
        "set.not_equal": "{left} en {right} zijn verschillende verzamelingen",
        "number.count": "het aantal {operand}",
        "number.add": "({left} plus {right})",
        "number.subtract": "({left} min {right})",
        "number.compare": "{left} is {comparison} {right}",
        "count.exactly": "precies",
        "count.at_least": "minstens",
        "count.at_most": "hoogstens",
        "count.people.one": "{quantifier} {count} persoon staat {relation} {target}",
        "count.people.many": "{quantifier} {count} mensen staan {relation} {target}",
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
        "choice.either": "of {left}, of {right}, maar niet allebei",
        "idiom.same_area": "{first} en {second} staan in hetzelfde gebied",
        "idiom.location.or": "{left} of {right}",
        "idiom.direction": "precies {count} {unit} {direction}",
        "idiom.distance": (
            "{first} en {second} zijn {comparison} {count} {unit} van elkaar verwijderd"
        ),
        "unit.areas.one": "gebiedsgrens",
        "unit.areas.many": "gebiedsgrenzen",
        "unit.manhattan.one": "stap",
        "unit.manhattan.many": "stappen",
        "unit.row.one": "rij",
        "unit.row.many": "rijen",
        "unit.column.one": "kolom",
        "unit.column.many": "kolommen",
        "choice.at least": "minstens {count} van ({choices}) gelden",
        "choice.at most": "hoogstens {count} van ({choices}) gelden",
        "idiom.alone": "{person} is alleen in het eigen gebied",
        "idiom.only_on": "{person} is de enige persoon op {target}",
        "idiom.most_populated": "{area} heeft meer personen dan ieder ander gebied",
        "idiom.least_populated": "{area} heeft minder personen dan ieder ander gebied",
        "idiom.most_populated.free": (
            "{area} heeft meer personen dan ieder ander gebied met een vrij vakje"
        ),
        "idiom.least_populated.free": (
            "{area} heeft minder personen dan ieder ander gebied met een vrij vakje"
        ),
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


def alone_person(formula: lang.Formula, people: Collection[str]) -> lang.Name | None:
    """Recognize exactly one person in a named person's area."""
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
                and counted.operand.target.operand.token.text in people
            ):
                return counted.operand.target.operand
    return None


def only_on(
    formula: lang.Formula, people: Collection[str]
) -> tuple[lang.Name, lang.Operand] | None:
    """Recognize a named person as the entire occupant set of a footprint."""
    if isinstance(formula, lang.SetComparison) and formula.operator.text == "=":
        for occupants, person in ((formula.left, formula.right), (formula.right, formula.left)):
            if (
                isinstance(occupants, lang.Filter)
                and isinstance(occupants.source, lang.Name)
                and occupants.source.token.text == "people"
                and occupants.operator.text == "on"
                and isinstance(person, lang.Name)
                and person.token.text in people
            ):
                return person, occupants.target
    return None


def feature_name(
    name: str,
    many: bool,
    names: Mapping[str, str],
    article: Callable[[str, bool], str],
) -> str:
    """Name one feature, using an indefinite article for repeated instances."""
    if name in names:
        given = names[name]
        determiner, _, noun = given.partition(" ")
        # Dutch adjectives may need different inflection after changing the article.
        if many and determiner.lower() in {"the", "de", "het"} and noun and " " not in noun:
            return article(noun, True)
        return given
    return article(name.replace("_", " "), many)


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
            missing = allowed - supplied
            if missing:
                raise ValueError(
                    f"Words: phrase {key!r} is missing placeholders: {', '.join(sorted(missing))}"
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
        key = "name.object.display" if kind == "object" and name in self.names else f"name.{kind}"
        if (
            kind == "role"
            and key not in self.phrases
            and any(role.name == name and role.allowed_counts == {1} for role in self.board.roles)
        ):
            key = "name.role.one"
        if kind in {"rows", "columns"} and name.isdigit() and key not in self.phrases:
            key = "name.row" if kind == "rows" else "name.column"
        rendered = self.names.get(name, name.replace("_", " "))
        if kind == "area":
            rendered = re.sub(
                r"^(?:in|on|at|op)\s+(?:(?:the|a|an|de|het|een)\s+)?",
                "",
                rendered,
                flags=re.IGNORECASE,
            )
        return self._phrase(key, name=rendered)

    def _atom_key(
        self, atom: lang.Atom, bindings: dict[str, Shape], *, negated: bool = False
    ) -> str:
        key = "atom.not" if negated else "atom.one"
        if (
            key in self.phrases
            or infer_operand(self.board, atom.subject, bindings).sort is not Sort.PERSON
        ):
            return key
        if atom.operator.text == "beside" or atom.operator.text.startswith("dir:"):
            return f"{key}.standing"
        if atom.operator.text == "on":
            return f"{key}.sitting"
        return key

    def _relation(
        self,
        operator: lang.Token,
        subject: lang.Operand,
        target: lang.Operand,
        bindings: dict[str, Shape],
        measure: lang.Measure | None,
    ) -> str:
        mode = operator.text
        if (
            mode == "in"
            and "rel.in" not in self.phrases
            and infer_operand(self.board, subject, bindings).sort is Sort.PERSON
            and isinstance(target, lang.Name)
            and target.token.text.startswith("area:")
        ):
            preposition, _ = self._area_location(target.token.text.partition(":")[2])
            if preposition is not None:
                return preposition
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
                elif (
                    direction == "furthest"
                    and not metric
                    and key not in self.phrases
                    and self._distinct_people(subject, target)
                ):
                    key += ".person"
            relation = self._phrase(key)
            if metric:
                relation = self._phrase(
                    "rel.metric", relation=relation, metric=self._phrase(f"metric.{metric}")
                )
        else:
            relation = self._phrase(f"rel.{mode}")
        return relation

    def _cell_target(
        self, target: lang.Operand, bindings: dict[str, Shape], namespace: str | None = None
    ) -> str | None:
        if isinstance(target, lang.Name):
            prefix, separator, name = target.token.text.partition(":")
            if not separator:
                prefix, name = namespace or "", prefix
            if prefix == "object" and not {"target.object", "target.object.named"}.intersection(
                self.phrases
            ):
                return self._phrase("target.object.cell", name=self._feature_name("object", name))
        elif isinstance(target, lang.Union):
            first = target.items[0]
            inherited = (
                first.token.text.partition(":")[0]
                if isinstance(first, lang.Name) and ":" in first.token.text
                else None
            )
            parts: list[str] = []
            for item in target.items:
                rendered = self._cell_target(item, bindings, inherited)
                if rendered is None:
                    return None
                parts.append(rendered)
            result = parts[0]
            for part in parts[1:]:
                result = self._phrase("target.or", left=result, right=part)
            return result
        elif (
            isinstance(target, lang.Filter)
            and isinstance(target.source, lang.Name)
            and target.source.token.text == "people"
            and target.operator.text == "on"
            and target.measure is None
            and "op.filter" not in self.phrases
        ):
            return self._phrase(
                "target.person.on",
                target=self._target(target.target, None, bindings, target.operator, target.source),
            )
        return None

    def _area_union(self, atom: lang.Atom, bindings: dict[str, Shape]) -> str | None:
        if (
            atom.operator.text != "in"
            or atom.determiner is not None
            or not isinstance(atom.subject, lang.Name)
            or atom.subject.token.text not in self.board.people
            or not isinstance(atom.target, lang.Union)
            or "op.union" in self.phrases
        ):
            return None
        parts: list[str] = []
        inherited = ""
        for item in atom.target.items:
            if not isinstance(item, lang.Name):
                return None
            namespace, separator, name = item.token.text.partition(":")
            if separator:
                inherited = namespace
            else:
                namespace, name = inherited, namespace
            if namespace != "area":
                return None
            preposition, noun = self._area_location(name)
            relation = (
                preposition
                if preposition and "rel.in" not in self.phrases
                else self._phrase("rel.in")
            )
            parts.append(
                self._phrase(
                    self._atom_key(atom, bindings),
                    subject=self._operand(atom.subject, bindings),
                    relation=relation,
                    target=noun,
                )
            )
        result = parts[0]
        for part in parts[1:]:
            result = self._phrase("idiom.location.or", left=result, right=part)
        return result

    def _exact_direction(
        self, atom: lang.Atom, bindings: dict[str, Shape], *, negated: bool = False
    ) -> str | None:
        direction = atom.operator.text.removeprefix("dir:")
        if (
            direction not in {"up", "down", "left", "right"}
            or atom.measure is None
            or atom.measure.comparison.text != "="
            or int(atom.measure.value.text) < 1
            or infer_operand(self.board, atom.subject, bindings).sort is not Sort.PERSON
            or infer_operand(self.board, atom.target, bindings).sort is not Sort.PERSON
            or {f"rel.dir.{direction}", f"rel.dir.{direction}.exact", "rel.measure"}.intersection(
                self.phrases
            )
        ):
            return None
        count = int(atom.measure.value.text)
        names = NUMBERS[self.language]
        unit = "row" if direction in {"up", "down"} else "column"
        return self._phrase(
            self._atom_key(atom, bindings, negated=negated),
            subject=self._determined(atom.subject, atom.determiner, bindings),
            relation=self._phrase(
                "idiom.direction",
                count=names[count] if count < len(names) else str(count),
                unit=self._phrase(f"unit.{unit}.{'one' if count == 1 else 'many'}"),
                direction=self._phrase(f"rel.dir.{direction}.exact"),
            ),
            target=self._target(atom.target, None, bindings, atom.operator, atom.subject),
        )

    def _distance_pair(self, atom: lang.Atom, bindings: dict[str, Shape]) -> str | None:
        mode = atom.operator.text.removeprefix("dir:")
        comparisons = {"=": "count.exactly", ">=": "count.at_least", "<=": "count.at_most"}
        if (
            not atom.operator.text.startswith("dir:")
            or mode not in {"areas", "manhattan"}
            or atom.determiner is not None
            or atom.measure is None
            or atom.measure.comparison.text not in comparisons
            or int(atom.measure.value.text) < 1
            or not self._distinct_people(atom.subject, atom.target)
            or {
                "atom.one",
                f"rel.dir.{mode}",
                "rel.measure",
                "rel.distinct_target",
                f"cmp.{atom.measure.comparison.text}",
            }.intersection(self.phrases)
        ):
            return None
        count = int(atom.measure.value.text)
        numbers = NUMBERS[self.language]
        return self._phrase(
            "idiom.distance",
            first=self._operand(atom.subject, bindings),
            second=self._operand(atom.target, bindings),
            comparison=self._phrase(comparisons[atom.measure.comparison.text]),
            count=numbers[count] if count < len(numbers) else str(count),
            unit=self._phrase(f"unit.{mode}.{'one' if count == 1 else 'many'}"),
        )

    def _near_king(
        self, atom: lang.Atom, bindings: dict[str, Shape], *, negated: bool = False
    ) -> str | None:
        if (
            atom.operator.text != "dir:king"
            or atom.determiner is not None
            or not isinstance(atom.subject, lang.Name)
            or atom.subject.token.text not in self.board.people
            or atom.measure is None
            or atom.measure.comparison.text != "<="
            or int(atom.measure.value.text) != 1
            or {"rel.dir.king", "rel.measure"}.intersection(self.phrases)
        ):
            return None
        target = self._cell_target(atom.target, bindings)
        if target is None:
            return None
        clause = self._phrase(
            self._atom_key(atom, bindings, negated=negated),
            subject=self._operand(atom.subject, bindings),
            relation=self._phrase("rel.dir.king.near"),
            target=target,
        )
        return self._phrase("idiom.king.not_near" if negated else "idiom.king.near", clause=clause)

    def _target(
        self,
        target: lang.Operand,
        measure: lang.Measure | None,
        bindings: dict[str, Shape],
        operator: lang.Token | None = None,
        subject: lang.Operand | None = None,
    ) -> str:
        namespace, _, name = (
            target.token.text.partition(":") if isinstance(target, lang.Name) else ("", "", "")
        )
        shape = infer_operand(self.board, subject, bindings) if subject is not None else None
        person = shape is not None and shape.sort is Sort.PERSON
        cell_target = (
            self._cell_target(target, bindings)
            if person and operator and operator.text in {"dir:king", "dir:knight"}
            else None
        )
        if cell_target is not None:
            rendered = cell_target
        elif namespace == "area" and person:
            _, rendered = self._area_location(name)
        elif (
            namespace == "corner"
            and person
            and shape is not None
            and shape.maximum == 1
            and operator is not None
            and operator.text == "in"
            and not {"name.corner", "rel.any_target"}.intersection(self.phrases)
        ):
            rendered = self._phrase("target.corner")
        elif namespace in {"edge_item", "point_object", "mark"} and person:
            rendered = self._phrase(
                f"target.{namespace}",
                name=self.names.get(name, name.replace("_", " "))
                if namespace == "mark"
                else self._feature_name(namespace, name),
            )
        elif namespace == "object":
            key = (
                "target.object.named"
                if name not in self.names and "target.object.named" in self.phrases
                else "target.object"
            )
            rendered = self._phrase(
                key,
                name=name if key == "target.object.named" else self._feature_name(namespace, name),
            )
        else:
            rendered = self._operand(target, bindings)
            if infer_operand(self.board, target, bindings).maximum > 1:
                rendered = self._phrase("rel.any_target", target=rendered)
        if (
            operator
            and operator.text == "dir:areas"
            and (subject is None or not self._distinct_people(subject, target))
        ):
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

    def _area_location(self, name: str) -> tuple[str | None, str]:
        if name in self.names:
            phrase = self.names[name]
            preposition, separator, noun = phrase.partition(" ")
            if separator and preposition.lower() in {"in", "on", "at", "op"}:
                return preposition.lower(), noun
            return None, phrase
        return None, self._phrase("noun.the", name=name.replace("_", " "))

    def _distinct_people(self, first: lang.Operand, second: lang.Operand) -> bool:
        return (
            isinstance(first, lang.Name)
            and isinstance(second, lang.Name)
            and first.token.text in self.board.people
            and second.token.text in self.board.people
            and first.token.text != second.token.text
        )

    def _feature_name(self, namespace: str, name: str) -> str:
        by_kind: dict[str, Collection[BoardObject | EdgeItem | PointObject | CellMark]] = {
            "object": self.board.objects,
            "edge_item": self.board.edge_items,
            "point_object": self.board.point_objects,
            "mark": self.board.marks,
        }
        entities = by_kind[namespace]
        many = sum(entity.name == name for entity in entities) > 1

        def article(noun: str, indefinite: bool) -> str:
            key = "the"
            if indefinite:
                key = "an" if self.language == "en" and noun[:1].lower() in "aeiou" else "a"
            return self._phrase(f"noun.{key}", name=noun)

        return feature_name(name, many, self.names, article)

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
                singular_area = isinstance(operand, lang.Name) and operand.token.text.startswith(
                    "area:"
                )
                key = f"adj.{adjective.text}" + ("" if singular_area else ".modifier")
                return f"{self._phrase(key)} {self._operand(operand, bindings)}"
            case lang.Projection(kind=kind, operand=operand):
                shape = infer_operand(self.board, operand, bindings)
                if (
                    kind.text == "area"
                    and shape.sort is Sort.PERSON
                    and shape.minimum == shape.maximum == 1
                    and "op.projection" not in self.phrases
                ):
                    return self._phrase(
                        "projection.area.person", operand=self._operand(operand, bindings)
                    )
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
                    target=self._target(target, measure, bindings, op, source),
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
                variable_name = self.names.get(
                    variable.text, self._phrase(f"variable.{shape.sort.value}")
                )
                scoped_words = replace(self, names={**self.names, variable.text: variable_name})
                return self._phrase(
                    "op.comprehension",
                    variable=variable_name,
                    source=self._operand(source, bindings),
                    condition=scoped_words._formula(condition, scoped),
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
        if (
            determiner is not None
            and determiner.text == "no"
            and "det.no" not in self.phrases
            and isinstance(subject, lang.Difference)
            and isinstance(subject.left, lang.Name)
            and subject.left.token.text == "people"
        ):
            return self._phrase("det.no_except", subject=self._operand(subject.right, bindings))
        rendered = self._operand(subject, bindings)
        return self._phrase(f"det.{determiner.text}", subject=rendered) if determiner else rendered

    def _count_idiom(
        self, formula: lang.NumberComparison, bindings: dict[str, Shape]
    ) -> str | None:
        if (
            "number.compare" in self.phrases
            or not isinstance(formula.left, lang.Count)
            or not isinstance(formula.left.operand, lang.Filter)
            or not isinstance(formula.right, lang.Integer)
        ):
            return None
        filtered = formula.left.operand
        if (
            not isinstance(filtered.source, lang.Name)
            or filtered.source.token.text != "people"
            or filtered.operator.text not in {"on", "in"}
            or filtered.measure is not None
            or formula.operator.text not in {"=", ">=", "<="}
        ):
            return None
        count = int(formula.right.value.text)
        names = NUMBERS[self.language]
        number = names[count] if 0 <= count < len(names) else str(count)
        quantifier = {"=": "exactly", ">=": "at_least", "<=": "at_most"}[formula.operator.text]
        target = self._target(filtered.target, None, bindings, filtered.operator, filtered.source)
        if isinstance(filtered.target, lang.Name):
            namespace, _, name = filtered.target.token.text.partition(":")
            if (
                namespace in {"edge_item", "point_object", "mark"}
                and f"target.{namespace}" not in self.phrases
            ):
                target = (
                    self.names.get(name, self._phrase("count.mark", name=name.replace("_", " ")))
                    if namespace == "mark"
                    else self._feature_name(namespace, name)
                )
        return self._phrase(
            "count.people.one" if count == 1 else "count.people.many",
            count=number,
            quantifier=self._phrase(f"count.{quantifier}"),
            relation=self._relation(
                filtered.operator, filtered.source, filtered.target, bindings, None
            ),
            target=target,
        )

    def _population_idiom(self, formula: lang.Quantified) -> str | None:
        if (
            formula.quantifier.text != "every"
            or len(formula.variables) != 1
            or not isinstance(formula.source, lang.Difference)
            or not isinstance(formula.source.right, lang.Name)
            or not formula.source.right.token.text.startswith("area:")
            or infer_operand(self.board, formula.source.right).maximum != 1
            or not isinstance(formula.body, lang.NumberComparison)
            or formula.body.operator.text not in {"<", ">"}
        ):
            return None
        domain = formula.source.left
        all_areas = isinstance(domain, lang.Name) and domain.token.text == "areas"
        free_areas = (
            isinstance(domain, lang.Projection)
            and domain.kind.text == "area"
            and isinstance(domain.operand, lang.Qualified)
            and domain.operand.adjective.text == "free"
            and isinstance(domain.operand.operand, lang.Name)
            and domain.operand.operand.token.text == "cells"
        )
        if not (all_areas or free_areas):
            return None
        comparison = formula.body
        if not isinstance(comparison.left, lang.Count) or not isinstance(
            comparison.right, lang.Count
        ):
            return None
        targets = []
        for count in (comparison.left, comparison.right):
            operand = count.operand
            if (
                not isinstance(operand, lang.Filter)
                or not isinstance(operand.source, lang.Name)
                or operand.source.token.text != "people"
                or operand.operator.text != "in"
                or not isinstance(operand.target, lang.Name)
            ):
                return None
            targets.append(operand.target.token.text)
        if targets != [formula.variables[0].text, formula.source.right.token.text]:
            return None
        key = "idiom.most_populated" if comparison.operator.text == "<" else "idiom.least_populated"
        if free_areas:
            key += ".free"
        return self._phrase(key, area=self._operand(formula.source.right, {}))

    def _formula(self, value: lang.Formula, bindings: dict[str, Shape]) -> str:
        if (
            isinstance(value, lang.Quantified)
            and value.quantifier.text == "every"
            and len(value.variables) == 1
            and "quant.every" not in self.phrases
            and (shape := infer_operand(self.board, value.source, bindings)).sort is Sort.PERSON
            and shape.minimum == shape.maximum == 1
        ):
            (variable,) = value.variables
            scoped = {**bindings, variable.text: shape}
            words = replace(
                self, names={**self.names, variable.text: self._operand(value.source, bindings)}
            )
            return words._formula(value.body, scoped)
        if isinstance(value, lang.Atom) and (idiom := self._area_union(value, bindings)):
            return idiom
        if isinstance(value, lang.Atom) and (idiom := self._exact_direction(value, bindings)):
            return idiom
        if isinstance(value, lang.Atom) and (idiom := self._distance_pair(value, bindings)):
            return idiom
        if isinstance(value, lang.Atom) and (idiom := self._near_king(value, bindings)):
            return idiom
        if isinstance(value, lang.NumberComparison) and (
            idiom := self._count_idiom(value, bindings)
        ):
            return idiom
        if isinstance(value, lang.Quantified) and (idiom := self._population_idiom(value)):
            return idiom
        match value:
            case lang.Atom(subject=subject, operator=op, target=target, determiner=det):
                if (
                    op.text == "dir:areas"
                    and self._same_area(value.measure)
                    and det is None
                    and self._distinct_people(subject, target)
                    and "rel.dir.areas.same" not in self.phrases
                ):
                    return self._phrase(
                        "idiom.same_area",
                        first=self._operand(subject, bindings),
                        second=self._operand(target, bindings),
                    )
                return self._phrase(
                    self._atom_key(value, bindings),
                    subject=self._determined(subject, det, bindings),
                    relation=self._relation(op, subject, target, bindings, value.measure),
                    target=self._target(target, value.measure, bindings, op, subject),
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
                if isinstance(formula, lang.Atom) and (
                    idiom := self._area_union(formula, bindings)
                ):
                    return self._phrase("bool.not", formula=idiom)
                if (
                    "bool.not" not in self.phrases
                    and isinstance(formula, lang.Atom)
                    and formula.determiner is None
                    and (idiom := self._exact_direction(formula, bindings, negated=True))
                ):
                    return idiom
                if (
                    "bool.not" not in self.phrases
                    and isinstance(formula, lang.Atom)
                    and (idiom := self._near_king(formula, bindings, negated=True))
                ):
                    return idiom
                if (
                    "bool.not" not in self.phrases
                    and isinstance(formula, lang.Atom)
                    and formula.determiner is None
                    and isinstance(formula.subject, lang.Name)
                    and formula.subject.token.text in self.board.people
                ):
                    return self._phrase(
                        self._atom_key(formula, bindings, negated=True),
                        subject=self._operand(formula.subject, bindings),
                        relation=self._relation(
                            formula.operator,
                            formula.subject,
                            formula.target,
                            bindings,
                            formula.measure,
                        ),
                        target=self._target(
                            formula.target,
                            formula.measure,
                            bindings,
                            formula.operator,
                            formula.subject,
                        ),
                    )
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
                if (
                    quantifier.text == "exactly"
                    and count.text == "1"
                    and len(choices) == 2
                    and "choice.exactly" not in self.phrases
                    and all(isinstance(choice, lang.Atom) for choice in choices)
                ):
                    return self._phrase(
                        "choice.either",
                        left=self._formula(choices[0], bindings),
                        right=self._formula(choices[1], bindings),
                    )
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
        if (
            isinstance(formula, lang.Quantified)
            and formula.quantifier.text == "every"
            and len(formula.variables) == 1
            and infer_operand(self.board, formula.source, {}).sort == Sort.AREA
            and isinstance(formula.body, lang.Atom)
            and isinstance(formula.body.subject, lang.Name)
            and not formula.body.subject.token.text.startswith("?")
            and infer_operand(self.board, formula.body.subject, {}).sort == Sort.PERSON
            and formula.body.operator.text == "in"
            and formula.body.determiner is not None
            and formula.body.determiner.text == "some"
            and isinstance(formula.body.target, lang.Name)
            and formula.body.target.token.text == formula.variables[0].text
        ):
            people = infer_operand(self.board, formula.body.subject)
            if (
                people.minimum == people.maximum == 1
                and "idiom.every_area_someone" not in self.phrases
            ):
                if (
                    isinstance(formula.source, lang.Name)
                    and formula.source.token.text.startswith(("area:", "tag:"))
                    and infer_operand(self.board, formula.source).maximum == 1
                ):
                    namespace, _, name = formula.source.token.text.partition(":")
                    if namespace == "tag" and name not in self.names:
                        (region,) = self.board.tagged_region_ids([name])
                        name = self.board.region_names[region]
                    preposition, noun = self._area_location(name)
                    return self._phrase(
                        "atom.one",
                        subject=self._operand(formula.body.subject, {}),
                        relation=preposition
                        if preposition and "rel.in" not in self.phrases
                        else self._phrase("rel.in"),
                        target=noun,
                    )
                return self._phrase(
                    "idiom.every_area_person",
                    areas=self._operand(formula.source, {}),
                    people=self._operand(formula.body.subject, {}),
                )
            return self._phrase(
                "idiom.every_area_someone",
                areas=self._operand(formula.source, {}),
                people=self._operand(formula.body.subject, {}),
            )
        if person := alone_person(formula, self.board.people):
            return self._phrase("idiom.alone", person=self._name(person.token))
        if only := only_on(formula, self.board.people):
            person, operand = only
            target = self._operand(operand, {})
            maximum = infer_operand(self.board, operand, {}).maximum
            if (
                maximum == 1
                and isinstance(operand, lang.Name)
                and operand.token.text.startswith("object:")
                and "name.object" not in self.phrases
            ):
                target = self._target(operand, None, {}, subject=person)
            if maximum > 1:
                target = self._phrase("rel.any_scope", target=target)
            return self._phrase("idiom.only_on", person=self._name(person.token), target=target)
        return self._formula(statement.formula, {})
