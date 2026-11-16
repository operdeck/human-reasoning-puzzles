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
  moved into the clues while searching, role rules included) cannot be made
  redundant. `--needs-mark` likewise preserves the occupancy effects of
  named marks. `--cover` then swaps added clues for clues about people no
  clue names, so every figure outside `--exclude` gets a clue.
  `--exclude-target` keeps decorative objects out of the suggestions.
- `ease`: add true clues to a unique puzzle until it is within `--max-grade`,
  keeping each `--needs` clue and `--needs-mark` effect necessary.
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
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from queue import Empty
from typing import Any

from . import murdoku, report
from .bruteforce import murdoku as brute
from .bruteforce import murdoku_expr as expression_brute
from .core import DEFAULT_RULES, Model, Solver
from .murdoku_expression_file import keyed_expression_clue_numbers, load_expression_board
from .murdoku_lang import Name, Statement, format_statement, holds, parse_statement
from .murdoku_lower import compile_statements
from .puzzlefile import (
    keyed_clue_numbers,
    load_board,
    load_board_layout,
    parse_clue_line,
    parse_square,
)

GRADES = tuple(rule.name for rule in DEFAULT_RULES)

# Clue kinds `suggest` may propose, most preferred first: area and object clues
# read better for people than exact distances.
SUGGEST_KINDS = (
    "in",
    "beside",
    "on",
    "not in",
    "not beside",
    "not on",
    "touches",
    "not touches",
    "dir",
)
EXTRA_KINDS = ("line",)

_SECTION = re.compile(r"^[A-Za-z]+:\s*$")


@dataclass(frozen=True)
class Outcome:
    """A puzzle's solution count, grade and optional late-figure check; None on timeout."""

    solutions: int | None
    grade: str | None
    late_last: bool | None = None

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


def without_mark_condition(text: str, name: str) -> str:
    """Keep a mark's cells but remove its occupancy effect for an ablation."""
    board = load_board_layout(text)
    mark = next((mark for mark in board.marks if mark.name == name), None)
    if mark is None or mark.occupant_condition is None:
        raise ValueError(f"mark {name!r} has no occupancy condition")
    inside = False
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if _SECTION.match(line):
            inside = line == "Marks:"
        if inside and line.partition(":")[0].strip() == name:
            raw = raw.partition(";")[0].rstrip()
        out.append(raw)
    return "\n".join(out) + "\n"


def _measure(text: str, late_person: str | None) -> tuple[str, bool | None]:
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    return _measure_model(board, model, late_person)


def _measure_expression(text: str, late_person: str | None) -> tuple[str, bool | None]:
    board, rules, clues = load_expression_board(text)
    return _measure_model(board, compile_statements(board, clues, rules=rules), late_person)


def _measure_model(
    board: murdoku.Board, model: Model, late_person: str | None
) -> tuple[str, bool | None]:
    domains = (
        {
            person: {model.value_of(literal) for literal in model.options(person)}
            for person in board.people
        }
        if late_person is not None
        else {}
    )
    initial_domains = {person: set(options) for person, options in domains.items()}
    fired: list[str] = []
    result = Solver(model).solve(on_step=lambda rule, steps: fired.append(rule))
    late_last = None
    if late_person is not None:
        first_singleton = {person: -1 for person, options in domains.items() if len(options) == 1}
        for index, step in enumerate(model.log):
            if step.var not in domains:
                continue
            if step.asserted:
                domains[step.var] = {step.value}
            else:
                domains[step.var].discard(step.value)
            if len(domains[step.var]) == 1:
                first_singleton.setdefault(step.var, index)
        other_resolutions = [
            index for person, index in first_singleton.items() if person != late_person
        ]
        late_last = (
            result.solved
            and late_person in initial_domains
            and len(initial_domains[late_person]) > 1
            and len(first_singleton) == len(board.people)
            and bool(other_resolutions)
            and first_singleton[late_person] > max(other_resolutions)
        )
    return report.grade(fired) if result.solved else "unsolved", late_last


