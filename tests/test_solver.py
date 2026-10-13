"""Tests for the exact-cover engine and both puzzle compilers.

The Murdoku cases check against the published solution and candidate lists in
the documents in proprietary puzzles/, so a wrong board transcription fails here rather than quietly
solving some other puzzle.
"""

import re
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from csp import bruteforce, calcudoku, cli, futoshiki, murdoku, report, sudoku
from csp.core import (
    DEFAULT_RULES,
    Contradiction,
    Kind,
    Model,
    Rule,
    Solver,
    follow_chain,
    rule_chains,
    rule_count,
    rule_cover,
    rule_relations,
    rule_single,
    rule_subsumption,
    rule_what_if,
)
from csp.proof import Move, replay
from csp.puzzlefile import load_board, parse_square

EXAMPLES = Path(__file__).parent.parent / "examples"


# --- engine ---------------------------------------------------------------


def test_assign_rules_out_siblings():
    m = Model()
    a, b, c = (m.literal("x", v) for v in (1, 2, 3))
    m.constrain("x picks one", Kind.EXACTLY_ONE, [a, b, c], defines="x")
    m.assign(a, "test", "chosen")
    assert m.is_true(a) and m.is_false(b) and m.is_false(c)
    assert m.chosen("x") == 1


def test_single_fires_on_last_option():
    m = Model()
    a, b = m.literal("x", 1), m.literal("x", 2)
    m.constrain("x picks one", Kind.EXACTLY_ONE, [a, b], defines="x")
    m.eliminate(a, "test", "ruled out")
    assert rule_single(m) is True
    assert m.chosen("x") == 2


def test_at_most_one_does_not_force():
    """The distinction the old engine got wrong: AT_MOST_ONE never forces."""
    m = Model()
    a, b = m.literal("x", 1), m.literal("y", 1)
    m.constrain("square shared", Kind.AT_MOST_ONE, [a, b])
    m.eliminate(a, "test", "ruled out")
    assert rule_single(m) is False
    assert not m.is_true(b)


def test_exhausted_exactly_one_is_a_contradiction():
    m = Model()
    a = m.literal("x", 1)
    m.constrain("x picks one", Kind.EXACTLY_ONE, [a], defines="x")
    m.eliminate(a, "test", "ruled out")
    with pytest.raises(Contradiction):
        m.check()


def test_subsumption_prunes_the_wider_constraint():
    m = Model()
    inner = [m.literal("p", 1), m.literal("p", 2)]
    extra = [m.literal("q", 3), m.literal("q", 4)]
    m.constrain("narrow", Kind.EXACTLY_ONE, inner)
    m.constrain("wide", Kind.EXACTLY_ONE, inner + extra)
    assert rule_subsumption(m) is True
    assert all(m.is_false(lit) for lit in extra)
    assert not any(m.is_false(lit) for lit in inner)


def _variable(m: Model, var: str, values) -> list[int]:
    """Declare `var` with the given domain; return its literals."""
    lits = [m.literal(var, v) for v in values]
    m.constrain(f"{var} picks one", Kind.EXACTLY_ONE, lits, defines=var)
    return lits


def _brute_force_count_solutions(model: Model) -> list[dict[str, Any]]:
    """Enumerate domain assignments and evaluate allowed counts without solver rules."""
    variables = model.variables
    domains = [
        [model.value_of(lit) for lit in model.constraints[model.domain_of(var)].literals]
        for var in variables
    ]
    solutions = []
    for values in product(*domains):
        assignment = dict(zip(variables, values, strict=True))
        if any(
            (model.is_true(lit) and assignment[model.var_of(lit)] != model.value_of(lit))
            or (model.is_false(lit) and assignment[model.var_of(lit)] == model.value_of(lit))
            for lit in range(model.num_literals)
        ):
            continue
        valid = True
        for constraint in model.constraints:
            count = sum(
                assignment[model.var_of(lit)] == model.value_of(lit) for lit in constraint.literals
            )
            allowed = count in constraint.allowed_counts
            if constraint.reified_by is not None:
                output = assignment[model.var_of(constraint.reified_by)] == model.value_of(
                    constraint.reified_by
                )
                if output != allowed:
                    valid = False
                    break
            elif not allowed:
                valid = False
                break
        if valid:
            solutions.append(assignment)
    return solutions


def _assert_logged_steps_preserve_solutions(model: Model, solutions: list[dict[str, Any]]) -> None:
    for step in model.log:
        for solution in solutions:
            if step.var not in solution:
                continue
            if step.asserted:
                assert solution[step.var] == step.value, step
            else:
                assert solution[step.var] != step.value, step


def test_count_constraint_propagates_an_exact_count_boundary():
    m = Model()
    a, b, c = (_variable(m, var, ("yes", "no"))[0] for var in "abc")
    m.constrain("two of three", Kind.COUNT, [a, b, c], allowed_counts={2})

    m.assign(a, "test", "chosen")
    solutions = _brute_force_count_solutions(m)
    assert rule_count(m) is False
    assert not m.is_false(b) and not m.is_false(c)
    m.assign(b, "test", "chosen")
    solutions = _brute_force_count_solutions(m)
    assert m.is_false(c)
    _assert_logged_steps_preserve_solutions(m, solutions)
    m.check()


def test_count_constraint_handles_even_parity():
    m = Model()
    a, b = (_variable(m, var, ("yes", "no"))[0] for var in "ab")
    m.constrain("an even number", Kind.COUNT, [a, b], allowed_counts={0, 2})
    m.assign(a, "test", "chosen")
    solutions = _brute_force_count_solutions(m)

    assert rule_count(m) is True
    assert m.is_true(b)
    _assert_logged_steps_preserve_solutions(m, solutions)
    m.check()


def test_single_propagates_a_count_with_one_live_literal():
    model = Model()
    first_false, first = (model.literal("first", value) for value in (False, True))
    last_false, last = (model.literal("last", value) for value in (False, True))
    model.constrain("exactly one", Kind.COUNT, [first, last], allowed_counts={1})
    model.constrain("first domain", Kind.EXACTLY_ONE, [first_false, first], defines="first")
    model.constrain("last domain", Kind.EXACTLY_ONE, [last_false, last], defines="last")
    model.eliminate(first, "test", "not selected")
    solutions = _brute_force_count_solutions(model)

    assert rule_single(model) is True
    assert model.is_true(last)
    _assert_logged_steps_preserve_solutions(model, solutions)
    model.check()


def test_cover2_uses_count_demand_and_outer_capacity():
    m = Model()
    a, b, c, extra_a, extra_b = (_variable(m, var, (False, True))[1] for var in "abcde")
    inner = m.constrain("two of three", Kind.COUNT, [a, b, c], allowed_counts={2})
    outer_a = m.constrain("first capacity", Kind.AT_MOST_ONE, [a, b, extra_a])
    outer_b = m.constrain("second capacity", Kind.AT_MOST_ONE, [b, c, extra_b])
    solutions = _brute_force_count_solutions(m)

    assert len(solutions) == 1
    changed = False
    while rule_cover(2)(m):
        changed = True
        m.check()
    assert changed
    assert m.is_false(extra_a) and m.is_false(extra_b)
    assert m.constraints[inner].kind is Kind.COUNT
    assert m.constraints[outer_a].kind is m.constraints[outer_b].kind is Kind.AT_MOST_ONE
    _assert_logged_steps_preserve_solutions(m, solutions)
    m.check()


def test_count_constraints_create_only_supported_chain_links():
    model = Model()
    a, b, candidate = (_variable(model, var, (False, True))[1] for var in "abc")
    model.constrain("one of a or b", Kind.COUNT, [a, b], allowed_counts={1})
    model.constrain("a excludes candidate", Kind.AT_MOST_ONE, [a, candidate])
    model.constrain("b excludes candidate", Kind.AT_MOST_ONE, [b, candidate])
    solutions = _brute_force_count_solutions(model)

    assert rule_chains(model) is True
    assert model.is_false(candidate)
    _assert_logged_steps_preserve_solutions(model, solutions)
    model.check()

    parity = Model()
    a, b, candidate = (_variable(parity, var, (False, True))[1] for var in "abc")
    parity.constrain("an even number of a and b", Kind.COUNT, [a, b], allowed_counts={0, 2})
    parity.constrain("a excludes candidate", Kind.AT_MOST_ONE, [a, candidate])
    parity.constrain("b excludes candidate", Kind.AT_MOST_ONE, [b, candidate])
    parity_solutions = _brute_force_count_solutions(parity)

    assert rule_chains(parity) is False
    assert not parity.is_false(candidate)
    _assert_logged_steps_preserve_solutions(parity, parity_solutions)
    parity.check()


def test_count_move_replays_its_propagation():
    model = Model()
    literal = model.literal("occupied", True)
    model.constrain("room empty", Kind.COUNT, [literal], allowed_counts={0})
    start = model.clone()

    assert rule_count(model) is True
    move = Move.of("count", model.log)
    assert move is not None
    replayed = replay(start, [move])

    assert replayed.is_false(literal)


