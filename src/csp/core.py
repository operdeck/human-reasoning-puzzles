"""Exact-cover and cardinality constraint engine.

A puzzle is compiled into a `Model` of

* literals    - atomic choices, such as ``r3c4=7`` or ``Tim=r1c2``,
* constraints - sets of literals with allowed counts of true members; exactly-one
    and at-most-one are the common special cases,
* relations   - predicates over the values of two or more variables.

`Solver` applies named deduction `Rule`s until nothing more follows. Every
deduction is logged as a `Step` with a human-readable reason.

Nothing in this module knows about any particular puzzle.
"""

import copy
import itertools
from bisect import bisect_left
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import product
from typing import Any, NamedTuple, Self

type LiteralId = int
type ConstraintId = int


class Truth(Enum):
    UNKNOWN = 0
    TRUE = 1
    FALSE = 2


class Kind(Enum):
    """How a constraint counts its true literals."""

    EXACTLY_ONE = "exactly one"
    AT_MOST_ONE = "at most one"
    COUNT = "count"


class Contradiction(Exception):
    """The current state cannot be extended to any solution.

    `source` names the constraint or relation that broke, when known.
    """

    def __init__(self, message: str, source: str | None = None) -> None:
        super().__init__(message)
        self.source = source


@dataclass(frozen=True)
class Literal:
    """The choice "variable `var` takes `value`"."""

    index: LiteralId
    var: str
    value: Any

    def __str__(self) -> str:
        return f"{self.var}={self.value}"


@dataclass(frozen=True)
class Constraint:
    """A set of literals with an allowed set of true counts.

    If `reified_by` is set, that literal is true exactly when the count is
    allowed; otherwise the complementary counts are allowed.

    `family` names the rule of the puzzle it is one instance of, such as
    "each digit once per row"; it only matters for explaining the model.
    """

    index: ConstraintId
    name: str
    kind: Kind
    literals: tuple[LiteralId, ...]
    allowed_counts: frozenset[int]
    reified_by: LiteralId | None = None
    family: str | None = None


@dataclass(frozen=True)
class Relation:
    """`holds(*values)` must be true in any solution, values in `variables` order."""

    name: str
    variables: tuple[str, ...]
    holds: Callable[..., bool]


@dataclass(frozen=True)
class Step:
    """One logged deduction: `var=value` was asserted or ruled out, and why.

    `reason` says why for people; the other fields say it for programs.
    `sources` names the constraints or relations the deduction rests on, and
    `scope` the constraints whose other options it pruned (subsumption,
    cover). `placing` is the var=value whose placement ruled this one out.
    `trail` holds what_if's steps from the assumption to the contradiction.
    `chain` holds a chain's literals as (var, value), start first: false,
    true, false, ... alternately, ending on one that must then be true.
    """

    var: str
    value: Any
    asserted: bool
    rule: str
    reason: str
    sources: tuple[str, ...] = ()
    scope: tuple[str, ...] = ()
    placing: tuple[str, Any] | None = None
    trail: tuple["Step", ...] = ()
    chain: tuple[tuple[str, Any], ...] = ()

    @property
    def literal(self) -> str:
        return f"{self.var}={self.value}"

    def __str__(self) -> str:
        arrow = "=" if self.asserted else "x"
        return f"{arrow} {self.literal}  ({self.reason})"


