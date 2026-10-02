---
title: "TRIALMATCH AI"
subtitle: "Updated Project Documentation and PowerPoint Presentation Brief"
author: "Competition Prototype"
date: "October 2, 2026"
---

# Executive Summary

TrialMatch AI is a completed competition prototype for evidence-grounded,
AI-assisted clinical-trial prescreening. It converts fragmented synthetic
patient documents into traceable evidence, retrieves potentially relevant
trials from a frozen ClinicalTrials.gov corpus, compares patient evidence with
individual trial criteria, and presents uncertainty and source citations for
human review.

The prototype is implemented as a four-tab Streamlit application backed by a
controlled 12-node LangGraph workflow. It supports text PDFs, scanned images,
handwritten-note transcription, structured evidence extraction, exact-quote
verification, hybrid retrieval, reranking, criterion-level assessment,
prompt-injection defense, and workflow tracing.

The system does not determine whether a patient is eligible or ineligible.
Its outputs are research-prescreening observations that require verification
by qualified study staff.

## Completion status

| Deliverable | Verified result |
|---|---:|
| Streamlit application | Complete and runnable locally |
| Synthetic patient evidence | 16 verified records |
| Frozen trial snapshot | 75 recruiting trials |
| Parsed atomic criteria | 1,542 |
| Semantic discovery chunks | 965 |
| Retrieved and reranked demo candidates | 5 |
| Criterion assessments in saved demo | 139 |
| LangGraph trace nodes | 12 successful nodes |
| Synthetic evaluation cases | 10 |
| Automated tests | 151 passed |
| Live API verification after key update | Passed |
| Saved-run replay | Complete |
| Final narrated video and submission upload | Manual submission step |

# 1. Problem Statement

Clinical-trial prescreening requires research staff to reconcile complex
eligibility criteria with patient facts distributed across notes, pathology
reports, laboratory reports, scans, and other unstructured documents. The task
is time-consuming and error-prone because essential facts may be missing,
contradictory, difficult to read, or described with different terminology.

Simple search tools return trial links but do not solve the difficult middle
layer: extracting auditable patient evidence, preserving its provenance,
handling uncertainty, and comparing that evidence with individual inclusion
and exclusion criteria.

# 2. Implemented Solution

TrialMatch AI implements this workflow:

```text
Patient documents
      |
      v
Text extraction and vision OCR
      |
      v
Structured evidence with source, page, date, and quote
      |
      v
Vector retrieval + BM25 + reciprocal rank fusion
      |
      v
Candidate reranking
      |
      v
Age/sex rules + free-text criterion assessment
      |
      v
Safety review, trace, and mandatory human review
```

The application exposes this workflow through four tabs:

1. **Patient Documents** - upload synthetic records or replay the validated
   SYN-001 run.
2. **Evidence** - inspect extracted facts, provenance, exact quotes, conflicts,
   and missing facts.
3. **Trial Matches** - inspect reranked trials and criterion-level results.
4. **Safety & Trace** - inspect the human-review disclaimer,
   prompt-injection defense, models, counts, and node latency.

# 3. Synthetic Demonstration Patient

The prepared demonstration uses a fictional 58-year-old woman with metastatic
colorectal adenocarcinoma. The source set includes:

- Oncology note PDF
- Pathology report PDF
- Laboratory report PDF
- Scanned outside-referral image
- Experimental handwritten-note image
- A separate malicious-text fixture for prompt-injection testing

The records intentionally contain one conflict and one missing fact:

- ECOG 1 is documented on 2026-03-10.
- ECOG 2 is documented by an outside source on 2026-03-11.
- Prior use of a KRAS G12C inhibitor is not documented.

These cases demonstrate that the application preserves uncertainty instead of
selecting a preferred value or inventing a negative treatment history.

# 4. Evidence Extraction Results

The saved SYN-001 run contains 16 evidence records. Every record includes the
fact category, value, source file, one-based page number, date when documented,
exact supporting quote, and a code-computed quote-verification flag.

