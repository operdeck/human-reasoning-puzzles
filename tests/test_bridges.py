from itertools import product

import pytest

from csp.bridges import crosses, pair_name, parse
from csp.bruteforce.bridges import solutions

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
