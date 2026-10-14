"""Brute-force solving: plain search, kept apart from the deduction engine.

Used to check that a puzzle has exactly one solution, and as an independent
answer to test the engine against. Each module reads the puzzle with the
same file reader and tests the same rule definitions as the engine does
(Calcudoku cage arithmetic, Murdoku clue conditions), but searches on its
own: nothing here imports from `csp.core`, so no literal, constraint or
deduction rule is involved.

Every `solutions` function returns up to `limit` solutions as dictionaries.
For Sudoku, Calcudoku, and Futoshiki they match the engine's
`Result.assignment`. Murdoku results also include each role membership as a
Boolean key such as `"Ada has role bandit"`; the engine keeps hidden role
states separate from its visible person-placement assignment.
"""

from collections.abc import Callable
from typing import Any

from ..puzzlefile import detect
from . import (
    akari,
    battleships,
    binairo,
    calcudoku,
    futoshiki,
    kakurasu,
    logicgrid,
    minesweeper,
    murdoku,
    queens,
    starbattle,
    sudoku,
    suguru,
    tents,
)

SOLVERS: dict[str, Callable[[str, int], list[dict[str, Any]]]] = {
    "sudoku": sudoku.solutions,
    "murdoku": murdoku.solutions,
    "queens": queens.solutions,
    "suguru": suguru.solutions,
    "logicgrid": logicgrid.solutions,
    "starbattle": starbattle.solutions,
    "binairo": binairo.solutions,
    "tents": tents.solutions,
    "minesweeper": minesweeper.solutions,
    "akari": akari.solutions,
    "kakurasu": kakurasu.solutions,
    "battleships": battleships.solutions,
    "calcudoku": calcudoku.solutions,
    "futoshiki": futoshiki.solutions,
}


def solutions(text: str, kind: str | None = None, limit: int = 2) -> list[dict[str, Any]]:
    """Up to `limit` solutions; the default of 2 is enough to test uniqueness."""
    return SOLVERS[kind or detect(text)](text, limit)
