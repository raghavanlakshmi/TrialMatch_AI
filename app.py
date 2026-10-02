"""TrialMatch AI research prescreening interface."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import streamlit as st

from src.evidence_view import build_evidence_groups, load_prepared_evidence
from src.safety import DISCLAIMER
from src.schemas import CriterionAssessment, DocumentPage, EvidenceItem
from src.workflow import build_workflow


PROJECT_ROOT = Path(__file__).resolve().parent
SAVED_RUN = PROJECT_ROOT / "data" / "sample_outputs" / "SYN-001_workflow.json"
DASH = "\u2014"
MIDDLE_DOT = "\u00b7"
CHECK = "\u2713"


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


def render_evidence(evidence: list[EvidenceItem], *, review_only: bool = False) -> None:
    for group in build_evidence_groups(evidence):
        if review_only and group.status is None and not group.has_unverified_quotes:
            continue
        with st.container(border=True):
            st.subheader(group.label)
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
                with st.expander("Supporting quote"):
                    st.text(item.evidence_text)


def main() -> None:
    st.set_page_config(page_title="TrialMatch AI", page_icon=":material/search:", layout="wide")
    st.markdown(
        """<style>
        .stApp {background:#fafaf7;color:#17252a}
        .stButton button {border-color:#207f78}
        div[data-testid='stMetric'] {border:1px solid #d9e4e2;padding:12px;border-radius:6px}
        </style>""",
        unsafe_allow_html=True,
    )
    st.title("TrialMatch AI")
    st.caption("Evidence-grounded research-trial prescreening for synthetic data")
    st.warning(DISCLAIMER)
    documents_tab, evidence_tab, trials_tab, safety_tab = st.tabs(
        ["Patient Documents", "Evidence", "Trial Matches", "Safety & Trace"]
    )
    with documents_tab:
        uploads = st.file_uploader(
            "Upload synthetic PDF, PNG, JPEG, or text files",
            type=["pdf", "png", "jpg", "jpeg", "txt"],
            accept_multiple_files=True,
        )
        if uploads:
            st.write([item.name for item in uploads])
        left, right = st.columns(2)
        if left.button("Analyze Patient Evidence", type="primary", disabled=not uploads):
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
            st.success("Analysis complete. Review every result before use.")
        if right.button("Replay saved SYN-001 run"):
            st.session_state.run = load_saved_run()
            st.success("Loaded the pre-tested saved run; no API call was made.")
        if "run" not in st.session_state and SAVED_RUN.exists():
            st.info("Choose replay to load the prepared demonstration.")

    run = st.session_state.get("run")
    if run:
        display_evidence = run.get("evidence", [])
    else:
        try:
            display_evidence, _ = load_prepared_evidence(PROJECT_ROOT)
        except Exception:
            display_evidence = []
    with evidence_tab:
        groups = build_evidence_groups(display_evidence)
        metrics = st.columns(3)
        metrics[0].metric("Evidence records", len(display_evidence))
        metrics[1].metric(
            "Potential conflicts", sum(group.status == "POTENTIAL_CONFLICT" for group in groups)
        )
        metrics[2].metric("Unknown facts", sum(group.status == "UNKNOWN" for group in groups))
        review_only = st.checkbox("Show only facts needing review", value=False)
        if display_evidence:
            render_evidence(display_evidence, review_only=review_only)
        else:
            st.info("Analyze documents or replay the saved run.")

    with trials_tab:
        if not run:
            st.info("Analyze documents or replay the saved run.")
        for candidate in (run or {}).get("candidate_trials", []):
            nct_id = candidate["nct_id"]
            summary = run.get("trial_summaries", {}).get(nct_id, {})
            label = summary.get("overall_label", "Insufficient information")
            with st.expander(f"{nct_id} {MIDDLE_DOT} {label}"):
                counts = summary.get("counts", {})
                cols = st.columns(4)
                for col, key in zip(
                    cols, ("MEETS", "DOES_NOT_MEET", "UNKNOWN", "POTENTIAL_CONFLICT")
                ):
                    col.metric(key.replace("_", " ").title(), counts.get(key, 0))
                st.caption(candidate.get("reason", ""))
                for item in run.get("assessments", {}).get(nct_id, []):
                    st.markdown(
                        f"**{item.status} {MIDDLE_DOT} {item.criterion_id} "
                        f"{MIDDLE_DOT} {item.method}**"
                    )
                    st.text(item.criterion_text)
                    st.caption(item.explanation)
                    for source in item.patient_evidence:
                        st.text(
                            f"{source.source_file} p{source.source_page}: {source.evidence_text}"
                        )

    with safety_tab:
        st.warning(DISCLAIMER)
        if run:
            flags = run.get("safety_flags", [])
            st.metric("Safety flags", len(flags))
            for flag in flags:
                st.warning(flag)
            if any("instruction-like" in flag for flag in flags):
                st.success(
                    "Prompt-injection test passed: source instruction was treated as untrusted data."
                )
            st.dataframe(run.get("trace", []), width="stretch", hide_index=True)
            st.caption(
                "Embedding model: sentence-transformers/all-MiniLM-L6-v2 "
                f"{MIDDLE_DOT} Fusion: RRF k=60 {MIDDLE_DOT} "
                "Criterion fallback: conservative offline mode"
            )
        else:
            st.info("Workflow trace appears after a run is loaded.")


if __name__ == "__main__":
    main()
