"""Pattern-first explanations for any puzzle family, told from the model alone.

Every compiler names its constraints for people ("3 once in col 4", "2 ones
in row 4", "4+ cage r1c1 r2c1") and labels each with the puzzle rule it is an
instance of (`family=`). That is enough to tell a short proof in the puzzle's
own terms: which rule or clue forced what, grouped by pattern rather than
listed cell by cell. The proof comes from `proof`; nothing here knows any
puzzle family, so a new family is explained as soon as it names its
constraints well.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations, product
from typing import Any

from .core import Kind, Model, Step
from .proof import HARDEST_FIRST, Episode, Inference, Move, episodes, essential, replay
from .story import Wording

SHOWN_CLUES = 5  # clue deductions told in one paragraph
PLACEMENTS_PER_PARAGRAPH = 10  # single placements told in one paragraph
MAX_REPLAYS = 60  # proof replays spent thinning one explanation
_CELL = re.compile(r"^r(\d+)c(\d+)$")


@dataclass(frozen=True)
class LostCause:
    source: str | None = None
    placement: tuple[str, Any] | None = None
    rule: str | None = None


@dataclass(frozen=True)
class CountEvidence:
    source: str
    facts: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class Pruned:
    """Count clues that took values from a variable before it had one left."""

    causes: tuple[tuple[str, tuple[Any, ...]], ...]


@dataclass(frozen=True)
class Exclusions:
    """Reasons for every other value of a single-valued variable."""

    causes: tuple[str, ...]
    earlier: bool = False
    constraint: str | None = None


@dataclass(frozen=True)
class Explanation:
    """Narrative paragraphs and whether they account for the entire solution."""

    paragraphs: tuple[str, ...]
    complete: bool

    def markdown(self) -> str:
        return "\n\n".join(f"- {paragraph}" for paragraph in self.paragraphs)


def _runs(points: list[tuple[int, int]], along: int) -> list[list[tuple[int, int]]]:
    """Consecutive cells that step by one along index `along`, the other fixed."""
    runs: list[list[tuple[int, int]]] = []
    for point in points:
        last = runs[-1][-1] if runs else None
        if (
            last is not None
            and last[1 - along] == point[1 - along]
            and last[along] + 1 == point[along]
        ):
            runs[-1].append(point)
        else:
            runs.append([point])
    return runs


def compress(names: Sequence[str], say: Wording) -> str:
    """Grid cells as runs along a row or column, joined by an en dash; others as listed."""
    cells = [_CELL.match(name) for name in names]
    if len(names) < 3 or not all(cells):
        return say.join(list(names))
    points = sorted({(int(m[1]), int(m[2])) for m in cells if m})
    runs = _runs(points, along=1)
    down = _runs(sorted(points, key=lambda p: (p[1], p[0])), along=0)
    if len(down) < len(runs):
        runs = down
    said: list[str] = []
    for run in runs:
        if len(run) > 2:
            said.append(f"r{run[0][0]}c{run[0][1]}\u2013r{run[-1][0]}c{run[-1][1]}")
        else:
            said += [f"r{row}c{col}" for row, col in run]
    return say.join(said)


class Narrator:
    """Render a generic proof, with overridable vocabulary for a puzzle family."""

    def __init__(
        self,
        model: Model,
        say: Wording,
        source_words: Mapping[str, str] | None = None,
        kind: str | None = None,
        hidden_words: Mapping[tuple[str, Any], str] | None = None,
        value_words: Mapping[Any, str] | None = None,
        comparisons: Mapping[str, tuple[tuple[str, str], ...]] | None = None,
        support_words: Mapping[tuple[str, Any], str] | None = None,
    ) -> None:
        self.model = model
        self.say = say
        self.kind = kind
        self.source_words = dict(source_words or {})
        self.hidden_words = dict(hidden_words or {})
        self.value_words: dict[Any, str] = dict(value_words or {})
        self.comparisons = dict(comparisons or {})
        self.support_words = dict(support_words or {})
        self.visible = set(model.variables) | {var for var, _ in self.hidden_words}
        self.constraints = {c.name: c for c in model.constraints}
        self.domains = {model.constraints[model.domain_of(var)].name for var in model.all_variables}
        self.told: set[tuple[str, Any]] = set()
        self.explained_removals: set[tuple[str, Any]] = set()
        self.explained_counts: set[CountEvidence] = set()
        self.lost: dict[tuple[str, Any], LostCause] = {}
        self.pruned: dict[str, dict[str, list[Any]]] = {}

    # --- literals ---------------------------------------------------------

    def _boolean(self, var: str) -> bool:
        return {self.model.value_of(x) for x in self._domain(var)} <= {True, False}

    def _yes_or_no(self, source: str) -> bool:
        """Whether a constraint only says a yes/no cell is one or the other."""
        constraint = self.constraints.get(source)
        if constraint is None or source not in self.domains or not constraint.literals:
            return False
        return self._boolean(self.model.var_of(constraint.literals[0]))

    def _domain(self, var: str) -> Sequence[int]:
        return self.model.constraints[self.model.domain_of(var)].literals

    def value_word(self, value: Any) -> str:
        return self.value_words.get(value, str(value))

    def placed(self, var: str, value: Any, name: str | None = None) -> str:
        """`var` takes `value`; `name` says which cells when several share it."""
        if (var, value) in self.hidden_words:
            return str(self.hidden_words[var, value])
        if isinstance(value, bool) and self._boolean(var):
            word = f"generic.{str(value).lower()}.{self.kind}"
            if self.say.has(word):
                return self.say("generic.placed", var=name or var, value=self.say(word))
            return self.say("generic.yes" if value else "generic.no", var=name or var)
        return self.say("generic.placed", var=name or var, value=self.value_word(value))

    def negated(self, var: str, value: Any) -> str:
        if isinstance(value, bool) and self._boolean(var):
            return self.placed(var, not value)
        return self.say("generic.not_placed", var=var, value=self.value_word(value))

    def conclusion(self, steps: Iterable[Step]) -> str | None:
        """What a deduction settled: its placements, then what it ruled out.

        Cells that lose the same values are named together, so a pattern reads
        "r1c1 and r1c2 cannot be 1, 2 or 3" rather than one cell at a time.
        """
        placements: list[tuple[str, Any]] = []
        removed: dict[str, list[Any]] = {}
        for step in steps:
            if step.var not in self.visible or step.placing is not None:
                continue
            if step.asserted:
                pair = (step.var, step.value)
            elif isinstance(step.value, bool) and self._boolean(step.var):
                pair = (step.var, not step.value)
            else:
                values = removed.setdefault(step.var, [])
                if step.value not in values:
                    values.append(step.value)
                continue
            if pair not in placements:
                placements.append(pair)
        settled = {var for var, _ in placements}
        self.explained_removals.update(
            (var, value)
            for var, values in removed.items()
            if var not in settled
            for value in values
        )
        alike: dict[tuple[Any, ...], list[str]] = {}
        for var, values in removed.items():
            if var not in settled:
                alike.setdefault(tuple(values), []).append(var)
        self.told.update(placements)
        together: dict[Any, tuple[Any, list[str]]] = {}
        for var, value in placements:
            key = (var, value) if (var, value) in self.hidden_words else (None, value)
            together.setdefault(key, (value, []))[1].append(var)
        said = [
            f"**{self.placed(where[0], value, compress(where, self.say))}**"
            for value, where in together.values()
        ]
        said += [
            "**"
            + self.say(
                "generic.cannot_be",
                where=compress(where, self.say),
                values=self.say.join([self.value_word(v) for v in values], "or"),
            )
            + "**"
            for values, where in alike.items()
        ]
        return self.say.join(said) if said else None

    # --- names ------------------------------------------------------------

    def rule_of(self, source: str) -> str:
        """The puzzle rule a constraint is one instance of, else its own name."""
        constraint = self.constraints.get(source)
        if constraint is not None and constraint.family:
            return constraint.family
        return source

    def names(self, sources: Sequence[str]) -> str:
        """Constraint names in italics, each with its clue's own wording when known."""
        shown = dict.fromkeys(self.source_words.get(name, name) for name in sources)
        return self.say.join([f"*{name}*" for name in shown])

    # --- singles ----------------------------------------------------------

    def _single_exclusions(
        self, before: Model, var: str, history: Sequence[Step]
    ) -> Exclusions | None:
        exclusions = [literal for literal in self._domain(var) if before.is_false(literal)]
        if not exclusions:
            return None
        placements: dict[str, list[tuple[str, Any]]] = {}
        values_by_source: dict[str, list[Any]] = {}
        earlier = False
        for literal in exclusions:
            value = before.value_of(literal)
            if (var, value) in self.explained_removals:
                earlier = True
                continue
            step = next(
                (
                    item
                    for item in history
                    if item.var == var and item.value == value and not item.asserted
                ),
                None,
            )
            if step is None:
                return None
            sources = [source for source in step.sources if source not in self.domains]
            if not sources:
                return None
            if (
                step.placing is not None
                and step.placing[0] in self.visible
                and len(sources) == 1
                and (constraint := self.constraints.get(sources[0])) is not None
                and constraint.kind in (Kind.EXACTLY_ONE, Kind.AT_MOST_ONE)
            ):
                source = constraint.family or constraint.name
                placed = placements.setdefault(source, [])
                if step.placing not in placed:
                    placed.append(step.placing)
                values_by_source.setdefault(source, []).append(value)
            else:
                return None
        causes = [
            self.say(
                "generic.exclusion_by_placements",
                placements=self.say.join([self.placed(*pair) for pair in placed]),
                source=self.names([source]),
                values=self.say.join(
                    [self.value_word(value) for value in values_by_source[source]]
                ),
                verb=self.say("generic.rule_out" if len(placed) > 1 else "generic.rules_out_verb"),
            )
            for source, placed in placements.items()
        ]
        return Exclusions(tuple(causes), earlier) if causes or earlier else None

    def _constraint_single_exclusions(
        self, before: Model, step: Step, source: str, history: Sequence[Step]
    ) -> Exclusions | None:
        constraint = self.constraints.get(source)
        if constraint is None or constraint.kind is not Kind.EXACTLY_ONE:
            return None
        live = before.live(constraint.index)
        if len(live) != 1 or (before.var_of(live[0]), before.value_of(live[0])) != (
            step.var,
            step.value,
        ):
            return None
        alternatives: dict[tuple[str, tuple[str, Any]], list[str]] = {}
        placed_elsewhere: dict[tuple[str, Any], list[tuple[str, tuple[str, Any]]]] = {}
        earlier = False
        for literal in constraint.literals:
            if literal == live[0]:
                continue
            var, value = before.var_of(literal), before.value_of(literal)
            if var not in self.visible or not before.is_false(literal):
                return None
            if (var, value) in self.explained_removals:
                earlier = True
                continue
            prior = next(
                (
                    item
                    for item in history
                    if item.var == var and item.value == value and not item.asserted
                ),
                None,
            )
            if prior is None or prior.placing is None or prior.placing[0] not in self.visible:
                return None
            sources = [name for name in prior.sources if name not in self.domains]
            if (
                not sources
                and prior.placing[0] == var
                and prior.placing[1] != value
                and prior.sources == (self.model.constraints[self.model.domain_of(var)].name,)
            ):
                sources = list(prior.sources)
            if len(sources) != 1:
                return None
            cause = self.constraints.get(sources[0])
            if cause is None or cause.kind not in (Kind.EXACTLY_ONE, Kind.AT_MOST_ONE):
                return None
            name = cause.family or cause.name
            if sources[0] in self.domains and prior.placing[0] == var:
                placed_elsewhere.setdefault((name, value), []).append((var, prior.placing))
            else:
                alternatives.setdefault((name, prior.placing), []).append(self.placed(var, value))
        grouped_causes = []
        for (name, value), placements in placed_elsewhere.items():
            if len(placements) > 1 and all(var in self.model.variables for var, _ in placements):
                grouped_causes.append(
                    self.say(
                        "generic.placed_elsewhere",
                        variables=self.say.join([var for var, _ in placements]),
                        value=self.value_word(value),
                    )
                )
            else:
                for var, placement in placements:
                    alternatives.setdefault((name, placement), []).append(self.placed(var, value))
        causes = [
            self.say(
                "generic.exclusion_by_placements",
                placements=self.placed(*placement),
                source=self.names([name]),
                values=self.say.join(values),
                verb=self.say("generic.rules_out_verb"),
            )
            for (name, placement), values in alternatives.items()
        ]
        causes.extend(grouped_causes)
        return Exclusions(tuple(causes), earlier, source) if causes else None

    def _count_single_support(
        self, before: Model, var: str, value: bool, sources: Sequence[str] = ()
    ) -> CountEvidence | None:
        """Cite a count only when already-told facts directly force the cell."""
        for constraint in before.constraints:
            if (
                constraint.kind is not Kind.COUNT
                or constraint.reified_by is not None
                or not constraint.allowed_counts
                or any(before.value_of(lit) is not True for lit in constraint.literals)
                or (sources and constraint.name not in sources)
            ):
                continue
            target = next(
                (
                    literal
                    for literal in constraint.literals
                    if before.var_of(literal) == var and before.value_of(literal) is True
                ),
                None,
            )
            if target is None or before.is_true(target) or (value and before.is_false(target)):
                continue
            if value:
                if sum(not before.is_false(lit) for lit in constraint.literals) != min(
                    constraint.allowed_counts
                ):
                    continue
                relevant = [lit for lit in constraint.literals if before.is_false(lit)]
                facts = [(before.var_of(lit), False) for lit in relevant]
            else:
                relevant = [lit for lit in constraint.literals if before.is_true(lit)]
                if len(relevant) != max(constraint.allowed_counts):
                    continue
                facts = [(before.var_of(lit), before.value_of(lit)) for lit in relevant]
            if not facts or any(
                fact_var not in self.visible
                or not self._boolean(fact_var)
                or (
                    (fact_var, fact_value) not in self.told
                    and self.model.chosen(fact_var) != fact_value
                )
                for fact_var, fact_value in facts
            ):
                continue
            return CountEvidence(constraint.name, tuple(facts))
        return None

    def _count_facts(self, evidence: CountEvidence) -> str:
        grouped: dict[tuple[Any, str | None], list[str]] = {}
        for var, value in evidence.facts:
            grouped.setdefault(
                (value, var if (var, value) in self.hidden_words else None), []
            ).append(var)
        return self.say.join(
            [
                self.placed(variables[0], value, compress(variables, self.say))
                for (value, _), variables in grouped.items()
            ]
        )

    def singles(self, inferences: Sequence[Inference], history: Sequence[Step]) -> list[str]:
        """Each placement in the order it was found, with the rule that left it.

        A yes/no cell losing one value is placed on the other, for the reason it
        lost it. Consecutive placements with one reason are told together, and
        those with one value too share a single "= value".
        """
        found: list[tuple[Any, str, Any]] = []
        for inference in inferences:
            for step in inference.steps:
                if step.placing is not None or step.var not in self.visible:
                    continue
                if step.asserted:
                    pair = (step.var, step.value)
                elif isinstance(step.value, bool) and self._boolean(step.var):
                    pair = (step.var, not step.value)
                else:
                    continue
                if pair in self.told:
                    continue
                self.told.add(pair)
                source = next((s for s in step.sources if not self._yes_or_no(s)), None)
                if isinstance(pair[1], bool) and not pair[1]:
                    opposite = next(
                        (
                            literal
                            for literal in self._domain(step.var)
                            if self.model.value_of(literal) is True
                        ),
                        None,
                    )
                    zero_count = next(
                        (
                            constraint.name
                            for constraint in inference.before.constraints
                            if constraint.kind is Kind.COUNT
                            and constraint.reified_by is None
                            and constraint.allowed_counts == {0}
                            and opposite in constraint.literals
                        ),
                        None,
                    )
                    if zero_count is not None:
                        source = zero_count
                reason: Any
                if source is None:
                    reason = self.lost.get((step.var, not step.value)) if step.asserted else None
                elif source in self.domains:
                    causes = self.pruned.pop(step.var, {})
                    for (var, value), lost in self.lost.items():
                        if var == step.var and lost.source is not None:
                            taken = causes.setdefault(lost.source, [])
                            if value not in taken:
                                taken.append(value)
                    reason = (
                        Pruned(tuple((name, tuple(values)) for name, values in causes.items()))
                        if causes and step.asserted
                        else self._single_exclusions(inference.before, step.var, history)
                        if step.asserted
                        else ""
                    )
                    if reason is None:
                        reason = ""
                else:
                    reason = (
                        self._constraint_single_exclusions(inference.before, step, source, history)
                        if step.asserted
                        else None
                    ) or source
                hidden_cause = (
                    isinstance(reason, LostCause)
                    and reason.placement is not None
                    and reason.placement[0] not in self.visible
                )
                hidden_options = (
                    isinstance(reason, str)
                    and (constraint := self.constraints.get(reason)) is not None
                    and (
                        len(constraint.literals) == 1
                        or any(
                            self.model.var_of(lit) not in self.visible
                            for lit in constraint.literals
                        )
                    )
                )
                count_cause = isinstance(reason, LostCause) and reason.source is not None
                direct_count = (
                    isinstance(reason, str)
                    and (constraint := self.constraints.get(reason)) is not None
                    and constraint.kind is Kind.COUNT
                )
                if isinstance(pair[1], bool) and (
                    hidden_cause or hidden_options or count_cause or direct_count
                ):
                    sources = (reason.source,) if count_cause else (reason,) if direct_count else ()
                    reason = self._count_single_support(inference.before, *pair, sources) or reason
                found.append((reason, *pair))
        paragraphs: list[str] = []
        chunks: list[list[tuple[Any, str, Any]]] = []
        weight = 0
        for item in found:
            size = 4 if isinstance(item[0], Exclusions) else 1
            if not chunks or weight + size > PLACEMENTS_PER_PARAGRAPH:
                chunks.append([])
                weight = 0
            chunks[-1].append(item)
            weight += size
        for index, chunk in enumerate(chunks):
            runs: list[tuple[Any, list[tuple[Any, list[str]]]]] = []
            for reason, var, value in chunk:
                if not runs or runs[-1][0] != reason:
                    runs.append((reason, []))
                values = runs[-1][1]
                if (
                    values
                    and values[-1][0] == value
                    and not {(var, value), (values[-1][1][0], value)} & self.hidden_words.keys()
                ):
                    values[-1][1].append(var)
                else:
                    values.append((value, [var]))
            parts = []
            for reason, values in runs:
                listed = self.say.join(
                    [
                        f"**{self.placed(where[0], value, compress(where, self.say))}**"
                        for value, where in values
                    ]
                )
                if reason is None:
                    parts.append(listed)
                elif reason == "":
                    many = sum(len(where) for _, where in values) > 1
                    key = "generic.last_left_each" if many else "generic.last_left"
                    parts.append(self.say(key, placements=listed))
                elif isinstance(reason, Pruned):
                    ruled_out = self.say.join(
                        [
                            self.say(
                                "generic.rules_out",
                                source=self.names([name]),
                                values=self.say.join([self.value_word(value) for value in taken]),
                            )
                            for name, taken in reason.causes
                        ]
                    )
                    many = sum(len(where) for _, where in values) > 1
                    key = "generic.left_after_each" if many else "generic.left_after"
                    parts.append(self.say(key, placements=listed, causes=ruled_out))
                elif isinstance(reason, Exclusions):
                    key = (
                        "generic.constraint_left_after_prior"
                        if reason.constraint and reason.earlier and reason.causes
                        else "generic.constraint_left_after"
                        if reason.constraint
                        else "generic.left_after_prior"
                        if reason.earlier and reason.causes
                        else "generic.left_after_previous"
                        if reason.earlier
                        else "generic.left_after"
                    )
                    parts.append(
                        self.say(
                            key,
                            placements=listed,
                            causes=self.say.join(list(reason.causes)),
                            source=self.names([reason.constraint]) if reason.constraint else "",
                        )
                    )
                elif isinstance(reason, CountEvidence):
                    key = (
                        "generic.count_single_again"
                        if reason in self.explained_counts
                        else "generic.count_single_support"
                    )
                    parts.append(
                        self.say(
                            key,
                            placements=listed,
                            facts=self._count_facts(reason),
                            source=self.names([reason.source]),
                        )
                    )
                    self.explained_counts.add(reason)
                elif isinstance(reason, LostCause):
                    cause = (
                        self.names([reason.source])
                        if reason.source is not None
                        else self.support_words[reason.placement]
                        if reason.placement in self.support_words
                        else self.placed(*reason.placement)
                        if reason.placement is not None
                        else ""
                    )
                    if all(isinstance(value, bool) for value, _ in values):
                        alternatives = self.say.join(
                            [
                                self.placed(where[0], not value, compress(where, self.say))
                                for value, where in values
                            ]
                        )
                        parts.append(
                            self.say(
                                "generic.opposite_ruled_out_by_support"
                                if reason.rule
                                else "generic.opposite_ruled_out_by",
                                placements=listed,
                                alternatives=alternatives,
                                cause=cause,
                                source=self.names([reason.rule]) if reason.rule else "",
                            )
                        )
                    else:
                        parts.append(self.say("generic.by_rule", rules=cause, placements=listed))
                else:
                    parts.append(
                        self.say("generic.by_rule", rules=self.names([reason]), placements=listed)
                    )
            key = "generic.singles_by" if index == 0 else "generic.singles_more"
            if [reason for reason, _ in runs] == [None]:
                key = "generic.singles_plain"
            paragraphs.append(self.say(key, parts="; ".join(parts)))
        return paragraphs

    # --- patterns ---------------------------------------------------------

    def pattern(self, inference: Inference, history: Sequence[Step]) -> str:
        move = inference.move
        assert move is not None
        if move.rule == "what_if":
            paragraph = self._what_if(inference, history)
            self.explained_removals.update(
                (step.var, step.value)
                for step in inference.steps
                if step.var in self.visible and not step.asserted
            )
            return paragraph
        conclusion = self.conclusion(inference.steps) or self.say("generic.internal")
        sources = self.names(move.sources)
        if move.rule in ("count", "relations"):
            if move.rule == "relations" and (candidates := self._relation_premises(inference)):
                clue = self.say(
                    "generic.clue_with_candidates",
                    candidates=candidates,
                    sources=sources,
                    conclusion=conclusion,
                )
                return self.say("generic.clues", items=clue)
            clue = self.say("generic.clue", sources=sources, conclusion=conclusion)
            return self.say("generic.clues", items=clue)
        if move.rule == "subsumption":
            if (
                len(move.sources) == 1
                and (constraint := self.constraints.get(move.sources[0]))
                and constraint.kind is Kind.COUNT
            ):
                placed = [
                    self.placed(
                        inference.before.var_of(literal), inference.before.value_of(literal)
                    )
                    for literal in constraint.literals
                    if inference.before.var_of(literal) in self.visible
                    and inference.before.is_true(literal)
                ]
                if placed:
                    live = inference.before.live(constraint.index)
                    if 1 <= len(live) <= 4 and all(
                        inference.before.var_of(literal) in self.visible for literal in live
                    ):
                        options = self.say.join(
                            [
                                self.placed(
                                    inference.before.var_of(literal),
                                    inference.before.value_of(literal),
                                )
                                for literal in live
                            ]
                        )
                        return self.say(
                            "generic.subsumption_count_options",
                            placed=self.say.join(placed),
                            options=options,
                            sources=sources,
                            scope=self.names(move.scope),
                            conclusion=conclusion,
                        )
                    return self.say(
                        "generic.subsumption_count",
                        placed=self.say.join(placed),
                        sources=sources,
                        scope=self.names(move.scope),
                        conclusion=conclusion,
                    )
            return self.say(
                "generic.subsumption",
                sources=sources,
                scope=self.names(move.scope),
                conclusion=conclusion,
            )
        if move.rule in ("cover2", "cover3"):
            if premise := self._cover_premise(inference):
                return premise
            if premise := self._count_cover_premise(inference, conclusion):
                return premise
            counted = dict.fromkeys(
                (inference.before.var_of(literal), inference.before.value_of(literal))
                for name in move.scope
                if (constraint := self.constraints.get(name)) is not None
                for literal in constraint.literals
                if inference.before.is_true(literal)
                and inference.before.var_of(literal) in self.visible
            )
            if counted:
                return self.say(
                    "generic.cover_counted",
                    counted=self.say.join([self.placed(*pair) for pair in counted]),
                    sources=self._sets(move.sources),
                    scope=self._sets(move.scope),
                    conclusion=conclusion,
                )
            return self.say(
                "generic.cover",
                sources=self._sets(move.sources),
                scope=self._sets(move.scope),
                conclusion=conclusion,
            )
        if move.rule == "chains":
            return self._chain(
                move.chain, conclusion, move.sources, inference.steps, inference.before
            )
        if move.rule == "wing":
            return self.say(
                "generic.wing",
                options=self.say.join([self.placed(*pair) for pair in move.chain], "or"),
                conclusion=conclusion,
            )
        return self.say("generic.other", rule=move.rule, conclusion=conclusion)

    def _relation_premises(self, inference: Inference) -> str | None:
        move = inference.move
        if move is None or len(move.sources) != 1:
            return None
        relation = next(
            (item for item in self.model.relations if item.name == move.sources[0]), None
        )
        if relation is None or not relation.variables:
            return None

        original = [
            {self.model.value_of(literal) for literal in self._domain(var)}
            for var in relation.variables
        ]
        current = [
            {inference.before.value_of(literal) for literal in inference.before.options(var)}
            for var in relation.variables
        ]
        combinations_count = 1
        for values in original:
            combinations_count *= len(values)
            if combinations_count > 4096:
                return None

        def supports(target_index: int, target: Any, domains: Sequence[set[Any]]) -> bool:
            options = [
                ({target} if index == target_index else values)
                for index, values in enumerate(domains)
            ]
            return any(relation.holds(*values) for values in product(*options))

        required: set[int] = set()
        for step in inference.steps:
            try:
                target_index = relation.variables.index(step.var)
            except ValueError:
                continue
            if not supports(target_index, step.value, current) and supports(
                target_index, step.value, original
            ):
                restricted = [
                    index
                    for index, (available, all_values) in enumerate(
                        zip(current, original, strict=True)
                    )
                    if index != target_index and available != all_values
                ]
                for count in range(1, len(restricted) + 1):
                    supports_with_relaxation = [
                        subset
                        for subset in combinations(restricted, count)
                        if supports(
                            target_index,
                            step.value,
                            [
                                original[index] if index in subset else current[index]
                                for index in range(len(current))
                            ],
                        )
                    ]
                    if supports_with_relaxation:
                        required.update(
                            index for subset in supports_with_relaxation for index in subset
                        )
                        break

        if not required:
            return None
        candidates = [
            said
            for index, var in enumerate(relation.variables)
            if index in required and (said := self.remaining(var, current[index]))
        ]
        return self.say.join(candidates) if candidates else None

    def remaining(self, var: str, values: Iterable[Any]) -> str | None:
        """The values `var` has left, or None when a player would not see it.

        A helper the puzzle keeps hidden, or a yes/no cell still open, adds
        nothing; a settled yes/no cell reads as its placement.
        """
        left = sorted(set(values), key=repr)
        if var not in self.visible:
            return None
        if self._boolean(var):
            return self.placed(var, left[0]) if len(left) == 1 else None
        return self.say(
            "generic.remaining_values",
            variable=var,
            values=self.say.join([self.value_word(value) for value in left], "or"),
        )

    def _cover_premise(self, inference: Inference) -> str | None:
        move = inference.move
        assert move is not None
        source_domains = all(name in self.domains for name in move.sources)
        scope_domains = all(name in self.domains for name in move.scope)
        if source_domains == scope_domains:
            return None
        cells_names = move.sources if source_domains else move.scope
        house_names = move.scope if source_domains else move.sources
        cells = [
            self.model.var_of(self.constraints[name].literals[0])
            for name in cells_names
            if self.constraints[name].literals
        ]
        if not cells or len(cells) != len(cells_names):
            return None
        house_values = [
            list(
                dict.fromkeys(
                    self.model.value_of(literal) for literal in self.constraints[name].literals
                )
            )
            for name in house_names
        ]
        if any(len(values) != 1 or isinstance(values[0], bool) for values in house_values):
            return None
        values = [items[0] for items in house_values]
        if len(set(values)) != len(cells):
            return None
        if source_domains:
            candidates = [
                {self.model.value_of(literal) for literal in inference.before.options(cell)}
                for cell in cells
            ]
            if any(not candidate_options <= set(values) for candidate_options in candidates):
                return None
            return self.say(
                "generic.cover_naked",
                cells=self._sets(cells_names),
                values=self.say.join([self.value_word(value) for value in values]),
                rules=self.names(house_names),
                conclusion=self.conclusion(inference.steps) or self.say("generic.internal"),
            )
        selected = set(cells)
        for name, value in zip(house_names, values, strict=True):
            constraint = self.constraints[name]
            matching = {
                self.model.var_of(literal)
                for literal in constraint.literals
                if self.model.value_of(literal) == value
                and literal in inference.before.options(self.model.var_of(literal))
            }
            if not matching or not matching <= selected:
                return None
        return self.say(
            "generic.cover_hidden",
            cells=self._sets(cells_names),
            values=self.say.join([self.value_word(value) for value in values]),
            rules=self.names(house_names),
            conclusion=self.conclusion(inference.steps) or self.say("generic.internal"),
        )

    def _count_cover_premise(self, inference: Inference, conclusion: str) -> str | None:
        move = inference.move
        assert move is not None
        if len(move.scope) != 1:
            return None
        scope = self.constraints.get(move.scope[0])
        sources = [self.constraints.get(name) for name in move.sources]
        if (
            scope is None
            or scope.kind is not Kind.COUNT
            or scope.reified_by is not None
            or any(
                source is None or source.kind is not Kind.COUNT or source.reified_by is not None
                for source in sources
            )
        ):
            return None
        before = inference.before
        counted = [lit for lit in scope.literals if before.is_true(lit)]
        if (
            not counted
            or any(
                before.var_of(lit) not in self.visible
                or (
                    (before.var_of(lit), before.value_of(lit)) not in self.told
                    and self.model.chosen(before.var_of(lit)) != before.value_of(lit)
                )
                for lit in counted
            )
            or before.feasible_counts(scope.index) != {len(counted) + len(sources)}
        ):
            return None
        scope_live = set(before.live(scope.index))
        used: set[int] = set()
        phrases = []
        for source in sources:
            assert source is not None
            live = before.live(source.index)
            true_count = sum(before.is_true(lit) for lit in source.literals)
            if (
                not 1 <= len(live) <= 4
                or before.feasible_counts(source.index) != {true_count + 1}
                or not set(live) <= scope_live
                or used.intersection(live)
                or any(
                    before.var_of(lit) not in self.visible or before.value_of(lit) is not True
                    for lit in live
                )
            ):
                return None
            used.update(live)
            phrases.append(
                self.say(
                    "generic.cover_count_option",
                    source=self.names([source.name]),
                    options=self.say.join(
                        [self.placed(before.var_of(lit), before.value_of(lit)) for lit in live],
                        "or",
                    ),
                )
            )
        excluded = {
            before.literal(step.var, step.value)
            for step in inference.steps
            if step.placing is None and not step.asserted and step.var in self.visible
        }
        if not excluded or not excluded <= scope_live - used:
            return None
        return self.say(
            "generic.cover_count_options",
            counted=self.say.join(
                [self.placed(before.var_of(lit), before.value_of(lit)) for lit in counted]
            ),
            options=self.say.join(phrases),
            scope=self.names(move.scope),
            conclusion=conclusion,
        )

    def _sets(self, names: Sequence[str]) -> str:
        """A cover's constraints by rule, with the cells of one-variable ones."""
        cells = [name for name in names if name in self.domains]
        if len(cells) == len(names):
            vars_ = [
                self.model.var_of(self.constraints[name].literals[0])
                for name in names
                if self.constraints[name].literals
            ]
            return compress(vars_, self.say)
        return self.names(names)

    def _chain(
        self,
        chain: Sequence[tuple[str, Any]],
        conclusion: str,
        sources: Sequence[str] = (),
        steps: Sequence[Step] = (),
        before: Model | None = None,
    ) -> str:
        """A chain starts from its first option false; links alternate true and false.

        A cell that just took a value obviously lost its others, so that link
        goes unsaid.
        """
        links = self._chain_links(chain, sources, before)
        end_reason = self._chain_end_reason(chain, steps)
        if end_reason:
            if len(chain) == 2:
                ends = self.say.join([self.placed(*chain[0]), self.placed(*chain[-1])], "or")
                if (
                    before is not None
                    and sources
                    and self._chain_supported_pair(before, sources[0], chain)
                ):
                    ends = self.say(
                        "generic.chain_supported_either",
                        options=ends,
                        source=self.names([sources[0]]),
                    )
                    ends = ends[:1].upper() + ends[1:]
                return self.say("generic.chain_either_explained", ends=ends, reason=end_reason)
            return self.say(
                "generic.chain_explained",
                start=self.say("generic.chain_if", assumption=self.negated(*chain[0])),
                links=self.say("generic.chain_link").join(links),
                first=self.placed(*chain[0]),
                last=self.placed(*chain[-1]),
                reason=end_reason,
            )
        return self.say(
            "generic.chain",
            start=self.negated(*chain[0]),
            first=self.placed(*chain[0]),
            last=self.placed(*chain[-1]),
            links=self.say("generic.chain_link").join(links),
            conclusion=conclusion,
        )

    def _chain_links(
        self,
        chain: Sequence[tuple[str, Any]],
        sources: Sequence[str],
        before: Model | None,
        start: int = 1,
    ) -> list[str]:
        links = []
        for i, pair in enumerate(chain[1:], start=1):
            if i < start:
                continue
            if not (i % 2 or pair[0] != chain[i - 1][0] or self._boolean(pair[0])):
                continue
            source = sources[i - 1] if i - 1 < len(sources) else None
            domain_link = (
                source is not None and source in self.domains and pair[0] == chain[i - 1][0]
            )
            if domain_link:
                link = self.placed(*pair) + self.say(
                    "generic.chain_domain_reason", excluded=self.placed(*chain[i - 1])
                )
            else:
                supported = (
                    self._chain_supported(before, source, chain[i - 1], pair)
                    if before is not None and source is not None and i % 2
                    else None
                )
                link = supported or (self.placed(*pair) if i % 2 else self.negated(*pair))
                if source is not None and supported is None:
                    link += self.say("generic.chain_reason", source=self.names([source]))
            links.append(link)
        return links

    def _chain_continuation(self, inference: Inference, previous: Inference) -> str | None:
        move, prior_move = inference.move, previous.move
        if (
            move is None
            or prior_move is None
            or move.rule != "chains"
            or prior_move.rule != "chains"
        ):
            return None
        chain, prior_chain = move.chain, prior_move.chain
        if not chain or not prior_chain or chain[0] != prior_chain[0]:
            return None
        shared = min(len(chain), len(prior_chain))
        if chain[:shared] != prior_chain[:shared]:
            return None

        conclusion = self.conclusion(inference.steps)
        end_reason = self._chain_end_reason(chain, inference.steps)
        if not end_reason and conclusion is None:
            return None
        continuation = end_reason.rstrip(".") if end_reason else conclusion
        links = self._chain_links(chain, move.sources, inference.before, len(prior_chain))
        if links:
            return self.say(
                "generic.chain_continuation",
                assumption=self.negated(*chain[0]),
                links=self.say("generic.chain_link").join(links),
                conclusion=continuation,
            )
        return self.say("generic.chain_also", conclusion=continuation)

    def _chain_reused(self, inference: Inference, previous: Sequence[Inference]) -> str | None:
        move = inference.move
        if move is None or move.rule != "chains" or not move.chain:
            return None
        reason = self._chain_end_reason(move.chain, inference.steps)
        if reason is None:
            return None

        match: tuple[int, int, int, Inference] | None = None
        for earlier in previous:
            prior_move = earlier.move
            if prior_move is None or prior_move.rule != "chains":
                continue
            for start in range(1, len(move.chain) - 2):
                for prior_start in range(len(prior_move.chain)):
                    overlap = 0
                    while (
                        start + overlap < len(move.chain)
                        and prior_start + overlap < len(prior_move.chain)
                        and move.chain[start + overlap] == prior_move.chain[prior_start + overlap]
                    ):
                        overlap += 1
                    end = start + overlap - 1
                    if overlap < 3 or end >= len(move.chain) - 1:
                        continue
                    if (
                        move.sources[start:end]
                        != prior_move.sources[prior_start : prior_start + overlap - 1]
                    ):
                        continue
                    candidate = (overlap, start, end, earlier)
                    if match is None or candidate[:3] > match[:3]:
                        match = candidate
        if match is None:
            return None

        _, start, end, earlier = match
        prefix = self._chain_links(move.chain[: start + 1], move.sources[:start], inference.before)
        continuation = self._chain_links(move.chain, move.sources, inference.before, end + 1)
        if not prefix or not continuation:
            return None
        return self.say(
            "generic.chain_reused",
            start=self.say("generic.chain_if", assumption=self.negated(*move.chain[0])),
            prefix=self.say("generic.chain_link").join(prefix),
            shared_start=self.placed(*move.chain[start]),
            shared_end=self.placed(*move.chain[end]),
            continuation=self.say("generic.chain_link").join(continuation),
            first=self.placed(*move.chain[0]),
            last=self.placed(*move.chain[-1]),
            reason=reason,
        )

    def _chain_supported(
        self,
        before: Model,
        source: str,
        previous: tuple[str, Any],
        current: tuple[str, Any],
    ) -> str | None:
        constraint = self.constraints.get(source)
        if constraint is None or not self._chain_supported_pair(
            before, source, (previous, current)
        ):
            return None
        candidates = [
            (before.var_of(literal), before.value_of(literal))
            for literal in before.live(constraint.index)
        ]
        return self.say(
            "generic.chain_supported",
            options=self.say.join([self.placed(*candidate) for candidate in candidates], "or"),
            source=self.names([source]),
            excluded=self.placed(*previous),
            placement=self.placed(*current),
        )

    def _chain_supported_pair(
        self, before: Model, source: str, options: Sequence[tuple[str, Any]]
    ) -> bool:
        constraint = self.constraints.get(source)
        if constraint is None or constraint.kind not in (Kind.EXACTLY_ONE, Kind.COUNT):
            return False
        true_count = sum(before.is_true(literal) for literal in constraint.literals)
        if before.feasible_counts(constraint.index) != {true_count + 1}:
            return False
        candidates = [
            (before.var_of(literal), before.value_of(literal))
            for literal in before.live(constraint.index)
        ]
        return len(candidates) == 2 and set(candidates) == set(options)

    def _chain_end_reason(
        self, chain: Sequence[tuple[str, Any]], steps: Sequence[Step]
    ) -> str | None:
        if not chain or not steps or any(len(step.end_sources) != 2 for step in steps):
            return None
        first = self.placed(*chain[0])
        last = self.placed(*chain[-1])
        return " ".join(
            self.say(
                "generic.chain_eliminates",
                target=self.placed(step.var, step.value),
                first=first,
                first_source=self.names([step.end_sources[0]]),
                last=last,
                last_source=self.names([step.end_sources[1]]),
            )
            for step in steps
        )

    def _relation_options(
        self, step: Step, before: Model, needed: Sequence[int]
    ) -> tuple[str, bool] | None:
        """What the broken relation's cells have left once the trail is played on `before`.

        The flag is true when the text names cells left with no value at all.
        """
        if not step.sources:
            return None
        relation = next((r for r in self.model.relations if r.name == step.sources[0]), None)
        if relation is None or len(relation.variables) > 6:
            return None
        candidate_values = {
            var: {before.value_of(literal) for literal in before.options(var)}
            for var in relation.variables
        }
        explained_values = {var: set(values) for var, values in candidate_values.items()}
        for index in needed:
            item = step.trail[index]
            if relation.name in item.sources:
                break
            if item.var in explained_values:
                if item.asserted:
                    explained_values[item.var] = {item.value}
                else:
                    explained_values[item.var].discard(item.value)
        combinations_count = 1
        for values in explained_values.values():
            combinations_count *= len(values)
        if (
            0 < combinations_count <= 256
            and all(var in self.visible and not self._boolean(var) for var in relation.variables)
            and not any(
                relation.holds(*values)
                for values in product(*(explained_values[var] for var in relation.variables))
            )
        ):
            premises = [self.remaining(var, explained_values[var]) for var in relation.variables]
            if all(item is not None for item in premises):
                return self.say.join([item for item in premises if item is not None]), False
        for item in step.trail:
            if item.var not in candidate_values:
                continue
            if item.asserted:
                candidate_values[item.var] = {item.value}
            else:
                candidate_values[item.var].discard(item.value)
        empty = [var for var, values in candidate_values.items() if not values]
        if empty:
            if not all(var in self.visible and not self._boolean(var) for var in empty):
                return None
            return compress(empty, self.say), True
        combinations = 1
        for values in candidate_values.values():
            combinations *= len(values)
            if combinations > 256:
                return None
        said = [
            option
            for var in relation.variables
            if (option := self.remaining(var, candidate_values[var]))
        ]
        return (self.say.join(said), False) if said else None

    def _what_if(self, inference: Inference, history: Sequence[Step]) -> str:
        step = next(step for step in inference.steps if step.rule == "what_if")
        needed = essential(self.model, history, step)
        broken = step.sources[0] if step.sources else None
        relation = next((item for item in self.model.relations if item.name == broken), None)
        if relation is not None and len(relation.variables) <= 6:
            known: set[tuple[str, Any]] = set()
            extra = []
            for index, item in enumerate(step.trail):
                if broken in item.sources:
                    break
                if index in needed and item.asserted and item.var in self.visible:
                    known.add((item.var, item.value))
                elif (
                    index not in needed
                    and not item.asserted
                    and item.var in relation.variables
                    and item.var in self.visible
                    and item.placing in known
                ):
                    extra.append(index)
            if len(extra) <= 8:
                needed = sorted([*needed, *extra])
        shown: list[str] = []
        shown_pairs: set[tuple[str, Any]] = set()
        eliminated: list[tuple[str, Any]] = []
        elimination_sources: tuple[str, ...] = ()

        def flush_eliminations() -> None:
            if eliminated:
                removed: dict[str, list[Any]] = {}
                boolean: list[str] = []
                for var, value in eliminated:
                    if isinstance(value, bool) and self._boolean(var):
                        boolean.append(self.negated(var, value))
                        shown_pairs.add((var, not value))
                    else:
                        removed.setdefault(var, []).append(value)
                alike: dict[tuple[Any, ...], list[str]] = {}
                for var, values in removed.items():
                    alike.setdefault(tuple(values), []).append(var)
                details = boolean + [
                    self.say(
                        "generic.cannot_be",
                        where=compress(variables, self.say),
                        values=self.say.join([self.value_word(value) for value in values], "or"),
                    )
                    for values, variables in alike.items()
                ]
                shown.append(
                    self.say(
                        "generic.trail_place",
                        placement=self.say.join(details),
                        sources=self.names(elimination_sources),
                    )
                )
                eliminated.clear()

        for j in needed:
            inner = step.trail[j]
            if j == 0 or inner.var not in self.visible:
                continue
            if not inner.asserted:
                if inner.sources and not all(source in self.domains for source in inner.sources):
                    if inner.sources != elimination_sources:
                        flush_eliminations()
                        elimination_sources = inner.sources
                    negation = (inner.var, inner.value)
                    if negation not in eliminated:
                        eliminated.append(negation)
                continue
            flush_eliminations()
            option = self.placed(inner.var, inner.value)
            if (inner.var, inner.value) in shown_pairs:
                continue
            shown_pairs.add((inner.var, inner.value))
            if inner.sources and not all(source in self.domains for source in inner.sources):
                shown.append(
                    self.say(
                        "generic.trail_place",
                        placement=option,
                        sources=self.names(inner.sources),
                    )
                )
            else:
                shown.append(self.say("generic.trail_only", placement=option))
        flush_eliminations()
        if premise := self._comparison_premise(step, inference.before, broken, needed):
            shown.append(premise)
        options = self._relation_options(step, inference.before, needed)
        if broken is None:
            breaks = self.say("generic.breaks_unknown")
        elif options is not None and options[1]:
            breaks = self.say("generic.breaks_empty", cells=options[0], source=self.names([broken]))
        elif options is not None:
            breaks = self.say(
                "generic.breaks_relation",
                options=options[0],
                source=self.names([broken]),
            )
        else:
            breaks = self.say("generic.breaks", source=self.names([broken]))
        assumed = self.placed(step.var, step.value)
        refuted = self.negated(step.var, step.value)
        if isinstance(step.value, bool) and self._boolean(step.var):
            self.told.add((step.var, not step.value))
        if not shown:
            return self.say(
                "generic.what_if_direct", assumed=assumed, breaks=breaks, refuted=refuted
            )
        return self.say(
            "generic.what_if",
            assumed=assumed,
            trail="; ".join(shown),
            breaks=breaks,
            refuted=refuted,
        )

    def _comparison_premise(
        self, step: Step, before: Model, broken: str | None, needed: Sequence[int]
    ) -> str | None:
        relation = next((item for item in self.model.relations if item.name == broken), None)
        if relation is None:
            return None
        for variable in relation.variables:
            pairs = self.comparisons.get(variable)
            if not pairs:
                continue
            names = {variable, *(cell for pair in pairs for cell in pair)}
            values = {
                name: {before.value_of(literal) for literal in before.options(name)}
                for name in names
            }
            for index in needed:
                item = step.trail[index]
                if item.var in values:
                    if item.asserted:
                        values[item.var] = {item.value}
                    else:
                        values[item.var].discard(item.value)
            if values[variable] != {False}:
                continue
            equal = []
            for left, right in pairs:
                if len(values[left]) != 1 or values[left] != values[right]:
                    break
                (value,) = values[left]
                equal.append(self.placed(left, value, self.say.join([left, right])))
            else:
                return self.say("generic.compared_equal", pairs=self.say.join(equal))
        return None

    def _note_pruned(self, rule: str, step: Step) -> None:
        """Remember a value a count clue took silently, to cite it at the last option."""
        if rule != "single" or step.asserted or step.placing is not None:
            return
        if step.var not in self.visible or self._boolean(step.var):
            return
        source = next(
            (
                name
                for name in step.sources
                if name not in self.domains
                and (constraint := self.constraints.get(name)) is not None
                and constraint.kind is Kind.COUNT
            ),
            None,
        )
        if source is not None:
            values = self.pruned.setdefault(step.var, {}).setdefault(source, [])
            if step.value not in values:
                values.append(step.value)

    def clue_list(self, clues: Sequence[str]) -> str:
        """Clue sentences joined by semicolons, "Given" lowercased after the first."""
        given = self.say(
            "generic.clue_with_candidates", candidates="", sources="", conclusion=""
        ).split()[0]
        return "; ".join(
            clue[:1].lower() + clue[1:] if index and clue.startswith(given + " ") else clue
            for index, clue in enumerate(clues)
        )

    # --- the whole story ---------------------------------------------------

    def tell(self, start: Model, groups: Sequence[Episode], solved: bool) -> Explanation:
        paragraphs: list[str] = []
        pending: list[Inference] = []
        clues: list[str] = []
        history: list[Step] = list(start.log)
        last_chain: Inference | None = None
        chains: list[Inference] = []

        def flush(final: bool) -> None:
            texts = self.singles(pending, history)
            pending.clear()
            if clues and (texts or final or len(clues) >= SHOWN_CLUES):
                paragraphs.append(self.say("generic.clues", items=self.clue_list(clues)))
                clues.clear()
            paragraphs.extend(texts)

        for group in groups:
            move = group.pattern.move
            if group.pattern.rule == "single":
                pending.append(group.pattern)
            elif move is not None and move.rule in ("count", "relations"):
                flush(False)
                conclusion = self.conclusion(group.pattern.steps) or self.say("generic.internal")
                candidates = (
                    self._relation_premises(group.pattern) if move.rule == "relations" else None
                )
                repeated_count = False
                if move.rule == "count":
                    evidence = [
                        self._count_single_support(
                            group.pattern.before,
                            step.var,
                            step.value if step.asserted else not step.value,
                            move.sources,
                        )
                        for step in group.pattern.steps
                        if step.placing is None
                        and step.var in self.visible
                        and isinstance(step.value, bool)
                    ]
                    if (
                        evidence
                        and evidence[0] is not None
                        and all(e == evidence[0] for e in evidence)
                    ):
                        if evidence[0] not in self.explained_counts:
                            candidates = self._count_facts(evidence[0])
                        else:
                            repeated_count = True
                        self.explained_counts.add(evidence[0])
                if candidates:
                    clues.append(
                        self.say(
                            "generic.clue_with_candidates",
                            candidates=candidates,
                            sources=self.names(move.sources),
                            conclusion=conclusion,
                        )
                    )
                else:
                    clues.append(
                        self.say(
                            "generic.clue_count_again" if repeated_count else "generic.clue",
                            sources=self.names(move.sources),
                            conclusion=conclusion,
                        )
                    )
                pending.extend(group.consequences)
            else:
                flush(False)
                if clues:
                    paragraphs.append(self.say("generic.clues", items=self.clue_list(clues)))
                    clues.clear()
                continuation = (
                    self._chain_continuation(group.pattern, last_chain)
                    if move is not None and move.rule == "chains" and last_chain is not None
                    else None
                )
                if continuation is not None and paragraphs:
                    paragraphs[-1] += f" {continuation}"
                else:
                    reused = (
                        self._chain_reused(group.pattern, chains)
                        if move is not None and move.rule == "chains"
                        else None
                    )
                    paragraphs.append(reused or self.pattern(group.pattern, history))
                pending.extend(group.consequences)
            last_chain = (
                group.pattern
                if move is not None and move.rule == "chains" and not group.consequences
                else None
            )
            if move is not None and move.rule == "chains":
                chains.append(group.pattern)
            for inference in (group.pattern, *group.consequences):
                for step in inference.steps:
                    self._note_pruned(inference.rule, step)
                    if step.placing is not None and not step.asserted:
                        count_source = next(
                            (
                                source
                                for source in step.sources
                                if (constraint := self.constraints.get(source)) is not None
                                and constraint.kind is Kind.COUNT
                            ),
                            None,
                        )
                        self.lost.setdefault(
                            (step.var, step.value),
                            LostCause(source=count_source)
                            if count_source is not None
                            else LostCause(
                                placement=step.placing,
                                rule=next(
                                    (
                                        constraint.family or constraint.name
                                        for source in step.sources
                                        if step.placing in self.support_words
                                        and (constraint := self.constraints.get(source)) is not None
                                        and constraint.kind is Kind.AT_MOST_ONE
                                    ),
                                    None,
                                ),
                            ),
                        )
                history.extend(inference.steps)
        flush(True)
        if not solved:
            paragraphs.append(self.say("generic.stalled"))
        elif not paragraphs:
            paragraphs.append(self.say("generic.givens_complete"))
        return Explanation(tuple(paragraphs), solved)


