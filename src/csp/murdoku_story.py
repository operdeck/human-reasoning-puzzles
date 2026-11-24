"""Murdoku explanations from expression origins and the generic engine's proof."""

from collections.abc import Iterable, Sequence
from dataclasses import replace
from itertools import combinations, product
from typing import Any

from . import generic_story
from .core import Constraint, Kind, Model, Solver, Step
from .murdoku import (
    POPULATION_FAMILY,
    Board,
    CellMark,
    Square,
    board_rules,
    mark_occupant_name,
    occupant_condition_sources,
    steps_between,
)
from .murdoku_eval import grounded_dependencies, holds_grounded
from .murdoku_expression_file import load_expression_board
from .murdoku_expression_words import ExpressionWords, only_on
from .murdoku_lang import (
    Atom,
    Count,
    Filter,
    Integer,
    Name,
    NumberComparison,
    Quantified,
    Statement,
    Token,
)
from .murdoku_lower import ExpressionCompilation, compile_statements_with_origins
from .proof import Episode, Inference, Move, episodes, essential, replay
from .story import MAX_LISTED, PHRASES, Places, Wording, _cap, presentation_reveal

MAX_CANDIDATE_BOUND_LINES = 4


class _Narrator(generic_story.Narrator):
    def __init__(
        self, text: str, board: Board, compilation: ExpressionCompilation, numbered: bool
    ) -> None:
        say = Wording.read(text).for_people(board.people)
        if not numbered:
            say = say.unnumbered()
        super().__init__(compilation.model, say)
        self.board = board
        self.numbered = numbered
        self.compilation = compilation
        self.places = Places(board, say)
        self.options = {person: set(board.free) for person in board.people}
        self.roles = {
            board.role_variable(person, role.name): (person, role.name)
            for person in board.people
            for role in board.roles
        }
        self.visible = set(board.people) | self.roles.keys()
        self.told_mark_counts: set[str] = set()
        self.spoken_placements: set[tuple[str, Square]] = set()
        self.spoken_rule_origins: set[str] = set()
        self.direct_clue_origins: set[str] = set()
        self.told_lines: set[tuple[str, str, int]] = set()
        self.told_line_exclusion_rule = False
        self.told_reservations: set[tuple[str, str, int]] = set()
        self.told_count_squares: set[tuple[str, frozenset[Square]]] = set()
        self.told_occupied_squares: set[Square] = set()
        self.told_area_exclusions: set[tuple[str, str]] = set()
        self.told_bounds: dict[str, dict[str, frozenset[int]]] = {}
        self.sole_marks = {
            formula.left.operand.target.token.text.removeprefix("mark:")
            for origin in compilation.origins
            if isinstance(formula := origin.statement.formula, NumberComparison)
            and formula.operator.text == "="
            and isinstance(formula.right, Integer)
            and formula.right.value.text == "1"
            and isinstance(formula.left, Count)
            and isinstance(formula.left.operand, Filter)
            and isinstance(formula.left.operand.source, Name)
            and formula.left.operand.source.token.text == "people"
            and formula.left.operand.operator.text == "on"
            and formula.left.operand.measure is None
            and isinstance(formula.left.operand.target, Name)
            and formula.left.operand.target.token.text.startswith("mark:")
        }
        self.mark_sources: dict[str, tuple[CellMark, str]] = {}
        self.mark_triggers: dict[str, tuple[CellMark, str]] = {}
        for mark in board.marks:
            if mark.occupant_condition is None:
                continue
            for region in {board.region_of(square) for square in mark.cells}:
                sources = occupant_condition_sources(
                    mark_occupant_name(mark, board.region_names[region])
                )
                self.mark_triggers[sources["trigger"]] = mark, region
                for source in sources.values():
                    self.mark_sources[source] = mark, region
                    self.source_words[source] = say(
                        f"count.mark_occupant.{mark.occupant_condition}",
                        mark=say.words.get(mark.name, mark.name.replace("_", " ")),
                        where=self.places.region(board.region_names[region]),
                    )
        self.source_variables = {
            constraint.name: {
                self.model.var_of(literal)
                for literal in (
                    *constraint.literals,
                    *((constraint.reified_by,) if constraint.reified_by is not None else ()),
                )
            }
            for constraint in self.model.constraints
        }
        self.source_variables.update(
            {relation.name: set(relation.variables) for relation in self.model.relations}
        )
        if not numbered:
            for specification in board.roles:
                if specification.eligible_people is None:
                    continue
                for person in board.people:
                    if person not in specification.eligible_people:
                        self.told.add((board.role_variable(person, specification.name), False))
                    elif specification.allowed_counts == {len(specification.eligible_people)}:
                        self.told.add((board.role_variable(person, specification.name), True))
        words = ExpressionWords.read(board, text)
        population_words = {
            origin.label: say(
                f"clue.{condition.kind}" + ("_tie" if len(condition.regions) > 1 else ""),
                areas=say.join(sorted(board.region_names[region] for region in condition.regions)),
            )
            for origin, condition in compilation.population_conditions
            if origin.statement.wording is None
            and not any(
                key.startswith(
                    "idiom.most_populated"
                    if condition.kind == "busiest_area"
                    else "idiom.least_populated"
                )
                for key in words.phrases
            )
        }
        self.statements = {}
        self.source_origins: dict[str, tuple[str, ...]] = {
            origin.label: (origin.label,) for origin in compilation.origins
        }
        self.clue_origins = {
            origin.label for origin in compilation.origins if origin.kind == "clue"
        }
        for origin in compilation.origins:
            label = say(f"expression.{origin.kind}", number=origin.number)
            statement = (
                population_words[origin.label]
                if origin.label in population_words
                else words.statement(origin.statement).rstrip(".")
            )
            self.source_words[origin.label] = f"{label}: {statement}" if numbered else statement
            self.statements[origin.label] = statement + (
                f" ({origin.number})" if numbered and origin.kind == "clue" else ""
            )
        self.population_levels = {
            constraint.name: (constraint, *level)
            for constraint in compilation.model.constraints
            if (level := self._population_level(constraint)) is not None
        }
        self.population_variables = {}
        self.told_population_limits: set[tuple[str, int]] = set()
        self.population_bounds: dict[str, int] = {}
        self.told_empty_regions: set[str] = set()
        for constraint, region, minimum in self.population_levels.values():
            literal = constraint.reified_by
            assert literal is not None
            self.population_variables[self.model.var_of(literal)] = (literal, region, minimum)
        for index, origins in compilation.constraint_origins.items():
            name = compilation.model.constraints[index].name
            self.source_origins[name] = tuple(origin.label for origin in origins)
            self.source_words[name] = say.join(
                [self.source_words[origin.label] for origin in origins]
            )
        for index, origins in compilation.relation_origins.items():
            name = compilation.model.relations[index].name
            self.source_origins[name] = tuple(origin.label for origin in origins)
            self.source_words[name] = say.join(
                [self.source_words[origin.label] for origin in origins]
            )
        for rule in board_rules(board):
            kind, value = rule.about
            key = {"person": "person", "square": "square", "row": "row", "col": "column"}[kind]
            if kind in {"row", "col"} and rule.kind is Kind.EXACTLY_ONE:
                key += "_exact"
            wording = say(
                f"expression.{key}",
                person=say.words.get(value, value) if kind == "person" else "",
                square=self.places.square(value) if kind == "square" else "",
            )
            self.source_words[rule.name] = wording
            if kind != "person":
                self.source_words[rule.family] = say(f"expression.{key}", square="", person="")
        self.exact_lines = {
            (kind, index)
            for rule in board_rules(board)
            if rule.kind is Kind.EXACTLY_ONE
            for kind, index in [rule.about]
            if kind in {"row", "col"}
        }
        self.board_sources = {rule.name: rule.about for rule in board_rules(board)}
        for variable, (person, role) in self.roles.items():
            name = say.words.get(role, role)
            self.source_words[
                compilation.model.constraints[compilation.model.domain_of(variable)].name
            ] = say("expression.role_state", person=person, role=name)
            self.source_words[f"{person} not eligible for {role}"] = say(
                "expression.role_eligibility"
            )
        for specification in board.roles:
            self.source_words[f"role {specification.name} cardinality"] = say(
                "expression.role_count",
                role=say.words.get(specification.name, specification.name),
                counts=say.join(
                    [str(count) for count in sorted(specification.allowed_counts)], "or"
                ),
            )
            if specification.different_regions:
                for first, second in combinations(board.people, 2):
                    self.source_words[
                        f"{first} and {second} {specification.name} in different regions"
                    ] = say(
                        "rule.role_separation",
                        a=first,
                        b=second,
                        role=say.words.get(specification.name, specification.name),
                    )

    def _because(self, sources: Sequence[str], conclusion: str) -> str:
        useful_sources = [source for source in sources if source not in self.domains]
        if useful_sources:
            sources = useful_sources
        sources = [
            source
            for source in sources
            if not (labels := self.source_origins.get(source, ()))
            or any(
                self.statements[label].casefold() not in conclusion.casefold() for label in labels
            )
        ]
        if not sources:
            return _cap(conclusion)
        origins = {origin for source in sources for origin in self.source_origins.get(source, ())}
        if (
            origins
            and all(source in self.source_origins for source in sources)
            and conclusion.startswith(self._origin_references(origins) + "; ")
        ):
            return _cap(conclusion)
        if (
            len(origins) == 1
            and origins <= self.clue_origins
            and all(source in self.source_origins for source in sources)
            and "expression.by" not in self.say.phrases
        ):
            (origin,) = origins
            statement = self.statements[origin]
            if statement.casefold() in conclusion.casefold():
                return conclusion
            return f"{_cap(statement)}, {self.say('so')} {conclusion}."
        for key in ("murdoku.person_single_explained", "murdoku.person_single_evidence"):
            template = self.say.phrases.get(key) or PHRASES[self.say.language][key]
            if conclusion.startswith(template.split(" ", 1)[0] + " "):
                conclusion = conclusion[0].lower() + conclusion[1:]
                break
        return self.say("expression.by", sources=self.names(sources), conclusion=conclusion)

    def _direct(
        self, sources: tuple[str, ...], steps: Sequence[Step], open_squares: set[Square]
    ) -> str | None:
        if len(sources) != 1:
            return None
        origin = next((item for item in self.compilation.origins if item.label == sources[0]), None)
        if origin is None or origin.kind != "clue":
            return None
        location = origin.statement
        if only := only_on(origin.statement.formula, self.board.people):
            owner, target = only
            location = Statement(
                Atom(owner, Token("on", owner.token.line, owner.token.column), target)
            )
        dependencies = grounded_dependencies(self.board, location)
        if dependencies is None or len(dependencies) != 1:
            return None
        (person,) = dependencies
        own = [step for step in steps if step.var == person]
        if not own:
            return None
        previous = set(self.options[person])
        already_told = set(self.told)
        reservations = set(self.told_reservations)
        line_rule = self.told_line_exclusion_rule
        self.conclusion(own, include_marks=False)
        self.told_reservations = reservations
        self.told_line_exclusion_rule = line_rule
        squares = self.options[person]
        if not squares:
            return None
        clue = _cap(self.statements[origin.label])
        self.direct_clue_origins.add(origin.label)
        region = self.places.common_region(squares)
        previous_region = self.places.common_region(previous)
        line = self.places.common_line(squares) if len(squares) > 1 else None
        line_where = self.say("in", what=self.places.line(*line)) if line else None
        where: str | None
        if len(squares) == 1:
            square = next(iter(squares))
            where = f"**{self.placed(person, square)}**"
            self.spoken_placements.add((person, square))
            if region and region != previous_region and region not in clue:
                where = f"**{region}**: {where}"
            self.told.add((person, square))
            open_squares.difference_update(
                {cell for cell in open_squares if cell.row == square.row or cell.col == square.col}
            )
        else:
            where = region or line_where or self.places.where(squares, self.places.free)
            if where and (where in clue or where == previous_region):
                where = ""
            if where:
                where = f"**{where}**"
        suffix = f": {where}" if where else ""
        if line:
            kind, index = line
            formula = origin.statement.formula
            explicit = (
                isinstance(formula, Atom)
                and formula.operator.text == "in"
                and isinstance(formula.target, Name)
                and formula.target.token.text.startswith("rows:" if kind == "row" else "columns:")
            )
            line_squares = {
                cell for cell in open_squares if (cell.row if kind == "row" else cell.col) == index
            }
            candidates = {
                cell
                for cell in previous & open_squares
                if holds_grounded(location, self.board, {person: cell}, dependencies)
            }
            if (region is None or explicit) and candidates and candidates <= line_squares:
                crossed = line_squares - candidates
                if crossed:
                    instruction = self.say(
                        "cross_out.one" if len(crossed) == 1 else "cross_out.many",
                        n=self.say.number(len(crossed)),
                        line=self.say(f"cross_out.{kind}"),
                        squares=self.places.squares(crossed, "and"),
                    )
                    suffix += f", {self.say('so')} **{instruction}**"
                    open_squares.difference_update(crossed)
        said = f"{clue}{suffix}."
        if isinstance(location.formula, Atom):
            detail = self._beside_different_area(location.formula, previous - squares)
            if detail:
                said += f" {detail}."
        if len(squares) == 1:
            (square,) = squares
            if (person, square) not in already_told and (
                meaning := self._mark_placement(person, square)
            ):
                said += f" {meaning}."
        other = self.conclusion(step for step in steps if step.var != person)
        if other:
            said += " " + self._because(sources, other)
        return said

    def _shared_rule_exclusions(
        self, sources: tuple[str, ...], steps: Sequence[Step]
    ) -> str | None:
        if len(sources) != 1 or len({step.var for step in steps}) < 3:
            return None
        origins = set(self.source_origins.get(sources[0], ()))
        if not any(
            origin.kind == "rule" and origin.label in origins for origin in self.compilation.origins
        ):
            return None
        if any(
            step.asserted or step.var not in self.board.people or not isinstance(step.value, Square)
            for step in steps
        ):
            return None
        by_person: dict[str, set[Square]] = {}
        for step in steps:
            by_person.setdefault(step.var, set()).add(step.value)
        squares = next(iter(by_person.values()))
        if not squares or any(cells != squares for cells in by_person.values()):
            return None
        remaining = [person for person in self.board.people if person not in by_person]
        return (
            self.say(
                "murdoku.shared_rule_exclusions_none"
                if not remaining
                else (
                    "murdoku.shared_rule_exclusions_one"
                    if len(remaining) == 1
                    else "murdoku.shared_rule_exclusions_some"
                ),
                source=self.names(sources),
                people=self.say.join(remaining),
                squares=self.say.join([self.places.square(square) for square in sorted(squares)]),
            )
            + "."
        )

    def _population_level(self, constraint: Constraint) -> tuple[str, int] | None:
        if (
            constraint.kind is not Kind.COUNT
            or constraint.family != POPULATION_FAMILY
            or constraint.reified_by is None
            or not constraint.allowed_counts
        ):
            return None
        minimum = min(constraint.allowed_counts)
        if minimum < 1 or constraint.allowed_counts != frozenset(
            range(minimum, len(constraint.literals) + 1)
        ):
            return None
        regions = set()
        for literal in constraint.literals:
            square = self.model.value_of(literal)
            if self.model.var_of(literal) not in self.board.people or not isinstance(
                square, Square
            ):
                return None
            regions.add(self.board.region_of(square))
        return (regions.pop(), minimum) if len(regions) == 1 else None

    def _population_evidence(self, levels: Sequence[tuple[str, int]]) -> list[str] | None:
        sentences = []
        known: dict[str, int] = {}
        pending = []
        for region, count in levels:
            people = [
                person
                for person, cells in self.options.items()
                if cells and all(self.board.region_of(cell) == region for cell in cells)
            ]
            if len(people) < count:
                pending.append((region, count))
                continue
            sentences.append(
                _cap(
                    self.say(
                        "count.population_person" if count == 1 else "count.population_people",
                        people=self.say.join(people[:count]),
                        where=self.places.region(self.board.region_names[region]),
                        count=self.say.number(count),
                    )
                )
                + "."
            )
            known[region] = count
        while pending:
            for region, count in pending:
                comparison = next(
                    (
                        origin
                        for origin, condition in self.compilation.population_conditions
                        for other, lower in known.items()
                        if count == lower + 1
                        and (
                            (
                                condition.kind == "busiest_area"
                                and region in condition.regions
                                and other not in condition.regions
                            )
                            or (
                                condition.kind == "quietest_area"
                                and other in condition.regions
                                and region not in condition.regions
                            )
                        )
                    ),
                    None,
                )
                if comparison is None:
                    continue
                minimum = self.say(
                    "count.population_minimum",
                    count=self.say.number(count),
                    where=self.places.region(self.board.region_names[region]),
                )
                sentences.append(
                    f"{_cap(self.statements[comparison.label])}, {self.say('so')} **{minimum}**."
                )
                known[region] = count
                pending.remove((region, count))
                break
            else:
                return None
        return sentences

    def _refuted_populations(self, steps: Iterable[Step]) -> Iterable[tuple[Step, str, int]]:
        for step in steps:
            if step.var not in self.population_variables:
                continue
            literal, region, minimum = self.population_variables[step.var]
            active = (step.value == self.model.value_of(literal)) == step.asserted
            if not active:
                yield step, region, minimum

    def _only_removes(self, steps: Iterable[Step], regions: set[str]) -> bool:
        return all(
            step.var not in self.visible
            or (
                step.var in self.options
                and not step.asserted
                and isinstance(step.value, Square)
                and self.board.region_of(step.value) in regions
            )
            for step in steps
        )

    def _population_full(self, inference: Inference) -> str | None:
        """Explain a refuted nonempty area using the floors that exhaust all people."""
        for step, region, minimum in self._refuted_populations(inference.steps):
            if minimum != 1 or not step.sources:
                continue
            levels = [
                (other_region, count)
                for name in step.sources[1:]
                if name in self.population_levels
                for _, other_region, count in [self.population_levels[name]]
            ]
            regions = {other_region for other_region, _ in levels}
            total = sum(count for _, count in levels)
            if (
                len(levels) < 2
                or len(regions) != len(levels)
                or region in regions
                or total != len(self.board.people)
                or not self._only_removes(inference.steps, {region})
            ):
                continue
            empty = self.say(
                "global_count.area_empty",
                where=self.places.region(self.board.region_names[region]),
            )
            if (evidence := self._population_evidence(levels)) is not None:
                reason = " ".join(
                    [*evidence, _cap(self.say("count.population_all", n=self.say.number(total)))]
                )
            else:
                reason = _cap(
                    self.say(
                        "count.population_full",
                        areas=self.say.join(
                            [
                                self.say(
                                    "count.population_reason_one"
                                    if count == 1
                                    else "count.population_reason",
                                    area=self.board.region_names[other_region],
                                    count=self.say.number(count),
                                )
                                for other_region, count in levels
                            ]
                        ),
                        n=self.say.number(total),
                    )
                )
            empty_cells = {cell for cell in self.board.free if self.board.region_of(cell) == region}
            for cells in self.options.values():
                cells.difference_update(empty_cells)
            self.told_empty_regions.add(region)
            return f"{reason}, {self.say('so')} **{empty}**."
        return None

    def _relation_with_candidates(self, inference: Inference, conclusion: str) -> str | None:
        move = inference.move
        if move is None or not move.sources:
            return None
        candidates = self._relation_candidate_summary(inference)
        if candidates is None:
            return None
        return self.say(
            "generic.clues",
            items=self.say(
                "murdoku.relation_with_candidates",
                candidates=candidates,
                sources=self.names(move.sources),
                conclusion=conclusion,
            ),
        )

    def _furthest_exclusion(self, inference: Inference, conclusion: str) -> str | None:
        move = inference.move
        if move is None or move.rule != "relations" or len(move.sources) != 1:
            return None
        labels = self.source_origins.get(move.sources[0], ())
        origin = next(
            (
                item
                for item in self.compilation.origins
                if item.label in labels
                and item.kind == "clue"
                and isinstance(item.statement.formula, Atom)
                and item.statement.formula.operator.text == "dir:furthest"
                and item.statement.formula.measure is None
                and isinstance(item.statement.formula.subject, Name)
                and isinstance(item.statement.formula.target, Name)
            ),
            None,
        )
        if origin is None:
            return None
        formula = origin.statement.formula
        assert isinstance(formula, Atom)
        if not isinstance(formula.subject, Name) or not isinstance(formula.target, Name):
            return None
        subject = formula.subject.token.text
        target = formula.target.token.text
        relation = next(
            (item for item in self.model.relations if item.name == move.sources[0]), None
        )
        if relation is None:
            return None
        rivals = [
            person
            for person in relation.variables
            if person in self.board.people and person not in {subject, target}
        ]
        excluded = [
            step.value
            for step in inference.steps
            if step.var == subject and not step.asserted and isinstance(step.value, Square)
        ]
        if len(rivals) != 1 or len(excluded) != 1:
            return None
        rival = rivals[0]
        candidate = excluded[0]

        def squares(person: str) -> list[Square] | None:
            values = [
                inference.before.value_of(literal) for literal in inference.before.options(person)
            ]
            if not values or len(values) > MAX_LISTED + 1:
                return None
            result = [value for value in values if isinstance(value, Square)]
            return result if len(result) == len(values) else None

        target_options = squares(target)
        rival_options = squares(rival)
        if target_options is None or rival_options is None:
            return None

        def distance(first: Square, second: Square) -> int:
            return abs(first.row - second.row) + abs(first.col - second.col)

        if any(
            distance(candidate, other) > distance(position, other)
            for other in target_options
            for position in rival_options
        ):
            return None
        return (
            self.say(
                "murdoku.furthest_exclusion",
                clue=self.names([origin.label]),
                subject=subject,
                candidate=self.places.square(candidate),
                rival=rival,
                rival_squares=self.places.squares(set(rival_options)),
                target=target,
                target_squares=self.places.squares(set(target_options)),
                conclusion=conclusion,
            )
            + "."
        )

    def _population_tied(self, inference: Inference) -> str | None:
        """Prove tied sole occupants using only already announced row/column blockers."""
        announced = {
            person: min(cells)
            for person, cells in self.options.items()
            if len(cells) == 1 and (person, min(cells)) in self.told
        }
        for _, target, minimum in self._refuted_populations(inference.steps):
            if minimum != 2 or (target, minimum) in self.told_population_limits:
                continue
            occupants = [
                person
                for person, square in announced.items()
                if self.board.region_of(square) == target
            ]
            if len(occupants) != 1:
                continue
            (target_person,) = occupants
            for origin, condition in self.compilation.population_conditions:
                if target not in condition.regions:
                    continue
                for source in condition.regions:
                    if source == target or not self._only_removes(
                        inference.steps, {source, target}
                    ):
                        continue
                    people = [
                        person
                        for person, square in announced.items()
                        if self.board.region_of(square) == source
                    ]
                    if len(people) != 1:
                        continue
                    (source_person,) = people
                    source_cells = {
                        square
                        for square in self.board.free
                        if self.board.region_of(square) == source
                    }
                    blockers = self.places.blockers(
                        source_cells - {announced[source_person]}, announced, max_people=3
                    )
                    if not blockers:
                        continue
                    source_where = self.places.region(self.board.region_names[source])
                    target_where = self.places.region(self.board.region_names[target])
                    reason = self.say(
                        "count.population_blocked",
                        blockers=self.say.join(blockers),
                        where=source_where,
                    )
                    source_only = self.say(
                        "count.population_only", who=source_person, where=source_where
                    )
                    target_only = self.say(
                        "count.population_only", who=target_person, where=target_where
                    )
                    for person, cells in self.options.items():
                        cells.difference_update(
                            {
                                square
                                for square in cells
                                if (person != source_person and square in source_cells)
                                or (
                                    person != target_person
                                    and self.board.region_of(square) == target
                                )
                            }
                        )
                    self.told_population_limits.update({(source, 2), (target, 2)})
                    return (
                        f"{_cap(reason)}, {self.say('so')} **{source_only}**. "
                        f"{_cap(self.statements[origin.label])}, "
                        f"{self.say('so')} **{target_only}**."
                    )
        return None

    def _population_ceiling(self, inference: Inference) -> str | None:
        for step in inference.steps:
            for name in step.sources:
                if name not in self.population_levels:
                    continue
                _, region, minimum = self.population_levels[name]
                maximum = self.population_bounds.get(region)
                if (
                    maximum is None
                    or maximum != minimum - 1
                    or not self._only_removes(inference.steps, {region})
                    or not any(item.var in self.visible for item in inference.steps)
                ):
                    continue
                conclusion = self.conclusion(inference.steps)
                if conclusion is None:
                    continue
                reason = self.say(
                    "count.population_at_most_zero"
                    if maximum == 0
                    else "count.population_at_most_one"
                    if maximum == 1
                    else "count.population_at_most",
                    where=self.places.region(self.board.region_names[region]),
                    count=self.say.number(maximum),
                )
                if maximum == 0:
                    self.told_empty_regions.add(region)
                return f"{_cap(reason)}, {self.say('so')} {conclusion}."
        return None

    def placed(self, var: str, value: Any, name: str | None = None) -> str:
        if var in self.board.people and isinstance(value, Square):
            return (
                self.say("placed", who=name or var, square=self.places.square(value))
                .removeprefix("**")
                .removesuffix("**")
            )
        if var in self.roles:
            person, role = self.roles[var]
            return self.say(
                "role_has" if value else "role_not",
                who=person,
                role=self.say.words.get(role, role),
            )
        return super().placed(var, value, name)

    def negated(self, var: str, value: Any) -> str:
        if var in self.board.people and isinstance(value, Square):
            return self.say("is_not", who=var, where=self.say("on", what=self.places.square(value)))
        return super().negated(var, value)

    def _mark_placement(self, person: str, square: Square) -> str:
        sentences = []
        for mark in self.board.marks:
            if square not in mark.cells:
                continue
            if mark.occupant_condition is not None:
                sentences.append(
                    self.say(
                        f"mark_placed.{mark.occupant_condition}",
                        who=person,
                        mark=mark.name.replace("_", " "),
                        where=self.places.region(
                            self.board.region_names[self.board.region_of(square)]
                        ),
                    )
                )
            if mark.name in self.sole_marks and mark.name not in self.told_mark_counts:
                self.told_mark_counts.add(mark.name)
                others = self.board.mark_cells([mark.name]) - {square}
                if others:
                    sentences.append(
                        self.say("mark_count_filled", mark=mark.name.replace("_", " "))
                    )
                    for cells in self.options.values():
                        cells.difference_update(others)
        return ". ".join(sentences)

    def conclusion(
        self,
        steps: Iterable[Step],
        *,
        include_marks: bool = True,
        group_candidates: bool = True,
        include_broad_candidates: bool = False,
        omit_origins: frozenset[str] = frozenset(),
        embedded: bool = False,
    ) -> str | None:
        steps = list(steps)
        before = {person: set(cells) for person, cells in self.options.items()}
        placed = set()
        new_placements = {
            step.var: step.value
            for step in steps
            if step.var in self.options
            and step.asserted
            and isinstance(step.value, Square)
            and before[step.var] != {step.value}
        }
        announced = {
            person: square
            for person in self.board.people
            for square in self.board.free
            if (person, square) in self.told
        }
        announced.update(new_placements)
        for step in steps:
            if step.var in self.options:
                if step.asserted:
                    self.options[step.var] = {step.value}
                    placed.add(step.var)
                else:
                    self.options[step.var].discard(step.value)
        placements_said = []
        position_said = []
        position_changes: list[tuple[str, set[Square], set[Square]]] = []
        suppressed = set()
        line_claims: dict[str, dict[str, set[int]]] = {}
        for person, previous in before.items():
            cells = self.options[person]
            if person in placed or cells == previous or not cells:
                continue
            gone = previous - cells
            blockers = self.places.blockers(gone, announced) if group_candidates else None
            if blockers:
                suppressed.add(person)
                if len(cells) == 1 and self._current_single_reason(
                    person, next(iter(cells)), previous, steps, omit_origins
                ):
                    continue
                for blocker, square in announced.items():
                    rows = {
                        cell.row
                        for cell in gone
                        if cell.row == square.row
                        and (blocker, "row", cell.row) not in self.told_lines
                    }
                    columns = {
                        cell.col
                        for cell in gone
                        if cell.col == square.col
                        and (blocker, "col", cell.col) not in self.told_lines
                    }
                    if rows or columns:
                        claim = line_claims.setdefault(blocker, {"row": set(), "col": set()})
                        claim["row"].update(rows)
                        claim["col"].update(columns)
        said = []
        for person, previous in before.items():
            cells = self.options[person]
            if len(cells) == 1 and (person in placed or cells != previous):
                (square,) = cells
                if (person, square) not in self.told:
                    sentence = (
                        self._current_single_reason(person, square, previous, steps, omit_origins)
                        or f"**{self.placed(person, square)}**"
                    )
                    if include_marks and (meaning := self._mark_placement(person, square)):
                        sentence += f". {meaning}"
                    placements_said.append(sentence)
                    self.spoken_placements.add((person, square))
                    self.told.add((person, square))
            elif cells != previous and cells and person not in suppressed:
                line = self.places.common_line(cells)
                if line is not None and line != self.places.common_line(previous):
                    self.told_reservations.add((person, *line))
                    remaining = self.places.describe(person, cells, previous, placing=False)
                    position_said.append(
                        "**"
                        + remaining
                        + "; "
                        + self.say("must_occupy_line", who=person, line=self.places.line(*line))
                        + "; "
                        + self.say("nobody_else_line")
                        + "**"
                    )
                else:
                    position_changes.append((person, cells, previous))
        excluded_areas: dict[str, set[str]] = {}
        for person, previous in before.items():
            current = self.options[person]
            for region in {self.board.region_of(square) for square in previous}:
                area_candidates = {
                    square for square in previous if self.board.region_of(square) == region
                }
                name = self.board.region_names[region]
                if (
                    not area_candidates
                    or any(self.board.region_of(square) == region for square in current)
                    or (person, name) in self.told_area_exclusions
                ):
                    continue
                evidence = {
                    step.value: step
                    for step in steps
                    if step.var == person and not step.asserted and step.value in area_candidates
                }
                if set(evidence) != area_candidates:
                    continue
                labels = {
                    label
                    for step in evidence.values()
                    for source in (*step.sources, *step.scope)
                    for label in self.source_origins.get(source, ())
                    if any(
                        origin.label == label and origin.kind == "clue"
                        for origin in self.compilation.origins
                    )
                }
                if not labels:
                    continue
                excluded_areas.setdefault(person, set()).add(name)
                self.told_area_exclusions.add((person, name))
        area_exclusions = [
            f"**{self.say('is_not', who=person, where=self.places.where_regions(sorted(names)))}**"
            for person, names in excluded_areas.items()
        ]
        for person in line_claims:
            square = announced[person]
            if (person, square) not in self.spoken_placements:
                placements_said.append(f"**{self.placed(person, square)}**")
                self.spoken_placements.add((person, square))
        said.extend(placements_said)
        if line_claims:
            blockers = []
            for person, lines in line_claims.items():
                occupied = [
                    self.places.lines(kind, indices) for kind, indices in lines.items() if indices
                ]
                blockers.append(
                    self.say(
                        "murdoku.line_takes_known",
                        who=person,
                        lines=self.say.join(occupied),
                    )
                )
            claimed_lines = {
                (kind, index)
                for lines in line_claims.values()
                for kind, indices in lines.items()
                for index in indices
            }
            exact = bool(claimed_lines) and claimed_lines <= self.exact_lines
            wording = (
                "line_exclusions_followup"
                if self.told_line_exclusion_rule
                else "line_exclusions_exact"
                if exact
                else "line_exclusions"
            )
            said.append(
                "**"
                + self.say(
                    wording,
                    blockers=self.say.join(blockers),
                )
                + "**"
            )
            self.told_line_exclusion_rule = True
            for person, lines in line_claims.items():
                self.told_lines.update(
                    (person, kind, index) for kind, indices in lines.items() for index in indices
                )
        grouped: dict[tuple[str, frozenset[int]], list[str]] = {}
        broad_exclusions: dict[frozenset[Square], list[str]] = {}
        individual = []
        for person, cells, previous in position_changes:
            bounds = []
            existing_bound = False
            if group_candidates and len(cells) > MAX_LISTED + 1:
                for kind in ("row", "col"):
                    indices = frozenset(
                        square.row if kind == "row" else square.col for square in cells
                    )
                    previous_bound = self.told_bounds.get(person, {}).get(kind)
                    if len(indices) <= MAX_CANDIDATE_BOUND_LINES and indices != previous_bound:
                        bounds.append((kind, indices))
                    elif indices == previous_bound:
                        existing_bound = True
            if bounds:
                kind, indices = min(bounds, key=lambda item: len(item[1]))
                grouped.setdefault((kind, indices), []).append(person)
            elif (
                not existing_bound
                and group_candidates
                and include_broad_candidates
                and len(cells) > MAX_LISTED + 1
                and self.places.where(cells, previous) is None
                and self.places.where(previous - cells, previous, most=1) is None
            ):
                broad_exclusions.setdefault(frozenset(previous - cells), []).append(person)
            elif not existing_bound and (len(cells) <= MAX_LISTED or include_broad_candidates):
                individual.append((person, cells, previous))
        for (kind, indices), people in grouped.items():
            bound = self.say(
                "candidate_bound",
                people=self.say.join(people),
                lines=self.places.lines(kind, indices),
            )
            if embedded:
                bound = bound[0].lower() + bound[1:]
            said.append("**" + bound + "**")
            for person in people:
                self.told_bounds.setdefault(person, {})[kind] = indices
        for person, cells, previous in individual:
            said.append("**" + self.places.describe(person, cells, previous, placing=False) + "**")
        for excluded_squares, people in broad_exclusions.items():
            if len(people) == 1:
                person = people[0]
                said.append(
                    "**"
                    + self.places.describe(
                        person, self.options[person], before[person], placing=False
                    )
                    + "**"
                )
            else:
                said.append(
                    "**"
                    + self.say(
                        "murdoku.group_excluded_squares",
                        people=self.say.join(people),
                        squares=self.places.squares(excluded_squares),
                    )
                    + "**"
                )
        said.extend(position_said)
        role_updates = {
            step.var: step.value if step.asserted else not step.value
            for step in steps
            if step.var in self.roles
            and (step.var, step.value if step.asserted else not step.value) not in self.told
        }
        self.told.update(role_updates.items())
        for role in self.board.roles:
            updates = [
                (variable, value)
                for variable, value in role_updates.items()
                if self.roles[variable][1] == role.name
            ]
            for variable, value in updates:
                if value:
                    said.append(f"**{self.placed(variable, value)}**")
            excluded = [variable for variable, value in updates if not value]
            holders = {
                person
                for variable, (person, name) in self.roles.items()
                if name == role.name and (variable, True) in self.told
            }
            if excluded and "role_not" in self.say.phrases:
                said.extend(f"**{self.placed(variable, False)}**" for variable in excluded)
            elif (
                len(excluded) > 1
                and holders
                and all(
                    (self.board.role_variable(person, role.name), False) in self.told
                    for person in self.board.people
                    if person not in holders
                )
            ):
                said.append(
                    "**"
                    + self.say("role_others", role=self.say.words.get(role.name, role.name))
                    + "**"
                )
            else:
                excluded_people = [self.roles[variable][0] for variable in excluded]
                eligible = next(
                    (
                        specification.eligible_people
                        for specification in self.board.roles
                        if specification.name == role.name
                    ),
                    None,
                )
                if (
                    eligible
                    and len(excluded) > 1
                    and set(excluded_people) == set(self.board.people) - set(eligible)
                ):
                    said.append(
                        "**"
                        + self.say(
                            "role_eligible_only_one"
                            if len(eligible) == 1
                            else "role_eligible_only_many",
                            people=self.say.join(sorted(eligible, key=self.board.people.index)),
                            role=self.say.words.get(role.name, role.name),
                        )
                        + "**"
                    )
                elif len(excluded) > 1:
                    said.append(
                        "**"
                        + self.say(
                            "role_not_many",
                            people=self.say.join(excluded_people),
                            role=self.say.words.get(role.name, role.name),
                        )
                        + "**"
                    )
                else:
                    said.extend(f"**{self.placed(variable, False)}**" for variable in excluded)
        said = [
            "**" + item[2].lower() + item[3:]
            if (index or area_exclusions) and item.startswith(("**Voor ", "**For "))
            else item
            for index, item in enumerate(said)
        ]
        conclusion = self.say.join(said)
        if area_exclusions:
            return self.say.join(area_exclusions) + (f"; {conclusion}" if conclusion else "")
        return conclusion or None

    def _advance_without_conclusion(self, steps: Iterable[Step]) -> None:
        spoken = set(self.spoken_placements)
        reservations = set(self.told_reservations)
        line_rule = self.told_line_exclusion_rule
        self.conclusion(steps)
        self.spoken_placements = spoken
        self.told_reservations = reservations
        self.told_line_exclusion_rule = line_rule

    def _person_case(self, step: Step, history: Sequence[Step]) -> str:
        needed = essential(self.model, history, step)
        parts: list[str] = []
        region = self.board.region_of(step.value)
        for mark in self.board.marks:
            if step.value not in mark.cells or mark.occupant_condition is None:
                continue
            sources = occupant_condition_sources(
                mark_occupant_name(mark, self.board.region_names[region])
            )
            if any(sources["count"] in step.trail[index].sources for index in needed):
                parts.append(
                    self.say(
                        f"mark_case.{mark.occupant_condition}",
                        mark=mark.name.replace("_", " "),
                        who=step.var,
                        where=self.places.region(self.board.region_names[region]),
                    )
                )
        placements: list[str] = []
        seen = {(step.var, step.value)}
        for index in needed:
            inner = step.trail[index]
            pair = inner.var, inner.value
            if index and inner.asserted and inner.var in self.board.people and pair not in seen:
                placements.append(
                    self.say(
                        "also_on" if placements else "then_on",
                        who=inner.var,
                        square=self.places.square(inner.value),
                    )
                )
                seen.add(pair)
        if placements:
            parts.append(self.say.join(placements))
        trial = {person: set(squares) for person, squares in self.options.items()}
        for inner in step.trail:
            if inner.var in trial:
                if inner.asserted:
                    trial[inner.var] = {inner.value}
                else:
                    trial[inner.var].discard(inner.value)
        for source in step.sources:
            kind, index = self.board_sources.get(source, ("", None))
            if kind in {"row", "col"} and not any(
                (square.row if kind == "row" else square.col) == index
                for squares in trial.values()
                for square in squares
            ):
                parts.append(self.say("nobody", line=self.places.line(kind, index)))
                return self.say(
                    "cannot",
                    who=step.var,
                    squares=self.places.square(step.value),
                    chain=", ".join(parts),
                )
        origins = {
            label for source in step.sources for label in self.source_origins.get(source, ())
        }
        broken = [origin for origin in self.compilation.origins if origin.label in origins]
        if len(broken) == 1 and broken[0].kind == "clue":
            parts.append(
                self.say(
                    "breaks_said" if parts else "breaks_said_first",
                    clue=self.statements[broken[0].label],
                )
            )
        else:
            parts.append(
                self.say("generic.breaks", source=self.names(step.sources))
                if step.sources
                else self.say("generic.breaks_unknown")
            )
        return self.say(
            "cannot",
            who=step.var,
            squares=self.places.square(step.value),
            chain=", ".join(parts),
        )

    def _mark_case_deduction(self, inference: Inference, history: Sequence[Step]) -> str | None:
        visible = [step for step in inference.steps if step.var in self.visible]
        if len(visible) != 1 or visible[0].asserted or visible[0].var not in self.board.people:
            return None
        (step,) = visible
        for source in step.sources:
            if source not in self.mark_triggers:
                continue
            mark, region = self.mark_triggers[source]
            candidates = {
                (person, square)
                for person, squares in self.options.items()
                for square in squares & set(mark.cells)
                if self.board.region_of(square) == region
            }
            if candidates != {(step.var, step.value)}:
                continue
            trigger = self.constraints[source].reified_by
            if trigger is None:
                continue
            variable, value = self.model.var_of(trigger), self.model.value_of(trigger)
            for index in range(len(history) - 1, -1, -1):
                refutation = history[index]
                if (
                    refutation.var == variable
                    and refutation.value == value
                    and not refutation.asserted
                    and refutation.rule == "what_if"
                    and any(
                        inner.asserted and (inner.var, inner.value) == (step.var, step.value)
                        for inner in refutation.trail
                    )
                ):
                    return self._person_case(
                        replace(refutation, var=step.var, value=step.value), history[:index]
                    )
        return None

    def _mark_blocked_by_occupant(self, inference: Inference) -> str | None:
        visible = [step for step in inference.steps if step.var in self.visible]
        if not visible or any(step.asserted or step.var not in self.options for step in visible):
            return None
        for source in dict.fromkeys(source for step in visible for source in step.sources):
            if source not in self.mark_sources:
                continue
            mark, region = self.mark_sources[source]
            marked = {square for square in mark.cells if self.board.region_of(square) == region}
            if mark.occupant_condition != "alone" or any(
                step.value not in marked for step in visible
            ):
                continue
            for person, squares in self.options.items():
                if (
                    squares
                    and not squares & marked
                    and all(self.board.region_of(square) == region for square in squares)
                ):
                    return self.say(
                        "mark_blocked.alone",
                        who=person,
                        where=self.places.region(self.board.region_names[region]),
                        mark=mark.name.replace("_", " "),
                    )
        return None

    def _what_if(self, inference: Inference, history: Sequence[Step]) -> str:
        step = next(step for step in inference.steps if step.rule == "what_if")
        broken = next(
            (self.mark_sources[source] for source in step.sources if source in self.mark_sources),
            None,
        )
        if step.var not in self.board.people:
            return super()._what_if(inference, history)
        if broken is None:
            return self._person_case(step, history)
        mark, region = broken
        if mark.occupant_condition != "not_alone":
            return self._person_case(step, history)
        trial = {person: set(cells) for person, cells in self.options.items()}
        for inner in step.trail:
            if inner.var in trial:
                if inner.asserted:
                    trial[inner.var] = {inner.value}
                else:
                    trial[inner.var].discard(inner.value)
        occupants = {
            person
            for person, cells in trial.items()
            if cells
            and all(
                square in mark.cells and self.board.region_of(square) == region for square in cells
            )
        }
        if (
            len(occupants) != 1
            or not all(trial.values())
            or any(
                self.board.region_of(square) == region
                for person, cells in trial.items()
                if person not in occupants
                for square in cells
            )
        ):
            return self._person_case(step, history)
        parts: list[str] = []
        seen: set[tuple[str, Square]] = set()
        for index in essential(self.model, history, step):
            inner = step.trail[index]
            if index and inner.asserted and inner.var in self.board.people:
                pair = inner.var, inner.value
                if pair not in seen:
                    parts.append(
                        self.say("then_on", who=inner.var, square=self.places.square(inner.value))
                    )
                    seen.add(pair)
        companions = [
            person
            for person, cells in self.options.items()
            if person not in occupants
            and any(self.board.region_of(square) == region for square in cells)
        ]
        if len(companions) == 1:
            (companion,) = companions
            elsewhere = {self.board.region_of(square) for square in trial[companion]}
            if len(elsewhere) == 1:
                (other_region,) = elsewhere
                parts.append(
                    self.say(
                        "then_in",
                        who=companion,
                        where=self.places.region(self.board.region_names[other_region]),
                    )
                )
        parts.append(
            self.say(
                "mark_breaks.not_alone",
                mark=mark.name.replace("_", " "),
                where=self.places.region(self.board.region_names[region]),
            )
        )
        return self.say(
            "cannot",
            who=step.var,
            squares=self.places.square(step.value),
            chain=", ".join(parts),
        )

    def _link_reason(self, source: str) -> str:
        kind, value = self.board_sources.get(source, ("", None))
        if kind in ("row", "col"):
            return f" ({self.places.line(kind, value)})"
        origins = set(self.source_origins.get(source, ()))
        labels = [
            self.statements[origin.label]
            for origin in self.compilation.origins
            if origin.label in origins
        ]
        if not labels and source in self.mark_sources:
            labels.append(self.source_words[source])
        return f" ({self.say.join(labels)})" if labels else ""

    def _chain(
        self,
        chain: Sequence[tuple[str, Any]],
        conclusion: str,
        sources: Sequence[str] = (),
        steps: Sequence[Step] = (),
        before: Model | None = None,
    ) -> str:
        if not chain or any(
            person not in self.board.people or not isinstance(square, Square)
            for person, square in chain
        ):
            paragraph = super()._chain(chain, conclusion, sources, steps, before)
            return self._because(sources, paragraph) if sources else paragraph
        first, a = chain[0]
        last, z = chain[-1]
        ends = self.say.join(
            [
                self.say("is", who=person, where=self.say("on", what=self.places.square(square)))
                for person, square in ((first, a), (last, z))
            ],
            "or",
        )
        if len(chain) == 2:
            if sources:
                ends += self._link_reason(sources[0])
            if end_reason := self._chain_end_reason(chain, steps):
                return self.say("generic.chain_either_explained", ends=ends, reason=end_reason)
            return _cap(self.say("chain_either", ends=ends, outcome=conclusion))
        parts = [self.say("chain_if", who=first, square=self.places.square(a))]
        for index, (person, square) in enumerate(chain[1:]):
            key = "chain_on" if index % 2 == 0 else "chain_off"
            source = sources[index] if index < len(sources) else None
            previous = chain[index]
            supported = (
                self._chain_supported(before, source, previous, (person, square))
                if before is not None and source is not None and index % 2 == 0
                else None
            )
            if supported is not None:
                parts.append(supported)
            elif source is not None and source in self.domains and person == previous[0]:
                parts.append(
                    self.say(key, who=person, square=self.places.square(square))
                    + self.say(
                        "murdoku.chain_domain_reason",
                        excluded=self.placed(*previous),
                    )
                )
            else:
                reason = self._link_reason(source) if source is not None else ""
                parts.append(self.say(key, who=person, square=self.places.square(square)) + reason)
        if end_reason := self._chain_end_reason(chain, steps):
            return f"{', '.join(parts)}. " + self.say(
                "generic.chain_either_explained", ends=ends, reason=end_reason
            )
        return f"{', '.join(parts)}. {self.say('chain_so', ends=ends, outcome=conclusion)}"

    def _line_single(self, inference: Inference, history: Sequence[Step] = ()) -> str | None:
        for step in inference.steps:
            if (
                not step.asserted
                or step.var not in self.board.people
                or not isinstance(step.value, Square)
                or (step.var, step.value) in self.spoken_placements
            ):
                continue
            for source in step.sources:
                if source not in self.board_sources:
                    continue
                kind, index = self.board_sources[source]
                if kind not in {"row", "col"} or (kind, index) not in self.exact_lines:
                    continue
                constraint = self.constraints.get(source)
                if constraint is None or constraint.kind is not Kind.EXACTLY_ONE:
                    continue
                live = inference.before.live(constraint.index)
                if (
                    len(live) == 1
                    and inference.before.var_of(live[0]) == step.var
                    and inference.before.value_of(live[0]) == step.value
                ):
                    context, clues = self._line_single_clues(
                        step.var, kind, index, step.value, history, inference.before
                    )
                    paired = self._line_single_consequences(inference, step, kind, index)
                    if paired:
                        if clues:
                            paired = f"{self.say.join(clues)}; {paired[0].lower()}{paired[1:]}"
                        return f"{context}. {paired}" if context else paired
                    if clues:
                        self.spoken_placements.add((step.var, step.value))
                        paragraph = self.say(
                            "murdoku.line_single_with_clues",
                            clues=self.say.join(clues),
                            line=self.places.line(kind, index),
                            placement=f"**{self.placed(step.var, step.value)}**",
                        )
                        return f"{context}. {paragraph}" if context else paragraph
                    self.spoken_placements.add((step.var, step.value))
                    return self.say(
                        "line_single",
                        line=self.places.line(kind, index),
                        placement=f"**{self.placed(step.var, step.value)}**",
                    )
            domain = self.model.constraints[self.model.domain_of(step.var)]
            live = inference.before.live(domain.index)
            if (
                len(live) == 1
                and inference.before.var_of(live[0]) == step.var
                and inference.before.value_of(live[0]) == step.value
            ):
                reason = self._person_single_reason(step, history)
                self.spoken_placements.add((step.var, step.value))
                return (
                    _cap(reason) + "."
                    if reason
                    else self.say(
                        "person_single", placement=f"**{self.placed(step.var, step.value)}**"
                    )
                )
        return None

    def _line_single_consequences(
        self, inference: Inference, placement: Step, kind: str, index: int
    ) -> str | None:
        others: list[tuple[str, Square]] = []
        for person in self.board.people:
            if person == placement.var:
                continue
            before = {
                inference.before.value_of(literal) for literal in inference.before.options(person)
            }
            if len(before) <= 1 or not all(isinstance(square, Square) for square in before):
                continue
            removed = {
                step.value
                for step in inference.steps
                if step.var == person
                and not step.asserted
                and step.placing == (placement.var, placement.value)
            }
            remaining = before - removed
            if len(remaining) == 1:
                (square,) = remaining
                if (person, square) not in self.spoken_placements:
                    others.append((person, square))
        if not others:
            return None
        assert isinstance(placement.value, Square)
        placements = [*others, (placement.var, placement.value)]
        placements.sort(key=lambda pair: self.board.people.index(pair[0]))
        if placements[0][0] == placement.var:
            return None
        self.spoken_placements.update(placements)
        return self.say(
            "murdoku.line_single_consequences",
            line=_cap(self.places.line(kind, index)),
            who=placement.var,
            square=self.places.square(placement.value),
            placements=self.say.join([f"**{self.placed(*pair)}**" for pair in placements]),
        )

    def _person_single_reason(self, step: Step, history: Sequence[Step]) -> str | None:
        initial = {
            self.model.value_of(literal)
            for literal in self.model.options(step.var)
            if isinstance(self.model.value_of(literal), Square)
        }
        if len(initial) <= 1 or step.value not in initial:
            return None

        labels: set[str] = set()
        placement_causes: set[Square] = set()
        placements: dict[str, Square] = {}
        for square in initial - {step.value}:
            evidence = [
                prior
                for prior in history
                if prior.var == step.var and not prior.asserted and prior.value == square
            ]
            recognized = False
            for prior in evidence:
                sources = (*prior.sources, *prior.scope)
                origins = {
                    label for source in sources for label in self.source_origins.get(source, ())
                }
                known_origins = {
                    label
                    for label in origins
                    if any(origin.label == label for origin in self.compilation.origins)
                }
                if known_origins:
                    labels.update(known_origins)
                    recognized = True
                elif (
                    prior.placing is not None
                    and prior.placing[0] in self.board.people
                    and isinstance(prior.placing[1], Square)
                ):
                    placements[prior.placing[0]] = prior.placing[1]
                    placement_causes.add(square)
                    recognized = True
                if recognized:
                    break
            if not recognized:
                return None

        if not labels and not placement_causes:
            return None
        support = self._origin_references(labels) if labels else ""
        if placement_causes:
            blockers = self.places.blockers(
                placement_causes,
                placements,
                max_people=len(placements),
            )
            if blockers is None:
                return None
            support = "; ".join([item for item in (support, *blockers) if item])
        return self.say(
            "murdoku.person_single_evidence",
            support=support,
            who=step.var,
            placement=f"**{self.placed(step.var, step.value)}**",
        )

    def _origin_references(self, labels: set[str]) -> str:
        references = []
        for origin in self.compilation.origins:
            if origin.label not in labels:
                continue
            if self.numbered and origin.label in self.direct_clue_origins:
                reference = self.say(
                    f"expression.{origin.kind}",
                    number=origin.number,
                )
                references.append(f"*{reference}*")
            else:
                references.append(self.statements[origin.label])
        if self.numbered and labels <= self.direct_clue_origins:
            return self.say("murdoku.use_sources", sources=self.say.join(references))
        return "; ".join(
            reference[0].lower() + reference[1:]
            if index and reference.startswith(("The ", "A ", "An ", "De ", "Het ", "Een "))
            else reference
            for index, reference in enumerate(references)
        )

    def _current_single_reason(
        self,
        person: str,
        square: Square,
        previous: set[Square],
        steps: Sequence[Step],
        omit_origins: frozenset[str] = frozenset(),
    ) -> str | None:
        labels: set[str] = set()
        placement_causes: set[Square] = set()
        placements: dict[str, Square] = {}
        for candidate in previous - {square}:
            recognized = False
            for evidence in steps:
                if evidence.var != person or evidence.asserted or evidence.value != candidate:
                    continue
                sources = (*evidence.sources, *evidence.scope)
                origins = {
                    label for source in sources for label in self.source_origins.get(source, ())
                }
                known_origins = {
                    label
                    for label in origins
                    if any(origin.label == label for origin in self.compilation.origins)
                }
                if known_origins:
                    labels.update(known_origins)
                    recognized = True
                elif (
                    evidence.placing is not None
                    and evidence.placing[0] in self.board.people
                    and isinstance(evidence.placing[1], Square)
                ):
                    placements[evidence.placing[0]] = evidence.placing[1]
                    placement_causes.add(candidate)
                    recognized = True
                if recognized:
                    break
            if not recognized:
                return None

        omitted = labels & omit_origins
        labels.difference_update(omit_origins)
        if not labels and not placement_causes:
            if omitted:
                only = self.say("person_single", placement=f"**{self.placed(person, square)}**")
                return only[0].lower() + only[1:].removesuffix(".")
            return None
        support = self._origin_references(labels) if labels else ""
        if placement_causes:
            blockers = self.places.blockers(
                placement_causes,
                placements,
                max_people=len(placements),
            )
            if blockers is None:
                return None
            support = "; ".join([item for item in (support, *blockers) if item])
        return self.say(
            "murdoku.person_single_evidence",
            support=support,
            who=person,
            placement=f"**{self.placed(person, square)}**",
        )

    def _line_single_clues(
        self,
        person: str,
        kind: str,
        index: int,
        placement: Square,
        history: Sequence[Step],
        before: Model,
    ) -> tuple[str | None, list[str]]:
        exclusions: dict[str, set[Square]] = {}
        for log_index, step in enumerate(self.compilation.model.log):
            if (
                step.var != person
                or step.asserted
                or not isinstance(step.value, Square)
                or step.value == placement
                or (step.value.row if kind == "row" else step.value.col) != index
            ):
                continue
            labels = {
                origin.label
                for origin in self.compilation.initial_step_origins.get(log_index, ())
                if origin.kind == "clue"
            }
            for label in labels:
                exclusions.setdefault(label, set()).add(step.value)
        clues = [
            self.say(
                "murdoku.line_single_excluded",
                clue=self.names([label]),
                who=person,
                squares=self.say.join([self.places.square(square) for square in sorted(squares)]),
            )
            for label, squares in exclusions.items()
        ]
        other_clues: dict[tuple[str, str], set[Square]] = {}
        for step in history:
            if (
                step.var not in self.board.people
                or step.var == person
                or step.asserted
                or step.placing is not None
                or step.value != placement
                or len(before.options(step.var)) <= 1
            ):
                continue
            for source in step.sources:
                for label in self.source_origins.get(source, ()):
                    if label in self.clue_origins:
                        other_clues.setdefault((step.var, label), set()).add(placement)
        if len(other_clues) <= 2:
            clues.extend(
                self.say(
                    "murdoku.line_single_excluded",
                    clue=self.names([label]),
                    who=who,
                    squares=self.places.squares(squares, "and"),
                )
                for (who, label), squares in other_clues.items()
            )
        recent = list(history)
        last_placement = next(
            (
                i
                for i in range(len(recent) - 1, -1, -1)
                if recent[i].asserted and recent[i].var in self.board.people
            ),
            -1,
        )
        other_exclusions: dict[tuple[str, str], set[Square]] = {}
        for step in recent[last_placement + 1 :]:
            if (
                step.var not in self.board.people
                or step.var == person
                or step.asserted
                or step.placing is not None
                or not isinstance(step.value, Square)
                or (step.value.row if kind == "row" else step.value.col) != index
            ):
                continue
            for source in step.sources:
                for label in self.source_origins.get(source, ()):
                    if any(
                        origin.label == label and origin.kind == "rule"
                        for origin in self.compilation.origins
                    ):
                        other_exclusions.setdefault((step.var, label), set()).add(step.value)
        context = None
        excluded_people = {who for who, _ in other_exclusions}
        if len(excluded_people) == 1 and len(self.board.people) <= 6:
            regions = {}
            for who in self.board.people:
                if who in excluded_people:
                    continue
                squares = [before.value_of(literal) for literal in before.options(who)]
                if not squares or not all(isinstance(square, Square) for square in squares):
                    break
                areas = {self.board.region_of(square) for square in squares}
                if len(areas) != 1:
                    break
                regions[who] = next(iter(areas))
            else:
                context = self.say(
                    "murdoku.region_candidates",
                    candidates="; ".join(
                        f"{self.say.people.get(who, who)}: "
                        f"{self.places.region(self.board.region_names[area])}"
                        for who, area in regions.items()
                    ),
                )
        if len(other_exclusions) <= 2:
            clues.extend(
                self.say(
                    "murdoku.line_single_excluded",
                    clue=self.names([label]),
                    who=who,
                    squares=self.places.squares(squares, "and"),
                )
                for (who, label), squares in other_exclusions.items()
                if len(squares) <= MAX_LISTED + 1
            )
        return context, clues

    def _relation_pair(self, inference: Inference) -> str | None:
        move = inference.move
        if move is None or move.rule != "relations" or len(move.sources) != 1:
            return None
        relation = next(
            (item for item in self.model.relations if item.name == move.sources[0]), None
        )
        if (
            relation is None
            or len(relation.variables) != 2
            or any(variable not in self.board.people for variable in relation.variables)
        ):
            return None
        domains = [
            [
                (variable, inference.before.value_of(literal))
                for literal in inference.before.options(variable)
            ]
            for variable in relation.variables
        ]
        if len(domains[0]) * len(domains[1]) > 4096:
            return None
        pairs = [
            (first, second)
            for first, second in product(*domains)
            if relation.holds(first[1], second[1])
        ]
        if len(pairs) != 1:
            return None
        known = [pair for pair in pairs[0] if pair in self.spoken_placements]
        new = [pair for pair in pairs[0] if pair not in self.spoken_placements]
        if not new:
            return None
        self.spoken_placements.update(
            (person, square) for person, square in new if isinstance(square, Square)
        )
        if known:
            return self.say(
                "murdoku.relation_pair_with_known",
                known=self.say.join([self.placed(*pair) for pair in known]),
                pair=self.say.join([f"**{self.placed(*pair)}**" for pair in new]),
                source=self.names(move.sources),
            )
        pair = self.say.join([self.placed(*candidate) for candidate in pairs[0]])
        return self.say(
            "murdoku.relation_pair",
            pair=f"**{pair}**",
            source=self.names(move.sources),
        )

    def _direction_boundary(self, inference: Inference) -> str | None:
        move = inference.move
        if move is None or len(move.sources) != 1:
            return None
        labels = self.source_origins.get(move.sources[0], ())
        origin = next(
            (
                item
                for item in self.compilation.origins
                if item.label in labels and item.kind == "clue"
            ),
            None,
        )
        if origin is None or not isinstance(origin.statement.formula, Atom):
            return None
        formula = origin.statement.formula
        if (
            formula.measure is not None
            or not isinstance(formula.subject, Name)
            or not isinstance(formula.target, Name)
            or formula.subject.token.text not in self.board.people
            or formula.target.token.text not in self.board.people
        ):
            return None
        direction = formula.operator.text
        boundaries = {
            "dir:up": ("row", self.board.size - 1, "row", 0),
            "dir:down": ("row", 0, "row", self.board.size - 1),
            "dir:left": ("col", self.board.size - 1, "col", 0),
            "dir:right": ("col", 0, "col", self.board.size - 1),
        }
        if direction not in boundaries:
            return None
        first_kind, first_index, second_kind, second_index = boundaries[direction]
        eliminations = {
            (step.var, step.value)
            for step in inference.steps
            if not step.asserted and isinstance(step.value, Square)
        }
        for person, kind, index in (
            (formula.subject.token.text, first_kind, first_index),
            (formula.target.token.text, second_kind, second_index),
        ):
            options = [
                inference.before.value_of(literal) for literal in inference.before.options(person)
            ]
            candidates = {
                square
                for square in options
                if isinstance(square, Square)
                and (square.row if kind == "row" else square.col) == index
            }
            if not candidates or any((person, square) not in eliminations for square in candidates):
                return None
        first = self.say(
            "clue.not_in_row",
            a=formula.subject.token.text,
            line=self.places.line(first_kind, first_index),
        )
        second = self.say(
            "clue.not_in_row",
            a=formula.target.token.text,
            line=self.places.line(second_kind, second_index),
        )
        return self.say(
            "murdoku.direction_boundaries",
            clue=_cap(self.statements[origin.label]),
            first=first,
            second=second,
        )

    def _direction_prior_exclusions(
        self, inference: Inference, history: Sequence[Step]
    ) -> str | None:
        move = inference.move
        if move is None or len(move.sources) != 1:
            return None
        origins = self.source_origins.get(move.sources[0], ())
        origin = next((item for item in self.compilation.origins if item.label in origins), None)
        if origin is None or not isinstance(origin.statement.formula, Atom):
            return None
        formula = origin.statement.formula
        if not isinstance(formula.subject, Name) or not isinstance(formula.target, Name):
            return None
        kind = "row" if formula.operator.text in {"dir:up", "dir:down"} else "col"
        for person in (formula.subject.token.text, formula.target.token.text):
            if person not in self.board.people:
                continue
            live = {
                inference.before.value_of(literal) for literal in inference.before.options(person)
            }
            for index in range(self.board.size):
                squares = {
                    square
                    for square in self.board.free
                    if (square.row if kind == "row" else square.col) == index
                }
                if not squares or squares & live:
                    continue
                clues: dict[str, set[Square]] = {}
                empty: set[str] = set()
                for square in squares:
                    region = self.board.region_of(square)
                    if region in self.told_empty_regions:
                        empty.add(region)
                        continue
                    labels = {
                        label
                        for step in history
                        if step.var == person and not step.asserted and step.value == square
                        for source in step.sources
                        for label in self.source_origins.get(source, ())
                        if label in self.direct_clue_origins
                    }
                    for clue in self.compilation.origins:
                        if clue.label not in labels:
                            continue
                        dependencies = grounded_dependencies(self.board, clue.statement)
                        if dependencies == frozenset({person}) and not holds_grounded(
                            clue.statement, self.board, {person: square}, dependencies
                        ):
                            clues.setdefault(clue.label, set()).add(square)
                            break
                    else:
                        break
                else:
                    if not clues or not empty:
                        continue
                    parts = [
                        self.say(
                            "murdoku.area_excluded_by_clue",
                            clue=self.names([label]),
                            who=person,
                            squares=self.places.squares(excluded, "and"),
                        )
                        for label, excluded in clues.items()
                    ]
                    parts.extend(
                        self.say(
                            "global_count.area_empty",
                            where=self.places.region(self.board.region_names[region]),
                        )
                        for region in sorted(empty)
                    )
                    return _cap("; ".join(parts)) + "."
        return None

    def _relation_candidate_summary(self, inference: Inference) -> str | None:
        move = inference.move
        if move is None or move.rule != "relations" or len(move.sources) != 1:
            return None
        relation = next(
            (item for item in self.model.relations if item.name == move.sources[0]), None
        )
        if (
            relation is None
            or len(relation.variables) < 2
            or any(person not in self.board.people for person in relation.variables)
        ):
            return None
        candidates = [
            [inference.before.value_of(literal) for literal in inference.before.options(person)]
            for person in relation.variables
        ]
        if any(
            not values or not all(isinstance(value, Square) for value in values)
            for values in candidates
        ):
            return None
        for kind, attribute in (("row", "row"), ("col", "col")):
            lines = [{getattr(square, attribute) for square in values} for values in candidates]
            if (
                all(available == lines[0] for available in lines[1:])
                and len(lines[0]) < self.board.size
            ):
                summary = self.say(
                    "murdoku.relation_candidate_bound",
                    people=self.say.join(relation.variables),
                    lines=self.places.lines(kind, lines[0]),
                )
                removed = {
                    (step.var, step.value)
                    for step in inference.steps
                    if not step.asserted and isinstance(step.value, Square)
                }
                for person, values in zip(relation.variables, candidates, strict=True):
                    if not 1 < len(values) <= MAX_LISTED + 3:
                        continue
                    areas = {self.board.region_of(square) for square in values}
                    if not 1 < len(areas) <= MAX_LISTED:
                        continue
                    if not any(
                        other != person
                        and all(
                            (other, square) in removed
                            for square in other_values
                            if self.board.region_of(square) == area
                        )
                        for other, other_values in zip(relation.variables, candidates, strict=True)
                        for area in {self.board.region_of(square) for square in other_values}
                    ):
                        continue
                    summary += (
                        " "
                        + self.say("and")
                        + " "
                        + self.say(
                            "murdoku.relation_area_bound",
                            who=person,
                            areas=self.places.regions(areas),
                        )
                    )
                return summary
        if all(1 < len(values) <= MAX_LISTED + 5 for values in candidates):
            return self.say.join(
                [
                    self.say(
                        "murdoku.relation_exact_candidates",
                        who=person,
                        squares=self.places.squares(set(values), "or"),
                    )
                    for person, values in zip(relation.variables, candidates, strict=True)
                ]
            )
        return None

    def _relation_occupied_lines(self, inference: Inference) -> str | None:
        move = inference.move
        if move is None or move.rule != "relations" or len(move.sources) != 1:
            return None
        relation = next(
            (item for item in self.model.relations if item.name == move.sources[0]), None
        )
        if (
            relation is None
            or len(relation.variables) != 2
            or any(person not in self.board.people for person in relation.variables)
            or any(step.asserted or step.var not in relation.variables for step in inference.steps)
        ):
            return None
        options = {
            person: {
                inference.before.value_of(literal) for literal in inference.before.options(person)
            }
            for person in relation.variables
        }
        remaining = {
            person: values
            - {step.value for step in inference.steps if step.var == person and not step.asserted}
            for person, values in options.items()
        }
        for person, other in (relation.variables, relation.variables[::-1]):
            if (
                len(options[person]) != 2
                or len(remaining[person]) != 1
                or not 1 < len(remaining[other]) <= MAX_LISTED + 1
                or not all(
                    isinstance(value, Square) for values in options.values() for value in values
                )
            ):
                continue
            (rejected,) = options[person] - remaining[person]
            (placed,) = remaining[person]
            possible = {
                square
                for square in self.board.free
                if relation.holds(
                    *((rejected, square) if relation.variables[0] == person else (square, rejected))
                )
            }
            if not possible or len(possible) > MAX_LISTED + 4 or possible & options[other]:
                continue
            occupied = self.told_occupied_squares | {
                square for _, squares in self.told_count_squares for square in squares
            }
            occupied.update(square for owner, square in self.spoken_placements if owner != other)
            lines: dict[str, set[int]] = {"row": set(), "col": set()}
            for square in possible:
                match = next(
                    (
                        (kind, index)
                        for occupied_square in sorted(occupied)
                        if occupied_square != square
                        for kind, index in (("row", square.row), ("col", square.col))
                        if (occupied_square.row if kind == "row" else occupied_square.col) == index
                    ),
                    None,
                )
                if match is None:
                    break
                kind, index = match
                lines[kind].add(index)
            else:
                self.conclusion(inference.steps)
                return self.say(
                    "murdoku.relation_occupied_lines",
                    who=person,
                    rejected=self.places.square(rejected),
                    other=other,
                    squares=self.places.squares(possible, "or"),
                    source=self.names(move.sources),
                    lines=self.say.join(
                        [
                            self.places.lines(kind, values)
                            for kind, values in lines.items()
                            if values
                        ]
                    ),
                    placement=f"**{self.placed(person, placed)}**",
                    remaining=self.places.squares(remaining[other], "or"),
                )
        return None

    def _row_reservation(self, inference: Inference) -> str | None:
        move = inference.move
        if move is None or move.rule != "cover2":
            return None
        people: list[str] = []
        for source in move.sources:
            variables = self.source_variables.get(source, set()) & self.options.keys()
            if len(variables) == 1:
                people.extend(variables)
        people = list(dict.fromkeys(people))
        if len(people) != 2:
            return None
        rows: list[int] = []
        for source in move.scope:
            constraint = self.constraints.get(source)
            if constraint is None or constraint.kind is not Kind.EXACTLY_ONE:
                return None
            indices = {
                square.row
                for literal in constraint.literals
                if isinstance((square := self.model.value_of(literal)), Square)
            }
            if len(indices) != 1:
                return None
            rows.extend(sorted(indices))
        if len(rows) != 2 or len(set(rows)) != 2:
            return None
        return self.say(
            "row_reservation",
            people=self.say.join(people),
            rows=self.places.lines("row", rows),
        )

    def _count_square_reservation(
        self, inference: Inference
    ) -> tuple[str | None, Square, str] | None:
        move = inference.move
        if move is None or move.rule not in {"cover2", "cover3"} or len(move.sources) != 1:
            return None
        source = move.sources[0]
        constraint = self.constraints.get(source)
        if (
            constraint is None
            or constraint.kind is not Kind.COUNT
            or constraint.reified_by is not None
            or len(set(constraint.literals)) != len(constraint.literals)
            or any(
                self.model.var_of(literal) not in self.board.people
                for literal in constraint.literals
            )
        ):
            return None
        live = [
            self.model.value_of(literal)
            for literal in constraint.literals
            if not inference.before.is_false(literal)
        ]
        if not live or not all(isinstance(square, Square) for square in live):
            return None
        squares = frozenset(live)
        key = (source, squares)
        if not 2 <= len(squares) <= 6 or constraint.allowed_counts != {len(squares)}:
            return None
        for scope in move.scope:
            kind, index = self.board_sources.get(scope, ("", None))
            if kind not in {"row", "col"} or index is None:
                continue
            matching = {
                square
                for square in squares
                if (square.row if kind == "row" else square.col) == index
            }
            if len(matching) != 1:
                continue
            (square,) = matching
            if not all(
                not step.asserted
                and step.var in self.board.people
                and isinstance(step.value, Square)
                and step.value != square
                and (step.value.row if kind == "row" else step.value.col) == index
                for step in inference.steps
            ):
                continue
            premise = None
            if key not in self.told_count_squares:
                self.told_count_squares.add(key)
                premise = self.say(
                    "murdoku.count_square_reservation",
                    source=self.names([source]),
                    count=self.say.number(len(squares)),
                    squares=self.places.squares(squares, "and"),
                )
                all_squares = {self.model.value_of(literal) for literal in constraint.literals}
                excluded = all_squares - squares
                for person, reserved_kind, reserved_index in sorted(self.told_reservations):
                    options = {
                        inference.before.value_of(literal)
                        for literal in inference.before.options(person)
                    }
                    if (
                        excluded
                        and len(excluded) <= 6
                        and options
                        and all(isinstance(cell, Square) for cell in excluded | options)
                        and all(
                            (cell.row if reserved_kind == "row" else cell.col) == reserved_index
                            for cell in excluded | options
                        )
                        and not excluded & options
                    ):
                        premise = (
                            self.say(
                                "murdoku.reserved_line_excludes_squares",
                                who=person,
                                line=self.places.line(reserved_kind, reserved_index),
                                squares=self.places.squares(excluded, "and"),
                            )
                            + " "
                            + premise
                        )
                        break
            return premise, square, self.places.line(kind, index)
        return None

    def _line_overlap(self, inference: Inference, conclusion: str | None) -> str | None:
        move = inference.move
        if move is None or move.rule != "subsumption":
            return None
        source_lines = [
            (source, *self.board_sources[source])
            for source in move.sources
            if self.board_sources.get(source, ("", None))[0] in {"row", "col"}
        ]
        scope_lines = [
            (source, *self.board_sources[source])
            for source in move.scope
            if self.board_sources.get(source, ("", None))[0] in {"row", "col"}
        ]
        if len(source_lines) != 1 or len(scope_lines) != 1:
            return None
        source, source_kind, source_index = source_lines[0]
        _, scope_kind, scope_index = scope_lines[0]
        if source_kind == scope_kind:
            return None
        constraint = self.constraints.get(source)
        if constraint is None or constraint.kind is not Kind.EXACTLY_ONE:
            return None
        squares = {
            inference.before.value_of(literal)
            for literal in inference.before.live(constraint.index)
            if inference.before.var_of(literal) in self.board.people
            and isinstance(inference.before.value_of(literal), Square)
        }
        if len(squares) != 1:
            return None
        (square,) = squares
        if (square.row if source_kind == "row" else square.col) != source_index or (
            square.row if scope_kind == "row" else square.col
        ) != scope_index:
            return None
        self.told_occupied_squares.add(square)
        return self.say(
            "murdoku.line_overlap" if conclusion else "murdoku.line_overlap_only",
            source_line=self.places.line(source_kind, source_index),
            square=self.places.square(square),
            scope_line=self.places.line(scope_kind, scope_index),
            conclusion=conclusion,
        )

    def _line_person(
        self, inference: Inference, conclusion: str, history: Sequence[Step]
    ) -> str | None:
        move = inference.move
        if move is None or move.rule != "subsumption" or len(move.sources) != 1:
            return None
        source = move.sources[0]
        kind, index = self.board_sources.get(source, ("", None))
        constraint = self.constraints.get(source)
        if (
            kind not in {"row", "col"}
            or constraint is None
            or constraint.kind is not Kind.EXACTLY_ONE
        ):
            return None
        people = [
            self.board_sources[scope][1]
            for scope in move.scope
            if self.board_sources.get(scope, ("", None))[0] == "person"
        ]
        if len(people) != 1:
            return None
        person = people[0]
        live = inference.before.live(constraint.index)
        if not live or any(inference.before.var_of(literal) != person for literal in live):
            return None
        squares = [inference.before.value_of(literal) for literal in live]
        if len(squares) > MAX_LISTED + 1 or not all(isinstance(sq, Square) for sq in squares):
            return None
        exclusions: dict[tuple[str, str], set[Square]] = {}
        for step in history:
            if (
                step.var not in self.board.people
                or step.var == person
                or step.asserted
                or step.placing is not None
                or not isinstance(step.value, Square)
                or (step.value.row if kind == "row" else step.value.col) != index
            ):
                continue
            for source in step.sources:
                for label in self.source_origins.get(source, ()):
                    if label in self.clue_origins:
                        exclusions.setdefault((step.var, label), set()).add(step.value)
        details = [
            self.say(
                "murdoku.line_single_excluded",
                clue=self.names([label]),
                who=who,
                squares=self.places.squares(values, "and"),
            )
            for (who, label), values in exclusions.items()
            if len(values) <= MAX_LISTED + 2
        ]
        if len(details) > 2:
            details = []
        reservation = self.say(
            "murdoku.line_person",
            who=person,
            line=self.places.line(kind, index),
            squares=self.places.squares(set(squares), "or"),
            conclusion=conclusion,
        )
        if details:
            reservation = reservation[0].lower() + reservation[1:]
            return self.say.join(details) + "; " + reservation + "."
        return reservation + "."

    def _area_exclusion_details(
        self, inference: Inference, history: Sequence[Step], person: str, region: str
    ) -> list[str]:
        area_squares = {
            square for square in self.board.free if self.board.region_of(square) == region
        }
        first: dict[Square, Step] = {}
        for step in (*self.compilation.model.log, *history):
            if (
                step.var == person
                and not step.asserted
                and isinstance(step.value, Square)
                and step.value in area_squares
            ):
                first.setdefault(step.value, step)

        clues: dict[str, set[Square]] = {}
        occupied: dict[tuple[str, str, int], set[Square]] = {}
        reserved: dict[tuple[str, str, int], set[Square]] = {}
        for square, step in first.items():
            clue_labels = {
                label
                for source in step.sources
                for label in self.source_origins.get(source, ())
                if label in self.clue_origins
            }
            if clue_labels:
                for label in clue_labels:
                    clues.setdefault(label, set()).add(square)
                continue
            line = next(
                (
                    self.board_sources[source]
                    for source in step.sources
                    if self.board_sources.get(source, ("", None))[0] in {"row", "col"}
                ),
                None,
            )
            if step.placing is not None and line is not None:
                blocker, placed = step.placing
                kind, index = line
                if isinstance(placed, Square) and (
                    (placed.row if kind == "row" else placed.col) == index
                    and (square.row if kind == "row" else square.col) == index
                ):
                    occupied.setdefault((blocker, kind, index), set()).add(square)
                    continue
            if step.rule == "subsumption":
                person_sources = [
                    source
                    for source in step.sources
                    if self.board_sources.get(source, ("", None))[0] == "person"
                ]
                line_sources = [
                    self.board_sources[source]
                    for source in step.scope
                    if self.board_sources.get(source, ("", None))[0] in {"row", "col"}
                ]
                if len(person_sources) == len(line_sources) == 1:
                    blocker = self.board_sources[person_sources[0]][1]
                    kind, index = line_sources[0]
                    options = {
                        inference.before.value_of(literal)
                        for literal in inference.before.options(blocker)
                    }
                    if options and all(
                        (candidate.row if kind == "row" else candidate.col) == index
                        for candidate in options
                    ):
                        reserved.setdefault((blocker, kind, index), set()).add(square)

        details = [
            self.say(
                "murdoku.area_excluded_by_clue",
                clue=self.names([label]),
                who=person,
                squares=self.say.join([self.places.square(square) for square in sorted(squares)]),
            )
            for label, squares in clues.items()
        ]
        details.extend(
            self.say(
                "murdoku.area_excluded_by_occupant",
                blocker=blocker,
                line=self.places.line(kind, index),
                who=person,
                squares=self.say.join([self.places.square(square) for square in sorted(squares)]),
            )
            for (blocker, kind, index), squares in occupied.items()
        )
        details.extend(
            self.say(
                "murdoku.area_excluded_by_reservation",
                blocker=blocker,
                line=self.places.line(kind, index),
                who=person,
                squares=self.say.join([self.places.square(square) for square in sorted(squares)]),
            )
            for (blocker, kind, index), squares in reserved.items()
        )
        return details

    def _role_area_reason(self, inference: Inference, history: Sequence[Step]) -> str | None:
        for step in inference.steps:
            if step.var not in self.roles or not step.asserted or step.value is not True:
                continue
            person, role = self.roles[step.var]
            specification = next((item for item in self.board.roles if item.name == role), None)
            if specification is None or specification.allowed_counts != frozenset({1}):
                continue
            eligible = set(specification.eligible_people or self.board.people)
            if person not in eligible:
                continue
            for source in step.sources:
                constraint = self.constraints.get(source)
                if constraint is None or constraint.kind is not Kind.COUNT:
                    continue
                squares = [
                    self.model.value_of(literal)
                    for literal in constraint.literals
                    if self.model.var_of(literal) == person
                    and isinstance(self.model.value_of(literal), Square)
                ]
                regions = {self.board.region_of(square) for square in squares}
                if len(regions) != 1:
                    continue
                (region,) = regions
                possible = [
                    candidate
                    for candidate in eligible
                    if any(
                        self.board.region_of(inference.before.value_of(literal)) == region
                        for literal in inference.before.options(candidate)
                    )
                ]
                if possible != [person]:
                    continue
                details = []
                for candidate in self.board.people:
                    if candidate not in eligible or candidate == person:
                        continue
                    options = {
                        inference.before.value_of(literal)
                        for literal in inference.before.options(candidate)
                    }
                    candidate_region = self.places.common_region(options)
                    if candidate_region and self.board.region_of(next(iter(options))) != region:
                        details.append(
                            self.say(
                                "murdoku.area_confined",
                                who=candidate,
                                area=candidate_region,
                            )
                        )
                    else:
                        details.extend(
                            self._area_exclusion_details(inference, history, candidate, region)
                        )
                        if not any(self.board.region_of(square) == region for square in options):
                            details.append(
                                self.say(
                                    "murdoku.area_no_candidate",
                                    who=candidate,
                                    area=self.places.region(self.board.region_names[region]),
                                )
                            )
                origin = next(
                    (
                        origin
                        for label in self.source_origins.get(source, ())
                        for origin in self.compilation.origins
                        if origin.label == label and origin.kind == "rule"
                    ),
                    None,
                )
                rule = (
                    self.source_words[origin.label] if origin is not None else self.names([source])
                )
                return self.say(
                    "murdoku.role_area_unique",
                    reasons=self.say.join(details),
                    who=person,
                    area=self.places.region(self.board.region_names[region]),
                    rule=_cap(rule),
                    role=self.say.words.get(role, role),
                )
        return None

    def _beside_different_area(self, formula: Atom, candidates: set[Square]) -> str | None:
        target = formula.target
        if (
            formula.operator.text != "beside"
            or not isinstance(target, Name)
            or not target.token.text.startswith("object:")
        ):
            return None
        name = target.token.text.removeprefix("object:")
        different_area = {
            square
            for square in candidates
            for obj in self.board.objects
            if obj.name == name
            for feature in obj.squares
            if steps_between(square, feature) == 1
            and self.board.region_of(square) != self.board.region_of(feature)
        }
        if not different_area:
            return None
        return self.say(
            "murdoku.beside_different_area",
            squares=self.places.squares(different_area, "and"),
            thing=self.places.thing(name),
        )

    def _role_exclusion(self, inference: Inference) -> str | None:
        visible = [step for step in inference.steps if step.var in self.roles]
        if len(visible) != 1:
            return None
        step = visible[0]
        if (step.value if step.asserted else not step.value) is not False:
            return None
        sources = inference.move.sources if inference.move is not None else ()
        if len(sources) != 1:
            return None
        labels = self.source_origins.get(sources[0], ())
        origin = next(
            (
                origin
                for origin in self.compilation.origins
                if origin.label in labels and origin.kind == "rule"
            ),
            None,
        )
        if origin is None:
            return None
        person, role = self.roles[step.var]
        formula = origin.statement.formula
        if (
            isinstance(formula, Quantified)
            and formula.quantifier.text == "every"
            and len(formula.variables) == 1
            and isinstance(formula.source, Name)
            and formula.source.token.text == f"role:{role}"
            and isinstance(formula.body, Atom)
            and isinstance(formula.body.subject, Name)
            and formula.body.subject.token.text == formula.variables[0].text
        ):
            statement = Statement(
                replace(
                    formula.body,
                    subject=Name(
                        Token(
                            person,
                            formula.body.subject.token.line,
                            formula.body.subject.token.column,
                        )
                    ),
                )
            )
            candidates = [
                inference.before.value_of(literal)
                for literal in inference.before.options(person)
                if isinstance(inference.before.value_of(literal), Square)
            ]
            dependencies = grounded_dependencies(self.board, statement)
            if (
                candidates
                and len(candidates) <= MAX_LISTED + 1
                and dependencies == frozenset({person})
                and all(
                    not holds_grounded(statement, self.board, {person: square}, dependencies)
                    for square in candidates
                )
            ):
                detail = ""
                if explanation := self._beside_different_area(formula.body, set(candidates)):
                    detail = f" {explanation}."
                self.spoken_rule_origins.add(origin.label)
                return self.say(
                    "murdoku.role_exclusion_candidates"
                    if self.numbered
                    else "murdoku.role_exclusion_candidates_unnumbered",
                    rule=_cap(self.say("expression.rule", number=origin.number)),
                    statement=_cap(self.statements[origin.label]),
                    detail=detail,
                    who=person,
                    role=self.say.words.get(role, role),
                    squares=self.say.join(
                        [self.places.square(square) for square in sorted(candidates)]
                    ),
                )
        return self.say(
            "murdoku.role_exclusion",
            rule=_cap(
                self.say("expression.rule", number=origin.number)
                if self.numbered
                else self.statements[origin.label]
            ),
            who=person,
            role=self.say.words.get(role, role),
        )

    def pattern(self, inference: Inference, history: Sequence[Step]) -> str:
        move = inference.move
        if line_single := self._line_single(inference, history):
            self._advance_without_conclusion(inference.steps)
            return line_single
        assert move is not None
        if move.rule == "what_if" and inference.steps[0].var in self.visible:
            paragraph = self._what_if(inference, history)
            if conclusion := self.conclusion(inference.steps):
                paragraph += f" {_cap(self.say('so'))} {conclusion}."
            return paragraph
        if occupied_reason := self._relation_occupied_lines(inference):
            return occupied_reason
        reservation = self._row_reservation(inference)
        line_reservation = self._line_reservation(inference)
        conclusion = self.conclusion(
            inference.steps,
            group_candidates=move.rule not in {"chains", "what_if"},
            embedded=reservation is not None or self._line_overlap(inference, None) is not None,
            include_broad_candidates=(
                (
                    move.rule == "relations"
                    and self._relation_candidate_summary(inference) is not None
                )
                or (
                    move.rule in {"cover2", "cover3"}
                    and any(
                        origin.kind == "rule"
                        and origin.label in self.source_origins.get(source, ())
                        for source in move.sources
                        for origin in self.compilation.origins
                    )
                )
            ),
        )
        if conclusion is None:
            if line_overlap := self._line_overlap(inference, None):
                return line_overlap + "."
            return reservation + "." if reservation is not None else ""
        if reservation is not None:
            return f"{reservation}. {_cap(self.say('so'))} {conclusion}."
        if line_reservation is not None:
            return (
                _cap(self.say("line_reservation", **line_reservation, conclusion=conclusion)) + "."
            )
        if line_overlap := self._line_overlap(inference, conclusion):
            return line_overlap + "."
        if line_person := self._line_person(inference, conclusion, history):
            return line_person
        if role_exclusion := self._role_exclusion(inference):
            return role_exclusion + "."
        if role_area := self._role_area_reason(inference, history):
            return role_area + "."
        if relation_pair := self._relation_pair(inference):
            return relation_pair
        if furthest := self._furthest_exclusion(inference, conclusion):
            return furthest
        if relation := self._relation_with_candidates(inference, conclusion):
            return relation
        if move.rule == "chains" and all(var in self.visible for var, _ in move.chain):
            return self._chain(
                move.chain, conclusion, move.sources, inference.steps, inference.before
            )
        sources = (
            move.sources + move.scope
            if move.rule in {"subsumption", "cover2", "cover3"}
            else move.sources
        )
        if square_reservation := self._count_square_reservation(inference):
            premise, square, line = square_reservation
            reason = self.say(
                "murdoku.occupied_square_line",
                square=self.places.square(square),
                line=line,
                conclusion=conclusion,
            )
            return f"{premise} {reason}" if premise else reason
        return self._because(sources, conclusion)

    def _line_reservation(self, inference: Inference) -> dict[str, str] | None:
        move = inference.move
        if move is None or move.rule != "subsumption":
            return None
        person_sources = [
            source
            for source in move.sources
            if self.board_sources.get(source, ("", None))[0] == "person"
        ]
        lines = [
            (source, *self.board_sources[source])
            for source in move.scope
            if self.board_sources.get(source, ("", None))[0] in {"row", "col"}
        ]
        if len(person_sources) != 1 or len(lines) != 1:
            return None
        person = self.board_sources[person_sources[0]][1]
        source, kind, index = lines[0]
        if (person, kind, index) in self.told_reservations:
            return None
        if not self.options[person] or any(
            (square.row if kind == "row" else square.col) != index
            for square in self.options[person]
        ):
            return None
        if not any(
            step.var != person
            and isinstance(step.value, Square)
            and (step.value.row if kind == "row" else step.value.col) == index
            for step in inference.steps
        ):
            return None
        return {
            "person": person,
            "line": self.places.line(kind, index),
            "rule": self.source_words[source],
        }

    def tell(
        self, start: Model, groups: Sequence[Episode], solved: bool
    ) -> generic_story.Explanation:
        paragraphs = []
        initial: dict[tuple[str, ...], list[Step]] = {}
        for index, step in enumerate(self.compilation.model.log):
            origins = self.compilation.initial_step_origins.get(index, ())
            sources = tuple(origin.label for origin in origins) or step.sources
            useful_sources = tuple(source for source in sources if source not in self.domains)
            if useful_sources:
                sources = useful_sources
            if sources and all(
                self.source_words.get(source) == self.say("expression.role_eligibility")
                for source in sources
            ):
                eligibility = self.say("expression.role_eligibility")
                self.source_words[eligibility] = eligibility
                sources = (eligibility,)
            initial.setdefault(sources, []).append(step)
        open_squares = set(self.board.free)
        for sources, steps in initial.items():
            if direct := self._direct(sources, steps, open_squares):
                paragraphs.append(direct)
            elif compact := self._shared_rule_exclusions(sources, steps):
                self._advance_without_conclusion(steps)
                paragraphs.append(compact)
            elif conclusion := self.conclusion(steps):
                paragraphs.append(self._because(sources, conclusion))
        if paragraphs:
            paragraphs = [f"**{self.say('direct')}.** " + " ".join(paragraphs)]
        if not self.numbered:
            for role in self.board.roles:
                if role.eligible_people is None:
                    continue
                eligible = sorted(role.eligible_people, key=self.board.people.index)
                if "role_has" in self.say.phrases and eligible:
                    statements = [
                        self.placed(self.board.role_variable(person, role.name), True)
                        for person in eligible
                    ]
                    certain = role.allowed_counts == {len(eligible)}
                    paragraphs.append(
                        self.say(
                            "role_eligible_true" if certain else "role_eligible_statements",
                            role=self.say.words.get(role.name, role.name),
                            statements=self.say.join(statements)
                            if certain
                            else "; ".join(statements),
                        )
                        + "."
                    )
                    continue
                paragraphs.append(
                    self.say(
                        "role_eligible_only_one"
                        if len(role.eligible_people) == 1
                        else "role_eligible_only_many",
                        people=self.say.join(eligible),
                        role=self.say.words.get(role.name, role.name),
                    )
                    + "."
                )
        history = list(self.compilation.model.log)
        support: dict[str, tuple[str, ...]] = {}
        for group in groups:
            for inference in (group.pattern, *group.consequences):
                for _, region, minimum in self._refuted_populations(inference.steps):
                    self.population_bounds[region] = min(
                        self.population_bounds.get(region, len(self.board.people)), minimum - 1
                    )
                sources = (
                    inference.move.sources
                    if inference.move is not None
                    else tuple(source for step in inference.steps for source in step.sources)
                )
                variables = {
                    variable
                    for source in sources
                    for variable in self.source_variables.get(source, ())
                }
                premises = tuple(
                    dict.fromkeys(
                        source
                        for variable, evidence in support.items()
                        if variable in variables
                        for source in evidence
                    )
                )
                if paragraph := self._mark_blocked_by_occupant(inference):
                    self._advance_without_conclusion(inference.steps)
                    paragraphs.append(paragraph + ".")
                elif paragraph := self._mark_case_deduction(inference, history):
                    if conclusion := self.conclusion(inference.steps):
                        paragraph += f" {_cap(self.say('so'))} {conclusion}."
                    paragraphs.append(paragraph)
                elif paragraph := self._direction_boundary(inference):
                    prior = self._direction_prior_exclusions(inference, history)
                    direction_origins = frozenset(
                        label
                        for source in (inference.move.sources if inference.move else ())
                        for label in self.source_origins.get(source, ())
                    )
                    if conclusion := self.conclusion(
                        inference.steps, omit_origins=direction_origins, embedded=True
                    ):
                        if prior:
                            paragraph += f" {prior}"
                        paragraph += f" {self.say('murdoku.with_prior', conclusion=conclusion)}."
                    paragraphs.append(paragraph)
                elif (
                    (
                        paragraph := (
                            self._population_full(inference)
                            or self._population_tied(inference)
                            or self._population_ceiling(inference)
                        )
                    )
                    or (paragraph := self._line_single(inference, history))
                    or (paragraph := self._relation_pair(inference))
                    or (paragraph := self._role_area_reason(inference, history))
                ):
                    self._advance_without_conclusion(inference.steps)
                    paragraphs.append(paragraph)
                elif reservation := self._line_reservation(inference):
                    if conclusion := self.conclusion(inference.steps):
                        paragraphs.append(
                            _cap(self.say("line_reservation", **reservation, conclusion=conclusion))
                            + "."
                        )
                    else:
                        paragraphs.append(
                            _cap(self.say("line_reservation_only", **reservation)) + "."
                        )
                elif paragraph := self._role_exclusion(inference):
                    self._advance_without_conclusion(inference.steps)
                    paragraphs.append(paragraph + ".")
                elif not any(step.var in self.visible for step in inference.steps):
                    for step in inference.steps:
                        support[step.var] = tuple(dict.fromkeys((*premises, *sources)))
                elif inference.move is not None and not premises:
                    if paragraph := self.pattern(inference, history):
                        paragraphs.append(
                            paragraph if paragraph.endswith((".", "!", "?")) else paragraph + "."
                        )
                else:
                    conclusion = self.conclusion(
                        inference.steps, embedded=self._line_overlap(inference, None) is not None
                    )
                    if conclusion is not None:
                        paragraph = self._line_overlap(inference, conclusion)
                        if paragraph is None:
                            paragraph = self._line_person(inference, conclusion, history)
                        if paragraph is None:
                            paragraph = self._furthest_exclusion(inference, conclusion)
                        if paragraph is None:
                            paragraph = self._relation_with_candidates(inference, conclusion)
                        paragraph = (
                            paragraph
                            if paragraph is not None
                            else self._because([*premises, *sources], conclusion)
                        )
                        paragraphs.append(
                            paragraph if paragraph.endswith((".", "!", "?")) else paragraph + "."
                        )
                history.extend(inference.steps)
        if not solved:
            paragraphs.append(self.say("generic.stalled"))
        elif not paragraphs:
            paragraphs.append(self.say("generic.givens_complete"))
        return generic_story.Explanation(tuple(paragraphs), solved)


