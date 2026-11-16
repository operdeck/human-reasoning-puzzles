"""Parser foundations for the planned Murdoku expression language.

The existing puzzle reader remains authoritative until the new language is
implemented and the corpus has been migrated.
"""

from dataclasses import dataclass

from lark import Lark, Transformer, UnexpectedInput, v_args
from lark import Token as LarkToken
from lark.exceptions import UnexpectedCharacters, UnexpectedToken


@dataclass(frozen=True)
class Token:
    """A lexical token with its one-based position in the source."""

    text: str
    line: int
    column: int


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


@dataclass(frozen=True)
class Measure:
    comparison: Token
    value: Token


@dataclass(frozen=True)
class Filter:
    source: "Operand"
    operator: Token
    target: "Operand"
    measure: Measure | None = None


type Operand = Name | Union | Difference | Qualified | Projection | Filter


@dataclass(frozen=True)
class Atom:
    subject: Operand
    operator: Token
    target: Operand
    determiner: Token | None = None
    measure: Measure | None = None


@dataclass(frozen=True)
class SetComparison:
    left: Operand
    operator: Token
    right: Operand


@dataclass(frozen=True)
class Negation:
    operator: Token
    formula: "Formula"


@dataclass(frozen=True)
class Binary:
    left: "Formula"
    operator: Token
    right: "Formula"


type Formula = Atom | SetComparison | Negation | Binary

_GRAMMAR = r"""
    ?operand: union ("except" union)*          -> difference
    ?union: primary ("," primary)*             -> union
    ?primary: NAME                             -> name
            | RANGE                            -> name
            | ADJECTIVE primary                -> qualified
            | PROJECTION "of" primary          -> projection
            | "(" filtered ")"
    ?filtered: operand filter_suffix*           -> filtered
    filter_suffix: RELATION union               -> spatial_filter
                 | DIRECTION union measure?     -> direction_filter
    measure: COMPARISON NUMBER

    ?formula: IF formula THEN formula           -> implication
            | equivalence
    ?equivalence: disjunction (IFF disjunction)* -> binary
    ?disjunction: conjunction (OR conjunction)* -> binary
    ?conjunction: negated (AND negated)*        -> binary
    ?negated: NOT negated                       -> negation
            | formula_primary
    ?formula_primary: "(" formula ")"
                    | operand RELATION operand   -> relation_atom
                    | operand DIRECTION operand measure? -> relation_atom
                    | DET operand RELATION operand -> determined_atom
                    | DET operand DIRECTION operand measure? -> determined_atom
                    | operand SET_COMPARISON operand  -> set_comparison

    ADJECTIVE.2: /(?:empty|occupied|free)(?![\w:-])/
    PROJECTION.2: /(?:area|row|column|cell)(?![\w:-])/
    RELATION.2: /(?:in|on|beside|touches|is)(?![\w:-])/
    DET.2: /(?:some|every|no)(?![\w:-])/
    IF.2: /if(?![\w:-])/
    THEN.2: /then(?![\w:-])/
    IFF.2: /iff(?![\w:-])/
    OR.2: /or(?![\w:-])/
    AND.2: /and(?![\w:-])/
    NOT.2: /not(?![\w:-])/
    DIRECTION.2: /dir:[\w-]+(?::[\w-]+)?(?:\+(?:up|down|left|right))?/
    NAME: /\?(?:[^\W\d]|_)\w*/ | /(?:[^\W\d]|_)[\w-]*(?::[\w-]+)*/
    RANGE: /\d+(?:-\d+)?/
    NUMBER: /\d+/
    COMPARISON: "=" | "<=" | ">="
    SET_COMPARISON: "=" | "!="
    %import common.WS
    %ignore WS
"""

_OPERAND_PARSER = Lark(_GRAMMAR, start="operand", parser="lalr", propagate_positions=True)
_FORMULA_PARSER = Lark(
    _GRAMMAR, start="formula", parser="earley", lexer="dynamic", ambiguity="explicit"
)


def _token(token: LarkToken, line_offset: int) -> Token:
    assert token.line is not None and token.column is not None
    return Token(str(token), token.line + line_offset, token.column)


@dataclass(frozen=True)
class _FilterSuffix:
    operator: Token
    target: Operand
    measure: Measure | None = None


