from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class VerificationStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


class CitationStatus(str, Enum):
    VALID = "VALID"
    PARTIALLY_VALID = "PARTIALLY_VALID"
    INVALID = "INVALID"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class CoverageStatus(str, Enum):
    NOT_STARTED = "not_started"
    PLANNED = "planned"
    RESEARCHING = "researching"
    IN_PROGRESS = "in_progress"
    PARTIAL = "partial"
    PARTIALLY_ANSWERED = "partially_answered"
    SUPPORTED = "supported"
    ANSWERED = "answered"
    UNRESOLVED = "unresolved"
    UNANSWERED = "unanswered"
    BLOCKED = "blocked"


class QueryIntent(BaseModel):
    original_query: str
    main_intent: str = "general_research"  # product_recommendation, scientific_evaluation, technical_comparison, etc.
    domain: str = "general"               # smartphones, laptops, healthcare_ai, cryptography, etc.
    topic: str = ""
    subtopics: List[str] = Field(default_factory=list)
    explicit_constraints: Dict[str, Any] = Field(default_factory=dict)  # e.g. {"max_budget": 30000, "currency": "INR", "geo": "India"}
    primary_criteria: List[str] = Field(default_factory=list)          # e.g. ["camera quality", "low light photo", "optical stabilization"]
    secondary_criteria: List[str] = Field(default_factory=list)        # e.g. ["battery life", "display", "software updates"]
    geographic_scope: Optional[str] = None                             # e.g. "India"
    time_sensitivity: Optional[str] = None                             # e.g. "current 2025-2026 market"
    expected_answer_format: str = "structured_recommendation"
    required_evidence_types: List[str] = Field(default_factory=list)
    excluded_topics: List[str] = Field(default_factory=list)           # e.g. ["electric vehicles", "automotive batteries", "gaming desktops"]
    ambiguities: List[str] = Field(default_factory=list)


class Source(BaseModel):
    source_id: str
    title: str
    url: str
    publisher: Optional[str] = None
    publication_date: Optional[str] = None
    published_at: Optional[str] = None
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_type: str = "web_article"  # official_specs, independent_review, tech_publication, academic, user_review, press_release
    snippet: str = ""
    extracted_content: str = ""
    retrieval_status: str = "FULL_TEXT_RETRIEVED"  # FULL_TEXT_RETRIEVED, SNIPPET_ONLY, failed
    error_message: Optional[str] = None
    relevance_score: float = 80.0     # 0 to 100
    credibility_assessment: str = "standard"  # strong, standard, weak, low
    relevant_questions: List[str] = Field(default_factory=list)
    relevant_question_ids: List[str] = Field(default_factory=list)
    relevant_excerpts: List[str] = Field(default_factory=list)
    accepted: bool = True
    rejection_reason: Optional[str] = None


class Evidence(BaseModel):
    claim_id: str
    evidence_id: Optional[str] = None
    claim_text: str
    claim: Optional[str] = None
    question_id: str
    research_question_id: Optional[str] = None
    source_ids: List[str] = Field(default_factory=list)
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    source_location: Optional[str] = None
    supporting_excerpts: List[str] = Field(default_factory=list)
    supporting_excerpt: Optional[str] = None
    evidence_type: str = "direct"  # direct vs inference vs calculation
    retrieval_status: str = "FULL_TEXT_RETRIEVED"
    publication_date: Optional[str] = None
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    extraction_confidence: float = 0.90
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_reason: str = "Awaiting evidence evaluation"


# Schema alias for Phase Four Evidence Ledger
EvidenceItem = Evidence


class VerifiedClaim(BaseModel):
    claim_id: str
    claim_text: str
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    verification_reason: str = ""
    reasoning_summary: str = ""
    limitations: List[str] = Field(default_factory=list)
    confidence: float = 0.85


class CitationValidation(BaseModel):
    citation_id: str
    claim_id: str
    source_id: str
    passage_verified: bool = True
    entity_match: bool = True
    claim_supported: bool = True
    citation_status: CitationStatus = CitationStatus.VALID
    reason: str = "The retrieved passage directly supports the associated statement."


