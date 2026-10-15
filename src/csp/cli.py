"""Command line front end."""

import argparse
import dataclasses
import glob
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from . import (
    akari,
    battleships,
    binairo,
    bruteforce,
    calcudoku,
    futoshiki,
    icons,
    kakurasu,
    logicgrid,
    minesweeper,
    murdoku,
    picture,
    queens,
    report,
    starbattle,
    story,
    sudoku,
    suguru,
    tents,
)
from .core import DEFAULT_RULES, Contradiction, Model, Solver, Step
from .puzzlefile import KINDS, detect, load_board, load_presentation

_PNG_DEFAULT = object()
_DOCX_DEFAULT = object()


@dataclass(frozen=True)
class Puzzle:
    """A compiled puzzle, and how to draw any state of its model."""

    kind: str
    model: Model
    render: Callable[[Model, str, Sequence[Step]], str]

    def draw(self, title: str, steps: Sequence[Step] = (), model: Model | None = None) -> str:
        """Draw `model` (by default the puzzle's own), highlighting `steps`."""
        return self.render(model or self.model, title, steps)


def load(text: str, kind: str) -> Puzzle:
    """Compile puzzle text of the given kind. Raises ValueError if malformed."""
    if kind == "sudoku":
        model, layout = sudoku.compile_puzzle(text)
        return Puzzle(kind, model, partial(sudoku.render, layout))
    if kind == "calcudoku":
        model, cages = calcudoku.compile_puzzle(text)
        return Puzzle(kind, model, partial(calcudoku.render, cages))
    if kind == "futoshiki":
        model, signs = futoshiki.compile_puzzle(text)
        return Puzzle(kind, model, partial(futoshiki.render, signs))
    if kind == "queens":
        model, queens_puzzle = queens.compile_puzzle(text)
        return Puzzle(kind, model, partial(queens.render, queens_puzzle))
    if kind == "suguru":
        model, suguru_puzzle = suguru.compile_puzzle(text)
        return Puzzle(kind, model, partial(suguru.render, suguru_puzzle))
    if kind == "logicgrid":
        model, logicgrid_puzzle = logicgrid.compile_puzzle(text)
        return Puzzle(kind, model, partial(logicgrid.render, logicgrid_puzzle))
    if kind == "starbattle":
        model, starbattle_puzzle = starbattle.compile_puzzle(text)
        return Puzzle(kind, model, partial(starbattle.render, starbattle_puzzle))
    if kind == "binairo":
        model, binairo_puzzle = binairo.compile_puzzle(text)
        return Puzzle(kind, model, partial(binairo.render, binairo_puzzle))
    if kind == "tents":
        model, tents_puzzle = tents.compile_puzzle(text)
        return Puzzle(kind, model, partial(tents.render, tents_puzzle))
    if kind == "minesweeper":
        model, minesweeper_puzzle = minesweeper.compile_puzzle(text)
        return Puzzle(kind, model, partial(minesweeper.render, minesweeper_puzzle))
    if kind == "akari":
        model, akari_puzzle = akari.compile_puzzle(text)
        return Puzzle(kind, model, partial(akari.render, akari_puzzle))
    if kind == "kakurasu":
        model, kakurasu_puzzle = kakurasu.compile_puzzle(text)
        return Puzzle(kind, model, partial(kakurasu.render, kakurasu_puzzle))
    if kind == "battleships":
        model, battleships_puzzle = battleships.compile_puzzle(text)
        return Puzzle(kind, model, partial(battleships.render, battleships_puzzle))
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    global_counts = murdoku.global_count_conditions(board, clues)
    return Puzzle(kind, model, partial(murdoku.render, board, global_counts=global_counts))


def narrate(rule: str, steps: Sequence[Step]) -> None:
    """Print one rule firing: what it placed, or a sample of what it ruled out."""
    placed = [s for s in steps if s.asserted]
    dropped = [s for s in steps if not s.asserted]
    print(f"\n{rule}")
    for s in placed:
        prefix, message = "=", s.literal
        if " has role " in s.var and isinstance(s.value, bool):
            person, _, role = s.var.partition(" has role ")
            message = f"{person} {'has' if s.value else 'does not have'} role {role}"
        print(f"  {prefix} {message}  ({s.reason})")
    if dropped and not placed:
        step = dropped[0]
        message = step.literal
        if " has role " in step.var and isinstance(step.value, bool):
            person, _, role = step.var.partition(" has role ")
            message = f"{person} {'has' if step.value else 'does not have'} role {role}"
        print(f"  x {message}  ({step.reason})")
    if dropped:
        print(f"  ... {len(dropped)} option{'s' if len(dropped) != 1 else ''} ruled out")


