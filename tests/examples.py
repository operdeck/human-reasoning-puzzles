"""Find the example puzzles: `examples/` (sorted into category folders) and the
test-only puzzles in `tests/puzzles/`."""

from pathlib import Path

EXAMPLES = Path(__file__).parent.parent / "examples"
TEST_PUZZLES = Path(__file__).parent / "puzzles"


def example(name: str) -> Path:
    """The puzzle file called `name`, wherever it is filed."""
    found = [*EXAMPLES.rglob(name), *TEST_PUZZLES.glob(name)]
    if len(found) != 1:
        raise FileNotFoundError(f"{name}: {len(found)} matches")
    return found[0]


def played_examples() -> list[Path]:
    """The puzzles published in the booklet and the web player."""
    return sorted(EXAMPLES.rglob("*.txt"), key=lambda path: path.name)


def all_examples() -> list[Path]:
    """Every puzzle file, the test-only ones included."""
    return played_examples() + sorted(TEST_PUZZLES.glob("*.txt"))
