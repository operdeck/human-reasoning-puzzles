"""The DOCX booklet: presentation text, clue wording and embedded diagrams."""

import zipfile
from pathlib import Path

import pytest

pytest.importorskip("docx")

from docx import Document

from csp.cli import main
from csp.docx_export import Entry, write_booklet
from csp.puzzlefile import load_presentation
from csp.story import clue_texts

EXAMPLES = Path(__file__).parent.parent / "examples"
PRRRDOKUS = ["prrrdoku1", "prrrdoku2", "prrrdoku3"]


def write_docx(text, out, base, solution=None):
    write_booklet([Entry(text, base / "x.txt", solution)], out)


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
    assert "Oplossing" in text
    media = [n for n in zipfile.ZipFile(out).namelist() if n.startswith("word/media/")]
    assert len(media) == 2
    assert text.index("Aanwijzingen") < text.index("Oplossing")


def test_clue_text_override_wins():
    source = (EXAMPLES / "prrrdoku1.txt").read_text()
    assert load_presentation(source).clue_text[5].startswith("Otto zit")


def test_puzzle_without_presentation_still_gets_a_booklet(tmp_path):
    source = EXAMPLES / "murdoku_house.txt"
    plain = source.read_text().split("# Booklet text")[0]
    assert not load_presentation(plain).title
    out = tmp_path / "plain.docx"
    write_docx(plain, out, source.parent)
    text = _text(out)
    assert "Clues" in text
    assert all(sentence in text for sentence in clue_texts(plain))


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
    bad = (EXAMPLES / "prrrdoku1.txt").read_text() + "\nFigures:\nNobody: x\n"
    with pytest.raises(ValueError):
        load_presentation(bad)


def test_human_readable_clues():
    got = clue_texts((EXAMPLES / "food-murdoku-3.txt").read_text())
    assert "Okonomiyaki is in column 1." in got
    assert any("somewhere above" in clue for clue in got)


def test_glob_makes_one_multi_puzzle_booklet(tmp_path):
    for name in PRRRDOKUS[:2]:
        (tmp_path / f"{name}.txt").write_text((EXAMPLES / f"{name}.txt").read_text())
    out = tmp_path / "all.docx"
    assert main([str(tmp_path / "prrrdoku*.txt"), "--docx", str(out)]) == 0
    text = _text(out)
    assert "Prrrdoku 1" in text and "Prrrdoku 2" in text
    assert text.count("Aanwijzingen") == 2 and "Oplossing" in text
    assert text.rindex("Prrrdoku 1") > text.index("Oplossing")
    assert not (tmp_path / "all-solution.docx").exists()


def test_inline_wording_does_not_change_the_puzzle():
    from csp.puzzlefile import load_board

    plain = (
        (EXAMPLES / "prrrdoku1.txt")
        .read_text()
        .replace(" | Otto zit precies één rij boven Tjitske.", "")
    )
    assert load_board(plain) == load_board((EXAMPLES / "prrrdoku1.txt").read_text())


def _media(path):
    return [n for n in zipfile.ZipFile(path).namelist() if n.startswith("word/media/")]


def test_figures_folder_gives_thumbnails_by_name(tmp_path):
    from PIL import Image

    text = (EXAMPLES / "tamagotchi-murdoku-6x6.txt").read_text()
    (tmp_path / "t.txt").write_text(text)
    folder = tmp_path / "t-figures"
    folder.mkdir()
    Image.new("RGB", (20, 20), "green").save(folder / "Mametchi.png")
    out = tmp_path / "x.docx"
    write_booklet([Entry(text, tmp_path / "t.txt")], out)
    assert len(_media(out)) == 7  # board + six figures


def test_icon_figures_use_builtin_icons(tmp_path, monkeypatch):
    from PIL import Image

    cache = tmp_path / "cache"
    monkeypatch.setenv("CSP_ICON_CACHE", str(cache))
    from csp import icons

    for code in ("1f35c", "1f362", "1f356", "1f364", "1f9d1"):
        (icons.cache_dir()).mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), "red").save(icons.cache_dir() / f"{code}.png")
    text = (EXAMPLES / "food-murdoku-1.txt").read_text()
    out = tmp_path / "x.docx"
    write_booklet([Entry(text, EXAMPLES / "food-murdoku-1.txt")], out)
    assert len(_media(out)) >= 2


def test_unknown_icon_is_linted(tmp_path, capsys):
    text = (EXAMPLES / "food-murdoku-1.txt").read_text().replace("U+1F35C", "nonsense")
    (tmp_path / "f.txt").write_text(text)
    main([str(tmp_path / "f.txt"), "--lint"])
    assert "unknown icon nonsense" in capsys.readouterr().out