def test_reified_zero_count_tracks_empty_and_nonempty():
    empty_model = Model()
    first, second = (_variable(empty_model, var, ("yes", "no"))[0] for var in "ab")
    is_empty, _ = _variable(empty_model, "room", ("empty", "occupied"))
    empty_model.constrain(
        "room has no occupants",
        Kind.COUNT,
        [first, second],
        allowed_counts={0},
        reified_by=is_empty,
    )
    empty_model.eliminate(first, "test", "not present")
    empty_model.eliminate(second, "test", "not present")
    empty_solutions = _brute_force_count_solutions(empty_model)

    assert rule_count(empty_model) is True
    assert empty_model.is_true(is_empty)
    _assert_logged_steps_preserve_solutions(empty_model, empty_solutions)

    occupied_model = Model()
    first, second = (_variable(occupied_model, var, ("yes", "no"))[0] for var in "ab")
    is_empty, _ = _variable(occupied_model, "room", ("empty", "occupied"))
    occupied_model.constrain(
        "room has no occupants",
        Kind.COUNT,
        [first, second],
        allowed_counts={0},
        reified_by=is_empty,
    )
    occupied_model.assign(first, "test", "present")
    occupied_solutions = _brute_force_count_solutions(occupied_model)

    assert rule_count(occupied_model) is True
    assert occupied_model.is_false(is_empty)
    _assert_logged_steps_preserve_solutions(occupied_model, occupied_solutions)


def _naked_pair_model():
    """Cells x, y take {1, 2}; z takes 1-4, w {3, 4}; each digit used once."""
    m = Model()
    allowed = {"x": (1, 2), "y": (1, 2), "z": (1, 2, 3, 4), "w": (3, 4)}
    for var, values in allowed.items():
        _variable(m, var, values)
    for d in (1, 2, 3, 4):
        holders = [m.literal(var, d) for var, values in allowed.items() if d in values]
        m.constrain(f"{d} used once", Kind.EXACTLY_ONE, holders)
    return m, {(var, d): m.literal(var, d) for var, values in allowed.items() for d in values}


def test_cover2_is_a_naked_pair():
    m, lit = _naked_pair_model()
    assert rule_subsumption(m) is False
    assert rule_cover(2)(m) is True
    assert m.is_false(lit["z", 1]) and m.is_false(lit["z", 2])
    assert not m.is_false(lit["z", 3]) and not m.is_false(lit["z", 4])


def test_cover_needs_disjoint_anchors():
    """A1 and A2 share their literals, so they place one truth, not two."""
    m = Model()
    a, b, c = m.literal("p", 1), m.literal("p", 2), m.literal("q", 1)
    m.constrain("A1", Kind.EXACTLY_ONE, [a, b])
    m.constrain("A2", Kind.EXACTLY_ONE, [a, b])
    m.constrain("B", Kind.AT_MOST_ONE, [a, c])
    m.constrain("C", Kind.AT_MOST_ONE, [b])
    assert rule_cover(2)(m) is False
    assert not m.is_false(c)


def test_three_way_relation_needs_a_supporting_combination():
    m = Model()
    for var in "abc":
        _variable(m, var, (1, 2, 3))
    m.relate("a is the sum", "abc", lambda a, b, c: a == b + c)
    while rule_relations(m):
        pass
    assert [m.value_of(lit) for lit in m.options("a")] == [2, 3]
    assert [m.value_of(lit) for lit in m.options("b")] == [1, 2]


def test_clone_leaves_the_original_untouched():
    m = Model()
    a, b = _variable(m, "x", (1, 2))
    twin = m.clone()
    twin.assign(a, "test", "chosen")
    assert twin.is_false(b) and not m.is_false(b) and m.log == []


def test_hidden_domain_participates_in_constraints_but_not_solution_assignments():
    model = Model()
    person = _variable(model, "Ada", ("r1c1", "r1c2"))
    role_yes = model.literal("Ada has role bandit", True)
    role_no = model.literal("Ada has role bandit", False)
    model.constrain(
        "Ada bandit state",
        Kind.EXACTLY_ONE,
        [role_yes, role_no],
        defines="Ada has role bandit",
        hidden=True,
    )
    model.constrain("bandit holds once", Kind.COUNT, [role_yes], allowed_counts={1})

    assert model.variables == ["Ada"]
    assert model.all_variables == ["Ada", "Ada has role bandit"]
    assert model.chosen("Ada has role bandit") is None
    model.assign(person[0], "test", "chosen")
    assert rule_count(model)

    assert model.solution() == {"Ada": "r1c1"}
    assert model.is_true(role_yes)


def test_roles_support_overlap_absence_some_unknown_and_eligibility():
    text = """Size: 5
Regions:
a: room
Grid:
a a a a a
a a a a a
a a a a a
a a a a a
a a a a a
People:
A
B
C
D
E
Roles:
captain: 1
seer: any
RoleEligibility:
captain: A
Rules:
has_role A seer
not_role B seer
some_role C
at_most_one_role C
roleless D
role_subset captain seer
"""
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    Solver(model).solve()
    brute_solutions = bruteforce.solutions(text, "murdoku", limit=10)
    _assert_logged_steps_preserve_solutions(model, brute_solutions)
    role = board.role_variable

    assert model.is_true(model.literal(role("A", "captain"), True))
    assert model.is_true(model.literal(role("A", "seer"), True))
    assert model.is_true(model.literal(role("B", "seer"), False))
    assert model.is_true(model.literal(role("C", "seer"), True))
    assert model.is_true(model.literal(role("D", "captain"), False))
    assert model.is_true(model.literal(role("D", "seer"), False))
    assert not model.is_true(model.literal(role("E", "seer"), True))
    assert not model.is_true(model.literal(role("E", "seer"), False))
    assert role("E", "seer") not in model.variables
    model_report = report.describe(model)
    assert "Role membership (10):" in model_report
    assert "A has role captain: present" in model_report
    assert "E has role seer: unknown" in model_report
    rendered = _plain(murdoku.render(board, model, "roles"))
    assert "role membership (+ present, - absent, ? unknown):" in rendered
    assert "seer: A+ B- C+ D- E?" in rendered


def test_cli_narrates_role_membership_without_boolean_literals(capsys):
    model = Model()
    has_role = model.literal("Ada has role bandit", True)
    lacks_role = model.literal("Ada has role bandit", False)
    model.constrain("Ada role", Kind.EXACTLY_ONE, [has_role, lacks_role])
    model.assign(has_role, "single", "known role")

    cli.narrate("single", model.log[:1])

    output = capsys.readouterr().out
    assert "Ada has role bandit" in output
    assert "True" not in output


def test_role_compiler_preserves_one_shot_clue_iterables():
    board = murdoku.Board(
        3,
        [["a"] * 3 for _ in range(3)],
        {"a": "room"},
        [],
        ["A", "B"],
        roles=[murdoku.RoleSpec("captain", frozenset({1}))],
    )
    model = murdoku.compile_puzzle(
        board, iter([("in_corner", ["A"]), ("has_role", ["A", "captain"])])
    )

    assert murdoku.Square(1, 1) not in {model.value_of(lit) for lit in model.options("A")}
    assert model.is_true(model.literal(board.role_variable("A", "captain"), True))


def test_role_below_and_sole_role_companion_match_brute_force():
    below_text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Roles:
scout: 1
Rules:
has_role A scout
Clues:
role_below B scout 1
"""
    below_solutions = bruteforce.solutions(below_text, "murdoku", limit=10)
    assert below_solutions
    assert all(solution["B"].row == solution["A"].row + 1 for solution in below_solutions)
    board, clues = load_board(below_text)
    model = murdoku.compile_puzzle(board, clues)
    Solver(model).solve()
    _assert_logged_steps_preserve_solutions(model, below_solutions)

    companion_text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Roles:
murderer: 1
Clues:
sole_role_companion B murderer
"""
    companion_solutions = bruteforce.solutions(companion_text, "murdoku", limit=10)

    assert companion_solutions
    assert all(solution["A has role murderer"] for solution in companion_solutions)
    board, clues = load_board(companion_text)
    model = murdoku.compile_puzzle(board, clues)
    Solver(model).solve()
    _assert_logged_steps_preserve_solutions(model, companion_solutions)


def test_role_occupant_effect_reuses_conditional_count_hook():
    permitted = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Roles:
bandit: 1
Rules:
role_occupant bandit not_alone
"""
    allowed_solutions = bruteforce.solutions(permitted, "murdoku", limit=10)
    assert allowed_solutions
    board, clues = load_board(permitted)
    model = murdoku.compile_puzzle(board, clues)
    Solver(model).solve()
    _assert_logged_steps_preserve_solutions(model, allowed_solutions)

    impossible = permitted.replace("not_alone", "alone")
    assert bruteforce.solutions(impossible, "murdoku", limit=2) == []


def test_role_bindings_to_marks_and_object_kinds_match_brute_force():
    text = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
Objects:
chair: standable r1c1
wall: blocking r2c2
People:
A
B
Roles:
captain: 1
scout: 1
Marks:
seat: r1c1
Rules:
has_role A captain
has_role B scout
role_on A captain seat
role_next_to B scout blocking
"""
    solutions = bruteforce.solutions(text, "murdoku", limit=10)
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    Solver(model).solve()

    assert solutions
    for solution in solutions:
        assert solution[board.role_variable("A", "captain")]
        assert solution[board.role_variable("B", "scout")]
        assert solution["A"] == murdoku.Square(0, 0)
        assert murdoku.steps_between(solution["B"], murdoku.Square(1, 1)) == 1
    for step in model.log:
        for solution in solutions:
            if step.var not in solution:
                continue
            if step.asserted:
                assert solution[step.var] == step.value, step
            else:
                assert solution[step.var] != step.value, step


