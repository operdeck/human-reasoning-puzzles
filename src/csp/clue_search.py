"""Search tools for designing Murdoku clue sets, so authors need no throwaway scripts.

Run as `uv run python -m csp.clue_search COMMAND FILE`:

- `report`: for every numbered clue, what the puzzle becomes without it
  (solution count and grade). A clue whose removal keeps one solution is
  redundant for uniqueness.
- `thin`: greedily drop clues while the puzzle stays unique and solved,
  optionally within `--max-grade`; `--keep` protects clue numbers.
- `suggest`: given the intended placement (`--solution "Ada=r1c2 Ben=r3c4"`),
  list simple clues that are true for it and greedily add the ones that rule
  out the most other placements until the puzzle is unique. `--needs` names
  clue numbers that must each stay necessary, so a themed clue (or a rule
  moved into the clues while searching) cannot be made redundant.

- `occupancy`: how often each object square is used across the placements the
  puzzle still allows (up to `--sample`). A decoy that is never used, or a
  square that is always used, cannot make a clue about that object matter.

Every solve runs in a child process with a hard `--timeout` (seconds); a
timeout counts as "not good enough" and is reported as such. The tools only
print; they never write puzzle files.
"""

import argparse
import multiprocessing
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import murdoku, report
from .bruteforce import murdoku as brute
from .core import DEFAULT_RULES, Solver
from .puzzlefile import load_board, parse_square

GRADES = tuple(rule.name for rule in DEFAULT_RULES)

# Clue kinds `suggest` may propose, most preferred first: area and object clues
# read better for people than exact distances.
SUGGEST_KINDS = (
    "in_region",
    "next_to",
    "on",
    "at",
    "not_next_to",
    "outside",
    "same_region",
    "different_region",
    "left_of",
    "above",
)

_SECTION = re.compile(r"^[A-Za-z]+:\s*$")


@dataclass(frozen=True)
class Outcome:
    """A puzzle's solution count (0, 1 or 2 meaning "more") and grade; None on timeout."""

    solutions: int | None
    grade: str | None

    @property
    def good(self) -> bool:
        return self.solutions == 1 and self.grade not in (None, "unsolved")

    def __str__(self) -> str:
        count = {None: "timeout", 0: "none", 1: "unique", 2: "several"}[self.solutions]
        return f"{count}, grade {self.grade or 'timeout'}"


def clue_lines(text: str) -> list[str]:
    """The `Clues:` section's clue lines, in order, as written (with any `| wording`)."""
    lines, inside = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if _SECTION.match(line):
            inside = line == "Clues:"
            continue
        if inside and line and not line.startswith("#"):
            lines.append(line)
    return lines


def with_clues(text: str, clues: Sequence[str]) -> str:
    """`text` with its `Clues:` section replaced by `clues` (added at the end if missing)."""
    out, inside, done = [], False, False
    for raw in text.splitlines():
        line = raw.strip()
        if _SECTION.match(line):
            if inside:
                inside = False
            if line == "Clues:":
                out.append(raw)
                out.extend(clues)
                inside = done = True
                continue
        if inside and line and not line.startswith("#"):
            continue
        out.append(raw)
    if not done:
        out += ["Clues:", *clues]
    return "\n".join(out) + "\n"


def _measure(text: str) -> tuple[int, str]:
    count = len(brute.solutions(text, 2))
    board, clues = load_board(text)
    fired: list[str] = []
    result = Solver(murdoku.compile_puzzle(board, clues)).solve(
        on_step=lambda rule, steps: fired.append(rule)
    )
    return count, report.grade(fired) if result.solved else "unsolved"


def _child(text: str, queue: Any) -> None:
    try:
        queue.put(_measure(text))
    except ValueError as error:
        queue.put(error)


def outcome(text: str, timeout: float = 5.0) -> Outcome:
    """Solution count and grade of `text`, measured in a child process killed after `timeout`."""
    context: Any = multiprocessing.get_context(
        "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
    )
    queue = context.Queue()
    process = context.Process(target=_child, args=(text, queue), daemon=True)
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.kill()
        process.join()
        return Outcome(None, None)
    result = queue.get() if not queue.empty() else None
    if isinstance(result, ValueError):
        raise result
    if result is None:
        return Outcome(None, None)
    return Outcome(*result)


def removal_report(text: str, timeout: float = 5.0) -> list[tuple[int, str, Outcome]]:
    """For each clue number: the clue and the puzzle's outcome without it."""
    lines = clue_lines(text)
    return [
        (number, line, outcome(with_clues(text, lines[: number - 1] + lines[number:]), timeout))
        for number, line in enumerate(lines, 1)
    ]


def _within(grade: str | None, max_grade: str | None) -> bool:
    if max_grade is None or grade is None:
        return True
    return grade in GRADES and GRADES.index(grade) <= GRADES.index(max_grade)


