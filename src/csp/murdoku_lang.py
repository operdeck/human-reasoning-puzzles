"""Parser foundations for the planned Murdoku expression language.

The existing puzzle reader remains authoritative until the new language is
implemented and the corpus has been migrated.
"""

from dataclasses import dataclass
from typing import assert_never

from lark import Lark, Transformer, Tree, UnexpectedInput, v_args
from lark import Token as LarkToken
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedToken


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


@dataclass(frozen=True)
class AdjectiveFilter:
    source: "Operand"
    operator: Token
    adjective: Token


@dataclass(frozen=True)
class Comprehension:
    variable: Token
    source: "Operand"
    condition: "Formula"


type Operand = (
    Name | Union | Difference | Qualified | Projection | Filter | AdjectiveFilter | Comprehension
)


@dataclass(frozen=True)
class Atom:
    subject: Operand
    operator: Token
    target: Operand
    determiner: Token | None = None
    measure: Measure | None = None


@dataclass(frozen=True)
class AdjectiveAtom:
    subject: Operand
    operator: Token
    adjective: Token
    determiner: Token | None = None


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


@dataclass(frozen=True)
class Integer:
    value: Token


@dataclass(frozen=True)
class Count:
    operand: Operand


@dataclass(frozen=True)
class Arithmetic:
    left: "Number"
    operator: Token
    right: "Number"


type Number = Integer | Count | Arithmetic


@dataclass(frozen=True)
class NumberComparison:
    left: Number
    operator: Token
    right: Number


@dataclass(frozen=True)
class Parity:
    number: Number
    parity: Token


@dataclass(frozen=True)
class NumberRange:
    number: Number
    lower: Token
    upper: Token


@dataclass(frozen=True)
class Quantified:
    quantifier: Token
    count: Token | None
    variables: tuple[Token, ...]
    source: Operand
    body: "Formula"


@dataclass(frozen=True)
class Choice:
    quantifier: Token
    count: Token
    choices: tuple["Formula", ...]


type Formula = (
    Atom
    | AdjectiveAtom
    | SetComparison
    | Negation
    | Binary
    | NumberComparison
    | Parity
    | NumberRange
    | Quantified
    | Choice
)

_KEYWORDS = (
    "and|or|not|iff|if|then|in|on|beside|touches|is|where|except|some|every|no|"
    "count|of|exactly|at|least|most|empty|occupied|free|area|row|column|cell|odd|even"
)
_NAME = (
    r"/\?(?:[^\W\d]|_)\w*/ | /(?!(?:" + _KEYWORDS + r")(?![\w:-]))(?:[^\W\d]|_)[\w-]*(?::[\w-]+)*/"
)