def test_role_area_minimum_and_distinct_regions_use_count_constraints():
    minimum_text = """Size: 2
Regions:
a: room
b: garden
Grid:
a b
a b
People:
A
B
AreaTags:
outside: room garden
Roles:
scout: any
Rules:
min_role_in_tagged scout outside 1
"""
    solutions = bruteforce.solutions(minimum_text, "murdoku", limit=10)
    assert solutions
    board, clues = load_board(minimum_text)
    model = murdoku.compile_puzzle(board, clues)
    for solution in solutions:
        assert all(solution[f"{person} has role scout"] for person in ("A", "B"))
        candidate = model.clone()
        for person in board.people:
            candidate.assign(candidate.literal(person, solution[person]), "test", "chosen")
        Solver(candidate).solve()
        assert all(
            candidate.chosen(board.role_variable(person, "scout")) is True
            for person in board.people
        )

    distinct_text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Roles:
scout: 2 different_regions
"""
    assert bruteforce.solutions(distinct_text, "murdoku", limit=2) == []


def test_role_area_policies_match_brute_force_and_model():
    text = """Size: 3
Regions:
a: room
b: hall
c: garden
Grid:
a b c
a b c
a b c
People:
Ada
Ben
AreaTags:
inside: room
Roles:
guide: any
Rules:
has_role Ada guide
has_role Ben guide
role_in_tagged Ada guide inside
role_not_in_tagged Ben guide inside
"""
    solutions = bruteforce.solutions(text, "murdoku", limit=50)
    assert solutions
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)

    for solution in solutions:
        assert board.region_of(solution["Ada"]) == "a"
        assert board.region_of(solution["Ben"]) != "a"
        candidate = model.clone()
        for variable, value in solution.items():
            candidate.assign(candidate.literal(variable, value), "test", "brute-force solution")
        candidate.check()


def test_what_if_eliminates_a_literal_that_leads_to_contradiction():
    """x=1 forces both y=1 and z=1, which may not hold together."""
    m = Model()
    for var in "xyz":
        _variable(m, var, (1, 2))
    m.relate("y follows x", "xy", lambda x, y: x != 1 or y == 1)
    m.relate("y avoids z", "yz", lambda y, z: y != 1 or z != 1)
    m.relate("z follows x", "xz", lambda x, z: x != 1 or z == 1)
    assert rule_relations(m) is False
    assert rule_what_if(m) is True
    assert m.is_false(m.literal("x", 1))


def test_what_if_rules_out_the_value_with_the_shortest_refutation():
    """x=1 comes first but fails only after y and z follow it; x=2 fails at
    once, so x=2 is the one ruled out."""
    m = Model()
    for var in "xyz":
        _variable(m, var, (1, 2))
    m.relate("x is never 2", "xy", lambda x, y: x != 2)
    m.relate("y follows x", "xy", lambda x, y: x != 1 or y == 1)
    m.relate("z follows y", "yz", lambda y, z: y != 1 or z == 1)
    m.relate("z avoids x", "xz", lambda x, z: x != 1 or z != 1)
    assert rule_what_if(m) is True
    (step,) = m.log
    assert (step.var, step.value) == ("x", 2)


# --- sudoku ---------------------------------------------------------------


def test_sudoku_model_shape():
    model, _ = sudoku.compile_puzzle((EXAMPLES / "sudoku_easy.txt").read_text())
    assert model.num_literals == 81 * 9
    assert len(model.constraints) == 81 + 3 * 81
    assert model.chosen("r1c1") == 5
    assert model.chosen("r1c3") is None


def test_sudoku_solves_to_a_valid_grid():
    model, puzzle = sudoku.compile_puzzle((EXAMPLES / "sudoku_easy.txt").read_text())
    grid = puzzle.grid
    result = Solver(model).solve()
    assert result.solved

    rows = [[result.assignment[sudoku.cell_name(r, c)] for c in range(9)] for r in range(9)]
    full = list(range(1, 10))
    assert all(sorted(row) == full for row in rows)
    assert all(sorted(rows[r][c] for r in range(9)) == full for c in range(9))
    assert all(
        sorted(rows[br * 3 + r][bc * 3 + c] for r in range(3) for c in range(3)) == full
        for br in range(3)
        for bc in range(3)
    )
    # every given survived
    assert all(grid[r][c] in (0, rows[r][c]) for r in range(9) for c in range(9))


def _before(rule: str) -> tuple[Rule, ...]:
    names = [r.name for r in DEFAULT_RULES]
    return DEFAULT_RULES[: names.index(rule)]


FISH = r"(\d) once in (row|col) \d+"  # a digit in one line; \1 digit, \2 row or col
LINE = r"once in \2 \d+"  # the same digit in another line of the same kind
HOUSE = r"\d once in [a-z]+ [\d,]+"  # any digit in any row, column or box

# file, the rule it needs, and the deduction pattern it must show
GRADED = [
    ("sudoku_pointing.txt", "subsumption", r"once in box"),
    ("sudoku_naked_pair.txt", "cover2", r"^r\dc\d holds one digit, r\dc\d holds one digit use up"),
    ("sudoku_hidden_pair.txt", "cover2", rf"^{HOUSE}, {HOUSE} use up r\dc\d holds"),
    ("sudoku_xwing.txt", "cover2", rf"^{FISH}, \1 {LINE} use up \1 once in (?!\2)"),
    ("sudoku_swordfish.txt", "cover3", rf"^{FISH}, \1 {LINE}, \1 {LINE} use up \1 once in (?!\2)"),
    ("sudoku_chains.txt", "chains", r"holds, by a chain of"),
]


@pytest.mark.parametrize("name, rule, pattern", GRADED)
def test_graded_sudoku_shows_its_pattern(name, rule, pattern):
    model, _ = sudoku.compile_puzzle((EXAMPLES / name).read_text())
    assert Solver(model).solve().solved
    assert any(s.rule == rule and re.search(pattern, s.reason) for s in model.log)


@pytest.mark.parametrize("name, rule, pattern", GRADED)
def test_graded_sudoku_stalls_without_its_rule(name, rule, pattern):
    model, _ = sudoku.compile_puzzle((EXAMPLES / name).read_text())
    result = Solver(model, _before(rule)).solve()
    assert not result.solved and result.contradiction is None


def test_sudoku_rejects_a_malformed_grid():
    with pytest.raises(ValueError):
        sudoku.parse("1 2 3\n4 5 6")
    with pytest.raises(ValueError, match="4 or 9"):
        sudoku.parse("\n".join([". " * 5] * 5))
    with pytest.raises(ValueError, match="go up to 4"):
        sudoku.parse("5 . . .\n. . . .\n. . . .\n. . . .")


def test_mini_sudoku_has_two_by_two_boxes():
    model, puzzle = sudoku.compile_puzzle((EXAMPLES / "sudoku_4x4.txt").read_text())
    grid = puzzle.grid
    boxes = [c for c in model.constraints if c.family == "each digit once per box"]
    assert len(grid) == 4 and len(boxes) == 4 * 4
    assert all(len(c.literals) == 4 for c in boxes)
    assert Solver(model).solve().solved


def test_jigsaw_boxes_and_x_diagonals_are_houses():
    jigsaw = sudoku.parse((EXAMPLES / "sudoku_jigsaw.txt").read_text())
    assert jigsaw.size == 6 and jigsaw.jigsaw and not jigsaw.extra_houses()
    boxes = [cells for family, _, cells in jigsaw.houses() if family == "box"]
    assert len(boxes) == 6 and all(len(cells) == 6 for cells in boxes)
    x = sudoku.parse((EXAMPLES / "sudoku_x.txt").read_text())
    assert not x.jigsaw and x.extra_houses() == {
        "x": [(i, i) for i in range(9)],
        "y": [(i, 8 - i) for i in range(9)],
    }


def test_x_sudoku_is_unique_only_because_of_its_diagonals():
    text = (EXAMPLES / "sudoku_x.txt").read_text()
    assert len(bruteforce.solutions(text)) == 1
    plain = text[: text.index("# The two diagonals")]
    assert len(bruteforce.solutions(plain)) == 2
    model, _ = sudoku.compile_puzzle(text)
    Solver(model).solve()
    assert any("extra house" in s.reason for s in model.log)


def test_nrc_sudoku_extra_boxes_are_houses_it_needs():
    text = (EXAMPLES / "sudoku_nrc.txt").read_text()
    puzzle = sudoku.parse(text)
    extra = puzzle.extra_houses()
    assert sorted(extra) == ["a", "b", "c", "d"]
    assert extra["a"] == [(r, c) for r in range(1, 4) for c in range(1, 4)]
    assert len(bruteforce.solutions(text)) == 1
    plain = text[: text.index("Extra:")]
    assert len(bruteforce.solutions(plain)) == 2


def test_extra_houses_must_have_n_cells():
    text = "Givens:\n" + ". . . .\n" * 4 + "Extra:\na a . .\na . . .\n. . . .\n. . . .\n"
    with pytest.raises(ValueError, match="do not have 4 cells"):
        sudoku.parse(text)
    shared = "Extra:\nab a . .\na b . .\na b . .\n. b . .\n"
    assert len(sudoku.parse(text[: text.index("Extra")] + shared).extra_houses()["b"]) == 4


@pytest.mark.parametrize(
    "boxes, problem",
    [
        ("a a b b\na a b b\nc c d d\nc c d", "not 4x4"),
        ("a a a b\na a b b\nc c d d\nc c d d", "4 boxes of 4 cells"),
    ],
)
def test_jigsaw_boxes_must_tile_the_grid(boxes, problem):
    text = "Givens:\n" + ". . . .\n" * 4 + "Boxes:\n" + boxes + "\n"
    with pytest.raises(ValueError, match=problem):
        sudoku.parse(text)


# --- murdoku --------------------------------------------------------------


@pytest.fixture
def prrrdoku1():
    board, clues = load_board((EXAMPLES / "prrrdoku1.txt").read_text())
    return board, murdoku.compile_puzzle(board, clues)


def test_people_are_the_variables(prrrdoku1):
    board, model = prrrdoku1
    assert sorted(model.variables) == sorted(board.people)
    # 7 people x 43 free squares
    assert len(board.free) == 49 - 6
    assert model.num_literals == 7 * 43


def test_prrrdoku1_candidate_lists_after_late_reveal_board_change(prrrdoku1):
    """The region tweak removes r4c2 from Tjitske's next-to candidates."""
    board, model = prrrdoku1
    open_sq = {p: [str(s) for s in sqs] for p, sqs in murdoku.open_squares(board, model).items()}
    assert open_sq["Tim"] == ["r1c1", "r2c2", "r3c1"]
    assert open_sq["Tjitske"] == ["r5c1", "r6c2"]
    assert open_sq["Jos"] == ["r1c4", "r1c5", "r2c4", "r3c4", "r3c5", "r3c6"]
    assert open_sq["Pip"] == ["r1c6", "r1c7", "r2c6", "r2c7", "r4c7", "r5c7"]


