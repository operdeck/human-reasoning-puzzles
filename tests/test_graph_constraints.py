"""Independent connectivity checks and provenance for generic graph rules."""

from itertools import product
from random import Random

import pytest

from csp import generic_story, report, story
from csp.core import (
    DEFAULT_RULES,
    Contradiction,
    Kind,
    Model,
    Solver,
    rule_closure,
    rule_cut,
    rule_reach,
    rule_what_if,
)
from csp.proof import Move, essential, replay


def boolean(model: Model, name: str, *, hidden: bool = False) -> int:
    yes, no = model.literal(name, True), model.literal(name, False)
    model.constrain(f"{name} domain", Kind.EXACTLY_ONE, (yes, no), defines=name, hidden=hidden)
    return yes


def test_registry_is_immutable_validated_and_clone_safe():
    model = Model()
    edge = boolean(model, "edge")
    nodes = {"a": None, "b": None}
    model.connect("network", nodes, (("a", "b", edge),), family="one network")
    nodes["c"] = None
    graph = model.graphs[0]
    assert tuple(graph.nodes) == ("a", "b")
    with pytest.raises(TypeError):
        graph.nodes["c"] = None  # type: ignore[index]
    twin = model.clone()
    assert twin.graphs is model.graphs
    twin.assign(edge, "test", "choose")
    assert not model.is_true(edge)
    twin.connect("other", {}, ())
    assert len(model.graphs) == 1
    with pytest.raises(ValueError, match="duplicate"):
        model.constrain("network", Kind.AT_MOST_ONE, ())
    with pytest.raises(ValueError, match="duplicate"):
        model.relate("network", (), lambda: True)
    with pytest.raises(ValueError, match="duplicate"):
        model.connect("edge domain", {}, ())
    with pytest.raises(ValueError, match="self-loop"):
        model.connect("loop", {"a": None}, (("a", "a", edge),))
    with pytest.raises(ValueError, match="endpoint"):
        model.connect("bad endpoint", {"a": None}, (("a", "b", edge),))
    with pytest.raises(ValueError, match="presence"):
        model.connect("bad literal", {"a": model.num_literals}, ())


def test_implicit_edges_do_not_force_optional_nodes_and_true_edges_do():
    model = Model()
    node = boolean(model, "b")
    model.connect("implicit", {"a": None, "b": node}, (("a", "b", None),))
    assert not rule_reach(model)
    assert not rule_cut(model)
    edge = boolean(model, "edge")
    model.connect("explicit", {"a": None, "b": node}, (("a", "b", edge),))
    model.assign(edge, "test", "present")
    assert rule_reach(model)
    assert model.is_true(node)
    assert model.log[-2].graph is not None
    assert model.log[-2].rule == "reach"


def test_reach_prunes_stranded_optional_nodes_and_edges():
    model = Model()
    b, c, edge = (boolean(model, name) for name in ("b", "c", "bc"))
    model.connect("network", {"a": None, "b": b, "c": c}, (("b", "c", edge),))
    while rule_reach(model):
        pass
    assert all(model.is_false(lit) for lit in (b, c, edge))
    assert all(step.rule == "reach" for step in model.log)
    assert model.graph_state(0).required == {"a"}
    absent = Model()
    node, edge = boolean(absent, "b"), boolean(absent, "edge")
    absent.connect("network", {"a": None, "b": node}, (("a", "b", edge),))
    absent.eliminate(node, "test", "absent")
    assert rule_reach(absent)
    assert absent.is_false(edge)


def test_no_required_node_does_not_select_a_component():
    model = Model()
    a, b = boolean(model, "a"), boolean(model, "b")
    model.connect("network", {"a": a, "b": b}, ())
    assert not rule_reach(model)
    assert not rule_cut(model)
    model.assign(a, "test", "present")
    assert rule_reach(model)
    assert model.is_false(b)


def test_shared_presence_literals_and_node_only_articulation():
    model = Model()
    middle = boolean(model, "middle")
    model.connect(
        "network",
        {"a": None, "middle": middle, "b": None},
        (("a", "middle", None), ("middle", "b", None)),
    )
    assert rule_cut(model)
    assert model.is_true(middle)
    assert model.log[0].graph.cut_nodes == ("middle",)
    move = Move.of("cut", model.log)
    before = Model()
    before_middle = boolean(before, "middle")
    before.connect(
        "network",
        {"a": None, "middle": before_middle, "b": None},
        (("a", "middle", None), ("middle", "b", None)),
    )
    assert replay(before, [move]).is_true(before_middle)
    shared = Model()
    presence = boolean(shared, "shared")
    shared.connect(
        "shared network",
        {"a": None, "b": presence, "c": presence},
        (("a", "b", presence), ("b", "c", presence)),
    )
    shared.assign(presence, "test", "present")
    assert Solver(shared).solve().solved