def _child(
    text: str, late_person: str | None, queue: Any, *, grading: bool, expressions: bool
) -> None:
    try:
        result: int | tuple[str, bool | None]
        if grading:
            result = (
                _measure_expression(text, late_person)
                if expressions
                else _measure(text, late_person)
            )
        elif expressions:
            board, rules, clues = load_expression_board(text)
            result = len(expression_brute.solutions(board, clues, 2, rules=rules))
        else:
            result = len(brute.solutions(text, 2))
        queue.put(result)
    except ValueError as error:
        queue.put(error)


def _timed(
    text: str, timeout: float, late_person: str | None, *, grading: bool, expressions: bool = False
) -> Any:
    context: Any = multiprocessing.get_context(
        "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
    )
    queue = context.Queue()
    process = context.Process(
        target=_child,
        args=(text, late_person, queue),
        kwargs={"grading": grading, "expressions": expressions},
        daemon=True,
    )
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.kill()
        process.join()
        queue.close()
        return None
    try:
        result = queue.get(timeout=1)
    except Empty as error:
        raise RuntimeError(
            f"clue search worker exited without a result: {process.exitcode}"
        ) from error
    finally:
        queue.close()
    if isinstance(result, ValueError):
        raise result
    return result


def outcome(
    text: str, timeout: float = 5.0, late_person: str | None = None, *, expressions: bool = False
) -> Outcome:
    """Measure solutions and grade with separate timeouts for the two solvers."""
    count = _timed(text, timeout, late_person, grading=False, expressions=expressions)
    if count is None:
        return Outcome(None, None)
    grade = _timed(text, timeout, late_person, grading=True, expressions=expressions)
    if grade is None:
        return Outcome(count, None)
    return Outcome(count, *grade)


def removal_report(
    text: str, timeout: float = 5.0, *, expressions: bool = False
) -> list[tuple[int, str, Outcome]]:
    """For each clue: the outcome without it, or the current outcome if Key requires it."""
    lines = clue_lines(text)
    keyed = (keyed_expression_clue_numbers if expressions else keyed_clue_numbers)(text)
    current = outcome(text, timeout, expressions=expressions) if keyed else None
    return [
        (
            number,
            line,
            current
            if number in keyed and current is not None
            else outcome(
                with_clues(text, lines[: number - 1] + lines[number:]),
                timeout,
                expressions=expressions,
            ),
        )
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
    *,
    expressions: bool = False,
) -> list[str]:
    """Clue lines left after greedily dropping each removable clue, last clue first.

    A clue is dropped when the puzzle stays unique, solved and within
    `max_grade` without it. Clue numbers in `keep` and `Key:` are never dropped.
    """
    lines = clue_lines(text)
    kept = set(keep) | (keyed_expression_clue_numbers if expressions else keyed_clue_numbers)(text)
    alive = list(range(1, len(lines) + 1))
    for number in reversed(alive[:]):
        if number in kept:
            continue
        trial = [lines[n - 1] for n in alive if n != number]
        result = outcome(with_clues(text, trial), timeout, expressions=expressions)
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
    try:
        parsed = [parse_clue_line(clue)]
        checks = murdoku.conditions(board, parsed) + murdoku.directional_conditions(
            board, parsed, include_rules=False
        )
    except ValueError:
        return False
    return bool(checks) and all(
        check.holds(board, placement, {})
        if isinstance(check, murdoku.DirectionCondition)
        else check.test(*(placement[p] for p in check.people))
        for check in checks
    )