def test_prrrdoku1_reaches_the_published_solution(prrrdoku1):
    _, model = prrrdoku1
    result = Solver(model).solve()
    assert result.solved
    assert {p: str(sq) for p, sq in result.assignment.items()} == {
        "Tim": "r1c1",
        "Jos": "r2c4",
        "Anna": "r3c6",
        "Pip": "r4c7",
        "Otto": "r5c5",
        "Tjitske": "r6c2",
        "Vladimir": "r7c3",
    }


def test_vladimir_shares_his_region_with_exactly_tjitske(prrrdoku1):
    """The puzzle's actual question."""
    board, model = prrrdoku1
    result = Solver(model).solve()
    assert result.solved
    vlad_region = board.region_of(result.assignment["Vladimir"])
    company = [
        p
        for p, sq in result.assignment.items()
        if p != "Vladimir" and board.region_of(sq) == vlad_region
    ]
    assert company == ["Tjitske"]
    assert board.region_names[vlad_region] == "kampeerplek"


def test_one_person_per_row_and_column(prrrdoku1):
    board, model = prrrdoku1
    result = Solver(model).solve()
    squares = list(result.assignment.values())
    assert sorted(s.row for s in squares) == list(range(board.size))
    assert sorted(s.col for s in squares) == list(range(board.size))


def test_nobody_stands_on_an_object(prrrdoku1):
    board, model = prrrdoku1
    result = Solver(model).solve()
    assert not set(result.assignment.values()) & board.blocked


def _one_region_board(
    size: int, people: list[str], objects: list[murdoku.BoardObject] | None = None
) -> murdoku.Board:
    """A size x size board that is all region 'a', called 'here'."""
    grid = [["a"] * size for _ in range(size)]
    return murdoku.Board(size, grid, {"a": "here"}, objects or [], people)


def test_objects_declare_kind_and_standable_objects_are_on_targets():
    text = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
Objects:
wall: blocking r1c1
rug: standable r2c1 r2c2
chair: standable r3c1
chair: standable r3c3
People:
A
B
"""
    board, _ = load_board(text)
    rug_squares = {murdoku.Square(1, 0), murdoku.Square(1, 1)}

    assert board.blocked == {murdoku.Square(0, 0)}
    assert board.squares_of(["chair"]) == {murdoku.Square(2, 0), murdoku.Square(2, 2)}
    model = murdoku.compile_puzzle(board, [("on", ["A", "rug"])])
    assert {model.value_of(lit) for lit in model.options("A")} == rug_squares

    with pytest.raises(ValueError, match="standable"):
        murdoku.compile_puzzle(board, [("on", ["A", "wall"])])


def test_object_kind_is_required_and_each_footprint_is_connected():
    base = """Size: 3
Regions:
a: room
Grid:
a a a
a a a
a a a
Objects:
rug: standable r1c1 r1c2
People:
A
"""
    with pytest.raises(ValueError, match="kind"):
        load_board(base.replace("rug: standable", "rug:"))
    with pytest.raises(ValueError, match="connected"):
        load_board(base.replace("r1c1 r1c2", "r1c1 r3c3"))
    with pytest.raises(ValueError, match="Furniture: is no longer supported"):
        load_board(base.replace("Objects:", "Furniture:"))


def test_object_footprints_cannot_overlap_or_change_kind():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
Objects:
wall: blocking r1c1
mat: standable r1c1
People:
A
B
"""
    with pytest.raises(ValueError, match="overlap"):
        load_board(text)

    conflicting = text.replace("mat: standable r1c1", "wall: standable r2c2")
    with pytest.raises(ValueError, match="conflicting kinds"):
        load_board(conflicting)


def test_people_count_cannot_exceed_board_size():
    with pytest.raises(ValueError):
        _one_region_board(3, ["one", "two", "three", "four"])


def test_sparse_board_allows_empty_rows_and_columns():
    board = _one_region_board(4, ["Ada", "Ben", "Vic"])
    model = murdoku.compile_puzzle(board, [])
    line_rules = [rule for rule in murdoku.board_rules(board) if rule.about[0] in {"row", "col"}]
    assert len(model.variables) == 3
    assert len(line_rules) == 8
    assert all(rule.kind is Kind.AT_MOST_ONE for rule in line_rules)


def test_sparse_murdoku_mystery_example_solves_unique_murderer():
    text = (EXAMPLES / "murdoku_sparse_mystery.txt").read_text()
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    result = Solver(model).solve()
    (expected,) = bruteforce.solutions(text, "murdoku", limit=2)

    assert result.solved and result.assignment == expected
    assert {person: str(square) for person, square in result.assignment.items()} == {
        "Mara": "r1c2",
        "Nico": "r2c3",
        "Ria": "r4c4",
        "Tomas": "r5c5",
    }
    victim_region = board.region_of(result.assignment["Tomas"])
    companions = [
        person
        for person, square in result.assignment.items()
        if person != "Tomas" and board.region_of(square) == victim_region
    ]
    assert companions == ["Ria"]
    assert len({square.row for square in result.assignment.values()}) == 4
    assert len({square.col for square in result.assignment.values()}) == 4


def test_area_tags_cover_disconnected_regions_and_tagged_clues():
    text = """Size: 2
Regions:
a: island
b: sea
Grid:
a b
b a
AreaTags:
water: island sea
islands: island
Hatched:
islands
People:
A
B
Clues:
in_tagged A islands
same_region A B
"""
    board, _ = load_board(text)
    solutions = bruteforce.solutions(text, limit=3)

    assert board.area_tags == {"water": ["island", "sea"], "islands": ["island"]}
    assert board.hatched == {"a"}
    assert len(solutions) == 2
    assert all(
        board.region_of(solution["A"]) == board.region_of(solution["B"]) == "a"
        for solution in solutions
    )


def test_next_to_does_not_cross_an_overlay_area_boundary_with_shared_tag():
    text = """Size: 3
Regions:
a: water
b: island
Grid:
a b a
a b a
a b a
AreaTags:
water_areas: water island
Objects:
post: blocking r2c2
People:
A
B
Clues:
next_to A post
"""
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    options = {model.value_of(lit) for lit in model.options("A")}

    assert options == {murdoku.Square(0, 1), murdoku.Square(2, 1)}
    assert board.region_ids(["water"]) == {"a"}
    assert board.tagged_region_ids(["water_areas"]) == {"a", "b"}


def test_rules_can_restrict_people_by_area_tag():
    text = """Size: 2
Regions:
a: island
b: sea
Grid:
a b
b a
AreaTags:
water: island
People:
A
B
Rules:
only_in_tagged A water
not_in_tagged B water
"""
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)

    assert {model.value_of(lit) for lit in model.options("A")} == {
        murdoku.Square(0, 0),
        murdoku.Square(1, 1),
    }
    assert {model.value_of(lit) for lit in model.options("B")} == {
        murdoku.Square(0, 1),
        murdoku.Square(1, 0),
    }


def test_legacy_groups_section_is_rejected():
    text = """Size: 2
Regions:
a: island
Grid:
a a
a a
Groups:
water: island
People:
A
B
"""
    with pytest.raises(ValueError, match="Groups: is no longer supported"):
        load_board(text)


def test_area_tags_and_board_rules_restrict_people():
    text = "\n".join(
        [
            "Size: 4",
            "Regions:",
            "a: village",
            "b: noble",
            "Grid:",
            "b b a a",
            "b a a a",
            "a a b a",
            "a a a b",
            "People:",
            "Anna",
            "Betsy",
            "Eli",
            "AreaTags:",
            "noble_areas: noble",
            "Rules:",
            "only_in_tagged Anna noble_areas",
            "not_in_tagged Betsy noble_areas",
            "",
        ]
    )
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    assert board.area_tags == {"noble_areas": ["noble"]}
    assert all(board.region_of(model.value_of(lit)) == "b" for lit in model.options("Anna"))
    assert all(board.region_of(model.value_of(lit)) != "b" for lit in model.options("Betsy"))
    assert len(model.options("Eli")) == len(board.free)