def brute_force(puzzle: Puzzle, text: str) -> int:
    """Search for solutions without the engine. Exit code 0 means exactly one."""
    start = time.perf_counter()
    found = bruteforce.solutions(text, puzzle.kind, limit=2)
    elapsed = time.perf_counter() - start
    if not found:
        print(f"\nbrute force: no solution ({elapsed:.2f}s)")
        return 1
    try:
        for i, solution in enumerate(found, 1):
            title = "The unique solution" if len(found) == 1 else f"Solution {i}"
            print(puzzle.draw(title, model=_filled(puzzle.model, solution)))
    except Contradiction as exc:
        print(f"\nbrute force found a solution the engine's model rules out: {exc}")
        return 3
    if len(found) == 1:
        print(f"\nbrute force: unique solution ({elapsed:.2f}s)")
        return 0
    first, second = found
    differ = ", ".join(
        f"{var} ({first[var]} or {second[var]})" for var in first if first[var] != second[var]
    )
    print(f"\nbrute force: more than one solution ({elapsed:.2f}s); these two differ at {differ}")
    return 1


def make_image(
    kind: str,
    text: str,
    solution: dict[str, Any] | None = None,
    role_statuses: dict[tuple[str, str], bool | None] | None = None,
) -> Any:
    """The picture of a puzzle of any family, with `solution` drawn in if given."""
    from . import picture

    if kind == "queens":
        image = picture.queens_picture(queens.parse(text), solution)
    elif kind == "suguru":
        image = picture.suguru_picture(suguru.parse(text), solution)
    elif kind == "starbattle":
        image = picture.starbattle_picture(starbattle.parse(text), solution)
    elif kind == "binairo":
        image = picture.binairo_picture(binairo.parse(text), solution)
    elif kind == "tents":
        image = picture.tents_picture(tents.parse(text), solution)
    elif kind == "minesweeper":
        image = picture.minesweeper_picture(minesweeper.parse(text), solution)
    elif kind == "akari":
        image = picture.akari_picture(akari.parse(text), solution)
    elif kind == "kakurasu":
        image = picture.kakurasu_picture(kakurasu.parse(text), solution)
    elif kind == "battleships":
        image = picture.battleships_picture(battleships.parse(text), solution)
    elif kind == "logicgrid":
        image = picture.logicgrid_picture(logicgrid.parse(text), solution)
    elif kind == "sudoku":
        image = picture.sudoku_picture(sudoku.parse(text), solution)
    elif kind == "calcudoku":
        image = picture.calcudoku_picture(calcudoku.parse(text), solution)
    elif kind == "futoshiki":
        image = picture.futoshiki_picture(futoshiki.parse(text), solution)
    else:
        board, clues = load_board(text)
        global_counts = murdoku.global_count_conditions(board, clues)
        if solution is None and (unknown := picture.unknown_object_icons(board)):
            print(
                f"warning: no icon for {', '.join(unknown)}; using text labels",
                file=sys.stderr,
            )
        image = picture.murdoku_picture(
            board,
            solution,
            role_statuses=role_statuses,
            global_counts=global_counts,
        )
    return image


def write_picture(
    kind: str,
    text: str,
    path: Path,
    solution: dict[str, Any] | None = None,
    role_statuses: dict[tuple[str, str], bool | None] | None = None,
) -> bool:
    """Save the puzzle as a PNG, with `solution` drawn in if given."""
    try:
        image = make_image(kind, text, solution, role_statuses)
    except ImportError:
        print("--png needs Pillow: uv sync --extra png", file=sys.stderr)
        return False
    image.save(path)
    print(f"wrote {path}")
    return True


