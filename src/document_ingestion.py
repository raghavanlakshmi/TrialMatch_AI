"""Load source documents without interpreting or inventing patient facts."""

import logging
from collections.abc import Iterable
from pathlib import Path

import pymupdf
from openai import OpenAI
from PIL import Image

from .ocr import OCRExtractionError, extract_text_from_image, extract_text_from_image_bytes
from .schemas import DocumentPage


LOGGER = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".txt"})
MIN_EXTRACTABLE_TEXT_CHARACTERS = 30


class DocumentIngestionError(ValueError):
    """A source file cannot be read as a supported document."""


def _read_pdf(
    path: Path,
    min_text_characters: int,
    use_ocr: bool,
    ocr_client: OpenAI | None,
    vision_model: str | None,
) -> list[DocumentPage]:
    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf:
                raise DocumentIngestionError(f"'{path.name}' is not a valid PDF.")
            if document.needs_pass:
                raise DocumentIngestionError(
                    f"PDF '{path.name}' is password-protected. Upload an unlocked copy."
                )
            if document.page_count == 0:
                raise DocumentIngestionError(f"PDF '{path.name}' contains no pages.")
            pages = []
            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text")
                # This threshold only selects pages for OCR, not clinical facts.
                meaningful_characters = sum(character.isalnum() for character in text)
                method = (
                    "OCR_REQUIRED"
                    if meaningful_characters < min_text_characters
                    else "PYMUPDF"
                )
                if method == "OCR_REQUIRED" and use_ocr:
                    # Render only the required page. Its PDF page number stays intact.
                    image_bytes = page.get_pixmap(dpi=200, alpha=False).tobytes("png")
                    try:
                        text = extract_text_from_image_bytes(
                            image_bytes, client=ocr_client, model=vision_model
                        )
                    except OCRExtractionError as error:
                        raise DocumentIngestionError(
                            f"OCR failed for '{path.name}', page {page_number}: {error}"
                        ) from None
                    method = "OPENAI_VISION"
                pages.append(
                    DocumentPage(
                        filename=path.name,
                        page_number=page_number,
                        text=text,
                        extraction_method=method,
                    )
                )
                if method == "OCR_REQUIRED":
                    LOGGER.info("OCR required for %s, page %d", path.name, page_number)
            return pages
    except DocumentIngestionError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise DocumentIngestionError(
            f"Cannot read PDF '{path.name}'. It may be corrupt, empty, or unreadable."
        ) from error


def _read_text(path: Path) -> list[DocumentPage]:
    try:
        # Accept an optional UTF-8 BOM without dropping undecodable bytes.
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DocumentIngestionError(
            f"TXT file '{path.name}' is not UTF-8. Save it as UTF-8 and try again."
        ) from error
    except OSError as error:
        raise DocumentIngestionError(f"Cannot read TXT file '{path.name}'.") from error
    return [
        DocumentPage(
            filename=path.name, page_number=1, text=text, extraction_method="TXT"
        )
    ]


def _read_image(
    path: Path,
    use_ocr: bool,
    ocr_client: OpenAI | None,
    vision_model: str | None,
) -> list[DocumentPage]:
    try:
        with Image.open(path) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise DocumentIngestionError(
                    f"Image '{path.name}' must contain PNG or JPEG image data."
                )
            image.verify()
    except DocumentIngestionError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise DocumentIngestionError(
            f"Cannot read image '{path.name}'. It may be corrupt or unreadable."
        ) from error
    text = ""
    method = "OCR_REQUIRED"
    if use_ocr:
        try:
            text = extract_text_from_image(path, client=ocr_client, model=vision_model)
        except OCRExtractionError as error:
            raise DocumentIngestionError(f"OCR failed for '{path.name}', page 1: {error}") from None
        method = "OPENAI_VISION"
    else:
        LOGGER.info("OCR required for %s, page 1", path.name)
    return [
        DocumentPage(
            filename=path.name,
            page_number=1,
            text=text,
            extraction_method=method,
        )
    ]


def ingest_document(
    file_path: str | Path,
    *,
    min_text_characters: int = MIN_EXTRACTABLE_TEXT_CHARACTERS,
    use_ocr: bool = False,
    ocr_client: OpenAI | None = None,
    vision_model: str | None = None,
) -> list[DocumentPage]:
    """Read a PDF, PNG, JPG, JPEG, or UTF-8 TXT file from a local path.

    PDF page numbers are one-based. TXT and image files are treated as a single
    page. PDF pages with fewer than ``min_text_characters`` alphanumeric
    characters are marked OCR_REQUIRED and retain any extracted text. Image
    pages contain empty text until an OCR/vision fallback transcribes them.
    The default threshold is a heuristic, not proof that a page is a scan.
    Set use_ocr=True to transcribe required pages using OpenAI vision. OCR
    failures raise a source-specific error, never substitute invented text.
    The default performs no API calls. There is no clinical reasoning.
    """
    if (
        not isinstance(min_text_characters, int)
        or isinstance(min_text_characters, bool)
        or min_text_characters < 1
    ):
        raise DocumentIngestionError("min_text_characters must be a positive integer.")
    try:
        path = Path(file_path)
    except (TypeError, ValueError) as error:
        raise DocumentIngestionError("Provide a valid filesystem path to a document.") from error
    if not path.exists():
        raise DocumentIngestionError(f"File not found: '{path.name}'.")
    if not path.is_file():
        raise DocumentIngestionError(f"'{path.name}' is not a regular file.")
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentIngestionError(
            f"Unsupported file type '{extension or '(none)'}' for '{path.name}'. "
            "Supported types: PDF, PNG, JPG, JPEG, TXT."
        )
    try:
        if extension == ".pdf":
            pages = _read_pdf(path, min_text_characters, use_ocr, ocr_client, vision_model)
        elif extension == ".txt":
            pages = _read_text(path)
        else:
            pages = _read_image(path, use_ocr, ocr_client, vision_model)
    except DocumentIngestionError:
        # Log only the source name, never patient text or document contents.
        LOGGER.warning("Document ingestion failed for %s", path.name)
        raise
    LOGGER.info("Ingested %s: %d page(s)", path.name, len(pages))
    return pages


def ingest_documents(
    file_paths: Iterable[str | Path],
    *,
    min_text_characters: int = MIN_EXTRACTABLE_TEXT_CHARACTERS,
    use_ocr: bool = False,
    ocr_client: OpenAI | None = None,
    vision_model: str | None = None,
) -> list[DocumentPage]:
    """Combine pages in input order; raise on any file error without skipping it."""
    if isinstance(file_paths, (str, Path)):
        raise DocumentIngestionError(
            "Pass a collection of paths to ingest_documents, or use ingest_document "
            "for a single file."
        )
    pages = []
    for file_path in file_paths:
        pages.extend(
            ingest_document(
                file_path, min_text_characters=min_text_characters,
                use_ocr=use_ocr, ocr_client=ocr_client, vision_model=vision_model,
            )
        )
    return pages
