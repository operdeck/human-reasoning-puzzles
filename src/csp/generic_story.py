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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .core import Model, Step
from .proof import HARDEST_FIRST, Episode, Inference, Move, episodes, essential, replay
from .story import Wording

SHOWN_SINGLES = 4  # placements named in one paragraph of singles
SHOWN_TRAIL = 4  # placements named on the way to a what-if contradiction
SHOWN_CLUES = 5  # clue deductions told in one paragraph
MAX_REPLAYS = 60  # proof replays spent thinning one explanation
_CELL = re.compile(r"^r(\d+)c(\d+)$")


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


class _Narrator:
    def __init__(self, model: Model, say: Wording) -> None:
        self.model = model
        self.say = say
        self.visible = set(model.variables)
        self.constraints = {c.name: c for c in model.constraints}
        self.domains = {model.constraints[model.domain_of(var)].name for var in model.all_variables}
        self.told: set[tuple[str, Any]] = set()

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

    def placed(self, var: str, value: Any, name: str | None = None) -> str:
        """`var` takes `value`; `name` says which cells when several share it."""
        if isinstance(value, bool) and self._boolean(var):
            return self.say("generic.yes" if value else "generic.no", var=name or var)
        return self.say("generic.placed", var=name or var, value=value)

    def negated(self, var: str, value: Any) -> str:
        if isinstance(value, bool) and self._boolean(var):
            return self.placed(var, not value)
        return self.say("generic.not_placed", var=var, value=value)

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
        alike: dict[tuple[Any, ...], list[str]] = {}
        for var, values in removed.items():
            if var not in settled:
                alike.setdefault(tuple(values), []).append(var)
        self.told.update(placements)
        together: dict[Any, list[str]] = {}
        for var, value in placements:
            together.setdefault(value, []).append(var)
        said = [
            f"**{self.placed(where[0], value, compress(where, self.say))}**"
            for value, where in together.items()
        ]
        said += [
            "**"
            + self.say(
                "generic.cannot_be",
                where=compress(where, self.say),
                values=self.say.join([str(v) for v in values], "or"),
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
        return self.say.join([f"*{name}*" for name in dict.fromkeys(sources)])

    # --- singles ----------------------------------------------------------

    def singles(self, inferences: Sequence[Inference], final: bool) -> str | None:
        found: list[tuple[str, Any]] = []
        rules: list[str] = []
        for inference in inferences:
            for step in inference.steps:
                if not step.asserted or step.placing is not None or step.var not in self.visible:
                    continue
                if (step.var, step.value) in self.told:
                    continue
                self.told.add((step.var, step.value))
                found.append((step.var, step.value))
                source = next(
                    (s for s in step.sources if not self._yes_or_no(s)),
                    None,
                )
                if source is not None:
                    rules.append(self.rule_of(source))
        if not found:
            return None
        together: dict[Any, list[str]] = {}
        for var, value in found:
            together.setdefault(value, []).append(var)
        placements = [
            f"**{self.placed(where[0], value, compress(where, self.say))}**"
            for value, where in together.items()
        ]
        shown = placements[:SHOWN_SINGLES]
        more = sum(len(where) for where in list(together.values())[SHOWN_SINGLES:])
        listed = self.say.join(shown)
        if more:
            key = "generic.singles_rest" if final else "generic.singles_more"
            if more == 1:
                key += "_one"
            listed = self.say(key, placements=", ".join(shown), count=more)
        if not rules:
            return self.say("generic.singles_plain", placements=listed)
        return self.say("generic.singles", rules=self.names(rules), placements=listed)

    # --- patterns ---------------------------------------------------------

    def pattern(self, inference: Inference, history: Sequence[Step]) -> str:
        move = inference.move
        assert move is not None
        if move.rule == "what_if":
            return self._what_if(inference, history)
        conclusion = self.conclusion(inference.steps) or self.say("generic.internal")
        sources = self.names(move.sources)
        if move.rule in ("count", "relations"):
            clue = self.say("generic.clue", sources=sources, conclusion=conclusion)
            return self.say("generic.clues", items=clue)
        if move.rule == "subsumption":
            return self.say(
                "generic.subsumption",
                sources=sources,
                scope=self.names(move.scope),
                conclusion=conclusion,
            )
        if move.rule in ("cover2", "cover3"):
            return self.say(
                "generic.cover",
                sources=self._sets(move.sources),
                scope=self._sets(move.scope),
                conclusion=conclusion,
            )
        if move.rule == "chains":
            return self._chain(move.chain, conclusion)
        if move.rule == "wing":
            return self.say(
                "generic.wing",
                options=self.say.join([self.placed(*pair) for pair in move.chain], "or"),
                conclusion=conclusion,
            )
        return self.say("generic.other", rule=move.rule, conclusion=conclusion)

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

    def _chain(self, chain: Sequence[tuple[str, Any]], conclusion: str) -> str:
        """A chain starts from its first option false; links alternate true and false.

        A cell that just took a value obviously lost its others, so that link
        goes unsaid.
        """
        links = [
            self.placed(*pair) if i % 2 else self.negated(*pair)
            for i, pair in enumerate(chain[1:], start=1)
            if i % 2 or pair[0] != chain[i - 1][0] or self._boolean(pair[0])
        ]
        return self.say(
            "generic.chain",
            start=self.negated(*chain[0]),
            first=self.placed(*chain[0]),
            last=self.placed(*chain[-1]),
            links=self.say("generic.chain_link").join(links),
            conclusion=conclusion,
        )

    def _what_if(self, inference: Inference, history: Sequence[Step]) -> str:
        step = next(step for step in inference.steps if step.rule == "what_if")
        needed = essential(self.model, history, step)
        shown: list[str] = []
        for j in needed:
            inner = step.trail[j]
            if j == 0 or not inner.asserted or inner.var not in self.visible:
                continue
            option = self.placed(inner.var, inner.value)
            if option not in shown:
                shown.append(option)
        trail = shown[:SHOWN_TRAIL]
        more = len(shown) - len(trail)
        broken = step.sources[0] if step.sources else None
        breaks = (
            self.say("generic.breaks", source=f"*{broken}*")
            if broken is not None
            else self.say("generic.breaks_unknown")
        )
        assumed = self.placed(step.var, step.value)
        refuted = self.negated(step.var, step.value)
        if not trail:
            return self.say(
                "generic.what_if_direct", assumed=assumed, breaks=breaks, refuted=refuted
            )
        if more:
            listed = self.say("generic.trail_more", placements=", ".join(trail), count=more)
        else:
            listed = self.say.join(trail)
        return self.say(
            "generic.what_if", assumed=assumed, trail=listed, breaks=breaks, refuted=refuted
        )

    # --- the whole story ---------------------------------------------------

    def tell(self, start: Model, groups: Sequence[Episode], solved: bool) -> Explanation:
        paragraphs: list[str] = []
        pending: list[Inference] = []
        clues: list[str] = []
        history: list[Step] = list(start.log)

        def flush(final: bool) -> None:
            text = self.singles(pending, final and solved)
            pending.clear()
            if clues and (text is not None or final or len(clues) >= SHOWN_CLUES):
                paragraphs.append(self.say("generic.clues", items="; ".join(clues)))
                clues.clear()
            if text is not None:
                paragraphs.append(text)

        for group in groups:
            move = group.pattern.move
            if group.pattern.rule == "single":
                pending.append(group.pattern)
            elif move is not None and move.rule in ("count", "relations"):
                flush(False)
                conclusion = self.conclusion(group.pattern.steps) or self.say("generic.internal")
                clues.append(
                    self.say(
                        "generic.clue", sources=self.names(move.sources), conclusion=conclusion
                    )
                )
                pending.extend(group.consequences)
            else:
                flush(False)
                if clues:
                    paragraphs.append(self.say("generic.clues", items="; ".join(clues)))
                    clues.clear()
                paragraphs.append(self.pattern(group.pattern, history))
                pending.extend(group.consequences)
            for inference in (group.pattern, *group.consequences):
                history.extend(inference.steps)
        flush(True)
        if not solved:
            paragraphs.append(self.say("generic.stalled"))
        elif not paragraphs:
            paragraphs.append(self.say("generic.givens_complete"))
        return Explanation(tuple(paragraphs), solved)


def thin(start: Model, moves: Sequence[Move], budget: int = MAX_REPLAYS) -> list[Move]:
    """Drop as many moves as still solve the puzzle, hardest rules first, in at most
    `budget` replays.

    `proof.shortest` tries moves one at a time, which takes minutes when a
    puzzle fires hundreds of small clue deductions. This tries large blocks of
    one rule first and halves them, so the many unneeded clue firings usually
    go in a few replays. The budget counts replays, not seconds, so the same
    puzzle always gets the same story.
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
                if replay(start, fewer).solution() is not None:
                    kept = fewer
            size //= 2
    return kept


def explain(text: str, start: Model, fired: Sequence[tuple[str, Sequence[Step]]]) -> Explanation:
    """Explain a solve of any compiled model from its rule firings, shortest proof first.

    `start` is the compiled model before solving and `fired` what the solver
    reported, rule by rule. `text` gives the puzzle's language.
    """
    moves = [move for rule, steps in fired if (move := Move.of(rule, steps)) is not None]
    if replay(start, moves).solution() is not None:
        moves = thin(start, moves)
    result, groups = episodes(start, moves)
    return _Narrator(start, Wording.read(text)).tell(start, groups, result.solution() is not None)
