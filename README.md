# TrialMatch_AI
Turn fragmented, unstructured synthetic clinical documents into traceable patient evidence, find potentially relevant clinical trials, compare the evidence against eligibility criteria, and present an auditable prescreening summary for human review.

## Prototype scope

The disease area is metastatic colorectal cancer. All patient documents are
fictional and clearly marked as synthetic. The primary demonstration patient is
SYN-001, a 58-year-old female with metastatic colorectal adenocarcinoma and liver
metastases.

## Synthetic patient documents

The four source documents are in `data/patients/SYN-001/`:

| Document | Date | Contents |
| --- | --- | --- |
| `oncology_note.pdf` | 2026-03-10 | Age, sex, diagnosis and metastatic site on page 1; FOLFOX then FOLFIRI and ECOG 1 on page 2. |
| `pathology_report.pdf` | 2026-02-24 | BRAF wild type on page 1; KRAS G12C and microsatellite stable (MSS) on page 2. |
| `lab_report.pdf` | 2026-03-08 | ANC 2.1 x 10^9/L, hemoglobin 11.2 g/dL and creatinine 0.9 mg/dL on page 1. |
| `outside_referral_scan.png` | 2026-03-11 | Typed referral image with ECOG 2 on page 1. |

The differing ECOG values are deliberately retained for human review as a
POTENTIAL CONFLICT. Prior KRAS G12C inhibitor use is deliberately undocumented in
all four source documents and must remain UNKNOWN. This README describes the
fixture; it is not a patient evidence source.

To regenerate the demonstration documents from the repository folder, with the
virtual environment active:

```bash
python scripts/create_synthetic_patient.py --overwrite
```

The generator uses the existing PyMuPDF and Pillow dependencies.

## Deliberate potential conflict

The source documents contain two different values for the same ECOG fact. The
expected display is saved in
[`SYN-001_potential_conflict.txt`](data/sample_outputs/SYN-001_potential_conflict.txt):

```text
POTENTIAL CONFLICT
ECOG 1 — oncology_note.pdf · p2 — 2026-03-10
ECOG 2 — outside_referral_scan.png · p1 — 2026-03-11
Both values retained. Reviewer reconciles.
```

[`SYN-001_potential_conflict.json`](data/sample_outputs/SYN-001_potential_conflict.json)
records both expected values, source documents, pages, dates and exact supporting
quotes for use during later implementation and evaluation. These files are
expected demo outputs, not results from a running extraction workflow.

Any differing values for the same fact must be flagged as `POTENTIAL_CONFLICT`.
Dates provide context for the reviewer; they must not determine whether a
difference is a conflict or select a preferred value. The reviewer reconciles
the evidence.

## Deliberately missing fact

Prior KRAS G12C inhibitor use is undocumented in all four SYN-001 patient
documents. The documented KRAS G12C mutation and FOLFOX/FOLFIRI treatment history
do not establish whether a KRAS G12C inhibitor was previously used. Keep this
fact `UNKNOWN`; absence of documentation is not a negative treatment history.

The expected display is saved in
[`SYN-001_missing_fact.txt`](data/sample_outputs/SYN-001_missing_fact.txt):

```text
UNKNOWN
No supporting evidence found in supplied documents.
```

[`SYN-001_missing_fact.json`](data/sample_outputs/SYN-001_missing_fact.json)
records the expected `UNKNOWN` status with a null value and an empty evidence
list. It is an expected demo output used in evaluation.
There is no supporting quote or source attribution to invent for a missing fact.

[`src/config.py`](src/config.py) defines `FACTS_TO_LOOK_FOR` for age,
sex, diagnosis, KRAS status, MSI status, prior therapies, prior KRAS G12C inhibitor,
ECOG and ANC. The extraction and UI workflow displays any checklist item
with no supporting evidence as `UNKNOWN`.

Once the trial snapshot is frozen, confirm that the chosen demo trial actually
has a prior-KRAS-G12C-inhibitor criterion. If it does not, choose a different
deliberately missing fact that a real criterion in the snapshot asks about.

## Experimental handwritten input

[`handwritten_note.png`](data/patients/SYN-001/handwritten_note.png) is an
additional synthetic, single-page note dated 2026-03-10 for SYN-001. Its three
handwritten facts are:

```text
ECOG 1
FOLFOX completed
KRAS G12C+
```