def test_exactly_one_noblewoman_one_row_above_eli():
    board = _one_region_board(4, ["Anna", "Betsy", "Eli", "Dean"])
    clue = (
        "exactly",
        ["1", "above", "Anna", "Eli", "1", ";", "above", "Betsy", "Eli", "1"],
    )
    (condition,) = murdoku.conditions(board, [clue])
    square = murdoku.Square
    assert condition.people == ("Anna", "Eli", "Betsy")
    assert condition.test(square(0, 0), square(1, 1), square(2, 2))
    assert condition.test(square(0, 0), square(3, 1), square(2, 2))
    assert not condition.test(square(0, 0), square(2, 1), square(3, 2))


def test_relations_prunes_a_whole_relation_in_one_step():
    m = Model()
    _variable(m, "a", (1, 2, 3, 4))
    _variable(m, "b", (1, 2, 3, 4))
    m.relate("a below 2 and b above 3", "ab", lambda a, b: a < 2 and b > 3)
    assert rule_relations(m) is True
    assert [m.value_of(lit) for lit in m.options("a")] == [1]
    assert [m.value_of(lit) for lit in m.options("b")] == [4]
    assert rule_relations(m) is False


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_render_crosses_out_squares_nobody_can_reach():
    board = _one_region_board(2, ["A", "B"])
    model = murdoku.compile_puzzle(board, [("in_region", ["A", "here"])])
    sq = murdoku.Square
    model.eliminate(model.literal("A", sq(0, 0)), "test", "gone")
    rows = _plain(murdoku.render(board, model, "t")).splitlines()[3:5]
    assert [row.split() for row in rows] == [["1", ".", "."], ["2", ".", "."]]
    steps_from = len(model.log)
    model.eliminate(model.literal("B", sq(0, 0)), "test", "gone")
    drawn = murdoku.render(board, model, "t", model.log[steps_from:])
    assert _plain(drawn).splitlines()[3].split() == ["1", "x", "."]
    assert "3 of 4 empty squares still possible" in _plain(drawn)
    assert re.search(r"B\s+-1\s+3 left", _plain(drawn))


def test_parse_square_rejects_garbage():
    assert parse_square("R2C5") == murdoku.Square(1, 4)
    with pytest.raises(ValueError):
        parse_square("r2x5")


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.txt")))
def test_every_step_is_logged_under_its_rule_name(name):
    """Narration groups steps by rule, so the names in the log must match the ladder."""
    text = (EXAMPLES / name).read_text()
    model = cli.load(text, cli.detect(text)).model
    fired: list[tuple[str, set[str]]] = []
    Solver(model).solve(on_step=lambda rule, steps: fired.append((rule, {s.rule for s in steps})))
    assert fired
    for rule, logged in fired:
        assert logged == {rule}


# --- prrrdoku 2 and 3 -----------------------------------------------------


def _load(name):
    board, clues = load_board((EXAMPLES / name).read_text())
    return board, murdoku.compile_puzzle(board, clues)


def _open(board, model):
    return {p: [str(s) for s in sqs] for p, sqs in murdoku.open_squares(board, model).items()}


def test_prrrdoku2_candidate_lists_match_the_document():
    board, model = _load("prrrdoku2.txt")
    open_sq = _open(board, model)
    assert open_sq["Tim"] == ["r1c2", "r2c1", "r2c3", "r3c2"]
    assert open_sq["Tjitske"] == ["r5c2", "r6c1", "r6c3", "r7c2"]
    assert open_sq["Otto"] == ["r5c6", "r6c5", "r6c7", "r7c6"]
    assert open_sq["Luna"] == ["r7c4", "r8c3", "r8c5", "r9c4"]


def test_prrrdoku2_region_borders_match_the_document():
    """'De speeltuin grenst aan het klimgebied, de keukenwinkel, het cafe en de kampeerplek.'"""
    board, _ = _load("prrrdoku2.txt")
    speeltuin = board.region_id("speeltuin")
    touching = {
        name for rid, name in board.region_names.items() if board.regions_touch(speeltuin, rid)
    }
    assert touching == {"klimgebied", "keukenwinkel", "cafe", "kampeerplek"}


def test_prrrdoku3_candidate_lists_after_late_reveal_board_change():
    """The connected-region redesign retains the late-reveal candidate lists."""
    board, model = _load("prrrdoku3.txt")
    open_sq = _open(board, model)
    assert open_sq["Tjitske"] == ["r4c1", "r5c2"]
    assert open_sq["Jos"] == ["r1c2", "r1c3", "r3c4", "r3c5", "r8c3", "r8c4"]
    assert open_sq["Tim"] == ["r1c6", "r3c6", "r6c7", "r6c9", "r7c6", "r9c6"]
    assert len(open_sq["Anna"]) == 8
    assert "r2c5" in open_sq["Anna"]
    assert len(open_sq["Luna"]) == 19


def test_prrrdoku3_bankastraat_is_connected():
    board, _ = _load("prrrdoku3.txt")
    region = board.region_id("bankastraat")
    cells = {
        (row, col)
        for row in range(board.size)
        for col in range(board.size)
        if board.regions[row][col] == region
    }
    reached = {next(iter(cells))}
    pending = list(reached)
    while pending:
        row, col = pending.pop()
        for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if neighbor in cells and neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    assert reached == cells


PUBLISHED = {
    "prrrdoku2.txt": (
        {
            "Jos": "r1c4",
            "Pip": "r2c8",
            "Tim": "r3c2",
            "Anna": "r4c7",
            "Vladimir": "r5c5",
            "Tjitske": "r6c1",
            "Otto": "r7c6",
            "Luna": "r8c3",
            "Mao": "r9c9",
        },
        "cafe",
        ["Otto"],
    ),
    "prrrdoku3.txt": (
        {
            "Anna": "r1c4",
            "Mao": "r2c9",
            "Tim": "r3c6",
            "Vladimir": "r4c5",
            "Tjitske": "r5c2",
            "Otto": "r6c7",
            "Luna": "r7c1",
            "Jos": "r8c3",
            "Pip": "r9c8",
        },
        "moestuin",
        ["Tim"],
    ),
}


@pytest.mark.parametrize("name", sorted(PUBLISHED))
def test_later_prrrdokus_reach_the_published_solution(name):
    solution, vlad_region, company = PUBLISHED[name]
    board, model = _load(name)
    result = Solver(model).solve()
    assert result.solved
    assert {p: str(sq) for p, sq in result.assignment.items()} == solution
    region = board.region_of(result.assignment["Vladimir"])
    assert board.region_names[region] == vlad_region
    assert [
        p
        for p, sq in result.assignment.items()
        if p != "Vladimir" and board.region_of(sq) == region
    ] == company


def test_prrrdoku2_still_needs_what_if():
    """The clue replacement preserves the answer and late reveal, but needs what-if."""
    _, model = _load("prrrdoku2.txt")
    result = Solver(model, _before("what_if")).solve()
    assert not result.solved and result.contradiction is None


def test_prrrdoku3_still_needs_what_if():
    _, model = _load("prrrdoku3.txt")
    result = Solver(model, _before("what_if")).solve()
    assert not result.solved and result.contradiction is None


def _chain_model(weak_by_relation: bool) -> Model:
    """A1 or A2, B1 or B2, T1 or T2; A2 and B1 exclude each other, and T1
    excludes both A1 and B2. Chain: A1 false, A2 true, B1 false, B2 true."""
    m = Model()
    lits = {(v, i): m.literal(v, i) for v in "ABT" for i in (1, 2)}
    for v in "ABT":
        m.constrain(f"{v} one", Kind.EXACTLY_ONE, [lits[v, 1], lits[v, 2]], defines=v)
    if weak_by_relation:
        m.relate("not A2 with B1", ("A", "B"), lambda a, b: (a, b) != (2, 1))
    else:
        m.constrain("A2 or B1", Kind.AT_MOST_ONE, [lits["A", 2], lits["B", 1]])
    m.constrain("A1 or T1", Kind.AT_MOST_ONE, [lits["A", 1], lits["T", 1]])
    m.constrain("B2 or T1", Kind.AT_MOST_ONE, [lits["B", 2], lits["T", 1]])
    return m


@pytest.mark.parametrize("weak_by_relation", [False, True])
def test_chains_rule_out_what_excludes_both_ends(weak_by_relation):
    m = _chain_model(weak_by_relation)
    assert not rule_relations(m) and not rule_subsumption(m)
    assert rule_chains(m)
    (step,) = m.log
    assert (step.var, step.value, step.asserted) == ("T", 1, False)
    assert step.chain == (("A", 1), ("A", 2), ("B", 1), ("B", 2))
    assert step.sources == ("A one", "not A2 with B1" if weak_by_relation else "A2 or B1", "B one")


def test_follow_chain_refuses_a_broken_chain():
    m = _chain_model(False)
    a1, a2, b1, b2 = (m.literal(v, i) for v, i in (("A", 1), ("A", 2), ("B", 1), ("B", 2)))
    assert not follow_chain(m, [a1, b1, a2, b2])
    assert not m.log


