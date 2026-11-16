"""Building blocks for the planned Murdoku expression language.

The existing puzzle reader remains authoritative until the new language is
implemented and the corpus has been migrated.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    """A lexical token with its one-based position in the source."""

    text: str
    line: int
    column: int


_TOKEN = re.compile(
    r"\?(?:[^\W\d]|_)\w*"
    r"|(?:[^\W\d]|_)[\w-]*(?::[\w-]+)*"
    r"|\d+"
    r"|<=|>=|!=|\.\."
    r"|[():,;=<>+\-]"
)


def tokenize(source: str, *, line: int = 1) -> tuple[Token, ...]:
    """Tokenize a formula, retaining locations for parser diagnostics."""
    tokens: list[Token] = []
    offset = 0
    column = 1
    while offset < len(source):
        char = source[offset]
        if char.isspace():
            if char == "\n":
                line += 1
                column = 1
            else:
                column += 1
            offset += 1
            continue
        match = _TOKEN.match(source, offset)
        if match is None:
            raise ValueError(f"line {line}, column {column}: unexpected character {char!r}")
        text = match.group()
        tokens.append(Token(text, line, column))
        offset = match.end()
        column += len(text)
    return tuple(tokens)