The note was generated with the built-in image generation tool. The complete
[generation prompt](data/eval/SYN-001_handwritten_note_prompt.txt) and
[expected transcription](data/eval/SYN-001_handwritten_note_expected.txt) are
saved for reference. The expected transcription is an evaluation fixture,
not an OCR result or a patient evidence source. The four primary synthetic
documents remain the main source set; this image is an optional fifth input.
The existing PDF/typed-referral generator does not recreate this image.

Handwriting is experimental and requires human review. When image ingestion and
the UI are implemented, show whether each extracted quote was verified against
the transcribed page text. A quote is verified only if it appears word for word
in that text; a match does not establish that the handwriting was transcribed
correctly. Do not set `quote_verified` from the expected transcription.

## Document ingestion

[`src/document_ingestion.py`](src/document_ingestion.py) provides
`ingest_document(path)` and `ingest_documents(paths)`. Each returns a list of
Pydantic `DocumentPage` records defined in [`src/schemas.py`](src/schemas.py),
with `filename`, `page_number`, `text` and `extraction_method`.

- PDF text is extracted with PyMuPDF and keeps its original one-based page
  numbers. The extraction method is `PYMUPDF`.
- PDF pages with fewer than 30 extractable alphanumeric characters are marked
  `OCR_REQUIRED`. Any text that was extracted is retained. This configurable
  threshold is a heuristic; a short text page can also require review.
- PNG, JPG and JPEG images are validated and returned as page 1 with empty
  text and `OCR_REQUIRED` by default. Set `use_ocr=True` to run the vision
  transcription fallback.
- UTF-8 TXT files, including files with a UTF-8 BOM, return one page with
  extraction method `TXT`. Unicode and whitespace are preserved.

Missing files, unsupported types, corrupt files, password-protected PDFs and
invalid TXT encodings raise `DocumentIngestionError` with an actionable message.
Batch ingestion preserves input order and raises on an invalid file rather
than silently skipping it. Logs include source filenames and page counts,
never document text. No clinical reasoning occurs here; external API calls
occur only when `use_ocr=True` and a page needs transcription.

Example usage from the repository folder with the virtual environment active:

```python
from pathlib import Path
from src.document_ingestion import ingest_documents

paths = sorted(Path("data/patients/SYN-001").iterdir())
pages = ingest_documents(paths)
for page in pages:
    print(page.filename, page.page_number, page.extraction_method)
```

[`SYN-001_document_pages.json`](data/sample_outputs/SYN-001_document_pages.json)
contains actual ingestion results for the five prepared documents: five PDF
pages and two image pages awaiting OCR. It contains source text, not extracted
patient facts or completed clinical assessments.

Run the ingestion checks from the repository folder:

```bash
python -m pytest tests/test_document_ingestion.py -q
```

## OCR and vision transcription