def test_standable_objects_can_be_stood_on_and_blocking_objects_cannot():
    sq = murdoku.Square
    board = _one_region_board(
        2,
        ["A", "B"],
        [
            murdoku.BoardObject("rock", "blocking", (sq(0, 0),)),
            murdoku.BoardObject("bank", "standable", (sq(1, 0), sq(1, 1))),
        ],
    )
    assert board.free == [sq(0, 1), sq(1, 0), sq(1, 1)]
    model = murdoku.compile_puzzle(board, [("on", ["A", "bank"])])
    assert sorted(model.value_of(lit) for lit in model.options("A")) == [sq(1, 0), sq(1, 1)]


def test_edge_items_and_corner_objects_expose_touched_cells():
    text = """Size: 3
Regions:
a: west
b: east
Grid:
a b a
a b a
a b a
People:
A
B
 C
EdgeItems:
gate: door r1c1 r1c2
gate: door r2c1 r2c2
window: window r3c3
CornerObjects:
critter: r1c1 r1c2 r2c1 r2c2
Clues:
next_to A gate
at A gate
at B window
next_to B window
next_to C critter
"""
    board, clues = load_board(text)
    square = murdoku.Square

    assert len(board.edge_items) == 3
    assert board.edge_item_cells(["gate"]) == {
        square(0, 0),
        square(0, 1),
        square(1, 0),
        square(1, 1),
    }
    assert board.edge_item_cells(["window"]) == {square(2, 2)}
    assert board.corner_object_cells(["critter"]) == {
        square(0, 0),
        square(0, 1),
        square(1, 0),
        square(1, 1),
    }
    assert len(board.free) == 9
    conditions = murdoku.conditions(board, clues)
    at_gate = next(condition for condition in conditions if condition.label == "at A gate")
    at_window = next(condition for condition in conditions if condition.label == "at B window")
    next_to_window = next(
        condition for condition in conditions if condition.label == "next_to B window"
    )
    next_to_gate = next(
        condition for condition in conditions if condition.label == "next_to A gate"
    )
    next_to_corner = next(
        condition for condition in conditions if condition.label == "next_to C critter"
    )
    assert {sq for sq in board.free if at_window.test(sq)} == {square(2, 2)}
    assert {sq for sq in board.free if at_gate.test(sq)} == board.edge_item_cells(["gate"])
    assert {sq for sq in board.free if next_to_window.test(sq)} == {square(2, 2)}
    assert {sq for sq in board.free if next_to_gate.test(sq)} == board.edge_item_cells(["gate"])
    assert {sq for sq in board.free if next_to_corner.test(sq)} == board.corner_object_cells(
        ["critter"]
    )
    rendered = _plain(murdoku.render(board, murdoku.compile_puzzle(board, clues), "t"))
    assert "edge items: gate door r1c1 r1c2, gate door r2c1 r2c2, window window r3c3" in rendered
    assert "corner objects: critter r1c1 r1c2 r2c1 r2c2" in rendered


def test_named_cell_marks_can_overlap_and_filter_occupants():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Marks:
quiet: r1c1 r1c2
social: r1c2
Clues:
on_mark A quiet
not_on_mark B social
"""
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)

    assert board.mark_names == {"quiet", "social"}
    assert board.mark_cells(["quiet", "social"]) == {
        murdoku.Square(0, 0),
        murdoku.Square(0, 1),
    }
    assert len(board.free) == 4
    assert {model.value_of(lit) for lit in model.options("A")} == board.mark_cells(["quiet"])
    assert murdoku.Square(0, 1) not in {model.value_of(lit) for lit in model.options("B")}
    rendered = _plain(murdoku.render(board, model, "marks"))
    assert "marks: quiet r1c1 r1c2, social r1c2" in rendered


def test_mark_names_cells_and_conditions_are_validated():
    base = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
"""
    with pytest.raises(ValueError, match="off the grid"):
        load_board(base + "Marks:\nquiet: r1c3\n")
    with pytest.raises(ValueError, match="defined more than once"):
        load_board(base + "Marks:\nquiet: r1c1\nquiet: r2c2\n")
    with pytest.raises(ValueError, match="use alone or not_alone"):
        load_board(base + "Marks:\nquiet: r1c1 ; crowded\n")

    board, _ = load_board(base + "Marks:\nquiet: r1c1\n")
    with pytest.raises(ValueError, match="unknown marks"):
        murdoku.compile_puzzle(board, [("on_mark", ["A", "missing"])])


def test_mark_occupant_conditions_are_conditional_and_match_brute_force():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Marks:
quiet: r1c1 ; alone
social: r1c2 ; not_alone
Clues:
on_mark A social
not_on_mark B quiet
"""
    (expected,) = bruteforce.solutions(text, "murdoku", limit=10)
    board, clues = load_board(text)
    model = murdoku.compile_puzzle(board, clues)
    result = Solver(model).solve()
    quiet = board.mark_cells(["quiet"])

    assert result.solved
    assert {person: result.assignment[person] for person in board.people} == expected
    assert not set(expected.values()) & quiet
    for step in model.log:
        if step.var not in board.people:
            continue
        if step.asserted:
            assert expected[step.var] == step.value, step
        else:
            assert expected[step.var] != step.value, step


def test_triggered_alone_mark_allows_other_regions_to_be_occupied():
    text = """Size: 2
Regions:
a: room
b: garden
Grid:
a b
a b
People:
A
B
Marks:
quiet: r1c1 ; alone
plain: r2c2
Clues:
on_mark A quiet
outside B room
"""
    (expected,) = bruteforce.solutions(text, "murdoku", limit=5)
    board, clues = load_board(text)
    result = Solver(murdoku.compile_puzzle(board, clues)).solve()

    assert result.solved
    assert {person: result.assignment[person] for person in board.people} == expected
    assert expected["A"] == murdoku.Square(0, 0)
    assert expected["B"] == murdoku.Square(1, 1)


def test_mark_occupant_conditions_only_count_the_marked_logical_area():
    text = """Size: 3
Regions:
a: room
b: garden
Grid:
a a b
a a b
a a b
People:
A
B
C
Marks:
quiet: r1c1 ; alone
social: r2c1 ; not_alone
"""
    board, _ = load_board(text)
    alone, not_alone = murdoku.conditions(board, [])
    square = murdoku.Square

    assert not alone.test(square(0, 0), square(1, 1), square(0, 2))
    assert alone.test(square(0, 0), square(0, 2), square(1, 2))
    assert alone.test(square(0, 1), square(1, 1), square(0, 2))
    assert not_alone.test(square(1, 0), square(0, 1), square(2, 2))
    assert not not_alone.test(square(1, 0), square(0, 2), square(2, 2))
    assert not_alone.test(square(0, 0), square(0, 2), square(2, 2))


def test_edge_item_geometry_is_validated():
    base = """Size: 3