def candidate_clues(
    board: murdoku.Board,
    placement: dict[str, murdoku.Square],
    kinds: Sequence[str] = SUGGEST_KINDS,
    exclude: Iterable[str] = (),
    exclude_targets: Iterable[str] = (),
) -> list[str]:
    """Simple clues of `kinds` that are true for `placement`, in `kinds` order.

    People in `exclude` (a late-reveal person) and targets in `exclude_targets`
    (decorative objects) appear in none of them.
    """
    people = [person for person in placement if person not in set(exclude)]
    regions = sorted(set(board.region_names.values()))
    tags = sorted(board.area_tags)
    locations = (
        [*(f"area:{name}" for name in regions), *(f"tag:{name}" for name in tags)]
        + [f"object:{name}" for name in sorted(board.object_names)]
        + [f"mark:{mark.name}" for mark in board.marks]
        + [f"edge_item:{name}" for name in sorted(board.edge_item_names)]
        + [f"point_object:{name}" for name in sorted(board.point_object_names)]
        + ["corner:board"]
        + [f"corner:area:{name}" for name in regions]
    )
    adjacent_locations = [f"object:{name}" for name in sorted(board.object_names)] + [
        f"object_kind:{kind}" for kind in ("blocking", "standable")
    ]
    people_pairs = [(a, b) for a in people for b in people if a != b]
    attribute_selectors = sorted(f"attribute:{name}" for name in board.attributes)
    position_selectors = people + attribute_selectors
    position_pairs = [(a, b) for a in position_selectors for b in position_selectors if a != b]
    lines = range(1, board.size + 1)
    directional = (
        [
            f"dir {a} {b} {mode}"
            for a, b in position_pairs
            for mode in ("left", "right", "up", "down", "knight")
        ]
        + [f"dir {a} {b} furthest" for a, b in people_pairs]
        + [f"dir {a} {b} areas = 0" for a, b in position_pairs]
        + [f"dir {a} {b} areas >= 1" for a, b in position_pairs]
        + [
            f"dir {a} {b} {mode} {comparison} {distance}"
            for a, b in position_pairs
            for mode, comparisons in (
                ("rows", ("<=", ">=")),
                ("cols", ("<=", ">=")),
                ("manhattan", ("<=", ">=")),
                ("euclidean", ("=",)),
                ("king", (">=",)),
                ("areas", ("=",)),
            )
            for comparison in comparisons
            for distance in (1, 2, 3)
        ]
    )
    options: dict[str, list[str]] = {
        "in": [f"in {p} {location}" for p in people for location in locations],
        "not in": [f"not in {p} {location}" for p in people for location in locations],
        "line": [
            f"{predicate} {person} {selector}"
            for predicate in ("in", "not in")
            for person in people
            for selector in (
                *(f"rows:{n}" for n in lines),
                *(f"columns:{n}" for n in lines),
            )
        ],
        "on": [
            f"on {p} {selector}"
            for p in people
            for selector in locations
            if selector.split(":", 1)[0] in ("object", "mark", "edge_item", "point_object")
        ],
        "not on": [
            f"not on {p} {selector}"
            for p in people
            for selector in locations
            if selector.split(":", 1)[0] in ("object", "mark", "edge_item", "point_object")
        ],
        "beside": [f"beside {p} {selector}" for p in people for selector in adjacent_locations],
        "not beside": [
            f"not beside {p} {selector}" for p in people for selector in adjacent_locations
        ],
        "touches": [
            f"touches {p} {selector}"
            for p in people
            for selector in locations
            if selector.split(":", 1)[0] in ("object", "mark", "edge_item", "point_object")
        ],
        "not touches": [
            f"not touches {p} {selector}"
            for p in people
            for selector in locations
            if selector.split(":", 1)[0] in ("object", "mark", "edge_item", "point_object")
        ],
        "dir": directional,
    }
    if unknown := [kind for kind in kinds if kind not in options]:
        raise ValueError(f"unknown clue kinds {unknown}; choose from {sorted(options)}")
    targets = set(exclude_targets)
    found = (clue for kind in kinds for clue in options.get(kind, []))
    return [
        clue
        for clue in found
        if not (
            targets
            and any(
                targets.intersection(token.split(":"))
                for token in clue.split("|")[0].split()
                if ":" in token
            )
        )
        and _true_for(board, clue, placement)
    ]


