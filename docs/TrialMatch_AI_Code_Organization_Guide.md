# TrialMatch AI Code Organization Guide

## Overview

TrialMatch AI is organized as a processing pipeline. Patient documents enter the system, clinical evidence is extracted and verified, relevant trials are retrieved, eligibility criteria are assessed, and the results pass through safety checks before appearing in the Streamlit interface.

**Workflow:**

> Patient documents → Ingestion and OCR → Evidence extraction → Quote verification → Conflict detection → Patient search query → Trial retrieval → Candidate reranking → Criteria loading → Eligibility assessment → Safety review → Human review

## Main project folders

| Location | Description |
|---|---|
| [`app.py`](../app.py) | Main Streamlit application and user interface. |
| [`src/`](../src/) | Core application logic, including ingestion, retrieval, matching, and safety checks. |
| [`scripts/`](../scripts/) | Commands for preparing data, building the search index, evaluating results, and validating the demo. |
| [`data/`](../data/) | Patient documents, trial snapshots, processed criteria, indexes, and evaluation datasets. |
| [`tests/`](../tests/) | Automated tests for the individual modules and safety rules. |
| [`artifacts/`](../artifacts/) | Generated reports, screenshots, documents, and saved demonstration results. |
| [`deploy/`](../deploy/) | Lightweight files used to deploy the Streamlit demonstration. |
| [`requirements.txt`](../requirements.txt) | Python packages required to run and test the project. |
| [`AGENTS.md`](../AGENTS.md) | Instructions and safety rules for AI coding assistants working in the repository. |

## Runtime workflow

The runtime workflow is coordinated by [`src/workflow.py`](../src/workflow.py). It runs the following steps.

### 1. Ingest patient documents

[`src/document_ingestion.py`](../src/document_ingestion.py) reads PDFs, text files, and images and converts them into individual document pages that the rest of the system can process consistently.

### 2. Run OCR when required

[`src/ocr.py`](../src/ocr.py) transcribes scanned or handwritten content using vision-based OCR. This allows handwritten notes and image-only documents to enter the same evidence pipeline as normal text.

### 3. Extract patient evidence

[`src/evidence_extraction.py`](../src/evidence_extraction.py) converts document text into structured facts such as diagnosis, age, sex, treatment history, performance status, and laboratory results. Each fact retains its source document, page, and supporting quote.

### 4. Verify the extracted quotes

The evidence extraction module confirms that every supporting quote appears in the referenced source text. A fact without an exact supporting quote is marked unverified instead of being treated as established evidence.

### 5. Detect conflicts and missing information

[`src/evidence_view.py`](../src/evidence_view.py) groups related patient facts and identifies contradictory values, unknown information, and evidence requiring human confirmation. Conflicting facts are preserved rather than automatically resolved.

### 6. Build the patient search query

[`src/retrieval.py`](../src/retrieval.py) creates a concise patient summary from verified evidence. This summary becomes the query used to search the frozen clinical-trial collection.

### 7. Retrieve relevant clinical trials

The retrieval module combines keyword search, semantic vector search, and reciprocal-rank fusion. This hybrid approach identifies candidate trials that match both the exact medical wording and the broader meaning of the patient summary.

### 8. Rerank the candidates

The same retrieval module reorders candidate trials according to how closely each trial corresponds to the patient's verified diagnosis and clinical details. This places the most useful trials near the top of the review list.

### 9. Load eligibility criteria

[`src/criteria.py`](../src/criteria.py) parses trial eligibility text into individual inclusion and exclusion criteria. Criteria are prepared during indexing and loaded for the retrieved trials during assessment.

### 10. Assess each criterion

[`src/eligibility.py`](../src/eligibility.py) compares every trial criterion with the available patient evidence. It uses deterministic checks for structured fields such as age and sex, plus guarded reasoning for free-text requirements.

Each criterion receives one of four statuses:

- **MEETS:** The available evidence supports the patient's position relative to the criterion.
- **DOES_NOT_MEET:** The available evidence conflicts with the criterion.
- **UNKNOWN:** The documents do not contain enough evidence to determine the result.
- **POTENTIAL_CONFLICT:** Available evidence contains contradictory or uncertain values that require review.

