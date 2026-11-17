"""Murdoku explanations from expression origins and the generic engine's proof."""

from collections.abc import Iterable, Sequence
from itertools import combinations
from typing import Any

from . import generic_story
from .core import Constraint, Kind, Model, Solver, Step
from .murdoku import POPULATION_FAMILY, Board, Square, board_rules
from .murdoku_eval import grounded_dependencies, holds_grounded
from .murdoku_expression_file import load_expression_board
from .murdoku_expression_words import ExpressionWords
from .murdoku_lang import Atom, Name
from .murdoku_lower import ExpressionCompilation, compile_statements_with_origins
from .proof import Episode, Inference, Move, episodes, replay
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
        self.visible.update(self.roles)
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
            self.source_words[compilation.model.constraints[index].name] = say.join(
                [self.source_words[origin.label] for origin in origins]
            )
        for index, origins in compilation.relation_origins.items():
            self.source_words[compilation.model.relations[index].name] = say.join(
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

    def _direct(
        self, sources: tuple[str, ...], steps: Sequence[Step], open_squares: set[Square]
    ) -> str | None:
        if len(sources) != 1:
            return None
        origin = next((item for item in self.compilation.origins if item.label == sources[0]), None)
        if origin is None or origin.kind != "clue":
            return None
        dependencies = grounded_dependencies(self.board, origin.statement)
        if dependencies is None or len(dependencies) != 1:
            return None
        (person,) = dependencies
        own = [step for step in steps if step.var == person]
        if not own:
            return None
        previous = set(self.options[person])
        self.conclusion(own)
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
                if holds_grounded(origin.statement, self.board, {person: cell}, dependencies)
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
        other = self.conclusion(step for step in steps if step.var != person)
        if other:
            said += " " + self.say("expression.by", sources=self.names(sources), conclusion=other)
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

    def conclusion(self, steps: Iterable[Step]) -> str | None:
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
            if person in placed:
                (square,) = cells
                if (person, square) not in self.told:
                    said.append(f"**{self.placed(person, square)}**")
                    self.told.add((person, square))
            elif cells != previous and cells:
                said.append(
                    "**" + self.places.describe(person, cells, previous, placing=False) + "**"
                )
        for step in steps:
            if step.var in self.roles:
                value = step.value if step.asserted else not step.value
                if (step.var, value) not in self.told:
                    said.append(f"**{self.placed(step.var, value)}**")
                    self.told.add((step.var, value))
        return self.say.join(said) if said else None

    def pattern(self, inference: Inference, history: Sequence[Step]) -> str:
        move = inference.move
        assert move is not None
        if move.rule == "what_if" and inference.steps[0].var in self.visible:
            paragraph = self._what_if(inference, history)
            self.conclusion(inference.steps)
            return paragraph
        conclusion = self.conclusion(inference.steps)
        if conclusion is None:
            return ""
        if move.rule == "chains" and all(var in self.visible for var, _ in move.chain):
            return self._chain(move.chain, conclusion)
        return self.say("expression.by", sources=self.names(move.sources), conclusion=conclusion)

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
                paragraphs.append(
                    self.say("expression.by", sources=self.names(sources), conclusion=conclusion)
                )
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
                if paragraph := (
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
                        paragraphs.append(
                            self.say(
                                "expression.by",
                                sources=self.names([*premises, *sources]),
                                conclusion=conclusion,
                            )
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
    return narrator.tell(start, groups, result.solution() is not None)
