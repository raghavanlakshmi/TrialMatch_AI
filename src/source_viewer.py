"""Render source documents for human review, with the supporting quote highlighted."""

from __future__ import annotations

from dataclasses import dataclass
import html
from pathlib import Path
import re

import pymupdf

from .evidence_view import source_file_path
from .schemas import DocumentPage


@dataclass
class SourceView:
    """What the reviewer sees for one cited source page."""

    filename: str
    page_number: int
    kind: str  # "pdf", "image", "text" or "missing"
    image: bytes | None = None
    quote_highlighted_on_image: bool = False
    transcription: str | None = None
    extraction_method: str | None = None


def _quote_pattern(quote: str) -> re.Pattern | None:
    words = quote.split()
    if not words:
        return None
    return re.compile(r"\s+".join(re.escape(word) for word in words), re.IGNORECASE)


def highlight_html(text: str, quote: str | None) -> str:
    """Escape untrusted source text, then mark the verified quote. Safe for st.markdown(unsafe_allow_html)."""
    pattern = _quote_pattern(quote or "")
    if pattern is None:
        return html.escape(text)
    pieces, last = [], 0
    for match in pattern.finditer(text):
        pieces.append(html.escape(text[last:match.start()]))
        pieces.append(f"<mark>{html.escape(match.group(0))}</mark>")
        last = match.end()
    pieces.append(html.escape(text[last:]))
    return "".join(pieces)


def render_pdf_page(path: Path, page_number: int, quote: str | None = None, zoom: float = 2.0) -> tuple[bytes, bool]:
    """Render one PDF page to PNG in memory; highlight the quote when PyMuPDF can locate it."""
    with pymupdf.open(path) as document:
        if not 1 <= page_number <= document.page_count:
            raise ValueError(f"{path.name} has no page {page_number}.")
        page = document[page_number - 1]
        found = False
        if quote:
            # Quotes may wrap across lines; fall back to highlighting each non-empty line.
            candidates = [quote] + [line.strip() for line in quote.splitlines() if line.strip()]
            for candidate in candidates:
                rects = page.search_for(candidate)
                for rect in rects:
                    page.add_highlight_annot(rect)
                if rects:
                    found = True
                    break
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True)
        return pixmap.tobytes("png"), found


def pdf_page_count(path: Path) -> int:
    with pymupdf.open(path) as document:
        return document.page_count


def build_source_view(patient_dir: Path, pages: list[DocumentPage], filename: str, page_number: int, quote: str | None = None) -> SourceView:
    """Combine the original file (when available) with the saved page transcription."""
    page = next((p for p in pages if p.filename == filename and p.page_number == page_number), None)
    transcription = page.text if page else None
    method = page.extraction_method if page else None
    path = source_file_path(patient_dir, filename)
    if path is None:
        return SourceView(filename, page_number, "missing" if transcription is None else "text", transcription=transcription, extraction_method=method)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        image, found = render_pdf_page(path, page_number, quote)
        return SourceView(filename, page_number, "pdf", image, found, transcription, method)
    if suffix in {".png", ".jpg", ".jpeg"}:
        return SourceView(filename, page_number, "image", path.read_bytes(), False, transcription, method)
    text = transcription if transcription is not None else path.read_text(encoding="utf-8", errors="replace")
    return SourceView(filename, page_number, "text", transcription=text, extraction_method=method)