def expression_candidate_clues(
    board: murdoku.Board,
    placement: dict[str, murdoku.Square],
    kinds: Sequence[str] = SUGGEST_KINDS,
    exclude: Iterable[str] = (),
    exclude_targets: Iterable[str] = (),
) -> list[Statement]:
    """Generate typed, true expression clues directly from named-person templates."""
    if set(placement) != set(board.people):
        raise ValueError(f"placement must name exactly the people {board.people}")
    unknown = set(kinds) - set(SUGGEST_KINDS) - set(EXTRA_KINDS)
    if unknown:
        raise ValueError(f"unknown clue kinds {sorted(unknown)}")
    excluded = set(exclude)
    people = [person for person in board.people if person not in excluded]
    blocked_targets = set(exclude_targets)
    areas = [
        ("area", name)
        for name in sorted(set(board.region_names.values()))
        if name not in blocked_targets
    ] + [("tag", name) for name in sorted(board.area_tags) if name not in blocked_targets]
    areas.append(("corner", "board"))
    features = [
        (kind, name)
        for kind, names in (
            ("object", board.object_names),
            ("mark", board.mark_names),
            ("edge_item", board.edge_item_names),
            ("point_object", board.point_object_names),
        )
        for name in sorted(names)
        if name not in blocked_targets
    ]
    roles = {(person, role.name): False for person in board.people for role in board.roles}
    found: list[Statement] = []
    seen: set[str] = set()

    def add(source: str) -> None:
        if source not in seen:
            statement = parse_statement(source)
            if holds(statement, board, placement, roles):
                found.append(statement)
                seen.add(source)

    for kind in kinds:
        if kind == "dir":
            for person in people:
                for other in people:
                    if person == other:
                        continue
                    for mode in ("left", "right", "up", "down", "knight", "furthest"):
                        add(f"{person} dir:{mode} {other}")
                    for mode in ("rows", "cols", "manhattan", "euclidean", "king", "areas"):
                        for comparison in ("=", "<=", ">="):
                            for distance in (0, 1, 2, 3):
                                add(f"{person} dir:{mode} {other} {comparison} {distance}")
            continue
        negative = kind.startswith("not ")
        operator = kind.removeprefix("not ")
        if operator == "line":
            options = [
                f"{axis}:{number}"
                for axis in ("rows", "columns")
                for number in range(1, board.size + 1)
            ]
            for person in people:
                for target in options:
                    add(f"{person} in {target}")
                    add(f"not {person} in {target}")
            continue
        targets = areas + features if operator == "in" else features
        if operator == "beside":
            targets = [(namespace, name) for namespace, name in targets if namespace == "object"]
            if not blocked_targets:
                targets += [
                    ("object_kind", kind)
                    for kind in ("blocking", "standable")
                    if any(obj.kind == kind for obj in board.objects)
                ]
        for person in people:
            for namespace, name in targets:
                prefix = "not " if negative else ""
                add(f"{prefix}{person} {operator} {namespace}:{name}")
    return found


def _placement(solution: dict[str, Any], people: Sequence[str]) -> dict[str, murdoku.Square]:
    return {person: solution[person] for person in people}


def _expression_people(value: object, people: set[str]) -> set[str]:
    if isinstance(value, Name):
        return {value.token.text} & people
    if isinstance(value, tuple):
        return set().union(*(_expression_people(item, people) for item in value))
    if is_dataclass(value):
        return set().union(
            *(_expression_people(getattr(value, field.name), people) for field in fields(value))
        )
    return set()


def _mentions(
    people: Sequence[str], clues: Iterable[str], *, expressions: bool = False
) -> dict[str, int]:
    """How many of `clues` name each person."""
    counts = dict.fromkeys(people, 0)
    for clue in clues:
        words = (
            _expression_people(parse_statement(clue).formula, set(people))
            if expressions
            else set(clue.split("|")[0].split()[1:])
        )
        for word in words:
            if word in counts:
                counts[word] += 1
    return counts


def _unnamed(
    people: Sequence[str],
    clues: Iterable[str],
    exclude: Iterable[str],
    *,
    expressions: bool = False,
) -> list[str]:
    """People outside `exclude` that none of `clues` names."""
    skip = set(exclude)
    return [
        p
        for p, n in _mentions(people, clues, expressions=expressions).items()
        if not n and p not in skip
    ]