class ContradictionRecord(BaseModel):
    conflict_id: str
    claim_a_id: str
    claim_b_id: Optional[str] = None
    claim_text: str = ""
    opposing_claim_text: Optional[str] = None
    entity: str = ""
    disagreement_description: str = ""
    source_a_id: Optional[str] = None
    source_b_id: Optional[str] = None
    source_a_date: Optional[str] = None
    source_b_date: Optional[str] = None
    methodology_comparison: Optional[str] = None
    resolution_status: str = "UNRESOLVED_DISCLOSED"  # RESOLVED, UNRESOLVED_DISCLOSED
    explanation: str = ""


class ResearchQuestion(BaseModel):
    question_id: str
    question_text: str
    question: Optional[str] = None  # alias for question_text
    importance: str = "high"       # high, medium, low
    dimension: Optional[str] = None  # e.g. "top_picks", "camera_quality", "benefits", "risks"
    reason: Optional[str] = None     # Why this question matters for answering user's query
    required_evidence: Optional[Union[str, List[str]]] = None
    preferred_source_types: List[str] = Field(default_factory=list)
    completion_criteria: Optional[Union[str, List[str]]] = None
    status: CoverageStatus = CoverageStatus.NOT_STARTED
    confidence: float = 0.0
    source_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    unresolved_reason: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.question:
            self.question = self.question_text
        if not self.question_text and self.question:
            self.question_text = self.question


class ResearchPlan(BaseModel):
    original_question: str
    query_intent: Optional[QueryIntent] = None
    subquestions: List[ResearchQuestion] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SearchRound(BaseModel):
    round_number: int
    round_type: str = "initial"  # initial, adaptive_follow_up
    queries_executed: List[str] = Field(default_factory=list)
    sources_found: int = 0
    gaps_targeted: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CriticalFailure(BaseModel):
    type: str  # "UNSUPPORTED_CLAIM", "INVALID_CITATION", "CONSTRAINT_VIOLATION", "OFF_TOPIC_SOURCE"
    claim_id: Optional[str] = None
    reason: str


class QualityGateResult(BaseModel):
    report_passed: bool = True
    passed: bool = True  # backward compatibility alias
    score: float = 1.0  # 0.0 to 1.0
    critical_failures: List[CriticalFailure] = Field(default_factory=list)
    checks: Dict[str, bool] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    repair_actions: List[str] = Field(default_factory=list)
    repairs_applied: List[str] = Field(default_factory=list)


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
    direct_answer: Optional[str] = None
    comparison_table_markdown: Optional[str] = None


class ResearchAudit(BaseModel):
    run_id: str
    original_query: str
    query_intent: Optional[QueryIntent] = None
    planned_questions: List[Dict[str, Any]] = Field(default_factory=list)
    queries_executed: List[str] = Field(default_factory=list)
    sources_retrieved_count: int = 0
    accepted_sources: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_sources: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_extracted_count: int = 0
    evidence_ledger: List[Dict[str, Any]] = Field(default_factory=list)
    verified_claims: List[Dict[str, Any]] = Field(default_factory=list)
    citation_validations: List[Dict[str, Any]] = Field(default_factory=list)
    conflicts_detected: List[Dict[str, Any]] = Field(default_factory=list)
    follow_up_searches: List[Dict[str, Any]] = Field(default_factory=list)
    unresolved_questions: List[Dict[str, Any]] = Field(default_factory=list)
    quality_gate: Optional[QualityGateResult] = None
    budget_summary: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ResearchRun(BaseModel):
    run_id: str
    original_question: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    status: str = "planning"
    query_intent: Optional[QueryIntent] = None
    research_plan: Optional[ResearchPlan] = None
    search_rounds: List[SearchRound] = Field(default_factory=list)
    sources: Dict[str, Source] = Field(default_factory=dict)
    rejected_sources: Dict[str, Source] = Field(default_factory=dict)
    evidence_records: Dict[str, Evidence] = Field(default_factory=dict)
    citation_validations: Dict[str, CitationValidation] = Field(default_factory=dict)
    contradictions: List[ContradictionRecord] = Field(default_factory=list)
    final_report: Optional[FinalReport] = None
    research_audit: Optional[ResearchAudit] = None
    quality_gate_result: Optional[QualityGateResult] = None
    execution_logs: List[Dict[str, Any]] = Field(default_factory=list)