Regions:
a: west
b: east
Grid:
a b a
a b a
a b a
People:
A
B
"""
    with pytest.raises(ValueError, match="two neighboring cells"):
        load_board(base + "EdgeItems:\ngate: door r1c1\n")
    with pytest.raises(ValueError, match="one inside cell"):
        load_board(base + "EdgeItems:\nwindow: window r1c1 r1c2\n")
    with pytest.raises(ValueError, match="neighboring cells"):
        load_board(base + "EdgeItems:\ngate: door r1c1 r3c2\n")
    with pytest.raises(ValueError, match="area boundary"):
        load_board(base + "EdgeItems:\ngate: door r1c1 r2c1\n")
    with pytest.raises(ValueError, match="four cells around one corner"):
        load_board(base + "CornerObjects:\ncritter: r1c1 r1c2 r2c1\n")


def test_next_to_objects_stays_in_area_but_edge_items_cross_boundaries():
    square = murdoku.Square
    board = murdoku.Board(
        2,
        [["west", "east"], ["west", "east"]],
        {"west": "west", "east": "east"},
        [murdoku.BoardObject("lamp", "blocking", (square(0, 0),))],
        ["A", "B"],
        edge_items=[murdoku.EdgeItem("gate", "door", (square(1, 0), square(1, 1)))],
    )
    object_condition, door_condition = murdoku.conditions(
        board, [("next_to", ["A", "lamp"]), ("next_to", ["B", "gate"])]
    )

    assert object_condition.test(square(1, 0))
    assert not object_condition.test(square(0, 1))
    assert door_condition.test(square(1, 0)) and door_condition.test(square(1, 1))


def test_not_on_excludes_a_standable_object_set():
    sq = murdoku.Square
    board = _one_region_board(
        3,
        ["A", "B", "C"],
        [murdoku.BoardObject("chair", "standable", (sq(0, 0), sq(0, 1)))],
    )
    model = murdoku.compile_puzzle(board, [("not_on", ["A", "chair"])])
    chair = board.squares_of(["chair"])
    assert all(model.value_of(lit) not in chair for lit in model.options("A"))


def test_only_on_standable_object_excludes_everyone_else_from_the_set():
    sq = murdoku.Square
    board = _one_region_board(
        3,
        ["A", "B", "C"],
        [murdoku.BoardObject("bed", "standable", (sq(0, 0), sq(0, 1)))],
    )
    model = murdoku.compile_puzzle(board, [("only_on", ["A", "bed"])])
    bed = board.squares_of(["bed"])
    assert {model.value_of(lit) for lit in model.options("A")} == bed
    assert all(
        model.value_of(lit) not in bed for person in ("B", "C") for lit in model.options(person)
    )


def test_in_corner_filters_to_the_four_grid_corners():
    board = _one_region_board(4, ["A", "B", "C"])
    model = murdoku.compile_puzzle(board, [("in_corner", ["A"])])
    assert {model.value_of(lit) for lit in model.options("A")} == {
        murdoku.Square(0, 0),
        murdoku.Square(0, 3),
        murdoku.Square(3, 0),
        murdoku.Square(3, 3),
    }


def test_left_of_can_require_an_exact_column_gap():
    board = _one_region_board(4, ["A", "B", "C", "D"])
    model = murdoku.compile_puzzle(board, [("left_of", ["A", "B", "1"])])
    (relation,) = model.relations
    assert relation.holds(murdoku.Square(0, 0), murdoku.Square(1, 1))
    assert not relation.holds(murdoku.Square(0, 0), murdoku.Square(1, 2))


def test_knight_move_and_shared_object_names():
    sq = murdoku.Square
    board = _one_region_board(
        3,
        ["A", "B", "C"],
        [
            murdoku.BoardObject("koffer", "blocking", (sq(0, 0),)),
            murdoku.BoardObject("koffer", "blocking", (sq(2, 2),)),
        ],
    )
    model = murdoku.compile_puzzle(board, [("knight_from", ["A", "koffer"])])
    reachable = sorted(model.value_of(lit) for lit in model.options("A"))
    assert reachable == [sq(0, 1), sq(1, 0), sq(1, 2), sq(2, 1)]
    with pytest.raises(ValueError):
        murdoku.compile_puzzle(board, [("next_to", ["A", "suitcase"])])


def test_furthest_is_strict():
    board = _one_region_board(2, ["A", "B"])
    model = murdoku.compile_puzzle(board, [("furthest", ["A", "B"])])
    assert len(model.relations) == 0
    board = _one_region_board(3, ["A", "B", "C"])
    model = murdoku.compile_puzzle(board, [("furthest", ["A", "B"])])
    (rel,) = model.relations
    sq = murdoku.Square
    assert rel.holds(sq(0, 0), sq(2, 2), sq(1, 1))
    assert not rel.holds(sq(0, 2), sq(2, 2), sq(2, 0))


def test_unknown_region_name_is_rejected():
    board = _one_region_board(2, ["A", "B"])
    with pytest.raises(ValueError):
        murdoku.compile_puzzle(board, [("in_region", ["A", "nowhere"])])


def test_not_next_to_rules_out_the_squares_beside_a_thing():
    sq = murdoku.Square
    board = _one_region_board(
        3, ["A", "B", "C"], [murdoku.BoardObject("vaas", "blocking", (sq(1, 1),))]
    )
    model = murdoku.compile_puzzle(board, [("not_next_to", ["A", "vaas"])])
    left = sorted(model.value_of(lit) for lit in model.options("A"))
    assert left == [sq(0, 0), sq(0, 2), sq(2, 0), sq(2, 2)]


def test_counting_clue_parses_its_parts():
    n, parts = murdoku.counted(["1", "in_region", "A", "x", ";", "left_of", "A", "B"])
    assert n == 1 and parts == [("in_region", ["A", "x"]), ("left_of", ["A", "B"])]
    with pytest.raises(ValueError, match="count first"):
        murdoku.counted(["in_region", "A", "x"])


def test_counting_clue_holds_when_exactly_n_parts_do():
    sq = murdoku.Square
    board = _one_region_board(3, ["A", "B", "C"])
    clue = ("exactly", ["1", "left_of", "A", "B", ";", "above", "A", "B"])
    (rel,) = murdoku.compile_puzzle(board, [clue]).relations
    assert rel.variables == ("A", "B")
    assert rel.holds(sq(1, 0), sq(0, 2))  # left of, not above
    assert not rel.holds(sq(0, 0), sq(2, 2))  # both
    assert not rel.holds(sq(2, 2), sq(0, 0))  # neither


def test_counting_clue_about_one_person_filters_at_compile_time():
    sq = murdoku.Square
    board = _one_region_board(2, ["A", "B"], [murdoku.BoardObject("vaas", "blocking", (sq(0, 0),))])
    clue = ("exactly", ["1", "next_to", "A", "vaas", ";", "not_next_to", "A", "vaas"])
    model = murdoku.compile_puzzle(board, [clue])
    assert not model.relations and len(model.options("A")) == 3


@pytest.mark.parametrize(
    "args, problem",
    [
        (["3", "left_of", "A", "B", ";", "above", "A", "B"], "can never hold"),
        (["1", "alone", "A", ";", "above", "A", "B"], "simple clues only"),
        (["1", "left_of", "A", "B", ";", "left_of", "C", "D"], "at most 3"),
    ],
)
def test_counting_clue_rejects_what_it_cannot_do(args, problem):
    board = _one_region_board(4, ["A", "B", "C", "D"])
    with pytest.raises(ValueError, match=problem):
        murdoku.compile_puzzle(board, [("exactly", args)])


def test_numeric_region_ids_still_read():
    """Ids are just tokens: older files numbered their regions."""
    text = (EXAMPLES / "prrrdoku1.txt").read_text()
    numbered = text.replace("\na: ", "\n0: ").replace("\nb: ", "\n1: ")
    numbered = re.sub(
        r"(?m)^([a-f] )+[a-f]$",
        lambda m: m[0].replace("a", "0").replace("b", "1"),
        numbered,
    )
    board, _ = load_board(numbered)
    assert board.region_names["0"] == "klimgebied"
    assert board.region_of(murdoku.Square(0, 3)) == "1"


# --- calcudoku -----------------------------------------------------------


# file, the rule it needs
CALCUDOKUS = [
    ("calcudoku_4x4_easy.txt", "relations"),
    ("calcudoku_6x6_medium.txt", "relations"),
    ("calcudoku_6x6_hard.txt", "cover2"),
    ("calcudoku_6x6_fiendish.txt", "what_if"),
    ("calcudoku_7x7_hard.txt", "cover3"),
]


@pytest.mark.parametrize("name, rule", CALCUDOKUS)
def test_calcudoku_solution_obeys_every_rule(name, rule):
    """A property check: Latin square, and every cage makes its target."""
    text = (EXAMPLES / name).read_text()
    model, puzzle = calcudoku.compile_puzzle(text)
    result = Solver(model).solve()
    assert result.solved
    n = puzzle.size
    grid = [[result.assignment[calcudoku.cell_name((r, c))] for c in range(n)] for r in range(n)]
    assert all(sorted(row) == list(range(1, n + 1)) for row in grid)
    assert all(sorted(col) == list(range(1, n + 1)) for col in zip(*grid, strict=True))
    assert all(cage.holds([grid[r][c] for r, c in cage.cells]) for cage in puzzle.cages)


@pytest.mark.parametrize("name, rule", [c for c in CALCUDOKUS if c[1] != "relations"])
def test_calcudoku_stalls_without_its_rule(name, rule):
    model, _ = calcudoku.compile_puzzle((EXAMPLES / name).read_text())
    result = Solver(model, _before(rule)).solve()
    assert not result.solved and result.contradiction is None


@pytest.mark.parametrize(
    "grid, cages, problem",
    [
        ("a a\nb b", "a: 3+", "no rule for cages"),
        ("a a\nb b", "a: 3+\nb: 3+\nc: 1", "not on the grid"),
        ("a b\nb a", "a: 3+\nb: 3+", "not one connected piece"),
        ("a a\nb c", "a: 1-\nb: 1\nc: 2/x", "bad rule"),
        ("a a\na b", "a: 2-\nb: 1", "needs exactly two cells"),
        ("a a\nb c", "a: 3\nb: 1\nc: 2", "need an operator"),
    ],
)
def test_calcudoku_rejects_malformed_files(grid, cages, problem):
    with pytest.raises(ValueError, match=problem):
        calcudoku.parse(f"Size: 2\nGrid:\n{grid}\nCages:\n{cages}\n")


def test_cage_arithmetic():
    cage = calcudoku.Cage
    assert cage(2, "/", ((0, 0), (0, 1))).holds([3, 6])
    assert cage(2, "/", ((0, 0), (0, 1))).holds([6, 3])
    assert not cage(2, "/", ((0, 0), (0, 1))).holds([4, 6])
    assert cage(3, "-", ((0, 0), (0, 1))).holds([1, 4])
    assert cage(24, "x", ((0, 0), (0, 1), (1, 0))).holds([2, 3, 4])


def test_cli_detects_calcudoku():
    text = (EXAMPLES / "calcudoku_4x4_easy.txt").read_text()
    assert cli.detect(text) == "calcudoku"
    assert cli.main([str(EXAMPLES / "calcudoku_4x4_easy.txt")]) == 0


# --- futoshiki ------------------------------------------------------------


def test_futoshiki_solution_obeys_every_sign_and_needs_chains():
    text = (EXAMPLES / "futoshiki_5x5.txt").read_text()
    assert cli.detect(text) == "futoshiki"
    model, puzzle = futoshiki.compile_puzzle(text)
    assert len(model.relations) == len(puzzle.signs) == 8
    result = Solver(model).solve()
    assert result.solved
    value = {
        (r, c): result.assignment[futoshiki.cell_name((r, c))] for r in range(5) for c in range(5)
    }
    assert all(value[s.smaller] < value[s.larger] for s in puzzle.signs)
    model, _ = futoshiki.compile_puzzle(text)
    stalled = Solver(model, _before("chains")).solve()
    assert not stalled.solved and stalled.contradiction is None


def test_futoshiki_signs_read_either_way_round():
    text = "Grid:\n" + ". . . .\n" * 4 + "Signs:\nr1c2 > r1c1\nr2c1 < R3C1\n"
    puzzle = futoshiki.parse(text)
    assert [(s.smaller, s.larger) for s in puzzle.signs] == [((0, 0), (0, 1)), ((1, 0), (2, 0))]
    assert puzzle.sign_between == {((0, 0), (0, 1)): "<", ((1, 0), (2, 0)): "<"}


@pytest.mark.parametrize(
    "grid, signs, problem",
    [
        (". . . .\n" * 3, "", "4x4 to 9x9"),
        (". . . .\n" * 3 + ". . . 5\n", "", "expected 1-4"),
        (". . . .\n" * 4, "r1c1 < r2c2", "not between neighbouring"),
        (". . . .\n" * 4, "r4c4 < r4c5", "off the grid"),
        (". . . .\n" * 4, "r1c1 = r1c2", "bad sign"),
    ],
)
def test_futoshiki_rejects_malformed_files(grid, signs, problem):
    with pytest.raises(ValueError, match=problem):
        futoshiki.parse(f"Grid:\n{grid}Signs:\n{signs}\n")


# --- brute force ----------------------------------------------------------


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.txt")))
def test_every_example_is_unique_and_the_engine_finds_it(name):
    text = (EXAMPLES / name).read_text()
    (expected,) = bruteforce.solutions(text)
    result = Solver(cli.load(text, cli.detect(text)).model).solve()
    assert result.solved
    assert result.assignment == expected


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.txt")))
def test_no_step_ever_contradicts_the_brute_force_solution(name):
    """Every placement is right and every elimination removes a wrong value,
    compile time included: the soundness contract, checked step by step."""
    text = (EXAMPLES / name).read_text()
    (expected,) = bruteforce.solutions(text)
    model = cli.load(text, cli.detect(text)).model
    Solver(model).solve()
    for step in model.log:
        assert (step.value == expected[step.var]) == step.asserted, step


def test_bruteforce_never_touches_the_engine():
    """Its whole point is independence: no import from csp.core, directly."""
    import ast

    package = Path(bruteforce.__file__).parent
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text())
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported |= {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not {m for m in imported if m.endswith("core")}, source.name


@pytest.mark.parametrize(
    "kind, text, count",
    [
        ("calcudoku", "Size: 2\nGrid:\na a\nb b\nCages:\na: 3+\nb: 3+\n", 2),
        ("calcudoku", "Size: 2\nGrid:\na a\nb b\nCages:\na: 4+\nb: 3+\n", 0),
        ("murdoku", "Size: 2\nRegions:\na: here\nGrid:\na a\na a\nPeople:\nA\nB\n", 4),
        ("sudoku", "\n".join(["5 5 . . . . . . ."] + [". " * 9] * 8), 0),
        ("futoshiki", "Grid:\n" + ". . . .\n" * 4 + "Signs:\n", 5),
        ("futoshiki", "Grid:\n" + ". . . .\n" * 4 + "Signs:\nr1c1 < r1c2\nr1c2 < r1c1\n", 0),
    ],
)
def test_bruteforce_reports_non_unique_and_impossible_puzzles(kind, text, count):
    assert len(bruteforce.solutions(text, kind, limit=5)) == count


def test_bruteforce_sudoku_stops_at_the_limit():
    empty = "\n".join([". " * 9] * 9)
    assert len(bruteforce.solutions(empty, "sudoku", limit=3)) == 3


def test_cli_brute_force_exit_codes(tmp_path, capsys):
    assert cli.main([str(EXAMPLES / "prrrdoku2.txt"), "--brute-force"]) == 0
    assert "unique solution" in capsys.readouterr().out
    two = tmp_path / "two.txt"
    two.write_text("Size: 2\nGrid:\na a\nb b\nCages:\na: 3+\nb: 3+\n")
    assert cli.main([str(two), "--brute-force"]) == 1
    assert "more than one solution" in capsys.readouterr().out


def test_cli_tracks_murdoku_person_candidates(capsys):
    assert cli.main([str(EXAMPLES / "prrrdoku1.txt"), "--track-person", "Vladimir"]) == 0
    out = capsys.readouterr().out
    assert "tracked Vladimir:" in out
    assert "region-overlap companions:" in out
    assert "tracked Vladimir: r7c3 (kampeerplek)" in out


@pytest.mark.parametrize("name", ["prrrdoku1.txt", "prrrdoku2.txt", "prrrdoku3.txt"])
def test_prrrdokus_keep_vladimir_open_until_last(name):
    board, clues = load_board((EXAMPLES / name).read_text())
    model = murdoku.compile_puzzle(board, clues)
    placements = []
    before_last = []

    def inspect_open_target():
        remaining_people = [
            person
            for person in board.people
            if person != "Vladimir" and model.chosen(person) is None
        ]
        if model.chosen("Vladimir") is None and remaining_people:
            squares, companions = murdoku.track_person_candidates(board, model, "Vladimir")
            before_last.append((len(squares), len(companions)))

    inspect_open_target()

    def on_step(rule, steps):
        assigned = [step.var for step in steps if step.asserted]
        placements.extend(assigned)
        if "Vladimir" in assigned:
            assert assigned == ["Vladimir"]
            assert all(
                model.chosen(person) is not None for person in board.people if person != "Vladimir"
            )
        else:
            inspect_open_target()

    result = Solver(model).solve(on_step=on_step)
    assert result.solved
    assert placements[-1] == "Vladimir"
    assert before_last
    assert all(
        square_count > 1 and companion_count > 1 for square_count, companion_count in before_last
    )
    squares, companions = murdoku.track_person_candidates(board, model, "Vladimir")
    assert len(squares) == 1
    assert len(companions) == 1


# --- model report ---------------------------------------------------------


def test_report_describes_prrrdoku1_as_the_engine_sees_it():
    _, model = _load("prrrdoku1.txt")
    text = report.describe(model)
    assert "7 variables, 301 literals, 64 constraints, 4 relations." in text
    assert re.search(r"each square holds at most one person\s+AT_MOST_ONE\s+43\s+7", text)
    assert "Every literal sits in exactly 4 constraints." in text
    assert re.search(r"next_to Tim klimwand\s+40 ruled out", text)
    assert re.search(r"Otto above Tjitske 1\s+12 of 86", text)
    assert all(re.search(rf"\d\. {rule.name}\s", text) for rule in DEFAULT_RULES)
    assert re.search(
        r"cover2\s+Find covers whose inner constraints guarantee `2` additional\s+truths", text
    )


def test_report_describes_count_constraints_and_reifiers():
    model = Model()
    first = model.literal("person_a", "west")
    second = model.literal("person_b", "west")
    empty = model.literal("west_empty", True)
    model.constrain(
        "west occupancy",
        Kind.COUNT,
        [first, second],
        allowed_counts={0, 2},
        reified_by=empty,
        family="area occupancy",
    )

    text = report.describe(model)

    assert "COUNT (1 here):" in text
    assert "COUNT {0, 2}" in text
    assert "allowed counts 0, 2; reified by west_empty=True" in text


def test_report_shows_known_and_unknown_role_membership():
    text = """Size: 2
