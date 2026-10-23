"""Turn a .docx booklet into a PDF with an installed office program.

Python cannot lay out a Word document itself, so this asks LibreOffice (any platform), or on
macOS Microsoft Word or Pages, to open the document and save it as PDF. Word and LibreOffice
fill in the contents page numbers; Pages keeps the placeholders.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_S = 600
_LIBREOFFICE_APP = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")

_WORD_SCRIPT = """
on run {source, target}
    tell application "Microsoft Word"
        open (POSIX file source)
        set theDocument to active document
        repeat with theField in (get fields of theDocument)
            update field theField
        end repeat
        save as theDocument file name target file format format PDF
        close theDocument saving no
    end tell
end run
"""

_PAGES_SCRIPT = """
on run {source, target}
    tell application "Pages"
        set theDocument to open (POSIX file source)
        export theDocument to (POSIX file target) as PDF
        close theDocument saving no
    end tell
end run
"""


class ConversionError(RuntimeError):
    pass


def _libreoffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        if found := shutil.which(name):
            return found
    return str(_LIBREOFFICE_APP) if _LIBREOFFICE_APP.exists() else None


def _mac_app(name: str) -> bool:
    if sys.platform != "darwin":
        return False
    for folder in (Path("/Applications"), Path.home() / "Applications"):
        if (folder / f"{name}.app").exists():
            return True
    found = subprocess.run(
        ["mdfind", f"kMDItemFSName == '{name}.app'"], capture_output=True, text=True
    )
    return bool(found.stdout.strip())


def converters() -> list[str]:
    """The installed programs that can convert, in the order they are tried."""
    found = []
    if _libreoffice():
        found.append("LibreOffice")
    if _mac_app("Microsoft Word"):
        found.append("Microsoft Word")
    if _mac_app("Pages"):
        found.append("Pages")
    return found


def _run(command: list[str]) -> None:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"{command[0]} took longer than {TIMEOUT_S} s") from exc
    if done.returncode != 0:
        raise ConversionError((done.stderr or done.stdout).strip() or f"exit {done.returncode}")


def _convert_with(program: str, source: Path, target: Path) -> None:
    if program == "LibreOffice":
        office = _libreoffice()
        assert office is not None
        with tempfile.TemporaryDirectory() as folder:
            _run([office, "--headless", "--convert-to", "pdf", "--outdir", folder, str(source)])
            shutil.move(Path(folder) / f"{source.stem}.pdf", target)
        return
    script = _WORD_SCRIPT if program == "Microsoft Word" else _PAGES_SCRIPT
    _run(["osascript", "-e", script, str(source), str(target)])


def docx_to_pdf(source: Path, target: Path) -> str:
    """Convert `source` to `target` with the first program that works; return its name."""
    source, target = source.resolve(), target.resolve()
    programs = converters()
    if not programs:
        raise ConversionError(
            "no program to make a PDF: install LibreOffice, or on macOS Microsoft Word or Pages"
        )
    failures = []
    for program in programs:
        target.unlink(missing_ok=True)
        try:
            _convert_with(program, source, target)
        except (ConversionError, OSError) as exc:
            failures.append(f"{program}: {exc}")
            continue
        if target.exists():
            return program
        failures.append(f"{program}: wrote no PDF")
    raise ConversionError("; ".join(failures))