def thin(
    start: Model,
    moves: Sequence[Move],
    budget: int = MAX_REPLAYS,
    *,
    required_values: Mapping[str, Any] | None = None,
) -> list[Move]:
    """Drop as many moves as still solve the puzzle, hardest rules first, in at most
    `budget` replays.

    `proof.shortest` tries moves one at a time, which takes minutes when a
    puzzle fires hundreds of small clue deductions. This tries large blocks of
    one rule first and halves them, so the many unneeded clue firings usually
    go in a few replays. The budget counts replays, not seconds, so the same
    puzzle always gets the same story. `required_values` also preserves facts
    about hidden variables, such as a mystery's deduced culprit.
    """
    kept = list(moves)
    replays = 0
    for rule in HARDEST_FIRST:
        size = len([m for m in kept if m.rule == rule])
        while size:
            mine = [m for m in kept if m.rule == rule][::-1]
            for i in range(0, len(mine), size):
                if replays >= budget:
                    return kept
                block = {id(m) for m in mine[i : i + size]}
                fewer = [m for m in kept if id(m) not in block]
                replays += 1
                result = replay(start, fewer)
                if result.solution() is not None and all(
                    result.chosen(var) == value for var, value in (required_values or {}).items()
                ):
                    kept = fewer
            size //= 2
    return kept