class Model:
    """Literals, count constraints and relations, plus their current truth state.

    Build it with `literal`, `constrain` and `relate`; rules then read it
    through the inspection methods and change it only via `assign` and
    `eliminate`, which log every change.
    """

    def __init__(self) -> None:
        self._literals: list[Literal] = []
        self._by_key: dict[tuple[str, Any], LiteralId] = {}
        self._state: list[Truth] = []
        self._in_constraints: list[list[ConstraintId]] = []
        self._constraints: list[Constraint] = []
        self._relations: list[Relation] = []
        self._domain_of: dict[str, ConstraintId] = {}
        self.log: list[Step] = []

    # --- construction -----------------------------------------------------

    def literal(self, var: str, value: Any) -> LiteralId:
        """The literal `var=value`, created on first use."""
        key = (var, value)
        if key in self._by_key:
            return self._by_key[key]
        index = len(self._literals)
        self._literals.append(Literal(index, var, value))
        self._state.append(Truth.UNKNOWN)
        self._in_constraints.append([])
        self._by_key[key] = index
        return index

    def constrain(
        self,
        name: str,
        kind: Kind,
        literals: Iterable[LiteralId],
        *,
        allowed_counts: Iterable[int] | None = None,
        reified_by: LiteralId | None = None,
        defines: str | None = None,
        family: str | None = None,
    ) -> ConstraintId:
        """Add a constraint over literals.

        `EXACTLY_ONE` and `AT_MOST_ONE` retain their familiar meanings.
        `COUNT` requires `allowed_counts`, the permitted numbers of true
        literals. With `reified_by`, that literal is true iff the count is in
        `allowed_counts`. `defines` marks the constraint as a variable's domain.
        """
        literals = tuple(literals)
        if kind is Kind.EXACTLY_ONE:
            if allowed_counts is not None or reified_by is not None:
                raise ValueError("EXACTLY_ONE does not take allowed_counts or reified_by")
            counts = frozenset((1,))
        elif kind is Kind.AT_MOST_ONE:
            if allowed_counts is not None or reified_by is not None:
                raise ValueError("AT_MOST_ONE does not take allowed_counts or reified_by")
            counts = frozenset((0, 1))
        else:
            if allowed_counts is None:
                raise ValueError("COUNT needs a non-empty allowed_counts set")
            counts = frozenset(allowed_counts)
            if not counts:
                raise ValueError("COUNT needs a non-empty allowed_counts set")
            if any(
                not isinstance(count, int)
                or isinstance(count, bool)
                or not 0 <= count <= len(literals)
                for count in counts
            ):
                raise ValueError(f"COUNT values must be between 0 and {len(literals)}")
            if len(set(literals)) != len(literals):
                raise ValueError("COUNT cannot contain a literal more than once")
            if reified_by is not None and (
                reified_by not in range(len(self._literals)) or reified_by in literals
            ):
                raise ValueError("reified_by must be a separate literal in this model")
        index = len(self._constraints)
        constraint = Constraint(index, name, kind, literals, counts, reified_by, family)
        self._constraints.append(constraint)
        for lit in constraint.literals:
            self._in_constraints[lit].append(index)
        if reified_by is not None:
            self._in_constraints[reified_by].append(index)
        if defines is not None:
            self._domain_of[defines] = index
        return index

    def relate(self, name: str, variables: Iterable[str], holds: Callable[..., bool]) -> None:
        """Require `holds(*values)` of the named variables' values, in order."""
        self._relations.append(Relation(name, tuple(variables), holds))

    def clone(self) -> Self:
        """A copy with its own truth state and an empty log.

        Structure is shared, so only clone a model that is fully built.
        """
        twin = copy.copy(self)
        twin._state = list(self._state)
        twin.log = []
        return twin

    # --- inspection -------------------------------------------------------

    @property
    def num_literals(self) -> int:
        return len(self._literals)

    @property
    def constraints(self) -> Sequence[Constraint]:
        return self._constraints

    @property
    def relations(self) -> Sequence[Relation]:
        return self._relations

    @property
    def variables(self) -> list[str]:
        return list(self._domain_of)

    def domain_of(self, var: str) -> ConstraintId:
        """The EXACTLY_ONE constraint listing every value `var` could take."""
        return self._domain_of[var]

    def describe(self, lit: LiteralId) -> str:
        return str(self._literals[lit])

    def value_of(self, lit: LiteralId) -> Any:
        return self._literals[lit].value

    def var_of(self, lit: LiteralId) -> str:
        return self._literals[lit].var

    def is_true(self, lit: LiteralId) -> bool:
        return self._state[lit] is Truth.TRUE

    def is_false(self, lit: LiteralId) -> bool:
        return self._state[lit] is Truth.FALSE

    def constraints_of(self, lit: LiteralId) -> Sequence[ConstraintId]:
        """Constraints that count this literal or use it as a reifier."""
        return self._in_constraints[lit]

    def live(self, constraint: ConstraintId) -> list[LiteralId]:
        """Literals of a constraint that are still undecided."""
        literals = self._constraints[constraint].literals
        return [lit for lit in literals if self._state[lit] is Truth.UNKNOWN]

    def active_counts(self, constraint: ConstraintId) -> frozenset[int]:
        """Counts allowed by the constraint and its reifier's current truth."""
        item = self._constraints[constraint]
        if item.reified_by is None or self.is_true(item.reified_by):
            return item.allowed_counts
        if self.is_false(item.reified_by):
            return frozenset(range(len(item.literals) + 1)) - item.allowed_counts
        return frozenset(range(len(item.literals) + 1))

    def feasible_counts(self, constraint: ConstraintId) -> frozenset[int]:
        """Allowed totals between the number already true and the live maximum.

        If the reifier is undecided, either truth value remains possible, so
        every total is provisionally feasible.
        """
        item = self._constraints[constraint]
        already_true = sum(self.is_true(lit) for lit in item.literals)
        maximum = already_true + len(self.live(constraint))
        return frozenset(
            count for count in self.active_counts(constraint) if already_true <= count <= maximum
        )

    def satisfied(self, constraint: ConstraintId) -> bool:
        """Whether every remaining completion satisfies this constraint."""
        item = self._constraints[constraint]
        if item.reified_by is not None and not (
            self.is_true(item.reified_by) or self.is_false(item.reified_by)
        ):
            return False
        already_true = sum(self.is_true(lit) for lit in item.literals)
        maximum = already_true + len(self.live(constraint))
        return all(
            count in self.active_counts(constraint) for count in range(already_true, maximum + 1)
        )

    def options(self, var: str) -> list[LiteralId]:
        """Literals for `var` that are not ruled out (undecided or true)."""
        domain = self._constraints[self._domain_of[var]]
        return [lit for lit in domain.literals if not self.is_false(lit)]

    def chosen(self, var: str) -> Any | None:
        """The value `var` has been assigned, or None while it is open."""
        domain = self._constraints[self._domain_of[var]]
        for lit in domain.literals:
            if self.is_true(lit):
                return self._literals[lit].value
        return None

    def assignment(self) -> dict[str, Any]:
        """Variables decided so far."""
        decided = {var: self.chosen(var) for var in self._domain_of}
        return {var: value for var, value in decided.items() if value is not None}

    def solution(self) -> dict[str, Any] | None:
        """The full assignment, or None if any variable is still open."""
        decided = self.assignment()
        return decided if len(decided) == len(self._domain_of) else None

    # --- mutation ---------------------------------------------------------

    def eliminate(
        self,
        lit: LiteralId,
        rule: str,
        reason: str,
        *,
        sources: tuple[str, ...] = (),
        scope: tuple[str, ...] = (),
        placing: tuple[str, Any] | None = None,
        trail: tuple[Step, ...] = (),
        chain: tuple[tuple[str, Any], ...] = (),
    ) -> bool:
        """Rule `lit` out. Returns whether that changed anything.

        The keywords become the logged `Step`'s fields of the same names.
        """
        match self._state[lit]:
            case Truth.FALSE:
                return False
            case Truth.TRUE:
                raise Contradiction(
                    f"{self.describe(lit)} is already true; {reason}",
                    sources[0] if sources else None,
                )
        self._state[lit] = Truth.FALSE
        literal = self._literals[lit]
        self.log.append(
            Step(
                literal.var,
                literal.value,
                False,
                rule,
                reason,
                sources,
                scope,
                placing,
                trail,
                chain,
            )
        )
        return True

    def assign(
        self, lit: LiteralId, rule: str, reason: str, *, sources: tuple[str, ...] = ()
    ) -> bool:
        """Make `lit` true and apply any immediate upper-count consequences.

        Other literals are removed only when no currently allowed count can
        accommodate another true member. Lower bounds and count-set gaps are
        propagated by `rule_count`.
        """
        match self._state[lit]:
            case Truth.TRUE:
                return False
            case Truth.FALSE:
                raise Contradiction(
                    f"{self.describe(lit)} is already ruled out; {reason}",
                    sources[0] if sources else None,
                )
        self._state[lit] = Truth.TRUE
        literal = self._literals[lit]
        self.log.append(Step(literal.var, literal.value, True, rule, reason, sources))
        for ci in self._in_constraints[lit]:
            constraint = self._constraints[ci]
            true_count = sum(self.is_true(item) for item in constraint.literals)
            open_literals = self.live(ci)
            if not self.feasible_counts(ci):
                raise Contradiction(f"{constraint.name}: no allowed count remains", constraint.name)
            if not any(
                count > true_count and count <= true_count + len(open_literals)
                for count in self.active_counts(ci)
            ):
                for other in open_literals:
                    self.eliminate(
                        other,
                        rule,
                        f"{literal} holds in {constraint.name}",
                        sources=(constraint.name,),
                        placing=(literal.var, literal.value),
                    )
        return True

    def check(self) -> None:
        """Raise Contradiction if a constraint has no feasible true count."""
        for constraint in self._constraints:
            states = [self._state[lit] for lit in constraint.literals]
            if constraint.kind is not Kind.COUNT and states.count(Truth.TRUE) > 1:
                raise Contradiction(
                    f"{constraint.name}: more than one literal true", constraint.name
                )
            if not self.feasible_counts(constraint.index):
                if constraint.kind is Kind.EXACTLY_ONE and all(s is Truth.FALSE for s in states):
                    raise Contradiction(
                        f"{constraint.name}: every option eliminated", constraint.name
                    )
                raise Contradiction(f"{constraint.name}: no allowed count remains", constraint.name)