Regions:
a: room
Grid:
a a
a a
People:
A
B
Roles:
bandit: any
Rules:
has_role A bandit
"""
    board, clues = load_board(text)
    text = report.describe(murdoku.compile_puzzle(board, clues))

    assert "Role membership (2):" in text
    assert "A has role bandit: present" in text
    assert "B has role bandit: unknown" in text


def test_report_groups_unlabelled_constraints_by_name():
    m = Model()
    lits = _variable(m, "x", (1, 2, 3))
    m.constrain("pair 1", Kind.AT_MOST_ONE, lits[:2])
    m.constrain("pair 2", Kind.AT_MOST_ONE, lits[1:])
    assert re.search(r"pair #\s+AT_MOST_ONE\s+2\s+2", report.describe(m))


def test_report_leaves_the_model_untouched():
    model, _ = sudoku.compile_puzzle((EXAMPLES / "sudoku_xwing.txt").read_text())
    before = (len(model.log), model.assignment(), [model.options(v) for v in model.variables])
    report.describe(model)
    assert before == (
        len(model.log),
        model.assignment(),
        [model.options(v) for v in model.variables],
    )


def test_grade_is_the_hardest_rung_used():
    assert report.grade(["single", "cover2", "relations", "single"]) == "cover2"
    assert report.grade([]) == "none"
    assert report.rules_used(["single", "cover2", "single"]) == (
        "rules used: single 2, cover2 1; grade: cover2"
    )


@pytest.mark.parametrize(
    "name, grade",
    [
        ("sudoku_easy.txt", "single"),
        ("sudoku_pointing.txt", "subsumption"),
        ("sudoku_swordfish.txt", "cover3"),
        ("sudoku_chains.txt", "chains"),
        ("prrrdoku2.txt", "what_if"),
        ("prrrdoku3.txt", "what_if"),
    ],
)
def test_cli_grade_prints_only_the_grade(name, grade, capsys):
    assert cli.main([str(EXAMPLES / name), "--grade"]) == 0
    assert capsys.readouterr().out == f"{grade}\n"


def test_show_model_explains_and_does_not_solve(capsys):
    assert cli.main([str(EXAMPLES / "sudoku_easy.txt"), "--show-model"]) == 0
    out = capsys.readouterr().out
    assert "each digit once per box" in out
    assert "How the solver will run" in out
    assert "Solved" not in out
    assert max(len(line) for line in out.split("Start", 1)[1].splitlines()) <= report.WIDTH