def test_cut_requires_only_separators_between_required_nodes():
    model = Model()
    middle, leaf = boolean(model, "middle"), boolean(model, "leaf")
    first, second, branch = (boolean(model, name) for name in ("first", "second", "branch"))
    model.connect(
        "network",
        {"a": None, "middle": middle, "b": None, "leaf": leaf},
        (("a", "middle", first), ("middle", "b", second), ("middle", "leaf", branch)),
    )
    while rule_cut(model):
        pass
    assert model.is_true(first) and model.is_true(second) and model.is_true(middle)
    assert not model.is_true(branch) and not model.is_true(leaf)
    assert {step.rule for step in model.log} == {"cut"}
    assert any(step.graph and step.graph.cut_nodes == ("middle",) for step in model.log)


def test_parallel_edges_are_not_bridges_and_articulation_still_works():
    model = Model()
    first, second, middle = (boolean(model, name) for name in ("first", "second", "middle"))
    model.connect(
        "network",
        {"a": None, "middle": middle, "b": None},
        (("a", "middle", first), ("a", "middle", second), ("middle", "b", None)),
    )
    assert rule_cut(model)
    assert model.is_true(middle)
    assert not model.is_true(first) and not model.is_true(second)


def test_empty_singleton_final_disconnected_and_hidden_graph_states():
    for nodes in ({}, {"a": None}):
        model = Model()
        model.connect("network", nodes, ())
        assert Solver(model).solve().solved
        assert "CONNECTED" in report.describe(model)
    model = Model()
    edge = boolean(model, "hidden edge", hidden=True)
    model.connect("network", {"a": None, "b": None}, (("a", "b", edge),))
    assert model.assignment() == {}
    assert model.solution() is None
    assert not Solver(model, ()).solve().solved
    model.eliminate(edge, "test", "absent")
    assert model.solution() is None
    result = Solver(model, ()).solve()
    assert not result.solved and "cannot connect" in result.contradiction
    bad = Model()
    node, edge = boolean(bad, "node"), boolean(bad, "edge")
    bad.connect("network", {"a": None, "b": node}, (("a", "b", edge),))
    bad.eliminate(node, "test", "absent")
    bad.assign(edge, "test", "present")
    with pytest.raises(Contradiction, match="endpoints"):
        bad.check()


def closure_model() -> tuple[Model, int]:
    """A doubled internal edge would consume the last exit from a triangle."""
    model = Model()
    multiplicities = [model.literal("ab", count) for count in range(3)]
    model.constrain("ab domain", Kind.EXACTLY_ONE, multiplicities, defines="ab")
    first, double = (
        boolean(model, "ab present", hidden=True),
        boolean(model, "ab double", hidden=True),
    )
    exit_a, exit_b = boolean(model, "ac"), boolean(model, "bc")
    model.constrain(
        "ab presence", Kind.COUNT, multiplicities[1:], allowed_counts=(1,), reified_by=first
    )
    model.constrain(
        "ab doubled", Kind.COUNT, multiplicities[2:], allowed_counts=(1,), reified_by=double
    )
    model.constrain("a degree", Kind.COUNT, (first, double, exit_a), allowed_counts=(2,))
    model.constrain("b degree", Kind.COUNT, (first, double, exit_b), allowed_counts=(2,))
    model.connect(
        "network",
        {"a": None, "b": None, "c": None},
        (("a", "b", first), ("a", "c", exit_a), ("b", "c", exit_b)),
        family="all nodes connected",
    )
    model.assign(first, "test", "already a bridge")
    return model, multiplicities[2]


def test_closure_refutes_double_options_with_graph_specific_evidence_and_replay():
    model, double = closure_model()
    start = model.clone(keep_log=True)
    assert not rule_reach(model) and not rule_cut(model)
    mark = len(model.log)
    assert rule_closure(model)
    assert model.is_false(double)
    step = model.log[mark]
    assert step.rule == "closure"
    assert step.graph and step.graph.assumption == double
    assert "closes off a required component" in step.reason
    assert step.trail and not any(s.rule == "what_if" for s in step.trail)
    assert essential(start, start.log, step)
    move = Move.of("closure", model.log[mark:])
    assert move is not None
    assert replay(start, [move]).is_false(double)
    for language, phrase in (("en", "Component closure"), ("nl", "Afgesloten deel")):
        explanation = generic_story.explain(
            f"Language: {language}\n", start, [("closure", model.log[mark:])]
        )
        assert phrase in explanation.markdown()
        assert "a" in explanation.markdown() and "c" in explanation.markdown()


def test_closure_does_not_accept_unrelated_count_contradictions():
    model = Model()
    edge = boolean(model, "edge")
    model.connect("network", {"a": None, "b": None}, (("a", "b", edge), ("a", "b", None)))
    model.constrain("unrelated rejection", Kind.COUNT, (edge,), allowed_counts=(0,))
    assert not rule_closure(model)
    assert not model.is_false(edge)