def explain(
    text: str,
    start: Model,
    fired: Sequence[tuple[str, Sequence[Step]]],
    source_words: Mapping[str, str] | None = None,
    kind: str | None = None,
    hidden_words: Mapping[tuple[str, Any], str] | None = None,
    value_words: Mapping[Any, str] | None = None,
    comparisons: Mapping[str, tuple[tuple[str, str], ...]] | None = None,
    support_words: Mapping[tuple[str, Any], str] | None = None,
) -> Explanation:
    """Explain a solve of any compiled model from its rule firings, shortest proof first.

    `start` is the compiled model before solving and `fired` what the solver
    reported, rule by rule. `text` gives the puzzle's language, and `source_words`
    maps a constraint name to how its clue reads. `kind` names the puzzle family, so
    a yes/no cell can be told in its own words ("r2c3 = bulb") where `story` has them.
    `hidden_words` gives the sentence for a hidden helper taking a value, so a step
    that settles one reads as a fact ("Dirk and Ada are together"). `value_words`
    translates model values such as zero-based coordinates into player-facing names.
    `comparisons` maps a hidden comparison state to its corresponding visible cell pairs.
    `support_words` gives a player-facing premise for a hidden, independently known fact.
    """
    moves = [move for rule, steps in fired if (move := Move.of(rule, steps)) is not None]
    if replay(start, moves).solution() is not None:
        moves = thin(start, moves)
    result, groups = episodes(start, moves)
    narrator = Narrator(
        start,
        Wording.read(text),
        source_words,
        kind,
        hidden_words,
        value_words,
        comparisons,
        support_words,
    )
    return narrator.tell(start, groups, result.solution() is not None)