def _murdoku_lint(
    board: murdoku.Board, clues: Sequence[murdoku.Clue], model: Model, text: str = ""
) -> list[str]:
    findings: list[str] = []
    for name in picture.unknown_object_icons(board):
        findings.append(f"warning: missing icon for {name}; PNG will use a text label")
    for number, other in murdoku.implied_clues(clues):
        findings.append(f"warning: clue {number} is already implied by clue {other}")

    try:
        presentation = load_presentation(text)
    except ValueError as error:
        findings.append(f"warning: booklet text: {error}")
    else:
        for person, figure in presentation.figures.items():
            if figure.icon and icons.code_for(figure.icon) is None:
                findings.append(f"warning: unknown icon {figure.icon} for {person} in Figures")

    candidate_squares = {
        model.value_of(literal) for person in board.people for literal in model.options(person)
    }
    for region, name in board.region_names.items():
        free_cells = [square for square in board.free if board.region_of(square) == region]
        if not free_cells or not (set(free_cells) & candidate_squares):
            findings.append(f"warning: unreachable area {name}; no person candidate remains")

    role_references: set[str] = set()
    role_positions = {
        "has_role": (1,),
        "not_role": (1,),
        "role_in_tagged": (1,),
        "role_not_in_tagged": (1,),
        "role_on": (1,),
        "role_not_on": (1,),
        "role_next_to": (1,),
        "role_below": (1,),
        "sole_role_companion": (1,),
        "role_subset": (0, 1),
        "min_role_in_tagged": (0,),
        "role_occupant": (0,),
    }
    for rule in murdoku.role_conditions(board, clues):
        if rule.kind in ("some_role", "roleless", "at_most_one_role"):
            role_references.update(board.role_names)
        for position in role_positions.get(rule.kind, ()):
            token = rule.args[position]
            name = token.partition(":")[2] if token.startswith("role:") else token
            if name in board.role_names:
                role_references.add(name)
    for target_condition in murdoku.quantified_conditions(board, clues):
        if target_condition.selector.kind == "role":
            role_references.add(target_condition.selector.name)
    for count_condition in murdoku.global_count_conditions(board, clues):
        if (
            count_condition.kind == "people_with"
            and count_condition.selector is not None
            and count_condition.selector.kind == "role"
        ):
            role_references.add(count_condition.selector.name)
    for role in board.roles:
        if (
            role.allowed_counts != frozenset(range(len(board.people) + 1))
            or role.different_regions
            or role.eligible_people is not None
        ):
            role_references.add(role.name)
    for role in board.roles:
        if role.eligible_people is not None and len(role.eligible_people) == 1:
            (only,) = role.eligible_people
            findings.append(
                f"warning: role {role.name} can only be held by {only}; "
                f"state it about {only} instead of making it a role"
            )
    for role_name in sorted(board.role_names - role_references):
        findings.append(f"warning: role {role_name} is declared but unused")
    return findings


def _filled(model: Model, solution: dict[str, Any]) -> Model:
    """A copy of `model` with every variable set as in `solution`, for drawing.

    Raises Contradiction if the model had already ruled that value out, which
    would mean the compiler and the brute force disagree about the puzzle.
    """
    twin = model.clone()
    for var, value in solution.items():
        domain = twin.constraints[twin.domain_of(var)].literals
        (lit,) = (lit for lit in domain if twin.value_of(lit) == value)
        twin.assign(lit, "brute_force", "found by search")
    return twin


