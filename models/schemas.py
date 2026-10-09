from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class VerificationStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


class CoverageStatus(str, Enum):
    NOT_STARTED = "not_started"
    RESEARCHING = "researching"
    PARTIAL = "partial"
    SUPPORTED = "supported"
    UNRESOLVED = "unresolved"


class Source(BaseModel):
    source_id: str
    title: str
    url: str
    publisher: Optional[str] = None
    publication_date: Optional[str] = None
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snippet: str = ""
    extracted_content: str = ""
    retrieval_status: str = "success"  # "success", "failed", "snippet_only"
    error_message: Optional[str] = None


class Evidence(BaseModel):
    claim_id: str
    claim_text: str
    question_id: str
    source_ids: List[str] = Field(default_factory=list)
    supporting_excerpts: List[str] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_reason: str = "Awaiting evidence evaluation"


class ResearchQuestion(BaseModel):
    question_id: str
    question_text: str
    dimension: Optional[str] = None  # e.g. "benefits", "risks", "costs", "alternatives", "limitations"
    status: CoverageStatus = CoverageStatus.NOT_STARTED
    source_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    unresolved_reason: Optional[str] = None


class ResearchPlan(BaseModel):
    original_question: str
    subquestions: List[ResearchQuestion] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SearchRound(BaseModel):
    round_number: int
    round_type: str = "initial"  # "initial" or "adaptive_follow_up"
    queries_executed: List[str] = Field(default_factory=list)
    sources_found: int = 0
    gaps_targeted: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FinalReport(BaseModel):
    title: str
    executive_summary: str
    scope_and_methodology: str
    key_findings: List[str] = Field(default_factory=list)
    evidence_and_citations: List[Evidence] = Field(default_factory=list)
    conflicting_evidence: Optional[str] = None
    recommendations: List[str] = Field(default_factory=list)
    limitations_and_unresolved: List[str] = Field(default_factory=list)
    references: List[Source] = Field(default_factory=list)
    markdown_content: str = ""


class ResearchRun(BaseModel):
    run_id: str
    original_question: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    status: str = "planning"
    research_plan: Optional[ResearchPlan] = None
    search_rounds: List[SearchRound] = Field(default_factory=list)
    sources: Dict[str, Source] = Field(default_factory=dict)
    evidence_records: Dict[str, Evidence] = Field(default_factory=dict)
    final_report: Optional[FinalReport] = None
    execution_logs: List[Dict[str, Any]] = Field(default_factory=list)
