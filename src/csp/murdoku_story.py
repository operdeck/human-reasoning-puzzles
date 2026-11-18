"""Murdoku explanations from expression origins and the generic engine's proof."""

from collections.abc import Iterable, Sequence
from dataclasses import replace
from itertools import combinations
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
)
from .murdoku_eval import grounded_dependencies, holds_grounded
from .murdoku_expression_file import load_expression_board
from .murdoku_expression_words import ExpressionWords, only_on
from .murdoku_lang import Atom, Count, Filter, Integer, Name, NumberComparison, Statement, Token
from .murdoku_lower import ExpressionCompilation, compile_statements_with_origins
from .proof import Episode, Inference, Move, episodes, essential, replay
from .story import Places, Wording, _cap


class _Narrator(generic_story.Narrator):
    def __init__(
        self, text: str, board: Board, compilation: ExpressionCompilation, numbered: bool
    ) -> None:
        say = Wording.read(text).for_people(board.people)
        if not numbered:
            say = say.unnumbered()
        super().__init__(compilation.model, say)
        self.board = board
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
            wording = say(
                f"expression.{key}",
                person=say.words.get(value, value) if kind == "person" else "",
                square=self.places.square(value) if kind == "square" else "",
            )
            self.source_words[rule.name] = wording
            if kind != "person":
                self.source_words[rule.family] = say(f"expression.{key}", square="", person="")
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
        origins = {origin for source in sources for origin in self.source_origins.get(source, ())}
        if (
            len(origins) == 1
            and origins <= self.clue_origins
            and all(source in self.source_origins for source in sources)
            and "expression.by" not in self.say.phrases
        ):
            (origin,) = origins
            return f"{_cap(self.statements[origin])}, {self.say('so')} {conclusion}."
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
        self.conclusion(own, include_marks=False)
        squares = self.options[person]
        if not squares:
            return None
        clue = _cap(self.statements[origin.label])
        region = self.places.common_region(squares)
        previous_region = self.places.common_region(previous)
        line = self.places.common_line(squares) if len(squares) > 1 else None
        line_where = self.say("in", what=self.places.line(*line)) if line else None
        where: str | None
        if len(squares) == 1:
            square = next(iter(squares))
            where = f"**{self.placed(person, square)}**"
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
                    )
                    suffix += f", {self.say('so')} **{instruction}**"
                    open_squares.difference_update(crossed)
        said = f"{clue}{suffix}."
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
            return f"{reason}, {self.say('so')} **{empty}**."
        return None

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

    def conclusion(self, steps: Iterable[Step], *, include_marks: bool = True) -> str | None:
        steps = list(steps)
        before = {person: set(cells) for person, cells in self.options.items()}
        placed = set()
        for step in steps:
            if step.var in self.options:
                if step.asserted:
                    self.options[step.var] = {step.value}
                    placed.add(step.var)
                else:
                    self.options[step.var].discard(step.value)
        said = []
        for person, previous in before.items():
            cells = self.options[person]
            if len(cells) == 1 and (person in placed or cells != previous):
                (square,) = cells
                if (person, square) not in self.told:
                    sentence = f"**{self.placed(person, square)}**"
                    if include_marks and (meaning := self._mark_placement(person, square)):
                        sentence += f". {meaning}"
                    said.append(sentence)
                    self.told.add((person, square))
            elif cells != previous and cells:
                line = self.places.common_line(cells)
                if line is not None and line != self.places.common_line(previous):
                    where = self.say("in", what=self.places.line(*line))
                    said.append(
                        "**"
                        + self.say("can_only_one", who=person, where=where)
                        + "**, **"
                        + self.say("nobody_else")
                        + "**"
                    )
                else:
                    said.append(
                        "**" + self.places.describe(person, cells, previous, placing=False) + "**"
                    )
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
            if (
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
                said.extend(f"**{self.placed(variable, False)}**" for variable in excluded)
        return self.say.join(said) if said else None

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
    ) -> str:
        if not chain or any(
            person not in self.board.people or not isinstance(square, Square)
            for person, square in chain
        ):
            paragraph = super()._chain(chain, conclusion)
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
            return _cap(self.say("chain_either", ends=ends, outcome=conclusion))
        parts = [self.say("chain_if", who=first, square=self.places.square(a))]
        for index, (person, square) in enumerate(chain[1:]):
            key = "chain_on" if index % 2 == 0 else "chain_off"
            reason = self._link_reason(sources[index]) if index < len(sources) else ""
            parts.append(self.say(key, who=person, square=self.places.square(square)) + reason)
        return f"{', '.join(parts)}. {self.say('chain_so', ends=ends, outcome=conclusion)}"

    def pattern(self, inference: Inference, history: Sequence[Step]) -> str:
        move = inference.move
        assert move is not None
        if move.rule == "what_if" and inference.steps[0].var in self.visible:
            paragraph = self._what_if(inference, history)
            if conclusion := self.conclusion(inference.steps):
                paragraph += f" {_cap(self.say('so'))} {conclusion}."
            return paragraph
        conclusion = self.conclusion(inference.steps)
        if conclusion is None:
            return ""
        if move.rule == "chains" and all(var in self.visible for var, _ in move.chain):
            return self._chain(move.chain, conclusion, move.sources)
        return self._because(move.sources, conclusion)

    def tell(
        self, start: Model, groups: Sequence[Episode], solved: bool
    ) -> generic_story.Explanation:
        paragraphs = []
        initial: dict[tuple[str, ...], list[Step]] = {}
        for index, step in enumerate(self.compilation.model.log):
            origins = self.compilation.initial_step_origins.get(index, ())
            sources = tuple(origin.label for origin in origins) or step.sources
            initial.setdefault(sources, []).append(step)
        open_squares = set(self.board.free)
        for sources, steps in initial.items():
            if direct := self._direct(sources, steps, open_squares):
                paragraphs.append(direct)
            elif conclusion := self.conclusion(steps):
                paragraphs.append(self._because(sources, conclusion))
        if paragraphs:
            paragraphs = [f"**{self.say('direct')}.** " + " ".join(paragraphs)]
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
                    self.conclusion(inference.steps)
                    paragraphs.append(paragraph + ".")
                elif paragraph := self._mark_case_deduction(inference, history):
                    if conclusion := self.conclusion(inference.steps):
                        paragraph += f" {_cap(self.say('so'))} {conclusion}."
                    paragraphs.append(paragraph)
                elif paragraph := (
                    self._population_full(inference)
                    or self._population_tied(inference)
                    or self._population_ceiling(inference)
                ):
                    self.conclusion(inference.steps)
                    paragraphs.append(paragraph)
                elif not any(step.var in self.visible for step in inference.steps):
                    for step in inference.steps:
                        support[step.var] = tuple(dict.fromkeys((*premises, *sources)))
                elif inference.move is not None and not premises:
                    if paragraph := self.pattern(inference, history):
                        paragraphs.append(paragraph)
                else:
                    conclusion = self.conclusion(inference.steps)
                    if conclusion is not None:
                        paragraphs.append(self._because([*premises, *sources], conclusion))
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
    return narrator.tell(start, groups, result.solution() is not None)