def test_cut_runs_inside_what_if_and_closure_never_runs_inside_it():
    model = Model()
    choose = boolean(model, "choose")
    first, second = boolean(model, "first"), boolean(model, "second")
    model.connect(
        "network",
        {"a": None, "b": None},
        (("a", "b", first), ("a", "b", second)),
    )
    model.constrain("chosen blocks first", Kind.AT_MOST_ONE, (choose, first))
    model.relate("chosen blocks second", ("choose", "second"), lambda a, b: not (a and b))
    assert rule_what_if(model)
    assert model.is_false(choose)
    assert any(step.rule == "cut" for step in model.log[0].trail)
    assert not any(step.rule == "closure" or step.trail for step in model.log[0].trail)


def test_graph_moves_report_and_bilingual_narration():
    model = Model()
    edge = boolean(model, "a-b")
    model.connect("network", {"a": None, "b": None}, (("a", "b", edge),), family="connected")
    start = model.clone()
    fired = []
    assert Solver(model).solve(on_step=lambda rule, steps: fired.append((rule, steps))).solved
    assert report.grade(rule for rule, _ in fired) == "cut"
    assert "CONNECTED, 2 nodes" in report.describe(start)
    moves = [Move.of(rule, steps) for rule, steps in fired if rule != "single"]
    assert replay(start, [move for move in moves if move]).solution() == model.solution()
    for language, expected in (("en", "Connectivity cut"), ("nl", "Verbindingssnede")):
        explanation = generic_story.explain(f"Language: {language}\n", start, fired)
        assert explanation.complete and expected in explanation.markdown()
    assert "two bridges" in story.family_rules("Family: bridges\n", "bridges")[0]
    assert "twee bruggen" in story.family_rules("Language: nl\nFamily: bridges\n", "bridges")[0]


def test_iterative_cut_handles_a_25_by_25_snaking_path():
    model = Model()
    nodes = {str(i): None for i in range(625)}
    edges = [(str(i), str(i + 1), boolean(model, f"edge{i}")) for i in range(624)]
    model.connect("network", nodes, edges)
    assert rule_cut(model)
    assert model.is_true(edges[0][2])


def _connected(nodes, edges, assignment):
    present = {node for node, lit in nodes.items() if lit is None or assignment[lit]}
    adjacency = {node: set() for node in present}
    for left, right, lit in edges:
        if lit is not None and assignment[lit] and not {left, right} <= present:
            return False
        if {left, right} <= present and (lit is None or assignment[lit]):
            adjacency[left].add(right)
            adjacency[right].add(left)
    if not present:
        return True
    seen = {next(iter(present))}
    todo = list(seen)
    while todo:
        for other in adjacency[todo.pop()] - seen:
            seen.add(other)
            todo.append(other)
    return seen == present


def test_random_graph_deductions_against_independent_exhaustive_completions():
    random = Random(178)
    for _ in range(100):
        model = Model()
        nodes = {
            str(i): None if random.random() < 0.4 else boolean(model, f"node{i}")
            for i in range(random.randrange(1, 5))
        }
        edges = []
        for left, right in product(nodes, repeat=2):
            if left < right and random.random() < 0.65:
                lit = None if random.random() < 0.3 else boolean(model, f"{left}-{right}")
                edges.append((left, right, lit))
        model.connect("network", nodes, edges)
        presences = [
            lit for lit in (*nodes.values(), *(edge[2] for edge in edges)) if lit is not None
        ]
        for lit in presences:
            state = random.randrange(3)
            if state == 1:
                model.assign(lit, "test", "present")
            elif state == 2:
                model.eliminate(lit, "test", "absent")
        completions = []
        for values in product((False, True), repeat=len(presences)):
            assignment = dict(zip(presences, values, strict=True))
            if any(
                (model.is_true(lit) and not assignment[lit])
                or (model.is_false(lit) and assignment[lit])
                for lit in presences
            ):
                continue
            if _connected(nodes, edges, assignment):
                completions.append(assignment)
        for rule in (rule_reach, rule_cut, rule_closure):
            trial = model.clone()
            try:
                mark = len(trial.log)
                while rule(trial):
                    for step in trial.log[mark:]:
                        lit = trial.literal(step.var, step.value)
                        if lit in presences:
                            assert all(
                                assignment[lit] == step.asserted for assignment in completions
                            )
                    mark = len(trial.log)
            except Contradiction:
                assert not completions


def test_graph_rules_are_noops_for_non_graph_models_and_have_ladder_log_names():
    model = Model()
    boolean(model, "a")
    assert not any(rule(model) for rule in (rule_reach, rule_cut, rule_closure))
    names = [rule.name for rule in DEFAULT_RULES]
    assert (
        names.index("reach") < names.index("cut") < names.index("closure") < names.index("what_if")
    )
