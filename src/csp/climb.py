"""Difficulty search for boards that a random builder only rarely makes hard or medium.

`fresh` draws a random solution and thins its clues, which is enough for most families.
A few families (Rectangles) jump straight from `single` to `subsumption` or `chains`
whatever the board, so the grade a tier asks for is almost never drawn. These searches start
from a unique board and keep changing its layout, never leaving the unique boards the
ladder solves, until the grade lands in the wanted set.

They live apart from `fresh` because they run the deduction ladder (`cli`, `core`), which
the plain builders do not need.
"""

import random
from collections.abc import Collection

from . import cli, fresh, report
from .core import DEFAULT_RULES, Solver
from .puzzlefile import detect

type Cell = tuple[int, int]

ORDER = [rule.name for rule in DEFAULT_RULES]


def grade(text: str) -> str | None:
    """The hardest rule the ladder needs for `text`, or None if it does not solve it."""
    fired: list[str] = []
    model = cli.load(text, detect(text)).model
    result = Solver(model).solve(on_step=lambda rule, steps: fired.append(rule))
    return report.grade(fired) if result.solved else None


# --- Rectangles --------------------------------------------------------------


def _is_rectangle(cells: set[Cell]) -> bool:
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    return (max(rows) - min(rows) + 1) * (max(cols) - min(cols) + 1) == len(cells)


def _rectangle_move(
    pieces: list[list[Cell]], numbers: list[Cell], rng: random.Random
) -> tuple[list[list[Cell]], list[Cell]] | None:
    """One random change: move a number, merge two touching pieces, or split a piece."""
    pieces, numbers = [list(piece) for piece in pieces], list(numbers)
    kind = rng.choice(("number", "merge", "split"))
    if kind == "number":
        i = rng.randrange(len(pieces))
        numbers[i] = rng.choice(pieces[i])
        return pieces, numbers
    if kind == "merge":
        owner = {cell: i for i, piece in enumerate(pieces) for cell in piece}
        touching = {
            (min(owner[(r, c)], owner[near]), max(owner[(r, c)], owner[near]))
            for (r, c) in owner
            for near in ((r + 1, c), (r, c + 1))
            if near in owner and owner[near] != owner[(r, c)]
        }
        joinable = [(i, j) for i, j in touching if _is_rectangle(set(pieces[i]) | set(pieces[j]))]
        if not joinable:
            return None
        i, j = rng.choice(joinable)
        pieces[i] = pieces[i] + pieces[j]
        numbers[i] = rng.choice(pieces[i])
        del pieces[j], numbers[j]
        return pieces, numbers
    i = rng.randrange(len(pieces))
    cells = sorted(pieces[i])
    top, bottom = cells[0][0], cells[-1][0]
    left, right = min(c for _, c in cells), max(c for _, c in cells)
    cuts = [("row", r) for r in range(top + 1, bottom + 1)]
    cuts += [("col", c) for c in range(left + 1, right + 1)]
    if not cuts:
        return None
    axis, at = rng.choice(cuts)
    first = [cell for cell in cells if cell[0 if axis == "row" else 1] < at]
    second = [cell for cell in cells if cell[0 if axis == "row" else 1] >= at]
    pieces[i] = first
    pieces.append(second)
    numbers[i] = rng.choice(first)
    numbers.append(rng.choice(second))
    return pieces, numbers


def rectangles(
    size: int,
    pieces: list[list[Cell]],
    numbers: list[Cell],
    rng: random.Random,
    goal: Collection[str],
    comment: str = "",
    steps: int = 300,
) -> str | None:
    """Reshape a unique Rectangles board until its grade is in `goal`, or give up.

    Moves keep the board unique and ladder-solved, and are kept when the hardest rule used
    does not fall (ties broken by how many rectangles each number could still be).
    """
    text = fresh._rectangles_text(size, pieces, numbers, comment)
    start = grade(text)
    if start is None:
        return None
    if start in goal:
        return text
    score = (ORDER.index(start), fresh._candidate_total(text))
    for _ in range(steps):
        move = _rectangle_move(pieces, numbers, rng)
        if move is None:
            continue
        text = fresh._rectangles_text(size, *move, comment)
        if not fresh.is_unique(text) or (found := grade(text)) is None:
            continue
        if found in goal:
            return text
        trial = (ORDER.index(found), fresh._candidate_total(text))
        if trial >= score:
            (pieces, numbers), score = move, trial
    return None
