"""Benchmark: run the ladder on a corpus sample or on the repo's own examples.

    uv run python -m benchmark.fetch --source norvig          # once, into the cache
    uv run python -m benchmark.bench --source norvig
    uv run python -m benchmark.bench --source sudoku-extreme --count 500 --timeout 30
    uv run python -m benchmark.bench --examples

Every puzzle is compiled and solved with one rule ladder, in a worker process
with a time limit, and judged against an answer the ladder did not produce: the
one the corpus ships, or the brute force's for `--examples`. Three questions
the report answers:

* **Does the ladder finish it?** `unsolved` and `timeout` are puzzles it cannot
  do. `wrong` (a solve that is not the known answer) and `unsound` (a step that
  contradicts it) are bugs, not difficulty, and are counted apart.
* **What does it cost, and which rule carries the work?** Times and iterations
  per grade, and with `--ladder` the same run with `chains`, `cover3` or
  `what_if` removed, or with the documented `cover4` gap filled in.
* **Does the grade mean anything?** The source's own difficulty (a rating
  column, or the set a puzzle came from) against the grade, by rank
  correlation and by bucket, plus how often `what_if` fires: a puzzle that only
  falls to assumption is not "hard", it is beyond deduction. The rank
  correlation covers the puzzles the ladder solved, and says how many it left
  out, because an unfinished puzzle only says where the clock stopped.

The report is Markdown on stdout; the same rows go to a CSV under
`benchmark/.cache/`, which is git-ignored. No puzzle text is written anywhere.
"""

import argparse
import csv
import json
import math
import os
import signal
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from benchmark import corpus
from csp import bruteforce, cli
from csp.core import DEFAULT_RULES, Rule, Solver, rule_cover, rule_forcing
from csp.puzzle_lab import TIERS, family_of
from csp.puzzlefile import detect
from csp.report import grade as grade_of
from csp.sudoku import compile_puzzle

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

# How `corpus.pick` spreads a sample: evenly by group or rating, or not at all.
BUCKETS: dict[str, Callable[[corpus.Row], str] | None] = {
    "none": None,
    "group": corpus.by_group,
    "rating": corpus.by_rating,
}


def _without(*names: str) -> tuple[Rule, ...]:
    """The default ladder with the named rules taken out."""
    return tuple(rule for rule in DEFAULT_RULES if rule.name not in names)


def _with_cover4() -> tuple[Rule, ...]:
    """The default ladder with `cover4` (quads, Jellyfish) before `chains`."""
    rules: list[Rule] = []
    for rule in DEFAULT_RULES:
        if rule.name == "chains":
            rules.append(Rule("cover4", rule_cover(4)))
        rules.append(rule)
    return tuple(rules)


def _with_forcing() -> tuple[Rule, ...]:
    """The default ladder with the experimental `forcing` rule before `what_if`.

    Issue #171: most no-what-if failures stall after `chains`, so a rule that
    draws a conclusion both branches of a two-option variable agree on is tried
    here, measured against the corpus, and promoted only if the delta earns it.
    """
    rules: list[Rule] = []
    for rule in DEFAULT_RULES:
        if rule.name == "what_if":
            rules.append(Rule("forcing", rule_forcing))
        rules.append(rule)
    return tuple(rules)


LADDERS: dict[str, tuple[Rule, ...]] = {
    "full": DEFAULT_RULES,
    "no-what-if": _without("what_if"),
    "no-chains": _without("chains"),
    "cover4": _with_cover4(),
    "cover4-no-what-if": tuple(rule for rule in _with_cover4() if rule.name != "what_if"),
    "forcing": _with_forcing(),
    "forcing-no-what-if": tuple(rule for rule in _with_forcing() if rule.name != "what_if"),
}

# The grades a run can end on, cheapest first, then the ways it can fail.
ENDINGS = ("unsolved", "ambiguous", "timeout")


class Job(NamedTuple):
    """One puzzle to run, as everything picklable needed to run it elsewhere."""

    index: int
    origin: str
    group: str
    rating: float | None
    kind: str
    text: str
    answer: dict[str, Any] | None
    ladder: str
    timeout: float


