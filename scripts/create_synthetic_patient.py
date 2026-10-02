"""Generate the fictional SYN-001 documents from build guide steps 10 and 11."""

import argparse
import logging
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont


LOGGER = logging.getLogger(__name__)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "patients" / "SYN-001"
DISCLAIMER = "SYNTHETIC PATIENT - FICTIONAL DATA - FOR DEMONSTRATION ONLY"

PDF_DOCUMENTS = {
    "oncology_note.pdf": {
        "title": "Oncology note",
        "date": "2026-03-10",
        "pages": [
            (
                "Patient overview",
                [
                    "Age: 58 years",
                    "Sex: Female",
                    "Diagnosis: Metastatic colorectal adenocarcinoma",
                    "Metastatic site: Liver",
                    "Treatment history and performance status continue on page 2.",
                ],
            ),
            (
                "Treatment history and performance status",
                [
                    "Prior treatment: FOLFOX, then FOLFIRI",
                    "Performance status: ECOG 1",
                ],
            ),
        ],
    },
    "pathology_report.pdf": {
        "title": "Pathology report",
        "date": "2026-02-24",
        "pages": [
            (
                "Molecular report overview",
                [
                    "BRAF: wild type",
                    "KRAS and microsatellite results continue on page 2.",
                ],
            ),
            (
                "Molecular findings",
                [
                    "KRAS: G12C mutation detected",
                    "MSI: microsatellite stable (MSS)",
                ],
            ),
        ],
    },
    "lab_report.pdf": {
        "title": "Laboratory report",
        "date": "2026-03-08",
        "pages": [
            (
                "Reported laboratory values",
                [
                    "Absolute neutrophil count (ANC): 2.1 x 10^9/L",
                    "Hemoglobin: 11.2 g/dL",
                    "Creatinine: 0.9 mg/dL",
                ],
            ),
        ],
    },
}


def write_pdf(path: Path, document: dict) -> None:
    """Keep each fact on the page specified by the build guide."""
    with pymupdf.open() as pdf:
        pdf.set_metadata(
            {"title": document["title"], "subject": DISCLAIMER, "author": "TrialMatch AI"}
        )
        for page_number, (section, facts) in enumerate(document["pages"], start=1):
            page = pdf.new_page(width=612, height=792)
            page.insert_text((48, 42), DISCLAIMER, fontsize=9, color=(0.45, 0.15, 0.1))
            page.insert_text((48, 88), document["title"], fontsize=23, fontname="hebo")
            page.insert_text((48, 120), "Patient ID: SYN-001", fontsize=11)
            page.insert_text((48, 142), f"Document date: {document['date']}", fontsize=11)
            page.draw_line((48, 160), (564, 160), color=(0.7, 0.7, 0.7))
            page.insert_text((48, 192), section, fontsize=14, fontname="hebo")
            remaining_space = page.insert_textbox(
                pymupdf.Rect(48, 218, 564, 680),
                "\n\n".join(facts),
                fontsize=12,
                lineheight=1.5,
            )
            if remaining_space < 0:
                raise ValueError(f"Content overflows {path.name}, page {page_number}")
            page.insert_text(
                (48, 738), "Fictional document. No real patient information.", fontsize=9
            )
            page.insert_text(
                (48, 756), f"Page {page_number} of {len(document['pages'])}", fontsize=9
            )
        pdf.save(path, deflate=True)


def image_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Use a readable installed font on Windows or Linux."""
    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"]
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def write_referral(path: Path) -> None:
    """Create a single-page typed referral image for the OCR workflow."""
    with Image.new("L", (1700, 2200), color=248) as scan:
        draw = ImageDraw.Draw(scan)
        draw.rectangle((80, 80, 1620, 2120), outline=150, width=2)
        draw.text((130, 130), "SYNTHETIC PATIENT - FICTIONAL DATA", font=image_font(32, True), fill=45)
        draw.text((130, 235), "OUTSIDE REFERRAL", font=image_font(56, True), fill=20)
        draw.text((130, 350), "Patient ID: SYN-001", font=image_font(36), fill=20)
        draw.text((130, 415), "Document date: 2026-03-11", font=image_font(36), fill=20)
        draw.line((130, 500, 1570, 500), fill=120, width=3)
        draw.text((130, 570), "Recorded performance status", font=image_font(40, True), fill=20)
        draw.text((130, 675), "ECOG 2", font=image_font(48, True), fill=20)
        draw.text((130, 1950), "For demonstration only. No real patient information.", font=image_font(28), fill=60)
        draw.text((130, 2015), "Page 1 of 1", font=image_font(28), fill=60)
        scan.save(path, dpi=(200, 200))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="Replace existing demo documents")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        paths = [OUTPUT_DIR / name for name in PDF_DOCUMENTS]
        paths.append(OUTPUT_DIR / "outside_referral_scan.png")
        existing = [path.name for path in paths if path.exists()]
        if existing and not args.overwrite:
            raise FileExistsError(
                f"Existing documents: {', '.join(existing)}. Use --overwrite to regenerate."
            )
        for name, document in PDF_DOCUMENTS.items():
            write_pdf(OUTPUT_DIR / name, document)
            LOGGER.info("Created %s", name)
        write_referral(OUTPUT_DIR / "outside_referral_scan.png")
        LOGGER.info("Created outside_referral_scan.png")
    except (OSError, ValueError, RuntimeError):
        LOGGER.exception("Could not create the synthetic patient documents")
        raise


if __name__ == "__main__":
    main()