All 16 saved evidence records passed exact source-quote verification.

| Evidence example | Value | Source | Date | Result |
|---|---|---|---|---|
| Age | 58 years | oncology_note.pdf, page 1 | 2026-03-10 | Verified |
| Sex | Female | oncology_note.pdf, page 1 | 2026-03-10 | Verified |
| Diagnosis | Metastatic colorectal adenocarcinoma | oncology_note.pdf, page 1 | 2026-03-10 | Verified |
| KRAS | G12C mutation detected | pathology_report.pdf, page 2 | 2026-02-24 | Verified |
| MSI | Microsatellite stable | pathology_report.pdf, page 2 | 2026-02-24 | Verified |
| Prior treatment | FOLFOX, then FOLFIRI | oncology_note.pdf, page 2 | 2026-03-10 | Verified |
| ANC | 2.1 x 10^9/L | lab_report.pdf, page 1 | 2026-03-08 | Verified |
| ECOG | 1 | oncology_note.pdf, page 2 | 2026-03-10 | Potential conflict |
| ECOG | 2 | outside_referral_scan.png, page 1 | 2026-03-11 | Potential conflict |
| Prior KRAS G12C inhibitor | No supported evidence | None | None | UNKNOWN |

Quote verification establishes that the quoted text appears in the named
source. It does not establish clinical correctness or eliminate the need to
review OCR and handwriting.

# 5. Trial Corpus and Index Results

The application uses a frozen ClinicalTrials.gov snapshot dated 2026-10-02.
The snapshot supports a reproducible demo and avoids runtime dependence on the
registry service.

| Corpus item | Count |
|---|---:|
| Total recruiting trials | 75 |
| Candidate-role trials | 55 |
| Deliberate distractor trials | 20 |
| Parsed inclusion criteria | 890 |
| Parsed exclusion criteria | 652 |
| Total atomic criteria | 1,542 |
| Discovery chunks | 965 |

Candidate and distractor roles describe corpus construction; they are not
patient-level relevance or eligibility labels.

Every eligibility block is parsed once at index time. Stable criterion IDs such
as `INC-01` and `EXC-03` are saved in `criteria.json`. Candidate discovery
indexes trial summaries and inclusion criteria. Exclusion criteria remain
available for the later prescreening stage, where their direction can be
evaluated safely.

# 6. Retrieval and Reranking

Trial discovery combines:

- Local `all-MiniLM-L6-v2` sentence embeddings
- Chroma with cosine distance
- BM25 lexical retrieval
- Reciprocal rank fusion with `k=60`
- Trial-level rollup using each trial's best chunk
- LLM reranking of the small candidate set

The saved demo returned five reranked candidates:

| Rank | Trial | Reranker score | Interpretation |
|---:|---|---:|---|
| 1 | NCT06412198 | 0.95 | Strong disease and KRAS G12C alignment; potential match with an ECOG conflict |
| 2 | NCT06252649 | 0.90 | Metastatic colorectal cancer and KRAS G12C alignment; potential match with an ECOG conflict |
| 3 | NCT07559760 | 0.80 | MSS metastatic colorectal cancer and treatment-history alignment; potential match with an ECOG conflict |
| 4 | NCT06645236 | 0.60 | Relevant companion-diagnostic study rather than a direct therapeutic match |
| 5 | NCT06782685 | 0.30 | Pancreatic-cancer distractor correctly assigned low relevance |

The reranker score represents relative candidate relevance. It is not an
eligibility probability.

# 7. Criterion-Level Prescreening Results

The saved workflow evaluated 129 parsed free-text criteria plus deterministic
age and sex checks for each of five trials, producing 139 assessments.

Allowed statuses are:

- `MEETS`
- `DOES_NOT_MEET`
- `UNKNOWN`
- `POTENTIAL_CONFLICT`

For an exclusion criterion, `MEETS` means the patient appears clear of the
exclusion, while `DOES_NOT_MEET` means the exclusion appears to apply.

