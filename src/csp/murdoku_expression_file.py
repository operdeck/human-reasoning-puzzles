"""Read a Murdoku layout and expression-language rules and clues."""

from dataclasses import fields, is_dataclass
from functools import lru_cache

from .murdoku import Board
from .murdoku_lang import RESERVED_IDENTIFIERS, Statement, Token, parse_statement
from .murdoku_typecheck import check_formula
from .puzzlefile import load_board_layout


def _read_statements(text: str) -> tuple[list[Statement], list[Statement], list[tuple[int, str]]]:
    sections: dict[str, list[tuple[int, str]]] = {
        "People": [],
        "Rules": [],
        "Clues": [],
        "Key": [],
    }
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
            sections[current].append((number, raw))
        elif current is None:
            head, separator, value = raw.partition(":")
            if separator and head.strip() == "People" and value.strip():
                sections["People"] = [(number, " " * (len(head) + 1) + value)]
    for number, raw in sections["People"]:
        name = raw.strip()
        if name in RESERVED_IDENTIFIERS:
            column = len(raw) - len(raw.lstrip()) + 1
            raise ValueError(
                f"line {number}, column {column}: person name {name!r} is reserved; "
                "choose a different name"
            )
    rules = [parse_statement(line, line=number) for number, line in sections["Rules"]]
    clues = [parse_statement(line, line=number) for number, line in sections["Clues"]]
    return rules, clues, sections["Key"]


def _ast_key(value: object) -> object:
    if isinstance(value, Token):
        return " ".join(value.text.split())
    if isinstance(value, tuple):
        return tuple(_ast_key(item) for item in value)
    if is_dataclass(value):
        return (type(value), *(_ast_key(getattr(value, field.name)) for field in fields(value)))
    return value


def _keyed_clues(
    rules: list[Statement], clues: list[Statement], references: list[tuple[int, str]]
) -> set[int]:
    numbers: set[int] = set()
    seen: list[tuple[str, object]] = []
    for line_number, raw in references:
        kind, separator, tail = raw.partition(":")
        reference = tail.strip()
        kind, reference = kind.strip(), reference.strip()
        if not separator or kind not in {"clue", "rule"} or not reference or "|" in reference:
            raise ValueError(
                f"line {line_number}: bad Key entry; expected 'clue: ...' or 'rule: ...'"
            )
        reference_ast = _ast_key(
            parse_statement(" " * (raw.index(":") + 1) + tail, line=line_number).formula
        )
        key = (kind, reference_ast)
        if key in seen:
            raise ValueError(f"line {line_number}: duplicate Key entry")
        seen.append(key)
        entries = clues if kind == "clue" else rules
        matches = [
            index
            for index, statement in enumerate(entries, 1)
            if _ast_key(statement.formula) == reference_ast
        ]
        if len(matches) != 1:
            raise ValueError(
                f"line {line_number}: unresolved Key {kind}; expected exactly one match"
            )
        if kind == "clue":
            numbers.add(matches[0])
    return numbers


def keyed_expression_clue_numbers(text: str) -> set[int]:
    """Resolve Key references by AST, ignoring source positions and wording."""
    rules, clues, references = _read_statements(text)
    return _keyed_clues(rules, clues, references)


def load_expression_board(
    text: str, *, validate_keys: bool = True
) -> tuple[Board, list[Statement], list[Statement]]:
    """Return the layout, unnumbered rules and numbered clues with source positions."""
    board = load_board_layout(text)
    rules, clues, references = _read_statements(text)
    for statement in (*rules, *clues):
        check_formula(board, statement.formula)
    if validate_keys:
        _keyed_clues(rules, clues, references)
    return board, rules, clues


@lru_cache(maxsize=256)
def is_expression_file(text: str) -> bool:
    """Whether a Murdoku file's clues and rules are written in the expression grammar.

    No legacy clue parses as an expression, so the reader can tell the two apart.
    """
    try:
        load_expression_board(text)
    except (ValueError, NotImplementedError):
        return False
    return True
