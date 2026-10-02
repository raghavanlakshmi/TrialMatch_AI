"""Configuration for the synthetic metastatic colorectal cancer demo."""


DEFAULT_VISION_MODEL = "gpt-4.1-mini"
DEFAULT_EXTRACTION_MODEL = "gpt-4.1-mini"

CLINICAL_TRIALS_API_URL = "https://clinicaltrials.gov/api/v2/studies"
TRIAL_SNAPSHOT_MIN_RECORDS = 50
TRIAL_SNAPSHOT_MAX_RECORDS = 100
TRIAL_QUERIES = (
    {
        "name": "colorectal_kras_g12c", "role": "candidate",
        "params": {"query.cond": "colorectal cancer", "query.term": "KRAS G12C"},
        "limit": 15,
    },
    {
        "name": "colorectal_recruiting", "role": "candidate",
        "params": {"query.cond": "colorectal cancer"}, "limit": 40,
    },
    {
        "name": "pancreatic_distractors", "role": "distractor",
        "params": {"query.cond": "pancreatic cancer"}, "limit": 10,
        "selection_filter": "exclude_colorectal_conditions",
    },
    {
        "name": "kras_g12d_distractors", "role": "distractor",
        "params": {"query.term": "KRAS G12D"}, "limit": 10,
        "selection_filter": "g12d_without_g12c",
    },
)


# Stable fact keys and display labels for the evidence view. A checklist item
# with no supporting evidence must remain UNKNOWN; never fill it with a
# negative value or invent a source quote. The extraction/UI workflow will
# use this checklist when those modules are implemented.
FACTS_TO_LOOK_FOR = {
    "age": "Age",
    "sex": "Sex",
    "diagnosis": "Diagnosis",
    "kras_status": "KRAS status",
    "msi_status": "MSI status",
    "prior_therapies": "Prior therapies",
    "prior_kras_g12c_inhibitor": "Prior KRAS G12C inhibitor",
    "ecog": "ECOG",
    "anc": "Absolute neutrophil count (ANC)",
}
