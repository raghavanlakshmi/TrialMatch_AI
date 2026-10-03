import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.schemas import DocumentPage
from src.source_viewer import build_source_view, highlight_html


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATIENT_DIR = PROJECT_ROOT / "data" / "patients" / "SYN-001"
SAVED_RUN = PROJECT_ROOT / "data" / "sample_outputs" / "SYN-001_workflow.json"


def saved_pages():
    return [DocumentPage.model_validate(p) for p in json.loads(SAVED_RUN.read_text(encoding="utf-8"))["pages"]]


def test_highlight_escapes_untrusted_text_and_marks_quote():
    rendered = highlight_html("<script>x</script>\nPerformance status: ECOG   1", "ECOG 1")
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert "<mark>ECOG   1</mark>" in rendered


def test_pdf_quote_is_highlighted_on_rendered_page():
    view = build_source_view(PATIENT_DIR, saved_pages(), "oncology_note.pdf", 2, "Performance status: ECOG 1")
    assert view.kind == "pdf" and view.image.startswith(b"\x89PNG")
    assert view.quote_highlighted_on_image


def test_handwritten_note_shows_image_and_transcription():
    view = build_source_view(PATIENT_DIR, saved_pages(), "handwritten_note.png", 1, "KRAS G12C+")
    assert view.kind == "image" and view.image
    assert "<mark>KRAS G12C+</mark>" in highlight_html(view.transcription, "KRAS G12C+")
    assert view.extraction_method == "OPENAI_VISION"


def test_viewer_cannot_open_files_outside_patient_folder():
    view = build_source_view(PATIENT_DIR, [], "../../../README.md", 1, None)
    assert view.kind == "missing" and view.image is None


def test_every_saved_evidence_record_has_a_viewable_source():
    run = json.loads(SAVED_RUN.read_text(encoding="utf-8"))
    pages = saved_pages()
    for item in run["evidence"]:
        view = build_source_view(PATIENT_DIR, pages, item["source_file"], item["source_page"], item["evidence_text"])
        assert view.kind in {"pdf", "image"}
        assert "<mark>" in highlight_html(view.transcription or "", item["evidence_text"])


def test_app_loads_saved_run_on_first_visit_and_opens_source_dialog():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert any("saved run" in info.value for info in app.info)
    buttons = [b for b in app.button if b.label == "View source"]
    assert buttons
    buttons[0].click().run(timeout=30)
    assert not app.exception