@v_args(inline=True)
class _OperandTransformer(Transformer[LarkToken, Operand | Formula]):
    def __init__(self, line_offset: int) -> None:
        super().__init__()
        self.line_offset = line_offset

    def name(self, token: LarkToken) -> Name:
        return Name(_token(token, self.line_offset))

    def union(self, *items: Operand) -> Operand:
        return items[0] if len(items) == 1 else Union(items)

    def difference(self, first: Operand, *others: Operand) -> Operand:
        result = first
        for other in others:
            result = Difference(result, other)
        return result

    def qualified(self, adjective: LarkToken, operand: Operand) -> Qualified:
        return Qualified(_token(adjective, self.line_offset), operand)

    def projection(self, kind: LarkToken, operand: Operand) -> Projection:
        return Projection(_token(kind, self.line_offset), operand)

    def measure(self, comparison: LarkToken, value: LarkToken) -> Measure:
        return Measure(_token(comparison, self.line_offset), _token(value, self.line_offset))

    def spatial_filter(self, operator: LarkToken, target: Operand) -> _FilterSuffix:
        return _FilterSuffix(_token(operator, self.line_offset), target)

    def direction_filter(
        self, operator: LarkToken, target: Operand, measure: Measure | None = None
    ) -> _FilterSuffix:
        return _FilterSuffix(_token(operator, self.line_offset), target, measure)

    def filtered(self, source: Operand, *suffixes: _FilterSuffix) -> Operand:
        for suffix in suffixes:
            source = Filter(source, suffix.operator, suffix.target, suffix.measure)
        return source


@v_args(inline=True)
class _FormulaTransformer(_OperandTransformer):
    def relation_atom(
        self, subject: Operand, operator: LarkToken, target: Operand, measure: Measure | None = None
    ) -> Atom:
        return Atom(subject, _token(operator, self.line_offset), target, measure=measure)

    def determined_atom(
        self,
        determiner: LarkToken,
        subject: Operand,
        operator: LarkToken,
        target: Operand,
        measure: Measure | None = None,
    ) -> Atom:
        return Atom(
            subject,
            _token(operator, self.line_offset),
            target,
            determiner=_token(determiner, self.line_offset),
            measure=measure,
        )

    def set_comparison(self, left: Operand, operator: LarkToken, right: Operand) -> SetComparison:
        return SetComparison(left, _token(operator, self.line_offset), right)

    def negation(self, operator: LarkToken, formula: Formula) -> Negation:
        return Negation(_token(operator, self.line_offset), formula)

    def binary(self, first: Formula, *parts: LarkToken | Formula) -> Formula:
        result = first
        for index in range(0, len(parts), 2):
            operator, right = parts[index : index + 2]
            assert isinstance(operator, LarkToken)
            assert isinstance(right, Atom | SetComparison | Negation | Binary)
            result = Binary(result, _token(operator, self.line_offset), right)
        return result

    def implication(
        self, operator: LarkToken, left: Formula, _then: LarkToken, right: Formula
    ) -> Binary:
        return Binary(left, _token(operator, self.line_offset), right)


def _parse(parser: Lark, source: str, line: int) -> object:
    try:
        tree = parser.parse(source)
    except UnexpectedInput as exc:
        error_line, column = exc.line + line - 1, exc.column
        if isinstance(exc, UnexpectedToken) and exc.token.type == "$END":
            lines = source.split("\n")
            error_line, column = line + len(lines) - 1, len(lines[-1]) + 1
            found = "end of input"
        elif isinstance(exc, UnexpectedToken):
            found = repr(str(exc.token))
        elif isinstance(exc, UnexpectedCharacters):
            found = repr(exc.char)
        else:
            found = "input"
        raise ValueError(f"line {error_line}, column {column}: unexpected {found}") from exc
    if any(subtree.data == "_ambig" for subtree in tree.iter_subtrees()):
        raise ValueError(f"line {line}: ambiguous expression")
    return _FormulaTransformer(line - 1).transform(tree)


def parse_operand(source: str, *, line: int = 1) -> Operand:
    """Parse a set-expression subset, without resolving or typechecking names."""
    result = _parse(_OPERAND_PARSER, source, line)
    assert isinstance(result, Name | Union | Difference | Qualified | Projection | Filter)
    return result


def parse_formula(source: str, *, line: int = 1) -> Formula:
    """Parse the implemented formula subset, without board-dependent checks."""
    result = _parse(_FORMULA_PARSER, source, line)
    assert isinstance(result, Atom | SetComparison | Negation | Binary)
    return result