def suggest(
    text: str,
    placement: dict[str, murdoku.Square],
    kinds: Sequence[str] = SUGGEST_KINDS,
    sample: int = 400,
    timeout: float = 5.0,
    log: Callable[[str], None] = lambda _line: None,
    exclude: Iterable[str] = (),
    needs: Iterable[int] = (),
    cover: bool = False,
    exclude_targets: Iterable[str] = (),
    needs_marks: Iterable[str] = (),
    *,
    expressions: bool = False,
) -> list[str]:
    """Clues to add to `text` so that `placement` becomes its only solution.

    Each round samples up to `sample` solutions of the current puzzle and adds
    the true candidate clue that rules out most other placements; ties go to
    clues about the people named least so far, then to earlier `kinds`. Stops
    when unique, or when no candidate helps.

    With `cover`, once unique, each person outside `exclude` that no clue names
    gets a true clue swapped in for one added clue, when one keeps the puzzle
    unique and the needed clues necessary; failing that, the search restarts
    from a clue about them that must stay necessary.

    Targets in `exclude_targets` are omitted from all suggested clues.

    `needs` lists clue numbers that must each remain necessary, and `needs_marks`
    names marks whose occupancy effects must remain necessary. Their rivals
    are the placements allowed without it but not with it (role rules are
    judged together, as one role holder must meet them all); a candidate that would rule out every
    rival of some needed clue is skipped, so removing any one of them still
    leaves another solution.
    """
    if expressions:
        board, rules, clues = load_expression_board(text)
    else:
        board, _ = load_board(text)
        rules, clues = [], []
    unknown = set(board.people) ^ set(placement)
    if unknown:
        raise ValueError(f"--solution must place exactly the people {board.people}")
    exclude_targets = tuple(exclude_targets)
    if expressions:
        if not expression_brute.accepts(board, clues, placement, rules=rules):
            raise ValueError("the intended placement does not satisfy the starting puzzle")
        statements = expression_candidate_clues(board, placement, kinds, exclude, exclude_targets)
        parsed_candidates = {format_statement(statement): statement for statement in statements}
        candidates = list(parsed_candidates)
    else:
        candidates = candidate_clues(board, placement, kinds, exclude, exclude_targets)
        parsed_candidates = {}
    lines = clue_lines(text)
    needed = sorted(set(needs))
    marks_needed = tuple(dict.fromkeys(needs_marks))
    for name in marks_needed:
        without_mark_condition(text, name)
    if bad := [n for n in needed if not 1 <= n <= len(lines)]:
        raise ValueError(f"--needs names clue numbers {bad}; the puzzle has {len(lines)} clues")
    added: list[str] = []

    def sampled(puzzle: str) -> list[dict[str, murdoku.Square]]:
        if expressions:
            trial_board, trial_rules, trial_clues = load_expression_board(
                puzzle, validate_keys=False
            )
            found = expression_brute.sample(trial_board, trial_clues, sample, rules=trial_rules)
        else:
            found = brute.sample(puzzle, sample)
        return [_placement(result, board.people) for result in found]

    def accepts(puzzle: str, other: dict[str, murdoku.Square]) -> bool:
        if expressions:
            trial_board, trial_rules, trial_clues = load_expression_board(
                puzzle, validate_keys=False
            )
            return expression_brute.accepts(trial_board, trial_clues, other, rules=trial_rules)
        return brute.accepts(puzzle, other)

    def true_for(trial_board: murdoku.Board, clue: str, other: dict[str, murdoku.Square]) -> bool:
        if expressions:
            roles = {
                (person, role.name): False
                for person in trial_board.people
                for role in trial_board.roles
            }
            return holds(parsed_candidates[clue], trial_board, other, roles)
        return _true_for(trial_board, clue, other)

    def unnamed(clue_lines: Iterable[str], excluded: Iterable[str]) -> list[str]:
        return _unnamed(board.people, clue_lines, excluded, expressions=expressions)

    def names(clue: str) -> set[str]:
        if expressions:
            return _expression_people(parsed_candidates[clue].formula, set(board.people))
        return set(clue.split()[1:]) & set(board.people)

    def solution_count(puzzle: str) -> int:
        if expressions:
            trial_board, trial_rules, trial_clues = load_expression_board(
                puzzle, validate_keys=False
            )
            return len(expression_brute.solutions(trial_board, trial_clues, 2, rules=trial_rules))
        return len(brute.solutions(puzzle, 2))

    def _reseed(person: str, added: list[str]) -> list[str]:
        # Start again from one clue about `person`, kept necessary like a needed clue.
        named = set(board.people) - set(unnamed(lines + added, ())) | {person}
        for clue in (c for c in candidates if person in names(c) and c not in lines):
            seeded = with_clues(text, [*lines, clue])
            more = suggest(
                seeded,
                placement,
                kinds,
                sample,
                timeout,
                exclude=exclude,
                needs=[*needed, len(lines) + 1],
                exclude_targets=exclude_targets,
                needs_marks=marks_needed,
                expressions=expressions,
            )
            trial = [clue, *more]
            completed = with_clues(text, lines + trial)
            if (
                solution_count(completed) == 1
                and named.isdisjoint(unnamed(lines + trial, ()))
                and all(
                    solution_count(with_clues(text, lines[: n - 1] + lines[n:] + trial)) > 1
                    for n in needed
                )
                and all(
                    solution_count(without_mark_condition(completed, name)) > 1
                    for name in marks_needed
                )
            ):
                log(f"restart from {clue} so {person} has a clue")
                return trial
        log(f"no clue about {person} fits")
        return added

    while True:
        current = with_clues(text, lines + added)
        others = sampled(current)
        others = [other for other in others if other != placement]
        rival_sets: list[tuple[murdoku.Board, list[dict[str, murdoku.Square]]]] = []
        for number in needed:
            without = with_clues(text, lines[: number - 1] + lines[number:] + added)
            found = sampled(without)
            rivals = [
                other for other in found if other != placement and not accepts(current, other)
            ]
            if not rivals:
                log(f"needed clue {number} is already redundant; add fewer clues first")
                return added
            rival_sets.append((board, rivals))
        for name in marks_needed:
            without = without_mark_condition(current, name)
            found = sampled(without)
            rivals = [
                other for other in found if other != placement and not accepts(current, other)
            ]
            if not rivals:
                log(f"no sampled rival found for mark {name}; try a larger sample or fewer clues")
                return added
            rival_sets.append((load_board_layout(without), rivals))
        if not others:
            if cover:
                added = _cover(
                    text,
                    lines,
                    added,
                    candidates,
                    board.people,
                    exclude,
                    needed,
                    log,
                    marks_needed,
                    expressions=expressions,
                )
                for person in unnamed(lines + added, exclude):
                    added = _reseed(person, added)
            result = outcome(with_clues(text, lines + added), timeout, expressions=expressions)
            if result.solutions == 1:
                log(f"unique with {len(added)} added clues ({result})")
            else:
                log(f"no other sampled placements; result is {result}")
            return added
        best, best_cut, best_key = None, 0, (0, 0)
        mentions = _mentions(board.people, lines + added, expressions=expressions)
        for clue in candidates:
            if clue in lines or clue in added:
                continue
            if any(
                not any(true_for(rival_board, clue, rival) for rival in rivals)
                for rival_board, rivals in rival_sets
            ):
                continue
            cut = sum(not true_for(board, clue, other) for other in others)
            # Equal cuts (often "all sampled") go to the least-mentioned people, so
            # the clues spread over the cast instead of piling up on one person.
            words = names(clue) if expressions else clue.split()[1:]
            spread = -sum(mentions.get(word, 0) for word in words)
            if cut and (cut, spread) > best_key:
                best, best_cut, best_key = clue, cut, (cut, spread)
        if best is None:
            log(f"stuck: {len(others)} other placements remain and no candidate separates them")
            for other in others[:3]:
                moved = {p: str(sq) for p, sq in other.items() if sq != placement[p]}
                log(f"  e.g. {moved}")
            return added
        added.append(best)
        log(f"add {best} (rules out {best_cut} of {len(others)} sampled placements)")


