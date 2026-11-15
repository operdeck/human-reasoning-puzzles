"""macOS Vision OCR, used by `scan.ocr` when the pyobjc bindings are installed.

Kept apart so that importing `scan` works on every platform: this module raises
`ImportError` off a Mac, which `scan.ocr` treats as "try the next backend".
"""

from __future__ import annotations

from typing import Any


def recognise(path: str) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Text lines with normalised boxes, origin at the bottom left (Vision's own)."""
    import Foundation
    import Vision

    url = Foundation.NSURL.fileURLWithPath_(path)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(0)  # accurate
    request.setUsesLanguageCorrection_(True)
    request.setRecognitionLanguages_(["nl-NL", "en-US"])
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Vision could not read {path}: {error}")

    lines: list[tuple[str, tuple[float, float, float, float]]] = []
    for observation in request.results() or []:
        candidates: Any = observation.topCandidates_(1)
        if not len(candidates):
            continue
        text = str(candidates.objectAtIndex_(0).string())
        box = observation.boundingBox()
        origin, size = box.origin, box.size
        lines.append(
            (
                text,
                (
                    float(origin.x),
                    float(origin.y),
                    float(origin.x + size.width),
                    float(origin.y + size.height),
                ),
            )
        )
    return lines
