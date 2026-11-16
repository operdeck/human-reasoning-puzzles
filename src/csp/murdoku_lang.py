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


@dataclass(frozen=True)
class Name:
    """A named set, a bound variable, or a shorthand item in a union."""

    token: Token


@dataclass(frozen=True)
class Union:
    """A comma-separated union; item names are resolved during typechecking."""

    items: tuple["Operand", ...]


@dataclass(frozen=True)
class Difference:
    left: "Operand"
    right: "Operand"


@dataclass(frozen=True)
class Qualified:
    adjective: Token
    operand: "Operand"


@dataclass(frozen=True)
class Projection:
    kind: Token
    operand: "Operand"


type Operand = Name | Union | Difference | Qualified | Projection

_ADJECTIVES = frozenset({"empty", "occupied", "free"})
_PROJECTIONS = frozenset({"area", "row", "column", "cell"})
_RESERVED = frozenset(
    {
        "and",
        "or",
        "not",
        "iff",
        "if",
        "then",
        "in",
        "on",
        "beside",
        "touches",
        "is",
        "where",
        "except",
        "some",
        "every",
        "no",
        "count",
        "of",
        "exactly",
        "at",
        "least",
        "most",
    }
)


class _Parser:
    def __init__(self, source: str, line: int) -> None:
        self.tokens = tokenize(source, line=line)
        lines = source.split("\n")
        self.end = Token("", line + len(lines) - 1, len(lines[-1]) + 1)
        self.index = 0

    def peek(self) -> Token:
        return self.tokens[self.index] if self.index < len(self.tokens) else self.end

    def take(self) -> Token:
        token = self.peek()
        if token.text:
            self.index += 1
        return token

    def error(self, message: str) -> ValueError:
        token = self.peek()
        return ValueError(f"line {token.line}, column {token.column}: {message}")

    def expect(self, text: str) -> Token:
        if self.peek().text != text:
            raise self.error(f"expected {text!r}, found {self.peek().text or 'end of input'!r}")
        return self.take()

    def operand(self) -> Operand:
        left = self.union()
        while self.peek().text == "except":
            self.take()
            left = Difference(left, self.union())
        return left

    def union(self) -> Operand:
        items = [self.operand_primary()]
        while self.peek().text == ",":
            self.take()
            items.append(self.operand_primary())
        return items[0] if len(items) == 1 else Union(tuple(items))

    def operand_primary(self) -> Operand:
        token = self.peek()
        if token.text == "(":
            self.take()
            result = self.operand()
            self.expect(")")
            return result
        if token.text in _ADJECTIVES:
            self.take()
            return Qualified(token, self.operand_primary())
        if token.text in _PROJECTIONS and self._next_is("of"):
            self.take()
            self.take()
            return Projection(token, self.operand_primary())
        if token.text.isdecimal():
            self.take()
            if self.peek().text == "-":
                self.take()
                end = self.peek()
                if not end.text.isdecimal():
                    raise self.error("expected a number after '-' in a range")
                self.take()
                token = Token(f"{token.text}-{end.text}", token.line, token.column)
            return Name(token)
        if (
            not token.text
            or token.text in _RESERVED
            or not (token.text[0].isalpha() or token.text[0] in "_?")
        ):
            raise self.error(f"expected an operand, found {token.text or 'end of input'!r}")
        self.take()
        return Name(token)

    def _next_is(self, text: str) -> bool:
        return self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].text == text


def parse_operand(source: str, *, line: int = 1) -> Operand:
    """Parse the static set-expression subset, without resolving board names."""
    parser = _Parser(source, line)
    result = parser.operand()
    if parser.peek().text:
        raise parser.error(f"unexpected token {parser.peek().text!r}")
    return result
