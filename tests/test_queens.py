from pathlib import Path

from csp import bruteforce, cli
from csp.bruteforce import queens as brute
from csp.core import Kind, Solver
from csp.queens import QUEEN_MARK, Cell, compile_puzzle, render

EXAMPLE = Path(__file__).parent.parent / "examples" / "queens_4x4.txt"

EXPECTED = {
    "a": Cell(0, 1),
    "b": Cell(1, 3),
    "c": Cell(2, 0),
    "d": Cell(3, 2),
}


def test_queens_model_uses_only_generic_constraints():
    model, puzzle = compile_puzzle(EXAMPLE.read_text())

    assert puzzle.size == 4
    assert model.variables == ["a", "b", "c", "d"]
    assert not model.relations
    assert sum(item.family == "one queen per region" for item in model.constraints) == 4
    assert sum(item.family == "one queen per row" for item in model.constraints) == 4
    assert sum(item.family == "one queen per column" for item in model.constraints) == 4
    assert sum(item.family == "queens do not touch" for item in model.constraints) == 9
    assert all(
        item.kind is Kind.AT_MOST_ONE
        for item in model.constraints
        if item.family == "queens do not touch"
    )


def test_queens_brute_force_and_engine_agree_on_unique_placement():
    text = EXAMPLE.read_text()
    (solution,) = brute.solutions(text)
    model, puzzle = compile_puzzle(text)
    result = Solver(model).solve()

    assert solution == EXPECTED
    assert result.solved
    assert result.assignment == solution
    assert QUEEN_MARK in render(puzzle, model, "Solved")


def test_queens_is_detected_and_loaded_through_the_cli():
    text = EXAMPLE.read_text()
    assert cli.detect(text) == "queens"
    assert len(bruteforce.solutions(text)) == 1
    assert cli.load(text, "queens").model.variables == ["a", "b", "c", "d"]


def test_queens_cli_png_writes_a_picture(tmp_path):
    import pytest

    pytest.importorskip("PIL")
    path = tmp_path / "queens.png"
    assert cli.write_picture("queens", EXAMPLE.read_text(), path)
    assert path.is_file()
