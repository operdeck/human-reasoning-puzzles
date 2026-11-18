"""Text-file entry points for the independent expression-language search."""

from typing import Any

from ..murdoku import Square
from ..murdoku_expression_file import load_expression_board
from . import murdoku_expr


def solutions(text: str, limit: int = 2) -> list[dict[str, Any]]:
    """Return up to `limit` placements and role assignments."""
    board, rules, clues = load_expression_board(text)
    return murdoku_expr.solutions(board, clues, limit, rules=rules)


def accepts(text: str, placement: dict[str, Square]) -> bool:
    """Check a placement against the reference evaluator and role declarations."""
    board, rules, clues = load_expression_board(text)
    return murdoku_expr.accepts(board, clues, placement, rules=rules)


def sample(text: str, limit: int) -> list[dict[str, Any]]:
    """Return distinct solutions spread over the search space."""
    board, rules, clues = load_expression_board(text)
    return murdoku_expr.sample(board, clues, limit, rules=rules)
