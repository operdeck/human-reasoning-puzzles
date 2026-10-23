import pytest

from csp import bruteforce, cli, queens, report
from csp.bruteforce import queens as brute
from csp.core import Kind, Solver
from csp.queens import DOG_MARK, PUPPY_MARK, QUEEN_MARK, Cell, compile_puzzle, render
from tests.examples import example

EXAMPLE = example("queens_4x4.txt")

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


def test_zones_may_differ_in_size_but_must_be_connected():
    sizes = "Family: queens\nSize: 3\nRegions:\na: x\nb: y\nc: z\nGrid:\na b b\nb b c\nb c c\n"
    puzzle = queens.parse(sizes)
    assert sorted(len(cells) for cells in puzzle.cells_by_region.values()) == [1, 3, 5]

    split = sizes.replace("a b b\nb b c\nb c c", "a b a\nb b c\nc c c")
    with pytest.raises(ValueError, match="connected"):
        queens.parse(split)


def test_the_first_deduction_places_a_one_cell_zone():
    text = (example("dogdoku_5x5.txt")).read_text()
    puzzle = queens.parse(text)
    lone = {region for region, cells in puzzle.cells_by_region.items() if len(cells) == 1}
    assert lone
    model, _ = compile_puzzle(text)
    steps = []
    Solver(model).solve(on_step=lambda rule, fired: steps.append((rule, fired)))
    rule, fired = steps[0]
    assert rule == "single"
    assert {step.var for step in fired} & lone


def test_queens_default_icon_is_a_queen_and_dogdoku_defaults_to_a_dog():
    base = EXAMPLE.read_text()
    assert queens.parse(base).icon == "queen"
    dog = base.replace("Family: queens", "Family: dogdoku")
    assert queens.parse(dog).icon == "dog"
    assert cli.detect(dog) == "queens"


@pytest.mark.parametrize(
    "icon, mark", [("queen", QUEEN_MARK), ("dog", DOG_MARK), ("puppy", PUPPY_MARK)]
)
def test_icon_section_picks_the_mark_in_the_text_board(icon, mark):
    text = EXAMPLE.read_text().replace("Family: queens", f"Family: queens\nIcon: {icon}")
    model, puzzle = compile_puzzle(text)
    Solver(model).solve()
    assert puzzle.icon == icon
    assert mark in render(puzzle, model, "Solved")


def test_unknown_icon_is_rejected():
    text = EXAMPLE.read_text().replace("Family: queens", "Family: queens\nIcon: cat")
    with pytest.raises(ValueError, match="Icon must be one of"):
        queens.parse(text)


def test_dogdoku_examples_are_unique_and_get_harder():
    ladder = ["single", "subsumption", "cover2"]
    grades = []
    for name in ("dogdoku_5x5", "dogdoku_7x7", "dogdoku_9x9"):
        text = (example(f"{name}.txt")).read_text()
        puzzle = queens.parse(text)
        assert len(brute.solutions(text)) == 1
        assert len(set(puzzle.region_names.values())) == puzzle.size
        model, _ = compile_puzzle(text)
        fired: list[str] = []
        result = Solver(model).solve(on_step=lambda rule, steps, log=fired: log.append(rule))
        assert result.solved
        assert "what_if" not in fired and "chains" not in fired  # eliminations only
        grades.append(report.grade(fired))
    assert grades == ladder