# --- rules ----------------------------------------------------------------
# A rule inspects the model, makes one deduction (which may rule out several
# literals at once), and returns whether it changed anything. Every rule must
# be sound for any model, and must log its deductions under its own
# `Rule.name`.


class Rule(NamedTuple):
    name: str
    apply: Callable[[Model], bool]


def rule_single(model: Model) -> bool:
    """Force a lone option in EXACTLY_ONE or a count with one feasible total.

    This covers Sudoku's naked single (the constraint is "this cell holds one
    digit") and its hidden single (the constraint is "this digit sits once in
    this row") with no special-casing. A COUNT with one live literal also
    forces it true or false when only one total remains feasible.
    """
    for constraint in model.constraints:
        if model.satisfied(constraint.index):
            continue
        live = model.live(constraint.index)
        if constraint.kind is Kind.EXACTLY_ONE and len(live) == 1:
            model.assign(
                live[0],
                "single",
                f"only option left in {constraint.name}",
                sources=(constraint.name,),
            )
            return True
        if constraint.kind is Kind.COUNT and len(live) == 1:
            feasible = model.feasible_counts(constraint.index)
            true_count = sum(model.is_true(lit) for lit in constraint.literals)
            if feasible == {true_count}:
                model.eliminate(
                    live[0],
                    "single",
                    f"{constraint.name} must stay at {true_count} true literals",
                    sources=(constraint.name,),
                )
                return True
            if feasible == {true_count + 1}:
                model.assign(
                    live[0],
                    "single",
                    f"{constraint.name} must reach {true_count + 1} true literals",
                    sources=(constraint.name,),
                )
                return True
    return False