def explain(
    text: str,
    *,
    start: Model | None = None,
    fired: Sequence[tuple[str, Sequence[Step]]] | None = None,
    numbered: bool = True,
) -> generic_story.Explanation:
    """Explain expressions without reading legacy clues or exposing auxiliary names."""
    board, rules, clues = load_expression_board(text)
    compilation = compile_statements_with_origins(board, clues, rules=rules)
    if start is None:
        start = compilation.model
    if fired is None:
        collected: list[tuple[str, Sequence[Step]]] = []
        Solver(start.clone()).solve(on_step=lambda rule, steps: collected.append((rule, steps)))
        fired = collected
    role_variables = {
        board.role_variable(person, role.name) for person in board.people for role in board.roles
    }
    required = {
        step.var: step.value if step.asserted else not step.value
        for _, steps in fired
        for step in steps
        if step.var in role_variables
    }
    moves = [move for rule, steps in fired if (move := Move.of(rule, steps)) is not None]
    if replay(start, moves).solution() is not None:
        moves = generic_story.thin(start, moves, required_values=required)
    result, groups = episodes(start, moves)
    narrator = _Narrator(text, board, compilation, numbered)
    explanation = narrator.tell(start, groups, result.solution() is not None)
    if explanation.complete:
        existing = "\n".join(explanation.paragraphs)
        missing_rules = [
            narrator.source_words[origin.label]
            for origin in compilation.origins
            if origin.kind == "rule"
            and origin.label not in narrator.spoken_rule_origins
            and narrator.source_words[origin.label].casefold() not in existing.casefold()
        ]
        if missing_rules:
            paragraphs = list(explanation.paragraphs)
            direct_heading = f"**{narrator.say('direct')}.**"
            insert_at = 1 if paragraphs and paragraphs[0].startswith(direct_heading) else 0
            paragraphs.insert(
                insert_at,
                narrator.say("murdoku.rule_context", rules="; ".join(missing_rules)),
            )
            explanation = replace(
                explanation,
                paragraphs=tuple(paragraphs),
            )
        missing = [
            f"**{narrator.placed(person, square)}**"
            for person, squares in narrator.options.items()
            if len(squares) == 1
            for square in squares
            if (person, square) not in narrator.spoken_placements
        ]
        if missing:
            explanation = replace(
                explanation,
                paragraphs=(
                    *explanation.paragraphs,
                    narrator.say(
                        "murdoku.final_placements",
                        placements=narrator.say.join(missing),
                    ),
                ),
            )
    if numbered and explanation.complete:
        reveal = presentation_reveal(text)
        spoken = "\n".join(explanation.paragraphs)
        for person in board.people:
            for role in board.roles:
                role_name = narrator.say.words.get(role.name, role.name)
                for title in (role_name, f"the {role_name}", f"de {role_name}", f"het {role_name}"):
                    assignment = f"{person} is {title}"
                    if assignment in reveal and f"**{assignment}**" not in spoken:
                        reveal = reveal.replace(assignment, f"**{assignment}**", 1)
                        break
        if reveal:
            explanation = replace(
                explanation,
                paragraphs=(
                    *explanation.paragraphs,
                    narrator.say("murdoku.final_answer", reveal=reveal),
                ),
            )
    return explanation
