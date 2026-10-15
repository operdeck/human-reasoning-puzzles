"""An editable Word booklet page for a Murdoku puzzle file (needs python-docx).

The booklet reads the optional presentation sections of the puzzle file
(`Title:`, `Intro:`, `Question:`, `ClueText:`, `Figures:`, `Reveal:`), draws the
board with `picture` and words the clues with `story`. Nothing here is needed to
solve; a file without presentation sections still gives a usable booklet.
"""

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import icons, picture
from .murdoku import global_count_conditions
from .puzzlefile import Figure, Presentation, load_board, load_presentation
from .story import clue_texts, explain, phrase

BOLD = re.compile(r"\*\*(.+?)\*\*")
BOARD_WIDTH_CM = 9.0
FIGURE_IMAGE_CM = 0.8


def _runs(paragraph: Any, text: str) -> None:
    """Add `text` to a paragraph, turning **bold** markers into bold runs."""
    position = 0
    for match in BOLD.finditer(text):
        paragraph.add_run(text[position : match.start()])
        paragraph.add_run(match[1]).bold = True
        position = match.end()
    paragraph.add_run(text[position:])


def _picture_stream(
    text: str,
    solution: dict[str, Any] | None,
    role_statuses: dict[tuple[str, str], bool | None] | None,
) -> io.BytesIO:
    board, clues = load_board(text)
    image = picture.murdoku_picture(
        board,
        solution,
        role_statuses=role_statuses,
        global_counts=global_count_conditions(board, clues),
    )
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return stream


def _figure_image(person: str, figure: Figure | None, source: Path) -> Path | None:
    """The thumbnail for a person: the `image=` file, a file in `<stem>-figures/` or
    `figures/` beside the puzzle named after the person, or the built-in `icon=`."""
    base = source.parent
    if figure is not None and figure.image and (base / figure.image).is_file():
        return base / figure.image
    for folder in (base / f"{source.stem}-figures", base / "figures"):
        for suffix in (".png", ".jpg", ".jpeg"):
            if (folder / f"{person}{suffix}").is_file():
                return folder / f"{person}{suffix}"
    if figure is not None and figure.icon:
        return icons.icon(figure.icon)
    return None


def _figures(document: Any, text: str, presentation: Presentation, source: Path) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    board, _ = load_board(text)
    figures = presentation.figures
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for number, person in enumerate(board.people):
        if number:
            paragraph.add_run("; " if figures else " · ")
        figure = figures.get(person)
        image = _figure_image(person, figure, source)
        if image is not None:
            paragraph.add_run().add_picture(str(image), height=Cm(FIGURE_IMAGE_CM))
            paragraph.add_run(" ")
        paragraph.add_run(person).bold = bool(figures)
        if figure is not None and figure.description:
            paragraph.add_run(f": {figure.description}")


@dataclass(frozen=True)
class Entry:
    """One puzzle of a booklet; `solution` makes its page a worked solution."""

    text: str
    path: Path
    solution: dict[str, Any] | None = None
    role_statuses: dict[tuple[str, str], bool | None] | None = None


def _add_puzzle(document: Any, entry: Entry, new_page: bool) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    text = entry.text
    presentation = load_presentation(text)
    first_comment = next((line for line in text.splitlines() if line.startswith("# ")), "")
    title = presentation.title or first_comment.removeprefix("# ").strip() or entry.path.stem
    heading = document.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.page_break_before = new_page
    document.add_heading(phrase(text, "doc.rules_title"), level=2)
    for line in presentation.intro or [phrase(text, "doc.rules")]:
        _runs(document.add_paragraph(style="List Bullet"), line)
    document.add_picture(_picture_stream(text, None, None), width=Cm(BOARD_WIDTH_CM))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    _figures(document, text, presentation, entry.path)

    document.add_heading(phrase(text, "doc.clues"), level=2)
    for number, generated in enumerate(clue_texts(text), 1):
        wording = presentation.clue_text.get(number, generated)
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.8)
        paragraph.paragraph_format.first_line_indent = Cm(-0.8)
        paragraph.paragraph_format.space_after = Pt(1)
        paragraph.add_run(f"{number}.\t")
        _runs(paragraph, wording)
    if presentation.question:
        _centred(document, presentation.question)


def _add_solution(document: Any, entry: Entry, title: str) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    text = entry.text
    presentation = load_presentation(text)
    heading = document.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.page_break_before = True
    document.add_picture(
        _picture_stream(text, entry.solution, entry.role_statuses), width=Cm(BOARD_WIDTH_CM)
    )
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_heading(phrase(text, "doc.how"), level=2)
    for block in explain(text).split("\n\n"):
        if block.strip():
            _runs(document.add_paragraph(style="List Bullet"), block.strip().removeprefix("- "))
    for line in presentation.reveal:
        _centred(document, line)


def _centred(document: Any, text: str) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _runs(paragraph, text)
    for run in paragraph.runs:
        run.bold = True


def _compact(document: Any) -> None:
    """Small margins and text so a puzzle, and its solution, each fit on one page."""
    from docx.shared import Cm, Pt

    for section in document.sections:
        section.top_margin = section.bottom_margin = Cm(1.4)
        section.left_margin = section.right_margin = Cm(1.8)
    normal = document.styles["Normal"]
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(3)
    for name in ("List Number", "List Bullet"):
        document.styles[name].paragraph_format.space_after = Pt(1)


def write_booklet(entries: list[Entry], path: Path) -> None:
    """Write one document: every puzzle on its own page, then the solved ones' solutions.

    A figure image path is relative to its puzzle file; a missing image is skipped,
    leaving the text-only entry. Raises ImportError without python-docx.
    """
    from docx import Document

    document = Document()
    _compact(document)
    for number, entry in enumerate(entries):
        _add_puzzle(document, entry, new_page=number > 0)
    solved = [entry for entry in entries if entry.solution is not None]
    if solved:
        for entry in solved:
            title = load_presentation(entry.text).title or entry.path.stem
            _add_solution(document, entry, f"{phrase(entry.text, 'doc.solution')}: {title}")
    document.save(str(path))
