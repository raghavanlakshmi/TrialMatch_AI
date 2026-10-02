"""Validated records shared by the document-processing modules."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentPage(BaseModel):
    """Source text from one page, or a page awaiting OCR transcription."""

    filename: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    text: str
    extraction_method: str


EvidenceCategory = Literal[
    "age",
    "sex",
    "diagnosis",
    "cancer_stage",
    "metastatic_site",
    "biomarker",
    "prior_treatment",
    "current_medication",
    "performance_status",
    "lab",
    "comorbidity",
]


class EvidenceItem(BaseModel):
    """An explicitly supported fact with provenance and its exact source quote.

    Source matching is performed separately; validation alone never verifies
    a quote. The extraction agent must not supply quote_verified. Code sets
    that flag after checking the named source page (step 18).
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    category: EvidenceCategory
    value: str = Field(min_length=1)
    normalized_value: str | None = None
    date: str | None = None
    source_file: str = Field(min_length=1)
    source_page: int = Field(ge=1, strict=True)
    evidence_text: str = Field(min_length=1, description="Exact quote copied from source page text")
    quote_verified: bool = Field(default=False, strict=True)

    @field_validator("value", "source_file", "evidence_text")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evidence values, source filenames, and quotes must not be blank.")
        # Preserve whitespace and case in the original value and exact quote.
        return value


class TrialRecord(BaseModel):
    """A validated trial from the frozen ClinicalTrials.gov snapshot."""

    model_config = ConfigDict(extra="forbid")

    nct_id: str = Field(pattern=r"^NCT\d{8}$")
    title: str = Field(min_length=1)
    overall_status: Literal["RECRUITING"]
    conditions: list[str] = Field(min_length=1)
    brief_summary: str | None = None
    eligibility_criteria: str = Field(min_length=1)
    minimum_age: str | None = None
    maximum_age: str | None = None
    minimum_age_years: float | None = Field(default=None, ge=0)
    maximum_age_years: float | None = Field(default=None, ge=0)
    sex: Literal["ALL", "FEMALE", "MALE"]
    locations: list[dict[str, Any]]
    interventions: list[dict[str, Any]] = Field(default_factory=list)
    source_url: str = Field(pattern=r"^https://clinicaltrials\.gov/study/NCT\d{8}$")
    last_updated: str | None = None
    snapshot_date: str
    selection_role: Literal["candidate", "distractor"]
    matched_queries: list[str] = Field(min_length=1)

    @field_validator("title", "eligibility_criteria")
    @classmethod
    def require_nonblank_trial_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Trial title and eligibility criteria must not be blank.")
        return value


CriterionType = Literal["inclusion", "exclusion"]
AssessmentStatus = Literal["MEETS", "DOES_NOT_MEET", "UNKNOWN", "POTENTIAL_CONFLICT"]


class TrialCriterion(BaseModel):
    """One stable, index-time criterion from the frozen trial snapshot."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(pattern=r"^(INC|EXC)-\d{2,3}$")
    type: CriterionType
    text: str = Field(min_length=1)


class CriterionAssessment(BaseModel):
    """Auditable prescreening result for one criterion."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    criterion_text: str = Field(min_length=1)
    criterion_type: CriterionType
    status: AssessmentStatus
    method: Literal["rule", "llm"]
    patient_evidence: list[EvidenceItem]
    explanation: str = Field(min_length=1)


class RetrievalChunk(BaseModel):
    """A semantic discovery chunk and its required metadata."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    nct_id: str = Field(pattern=r"^NCT\d{8}$")
    section: Literal["trial_summary", "inclusion"]
    criterion_id: str | None = None
    source: Literal["ClinicalTrials.gov"] = "ClinicalTrials.gov"