def rule_relations(model: Model) -> bool:
    """Generalised arc consistency: drop every value that no combination of the
    other variables' values can satisfy, one relation at a time.

    All unsupported values of a relation go together. That is sound: support
    is checked against the options before any are removed, and removing
    options never creates support.
    """
    return any(prune_relation(model, relation) for relation in model.relations)


def rule_count(model: Model) -> bool:
    """Propagate allowed counts, including parity and reified count constraints."""
    return any(
        propagate_count(model, constraint.index)
        for constraint in model.constraints
        if constraint.kind is Kind.COUNT
    )


def propagate_count(model: Model, constraint_id: ConstraintId) -> bool:
    """Make one sound deduction from a count constraint; whether it changed state."""
    constraint = model.constraints[constraint_id]
    if constraint.kind is not Kind.COUNT or model.satisfied(constraint_id):
        return False

    live = model.live(constraint_id)
    already_true = sum(model.is_true(lit) for lit in constraint.literals)
    possible = range(already_true, already_true + len(live) + 1)
    if constraint.reified_by is not None and not (
        model.is_true(constraint.reified_by) or model.is_false(constraint.reified_by)
    ):
        can_be_true = any(count in constraint.allowed_counts for count in possible)
        can_be_false = any(count not in constraint.allowed_counts for count in possible)
        if not can_be_true:
            model.eliminate(
                constraint.reified_by,
                "count",
                f"{constraint.name} cannot reach an allowed count",
                sources=(constraint.name,),
            )
            return True
        if not can_be_false:
            model.assign(
                constraint.reified_by,
                "count",
                f"{constraint.name} can reach only allowed counts",
                sources=(constraint.name,),
            )
            return True
        return False

    allowed = model.active_counts(constraint_id)
    can_be_true = any(
        total in allowed for total in range(already_true + 1, already_true + len(live) + 1)
    )
    can_be_false = any(total in allowed for total in range(already_true, already_true + len(live)))
    eliminate: list[LiteralId] = []
    for lit in live:
        if not can_be_true:
            eliminate.append(lit)
        elif not can_be_false:
            model.assign(
                lit,
                "count",
                f"{constraint.name} requires this literal to reach an allowed count",
                sources=(constraint.name,),
            )
            return True
    for lit in eliminate:
        model.eliminate(
            lit,
            "count",
            f"{constraint.name} cannot reach an allowed count with this literal true",
            sources=(constraint.name,),
        )
    return bool(eliminate)


def prune_relation(model: Model, relation: Relation) -> bool:
    """Drop the values `relation` leaves without support; whether any went."""
    domains = [model.options(var) for var in relation.variables]
    unsupported = _unsupported(model, relation, domains)
    for lit in unsupported:
        model.eliminate(
            lit, "relations", f"nothing satisfies {relation.name}", sources=(relation.name,)
        )
    return bool(unsupported)


