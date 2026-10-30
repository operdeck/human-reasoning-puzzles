import random

import pytest

from csp import bruteforce, calcudoku, fresh
from csp.puzzle_lab import _generate_calcudoku, main, rate
from tests.examples import example


@pytest.mark.parametrize("size", (2, 4, 6, 7))
@pytest.mark.parametrize("seed", range(5))
def test_cage_partition_merges_stranded_single_cells(size, seed):
    owner = fresh._cages(size, random.Random(seed), (2, 3, 4))
    assert set(owner) == {(r, c) for r in range(size) for c in range(size)}
    for cage in set(owner.values()):
        cells = [cell for cell, group in owner.items() if group == cage]
        assert len(cells) >= 2
        assert calcudoku._connected(cells)


def test_merging_rederives_the_receiving_cages_clue():
    grid = [[1, 2], [2, 1]]
    owner = {(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): 1}
    text = fresh.calcudoku_from_solution(grid, owner, random.Random(135), clues={0: "1", 1: "5+"})
    puzzle = calcudoku.parse(text)
    assert len(puzzle.cages) == 1
    cage = puzzle.cages[0]
    assert len(cage.cells) == 4
    assert cage.label != "5+"
    assert cage.holds([grid[r][c] for r, c in cage.cells])


@pytest.mark.parametrize("size,seed", [(4, 13504), (6, 13506)])
def test_fresh_calcudoku_is_repeatable_unique_and_has_no_singletons(size, seed):
    text = fresh.fresh_calcudoku(size, random.Random(seed))
    assert text is not None
    assert text == fresh.fresh_calcudoku(size, random.Random(seed))
    assert all(len(cage.cells) >= 2 for cage in calcudoku.parse(text).cages)
    assert len(bruteforce.solutions(text, limit=2)) == 1
    assert rate(text).tier != "trivial"


def test_fresh_calcudoku_rejects_size_without_room_for_a_multi_cell_cage():
    with pytest.raises(ValueError, match="at least 2x2"):
        fresh.fresh_calcudoku(1, random.Random(135))


@pytest.mark.parametrize("seed", range(5))
def test_seed_variations_keep_the_solution_without_creating_singletons(seed):
    source = example("calcudoku_single_cell_cages.txt").read_text()
    (solution,) = bruteforce.solutions(source)
    candidate = _generate_calcudoku(source, solution, random.Random(seed))
    assert candidate is not None
    puzzle = calcudoku.parse(candidate)
    assert all(len(cage.cells) >= 2 for cage in puzzle.cages)
    assert all(
        cage.holds([solution[calcudoku.cell_name(c)] for c in cage.cells]) for cage in puzzle.cages
    )
    assert candidate.startswith(source.split("Size:")[0])
    assert candidate == _generate_calcudoku(source, solution, random.Random(seed))


def test_fresh_command_honours_exact_grade_and_does_not_write_a_mismatch(tmp_path, capsys):
    output = tmp_path / "candidate.txt"
    args = [
        "fresh",
        "calcudoku",
        "--size",
        "4",
        "--tier",
        "easy",
        "--seed",
        "13504",
        "--attempts",
        "2",
        "--output",
        str(output),
    ]
    assert main([*args, "--grade", "relations"]) == 0
    assert rate(output.read_text()).grade == "relations"
    assert "wrote" in capsys.readouterr().out
    output.unlink()
    assert main([*args, "--grade", "chains"]) == 1
    assert not output.exists()
    assert "no unique" in capsys.readouterr().err


def test_seed_command_honours_grade_and_never_adds_singleton_hints(tmp_path, capsys):
    source = example("calcudoku_1_4x4.txt")
    output = tmp_path / "candidate.txt"
    args = [
        "generate",
        str(source),
        "--tier",
        "easy",
        "--seed",
        "13501",
        "--attempts",
        "40",
        "--output",
        str(output),
    ]
    assert main([*args, "--grade", "relations"]) == 0
    result = rate(output.read_text())
    assert (result.tier, result.grade, result.solutions) == ("easy", "relations", "unique")
    assert all(len(cage.cells) >= 2 for cage in calcudoku.parse(output.read_text()).cages)
    assert "wrote" in capsys.readouterr().out
    output.unlink()
    assert main([*args, "--grade", "chains"]) == 1
    assert not output.exists()
    assert "chains" in capsys.readouterr().err