@dataclass(frozen=True)
class Outcome:
    """What one puzzle cost the ladder, and how it ended.

    `origin` names the file the puzzle came from, never the puzzle itself.
    `agrees` says the ladder's solution is the known answer; `unsound` lists
    the steps that contradict it, which no amount of difficulty excuses.
    """

    index: int
    origin: str
    group: str
    rating: float | None
    grade: str
    solved: bool
    agrees: bool
    unsound: tuple[str, ...]
    contradiction: str | None
    timed_out: bool
    ms: float
    iterations: int
    steps: int
    what_if: int
    counts: dict[str, int]
    last_rule: str | None = None

    @property
    def suspect(self) -> bool:
        """Whether the run went wrong rather than merely surprising us."""
        return not self.solved or not self.agrees or bool(self.unsound)


class TimedOut(TimeoutError):
    """The puzzle was still running when its time ran out."""


def _raise_timeout(signum: int, frame: Any) -> None:
    raise TimedOut


def _audit(steps: Sequence[Any], answer: dict[str, Any]) -> tuple[str, ...]:
    """Steps that contradict the known answer: an asserted literal has to be
    it, a ruled-out literal must not. Anything the answer says nothing about is
    no evidence either way, so it is skipped rather than guessed at."""
    wrong: list[str] = []
    for step in steps:
        expected = answer.get(step.var)
        if expected is None or step.rule == "given":
            continue
        try:
            matches = bool(step.value == expected)
        except Exception:  # a value the answer cannot compare: no evidence
            continue
        if matches != step.asserted:
            wrong.append(f"{step.rule} {'=' if step.asserted else 'x'} {step.literal}")
    return tuple(wrong[:5])