def _unsupported(
    model: Model, relation: Relation, domains: list[list[LiteralId]]
) -> list[LiteralId]:
    """Options that appear in no combination satisfying `relation`.

    One pass over the combinations serves every variable at once, skipping
    combinations that could not support anything new, and stopping as soon
    as every option has support.
    """
    lacking = [set(options) for options in domains]
    for combo in product(*domains):
        if not any(lit in lacking[i] for i, lit in enumerate(combo)):
            continue
        if relation.holds(*(model.value_of(lit) for lit in combo)):
            for i, lit in enumerate(combo):
                lacking[i].discard(lit)
            if not any(lacking):
                return []
    return [lit for i, options in enumerate(domains) for lit in options if lit in lacking[i]]


def rule_subsumption(model: Model) -> bool:
    """If one required true literal fills an outer constraint's remaining capacity.

    The inner constraint guarantees one additional true literal, and all of
    its live options are inside the outer constraint. If the outer has room
    for exactly one more true literal, every other outer option is false.

    In Sudoku this is the pointing pair and box/line reduction at once; in
    Murdoku it prunes rows against regions. Nothing here is puzzle-specific.
    """
    for a in model.constraints:
        if model.satisfied(a.index) or _minimum_additional(model, a.index) != 1:
            continue
        candidates: set[ConstraintId] = set()
        for lit in model.live(a.index):
            candidates.update(model.constraints_of(lit))
        candidates.discard(a.index)
        if any(cover(model, [a.index], [b]) for b in sorted(candidates)):
            return True
    return False


def _minimum_additional(model: Model, constraint: ConstraintId) -> int:
    """The fewest more literals this constraint requires to become true."""
    counts = model.feasible_counts(constraint)
    if not counts:
        return 0
    already_true = sum(model.is_true(lit) for lit in model.constraints[constraint].literals)
    return min(counts) - already_true


def _maximum_additional(model: Model, constraint: ConstraintId) -> int:
    """The most more literals this constraint can allow to become true."""
    counts = model.feasible_counts(constraint)
    if not counts:
        return 0
    already_true = sum(model.is_true(lit) for lit in model.constraints[constraint].literals)
    return max(counts) - already_true


def cover(model: Model, inner: Sequence[ConstraintId], outer: Sequence[ConstraintId]) -> bool:
    """If disjoint inner options use all aggregate capacity of the outer set,
    rule out the rest of the outer options.

    Each inner constraint contributes its minimum guaranteed number of
    additional truths. If those totals equal the outer constraints' combined
    maximum additional capacity, any outer literal outside the inner union
    would exceed that capacity. Whether anything was ruled out.
    """
    constraints = model.constraints
    if not inner or not outer:
        return False
    if any(model.satisfied(ci) for ci in (*inner, *outer)):
        return False
    lives = [set(model.live(a)) for a in inner]
    union = set().union(*lives)
    if (
        not all(lives)
        or len(union) != sum(map(len, lives))
        or any(_minimum_additional(model, ci) < 1 for ci in inner)
    ):
        return False
    around = set().union(*(model.live(b) for b in outer))
    if not union < around:
        return False
    required = sum(_minimum_additional(model, ci) for ci in inner)
    capacity = sum(_maximum_additional(model, ci) for ci in outer)
    if required != capacity:
        return False
    a_names = tuple(constraints[a].name for a in inner)
    b_names = tuple(constraints[b].name for b in outer)
    if required == 1:
        rule, reason = "subsumption", f"{a_names[0]} already uses one of {b_names[0]}"
    else:
        rule, reason = f"cover{required}", f"{', '.join(a_names)} use up {', '.join(b_names)}"
    for lit in sorted(around - union):
        model.eliminate(lit, rule, reason, sources=a_names, scope=b_names)
    return True


def rule_cover(k: int) -> Callable[[Model], bool]:
    """Find covers whose inner constraints guarantee `k` additional truths.

    The inner constraints have pairwise-disjoint live sets. Their lower bounds
    sum to `k`, and their live literals fit inside outer constraints whose
    combined remaining capacity is also `k`. Those outer constraints are full;
    every option outside the inner union is false.

    In Sudoku, As as cells and Bs as digit-in-house give naked subsets;
    swapped, hidden subsets; As as digit-in-row and Bs as digit-in-column
    give X-Wing (k=2) and Swordfish (k=3). The rule sees none of that.
    """

    def apply(model: Model) -> bool:
        return _CoverSearch(model, k).run()

    apply.__doc__ = (rule_cover.__doc__ or "").replace("`k`", f"`{k}`")
    return apply