_GRAMMAR = r"""
    ?operand: union ("except" union)*          -> difference
    ?union: primary ("," union_item)*          -> union
    ?union_item: primary | RANGE                -> name
    ?primary: NAME                             -> name
            | ADJECTIVE primary                -> qualified
            | PROJECTION "of" primary          -> projection
            | "(" filtered ")"
            | "(" VARIABLE "in" operand "where" formula ")" -> comprehension
    ?filtered: operand filter_suffix*           -> filtered
    filter_suffix: RELATION union               -> spatial_filter
                 | IS union                     -> spatial_filter
                 | IS ADJECTIVE                 -> adjective_filter
                 | DIRECTION union measure?     -> direction_filter
    measure: COMPARISON NUMBER

    ?formula: IF formula THEN formula           -> implication
            | quantified
            | equivalence
    ?equivalence: disjunction (IFF disjunction)* (IFF quantified)? -> binary
    ?disjunction: conjunction (OR conjunction)* (OR quantified)? -> binary
    ?conjunction: negated (AND negated)* (AND quantified)? -> binary
    ?negated: NOT negated                       -> negation
            | NOT quantified                    -> negation
            | formula_primary
    ?formula_primary: "(" formula ")"
                    | choice
                    | operand RELATION operand   -> relation_atom
                    | operand IS operand         -> relation_atom
                    | operand IS ADJECTIVE       -> adjective_atom
                    | operand DIRECTION operand measure? -> relation_atom
                    | DET operand RELATION operand -> determined_atom
                    | DET operand IS operand       -> determined_atom
                    | DET operand IS ADJECTIVE     -> determined_adjective
                    | DET operand DIRECTION operand measure? -> determined_atom
                    | operand SET_COMPARISON operand  -> set_comparison
                    | number NUM_COMPARISON number -> number_comparison
                    | number PARITY             -> parity
                    | number NUMBER ".." NUMBER -> number_range
    ?number: number ADD_OP number_atom         -> arithmetic
           | number_atom
    ?number_atom: NUMBER                       -> integer
                | COUNT filtered               -> count
                | "(" number ")"
    quantified: quantifier_head VARIABLE ("," VARIABLE)* "in" operand ":" formula
    ?quantifier_head: DET                       -> simple_head
                    | BOUND NUMBER              -> bounded_head
    choice: BOUND NUMBER "of" "(" formula (";" formula)* ")"

    ADJECTIVE.2: /(?:empty|occupied|free)(?![\w:-])/
    PROJECTION.2: /(?:area|row|column|cell)(?![\w:-])/
    RELATION.2: /(?:in|on|beside|touches)(?![\w:-])/
    IS.2: /is(?![\w:-])/
    DET.2: /(?:some|every|no)(?![\w:-])/
    BOUND.2: /(?:exactly|at[ \t]+least|at[ \t]+most)(?![\w:-])/
    VARIABLE: /\?(?:[^\W\d]|_)\w*/
    IF.2: /if(?![\w:-])/
    THEN.2: /then(?![\w:-])/
    IFF.2: /iff(?![\w:-])/
    OR.2: /or(?![\w:-])/
    AND.2: /and(?![\w:-])/
    NOT.2: /not(?![\w:-])/
    DIRECTION.2: /dir:[\w-]+(?::[\w-]+)?(?:\+(?:up|down|left|right))?/
    NAME: __NAME__
    RANGE: /\d+(?:-\d+)?/
    NUMBER: /\d+/
    COMPARISON: "=" | "<=" | ">="
    SET_COMPARISON: "=" | "!="
    NUM_COMPARISON: "=" | "!=" | "<" | "<=" | ">" | ">="
    ADD_OP: "+" | "-"
    PARITY.2: /(?:odd|even)(?![\w:-])/
    COUNT.2: /count(?![\w:-])/
    %import common.WS
    %ignore WS
""".replace("__NAME__", _NAME)

_OPERAND_PARSER = Lark(
    _GRAMMAR,
    start="operand",
    parser="earley",
    lexer="dynamic",
    ambiguity="explicit",
    propagate_positions=True,
)
_FORMULA_PARSER = Lark(
    _GRAMMAR,
    start="formula",
    parser="earley",
    lexer="dynamic",
    ambiguity="explicit",
    propagate_positions=True,
)


@dataclass(frozen=True)
class Statement:
    formula: Formula
    wording: str | None = None


def _token(token: LarkToken, line_offset: int) -> Token:
    assert token.line is not None and token.column is not None
    return Token(str(token), token.line + line_offset, token.column)


@dataclass(frozen=True)
class _FilterSuffix:
    operator: Token
    target: Operand
    measure: Measure | None = None


@dataclass(frozen=True)
class _AdjectiveSuffix:
    operator: Token
    adjective: Token


@dataclass(frozen=True)
class _QuantifierHead:
    quantifier: Token
    count: Token | None = None


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

    def adjective_filter(self, operator: LarkToken, adjective: LarkToken) -> _AdjectiveSuffix:
        return _AdjectiveSuffix(
            _token(operator, self.line_offset), _token(adjective, self.line_offset)
        )

    def direction_filter(
        self, operator: LarkToken, target: Operand, measure: Measure | None = None
    ) -> _FilterSuffix:
        return _FilterSuffix(_token(operator, self.line_offset), target, measure)

    def filtered(self, source: Operand, *suffixes: _FilterSuffix | _AdjectiveSuffix) -> Operand:
        for suffix in suffixes:
            if isinstance(suffix, _AdjectiveSuffix):
                source = AdjectiveFilter(source, suffix.operator, suffix.adjective)
            else:
                source = Filter(source, suffix.operator, suffix.target, suffix.measure)
        return source


