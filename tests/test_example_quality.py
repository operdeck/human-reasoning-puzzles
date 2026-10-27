"""Quality checks on the published example collection."""

import functools
import re
from collections import defaultdict
from pathlib import Path

import pytest

from csp import audit, queens
from csp.collection import arrange
from csp.puzzle_lab import Rating, family_of, rate
from csp.puzzlefile import detect
from tests.examples import played_examples

QUEENS_FILES = [path for path in played_examples() if detect(path.read_text()) == "queens"]


@pytest.mark.parametrize("path", QUEENS_FILES, ids=lambda path: path.name)
def test_queens_examples_use_the_piece_of_their_family(path):
    text = path.read_text()
    allowed = {"dog", "puppy"} if family_of(text) == "dogdoku" else {"queen"}
    assert queens.parse(text).icon in allowed
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
