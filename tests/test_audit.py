from pathlib import Path

from csp import audit
from csp.puzzle_lab import main
from tests.examples import example

BINAIRO = """Family: binairo
Size: 4
Givens:
0 0 . .
. 1 0 .
. . . .
1 1 . .
"""
# The same board turned a quarter: still the same puzzle.
BINAIRO_TURNED = """Family: binairo
Size: 4
Givens:
1 . . 0
1 . 1 0
. . 0 .
. . . .
"""


def _write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text)
    return path


def test_turned_copy_shares_a_solution(tmp_path):
    first = _write(tmp_path, "binairo_a.txt", BINAIRO)
    turned = _write(tmp_path, "binairo_b.txt", BINAIRO_TURNED)
    assert audit.solution_key(first.read_text(), "binairo") == audit.solution_key(
        turned.read_text(), "binairo"
    )
    found = audit.audit(audit.profiles([first, turned]))
    assert found.shared_solutions == [[first, turned]]


def test_relabelled_regions_share_a_layout():
    text = example("queens_4x4_easy.txt").read_text()
    relabelled = text.replace("a a a b", "z z z y").replace("a b b b", "z y y y")
    assert audit.layout_key(text, "queens") == audit.layout_key(relabelled, "queens")


def test_same_placement_on_another_region_map_is_a_different_solution():
    text = example("queens_4x4_easy.txt").read_text()
    other = text.replace("a a a b\na b b b", "a a b b\na a b b")
    assert audit.solution_key(text, "queens") != audit.solution_key(other, "queens")


def _profile(name: str, tier: str, grade: str, category: str | None = None) -> audit.Profile:
    return audit.Profile(Path(name), "binairo", "Binairo", category, grade, tier, name, None)


def test_sections_must_run_from_easy_to_hard():
    ordered = [_profile("a.txt", "easy", "single"), _profile("b.txt", "hard", "what_if")]
    assert audit.audit(ordered).clean
    found = audit.audit(list(reversed(ordered)))
    assert list(found.out_of_order) == ["Binairo"]


def test_grade_breaks_ties_within_a_tier():
    found = audit.audit(
        [_profile("a.txt", "medium", "cover2"), _profile("b.txt", "medium", "relations")]
    )
    assert "Binairo" in found.out_of_order


def test_series_with_a_fixed_story_order_is_not_reordered():
    category = next(iter(audit.FIXED_ORDER))
    found = audit.audit(
        [
            _profile("a.txt", "hard", "what_if", category),
            _profile("b.txt", "easy", "single", category),
        ]
    )
    assert found.clean


def test_audit_command_reports_problems(tmp_path, capsys):
    _write(tmp_path, "binairo_a.txt", BINAIRO)
    _write(tmp_path, "binairo_b.txt", BINAIRO_TURNED)
    assert main(["audit", str(tmp_path)]) == 1
    assert "Shared solution: binairo_a.txt, binairo_b.txt" in capsys.readouterr().out
