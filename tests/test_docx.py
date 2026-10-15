"""The DOCX booklet: presentation text, clue wording and embedded diagrams."""

import zipfile
from pathlib import Path

import pytest

pytest.importorskip("docx")

from docx import Document

from csp.cli import main
from csp.docx_export import write_docx
from csp.puzzlefile import load_presentation
from csp.story import clue_texts

EXAMPLES = Path(__file__).parent.parent / "examples"
PRRRDOKUS = ["prrrdoku1", "prrrdoku2", "prrrdoku3"]


def _text(path: Path) -> str:
    return "\n".join(p.text for p in Document(str(path)).paragraphs)


@pytest.mark.parametrize("name", PRRRDOKUS)
def test_prrrdoku_booklet_has_text_and_diagram(name, tmp_path):
    source = EXAMPLES / f"{name}.txt"
    out = tmp_path / f"{name}.docx"
    assert main([str(source), "--docx", str(out)]) == 0
    text = _text(out)
    assert "Prrrdoku" in text and "Aanwijzingen" in text and "Vladimir" in text
    assert any(n.startswith("word/media/") for n in zipfile.ZipFile(out).namelist())
    solution = _text(tmp_path / f"{name}-solution.docx")
    assert "Oplossing" in solution
    assert (
        len(
            [
                n
                for n in zipfile.ZipFile(tmp_path / f"{name}-solution.docx").namelist()
                if n.startswith("word/media/")
            ]
        )
        == 2
    )


def test_clue_text_override_wins():
    source = (EXAMPLES / "prrrdoku1.txt").read_text()
    assert load_presentation(source).clue_text[5].startswith("Otto zit")


def test_puzzle_without_presentation_still_gets_a_booklet(tmp_path):
    source = EXAMPLES / "food-murdoku-1.txt"
    assert not load_presentation(source.read_text()).title
    out = tmp_path / "food.docx"
    write_docx(source.read_text(), out, source.parent)
    text = _text(out)
    assert "Clues" in text
    assert all(sentence in text for sentence in clue_texts(source.read_text()))


def test_missing_figure_image_falls_back_to_text(tmp_path):
    base = (EXAMPLES / "prrrdoku1.txt").read_text()
    source = base.replace(
        "Figures:\nVladimir: de poes die iemand op schoot zoekt",
        "Figures:\nVladimir: de poes ; image=missing.png",
    )
    out = tmp_path / "x.docx"
    write_docx(source, out, tmp_path)
    assert "Vladimir: de poes" in _text(out)


def test_figure_image_is_embedded(tmp_path):
    from PIL import Image

    Image.new("RGB", (20, 20), "red").save(tmp_path / "v.png")
    source = (
        (EXAMPLES / "prrrdoku1.txt")
        .read_text()
        .replace("Vladimir: de poes die iemand op schoot zoekt", "Vladimir: poes ; image=v.png")
    )
    out = tmp_path / "x.docx"
    write_docx(source, out, tmp_path)
    assert len([n for n in zipfile.ZipFile(out).namelist() if n.startswith("word/media/")]) == 2


def test_bad_presentation_is_rejected_and_linted():
    bad = (EXAMPLES / "prrrdoku1.txt").read_text() + "\nClueText:\n99: nope\n"
    with pytest.raises(ValueError):
        load_presentation(bad)


def test_human_readable_clues():
    got = clue_texts((EXAMPLES / "food-murdoku-3.txt").read_text())
    assert "Gyoza is in column 5." in got
    assert "Gyoza is somewhere above Jos." in got