def _booklet(files: list[Path], docx: Any) -> int:
    """One booklet, puzzles first and then solutions, for the puzzle `files` of any family."""
    if docx is not _DOCX_DEFAULT:
        out = docx
    elif len(files) == 1:
        out = files[0].with_suffix(".docx")
    else:
        out = files[0].parent / "booklet.docx"
    try:
        from . import docx_export
    except ImportError:
        print("--docx needs python-docx and Pillow: uv sync --extra docx", file=sys.stderr)
        return 2
    entries = []
    for file in files:
        text = file.read_text()
        try:
            kind = detect(text)
            model = load(text, kind).model
        except ValueError as exc:
            print(f"could not read {file.name}: {exc}", file=sys.stderr)
            return 2
        result = Solver(model).solve()
        placed = None
        roles = None
        if result.solved:
            placed = dict(result.assignment)
            if kind == "murdoku":
                placed = {k: v for k, v in placed.items() if not isinstance(v, bool)}
                roles = murdoku.role_statuses(load_board(text)[0], model)
        else:
            print(f"warning: {file.name} is not solved by the rules; solution page omitted")
        entry = docx_export.Entry(text, file, placed, roles, kind)
        if kind != "murdoku":
            entry = dataclasses.replace(
                entry,
                puzzle_image=make_image(kind, text),
                solution_image=make_image(kind, text, placed) if placed is not None else None,
            )
        entries.append(entry)
    docx_export.write_booklet(entries, out)
    print(f"wrote {out} ({len(entries)} puzzles, then their solutions)")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact-cover puzzle solver")
    parser.add_argument(
        "puzzles",
        nargs="+",
        metavar="PUZZLE",
        help=(
            "puzzle file(s) or glob pattern(s); quote a pattern to let the program "
            "expand it; --docx puts them in one booklet"
        ),
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="narrate each deduction")
    parser.add_argument(
        "--step", "-s", action="store_true", help="redraw and pause after each deduction"
    )
    parser.add_argument(
        "--track-person",
        metavar="PERSON",
        help="Murdoku only: trace a person's live squares and region-overlap companions",
    )
    parser.add_argument("--type", choices=["auto", *KINDS], default="auto")
    instead = parser.add_mutually_exclusive_group()
    instead.add_argument(
        "--show-model",
        action="store_true",
        help="explain the compiled model and the solving algorithm, then stop",
    )
    instead.add_argument(
        "--brute-force",
        action="store_true",
        help="search for every solution without the engine, to check uniqueness",
    )
    instead.add_argument(
        "--explain",
        action="store_true",
        help="Murdoku only: write out a short worked solution, as for a puzzle booklet",
    )
    instead.add_argument(
        "--grade",
        action="store_true",
        help="print only the puzzle's grade: the hardest rule the solve needed",
    )
    instead.add_argument(
        "--lint",
        action="store_true",
        help="Murdoku only: check declarations, icons, reachable areas, and role usage",
    )
    instead.add_argument(
        "--require-forward",
        action="store_true",
        help="Murdoku only: lint and require a solve without what_if",
    )
    parser.add_argument(
        "--png",
        nargs="?",
        type=Path,
        const=_PNG_DEFAULT,
        metavar="FILE",
        help=(
            "write the puzzle as a picture to FILE (default: beside the puzzle), and once solved "
            "the solution to FILE with '-solution' before the extension (needs Pillow)"
        ),
    )
    parser.add_argument(
        "--docx",
        nargs="?",
        type=Path,
        const=_DOCX_DEFAULT,
        metavar="FILE",
        help=(
            "Murdoku only: write an editable Word booklet to FILE (default: beside the puzzle, or "
            "booklet.docx for a glob): all puzzles, then all solutions (needs python-docx: "
            "uv sync --extra docx)"
        ),
    )
    args = parser.parse_args(argv)
    paths = _expand_patterns(args.puzzles)
    if paths is None:
        return 2
    if args.png not in (None, _PNG_DEFAULT) and len(paths) > 1:
        parser.error("--png FILE needs a single puzzle; use --png alone for several")
    if args.docx is not None:
        return _booklet(paths, args.docx)
    status = 0
    for path in paths:
        status = max(status, _solve_one(args, path, parser))
    return status


def _expand_patterns(patterns: Sequence[str]) -> list[Path] | None:
    """Existing paths as given; anything else is a glob pattern. None if one matches nothing."""
    found: list[Path] = []
    for pattern in patterns:
        if Path(pattern).exists():
            matches = [pattern]
        else:
            matches = sorted(glob.glob(pattern, recursive=True))
        files = [Path(match) for match in matches if Path(match).is_file()]
        if not files:
            print(f"no such file: {pattern}", file=sys.stderr)
            return None
        found.extend(files)
    return found