def thin(
    text: str,
    keep: Iterable[int] = (),
    max_grade: str | None = None,
    timeout: float = 5.0,
    log: Callable[[str], None] = lambda _line: None,
) -> list[str]:
    """Clue lines left after greedily dropping each removable clue, last clue first.

    A clue is dropped when the puzzle stays unique, solved and within
    `max_grade` without it. Clue numbers in `keep` are never dropped.
    """
    lines = clue_lines(text)
    kept = set(keep)
    alive = list(range(1, len(lines) + 1))
    for number in reversed(alive[:]):
        if number in kept:
            continue
        trial = [lines[n - 1] for n in alive if n != number]
        result = outcome(with_clues(text, trial), timeout)
        if result.good and _within(result.grade, max_grade):
            alive.remove(number)
            log(f"dropped {number}: {lines[number - 1]} ({result})")
    return [lines[n - 1] for n in alive]


def parse_solution(spec: str) -> dict[str, murdoku.Square]:
    """'Ada=r1c2 Ben=r3c4' -> {'Ada': Square(0, 1), 'Ben': Square(2, 3)}."""
    placement = {}
    for token in spec.replace(",", " ").split():
        person, _, square = token.partition("=")
        placement[person] = parse_square(square)
    return placement


def _true_for(board: murdoku.Board, clue: str, placement: dict[str, murdoku.Square]) -> bool:
    kind, *args = clue.split()
    try:
        checks = murdoku.conditions(board, [(kind, args)])
    except ValueError:
        return False
    return bool(checks) and all(
        check.test(*(placement[p] for p in check.people)) for check in checks
    )


def candidate_clues(
    board: murdoku.Board,
    placement: dict[str, murdoku.Square],
    kinds: Sequence[str] = SUGGEST_KINDS,
    exclude: Iterable[str] = (),
) -> list[str]:
    """Simple clues of `kinds` that are true for `placement`, in `kinds` order.

    People in `exclude` (a late-reveal person) appear in none of them.
    """
    people = [person for person in placement if person not in set(exclude)]
    regions = sorted(set(board.region_names.values()))
    things = sorted(board.object_names | board.edge_item_names | board.point_object_names)
    standable = sorted({o.name for o in board.objects if o.kind == "standable"})
    edges = sorted(board.edge_item_names)
    pairs = [(a, b) for a in people for b in people if a != b]
    options: dict[str, list[str]] = {
        "in_region": [f"in_region {p} {r}" for p in people for r in regions],
        "outside": [f"outside {p} {r}" for p in people for r in regions],
        "next_to": [f"next_to {p} {t}" for p in people for t in things],
        "not_next_to": [f"not_next_to {p} {t}" for p in people for t in things],
        "on": [f"on {p} {t}" for p in people for t in standable],
        "at": [f"at {p} {t}" for p in people for t in edges],
        "same_region": [f"same_region {a} {b}" for a, b in pairs if a < b],
        "different_region": [f"different_region {a} {b}" for a, b in pairs if a < b],
        "left_of": [f"left_of {a} {b}" for a, b in pairs],
        "above": [f"above {a} {b}" for a, b in pairs],
    }
    found = (clue for kind in kinds for clue in options.get(kind, []))
    return [clue for clue in found if _true_for(board, clue, placement)]


def _satisfies(text: str, placement: dict[str, murdoku.Square]) -> bool:
    """Whether `placement` meets every rule and clue of `text` that needs no roles."""
    board, clues = load_board(text)
    simple = all(
        check.test(*(placement[person] for person in check.people))
        for check in murdoku.conditions(board, clues)
    )
    targets = all(
        condition.holds(board, placement, {})
        for condition in murdoku.quantified_conditions(board, clues)
    )
    counts = all(
        condition.count(board, placement, {}) in condition.allowed_counts
        for condition in murdoku.global_count_conditions(board, clues)
    )
    return simple and targets and counts


def _placement(solution: dict[str, Any], people: Sequence[str]) -> dict[str, murdoku.Square]:
    return {person: solution[person] for person in people}