@v_args(inline=True)
class _FormulaTransformer(_OperandTransformer):
    def adjective_atom(
        self, subject: Operand, operator: LarkToken, adjective: LarkToken
    ) -> AdjectiveAtom:
        return AdjectiveAtom(
            subject, _token(operator, self.line_offset), _token(adjective, self.line_offset)
        )

    def determined_adjective(
        self, determiner: LarkToken, subject: Operand, operator: LarkToken, adjective: LarkToken
    ) -> AdjectiveAtom:
        return AdjectiveAtom(
            subject,
            _token(operator, self.line_offset),
            _token(adjective, self.line_offset),
            _token(determiner, self.line_offset),
        )

    def comprehension(
        self, variable: LarkToken, source: Operand, condition: Formula
    ) -> Comprehension:
        return Comprehension(_token(variable, self.line_offset), source, condition)

    def simple_head(self, quantifier: LarkToken) -> _QuantifierHead:
        return _QuantifierHead(_token(quantifier, self.line_offset))

    def bounded_head(self, quantifier: LarkToken, count: LarkToken) -> _QuantifierHead:
        return _QuantifierHead(
            _token(quantifier, self.line_offset), _token(count, self.line_offset)
        )

    def quantified(self, head: _QuantifierHead, *parts: object) -> Quantified:
        *variables, source, body = parts
        bound: list[Token] = []
        for variable in variables:
            assert isinstance(variable, LarkToken)
            bound.append(_token(variable, self.line_offset))
        assert isinstance(
            source,
            Name
            | Union
            | Difference
            | Qualified
            | Projection
            | Filter
            | AdjectiveFilter
            | Comprehension,
        )
        assert isinstance(
            body,
            Atom
            | AdjectiveAtom
            | SetComparison
            | Negation
            | Binary
            | NumberComparison
            | Parity
            | NumberRange
            | Quantified
            | Choice,
        )
        return Quantified(head.quantifier, head.count, tuple(bound), source, body)

    def choice(self, quantifier: LarkToken, count: LarkToken, *choices: Formula) -> Choice:
        return Choice(
            _token(quantifier, self.line_offset), _token(count, self.line_offset), choices
        )

    def integer(self, value: LarkToken) -> Integer:
        return Integer(_token(value, self.line_offset))

    def count(self, _count: LarkToken, operand: Operand) -> Count:
        return Count(operand)

    def arithmetic(self, left: Number, operator: LarkToken, right: Number) -> Arithmetic:
        return Arithmetic(left, _token(operator, self.line_offset), right)

    def number_comparison(
        self, left: Number, operator: LarkToken, right: Number
    ) -> NumberComparison:
        return NumberComparison(left, _token(operator, self.line_offset), right)

    def parity(self, number: Number, parity: LarkToken) -> Parity:
        return Parity(number, _token(parity, self.line_offset))

    def number_range(self, number: Number, lower: LarkToken, upper: LarkToken) -> NumberRange:
        return NumberRange(number, _token(lower, self.line_offset), _token(upper, self.line_offset))

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
            assert isinstance(
                right,
                Atom
                | AdjectiveAtom
                | SetComparison
                | Negation
                | Binary
                | NumberComparison
                | Parity
                | NumberRange
                | Quantified
                | Choice,
            )
            result = Binary(result, _token(operator, self.line_offset), right)
        return result

    def implication(
        self, operator: LarkToken, left: Formula, _then: LarkToken, right: Formula
    ) -> Binary:
        return Binary(left, _token(operator, self.line_offset), right)


def _resolve_ambiguity(tree: Tree[LarkToken], line: int) -> Tree[LarkToken]:
    children = [
        _resolve_ambiguity(child, line) if isinstance(child, Tree) else child
        for child in tree.children
    ]
    if tree.data == "_ambig":
        assert all(isinstance(child, Tree) for child in children)
        alternatives = [child for child in children if isinstance(child, Tree)]
        spans = [
            sorted(
                (node.meta.start_pos, node.meta.end_pos)
                for node in candidate.iter_subtrees()
                if node.data == "quantified"
            )
            for candidate in alternatives
        ]
        starts = [tuple(start for start, _ in candidate) for candidate in spans]
        if any(candidate != starts[0] for candidate in starts[1:]):
            raise ValueError(f"line {line}: ambiguous expression")
        # A quantifier consumes the longest body before the enclosing delimiter.
        lengths = [tuple(end for _, end in candidate) for candidate in spans]
        longest = max(lengths)
        preferred = [
            candidate
            for candidate, candidate_lengths in zip(alternatives, lengths, strict=True)
            if candidate_lengths == longest
        ]
        if any(candidate != preferred[0] for candidate in preferred[1:]):
            raise ValueError(f"line {line}: ambiguous expression")
        return preferred[0]
    return Tree(tree.data, children, tree.meta)