| Trial | Meets | Does not meet | Unknown | Potential conflict | Review label |
|---|---:|---:|---:|---:|---|
| NCT06412198 | 4 | 0 | 46 | 1 | Potential match - needs verification |
| NCT06252649 | 4 | 0 | 6 | 1 | Potential match - needs verification |
| NCT07559760 | 4 | 0 | 38 | 1 | Potential match - needs verification |
| NCT06645236 | 3 | 0 | 1 | 0 | Potential match - needs verification |
| NCT06782685 | 3 | 1 | 26 | 0 | Apparent exclusion - needs verification |

The pancreatic distractor `NCT06782685` is not treated as a potential match
merely because its structured age and sex fields pass. Its inclusion criterion
requires pancreatic cancer, while the verified patient diagnosis is colorectal
cancer, so the narrow deterministic diagnosis rule returns `DOES_NOT_MEET`.
Across all 1,542 criteria, this rule flags four criteria, all in pancreatic
distractor trials and none in the 55 candidate-role trials. Cohort-specific,
metastasis, history, multi-cancer, and exception wording remain guarded against
false-positive diagnosis mismatches.

For `NCT06412198`, verified KRAS G12C mutation evidence is not treated as proof
of prior KRAS G12C inhibition therapy. That exclusion therefore remains
`UNKNOWN`. The inclusion criterion requiring ECOG 0 or 1 receives different
outcomes from the documented ECOG 1 and ECOG 2 values, so it is marked
`POTENTIAL_CONFLICT`. The trial remains a potential match requiring human
verification.

The large number of `UNKNOWN` results is intentional. It shows that sparse
patient records are not silently converted into supportive evidence.

# 8. Agentic Workflow and Observability

The application uses one controlled LangGraph rather than multiple autonomous
agents. The saved run completed all 12 nodes successfully:

1. `ingest_documents`
2. `extract_evidence`
3. `verify_quotes`
4. `detect_conflicts`
5. `build_patient_query`
6. `retrieve_trials`
7. `rerank_trials`
8. `load_trial_criteria`
9. `check_structured_rules`
10. `assess_criteria`
11. `safety_review`
12. `prepare_human_review`

The trace stores start/end times, latency, input and output counts, status,
errors, LLM-call counts, and model information when applicable. In the saved
run, retrieval produced five candidates and the workflow prepared five records
for human review. The replay preserves the trace while avoiding network delays
during the recorded demonstration.

# 9. Safety and Responsible-AI Results

The implemented safety controls include:

- Synthetic patient data only
- No definitive patient eligibility statement
- Required provenance for every patient fact
- Code-based exact-quote verification
- Missing evidence remains `UNKNOWN`
- Differing evidence remains `POTENTIAL_CONFLICT`
- Deterministic age and sex checks
- Explicit exclusion-criterion direction
- Unsupported LLM conclusions converted to `UNKNOWN`
- Unverified source quotes cannot support a conclusion
- Trial and patient text treated as untrusted data
- Required visible human-review disclaimer

The malicious fixture contains an instruction telling the model to ignore the
criteria and mark the patient eligible. The saved workflow flagged the text as
instruction-like source content and continued to treat it as data. The safety
result displayed in the application is:

```text
Prompt-injection test passed: source instruction was treated as untrusted data.
```

# 10. Evaluation Results

The evaluation set contains 10 synthetic cases covering:

1. Clear match
2. Clear exclusion
3. Missing biomarker and inhibitor history
4. ECOG conflict
5. Scanned-document transcript
6. Synonym/paraphrase
7. Irrelevant document
8. Prompt injection
9. Old versus new evidence
10. No appropriate trial

## Extraction fixture

| Metric | Result |
|---|---:|
| Fact precision | 1.00 |
| Fact recall | 1.00 |
| Source citation accuracy | 1.00 |
| Quote verification rate | 1.00 |

These extraction figures measure a frozen tagged-text fixture. They are a
pipeline regression check, not a clinical-performance or general OCR claim.

## Retrieval comparison