def _cover(
    text: str,
    lines: list[str],
    added: list[str],
    candidates: Sequence[str],
    people: Sequence[str],
    exclude: Iterable[str],
    needed: Sequence[int],
    log: Callable[[str], None],
    marks_needed: Sequence[str] = (),
    *,
    expressions: bool = False,
) -> list[str]:
    """`added` with clues swapped so that every person outside `exclude` is named.

    For each unnamed person, the first candidate about them that can replace one
    added clue is swapped in; the puzzle must stay unique, no other person may
    lose their last clue, and each needed clue must stay necessary.
    """

    def solution_count(puzzle: str) -> int:
        if expressions:
            board, rules, parsed = load_expression_board(puzzle, validate_keys=False)
            return len(expression_brute.solutions(board, parsed, 2, rules=rules))
        return len(brute.solutions(puzzle, 2))

    def unique(clues: list[str]) -> bool:
        return solution_count(with_clues(text, clues)) == 1

    def named_in(clue: str) -> set[str]:
        if expressions:
            return _expression_people(parse_statement(clue).formula, set(people))
        return set(clue.split()[1:])

    def fine(trial: list[str]) -> bool:
        named = {
            p for p, n in _mentions(people, lines + trial, expressions=expressions).items() if n
        }
        return (
            named
            >= {
                p for p, n in _mentions(people, lines + added, expressions=expressions).items() if n
            }
            and unique(lines + trial)
            and not any(unique(lines[: n - 1] + lines[n:] + trial) for n in needed)
            and all(
                solution_count(without_mark_condition(with_clues(text, lines + trial), name)) > 1
                for name in marks_needed
            )
        )

    skip = set(exclude)
    for person in people:
        if person in skip or _mentions(people, lines + added, expressions=expressions)[person]:
            continue
        swap = next(
            (
                [*added[:i], clue, *added[i + 1 :]]
                for clue in candidates
                if person in named_in(clue)
                for i in reversed(range(len(added)))
                if fine([*added[:i], clue, *added[i + 1 :]])
            ),
            None,
        )
        if swap is None:
            log(f"no clue about {person} can replace an added clue")
            continue
        log(f"swap in {next(c for c in swap if c not in added)} so {person} has a clue")
        added = swap
    return added


