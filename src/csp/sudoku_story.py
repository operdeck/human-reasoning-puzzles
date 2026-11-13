"""Pattern-first Sudoku explanations based on replayable solver deductions."""

from collections.abc import Sequence
from dataclasses import dataclass

from . import sudoku
from .core import Kind, Model, Solver, Step
from .proof import Episode, Inference, Move, episodes, replay, shortest
from .story import Wording


@dataclass(frozen=True)
class Explanation:
    """Narrative paragraphs and whether they account for the entire solution."""

    paragraphs: tuple[str, ...]
    complete: bool

    def markdown(self) -> str:
        return "\n\n".join(f"- {paragraph}" for paragraph in self.paragraphs)


@dataclass(frozen=True)
class _House:
    family: str
    cells: frozenset[str]
    digit: int
    label: str


class _Narrator:
    def __init__(self, puzzle: sudoku.Puzzle, model: Model, say: Wording) -> None:
        self.say = say
        self.cells = {
            sudoku.cell_name(row, col): say("square", row=row + 1, col=col + 1)
            for row in range(puzzle.size)
            for col in range(puzzle.size)
        }
        domains = {model.domain_of(cell): cell for cell in self.cells}
        self.domains = {model.constraints[index].name: cell for index, cell in domains.items()}

        houses: dict[frozenset[int], _House] = {}
        extras = {frozenset(cells): name for name, cells in puzzle.extra_houses().items()}
        for family, _, members in puzzle.houses():
            cells = frozenset(sudoku.cell_name(*cell) for cell in members)
            first = min(members)
            if family == "row":
                label = say("sudoku.row", number=first[0] + 1)
            elif family == "col":
                label = say("sudoku.column", number=first[1] + 1)
            elif family == "box":
                label = say("sudoku.box", cell=self.cells[sudoku.cell_name(*first)])
            else:
                label = say("sudoku.extra", name=extras[frozenset(members)])
            for digit in range(1, puzzle.size + 1):
                literals = frozenset(model.literal(cell, digit) for cell in cells)
                houses.setdefault(literals, _House(family, cells, digit, label))
        self.houses = {
            constraint.name: houses[frozenset(constraint.literals)]
            for constraint in model.constraints
            if constraint.kind is Kind.EXACTLY_ONE
            and constraint.index not in domains
            and frozenset(constraint.literals) in houses
        }

    def single(self, inference: Inference) -> str | None:
        step = next((step for step in inference.steps if step.asserted and not step.placing), None)
        if step is None or step.var not in self.cells or not step.sources:
            return None
        fields = {"cell": self.cells[step.var], "digit": step.value}
        if step.sources[0] in self.domains:
            return self.say("sudoku.single_cell", **fields)
        house = self.houses.get(step.sources[0])
        if house is not None:
            return self.say("sudoku.single_house", house=house.label, **fields)
        return None

    def pattern(self, inference: Inference) -> str | None:
        move = inference.move
        if move is None:
            return None
        if move.rule == "subsumption" and len(move.sources) == len(move.scope) == 1:
            source = self.houses.get(move.sources[0])
            target = self.houses.get(move.scope[0])
            if source is None or target is None or source.digit != target.digit:
                return None
            removed = [
                step.var
                for step in inference.steps
                if not step.asserted and step.value == source.digit and step.var in self.cells
            ]
            if not removed:
                return None
            if len(removed) == 1:
                conclusion = self.say(
                    "sudoku.cross_one", digit=source.digit, cell=self.cells[removed[0]]
                )
            else:
                conclusion = self.say("sudoku.cross_many", digit=source.digit, target=target.label)
            return self.say(
                "sudoku.locked",
                source=source.label,
                target=target.label,
                digit=source.digit,
                conclusion=conclusion,
            )

        if move.rule not in ("cover2", "cover3") or not move.sources or not move.scope:
            return None
        sources = [self.houses.get(name) for name in move.sources]
        targets = [self.houses.get(name) for name in move.scope]
        source_cells = [self.domains[name] for name in move.sources if name in self.domains]
        target_cells = [self.domains[name] for name in move.scope if name in self.domains]
        if len(source_cells) == len(move.sources) and all(targets):
            return self._naked(inference, source_cells, [house for house in targets if house])
        if len(target_cells) == len(move.scope) and all(sources):
            return self._hidden(
                inference, move.sources, [house for house in sources if house], target_cells
            )
        if all(sources) and all(targets):
            return self._fish(
                [house for house in sources if house], [house for house in targets if house]
            )
        return None

    def _naked(self, inference: Inference, cells: list[str], houses: list[_House]) -> str | None:
        if (
            len(cells) != len(houses)
            or len({house.cells for house in houses}) != 1
            or len({house.digit for house in houses}) != len(houses)
            or not set(cells) <= houses[0].cells
        ):
            return None
        digits = {house.digit for house in houses}
        options = {
            inference.before.value_of(literal)
            for cell in cells
            for literal in inference.before.options(cell)
        }
        if options != digits:
            return None
        return self.say(
            "sudoku.naked_set",
            house=houses[0].label,
            cells=self.say.join([self.cells[cell] for cell in cells]),
            digits=self.say.join([str(digit) for digit in sorted(digits)]),
        )

    def _hidden(
        self, inference: Inference, names: tuple[str, ...], houses: list[_House], cells: list[str]
    ) -> str | None:
        if (
            len(cells) != len(houses)
            or len({house.cells for house in houses}) != 1
            or len({house.digit for house in houses}) != len(houses)
            or not set(cells) <= houses[0].cells
        ):
            return None
        live = {
            inference.before.var_of(literal)
            for name in names
            for constraint in inference.before.constraints
            if constraint.name == name
            for literal in inference.before.live(constraint.index)
        }
        if live != set(cells):
            return None
        return self.say(
            "sudoku.hidden_set",
            house=houses[0].label,
            cells=self.say.join([self.cells[cell] for cell in cells]),
            digits=self.say.join([str(house.digit) for house in houses]),
        )

    def _fish(self, sources: list[_House], targets: list[_House]) -> str | None:
        if (
            len(sources) != len(targets)
            or len({house.digit for house in [*sources, *targets]}) != 1
            or {house.family for house in sources} not in ({"row"}, {"col"})
            or {house.family for house in targets}
            != ({"col"} if sources[0].family == "row" else {"row"})
            or len({house.cells for house in sources}) != len(sources)
            or len({house.cells for house in targets}) != len(targets)
        ):
            return None
        return self.say(
            "sudoku.fish",
            sources=self.say.join([house.label for house in sources]),
            targets=self.say.join([house.label for house in targets]),
            digit=sources[0].digit,
        )

    def tell(self, groups: Sequence[Episode], solved: bool, unavailable: str | None) -> Explanation:
        paragraphs: list[str] = []
        pending: list[Inference] = []

        def singles(final: bool) -> bool:
            descriptions = [self.single(inference) for inference in pending]
            if any(description is None for description in descriptions):
                return False
            if descriptions:
                shown = [description for description in descriptions[:2] if description]
                if len(descriptions) > 2:
                    shown.append(
                        self.say("sudoku.finish_singles" if final else "sudoku.continue_singles")
                    )
                paragraphs.append(" ".join([self.say("sudoku.singles"), *shown]))
            pending.clear()
            return True

        for group in groups:
            if group.pattern.rule == "single":
                pending.append(group.pattern)
                continue
            if not singles(False):
                unavailable = "single"
                break
            description = self.pattern(group.pattern)
            if description is None:
                unavailable = group.pattern.rule
                break
            paragraphs.append(description)
            pending.extend(group.consequences)
        else:
            if not singles(solved and unavailable is None):
                unavailable = "single"

        complete = solved and unavailable is None
        if unavailable is not None:
            names = {
                "single",
                "subsumption",
                "cover2",
                "cover3",
                "chains",
                "wing",
                "what_if",
                "relations",
                "count",
            }
            rule = self.say(f"sudoku.rule.{unavailable}") if unavailable in names else unavailable
            paragraphs.append(self.say("sudoku.unavailable", rule=rule))
        elif not solved:
            paragraphs.append(self.say("sudoku.stalled"))
        elif not paragraphs:
            paragraphs.append(self.say("sudoku.givens_complete"))
        return Explanation(tuple(paragraphs), complete)


def explain(
    text: str,
    *,
    start: Model | None = None,
    fired: Sequence[tuple[str, Sequence[Step]]] | None = None,
) -> Explanation:
    """Explain a solve without guessing at deductions that lack a known pattern."""
    if start is None and fired is None:
        start, puzzle = sudoku.compile_puzzle(text)
        history: list[tuple[str, Sequence[Step]]] = []
        Solver(start.clone()).solve(on_step=lambda rule, steps: history.append((rule, steps)))
        fired = history
    elif start is not None and fired is not None:
        puzzle = sudoku.parse(text)
    else:
        raise ValueError("start and fired must be supplied together")

    moves = [move for rule, steps in fired if (move := Move.of(rule, steps)) is not None]
    unsupported = next(
        (
            index
            for index, move in enumerate(moves)
            if move.rule not in {"subsumption", "cover2", "cover3"}
        ),
        None,
    )
    available = moves if unsupported is None else moves[:unsupported]
    if unsupported is None and replay(start, available).solution() is not None:
        available = shortest(start, available)
    result, groups = episodes(start, available)
    unavailable = moves[unsupported].rule if unsupported is not None else None
    return _Narrator(puzzle, start, Wording.read(text)).tell(
        groups, result.solution() is not None, unavailable
    )
