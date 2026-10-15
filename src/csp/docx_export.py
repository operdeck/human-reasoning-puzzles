"""An editable Word booklet page for a Murdoku puzzle file (needs python-docx).

The booklet reads the optional presentation sections of the puzzle file
(`Title:`, `Intro:`, `Question:`, `ClueText:`, `Figures:`, `Reveal:`), draws the
board with `picture` and words the clues with `story`. Nothing here is needed to
solve; a file without presentation sections still gives a usable booklet.
"""

import io
import re
from pathlib import Path
from typing import Any

from . import picture
from .murdoku import global_count_conditions
from .puzzlefile import Presentation, load_board, load_presentation
from .story import clue_texts, explain, phrase

BOLD = re.compile(r"\*\*(.+?)\*\*")
BOARD_WIDTH_CM = 14.0
FIGURE_IMAGE_CM = 2.0


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


def _figures(document: Any, text: str, presentation: Presentation, base: Path) -> None:
    from docx.shared import Cm

    board, _ = load_board(text)
    document.add_heading(phrase(text, "doc.figures"), level=2)
    for person in board.people:
        figure = presentation.figures.get(person)
        paragraph = document.add_paragraph(style="List Bullet")
        if figure is not None and figure.image:
            path = base / figure.image
            if path.is_file():
                paragraph.add_run().add_picture(str(path), height=Cm(FIGURE_IMAGE_CM))
                paragraph.add_run(" ")
        paragraph.add_run(person).bold = True
        if figure is not None and figure.description:
            paragraph.add_run(f": {figure.description}")


def write_docx(
    text: str,
    path: Path,
    base: Path,
    solution: dict[str, Any] | None = None,
    role_statuses: dict[tuple[str, str], bool | None] | None = None,
) -> None:
    """Write the booklet; with `solution`, it ends with the answer and worked solution.

    `base` is the directory that figure image paths are relative to. A missing figure
    image is skipped, leaving the text-only entry. Raises ImportError without python-docx.
    """
    from docx import Document
    from docx.shared import Cm

    presentation = load_presentation(text)
    first_comment = next((line for line in text.splitlines() if line.startswith("# ")), "")
    title = presentation.title or first_comment.removeprefix("# ").strip() or path.stem

    document = Document()
    document.add_heading(title, level=0)
    for line in presentation.intro or [phrase(text, "doc.rules")]:
        _runs(document.add_paragraph(), line)
    document.add_picture(_picture_stream(text, None, None), width=Cm(BOARD_WIDTH_CM))
    _figures(document, text, presentation, base)

    document.add_heading(phrase(text, "doc.clues"), level=2)
    for number, generated in enumerate(clue_texts(text), 1):
        wording = presentation.clue_text.get(number, generated)
        _runs(document.add_paragraph(style="List Number"), wording)
    if presentation.question:
        document.add_heading(phrase(text, "doc.question"), level=2)
        _runs(document.add_paragraph(), presentation.question)

    if solution is not None:
        document.add_page_break()  # type: ignore[no-untyped-call]
        document.add_heading(phrase(text, "doc.solution"), level=1)
        document.add_picture(
            _picture_stream(text, solution, role_statuses), width=Cm(BOARD_WIDTH_CM)
        )
        if presentation.reveal:
            document.add_heading(phrase(text, "doc.answer"), level=2)
            for line in presentation.reveal:
                _runs(document.add_paragraph(), line)
        for block in explain(text).split("\n\n"):
            if block.strip():
                _runs(document.add_paragraph(), block.strip().removeprefix("- "))
    document.save(str(path))
