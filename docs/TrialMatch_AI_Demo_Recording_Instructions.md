---
title: "TrialMatch AI Demo Recording Instructions"
subtitle: "Fast step-by-step walkthrough"
author: "TrialMatch AI"
date: "October 2, 2026"
---

# Purpose

This guide gives the shortest reliable sequence for recording the TrialMatch AI
demonstration. Use the saved SYN-001 replay so network latency or an API failure
cannot interrupt the recording. The complete walkthrough should take about
three to five minutes.

Throughout the recording, describe the application as a **research-trial
prescreening tool**. Do not describe the patient as definitively eligible or
ineligible.

# 1. Open the application

Open PowerShell in:

```text
C:\Users\laksh\Documents\MasteringGenAI\TrialMatch AI\TrialMatch_AI
```

If the app is not already running, enter:

```powershell
..\.venv\Scripts\python.exe -m streamlit run app.py
```

Open this address in a browser:

<http://127.0.0.1:8501>

# 2. Load the prepared demonstration

1. Select the **Patient Documents** tab.
2. Click **Replay saved SYN-001 run**.
3. Wait for this confirmation:

   ```text
   Loaded the pre-tested saved run; no API call was made.
   ```

Suggested narration:

> TrialMatch AI performs research-trial prescreening using synthetic patient
> records. This replay contains a previously validated run and avoids API
> delays during the demonstration.

# 3. Show the extracted evidence

Select the **Evidence** tab.

At the top, point out these three values:

- **Evidence records:** 16
- **Potential conflicts:** 1
- **Unknown facts:** 1

Explain that each evidence card includes:

- The extracted value
- Source filename
- Page number
- Document date
- Quote-verification status
- A **Supporting quote** expander

Open one **Supporting quote** expander under **Diagnosis** or **KRAS status**.

Suggested narration:

> Every extracted fact retains its source file, page, date, and exact
> supporting quote. Quote verification is performed against the source text.

# 4. Show the ECOG conflict

Remain in the **Evidence** tab and find:

```text
Performance status (ECOG)
```

Show both values:

- `ECOG 1`
- `ECOG 2`

Also show the **Potential conflict** warning and the separate sources:

- `oncology_note.pdf`, page 2, dated 2026-03-10
- `outside_referral_scan.png`, page 1, dated 2026-03-11

Suggested narration:

> The documents contain different ECOG values. The system retains both values
> and marks a potential conflict instead of choosing one automatically.

# 5. Show the missing treatment fact

Still in **Evidence**, scroll to:

```text
Prior KRAS G12C inhibitor
```

Show the message:

```text
UNKNOWN - no supporting evidence found in supplied documents.
```

Suggested narration:

> KRAS G12C mutation status does not prove prior treatment with a KRAS G12C
> inhibitor. Because treatment history is missing, the result remains UNKNOWN.

This is one of the most important safety behaviors in the demonstration.

# 6. Show trial retrieval

Select **Trial Matches**. Five candidate-trial expanders should be visible.

Open the first candidate:

```text
NCT06412198
```

Point out:

- The label **Potential match - needs verification**
- Meets count: 4
- Does Not Meet count: 0
- Unknown count: 46
- Potential Conflict count: 1
- The reranking explanation

Suggested narration:

> Candidates come from a frozen 75-trial ClinicalTrials.gov snapshot.
> Discovery combines vector retrieval and BM25 using reciprocal rank fusion,
> followed by reranking.

Do not say that the patient is eligible or ineligible.

# 7. Show deterministic age and sex checks

Inside the expanded trial, find the first two assessments:

```text
RULE-AGE
RULE-SEX
```

Both should identify their method as `rule`.

Suggested narration:

> Age and sex are checked deterministically against the structured trial
> fields. They are not delegated to the language model.

# 8. Show an LLM criterion assessment

Inside `NCT06412198`, find:

```text
INC-01
```

It should show:

```text
method: llm
status: MEETS
```

Show the patient evidence cited below the assessment.

Suggested narration:

> Free-text eligibility criteria are assessed individually. The result cites
> the exact patient evidence used and remains subject to human verification.

`MEETS` describes only that individual criterion. It is not an overall patient
eligibility decision.

# 9. Show an UNKNOWN criterion

Within the same trial, show `INC-11` as `POTENTIAL_CONFLICT`. Explain that ECOG
1 meets the trial's ECOG 0-or-1 requirement while ECOG 2 does not, so both
documented outcomes remain visible.

Then find `EXC-02`, **Prior KRASG12C inhibition therapy**. It should be
`UNKNOWN`: mutation evidence does not prove that the patient received a KRAS
G12C inhibitor. There is no need to read every other unknown criterion.

Suggested narration:

> Missing documentation stays UNKNOWN. The system does not use general medical
> knowledge to invent patient facts.

# 10. Show prompt-injection defense

Select **Safety & Trace** and find the green message:

```text
Prompt-injection test passed: source instruction was treated as untrusted data.
```

Suggested narration:

> One synthetic source document contains an instruction telling the system to
> ignore the criteria and mark the patient eligible. The application treats
> that sentence as untrusted document content, so it cannot control the
> workflow.

# 11. Show the workflow trace

On **Safety & Trace**, show the trace table. It contains these 12 steps:

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

Point out the status, latency, input/output counts, LLM-call count, and model
information.

Suggested narration:

> Every workflow stage records its status, latency, input and output counts,
> and model usage, making the result auditable.

# 12. Finish on the disclaimer

Show the visible disclaimer:

```text
AI-assisted prescreening only.
This system does not determine final clinical-trial eligibility.
Research staff must verify source records and trial criteria.
```

Closing narration:

> TrialMatch AI retrieves candidate trials and organizes source-supported
> evidence for research staff. It preserves missing information and conflicts,
> while final eligibility remains with the study team.

# Final recording checklist

Before uploading, confirm all of the following:

- [ ] The API key never appeared on screen.
- [ ] ECOG 1 and ECOG 2 were both visible.
- [ ] Prior KRAS G12C inhibitor history showed `UNKNOWN`.
- [ ] At least one supporting source quote was expanded.
- [ ] `RULE-AGE`, `RULE-SEX`, and `INC-01` were shown.
- [ ] The prompt-injection defense result was visible.
- [ ] The workflow trace was visible.
- [ ] The human-review disclaimer was visible.
- [ ] The patient was never described as definitively eligible or ineligible.
- [ ] The exported video meets the competition's duration and file-format rules.
- [ ] The uploaded video was played back successfully from the submission page.