def ease(
    text: str,
    placement: dict[str, murdoku.Square],
    max_grade: str,
    kinds: Sequence[str] = SUGGEST_KINDS,
    timeout: float = 5.0,
    log: Callable[[str], None] = lambda _line: None,
    exclude: Iterable[str] = (),
    needs: Iterable[int] = (),
    needs_marks: Iterable[str] = (),
) -> list[str]:
    """Clues to add to a unique `text` until its grade is at most `max_grade`.

    Each round adds a true candidate clue while every clue numbered in `needs`
    and every mark in `needs_marks` stays necessary. A clue that reaches
    `max_grade` or below is preferred, the hardest such grade first, so the
    puzzle is not made easier than asked; otherwise the easiest grade wins.
    Ties go to clues about the people named least so far. Stops within
    `max_grade` or when nothing helps.
    """
    board, _ = load_board(text)
    candidates = candidate_clues(board, placement, kinds, exclude)
    lines = clue_lines(text)
    needed = sorted(set(needs))
    marks_needed = tuple(dict.fromkeys(needs_marks))
    for name in marks_needed:
        if len(brute.solutions(without_mark_condition(text, name))) < 2:
            raise ValueError(f"mark {name!r} is not necessary in the starting puzzle")
    added: list[str] = []
    current = outcome(text, timeout)
    while not _within(current.grade, max_grade):
        mentions = _mentions(board.people, lines + added)
        best: tuple[tuple[int, int], int, str, Outcome] | None = None
        for clue in candidates:
            if clue in lines or clue in added:
                continue
            if any(
                len(brute.solutions(with_clues(text, [*lines[: n - 1], *lines[n:], *added, clue])))
                == 1
                for n in needed
            ):
                continue
            trial = with_clues(text, [*lines, *added, clue])
            if any(
                len(brute.solutions(without_mark_condition(trial, name))) == 1
                for name in marks_needed
            ):
                continue
            result = outcome(trial, timeout)
            if not result.good or result.grade is None:
                continue
            spread = sum(mentions.get(word, 0) for word in clue.split()[1:])
            level = GRADES.index(result.grade)
            rank = (0, -level) if _within(result.grade, max_grade) else (1, level)
            key = (rank, spread, clue, result)
            if best is None or key[:2] < best[:2]:
                best = key
        if best is None or best[3].grade == current.grade:
            log(f"stuck at grade {current.grade}: no clue eases it while keeping {needed} needed")
            return added
        added.append(best[2])
        current = best[3]
        log(f"add {best[2]} ({current})")
    return added


