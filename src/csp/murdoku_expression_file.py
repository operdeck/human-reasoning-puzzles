"""Read a Murdoku layout and expression-language rules and clues."""

from .murdoku import Board
from .murdoku_lang import Statement, parse_statement
from .murdoku_typecheck import check_formula
from .puzzlefile import load_board_layout


def load_expression_board(text: str) -> tuple[Board, list[Statement], list[Statement]]:
    """Return the layout, unnumbered rules and numbered clues with source positions."""
    board = load_board_layout(text)
    sections: dict[str, list[Statement]] = {"Rules": [], "Clues": []}
    current: str | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(":") and " " not in line[:-1]:
            current = line[:-1]
            if current in sections:
                sections[current] = []
        elif current in sections:
            statement = parse_statement(raw, line=number)
            check_formula(board, statement.formula)
            sections[current].append(statement)
    return board, sections["Rules"], sections["Clues"]