| Retrieval method | Recall@5 |
|---|---:|
| Vector only | 1.00 |
| BM25 only | 0.75 |
| Hybrid RRF | 0.75 |
| Hybrid RRF plus offline rerank | 0.75 |

The comparison is intentionally reported without hiding the weaker hybrid
result. On this small fixture, vector retrieval performed best. The hybrid
design remains useful for exact drug and biomarker terms, but its fusion and
gold labels require tuning on a larger evaluation set.

## Criterion classification

| Metric | Result |
|---|---:|
| Labeled criterion checks | 8 |
| Accuracy | 1.00 |
| UNKNOWN incorrectly converted to MEETS | 0 |

The criterion results measure a conservative offline baseline on a small
synthetic set. The optional LLM judge remains disabled; deterministic metrics
are the primary evaluation.

# 11. Live API Verification After Key Update

On 2026-10-02, the updated API key stored in the ignored repository `.env` file
was tested without displaying or logging the key.

| Live check | Result |
|---|---|
| API-key source | Repository `.env` confirmed |
| Vision OCR | Passed; 151 characters returned from the handwritten note |
| Structured evidence extraction | Passed; 16 evidence records returned |
| Quote verification | Passed; all 16 live extraction quotes verified |
| Trial reranking | Passed; five scored candidates returned |
| Criterion assessment | Passed; NCT06412198 INC-01 returned `MEETS` with method `llm` |

The `.env` file is ignored by Git and the key is not present in the repository.

# 12. Testing and Engineering Status

The final test suite contains 151 passing tests. Coverage includes:

- Text-PDF ingestion with page preservation
- OCR and vision-response handling
- Evidence schemas and exact-quote verification
- Missing evidence remaining `UNKNOWN`
- ECOG conflict retention with both dates
- Trial snapshot and manifest validation
- Age parsing and age/sex rules
- Semantic chunk metadata
- BM25 and reciprocal-rank fusion behavior
- Exclusion-criterion direction
- Primary-cancer diagnosis mismatch and false-positive guards
- Prior-inhibitor evidence distinguished from mutation status
- ECOG "0 or 1" parsing with conflict preservation
- Prompt-injection detection
- Definitive eligibility-language blocking
- Streamlit evidence rendering

The final demo validator also passed with:

- 75 trials
- 1,542 criteria
- 16 evidence records
- 5 candidates
- 139 criterion assessments
- 12 trace steps
- 10 evaluation cases

The source repository is available at:

<https://github.com/raghavanlakshmi/TrialMatch_AI>

# 13. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Experience | Streamlit | Four-tab interactive demonstration |
| Orchestration | LangGraph | Controlled workflow and conditional route |
| AI | OpenAI Responses API | Vision OCR, structured extraction, reranking, criterion reasoning |
| Local embeddings | sentence-transformers | Semantic trial representations |
| Vector store | Chroma | Persistent cosine index |
| Lexical retrieval | rank-bm25 | Exact drug, biomarker, and disease matching |
| Fusion | Reciprocal rank fusion | Combines vector and BM25 ranks without score normalization |
| Document parsing | PyMuPDF | Page-preserving PDF extraction |
| Validation | Pydantic | Evidence, trial, chunk, and assessment schemas |
| Trial source | ClinicalTrials.gov | Public frozen study snapshot |
| Testing | pytest | Automated regression and safety tests |
| Version control | Git and GitHub | Reproducible code freeze and backup |

# 14. Demonstration Sequence

The shortest reliable demonstration uses **Replay saved SYN-001 run**:

1. Load the saved run in **Patient Documents**.
2. In **Evidence**, show the 16 evidence records and one verified quote.
3. Show ECOG 1 and ECOG 2 as a dated `POTENTIAL_CONFLICT`.
4. Show prior KRAS G12C inhibitor history as `UNKNOWN`.
5. In **Trial Matches**, open NCT06412198.
6. Show deterministic `RULE-AGE` and `RULE-SEX` assessments.
7. Show the live-validated `INC-01` LLM assessment and its evidence.
8. Show an `UNKNOWN` criterion.
9. In **Safety & Trace**, show the prompt-injection pass result.
10. Show all 12 traced workflow nodes.
11. End on the human-review disclaimer.