def measure(job: Job) -> Outcome:
    """Run one puzzle on the ladder its job names, within its time limit.

    The limit is the worker's own alarm, so a puzzle that would not finish
    costs its limit and nothing more and the rest of the batch runs on.
    """
    started = time.perf_counter()
    signal.setitimer(signal.ITIMER_REAL, 0)  # nothing left over from an earlier run
    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    try:
        # Armed inside the guard on purpose: with a limit this short the alarm
        # can fire before the body starts, and that is a timeout, not a crash.
        if job.timeout:
            signal.setitimer(signal.ITIMER_REAL, job.timeout)
        answer = job.answer
        if answer is None:
            found = bruteforce.solutions(job.text, job.kind, limit=2)
            if len(found) != 1:
                return Outcome(
                    job.index,
                    job.origin,
                    job.group,
                    job.rating,
                    "ambiguous",
                    False,
                    False,
                    (),
                    f"{len(found)} solutions, so there is no one answer to judge",
                    False,
                    0.0,
                    0,
                    0,
                    0,
                    {},
                )
            answer = found[0]
        if job.kind == "sudoku":
            model, _ = compile_puzzle(job.text)
        else:
            model = cli.load(job.text, job.kind).model
        fired: list[str] = []
        result = Solver(model, LADDERS[job.ladder]).solve(
            on_step=lambda rule, steps: fired.append(rule)
        )
    except TimedOut:
        return Outcome(
            job.index,
            job.origin,
            job.group,
            job.rating,
            "timeout",
            False,
            False,
            (),
            None,
            True,
            (time.perf_counter() - started) * 1000,
            0,
            0,
            0,
            {},
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    ms = (time.perf_counter() - started) * 1000
    counts = Counter(fired)
    return Outcome(
        index=job.index,
        origin=job.origin,
        group=job.group,
        rating=job.rating,
        grade=grade_of(fired) if result.solved else "unsolved",
        solved=result.solved,
        agrees=result.solved and result.assignment == answer,
        unsound=_audit(model.log, answer),
        contradiction=result.contradiction,
        timed_out=False,
        ms=ms,
        iterations=result.iterations,
        steps=len(model.log),
        what_if=counts["what_if"],
        counts=dict(counts),
        last_rule=fired[-1] if fired else None,
    )


GRADES = ("none", *(rule.name for rule in DEFAULT_RULES), *ENDINGS)


def grades_for(ladder: str) -> tuple[str, ...]:
    """The grades a run on this ladder can end on, cheapest first."""
    return ("none", *(rule.name for rule in LADDERS[ladder]), *ENDINGS)


def percentile(values: Sequence[float], share: float) -> float:
    """The value `share` of the way up a sorted list, without interpolation."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, round(share * (len(ordered) - 1)))]


def ranks(values: Sequence[float]) -> list[float]:
    """Each value's place in the order, ties sharing the average place."""
    order = sorted(range(len(values)), key=values.__getitem__)
    places = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        for slot in range(index, end + 1):
            places[order[slot]] = (index + end) / 2 + 1
        index = end + 1
    return places


def spearman(pairs: Sequence[tuple[float, float]]) -> float | None:
    """How well two orderings agree, from -1 to 1; None when one never varies."""
    if len(pairs) < 3:
        return None
    first, second = ranks([x for x, _ in pairs]), ranks([y for _, y in pairs])
    left = [a - statistics.fmean(first) for a in first]
    right = [b - statistics.fmean(second) for b in second]
    spread = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return sum(a * b for a, b in zip(left, right, strict=True)) / spread if spread else None


def bands(outcomes: Sequence[Outcome], count: int = 4) -> list[tuple[str, list[Outcome]]]:
    """The source's own difficulty, as equal bands of its rating if it has one.

    Without a rating the source's own grouping is used instead (the set a
    puzzle came from), which is coarser but still the source's own opinion.
    """
    ratings = [outcome.rating for outcome in outcomes if outcome.rating is not None]
    if not ratings:
        groups: dict[str, list[Outcome]] = {}
        for outcome in outcomes:
            groups.setdefault(outcome.group or "all", []).append(outcome)
        return sorted(groups.items())
    cuts = [percentile(ratings, index / count) for index in range(1, count)]
    grouped: dict[int, list[Outcome]] = {}
    for outcome in outcomes:
        if outcome.rating is None:
            grouped.setdefault(count, []).append(outcome)
        else:
            grouped.setdefault(sum(cut < outcome.rating for cut in cuts), []).append(outcome)
    labelled = []
    for band in sorted(grouped):
        members = grouped[band]
        known = [member.rating for member in members if member.rating is not None]
        if not known:
            label = "unrated"
        elif len(set(known)) == 1:
            label = f"rating {known[0]:g}"
        else:
            label = f"rating {min(known):g} to {max(known):g}"
        labelled.append((label, members))
    return labelled


def median_grade(outcomes: Sequence[Outcome], grades: Sequence[str]) -> str:
    """The middle grade of a group, in the ladder's own order."""
    return grades[round(statistics.median(grades.index(outcome.grade) for outcome in outcomes))]


def _why(outcome: Outcome) -> str:
    """In a few words, what went wrong with one puzzle."""
    parts = []
    if outcome.timed_out:
        parts.append("timed out")
    elif not outcome.solved:
        parts.append(outcome.contradiction or "the rules ran out")
    if outcome.solved and not outcome.agrees:
        parts.append("the solution is not the source's")
    if outcome.unsound:
        parts.append("unsound: " + "; ".join(outcome.unsound))
    return "; ".join(parts).replace("|", "\\|")


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}"


def _bucket(outcome: Outcome) -> str:
    """Which rung a failing puzzle reached, as a bucket label.

    `no-what-if` stops just below `what_if`, so an unsolved puzzle is one the
    cheaper rungs cannot finish. Whether `chains` and `wing` fired says where a
    strength change would bite (issue #171).
    """
    if outcome.timed_out:
        return "timed out"
    if outcome.solved and not outcome.agrees:
        return "wrong answer"
    if outcome.unsound:
        return "unsound"
    chains = outcome.counts.get("chains", 0)
    wing = outcome.counts.get("wing", 0)
    if chains and wing:
        return "stalled after chains and wing"
    if chains:
        return "stalled after chains, no wing"
    if wing:
        return "stalled after wing, no chains"
    return "stalled before chains (nothing on the top rungs fired)"


def failure_buckets(outcomes: Sequence[Outcome]) -> list[tuple[str, list[Outcome]]]:
    """The failing puzzles grouped by how far up the ladder they got (issue #171)."""
    groups: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        if outcome.suspect:
            groups.setdefault(_bucket(outcome), []).append(outcome)
    return sorted(groups.items())