class _CoverSearch:
    """One pass of `rule_cover(k)`: grow inner groups with total demand `k`.

    Only connected groups of As are grown: a disconnected group splits into
    smaller ones that a lower k already handles.
    """

    def __init__(self, model: Model, k: int) -> None:
        self.model = model
        self.k = k
        self.live = {
            c.index: frozenset(model.live(c.index))
            for c in model.constraints
            if not model.satisfied(c.index)
        }
        self.required = {ci: _minimum_additional(model, ci) for ci in self.live}
        self.anchors = {ci for ci, lits in self.live.items() if lits and self.required[ci] > 0}
        self.seen: set[frozenset[ConstraintId]] = set()

    def run(self) -> bool:
        return any(self._grow(frozenset([a]), self.live[a], a) for a in sorted(self.anchors))

    def _grow(
        self, group: frozenset[ConstraintId], union: frozenset[LiteralId], first: ConstraintId
    ) -> bool:
        if group in self.seen:
            return False
        self.seen.add(group)
        demand = sum(self.required[ci] for ci in group)
        if demand > self.k:
            return False
        if next(self._covers(union, (), group), None) is None:
            return False
        if demand < self.k:
            return any(
                self._grow(group | {ci}, union | self.live[ci], first)
                for ci in self._neighbours(group, union, first)
                if demand + self.required[ci] <= self.k
            )
        return any(cover(self.model, sorted(group), bs) for bs in self._covers(union, (), group))

    def _covers(
        self,
        need: frozenset[LiteralId],
        used: tuple[ConstraintId, ...],
        group: frozenset[ConstraintId],
    ) -> Iterator[tuple[ConstraintId, ...]]:
        """Every way to pick at most k constraints outside `group` containing `need`."""
        if not need:
            yield used
            return
        if len(used) == self.k:
            return
        for b in self.model.constraints_of(min(need)):
            if b not in group and b not in used and b in self.live:
                yield from self._covers(need - self.live[b], (*used, b), group)

    def _neighbours(
        self, group: frozenset[ConstraintId], union: frozenset[LiteralId], first: ConstraintId
    ) -> list[ConstraintId]:
        """Anchors that share a constraint with `union` and are disjoint from it.

        Only anchors after `first` are offered, so each group is grown from
        its lowest-numbered member and found once.
        """
        near: set[ConstraintId] = set()
        for lit in union:
            for ci in self.model.constraints_of(lit):
                for other in self.live.get(ci, ()):
                    near.update(self.model.constraints_of(other))
        return sorted(
            ci
            for ci in near
            if ci in self.anchors and ci > first and ci not in group and not self.live[ci] & union
        )


_WHAT_IF_INNER = (rule_single, rule_count, rule_relations, rule_subsumption)


def rule_chains(model: Model) -> bool:
    """If one of two options must hold, anything that excludes both is false.

    A strong link joins two options that cannot both be false under a
    constraint's allowed counts; a weak link joins two that cannot both be
    true. The links are checked against actual count support, not inferred
    from an EXACTLY_ONE assumption. For example, an even-count constraint may
    allow both options true and both false, so it creates neither link.
    Assume a start option false and follow strong and weak links in turn;
    each option reached as true makes "the start or this one" certain, so
    every option weakly linked to both is false. Each link is a valid
    implication, so this is sound for any model.

    In Sudoku this is simple colouring, X- and XY-chains, Y- and W-wings
    and 3D Medusa: alternating inference chains. The shortest chain that
    rules anything out is used.
    """
    links = _Links(model)
    best: list[LiteralId] | None = None
    for start in sorted(links.strong):
        chain = links.shortest_from(start, longest=len(best) if best else None)
        if chain is not None and (best is None or len(chain) < len(best)):
            best = chain
    return best is not None and follow_chain(model, best, links)


def follow_chain(model: Model, chain: Sequence[LiteralId], links: "_Links | None" = None) -> bool:
    """Rule out every option weakly linked to both ends of `chain`, if its
    links all still hold; whether anything was ruled out."""
    links = links or _Links(model)
    if len(chain) < 2 or len(chain) % 2:
        return False
    for i, (a, b) in enumerate(itertools.pairwise(chain)):
        if b not in (links.weak if i % 2 else links.strong).get(a, ()):
            return False
    first, last = chain[0], chain[-1]
    targets = sorted((links.weak.get(first, set()) & links.weak.get(last, set())) - {first, last})
    if not targets:
        return False
    pairs = tuple((model.var_of(x), model.value_of(x)) for x in chain)
    why = tuple(links.why[frozenset(link)] for link in itertools.pairwise(chain))
    reason = f"{model.describe(first)} or {model.describe(last)} holds, by a chain of {len(chain)}"
    for lit in targets:
        model.eliminate(lit, "chains", reason, sources=why, chain=pairs)
    return True