This module also contains the added rules for cancer diagnosis mismatch, inhibitor exposure, ECOG status, exclusion mapping, organ function, and line of therapy.

### 11. Apply safety checks

[`src/safety.py`](../src/safety.py) prevents unsupported or overconfident conclusions. It checks for prompt injection, incomplete evidence, exclusion criteria, prior treatment requirements, organ-function requirements, investigator-dependent decisions, and other cases that require conservative handling.

### 12. Prepare the human review

The workflow packages the final candidate list, criterion assessments, supporting evidence, conflicts, safety flags, and workflow trace. The Streamlit application presents these results for human verification and does not make a definitive eligibility decision.

## Supporting modules

| Module | Purpose |
|---|---|
| [`src/schemas.py`](../src/schemas.py) | Defines the Pydantic data models shared across the project, including document pages, evidence items, trials, criteria, and assessments. |
| [`src/trial_loader.py`](../src/trial_loader.py) | Loads, validates, and normalizes downloaded ClinicalTrials.gov records. |
| [`src/source_viewer.py`](../src/source_viewer.py) | Displays source documents beside extracted quotes and highlights the evidence location. |
| [`src/tools.py`](../src/tools.py) | Provides controlled access to patient evidence, trial records, criteria, and source pages. |
| [`src/observability.py`](../src/observability.py) | Records workflow steps, execution status, timing, result counts, and errors. |
| [`src/config.py`](../src/config.py) | Stores project paths, environment settings, model configuration, and other shared options. |
| [`src/workflow.py`](../src/workflow.py) | Connects all runtime stages in a LangGraph workflow and records the execution trace. |

## Data-preparation and validation scripts

The files in [`scripts/`](../scripts/) prepare the application and verify its output.

### 1. Create the demonstration patient

`scripts/create_synthetic_patient.py` creates the synthetic patient files used in the demonstration. Synthetic data makes the workflow reproducible without exposing real patient information.

### 2. Download and freeze trial data

`scripts/download_trials.py` downloads a controlled clinical-trial snapshot. Freezing the dataset keeps retrieval and evaluation results reproducible.

### 3. Build the search index

`scripts/build_index.py` validates trial records, parses eligibility criteria, creates searchable trial chunks, and builds the retrieval index.

### 4. Create evaluation data

`scripts/create_eval_dataset.py` prepares evaluation cases and expected answers for repeatable testing.

### 5. Evaluate extraction and retrieval

`scripts/run_eval.py` measures whether the system extracts the expected patient facts and retrieves the expected trials.

### 6. Evaluate criterion assessments

`scripts/run_criterion_eval.py` compares criterion-level predictions with labeled evaluation data, including the held-out evaluation set.

### 7. Refresh the saved demonstration

`scripts/run_live_assessment.py` runs the current workflow and saves an updated demonstration result for the Streamlit application.

### 8. Validate the final demonstration

`scripts/validate_demo.py` verifies that the saved run contains the expected patient evidence, candidate trials, assessments, safety results, and human-review information.

## Streamlit interface

[`app.py`](../app.py) is the main local user interface. It lets the reviewer inspect uploaded documents, extracted evidence, source quotes, trial matches, criterion assessments, safety flags, and the workflow trace.

[`deploy/streamlit_app.py`](../deploy/streamlit_app.py) is the lightweight deployment entry point used for the hosted replay demonstration.

## Automated tests

The [`tests/`](../tests/) folder contains focused tests for document ingestion, OCR, evidence extraction, retrieval, eligibility rules, safety guards, source viewing, trial loading, schemas, and live assessment behavior.

These tests verify individual components. The demo validator then checks that the components work together as a complete end-to-end workflow.

## Organization summary

The repository separates responsibilities into three main layers:

1. **Preparation:** Scripts create the synthetic data, freeze trial records, build the index, and prepare evaluation datasets.
2. **Core processing:** Modules in `src/` ingest documents, extract evidence, retrieve trials, assess criteria, and apply safety rules.
3. **Presentation and validation:** Streamlit displays the results, while automated tests and evaluation scripts confirm that the workflow behaves as expected.