# 15. Limitations

- The prototype is not clinically validated and must not be used for real
  enrollment decisions.
- The evaluation set is small and synthetic.
- The extraction fixture uses tagged text and is not a general clinical NLP
  benchmark.
- The frozen trial corpus can become stale as recruitment status changes.
- OCR and handwriting transcription still require human review.
- Complex temporal and relational criteria may require evidence not present in
  the supplied documents.
- Hybrid retrieval did not outperform vector retrieval on the current 10-case
  fixture and requires further tuning.
- The saved replay combines live-validated components with a conservative
  offline baseline to keep the recorded demo reliable.
- The prototype does not implement EHR integration, identity matching,
  production authorization, consent, or institutional governance.

# 16. Future Work

- Expand the synthetic gold set and conduct blinded human review.
- Tune RRF candidate depth and add exclusion-aware ranking experiments.
- Add trial-snapshot freshness monitoring.
- Evaluate OCR across more scan and handwriting conditions.
- Add role-based access and an immutable audit log.
- Integrate only with authorized clinical data sources.
- Evaluate local models for narrow privacy-sensitive tasks.
- Add deployment controls appropriate to the target institution.

# 17. PowerPoint Presentation Outline

The following 12-slide structure can be copied directly into a competition
presentation.

## Slide 1 - Title

**Title:** TrialMatch AI<br>
**Subtitle:** Evidence-grounded AI-assisted clinical-trial prescreening

Include:

- Synthetic data prototype
- Human review required
- Presenter name and competition name

Suggested visual: the application title screen or four-tab interface.

## Slide 2 - The Problem

Key message: Trial prescreening requires staff to reconcile long eligibility
criteria with facts scattered across unstructured records.

Include:

- Fragmented PDFs, scans, pathology, labs, and notes
- Missing and contradictory evidence
- Manual, labor-intensive review

Suggested visual: four document icons converging on one reviewer.

## Slide 3 - The Solution

Key message: TrialMatch AI turns documents into auditable evidence and
criterion-level prescreening results.

Use this flow:

```text
Documents -> Evidence -> Hybrid retrieval -> Criteria -> Safety -> Human review
```

Suggested visual: simplified workflow diagram.

## Slide 4 - Evidence Grounding

Include:

- 16 evidence records
- Source file, page, date, and exact quote retained
- 16 of 16 saved quotes verified
- Missing information remains `UNKNOWN`

Suggested visual: screenshot of a Diagnosis or KRAS evidence card with the
supporting quote expanded.

## Slide 5 - Uncertainty by Design

Include:

- ECOG 1 and ECOG 2 both retained with dates
- One `POTENTIAL_CONFLICT`
- Prior KRAS G12C inhibitor history remains `UNKNOWN`
- No automatic reconciliation or negative inference

Suggested visual: side-by-side ECOG values plus the UNKNOWN card.

## Slide 6 - RAG and Trial Discovery

Include:

- 75 recruiting trials
- 55 candidate-role trials and 20 distractors
- 965 semantic chunks
- Vector retrieval + BM25 + RRF (`k=60`)
- Five candidates sent to reranking

Suggested visual: two ranked lists merging into five candidates.

## Slide 7 - Criterion-Level Reasoning

Include:

- 1,542 criteria parsed once with stable IDs
- 139 assessments in the saved run
- Age and sex checked with deterministic rules
- Free-text criteria assessed with cited evidence
- Four exact statuses

Suggested visual: screenshot showing `RULE-AGE`, `RULE-SEX`, and `INC-01`.

## Slide 8 - Safety and Human Control

Include:

- No final eligible/ineligible decision
- Unsupported conclusions become `UNKNOWN`
- Unverified quotes cannot support conclusions
- Source text is untrusted data
- Prompt-injection test passed
- Visible human-review disclaimer