class _Links:
    """Pair implications with support-based reasons for `rule_chains`.

    Strong links forbid both options being false; weak links forbid both
    being true. `why` records the constraint or relation establishing each.
    """

    def __init__(self, model: Model) -> None:
        self.model = model
        self.strong: dict[LiteralId, set[LiteralId]] = {}
        self.weak: dict[LiteralId, set[LiteralId]] = {}
        self.why: dict[frozenset[LiteralId], str] = {}
        self._ordered_counts: dict[tuple[int, bool], tuple[int, ...]] = {}
        for c in model.constraints:
            if model.satisfied(c.index):
                continue
            live = model.live(c.index)
            true_count = sum(model.is_true(lit) for lit in c.literals)
            reifier = c.reified_by
            if reifier is not None and not (model.is_true(reifier) or model.is_false(reifier)):
                pairs: Iterable[tuple[LiteralId, LiteralId]] = ((reifier, lit) for lit in live)
            else:
                pairs = itertools.combinations(live, 2)
            for a, b in pairs:
                if not self._supports(c, {a: True, b: True}, live, true_count):
                    self._weak(a, b, c.name)
                if not self._supports(c, {a: False, b: False}, live, true_count):
                    self.strong.setdefault(a, set()).add(b)
                    self.strong.setdefault(b, set()).add(a)
                    self.why.setdefault(frozenset((a, b)), c.name)
        for relation in model.relations:
            if len(relation.variables) != 2:
                continue
            left, right = (self._open(var) for var in relation.variables)
            for a, b in itertools.product(left, right):
                if not relation.holds(model.value_of(a), model.value_of(b)):
                    self._weak(a, b, relation.name)

    def _open(self, var: str) -> list[LiteralId]:
        return [lit for lit in self.model.options(var) if not self.model.is_true(lit)]

    def _weak(self, a: LiteralId, b: LiteralId, why: str) -> None:
        self.weak.setdefault(a, set()).add(b)
        self.weak.setdefault(b, set()).add(a)
        self.why.setdefault(frozenset((a, b)), why)

    def _supports(
        self,
        constraint: Constraint,
        forced: dict[LiteralId, bool],
        live: Sequence[LiteralId],
        true_count: int,
    ) -> bool:
        """Whether a pair assumption leaves an allowed count in its live interval."""
        forced_true = sum(forced.get(lit) is True for lit in live)
        forced_false = sum(forced.get(lit) is False for lit in live)
        minimum = true_count + forced_true
        maximum = true_count + len(live) - forced_false
        if minimum > maximum:
            return False
        reifier = constraint.reified_by
        if reifier is None:
            complement = False
        elif reifier in forced:
            complement = not forced[reifier]
        elif self.model.is_true(reifier):
            complement = False
        elif self.model.is_false(reifier):
            complement = True
        else:
            return True
        key = (constraint.index, complement)
        if key not in self._ordered_counts:
            allowed = constraint.allowed_counts
            if complement:
                allowed = frozenset(range(len(constraint.literals) + 1)) - allowed
            self._ordered_counts[key] = tuple(sorted(allowed))
        counts = self._ordered_counts[key]
        index = bisect_left(counts, minimum)
        return index < len(counts) and counts[index] <= maximum

    def shortest_from(self, start: LiteralId, longest: int | None) -> list[LiteralId] | None:
        """The shortest chain from `start` (assumed false) that rules something
        out, no longer than `longest` options; breadth first."""
        parent: dict[tuple[LiteralId, bool], tuple[LiteralId, bool] | None] = {(start, False): None}
        frontier = [(start, False)]
        length = 1
        while frontier and (longest is None or length < longest):
            length += 1
            reached = []
            for lit, true in frontier:
                for nxt in sorted((self.weak if true else self.strong).get(lit, ())):
                    state = (nxt, not true)
                    if state in parent:
                        continue
                    parent[state] = (lit, true)
                    reached.append(state)
                    if not true and nxt != start:
                        both = self.weak.get(start, set()) & self.weak.get(nxt, set())
                        if both - {start, nxt}:
                            return self._path(parent, state)
            frontier = reached
        return None

    @staticmethod
    def _path(
        parent: dict[tuple[LiteralId, bool], tuple[LiteralId, bool] | None],
        state: tuple[LiteralId, bool],
    ) -> list[LiteralId]:
        path: list[LiteralId] = []
        at: tuple[LiteralId, bool] | None = state
        while at is not None:
            path.append(at[0])
            at = parent[at]
        return path[::-1]


