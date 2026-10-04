"""TrialMatch AI research prescreening interface."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

import streamlit as st

from src.evidence_view import build_evidence_groups, load_prepared_evidence
from src.safety import DISCLAIMER
from src.schemas import CriterionAssessment, DocumentPage, EvidenceItem
from src.source_viewer import build_source_view, highlight_html, pdf_page_count


PROJECT_ROOT = Path(__file__).resolve().parent
SAVED_RUN = PROJECT_ROOT / "data" / "sample_outputs" / "SYN-001_workflow.json"
PATIENT_DIR = PROJECT_ROOT / "data" / "patients" / "SYN-001"
REPO_URL = "https://github.com/raghavanlakshmi/TrialMatch_AI"
DASH = "—"
MIDDLE_DOT = "·"
CHECK = "✓"

STATUS_UI = {
    "MEETS": ("Meets", "green"),
    "DOES_NOT_MEET": ("Does not meet", "red"),
    "UNKNOWN": ("Unknown", "gray"),
    "POTENTIAL_CONFLICT": ("Potential conflict", "orange"),
}
LABEL_COLORS = {
    "Potential match": "green",
    "Apparent exclusion": "red",
    "Insufficient information": "gray",
}
DOCUMENT_ROLES = {
    "oncology_note.pdf": "Oncology clinic note",
    "pathology_report.pdf": "Pathology report",
    "lab_report.pdf": "Laboratory report",
    "outside_referral_scan.png": "Scanned outside referral",
    "handwritten_note.png": "Handwritten clinician note (experimental)",
    "prompt_injection_test.txt": "Prompt-injection test fixture",
}
CSS = """<style>
.stApp {background:#fafaf7;color:#17252a}
.block-container {padding-top:2rem;max-width:1200px}
h1 {letter-spacing:-0.02em}
div[data-testid='stMetric'] {background:#ffffff;border:1px solid #d9e4e2;padding:12px 14px;border-radius:8px}
div[data-testid='stExpander'] details {background:#ffffff;border-radius:8px}
.tm-source {white-space:pre-wrap;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:0.9rem;
  background:#ffffff;border:1px solid #d9e4e2;border-radius:8px;padding:12px;max-height:420px;overflow:auto}
.tm-source mark {background:#ffe08a;padding:0 2px;border-radius:3px}
.tm-muted {color:#5b6b6f;font-size:0.9rem}
</style>"""


# ----------------------------------------------------------------- data ---
def _deserialize_run(payload: dict) -> dict:
    payload["pages"] = [DocumentPage.model_validate(x) for x in payload.get("pages", [])]
    payload["evidence"] = [EvidenceItem.model_validate(x) for x in payload.get("evidence", [])]
    payload["assessments"] = {
        nct: [CriterionAssessment.model_validate(x) for x in items]
        for nct, items in payload.get("assessments", {}).items()
    }
    return payload


def load_saved_run() -> dict:
    return _deserialize_run(json.loads(SAVED_RUN.read_text(encoding="utf-8")))


def _label_color(label: str) -> str:
    return next((color for prefix, color in LABEL_COLORS.items() if label.startswith(prefix)), "gray")


# --------------------------------------------------------------- viewer ---
@st.dialog("Source review", width="large")
def show_source(filename: str, page_number: int, quote: str | None) -> None:
    pages = st.session_state.get("run", {}).get("pages", [])
    try:
        view = build_source_view(PATIENT_DIR, pages, filename, page_number, quote)
    except Exception as exc:  # unreadable file: show a clear message instead of a stack trace
        st.error(f"The source could not be opened: {exc}")
        return
    st.markdown(f"**{DOCUMENT_ROLES.get(filename, filename)}**")
    st.caption(f"{filename} {MIDDLE_DOT} page {page_number} {MIDDLE_DOT} extraction: {view.extraction_method or 'not recorded'}")
    if view.kind in {"pdf", "image"} and view.image:
        left, right = st.columns([3, 2], gap="large", vertical_alignment="top")
        with left:
            st.markdown("**Source document**")
            st.image(view.image, width="stretch")
            if view.kind == "pdf":
                st.caption("Quote highlighted on the page." if view.quote_highlighted_on_image else "Quote could not be located on the rendered page; see the transcription.")
            else:
                st.caption("Original image. The highlighted text on the right is the saved transcription.")
        with right:
            st.markdown("**Extracted evidence**")
            if quote:
                st.caption("Supporting quote")
                st.markdown(f"<div class='tm-source'><mark>{highlight_html(quote, None)}</mark></div>", unsafe_allow_html=True)
            if view.transcription is not None:
                with st.expander("Full extracted page text", expanded=not quote):
                    st.markdown(f"<div class='tm-source'>{highlight_html(view.transcription, quote)}</div>", unsafe_allow_html=True)
            elif not quote:
                st.info("No extracted text is available for this page.")
    elif view.transcription is not None:
        st.markdown("**Extracted evidence**")
        if quote:
            st.caption("Supporting quote")
            st.markdown(f"<div class='tm-source'><mark>{highlight_html(quote, None)}</mark></div>", unsafe_allow_html=True)
            with st.expander("Full extracted page text"):
                st.markdown(f"<div class='tm-source'>{highlight_html(view.transcription, quote)}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='tm-source'>{highlight_html(view.transcription, None)}</div>", unsafe_allow_html=True)
    else:
        st.info("The original source is not available in this session.")
    st.caption("Human review: confirm the value, date and context in the original record before relying on it.")


@st.dialog("Source document", width="large")
def show_document(filename: str) -> None:
    pages = sorted((p for p in st.session_state.get("run", {}).get("pages", []) if p.filename == filename), key=lambda p: p.page_number)
    path = PATIENT_DIR / filename
    count = pdf_page_count(path) if path.suffix.lower() == ".pdf" and path.exists() else max(1, len(pages))
    st.markdown(f"**{DOCUMENT_ROLES.get(filename, filename)}**")
    page_number = st.number_input("Page", min_value=1, max_value=count, value=1, step=1) if count > 1 else 1
    view = build_source_view(PATIENT_DIR, pages, filename, int(page_number))
    if view.image and view.transcription is not None:
        left, right = st.columns([3, 2], gap="large", vertical_alignment="top")
        with left:
            st.markdown("**Source document**")
            st.image(view.image, width="stretch")
        with right:
            st.markdown("**Extracted text**")
            st.markdown(f"<div class='tm-source'>{highlight_html(view.transcription, None)}</div>", unsafe_allow_html=True)
    elif view.image:
        st.image(view.image, width="stretch")
    elif view.transcription is not None:
        st.markdown(f"<div class='tm-source'>{highlight_html(view.transcription, None)}</div>", unsafe_allow_html=True)


def source_button(item: EvidenceItem, key: str) -> None:
    if st.button("View source", key=key, icon=":material/description:"):
        show_source(item.source_file, item.source_page, item.evidence_text)


# ------------------------------------------------------------- sections ---
def render_documents_tab(run: dict | None) -> None:
    st.subheader("Source documents")
    st.markdown("<span class='tm-muted'>One synthetic patient, split across documents on purpose. No single file holds every fact.</span>", unsafe_allow_html=True)
    pages = (run or {}).get("pages", [])
    evidence = (run or {}).get("evidence", [])
    order = list(DOCUMENT_ROLES)
    files = sorted(PATIENT_DIR.iterdir(), key=lambda p: order.index(p.name) if p.name in order else len(order)) if PATIENT_DIR.exists() else []
    columns = st.columns(3)
    for index, path in enumerate(files):
        file_pages = [p for p in pages if p.filename == path.name]
        methods = sorted({p.extraction_method for p in file_pages}) or ["not processed"]
        facts = sum(item.source_file == path.name for item in evidence)
        with columns[index % 3].container(border=True):
            st.markdown(f"**{DOCUMENT_ROLES.get(path.name, path.name)}**")
            st.caption(f"{path.name} {MIDDLE_DOT} {len(file_pages) or '?'} page(s) {MIDDLE_DOT} {', '.join(methods)}")
            st.markdown(f"{facts} fact(s) extracted")
            if st.button("Open document", key=f"doc-{path.name}", icon=":material/visibility:"):
                show_document(path.name)

    st.divider()
    with st.expander("Analyze new synthetic documents (live run, requires an OpenAI API key)"):
        uploads = st.file_uploader(
            "Upload synthetic PDF, PNG, JPEG, or text files",
            type=["pdf", "png", "jpg", "jpeg", "txt"],
            accept_multiple_files=True,
        )
        if st.button("Analyze Patient Evidence", type="primary", disabled=not uploads):
            try:
                from src.workflow import build_workflow  # heavy imports load only for live runs
            except ImportError:
                st.error("Live analysis needs the full requirements (LangGraph, Chroma, sentence-transformers). "
                         "The hosted demo runs in replay mode; clone the repository to run live analysis.")
                return

            with tempfile.TemporaryDirectory() as folder:
                paths = []
                for upload in uploads:
                    path = Path(folder) / Path(upload.name).name
                    path.write_bytes(upload.getvalue())
                    paths.append(str(path))
                with st.spinner("Running evidence and trial workflow..."):
                    st.session_state.run = build_workflow().invoke(
                        {"uploaded_files": paths, "trace": [], "safety_flags": [], "top_k": 5}
                    )
                    st.session_state.run_source = "live"
            st.success("Analysis complete. Review every result before use.")
    if st.button("Reload saved SYN-001 run", icon=":material/replay:"):
        st.session_state.run = load_saved_run()
        st.session_state.run_source = "saved"
        st.success("Loaded the pre-tested saved run; no API call was made.")


def render_evidence(evidence: list[EvidenceItem], *, review_only: bool = False) -> None:
    for group in build_evidence_groups(evidence):
        if review_only and group.status is None and not group.has_unverified_quotes:
            continue
        with st.container(border=True):
            header, badge = st.columns([4, 1])
            header.subheader(group.label)
            if group.status:
                text, color = STATUS_UI[group.status]
                badge.badge(text, color=color)
            else:
                badge.badge("Supported", color="green", icon=":material/check:")
            if group.status == "POTENTIAL_CONFLICT":
                st.warning(f"Potential conflict {DASH} reviewer reconciles. Both values retained.")
            elif group.status == "UNKNOWN":
                message = (
                    f"UNKNOWN {DASH} no supporting evidence found in supplied documents."
                    if not group.items
                    else f"UNKNOWN {DASH} supporting quotes have not been verified."
                )
                st.info(message)
            for index, item in enumerate(group.items):
                if index:
                    st.divider()
                st.text(item.value)
                st.text(
                    f"{item.source_file} {MIDDLE_DOT} p{item.source_page} "
                    f"{MIDDLE_DOT} {item.date or 'date not documented'}"
                )
                if item.quote_verified:
                    st.caption(f"{CHECK} Quote verified against source text")
                else:
                    st.warning(f"Unverified quote {DASH} review the source before using this fact.")
                source_button(item, key=f"ev-{group.key}-{index}")


def render_review_checklist(evidence: list[EvidenceItem]) -> None:
    groups = [g for g in build_evidence_groups(evidence) if g.status or g.has_unverified_quotes]
    st.subheader("Reviewer checklist")
    st.markdown("<span class='tm-muted'>Items the system will not resolve on its own. Record your decision, then download the review summary.</span>", unsafe_allow_html=True)
    notes = {}
    for group in groups:
        status = STATUS_UI[group.status][0] if group.status else "Unverified quote"
        with st.container(border=True):
            done = st.checkbox(f"{group.label} {DASH} {status}", key=f"rev-{group.key}")
            hint = ("e.g. confirmed current value with the treating team" if group.status == "POTENTIAL_CONFLICT"
                    else "e.g. requested treatment history from the referring clinic")
            note = st.text_input("Reviewer note", key=f"note-{group.key}", placeholder=hint)
            notes[group.label] = {"status": status, "reviewed": done, "note": note,
                                  "sources": [f"{i.source_file} p{i.source_page}: {i.value}" for i in group.items]}
    lines = ["# TrialMatch AI reviewer summary", f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "", DISCLAIMER.replace("\n", " "), ""]
    for label, record in notes.items():
        lines.append(f"## {label} {DASH} {record['status']}")
        lines.append(f"- Reviewed: {'yes' if record['reviewed'] else 'no'}")
        lines.append(f"- Note: {record['note'] or '(none)'}")
        lines.extend(f"- Source: {source}" for source in record["sources"] or ["no supporting evidence"])
        lines.append("")
    st.download_button("Download review summary", "\n".join(lines), file_name="trialmatch_review_summary.md", mime="text/markdown", icon=":material/download:")


def render_trials_tab(run: dict | None) -> None:
    if not run:
        st.info("Analyze documents or replay the saved run.")
        return
    candidates = run.get("candidate_trials", [])
    summaries = run.get("trial_summaries", {})
    if not candidates:
        st.info(run.get("human_review", {}).get("message", "Insufficient information"))
        return
    rows = []
    for rank, candidate in enumerate(candidates, start=1):
        summary = summaries.get(candidate["nct_id"], {})
        counts = summary.get("counts", {})
        rows.append({
            "Rank": rank, "Trial": candidate["nct_id"],
            "Review label": summary.get("overall_label", "Insufficient information"),
            "Relevance": candidate.get("relevance_score"),
            "Meets": counts.get("MEETS", 0), "Does not meet": counts.get("DOES_NOT_MEET", 0),
            "Unknown": counts.get("UNKNOWN", 0), "Potential conflict": counts.get("POTENTIAL_CONFLICT", 0),
        })
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("Relevance is the reranker's relative score, not an eligibility probability.")

    for rank, candidate in enumerate(candidates, start=1):
        nct_id = candidate["nct_id"]
        summary = summaries.get(nct_id, {})
        label = summary.get("overall_label", "Insufficient information")
        assessments = run.get("assessments", {}).get(nct_id, [])
        with st.expander(f"{rank}. {nct_id} {MIDDLE_DOT} {label}", expanded=rank == 1):
            top, link = st.columns([4, 1])
            top.badge(label, color=_label_color(label))
            link.link_button("ClinicalTrials.gov", f"https://clinicaltrials.gov/study/{nct_id}", icon=":material/open_in_new:")
            st.caption(candidate.get("reason", ""))
            counts = summary.get("counts", {})
            cols = st.columns(4)
            for col, key in zip(cols, ("MEETS", "DOES_NOT_MEET", "UNKNOWN", "POTENTIAL_CONFLICT")):
                col.metric(STATUS_UI[key][0], counts.get(key, 0))
            methods = Counter(item.method for item in assessments)
            st.caption(f"Assessed by deterministic rules: {methods.get('rule', 0)} {MIDDLE_DOT} by the LLM assessor: {methods.get('llm', 0)}")
            default = [s for s in ("MEETS", "DOES_NOT_MEET", "POTENTIAL_CONFLICT") if counts.get(s)]
            shown = st.pills("Show criteria", list(STATUS_UI), default=default or list(STATUS_UI),
                             selection_mode="multi", format_func=lambda s: STATUS_UI[s][0], key=f"pills-{nct_id}")
            for index, item in enumerate(assessments):
                if item.status not in (shown or []):
                    continue
                with st.container(border=True):
                    badges = st.columns([2, 2, 6])
                    text, color = STATUS_UI[item.status]
                    badges[0].badge(text, color=color)
                    badges[1].badge("LLM" if item.method == "llm" else "Rule", color="violet" if item.method == "llm" else "blue")
                    badges[2].caption(f"{item.criterion_id} {MIDDLE_DOT} {item.criterion_type}")
                    st.text(item.criterion_text)
                    st.caption(item.explanation)
                    for source_index, source in enumerate(item.patient_evidence):
                        st.text(f"{source.source_file} p{source.source_page}: {source.evidence_text}")
                        source_button(source, key=f"cr-{nct_id}-{index}-{source_index}")


def render_safety_tab(run: dict | None) -> None:
    if not run:
        st.info("Workflow trace appears after a run is loaded.")
        return
    flags = run.get("safety_flags", [])
    methods = Counter(item.method for items in run.get("assessments", {}).values() for item in items)
    cols = st.columns(3)
    cols[0].metric("Safety flags", len(flags))
    cols[1].metric("Rule assessments", methods.get("rule", 0))
    cols[2].metric("LLM assessments", methods.get("llm", 0))
    if any("instruction-like" in flag for flag in flags):
        st.success("Prompt-injection test passed: source instruction was treated as untrusted data.")
    for flag in flags:
        st.warning(flag)
    trace = run.get("trace", [])
    st.subheader("Workflow trace")
    st.dataframe(
        [{"Step": t.get("step"), "Status": t.get("status"), "Latency (ms)": t.get("latency_ms"),
          "In": t.get("input_count"), "Out": t.get("output_count"), "LLM calls": t.get("llm_calls", 0),
          "Model": t.get("model", "")} for t in trace],
        width="stretch", hide_index=True,
    )
    st.caption(
        "Embedding model: sentence-transformers/all-MiniLM-L6-v2 "
        f"{MIDDLE_DOT} Fusion: RRF k=60 {MIDDLE_DOT} Age and sex: deterministic rules"
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### TrialMatch AI")
        st.markdown("Evidence-grounded clinical-trial **prescreening** on synthetic data. It never decides eligibility.")
        st.markdown("**How to read results**")
        for key, (text, color) in STATUS_UI.items():
            st.badge(text, color=color)
        st.caption("For exclusion criteria, Meets means the patient appears clear of the exclusion.")
        st.link_button("Source code on GitHub", REPO_URL, icon=":material/code:")


# ----------------------------------------------------------------- main ---
def main() -> None:
    st.set_page_config(page_title="TrialMatch AI", page_icon=":material/clinical_notes:", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    if "run" not in st.session_state and SAVED_RUN.exists():
        st.session_state.run = load_saved_run()
        st.session_state.run_source = "saved"
    render_sidebar()

    st.title("TrialMatch AI")
    st.caption("Evidence-grounded research-trial prescreening for synthetic data")
    st.warning(DISCLAIMER)
    run = st.session_state.get("run")
    if st.session_state.get("run_source") == "saved":
        st.info("Showing the validated SYN-001 saved run. No API calls are made in this view.", icon=":material/replay:")

    documents_tab, evidence_tab, trials_tab, safety_tab = st.tabs(
        ["Patient Documents", "Evidence", "Trial Matches", "Safety & Trace"]
    )
    with documents_tab:
        render_documents_tab(run)

    if run:
        display_evidence = run.get("evidence", [])
    else:
        try:
            display_evidence, _ = load_prepared_evidence(PROJECT_ROOT)
        except Exception:
            display_evidence = []
    with evidence_tab:
        groups = build_evidence_groups(display_evidence)
        metrics = st.columns(4)
        metrics[0].metric("Evidence records", len(display_evidence))
        metrics[1].metric("Verified quotes", f"{sum(i.quote_verified for i in display_evidence)}/{len(display_evidence)}")
        metrics[2].metric("Potential conflicts", sum(group.status == "POTENTIAL_CONFLICT" for group in groups))
        metrics[3].metric("Unknown facts", sum(group.status == "UNKNOWN" for group in groups))
        review_only = st.checkbox("Show only facts needing review", value=False)
        if display_evidence:
            left, right = st.columns([3, 2])
            with left:
                render_evidence(display_evidence, review_only=review_only)
            with right:
                render_review_checklist(display_evidence)
        else:
            st.info("Analyze documents or replay the saved run.")

    with trials_tab:
        render_trials_tab(run)
    with safety_tab:
        render_safety_tab(run)


if __name__ == "__main__":
    main()
