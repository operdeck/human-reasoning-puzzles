import random
from itertools import product
from pathlib import Path

import pytest

from csp import cli, fresh
from csp.bridges import compile_puzzle, crosses, pair_name, parse
from csp.bruteforce.bridges import solutions
from csp.core import DEFAULT_RULES, Solver

SQUARE = "Family: bridges\nSize: 3\nIslands:\n2 . 2\n. . .\n2 . 2\n"


def test_neighbours_skip_water_but_never_intermediate_islands():
    puzzle = parse("Family: Bridges\nSize: 2 5\nIslands:\n1 . 2 . 1\n. . . . .\n")
    assert puzzle.pairs == (((0, 0), (0, 2)), ((0, 2), (0, 4)))


@pytest.mark.parametrize(
    "text",
    [
        SQUARE.replace("Size: 3", "Size: 1"),
        SQUARE.replace("Size: 3", "Size: 3 3 3"),
        SQUARE.replace("Size: 3", "Size: not-a-size"),
        SQUARE.replace("2 . 2", "2 .", 1),
        SQUARE.replace("2 . 2", "9 . 2", 1),
        SQUARE.replace("Family: bridges", "Family: slant"),
        "Family: bridges\nSize: 2\nIslands:\n1 .\n. .\n",
    ],
)
def test_invalid_boards_have_explicit_errors(text):
    with pytest.raises(ValueError):
        parse(text)


def test_crossings_exclude_parallel_segments_and_shared_endpoints():
    assert crosses(((1, 0), (1, 4)), ((0, 2), (3, 2)))
    assert not crosses(((1, 0), (1, 4)), ((1, 4), (3, 4)))
    assert not crosses(((1, 0), (1, 4)), ((2, 0), (2, 4)))


def test_connectivity_excludes_the_two_disconnected_double_bridge_solutions():
    puzzle = parse(SQUARE)
    found = solutions(SQUARE, limit=10)
    assert found == [{pair_name(pair): 1 for pair in puzzle.pairs}]


def test_compiler_counts_both_bridge_units_and_requires_a_connected_network():
    model, puzzle = compile_puzzle(SQUARE)
    counts = [
        constraint
        for constraint in model.constraints
        if constraint.family == "each island has its numbered bridge count"
    ]
    assert len(counts) == len(puzzle.islands)
    assert all(len(constraint.literals) == 4 for constraint in counts)
    answer = Solver(model).solve()
    assert answer.solved and answer.assignment == solutions(SQUARE)[0]


def test_one_island_capacity_forces_a_single_bridge_without_graph_rules():
    text = "Family: bridges\nSize: 2 3\nIslands:\n1 . 1\n. . .\n"
    model, _ = compile_puzzle(text)
    before = next(i for i, rule in enumerate(DEFAULT_RULES) if rule.name == "reach")
    answer = Solver(model, DEFAULT_RULES[:before]).solve()
    assert answer.solved and answer.assignment == {"r1c1-r1c3": 1}


def test_fresh_generation_is_reproducible_original_and_unique():
    first = fresh.fresh("bridges", 7, random.Random(0))
    assert first is not None
    assert len(solutions(first)) == 1
    assert first == fresh.fresh("bridges", 7, random.Random(0))
    assert first != fresh.fresh("bridges", 7, random.Random(1))
    assert all(value in range(1, 9) for value in parse(first).islands.values())


def test_search_distinguishes_multiple_impossible_and_limited_results():
    multiple = SQUARE.replace("2 . 2", "3 . 3")
    assert len(solutions(multiple, limit=10)) == 2
    assert len(solutions(multiple, limit=1)) == 1
    assert solutions(multiple, limit=0) == []
    assert solutions(SQUARE.replace("2 . 2", "1 . 1"), limit=10) == []


def test_brute_force_matches_exhaustive_degree_and_connectivity_oracle():
    puzzle = parse(SQUARE)
    endpoints = puzzle.pairs
    for clues in product((1, 2, 3), repeat=4):
        islands = dict(zip(sorted(puzzle.islands), clues, strict=True))
        text = (
            "Family: bridges\nSize: 3\nIslands:\n"
            f"{clues[0]} . {clues[1]}\n. . .\n{clues[2]} . {clues[3]}\n"
        )
        expected = []
        for values in product(range(3), repeat=len(endpoints)):
            if any(
                sum(value for pair, value in zip(endpoints, values, strict=True) if cell in pair)
                != clue
                for cell, clue in islands.items()
            ):
                continue
            reached = {min(islands)}
            while True:
                expanded = reached | {
                    cell
                    for pair, value in zip(endpoints, values, strict=True)
                    if value and reached.intersection(pair)
                    for cell in pair
                }
                if expanded == reached:
                    break
                reached = expanded
            if reached == set(islands):
                expected.append(dict(zip(map(pair_name, endpoints), values, strict=True)))
        assert sorted(solutions(text, limit=100), key=repr) == sorted(expected, key=repr)


@pytest.mark.solutions
@pytest.mark.parametrize(
    "path",
    sorted((Path(__file__).resolve().parents[1] / "examples").glob("bridges_*.txt")),
    ids=lambda path: path.name,
)
def test_original_examples_have_sound_deductions_and_independent_unique_solutions(path):
    text = path.read_text()
    (answer,) = solutions(text, limit=2)
    model, puzzle = compile_puzzle(text)
    result = Solver(model).solve()
    assert result.solved and result.assignment == answer
    for step in model.log:
        if step.var in answer:
            assert (answer[step.var] == step.value) == step.asserted
        else:
            pair, _, threshold = step.var.rpartition(" at least ")
            assert pair in answer and threshold in {"1", "2"}
            truth = answer[pair] >= int(threshold)
            assert (truth == step.value) == step.asserted
    assert any(value == 1 for value in answer.values())
    assert any(value == 2 for value in answer.values())
    assert len(puzzle.islands) >= 6


@pytest.mark.solutions
@pytest.mark.parametrize(
    "file,rule",
    [("bridges_2_7x7.txt", "cut"), ("bridges_5_13x13.txt", "closure")],
)
def test_graph_techniques_are_necessary_in_published_examples(file, rule):
    text = (Path(__file__).resolve().parents[1] / "examples" / file).read_text()
    before = next(i for i, candidate in enumerate(DEFAULT_RULES) if candidate.name == rule)
    model, _ = compile_puzzle(text)
    assert not Solver(model, DEFAULT_RULES[:before]).solve().solved
    model, _ = compile_puzzle(text)
    fired = []
    assert Solver(model).solve(on_step=lambda name, steps: fired.append(name)).solved
    assert rule in fired


@pytest.mark.parametrize("language", ("en", "nl"))
def test_worked_solutions_describe_bridge_units_instead_of_hidden_helpers(language):
    text = (
        Path(__file__).resolve().parents[1] / "examples" / "bridges_2_7x7.txt"
    ).read_text() + f"\nLanguage:\n{language}\n"
    model, _ = compile_puzzle(text)
    explanation = cli.pattern_story("bridges", text, model)
    assert explanation.complete
    prose = "\n".join(explanation.paragraphs)
    assert "intermediate step" not in prose
    assert "matches its bridge count" not in prose
    assert ("brug" if language == "nl" else "bridge") in prose