Suggested visual: Safety & Trace tab with the green injection-defense message.

## Slide 9 - Agentic Workflow and Trace

Include:

- 12 controlled LangGraph nodes
- One meaningful conditional edge
- Latency and counts for every node
- Model and LLM-call tracking

Suggested visual: trace table or a vertical node diagram.

## Slide 10 - Evaluation Results

Use this table:

| Metric | Result |
|---|---:|
| Synthetic cases | 10 |
| Vector Recall@5 | 1.00 |
| BM25 Recall@5 | 0.75 |
| Hybrid RRF Recall@5 | 0.75 |
| Criterion accuracy | 1.00 on 8 labeled checks |
| UNKNOWN to MEETS errors | 0 |
| Automated tests | 151 passed |

State clearly that these are small synthetic-fixture results, not clinical
validation.

Suggested visual: simple bar chart for retrieval Recall@5.

## Slide 11 - Live Validation and Engineering Quality

Include:

- Updated API key validated successfully
- Vision OCR passed
- 16 live evidence records, all quotes verified
- Five live reranker scores returned
- Live LLM criterion assessment passed
- Saved replay prevents demo failure
- `.env` excluded from Git

Suggested visual: a checklist with green checkmarks.

## Slide 12 - Impact, Limitations, and Ask

Impact statement:

> TrialMatch AI helps research teams focus their review by organizing
> source-supported facts, relevant trials, missing information, and conflicts
> in one auditable workflow.

Include:

- Current scope: synthetic prototype
- Required next step: broader validation with authorized data and human review
- Final principle: assist research staff, never replace eligibility decisions

Suggested visual: human reviewer at the end of the workflow.

# 18. Slide-Ready Metrics

Use these numbers consistently across the presentation:

| Metric | Slide-ready value |
|---|---:|
| Patient evidence records | 16 |
| Verified saved quotes | 16/16 |
| Frozen recruiting trials | 75 |
| Deliberate distractors | 20 |
| Atomic eligibility criteria | 1,542 |
| Discovery chunks | 965 |
| Reranked candidates | 5 |
| Criterion assessments | 139 |
| Workflow nodes | 12 |
| Synthetic evaluation cases | 10 |
| Passing tests | 151 |

# 19. Competition Pitch

## 30-second version

Clinical-trial prescreening still requires people to reconcile complex
eligibility rules with patient information buried across unstructured records.
TrialMatch AI turns synthetic notes, reports, and scanned documents into
traceable patient evidence, uses hybrid RAG to find potentially relevant
trials, and performs criterion-level prescreening with citations, explicit
uncertainty, conflict detection, and mandatory human review. The result is not
an eligibility decision; it is an auditable first-pass review designed to help
research teams focus their time.

## One-sentence differentiator

TrialMatch AI connects messy documents to source-grounded evidence, hybrid
retrieval, criterion-level reasoning, explicit uncertainty, and human review in
one measurable workflow.

# 20. References

1. Unlu O, et al. Manual vs AI-Assisted Prescreening for Trial Eligibility
   Using Large Language Models - A Randomized Clinical Trial. *JAMA*.
   2025;333(12):1084-1087. <https://doi.org/10.1001/jama.2024.28047>
2. Natural language processing systems for eligibility prescreening in
   clinical research: systematic review. <https://pubmed.ncbi.nlm.nih.gov/34725689/>
3. Automated clinical-trial eligibility prescreening for pediatric oncology
   patients. <https://pubmed.ncbi.nlm.nih.gov/25881112/>
4. Automating Clinical Trial Matches Via Natural Language Processing of
   Synthetic Electronic Health Records and Clinical Trial Eligibility
   Criteria. AMIA 2024. <https://pubmed.ncbi.nlm.nih.gov/38827083/>
5. ClinicalTrials.gov public study registry. <https://clinicaltrials.gov/>

---

**Required disclaimer**

AI-assisted prescreening only. This system does not determine final
clinical-trial eligibility. Research staff must verify source records and trial
criteria.
