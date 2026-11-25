"""Find and check clue sets for a rooms plan against an author's brief.

A room puzzle is easy to make correct and hard to make well: the brief usually
asks for more than a unique answer — only plain spatial clues, no room aliased
twice, and one person discovered last. This searches for such a set and checks a
finished file against the same brief, so authors do not tune clauses by hand.

    uv run puzzle-lab rooms-clues plan.txt --clues 10 --kinds in,dir,beside,empty \
        --last Ada --output puzzle.txt
    uv run puzzle-lab rooms-check puzzle.txt --kinds in,dir,beside,empty --last Ada

A plan file is a rooms puzzle with a `Solution: Ada=a Ben=b` line and no clues.
"""

import random
import re
import time
from dataclasses import dataclass, field, replace

from . import bruteforce, report, rooms
from .bruteforce import rooms as brute
from .core import Model, Solver
from .puzzlefile import read_sections

KINDS = {
    "in": "a person is (not) in a room or group of rooms",
    "dir": "one person's room is directly north, east, south or west of another's",
    "beside": "two people share a room or stand in rooms that touch",
    "empty": "a room or group of rooms is empty, or is not",
    "together": "two people are together or apart",
    "alone": "a person stands alone or does not",
    "choice": "exactly one of two room clauses holds",
}
BRIEF_KINDS = frozenset(KINDS)
_AREA = re.compile(r"area:(\S+?)[\s);]|area:(\S+)$")


@dataclass(frozen=True)
class Brief:
    """What a clue set has to be: its size, its kinds, and who comes last."""

    clues: int = 10
    kinds: frozenset[str] = BRIEF_KINDS
    last: str | None = None
    aliases_once: bool = True
    attempts: int = 200
    seconds: float = 120.0
    seed: int = 0


@dataclass
class Finding:
    """One clue of a finished puzzle, with what it leaves and whether it is needed."""

    line: str
    kind: str
    share: float
    needed: bool
    pins: list[str] = field(default_factory=list)


def read_plan(text: str) -> tuple[str, dict[str, str]]:
    """The plan without its `Solution:` line, and the placement it states."""
    sections = read_sections(text)
    if "Solution" not in sections:
        raise ValueError("a plan file needs a 'Solution: Ada=a Ben=b' line")
    solution = dict(entry.split("=") for entry in " ".join(sections["Solution"]).split())
    surface = "\n".join(line for line in text.splitlines() if not line.startswith("Solution:"))
    return surface + "\n", solution


def plan_puzzle(text: str) -> tuple[str, dict[str, str], rooms.Puzzle]:
    """The plan text, its placement, and the puzzle object without clues."""
    surface, solution = read_plan(text)
    first = surface.split("Plan:\n")[1].split()[0]
    parsed = rooms.parse(surface + f"Clues:\ncount (people in area:{first}) >= 0\n")
    puzzle = replace(parsed, clues=(), wording={})
    for rule in puzzle.rules:
        if not rule.holds(solution, puzzle):
            raise ValueError(f"the plan breaks the rule {rule.describe(puzzle)!r}")
    return surface, solution, puzzle


def with_clues(surface: str, clues: list[str]) -> str:
    return surface + "Clues:\n" + "\n".join(clues) + "\n"


def placement_count(surface: str) -> int:
    """How many placements the plan allows before any clue."""
    first = surface.split("Plan:\n")[1].split()[0]
    return brute.count(with_clues(surface, [f"count (people in area:{first}) >= 0"]))


def kind_of(line: str) -> str:
    """The clue kind a line uses, named as `KINDS` names it."""
    if "dir:" in line:
        return "dir"
    if " beside " in line:
        return "beside"
    if line.startswith("count"):
        return "empty"
    if " alone" in line:
        return "alone"
    if " together " in line or " apart " in line:
        return "together"
    if line.startswith("exactly"):
        return "choice"
    return "in"


def area_of(line: str) -> str | None:
    """The area a clue names, if it names one."""
    match = _AREA.search(line)
    return next((group for group in match.groups() if group), None) if match else None


def allowed(line: str, brief: Brief) -> bool:
    """Whether a clue line fits the brief's kinds and its no-count rule."""
    kind = kind_of(line)
    if kind not in brief.kinds:
        return False
    if kind == "empty":
        # Only emptiness and non-emptiness; a specific number is a count clue.
        return bool(re.fullmatch(r"count \(people in area:\S+\) (= 0|>= 1)", line))
    return True


def areas_once(clues: list[str]) -> bool:
    """Whether no room or group is named by more than one clue."""
    named = [area for area in (area_of(line) for line in clues) if area]
    return len(named) == len(set(named))


def pins_someone(puzzle: rooms.Puzzle, line: str, header: str) -> list[str]:
    """People a single clue fixes in one room, once its own deductions are made."""
    model = rooms.compile_puzzle(header + "Clues:\n" + line + "\n")[0]
    Solver(model).solve()
    return [person for person in model.variables if len(model.options(person)) < 2]


def unique(surface: str, clues: list[str]) -> bool:
    return len(bruteforce.solutions(with_clues(surface, clues), "rooms", 2)) == 1


def needed(surface: str, clues: list[str]) -> bool:
    """Whether dropping any one clue leaves the answer open."""
    if not unique(surface, clues):
        return False
    return all(
        len(bruteforce.solutions(with_clues(surface, clues[:i] + clues[i + 1 :]), "rooms", 2)) > 1
        for i in range(len(clues))
    )