def suggest(
    text: str,
    placement: dict[str, murdoku.Square],
    kinds: Sequence[str] = SUGGEST_KINDS,
    sample: int = 400,
    timeout: float = 5.0,
    log: Callable[[str], None] = lambda _line: None,
    exclude: Iterable[str] = (),
    needs: Iterable[int] = (),
) -> list[str]:
    """Clues to add to `text` so that `placement` becomes its only solution.

    Each round samples up to `sample` solutions of the current puzzle and adds
    the true candidate clue that rules out most other placements (earlier
    `kinds` win ties). Stops when unique, or when no candidate helps.

    `needs` lists clue numbers that must each remain necessary. A clue's rivals
    are the placements allowed without it that break it (role clues are not
    checked); a candidate that would rule out every rival of some needed clue
    is skipped, so removing any one of them still leaves another solution.
    """
    board, _ = load_board(text)
    unknown = set(board.people) ^ set(placement)
    if unknown:
        raise ValueError(f"--solution must place exactly the people {board.people}")
    candidates = candidate_clues(board, placement, kinds, exclude)
    lines = clue_lines(text)
    needed = sorted(set(needs))
    if bad := [n for n in needed if not 1 <= n <= len(lines)]:
        raise ValueError(f"--needs names clue numbers {bad}; the puzzle has {len(lines)} clues")
    added: list[str] = []
    while True:
        current = with_clues(text, lines + added)
        others = [_placement(found, board.people) for found in brute.solutions(current, sample)]
        others = [other for other in others if other != placement]
        rival_sets: list[list[dict[str, murdoku.Square]]] = []
        for number in needed:
            without = with_clues(text, lines[: number - 1] + lines[number:] + added)
            only = with_clues(text, [lines[number - 1]])
            found = [_placement(f, board.people) for f in brute.solutions(without, sample)]
            rivals = [
                other for other in found if other != placement and not _satisfies(only, other)
            ]
            if not rivals:
                log(f"needed clue {number} is already redundant; add fewer clues first")
                return added
            rival_sets.append(rivals)
        if not others:
            result = outcome(current, timeout)
            log(f"unique with {len(added)} added clues ({result})")
            return added
        best, best_cut = None, 0
        for clue in candidates:
            if clue in lines or clue in added:
                continue
            if any(
                not any(_true_for(board, clue, rival) for rival in rivals) for rivals in rival_sets
            ):
                continue
            cut = sum(not _true_for(board, clue, other) for other in others)
            if cut > best_cut:
                best, best_cut = clue, cut
        if best is None:
            log(f"stuck: {len(others)} other placements remain and no candidate separates them")
            for other in others[:3]:
                moved = {p: str(sq) for p, sq in other.items() if sq != placement[p]}
                log(f"  e.g. {moved}")
            return added
        added.append(best)
        log(f"add {best} (rules out {best_cut} of {len(others)} sampled placements)")


def occupancy(text: str, sample: int = 400) -> tuple[int, list[tuple[str, str, int]]]:
    """(placements seen, [(object, square, times occupied)]) over the allowed placements."""
    board, _ = load_board(text)
    found = brute.solutions(text, sample)
    used = [{found_one[person] for person in board.people} for found_one in found]
    rows = [
        (obj.name, str(square), sum(square in squares for squares in used))
        for obj in board.objects
        if obj.kind == "standable"
        for square in obj.squares
    ]
    return len(found), rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m csp.clue_search", description=__doc__)
    parser.add_argument("command", choices=("report", "thin", "suggest", "occupancy"))
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds per trial")
    parser.add_argument("--keep", type=int, nargs="*", default=[], help="thin: clue numbers")
    parser.add_argument("--max-grade", choices=GRADES, help="thin: hardest grade allowed")
    parser.add_argument("--solution", help='suggest: intended placement, "Ada=r1c2 Ben=r3c4"')
    parser.add_argument(
        "--kinds", nargs="*", default=list(SUGGEST_KINDS), help="suggest: clue kinds to try"
    )
    parser.add_argument(
        "--exclude", nargs="*", default=[], help="suggest: people no clue may mention"
    )
    parser.add_argument("--sample", type=int, default=400, help="suggest: solutions per round")
    parser.add_argument(
        "--needs",
        type=int,
        nargs="*",
        default=[],
        help="suggest: clue numbers that must stay needed",
    )
    args = parser.parse_args(argv)
    text = args.puzzle.read_text()
    if args.command == "occupancy":
        seen, rows = occupancy(text, args.sample)
        print(f"{seen} placements{' (sample limit)' if seen >= args.sample else ''}")
        for name, square, times in rows:
            note = "  <- never" if times == 0 else "  <- always" if times == seen else ""
            print(f"{name:20} {square:6} {times:5}{note}")
        return 0
    print(f"start: {outcome(text, args.timeout)}")
    if args.command == "report":
        for number, line, result in removal_report(text, args.timeout):
            note = "  <- removable" if result.good else ""
            print(f"{number:3}. {line}\n     without it: {result}{note}")
        return 0
    if args.command == "thin":
        kept = thin(text, args.keep, args.max_grade, args.timeout, print)
        print(f"result: {outcome(with_clues(text, kept), args.timeout)}\nClues:")
        print("\n".join(kept))
        return 0
    if not args.solution:
        parser.error("suggest needs --solution")
    placement = parse_solution(args.solution)
    added = suggest(
        text, placement, args.kinds, args.sample, args.timeout, print, args.exclude, args.needs
    )
    print("Clues to add:")
    print("\n".join(added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