[`src/ocr.py`](src/ocr.py) provides `extract_text_from_image(image_path) -> str`
using the OpenAI Responses API. The implementation follows the official
[images and vision guide](https://developers.openai.com/api/docs/guides/images-vision).
It sends a PNG/JPEG image with high detail and explicitly instructs the model:

```text
Transcribe the visible clinical text faithfully.
Do not interpret, summarize, correct, or add missing words.
If a word is unreadable, output [UNREADABLE].
```

Visible instructions in the image are treated as source text, never followed.
The transcription is returned unchanged, including `[UNREADABLE]` markers.
Expected evaluation transcripts are never used to fill missing words. Images
and text are not logged; requests use `store=False`. Handwritten text still
requires human review, and transcription does not set quote-verification flags.

Configure the repository `.env` with plain `NAME=value` lines, without Markdown
code fences or quotes around the whole file. Environment variables take
precedence over `.env`:

```dotenv
OPENAI_API_KEY=your_api_key_here
OPENAI_VISION_MODEL=gpt-4.1-mini
```

Replace the placeholder locally with your API key. The configurable default is
[`gpt-4.1-mini`](https://developers.openai.com/api/docs/models/gpt-4.1-mini), which
supports image input and the Responses API. Tesseract is not required for this
vision fallback. Text PDF pages continue to use PyMuPDF locally.

To enable transcription in the ingestion API:

```python
from src.document_ingestion import ingest_document
from src.ocr import extract_text_from_image

text = extract_text_from_image("data/patients/SYN-001/handwritten_note.png")
pages = ingest_document("data/patients/SYN-001/outside_referral_scan.png", use_ocr=True)
```

`ingest_documents(paths, use_ocr=True)` also supports batches. Only PDF pages
marked `OCR_REQUIRED` are rendered to PNG at 200 DPI for transcription; their
original filenames and one-based page numbers are preserved. Successfully
transcribed pages use extraction method `OPENAI_VISION`.

Missing credentials, authentication/permission errors, quota/rate limits,
timeouts, corrupt images, refusals, incomplete responses and empty results
raise clear errors. Ingestion adds the source filename and page to OCR errors.
No failed or partial response becomes patient evidence. Default ingestion
remains local and makes no API requests.

The existing seven-page sample JSON reflects local ingestion with OCR disabled.
The OCR tests exercise the installed SDK with mocked HTTP responses; they
do not make live API requests or establish transcription accuracy.

A live check using the configured API key successfully transcribed both
`outside_referral_scan.png` and `handwritten_note.png`. The seven combined page
records are saved in
[`SYN-001_document_pages_with_ocr.json`](data/sample_outputs/SYN-001_document_pages_with_ocr.json).
The referral retained ECOG 2 and its 2026-03-11 date. The handwritten note's full
transcription matched the expected fixture after whitespace/case normalization,
including ECOG 1, FOLFOX completed and KRAS G12C+. This single prepared-fixture
check does not replace human review of handwriting or future source pages.

The user confirmed review of the handwritten note on 2026-10-02. That
confirmation is recorded in
[`SYN-001_human_review.md`](data/eval/SYN-001_human_review.md).

```bash
python -m pytest tests/test_document_ingestion.py tests/test_ocr.py -q
```

## Evidence schema

[`src/schemas.py`](src/schemas.py) defines `EvidenceItem` with
eight fields: `category`, `value`, `normalized_value`, `date`, `source_file`,
`source_page`, `evidence_text` and `quote_verified`.

The schema accepts the eleven prototype categories: age, sex, diagnosis,
cancer_stage, metastatic_site, biomarker, prior_treatment, current_medication,
performance_status, lab and comorbidity. A fact requires a nonblank value,
source filename, positive integer source page and nonblank supporting quote.
The exact quote is retained without changing whitespace or case. Optional
normalized values and dates default to null when unavailable.

`quote_verified` defaults to false. Schema validation cannot establish whether
a quote appears in the source; the extraction workflow sets the
flag with a source-text check and never trusts a model-supplied flag. No confidence
field is included, and extra fields such as confidence scores are rejected.

```bash
python -m pytest tests/test_schemas.py -q
```

## Clinical evidence extraction

[`src/evidence_extraction.py`](src/evidence_extraction.py) provides
`extract_evidence(pages) -> list[EvidenceItem]` and
`verify_quotes(evidence, pages) -> list[EvidenceItem]`. Extraction uses
[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
with Pydantic. The model's response schema excludes `quote_verified` and
confidence scores; extra fields are rejected. The default model is
`gpt-4.1-mini`, configurable with `OPENAI_EXTRACTION_MODEL` in `.env` or the
environment.

Source pages are supplied as untrusted data. The prompt requires explicitly
supported facts, exact supporting quotes, accurate source filenames/pages and
documented dates. Each differing fact remains a separate record. Missing
checklist facts have no evidence records and display as `UNKNOWN` in the
patient evidence view; no negative treatment history is inferred from absent information.

Code recomputes every quote flag against the named source file and page after
whitespace and case normalization. Paraphrases, wrong sources/pages, quotes
containing `[UNREADABLE]`, and partial-number matches such as ECOG 1 versus
ECOG 10 are not verified. Unsupported dates are cleared to null. Unverified
records remain available for review; downstream consumers must check their
flags. Quote matching establishes text presence, not clinical correctness or
handwriting accuracy.

Duplicate source identities and pages still requiring OCR raise clear errors.
Empty input returns no facts. Missing credentials, invalid model output,
incomplete responses, refusals and API failures never produce substitute facts.
Logs contain record counts and source references, not patient text.

To extract from the saved seven-page transcription result:

```python
import json
from pathlib import Path
from src.evidence_extraction import extract_evidence
from src.schemas import DocumentPage

records = json.loads(
    Path("data/sample_outputs/SYN-001_document_pages_with_ocr.json").read_text(encoding="utf-8")
)
pages = [DocumentPage.model_validate(record) for record in records]
evidence = extract_evidence(pages)
```

A live SYN-001 extraction returned 16 facts with 16 source-matched quotes. The
actual records are saved in
[`SYN-001_evidence.json`](data/sample_outputs/SYN-001_evidence.json). ECOG 1
from the oncology note/handwritten note and ECOG 2 from the referral are retained
with their individual dates and sources. No prior KRAS G12C inhibitor history
was extracted. The prepared-fixture result is a development check, not an
eligibility assessment.

```bash
python -m pytest tests/test_extraction.py tests/test_schemas.py tests/test_document_ingestion.py tests/test_ocr.py -q
```

## Patient evidence view

From the repository folder, with the virtual environment active, launch:

```bash
python -m streamlit run app.py
```

The Streamlit view opens the prepared synthetic SYN-001 evidence without making
API calls. It displays all nine checklist facts and the additional documented
findings, with source filenames, page numbers, dates, quote-verification labels
and expandable exact quotes. Stored verification flags are recomputed against
the saved page/transcription text on each run.

The prepared patient shows 16 evidence records, one ECOG `POTENTIAL_CONFLICT`
and one `UNKNOWN` fact for prior KRAS G12C inhibitor history. Both ECOG values
and every supporting source remain visible, regardless of their dates. A
review filter keeps conflicts, unknowns and unverified quotes visible. The
source sidebar previews images, downloads source documents, and provides the
recorded handwritten transcription review.

[`src/evidence_view.py`](src/evidence_view.py) uses the prototype's named facts
to group evidence. It compares explicit scalar values without selecting a
preferred source. Equivalent KRAS G12C-positive wordings are treated as
equivalent for display while retaining both original records. Treatment
history, metastatic sites, medications and comorbidities can have multiple
complementary entries; they are retained as lists rather than treated as
conflicting scalar measurements. This grouping is scoped to the prepared
prototype and should be extended as the trial checklist evolves.

Unverified claims remain visible for review and do not fill an unknown
checklist fact by themselves. Patient values and quotes render as plain text.
Source downloads are restricted to the SYN-001 folder. Upload, trial
matching and criterion review are covered in the sections below.

```bash
python -m pytest tests/test_evidence_view.py tests/test_extraction.py tests/test_schemas.py tests/test_document_ingestion.py tests/test_ocr.py -q
```

## Frozen ClinicalTrials.gov snapshot

[`scripts/download_trials.py`](scripts/download_trials.py) downloads recruiting
studies from the ClinicalTrials.gov API v2 `/studies` endpoint, follows
`nextPageToken`, validates source records, deduplicates them by NCT ID, and
writes a reproducible local snapshot. The application never calls the service
at runtime.

The snapshot dated 2026-10-02 contains 75 unique records in
[`data/trials/trials.jsonl`](data/trials/trials.jsonl): 55 candidate records
from colorectal-cancer and KRAS G12C queries, plus 20 deliberate pancreatic and
KRAS G12D distractors. All 75 had `RECRUITING` status and nonblank full
eligibility text at download time. The
[`snapshot manifest`](data/trials/snapshot_manifest.json) records the source,
queries, counts, date, timezone, and selection notes.

Every record stores its NCT ID, title, status, conditions, summary, complete
eligibility criteria, source age strings, sex, locations, interventions, source
URL, last-update date, and snapshot date. Candidate/distractor roles describe
corpus construction only; they are not patient assessments or gold relevance
labels. Retrieved trial text remains untrusted data in downstream prompts.

The downloader refuses to replace an existing snapshot unless `--overwrite` is
explicitly supplied. To deliberately refresh it:

```powershell
python scripts/download_trials.py --snapshot-date YYYY-MM-DD --overwrite
```

Recruitment status can change after the recorded snapshot date. Review the
manifest whenever the snapshot is refreshed.

```powershell
python -m pytest tests/test_download_trials.py -q
```

## Validated trial records and searchable text

[`src/trial_loader.py`](src/trial_loader.py) loads the frozen JSONL snapshot and
validates every record with the Pydantic `TrialRecord` schema. It checks unique
NCT IDs, ClinicalTrials.gov source URLs, recruiting status, required text,
manifest count/date/role metadata, and valid age ranges.

Original ClinicalTrials.gov age strings remain in `minimum_age` and
`maximum_age`. Deterministic parsed values are added as `minimum_age_years` and
`maximum_age_years`. Years, months, weeks, days, hours, and minutes are
supported; missing limits remain null and malformed values raise a clear error.
These numeric fields drive the code-based age check.

Each trial also receives stable searchable text containing its NCT ID, title,
conditions, recruiting status, summary, and complete eligibility block. The 75
derived records are saved in
[`normalized_trials.jsonl`](data/trials/normalized_trials.jsonl). The raw
snapshot remains unchanged and auditable.

Regenerate the derived file after deliberately refreshing the snapshot:

```powershell
python -m src.trial_loader --overwrite
```

```powershell
python -m pytest tests/test_trial_loader.py -q
```

## Retrieval and criterion-level prescreening

`scripts/build_index.py` performs the index-time work. It deterministically
parses the frozen eligibility blocks into stable `INC-xx` and `EXC-xx` IDs in
`data/trials/criteria.json`, writes semantic discovery chunks to
`data/trials/chunks.jsonl`, and persists a Chroma cosine collection under
`data/trials/chroma/`. The current snapshot contains 1,542 criteria and 965
discovery chunks. Discovery contains trial summaries and inclusion criteria;
all exclusions remain available for criterion-level prescreening.

`src/retrieval.py` implements BM25 and `all-MiniLM-L6-v2` vector retrieval over
the same chunks. Reciprocal rank fusion uses rank positions with `k=60`, then
rolls chunk results up to trials using each trial's best chunk. The optional
LLM reranker receives only the compact patient summary and small candidate set.

`src/eligibility.py` checks age and sex with deterministic Python rules and can
assess free-text criteria with a structured LLM response. The LLM receives one
bounded callable tool, `get_source_evidence`, for a named supplied source page.
Offline replay uses a deliberately conservative rule baseline and leaves
unsupported facts `UNKNOWN`. Exclusion status follows the fixed direction:
`DOES_NOT_MEET` means the exclusion appears to apply. Trial summaries show
counts and one of the three review labels; they never declare eligibility.

Regenerate the immutable derived artifacts after intentionally changing the
trial snapshot:

```powershell
python scripts/build_index.py
```

## Workflow, safety, trace, and interface

`src/workflow.py` compiles the 12-node LangGraph from document intake through
human review. A conditional edge sends an empty retrieval result directly to
review. Every node records timestamps, latency, input/output counts, status,
errors, model metadata where applicable, and LLM-call counts.

`src/tools.py` contains bounded evidence, trial, criterion, search, and source
functions. `src/safety.py` blocks definitive enrollment language, downgrades
unsupported or unverified criterion conclusions, reports conflicts, displays
the required disclaimer, and flags instruction-like source text. The synthetic
`prompt_injection_test.txt` is treated only as document data.

The Streamlit app has Patient Documents, Evidence, Trial Matches, and Safety &
Trace tabs. It supports uploads and a pre-tested replay from
`data/sample_outputs/SYN-001_workflow.json`. The replay includes five candidate
trials, criterion-level evidence, an injection-defense result, and all 12 trace
records without making an API call.

## Evaluation and tests

`data/eval/gold_dataset.json` freezes 10 synthetic cases covering a clear
match, apparent exclusion, missing facts, ECOG conflict, scanned text,
paraphrase, irrelevant text, prompt injection, old/new evidence, and no
appropriate trial. Its criterion labels use IDs from the frozen criteria file.

Run the reproducible evaluation:

```powershell
python scripts/run_eval.py
```

The report at `data/eval/evaluation_report.json` compares vector, BM25, hybrid
RRF, and offline rerank retrieval; reports Recall@5 and expected ranks; and
includes extraction checks and a criterion confusion matrix. This is a small,
tagged synthetic fixture and conservative offline baseline, not a clinical
performance claim. The optional LLM judge is disabled by default and is never
the sole evaluator.

The full test suite covers ingestion, quote verification, missing evidence,
conflicts, age/sex, exclusion direction, RRF, retrieval metadata, injection
defense, output language, UI rendering, and frozen-data validation:

```powershell
python -m pytest -q
```

A local-model (Ollama) comparison was intentionally left out of scope because it
does not improve the core demonstration; it is listed as future work.

## Running the demo

Start the application from this repository with the project virtual
environment active:

```powershell
python -m streamlit run app.py
```

For a reliable demonstration, choose **Replay saved SYN-001 run**, then follow
the four tabs in order. The saved run exposes the ECOG conflict, missing prior
KRAS G12C inhibitor history, trial candidates, criterion evidence, injection
defense, and trace. The narrated demo video was recorded from this replay.

Run the final acceptance check:

```powershell
python scripts/validate_demo.py
```

The completed submission documentation is available as
[`TrialMatch_AI_Project_Documentation_Final.docx`](artifacts/TrialMatch_AI_Project_Documentation_Final.docx).
