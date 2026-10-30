"""Quality checks on the published example collection."""

import functools
import re
from collections import defaultdict
from pathlib import Path

import pytest

from csp import audit, calcudoku, queens
from csp.collection import arrange
from csp.puzzle_lab import Rating, family_of, rate
from csp.puzzlefile import detect
from tests.examples import played_examples

QUEENS_FILES = [path for path in played_examples() if detect(path.read_text()) == "queens"]
CALCUDOKU_FILES = [path for path in played_examples() if detect(path.read_text()) == "calcudoku"]


@pytest.mark.parametrize("path", CALCUDOKU_FILES, ids=lambda path: path.name)
def test_calcudoku_examples_have_no_single_cell_cages(path):
    assert all(len(cage.cells) >= 2 for cage in calcudoku.parse(path.read_text()).cages)


@pytest.mark.parametrize(
    "relative", ("README.md", "docs/puzzle-collection.md", "docs/model-and-puzzle-formats.md")
)
def test_documentation_links_and_images_exist(relative):
    source = Path(__file__).resolve().parents[1] / relative
    targets = re.findall(r'\[[^\]]*\]\(([^)]+)\)|(?:href|src)="([^"]+)"', source.read_text())
    for markdown, html in targets:
        target = (markdown or html).split("#", 1)[0]
        if target and "://" not in target:
            assert (source.parent / target).exists(), f"{relative}: {target}"


def test_documentation_and_skills_use_the_web_index_instead_of_the_retired_gallery():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "docs" / "examples.md").exists()
    sources = [root / "README.md", root / "AGENT.md"]
    sources.extend((root / "docs").glob("*.md"))
    sources.extend((root / ".github" / "skills").rglob("*.md"))
    for source in sources:
        assert "examples.md" not in source.read_text(), str(source.relative_to(root))


@pytest.mark.parametrize("path", QUEENS_FILES, ids=lambda path: path.name)
def test_queens_examples_use_the_piece_of_their_family(path):
    text = path.read_text()
    puzzle = queens.parse(text)
    assert puzzle.icon == "queen"
    assert all(len(cells) >= 2 for cells in puzzle.cells_by_region.values())
    assert path.name.split("_")[0] == family_of(text)


NON_MURDOKU_FILES = [path for path in played_examples() if detect(path.read_text()) != "murdoku"]


@functools.cache
def _rating(path: Path) -> Rating:
    return rate(path.read_text(), str(path))


@pytest.mark.parametrize("path", NON_MURDOKU_FILES, ids=lambda path: path.name)
def test_examples_leave_enough_to_deduce(path):
    result = _rating(path)
    assert result.solutions == "unique"
    assert result.tier != "trivial", f"{path.name} is prefilled or needs no deduction"


def test_no_two_examples_share_a_solution_or_a_layout():
    found = audit.audit(audit.boards(played_examples()))
    assert not found.shared_solutions, [[p.name for p in group] for group in found.shared_solutions]
    assert not found.shared_layouts, [[p.name for p in group] for group in found.shared_layouts]


def test_each_section_is_numbered_from_easy_to_hard():
    """`<family>_<n>_<size>...`: n counts up through a section, and difficulty never drops."""
    texts = {path: path.read_text() for path in NON_MURDOKU_FILES}
    kinds = {path: detect(text) for path, text in texts.items()}
    sections: dict[str, list[Path]] = defaultdict(list)
    for item in arrange(kinds, {path: family_of(text) for path, text in texts.items()}):
        sections[item.section].append(item.path)
    for name, paths in sections.items():
        numbers = [int(re.match(r"[a-z]+_(\d+)_", path.stem).group(1)) for path in paths]
        assert numbers == list(range(1, len(paths) + 1)), (name, [p.name for p in paths])
        levels = [
            (audit.TIER_ORDER.index(_rating(p).tier), audit.GRADE_ORDER.index(_rating(p).grade))
            for p in paths
        ]
        assert levels == sorted(levels), (name, [p.name for p in paths])
