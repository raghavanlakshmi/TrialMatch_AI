# TrialMatch AI demo recording guide

Use the saved replay so network latency cannot interrupt the recording. The
application must be running at `http://127.0.0.1:8501`.

## Before recording

1. From the repository folder, run `python scripts/validate_demo.py`.
2. Run `python -m pytest -q` and confirm all tests pass.
3. Start the app with `python -m streamlit run app.py` if it is not running.
4. Open the app in a clean browser window at 100% zoom.
5. Close notifications and any window that could expose an API key.
6. Select **Replay saved SYN-001 run** once and rehearse the sequence below.

## Recording sequence and narration

Aim for a concise recording and follow the competition's published length
limit.

1. **Patient Documents**
   - Say: “TrialMatch AI performs research-trial prescreening with synthetic
     patient records. It does not determine final eligibility.”
   - Click **Replay saved SYN-001 run**.
   - Explain that this is the pre-tested output of the same workflow used for
     uploads and avoids a live API dependency during the recording.

2. **Evidence**
   - Show that each fact retains its source file, page, date, supporting quote,
     and quote-verification status.
   - Show the ECOG potential conflict. Point out ECOG 1 and ECOG 2 with their
     separate dates and sources.
   - Show `UNKNOWN` for prior KRAS G12C inhibitor history. Say: “The system
     does not turn a missing mention into a negative fact.”

3. **Trial Matches**
   - Explain that retrieval uses a frozen 75-trial ClinicalTrials.gov snapshot,
     vector search, BM25, and reciprocal rank fusion.
   - Open the first candidate, NCT06412198. Show **Potential match - needs
     verification** with 4 Meets, 0 Does Not Meet, 46 Unknown, and 1 Potential
     Conflict.
   - Show `RULE-AGE` and `RULE-SEX` as deterministic checks.
   - Show an `llm` criterion and its cited patient evidence.
   - Show `INC-11` as `POTENTIAL_CONFLICT` for ECOG 0 or 1, and `EXC-02` as
     `UNKNOWN` because KRAS mutation does not prove prior inhibition therapy.
   - Show an `UNKNOWN` criterion. Explain that inclusion and exclusion criteria
     use stable IDs parsed once at index time.

4. **Safety & Trace**
   - Show the prompt-injection pass result. Say: “The instruction embedded in a
     patient document remained untrusted data and did not control the model.”
   - Show all 12 workflow trace rows, latency, counts, model information, and
     the human-review disclaimer.

5. **Close**
   - Say: “TrialMatch AI retrieves candidates and organizes evidence for
     research staff. Every source and uncertainty remains visible, and final
     trial eligibility stays with the study team.”

## After recording

1. Watch the exported video from beginning to end.
2. Confirm no API key, personal information, or desktop notification appears.
3. Confirm the disclaimer, conflict, missing fact, criterion evidence,
   injection defense, and trace are readable.
4. Export within the competition's required format and duration.
5. Upload through the competition submission page and verify playback there.

The upload and account-specific submission fields require the project owner's
manual action.