def _solve_one(args: argparse.Namespace, path: Path, parser: argparse.ArgumentParser) -> int:
    png_path = path.with_suffix(".png") if args.png is _PNG_DEFAULT else args.png
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    text = path.read_text()
    kind = detect(text) if args.type == "auto" else args.type
    if (args.lint or args.require_forward) and kind != "murdoku":
        parser.error("--lint and --require-forward are only available for Murdoku")
    try:
        puzzle = load(text, kind)
    except ValueError as exc:
        if args.lint or args.require_forward:
            print(f"lint error in {path.name}: {exc}", file=sys.stderr)
            return 1
        print(f"could not read {path.name}: {exc}", file=sys.stderr)
        return 2

    model = puzzle.model
    track_board: murdoku.Board | None = None
    if args.track_person:
        if kind != "murdoku":
            parser.error("--track-person is only available for Murdoku")
        if (
            args.show_model
            or args.brute_force
            or args.explain
            or args.grade
            or args.lint
            or args.require_forward
        ):
            parser.error("--track-person requires a normal solve")
        track_board, _ = load_board(text)
        if args.track_person not in track_board.people:
            parser.error(
                f"unknown person {args.track_person!r}; have {', '.join(track_board.people)}"
            )
    if args.lint or args.require_forward:
        board, clues = load_board(text)
        findings = _murdoku_lint(board, clues, model, text)
        for finding in findings:
            print(finding)
        if not findings:
            print("lint: no issues found")
        if args.require_forward:
            forward_rules = tuple(rule for rule in DEFAULT_RULES if rule.name != "what_if")
            forward_result = Solver(model.clone(), forward_rules).solve()
            if not forward_result.solved:
                detail = f": {forward_result.contradiction}" if forward_result.contradiction else ""
                print(
                    f"lint error: puzzle does not solve using forward rules "
                    f"without what_if{detail}",
                    file=sys.stderr,
                )
                return 1
            print("require-forward: solved without what_if")
        return 0
    if args.grade:
        fired: list[str] = []
        result = Solver(model).solve(on_step=lambda rule, steps: fired.append(rule))
        print(report.grade(fired) if result.solved else "unsolved")
        return 0 if result.solved else 1
    print(
        f"{kind}: {model.num_literals} literals, {len(model.constraints)} constraints, "
        f"{len(model.relations)} relations"
    )
    print(puzzle.draw("Start"))
    if args.track_person:
        assert track_board is not None
        print(murdoku.track_person_status(track_board, model, args.track_person))
    if png_path is not None:
        role_statuses = None
        if kind == "murdoku":
            role_board = track_board
            if role_board is None:
                role_board, _ = load_board(text)
            role_statuses = murdoku.role_statuses(role_board, model)
        if not write_picture(kind, text, png_path, role_statuses=role_statuses):
            return 2

    if args.show_model:
        print(f"\n{report.describe(model)}")
        return 0
    if args.brute_force:
        return brute_force(puzzle, text)
    if args.explain:
        if kind != "murdoku":
            print(
                f"--explain only writes out Murdoku solutions so far, not {kind}", file=sys.stderr
            )
            return 2
        print(f"\n{story.explain(text)}")
        return 0

    used: list[str] = []

    def on_step(rule: str, steps: Sequence[Step]) -> None:
        used.append(rule)
        if not (args.verbose or args.step or args.track_person):
            return
        narrate(rule, steps)
        if args.track_person:
            assert track_board is not None
            print(murdoku.track_person_status(track_board, model, args.track_person))
        if args.step:
            print(puzzle.draw("After this step", steps))
            try:
                input("\n[enter] ")
            except EOFError:
                raise SystemExit(0) from None

    result = Solver(model).solve(on_step=on_step)

    if result.solved:
        print(puzzle.draw("Solved"))
        if png_path is not None:
            solved = png_path.with_stem(f"{png_path.stem}-solution")
            roles = None
            if kind == "murdoku":
                board, _ = load_board(text)
                roles = murdoku.role_statuses(board, model)
            write_picture(kind, text, solved, result.assignment, roles)
    elif result.contradiction:
        print(puzzle.draw("Stuck"))
        print(f"\ncontradiction: {result.contradiction}")
    else:
        print(puzzle.draw("As far as the rules go"))
        undecided = [v for v in model.variables if v not in result.assignment]
        print(f"\n{len(undecided)} undecided: {', '.join(undecided)}")
        print(f"needs a rule beyond {'/'.join(rule.name for rule in DEFAULT_RULES)}.")

    print(f"\n{result.iterations} iterations, {len(model.log)} deductions logged")
    print(report.rules_used(used))
    return 0 if result.solved else 1


if __name__ == "__main__":
    sys.exit(main())
