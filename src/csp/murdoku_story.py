"""Murdoku explanations from expression origins and the generic engine's proof."""

from collections.abc import Iterable, Sequence
from itertools import combinations
from typing import Any

from . import generic_story
from .core import Model, Solver, Step
from .murdoku import Board, Square, board_rules
from .murdoku_expression_file import load_expression_board
from .murdoku_expression_words import ExpressionWords
from .murdoku_lower import ExpressionCompilation, compile_statements_with_origins
from .proof import Episode, Inference, Move, episodes, replay
from .story import Places, Wording


class _Narrator(generic_story.Narrator):
    def __init__(
        self, text: str, board: Board, compilation: ExpressionCompilation, numbered: bool
    ) -> None:
        say = Wording.read(text).for_people(board.people)
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
        words = ExpressionWords.read(board, text)
        for origin in compilation.origins:
            label = say(f"expression.{origin.kind}", number=origin.number)
            statement = words.statement(origin.statement).rstrip(".")
            self.source_words[origin.label] = f"{label}: {statement}" if numbered else statement
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
        for sources, steps in initial.items():
            if conclusion := self.conclusion(steps):
                paragraphs.append(
                    self.say("expression.by", sources=self.names(sources), conclusion=conclusion)
                )
        history = list(self.compilation.model.log)
        support: list[str] = []
        for group in groups:
            for inference in (group.pattern, *group.consequences):
                sources = (
                    inference.move.sources
                    if inference.move is not None
                    else tuple(source for step in inference.steps for source in step.sources)
                )
                if not any(step.var in self.visible for step in inference.steps):
                    support.extend(sources)
                elif inference.move is not None and not support:
                    if paragraph := self.pattern(inference, history):
                        paragraphs.append(paragraph)
                else:
                    conclusion = self.conclusion(inference.steps)
                    if conclusion is not None:
                        paragraphs.append(
                            self.say(
                                "expression.by",
                                sources=self.names([*support, *sources]),
                                conclusion=conclusion,
                            )
                        )
                        support.clear()
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