def report(outcomes: Sequence[Outcome], *, title: str, ladder: str, timeout: float) -> str:
    """The Markdown account of a run: what it managed, what it cost, and how
    the grade lines up with the source's own idea of difficulty."""
    total = max(1, len(outcomes))
    grades = grades_for(ladder)
    solved = [outcome for outcome in outcomes if outcome.solved]
    finished = [outcome.ms for outcome in outcomes if not outcome.timed_out]
    failures = [outcome for outcome in outcomes if outcome.suspect]
    wrong = [outcome for outcome in outcomes if outcome.solved and not outcome.agrees]
    unsound = [outcome for outcome in outcomes if outcome.unsound]
    stuck = [outcome for outcome in outcomes if not outcome.solved and not outcome.timed_out]
    late = [outcome for outcome in outcomes if outcome.timed_out]
    assumption = sum(1 for outcome in outcomes if outcome.what_if)
    finished_time = (
        f"median {statistics.median(finished):.1f} ms, "
        f"p90 {percentile(finished, 0.9):.1f} ms, max {max(finished):.1f} ms"
        if finished
        else "median n/a ms, p90 n/a ms, max n/a ms"
    )

    lines = [
        f"### {title}",
        "",
        f"Ladder `{ladder}`, {timeout:g} s per puzzle.",
        "",
        f"- Solved: **{len(solved)} of {total}** ({100 * len(solved) / total:.1f}%)",
        f"- Unsolved: {len(stuck)}; timed out: {len(late)}",
        f"- Wrong solution: {len(wrong)}; unsound steps: {len(unsound)}",
        f"- Time where it finished: {finished_time}",
        f"- `what_if` fired on {assumption} of {total} puzzles "
        f"({100 * assumption / total:.0f}%), {sum(o.what_if for o in outcomes)} times in all",
        "",
        "| Grade | Puzzles | Share | Median ms | p90 ms | Max ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in grades:
        members = [outcome for outcome in outcomes if outcome.grade == name]
        if not members:
            continue
        times = [outcome.ms for outcome in members]
        lines.append(
            f"| `{name}` | {len(members)} | {100 * len(members) / total:.0f}% "
            f"| {statistics.median(times):.1f} | {percentile(times, 0.9):.1f} | {max(times):.1f} |"
        )

    firings: Counter[str] = Counter()
    for outcome in outcomes:
        firings.update(outcome.counts)
    lines += ["", "| Rule | Firings |", "|---|---:|"]
    lines += [f"| `{rule.name}` | {firings[rule.name]} |" for rule in LADDERS[ladder]]

    lines += [
        "",
        "| Source's own difficulty | Puzzles | Solved | Unsolved | Median grade "
        "| Median `what_if` | Median ms |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for label, members in bands(outcomes):
        inside = [outcome for outcome in members if outcome.solved]
        lines.append(
            f"| {label} | {len(members)} | {len(inside)} | {len(members) - len(inside)} "
            f"| `{median_grade(members, grades)}` "
            f"| {statistics.median(o.what_if for o in members)} "
            f"| {statistics.median(o.ms for o in members):.1f} |"
        )
    return "\n".join(lines + _tail(outcomes, failures, grades))


def _tail(
    outcomes: Sequence[Outcome], failures: Sequence[Outcome], grades: Sequence[str]
) -> list[str]:
    """The last of the report: agreement with the source's ranking, how often
    `what_if` carried a puzzle, and the index of what went wrong.

    The rank correlation is measured over the rated puzzles the ladder solved,
    and the line says how many rated puzzles that leaves out. A puzzle it could
    not finish is not evidence that the grade *ranks* the source's ratings: the
    failure grades come last in `grades_for`, so a slower machine or a shorter
    limit raises the correlation purely by timing out more puzzles, and the cost
    columns of an unfinished puzzle are whatever it had not spent yet, which
    puts their sign the wrong way round.
    """
    lines: list[str] = []
    rated = [outcome for outcome in outcomes if outcome.rating is not None]
    solved = [outcome for outcome in rated if outcome.solved]
    if len(solved) >= 3:
        measures = (
            ("grade", [(o.rating, grades.index(o.grade)) for o in solved]),
            ("iterations", [(o.rating, o.iterations) for o in solved]),
            ("ms", [(o.rating, o.ms) for o in solved]),
            ("what_if", [(o.rating, o.what_if) for o in solved]),
        )
        late = sum(1 for outcome in rated if outcome.timed_out)
        lines += [
            "",
            f"Rank correlation with the source's rating, over the {len(solved)} of "
            f"{len(rated)} rated puzzles it solved "
            f"({len(rated) - len(solved) - late} unsolved, {late} timed out): "
            + ", ".join(f"{name} {_number(spearman(pairs))}" for name, pairs in measures)
            + ".",
        ]
    elif rated:
        lines += [
            "",
            f"Rank correlation: only {len(solved)} of {len(rated)} rated puzzles "
            "were solved, too few to read the grade off the source's rating.",
        ]

    tiers = Counter(
        next((name for name, grades in TIERS.items() if outcome.grade in grades), "invalid")
        for outcome in outcomes
    )
    cells = " · ".join(f"{name} {tiers[name]}" for name in (*TIERS, "invalid") if tiers[name])
    lines += ["", f"Repo tiers (`csp.puzzle_lab.TIERS`): {cells}."]

    lines += ["", "| `what_if` firings | Puzzles |", "|---|---:|"]
    for steps in (0, 1, 2, 3):
        label = "3+" if steps == 3 else str(steps)
        count = sum(1 for outcome in outcomes if min(outcome.what_if, 3) == steps)
        lines.append(f"| {label} | {count} |")

    lines += ["", "**Slowest puzzles**", ""]
    lines += ["| # | Origin | Group | Rating | Grade | ms |", "|---|---|---|---|---:|---:|"]
    for outcome in sorted(outcomes, key=lambda o: -o.ms)[:10]:
        rating = "" if outcome.rating is None else f"{outcome.rating:g}"
        lines.append(
            f"| {outcome.index} | {outcome.origin} | {outcome.group} | {rating} "
            f"| `{outcome.grade}` | {outcome.ms:.0f} |"
        )

    lines += ["", "**Failure index**", ""]
    if not failures:
        lines.append("Empty: every puzzle was solved, and every step agrees with the source.")
        return lines

    lines += [
        "",
        "**Failure buckets** (where a strength change would bite, issue #171)",
        "",
        "| Bucket | Puzzles | Median iterations | Median ms | Last rules |",
        "|---|---:|---:|---:|---|",
    ]
    for label, members in failure_buckets(failures):
        last = Counter(outcome.last_rule or "-" for outcome in members)
        rules = ", ".join(f"{rule} x{count}" for rule, count in last.most_common())
        lines.append(
            f"| {label} | {len(members)} "
            f"| {statistics.median(o.iterations for o in members):.0f} "
            f"| {statistics.median(o.ms for o in members):.0f} | {rules} |"
        )

    lines += [
        "| # | Origin | Group | Rating | Grade | Last rule | ms | Why |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    for outcome in failures[:40]:
        rating = "" if outcome.rating is None else f"{outcome.rating:g}"
        lines.append(
            f"| {outcome.index} | {outcome.origin} | {outcome.group} | {rating} "
            f"| `{outcome.grade}` | {outcome.last_rule or '-'} | {outcome.ms:.0f} "
            f"| {_why(outcome)[:160]} |"
        )
    if len(failures) > 40:
        lines.append(f"\n(first 40 of {len(failures)}; see the CSV for the rest.)")
    return lines


CSV_COLUMNS = (
    "index",
    "origin",
    "group",
    "rating",
    "grade",
    "solved",
    "agrees",
    "unsound",
    "timed_out",
    "ms",
    "iterations",
    "steps",
    "what_if",
    "rules",
    "last_rule",
)


def csv_rows(outcomes: Iterable[Outcome]) -> Iterable[dict[str, Any]]:
    """One flat line per puzzle; nothing here says what a puzzle was."""
    for outcome in outcomes:
        yield {
            "index": outcome.index,
            "origin": outcome.origin,
            "group": outcome.group,
            "rating": "" if outcome.rating is None else f"{outcome.rating:g}",
            "grade": outcome.grade,
            "solved": int(outcome.solved),
            "agrees": int(outcome.agrees),
            "unsound": len(outcome.unsound),
            "timed_out": int(outcome.timed_out),
            "ms": f"{outcome.ms:.1f}",
            "iterations": outcome.iterations,
            "steps": outcome.steps,
            "what_if": outcome.what_if,
            "rules": json.dumps(outcome.counts, sort_keys=True),
            "last_rule": outcome.last_rule or "",
        }


def write_csv(path: Path, outcomes: Sequence[Outcome]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(csv_rows(outcomes))


# --- the two sources of jobs ------------------------------------------------


def corpus_jobs(sample: corpus.Sample, ladder: str, timeout: float) -> list[Job]:
    """One job per row of a fetched sample, with the answer the sample carries."""
    jobs: list[Job] = []
    for row in corpus.load(sample.path):
        if row.solution is None:
            continue
        jobs.append(
            Job(
                index=row.index,
                origin=row.origin,
                group=row.group or Path(row.origin).stem,
                rating=row.rating,
                kind="sudoku",
                text=corpus.grid(row.puzzle),
                answer=corpus.oracle(row.solution),
                ladder=ladder,
                timeout=timeout,
            )
        )
    return jobs


def example_jobs(ladder: str, timeout: float) -> list[Job]:
    """One job per checked-in puzzle; the brute force supplies the answer.

    Murdoku is left out: it has its own tools, and its brute force is not what
    this benchmark is about.
    """
    jobs: list[Job] = []
    for path in sorted(EXAMPLES.rglob("*.txt")):
        text = path.read_text()
        kind = detect(text)
        if kind == "murdoku":
            continue
        jobs.append(
            Job(
                index=len(jobs),
                origin=path.name,
                group=family_of(text),
                rating=None,
                kind=kind,
                text=text,
                answer=None,
                ladder=ladder,
                timeout=timeout,
            )
        )
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=sorted(corpus.SOURCES), default=None)
    parser.add_argument("--count", type=int, default=None, help="rows per bucket")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--bucket",
        choices=("none", "group", "rating"),
        default="none",
        help="how to spread the sample; see corpus.pick",
    )
    parser.add_argument("--examples", action="store_true", help="the repo's own puzzles")
    parser.add_argument("--ladder", choices=sorted(LADDERS), default="full")
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="seconds per puzzle; 0 waits for ever"
    )
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--csv", type=Path, default=None, help="where the per-puzzle rows go")
    args = parser.parse_args()
    if args.examples == (args.source is not None):
        parser.error("choose one: --examples or --source")

    if args.examples:
        jobs = example_jobs(args.ladder, args.timeout)
        title = f"The repo's own puzzles ({len(jobs)})"
        stem = "examples"
    else:
        source = corpus.SOURCES[args.source]
        sample = corpus.build(source, args.count, args.seed, args.bucket, BUCKETS[args.bucket])
        jobs = corpus_jobs(sample, args.ladder, args.timeout)
        title = f"{source.name} ({len(jobs)} puzzles, bucket {args.bucket}, seed {args.seed})"
        stem = sample.path.stem
    if not jobs:
        raise SystemExit("error: no puzzles to run; fetch a sample first (benchmark.fetch)")

    print(f"running {len(jobs)} puzzles, ladder {args.ladder}", file=sys.stderr, flush=True)
    started = time.perf_counter()
    chunk = max(1, len(jobs) // (max(1, args.workers) * 4))
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        outcomes = list(pool.map(measure, jobs, chunksize=chunk))
    wall = time.perf_counter() - started

    print(report(outcomes, title=title, ladder=args.ladder, timeout=args.timeout))
    path = args.csv or corpus.CACHE / "reports" / f"{stem}-{args.ladder}-{args.seed}.csv"
    write_csv(path, outcomes)
    print(f"\n{wrote(path)}; wall clock {wall:.0f} s with {args.workers} workers.")


def wrote(path: Path) -> str:
    """The path, relative to the repository when it is inside it."""
    root = Path(__file__).resolve().parent.parent
    try:
        return f"CSV: `{path.relative_to(root)}`"
    except ValueError:
        return f"CSV: `{path}`"


if __name__ == "__main__":
    main()