def _parse(parser: Lark, source: str, line: int) -> object:
    try:
        tree = parser.parse(source)
    except UnexpectedInput as exc:
        error_line, column = exc.line + line - 1, exc.column
        if isinstance(exc, UnexpectedEOF) or (
            isinstance(exc, UnexpectedToken) and exc.token.type == "$END"
        ):
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
    return _FormulaTransformer(line - 1).transform(_resolve_ambiguity(tree, line))


def _bound_references(
    variables: tuple[Token, ...],
    source: Operand,
    body: Formula,
    outer: frozenset[str],
) -> set[str]:
    references = _references(source, outer)
    declared: set[str] = set()
    for variable in variables:
        if variable.text in outer or variable.text in declared:
            raise ValueError(
                f"line {variable.line}, column {variable.column}: "
                f"variable {variable.text!r} clashes with an existing binding"
            )
        declared.add(variable.text)
    body_references = _references(body, outer | declared)
    for variable in variables:
        if variable.text not in body_references:
            raise ValueError(
                f"line {variable.line}, column {variable.column}: unused variable {variable.text!r}"
            )
    return references | (body_references - declared)


def _references(node: Operand | Formula | Number, bound: frozenset[str]) -> set[str]:
    match node:
        case Name(token=token):
            if not token.text.startswith("?"):
                return set()
            if token.text not in bound:
                raise ValueError(
                    f"line {token.line}, column {token.column}: unbound variable {token.text!r}"
                )
            return {token.text}
        case Union(items=items) | Choice(choices=items):
            return set().union(*(_references(item, bound) for item in items))
        case Difference(left=left, right=right) | SetComparison(left=left, right=right):
            return _references(left, bound) | _references(right, bound)
        case Qualified(operand=operand) | Projection(operand=operand) | Count(operand=operand):
            return _references(operand, bound)
        case Filter(source=source, target=target):
            return _references(source, bound) | _references(target, bound)
        case AdjectiveFilter(source=source):
            return _references(source, bound)
        case Comprehension(variable=variable, source=source, condition=condition):
            return _bound_references((variable,), source, condition, bound)
        case Atom(subject=subject, target=target):
            return _references(subject, bound) | _references(target, bound)
        case AdjectiveAtom(subject=subject):
            return _references(subject, bound)
        case Negation(formula=formula):
            return _references(formula, bound)
        case Binary(left=left, right=right):
            return _references(left, bound) | _references(right, bound)
        case NumberComparison(left=left, right=right) | Arithmetic(left=left, right=right):
            return _references(left, bound) | _references(right, bound)
        case Parity(number=number) | NumberRange(number=number):
            return _references(number, bound)
        case Quantified(variables=variables, source=source, body=body):
            return _bound_references(variables, source, body, bound)
        case Integer():
            return set()
        case _:
            assert_never(node)


def parse_operand(source: str, *, line: int = 1) -> Operand:
    """Parse a set-expression subset, without resolving or typechecking names."""
    result = _parse(_OPERAND_PARSER, source, line)
    assert isinstance(
        result,
        Name
        | Union
        | Difference
        | Qualified
        | Projection
        | Filter
        | AdjectiveFilter
        | Comprehension,
    )
    _references(result, frozenset())
    return result


def parse_formula(source: str, *, line: int = 1) -> Formula:
    """Parse the implemented formula subset, without board-dependent checks."""
    result = _parse(_FORMULA_PARSER, source, line)
    assert isinstance(
        result,
        Atom
        | AdjectiveAtom
        | SetComparison
        | Negation
        | Binary
        | NumberComparison
        | Parity
        | NumberRange
        | Quantified
        | Choice,
    )
    _references(result, frozenset())
    return result


def parse_statement(source: str, *, line: int = 1) -> Statement:
    """Parse a formula and preserve its optional author-supplied wording."""
    formula, separator, wording = source.partition("|")
    return Statement(parse_formula(formula, line=line), wording.strip() if separator else None)
