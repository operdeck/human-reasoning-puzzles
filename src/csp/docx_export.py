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
from .puzzlefile import Figure, Presentation, load_board, load_presentation
from .story import clue_paragraphs, explain, phrase

BOLD = re.compile(r"\*\*(.+?)\*\*")
BOARD_WIDTH_CM = 9.0
MIN_BOARD_WIDTH_CM = 3.8
PAGE_BODY_CM = 26.0
FIXED_CM = 7.5
CLUE_LINE_CM = 0.5
SMALL_CLUE_LINE_CM = 0.4
MANY_CLUES = 18
CLUE_LINE_CHARS = 105
MANY_SOLUTION_LINES = 30
SOLUTION_MIN_BOARD_CM = 5.0
FIGURE_LINE_CM = 1.2
FIGURE_IMAGE_CM = 0.8
GENERIC_BOARD_WIDTH_CM = 14.0


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
) -> tuple[io.BytesIO, float]:
    """The board picture and its height/width ratio."""
    board, _ = load_board(text)
    image = picture.murdoku_picture(board, solution, show_roles=False)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return stream, image.height / image.width


def _puzzle_board_width(aspect: float, clue_count: int, figure_lines: int) -> float:
    """Board width in cm, shrunk so a long clue list still leaves the page whole."""
    free = (
        PAGE_BODY_CM
        - FIXED_CM
        - (CLUE_LINE_CM if clue_count <= MANY_CLUES else SMALL_CLUE_LINE_CM) * clue_count
        - FIGURE_LINE_CM * figure_lines
    )
    return max(MIN_BOARD_WIDTH_CM, min(BOARD_WIDTH_CM, free / aspect))


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
    kind: str = "murdoku"
    puzzle_image: Any = None
    solution_image: Any = None


RULES = {
    "sudoku": "Fill the grid so every row, column and box contains each digit once.",
    "calcudoku": "Fill the grid so no digit repeats in a row or column, and each cage's "
    "digits combine to its target with its operation.",
    "futoshiki": "Fill the grid so no digit repeats in a row or column and every "
    "inequality sign between neighbouring cells holds.",
    "queens": "Place one queen in every row, column and region; queens may not touch, "
    "not even diagonally.",
    "suguru": "Fill every region of n cells with 1..n; equal digits may not touch, "
    "not even diagonally.",
    "starbattle": "Place stars so each row, column and region holds the same number; "
    "stars may not touch, not even diagonally.",
    "binairo": "Fill the grid with two symbols: no three equal in a row or column, "
    "each row and column has equally many of each, and no two rows or columns are identical.",
    "tents": "Put a tent next to each tree (horizontally or vertically), one tent per tree; "
    "tents never touch each other, and the numbers give the tents per row and column.",
    "minesweeper": "Mark the mines: each number tells how many of its eight neighbours are mines.",
    "akari": "Place lights so every white cell is lit and no two lights see each other; "
    "a number tells how many lights touch that black cell.",
    "kakurasu": "Shade cells so each row and column adds up to its target, where a "
    "shaded cell counts its position number.",
    "battleships": "Place the fleet without ships touching, even diagonally; the numbers "
    "give the ship cells per row and column.",
    "logicgrid": "Use the clues to match every item of each category with exactly one "
    "item of every other category.",
}


def _generic_title(entry: Entry) -> str:
    return load_presentation(entry.text).title or entry.path.stem.replace("_", " ").capitalize()


def _add_generic(document: Any, entry: Entry, title: str, new_page: bool, solved: bool) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    heading = document.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.page_break_before = new_page
    if not solved:
        document.add_heading("Rules", level=2)
        document.add_paragraph(RULES.get(entry.kind, ""), style="List Bullet")
    stream = io.BytesIO()
    (entry.solution_image if solved else entry.puzzle_image).save(stream, format="PNG")
    stream.seek(0)
    document.add_picture(stream, width=Cm(GENERIC_BOARD_WIDTH_CM))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER


def _add_puzzle(document: Any, entry: Entry, new_page: bool) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    if entry.kind != "murdoku":
        _add_generic(document, entry, _generic_title(entry), new_page, solved=False)
        return
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
    clues = clue_paragraphs(text, presentation.clue_text)
    stream, aspect = _picture_stream(text, None, None)
    figure_lines = 2 if presentation.figures else 1
    clue_lines = sum(-(-len(clue) // CLUE_LINE_CHARS) for clue in clues)
    width = _puzzle_board_width(aspect, clue_lines, figure_lines)
    document.add_picture(stream, width=Cm(width))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    _figures(document, text, presentation, entry.path)

    document.add_heading(phrase(text, "doc.clues"), level=2)
    for clue in clues:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        _runs(paragraph, clue)
        if clue_lines > MANY_CLUES:
            for run in paragraph.runs:
                run.font.size = Pt(9)
    if presentation.question:
        _centred(document, presentation.question)


def _add_solution(document: Any, entry: Entry, title: str) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    if entry.kind != "murdoku":
        _add_generic(document, entry, title, True, solved=True)
        return
    text = entry.text
    presentation = load_presentation(text)
    heading = document.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.page_break_before = True
    stream, aspect = _picture_stream(text, entry.solution, entry.role_statuses)
    blocks = [b.strip().removeprefix("- ") for b in explain(text, numbered=False).split("\n\n")]
    blocks = [b for b in blocks if b]
    lines = sum(-(-len(b) // CLUE_LINE_CHARS) for b in blocks)
    small = lines > MANY_SOLUTION_LINES
    width = _puzzle_board_width(aspect, int(lines * (0.8 if small else 1)), 0)
    document.add_picture(stream, width=Cm(max(width, SOLUTION_MIN_BOARD_CM)))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_heading(phrase(text, "doc.how"), level=2)
    for block in blocks:
        paragraph = document.add_paragraph(style="List Bullet")
        _runs(paragraph, block)
        if small:
            for run in paragraph.runs:
                run.font.size = Pt(8)
    for line in presentation.reveal:
        _centred(document, line)


def _centred(document: Any, text: str) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _runs(paragraph, text)
    for run in paragraph.runs:
        run.bold = True


COPYRIGHT_NOTICE = (
    "\u00a9 Otto Perdeck. All rights reserved. No copying, redistribution or other use "
    "of these puzzles without the explicit written permission of the author."
)


def _footer(document: Any) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    for section in document.sections:
        paragraph = section.footer.paragraphs[0]
        paragraph.text = COPYRIGHT_NOTICE
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in paragraph.runs:
            run.font.size = Pt(7)


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
    _footer(document)
    for number, entry in enumerate(entries):
        _add_puzzle(document, entry, new_page=number > 0)
    solved = [entry for entry in entries if entry.solution is not None]
    if solved:
        for entry in solved:
            title = (
                _generic_title(entry)
                if entry.kind != "murdoku"
                else (load_presentation(entry.text).title or entry.path.stem)
            )
            label = "Solution" if entry.kind != "murdoku" else phrase(entry.text, "doc.solution")
            _add_solution(document, entry, f"{label}: {title}")
    document.save(str(path))