def occupancy(text: str, sample: int = 400) -> tuple[int, list[tuple[str, str, int]]]:
    """(placements seen, [(object, square, times occupied)]) over the allowed placements."""
    board, _ = load_board(text)
    found = brute.sample(text, sample)
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
    parser.add_argument("command", choices=("report", "thin", "suggest", "ease", "occupancy"))
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds per trial")
    parser.add_argument(
        "--expressions",
        action="store_true",
        help="report, thin, suggest: read the developing expression language",
    )
    parser.add_argument("--keep", type=int, nargs="*", default=[], help="thin: clue numbers")
    parser.add_argument("--max-grade", choices=GRADES, help="thin, ease: hardest grade allowed")
    parser.add_argument("--solution", help='suggest: intended placement, "Ada=r1c2 Ben=r3c4"')
    parser.add_argument(
        "--kinds",
        nargs="*",
        default=list(SUGGEST_KINDS),
        help=f"suggest, ease: clue kinds to try (also available: {' '.join(EXTRA_KINDS)})",
    )
    parser.add_argument(
        "--exclude", nargs="*", default=[], help="suggest, ease: people no clue may mention"
    )
    parser.add_argument(
        "--exclude-target",
        nargs="*",
        default=[],
        help="suggest: objects no clue may mention",
    )
    parser.add_argument("--sample", type=int, default=400, help="suggest: solutions per round")
    parser.add_argument(
        "--cover",
        action="store_true",
        help="suggest: swap in clues so everyone outside --exclude is named",
    )
    parser.add_argument(
        "--needs",
        type=int,
        nargs="*",
        default=[],
        help="suggest, ease: clue numbers that must stay needed",
    )
    parser.add_argument(
        "--needs-mark",
        nargs="*",
        default=[],
        help="suggest, ease: marks whose occupancy effects must stay necessary",
    )
    args = parser.parse_args(argv)
    if args.expressions and args.command not in ("report", "thin", "suggest"):
        parser.error("--expressions is supported only by report, thin and suggest")
    if args.needs_mark and args.command not in ("suggest", "ease"):
        parser.error("--needs-mark is supported only by suggest and ease")
    text = args.puzzle.read_text()
    if args.command == "occupancy":
        seen, rows = occupancy(text, args.sample)
        print(f"{seen} placements{' (sample limit)' if seen >= args.sample else ''}")
        for name, square, times in rows:
            note = "  <- never" if times == 0 else "  <- always" if times == seen else ""
            print(f"{name:20} {square:6} {times:5}{note}")
        return 0
    print(f"start: {outcome(text, args.timeout, expressions=args.expressions)}")
    if args.command == "report":
        keyed = (keyed_expression_clue_numbers if args.expressions else keyed_clue_numbers)(text)
        for number, line, result in removal_report(
            text, args.timeout, expressions=args.expressions
        ):
            if number in keyed:
                print(f"{number:3}. {line}\n     required by Key; current puzzle: {result}")
            else:
                note = "  <- removable" if result.good else ""
                print(f"{number:3}. {line}\n     without it: {result}{note}")
        return 0
    if args.command == "thin":
        kept = thin(
            text, args.keep, args.max_grade, args.timeout, print, expressions=args.expressions
        )
        print(
            f"result: {outcome(with_clues(text, kept), args.timeout, expressions=args.expressions)}"
            "\nClues:"
        )
        print("\n".join(kept))
        return 0
    if not args.solution:
        parser.error(f"{args.command} needs --solution")
    placement = parse_solution(args.solution)
    if args.command == "ease":
        if not args.max_grade:
            parser.error("ease needs --max-grade")
        added = ease(
            text,
            placement,
            args.max_grade,
            args.kinds,
            args.timeout,
            print,
            args.exclude,
            args.needs,
            args.needs_mark,
        )
        print("Clues to add:")
        print("\n".join(added))
        return 0
    added = suggest(
        text,
        placement,
        args.kinds,
        args.sample,
        args.timeout,
        print,
        args.exclude,
        args.needs,
        args.cover,
        args.exclude_target,
        args.needs_mark,
        expressions=args.expressions,
    )
    print("Clues to add:")
    print("\n".join(added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