def solved(surface: str, clues: list[str]) -> Model:
    """The ladder's solve of a clue set, for its placement order."""
    model = rooms.compile_puzzle(with_clues(surface, clues))[0]
    Solver(model).solve()
    return model


def solve_report(text: str) -> tuple[bool, str, list[str]]:
    """Whether the ladder closes the puzzle, its grade, and the rules it fired."""
    model = rooms.compile_puzzle(text)[0]
    fired: list[str] = []
    result = Solver(model).solve(on_step=lambda rule, steps: fired.append(rule))
    return result.solved, (report.grade(fired) if result.solved else "unsolved"), fired


def placement_order(surface: str, clues: list[str]) -> list[str]:
    """The people the ladder fixes, in the order it fixes them."""
    model = rooms.compile_puzzle(with_clues(surface, clues))[0]
    order: list[str] = []

    def watch(rule: str, steps: object) -> None:
        for person in model.variables:
            if model.chosen(person) is not None and person not in order:
                order.append(person)

    Solver(model).solve(on_step=watch)
    return order


def placements_last(surface: str, clues: list[str], person: str) -> bool:
    """Whether `person` is the last clue-named person the ladder fixes.

    A seat can also fall to whoever is left over, or to a puzzle rule that fills a
    room. A late discovery means the answer itself is the last thing a clue
    settles, so only people some clue names are counted.
    """
    text = with_clues(surface, clues)
    named: set[str] = set()
    for clue in rooms.parse(text).clues:
        named |= rooms.people_of(clue)
    determined = [name for name in placement_order(surface, clues) if name in named]
    return bool(determined) and determined[-1] == person


def fits(brief: Brief, surface: str, puzzle: rooms.Puzzle, clues: list[str]) -> bool:
    """Whether a clue set is unique, every clue needed, and matches the brief."""
    if brief.aliases_once and not areas_once(clues):
        return False
    if any(pins_someone(puzzle, line, surface) for line in clues):
        return False
    if not unique(surface, clues) or not needed(surface, clues):
        return False
    return not brief.last or placements_last(surface, clues, brief.last)


def search(text: str, brief: Brief = Brief()) -> str | None:
    """Grow and thin a clue set until it fits the brief, or give up."""
    surface, placement, puzzle = plan_puzzle(text)
    pool = [
        line for _rank, line in rooms.candidate_clues(puzzle, placement) if allowed(line, brief)
    ]
    rng = random.Random(brief.seed)
    started = time.perf_counter()
    for _ in range(brief.attempts):
        if time.perf_counter() - started > brief.seconds:
            break
        chosen = rng.sample(pool, min(brief.clues, len(pool)))
        for line in rng.sample(pool, len(pool)):
            if unique(surface, chosen):
                break
            if line not in chosen:
                chosen.append(line)
        if not unique(surface, chosen):
            continue
        rng.shuffle(chosen)
        for line in list(chosen):
            fewer = [item for item in chosen if item != line]
            if fits(brief, surface, puzzle, fewer) or (
                unique(surface, fewer) and not (brief.aliases_once and not areas_once(fewer))
            ):
                chosen = fewer
        if len(chosen) > brief.clues:
            continue
        if fits(brief, surface, puzzle, chosen):
            return with_clues(surface, sorted(chosen))
    return None


def check(text: str, brief: Brief = Brief()) -> tuple[list[Finding], list[str]]:
    """Report every clue of a finished puzzle, and what the brief makes of it."""
    puzzle = rooms.parse(text)
    header, _, rest = text.partition("Clues:")
    lines = [line.strip() for line in rest.splitlines() if line.strip()]
    clues = [line.partition("|")[0].strip() for line in lines]
    end = next((index for index, line in enumerate(clues) if line.endswith(":")), len(clues))
    clues = clues[:end]
    base = placement_count(header)
    findings = []
    for clue in clues:
        share = brute.count(header + "Clues:\n" + clue + "\n") / base
        fewer = [item for item in clues if item != clue]
        still = len(bruteforce.solutions(header + "Clues:\n" + "\n".join(fewer) + "\n", "rooms", 2))
        findings.append(
            Finding(clue, kind_of(clue), share, still > 1, pins_someone(puzzle, clue, header))
        )
    problems = []
    if len(findings) > brief.clues:
        problems.append(f"{len(findings)} clues; the brief allows at most {brief.clues}")
    closed, _grade, _fired = solve_report(text)
    if not closed:
        problems.append("the ladder stalls on this clue set")
    for finding in findings:
        if finding.kind not in brief.kinds:
            problems.append(f"{finding.line!r} uses the kind {finding.kind!r}")
        elif not allowed(finding.line, brief):
            problems.append(f"{finding.line!r} gives a number; only empty or not empty is allowed")
        if not finding.needed:
            problems.append(f"{finding.line!r} is not needed")
        if finding.pins:
            problems.append(f"{finding.line!r} pins {', '.join(finding.pins)} on its own")
    if brief.aliases_once and not areas_once(clues):
        problems.append("an area is named by more than one clue")
    if brief.last and not placements_last(header, clues, brief.last):
        problems.append(f"{brief.last} is not the last person placed")
    return findings, problems
