"""Quality checks on the published example collection."""

import functools
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pytest

from csp import audit, calcudoku, starbattle
from csp.collection import arrange
from csp.murdoku_expression_file import load_expression_board
from csp.murdoku_lang import format_statement
from csp.puzzle_lab import Rating, family_of, rate
from csp.puzzlefile import detect, display_family
from tests.examples import example, played_examples

pytestmark = pytest.mark.solutions

QUEENS_FILES = [
    path
    for path in played_examples()
    if detect(path.read_text()) == "starbattle" and family_of(path.read_text()) == "queens"
]
CALCUDOKU_FILES = [path for path in played_examples() if detect(path.read_text()) == "calcudoku"]


@pytest.mark.parametrize(
    ("size", "marks"),
    [
        (6, {"quiet": "alone"}),
        (9, {"social": "not_alone"}),
        (12, {"quiet": "alone", "social": "not_alone"}),
    ],
)
def test_tamagotchi_series_uses_its_marks_with_at_most_one_count_clue(size, marks):
    board, _rules, clues = load_expression_board(
        example(f"tamagotchi-murdoku-{size}x{size}.txt").read_text()
    )
    assert {mark.name: mark.occupant_condition for mark in board.marks} == marks
    counts = [
        clue
        for clue in clues
        if re.search(r"\bcount\b|\bdir:\w+ \d|\b\d+\s*(?:<|>|=)", format_statement(clue))
    ]
    assert len(counts) <= 1


@pytest.mark.parametrize("path", CALCUDOKU_FILES, ids=lambda path: path.name)
def test_calcudoku_examples_have_no_single_cell_cages(path):
    assert all(len(cage.cells) >= 2 for cage in calcudoku.parse(path.read_text()).cages)


@pytest.mark.parametrize(
    "relative",
    (
        "README.md",
        "docs/puzzle-collection.md",
        "docs/model-and-puzzle-formats.md",
        "docs/cli.md",
        "docs/murdoku-grammar.md",
        "docs/web-interface.md",
        "docs/discoverability.md",
    ),
)
def test_documentation_links_and_images_exist(relative):
    source = Path(__file__).resolve().parents[1] / relative
    targets = re.findall(r'\[[^\]]*\]\(([^)]+)\)|(?:href|src)="([^"]+)"', source.read_text())
    for markdown, html in targets:
        target = (markdown or html).split("#", 1)[0]
        if target and "://" not in target:
            assert (source.parent / target).exists(), f"{relative}: {target}"


def _section_anchor(label: str) -> str:
    # Mirrors web/src/sections.mjs.
    text = "".join(c for c in unicodedata.normalize("NFKD", label) if not unicodedata.combining(c))
    return "family-" + re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def test_readme_gallery_links_open_existing_web_index_sections():
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text()
    site = r'href="https://operdeck\.github\.io/human-reasoning-puzzles/#([\w-]+)"'
    anchors = re.findall(site, readme)
    assert anchors
    paths = sorted((root / "examples").rglob("*.txt"))
    kinds = {path: detect(path.read_text()) for path in paths}
    names = {path: display_family(path.read_text(), kind) for path, kind in kinds.items()}
    sections = {_section_anchor(listed.section) for listed in arrange(kinds, names)}
    assert set(anchors) <= sections, sorted(set(anchors) - sections)


def test_documentation_and_skills_use_the_web_index_instead_of_the_retired_gallery():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "docs" / "examples.md").exists()
    sources = [root / "README.md", root / "AGENT.md"]
    sources.extend((root / "docs").glob("*.md"))
    sources.extend((root / ".github" / "skills").rglob("*.md"))
    for source in sources:
        assert "examples.md" not in source.read_text(), str(source.relative_to(root))


def test_agent_entrypoints_share_one_repository_guide():
    root = Path(__file__).resolve().parents[1]
    pointer = "Read and follow `AGENT.md`."
    # Every entrypoint points at the one guide. `.clinerules` opens with the
    # pointer and may add local shell-hygiene notes after it; the others are the
    # bare pointer.
    assert (root / ".clinerules").read_text().splitlines()[0].strip() == pointer
    assert (root / ".github/copilot-instructions.md").read_text().strip() == pointer
    assert (root / "CLAUDE.md").read_text().strip() == "@AGENT.md"


def test_the_documented_example_count_matches_the_collection():
    """The frontier sentences quote how many of how many puzzles need `what_if`: keep both true."""
    from tests.test_web import BEYOND_DEDUCTION

    root = Path(__file__).resolve().parents[1]
    for relative in ("docs/puzzle-collection.md", "RELEASE_NOTES.md"):
        source = root / relative
        quoted = re.findall(r"(\d+) of the (\d+) published", source.read_text())
        assert quoted, f"{relative} no longer quotes the frontier count"
        assert {(int(some), int(total)) for some, total in quoted} == {
            (len(BEYOND_DEDUCTION), len(played_examples()))
        }


@pytest.mark.parametrize("path", QUEENS_FILES, ids=lambda path: path.name)
def test_queens_examples_use_the_piece_of_their_family(path):
    text = path.read_text()
    puzzle = starbattle.parse(text)
    assert puzzle.icon == "queen"
    assert all(len(cells) >= 2 for cells in puzzle.areas.cells_by_region.values())
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


@pytest.mark.parametrize("category", ["japan", "wie-doet-het-met-wie"])
def test_murdoku_series_run_from_easy_to_hard(category):
    members = audit.profiles(path for path in played_examples() if path.parent.name == category)
    assert members, category
    assert not audit.audit(members).out_of_order, [
        (member.path.name, member.grade) for member in members
    ]


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