def rule_what_if(model: Model) -> bool:
    """Assume a literal on a copy; if the cheap rules then contradict, it is false.

    Sound because every rule used on the copy is sound: a contradiction
    reached from "x holds" proves x cannot hold. Only cheap rules run on the
    copy, never what-if itself, so the search stays one level deep. Variables
    with the fewest options are tried first, as a person would; of the first
    variable's refutable values, the one with the shortest trail to its
    contradiction is ruled out, the simplest case split to explain.
    """
    undecided = [var for var in model.variables if model.chosen(var) is None]
    for var in sorted(undecided, key=lambda v: len(model.options(v))):
        best: tuple[int, LiteralId, tuple[str, tuple[Step, ...], str | None]] | None = None
        for lit in model.options(var):
            if model.is_true(lit):
                continue
            refutation = _refute(model, lit)
            if refutation is not None and (best is None or len(refutation[1]) < best[0]):
                best = (len(refutation[1]), lit, refutation)
        if best is not None:
            _, lit, (reason, trail, broken) = best
            sources = () if broken is None else (broken,)
            model.eliminate(lit, "what_if", reason, sources=sources, trail=trail)
            return True
    return False


def refute(model: Model, lit: LiteralId) -> bool:
    """Rule `lit` out if assuming it leads the cheap rules to a contradiction."""
    if model.is_true(lit) or model.is_false(lit):
        return False
    refutation = _refute(model, lit)
    if refutation is None:
        return False
    reason, trail, broken = refutation
    sources = () if broken is None else (broken,)
    model.eliminate(lit, "what_if", reason, sources=sources, trail=trail)
    return True


def _refute(model: Model, lit: LiteralId) -> tuple[str, tuple[Step, ...], str | None] | None:
    """Why assuming `lit` leads to a contradiction, or None if it does not:
    the reason, the steps taken on the way, and what broke."""
    twin = model.clone()
    try:
        twin.assign(lit, "what_if", "assumed")
        twin.check()
        while any(rule(twin) for rule in _WHAT_IF_INNER):
            twin.check()
    except Contradiction as exc:
        reason = f"assuming it leads, in {len(twin.log)} steps, to: {exc}"
        return reason, tuple(twin.log), exc.source
    return None


DEFAULT_RULES: tuple[Rule, ...] = (
    Rule("single", rule_single),
    Rule("count", rule_count),
    Rule("relations", rule_relations),
    Rule("subsumption", rule_subsumption),
    Rule("cover2", rule_cover(2)),
    Rule("cover3", rule_cover(3)),
    Rule("chains", rule_chains),
    Rule("what_if", rule_what_if),
)


# --- solver ---------------------------------------------------------------

type StepCallback = Callable[[str, Sequence[Step]], None]


@dataclass(frozen=True)
class Result:
    """Outcome of `Solver.solve`.

    `assignment` is the full solution when `solved`, otherwise whatever had
    been decided when the rules ran out or hit `contradiction`.
    """

    solved: bool
    assignment: dict[str, Any]
    iterations: int
    contradiction: str | None = None


class Solver:
    """Applies rules cheapest-first, restarting after each success, until
    nothing more can be deduced."""

    def __init__(self, model: Model, rules: Iterable[Rule] = DEFAULT_RULES) -> None:
        self.model = model
        self.rules = tuple(rules)

    def solve(self, on_step: StepCallback | None = None) -> Result:
        """Run to a fixed point.

        `on_step` receives the rule name and the steps it produced, so callers
        can render progress without this module knowing how to draw.
        """
        iterations = 0
        try:
            self.model.check()
            while True:
                iterations += 1
                fired = self._apply_cheapest_progress()
                if fired is None:
                    break
                if on_step is not None:
                    on_step(*fired)
        except Contradiction as exc:
            return Result(False, self.model.assignment(), iterations, str(exc))

        solution = self.model.solution()
        if solution is None:
            return Result(False, self.model.assignment(), iterations)
        return Result(True, solution, iterations)

    def _apply_cheapest_progress(self) -> tuple[str, Sequence[Step]] | None:
        """Apply the first rule that changes something; its name and new steps."""
        for rule in self.rules:
            mark = len(self.model.log)
            if rule.apply(self.model):
                self.model.check()
                return rule.name, self.model.log[mark:]
        return None
