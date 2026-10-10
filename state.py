"""
authoritative Research State definition for ResearchPilot AI Multi-Agent Workflow.
Provides typed, validated state management with provenance tracking and thread isolation.
"""
from __future__ import annotations
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from models.schemas import (
    QueryIntent, Source, Evidence, VerifiedClaim,
    CitationValidation, ContradictionRecord, QualityGateResult,
    FinalReport, ResearchAudit, CoverageStatus, VerificationStatus, ResearchRun
)


class ResearchState(BaseModel):
    """
    Central authoritative research state for a single research run.
    Passed between specialized agents and updated by the central orchestrator.
    """
    run_id: str = Field(default_factory=lambda: f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}")
    original_query: str
    context: Optional[str] = None
    query_intent: Optional[Dict[str, Any]] = None
    research_plan: Optional[Dict[str, Any]] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_sources: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    verified_claims: List[Dict[str, Any]] = Field(default_factory=list)
    coverage: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    follow_up_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    citation_validations: List[Dict[str, Any]] = Field(default_factory=list)
    final_report: Optional[Dict[str, Any]] = None
    quality_status: str = "IN_PROGRESS"  # IN_PROGRESS, PASSED, PASSED_WITH_LIMITATIONS, FAILED
    quality_gate_result: Optional[Dict[str, Any]] = None
    research_audit: Optional[Dict[str, Any]] = None
    audit_log: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    retry_counts: Dict[str, int] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def log_event(self, agent_name: str, event_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Appends a structured event to the audit trail."""
        self.audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent_name,
            "event_type": event_type,
            "message": message,
            "details": details or {}
        })

    def add_error(self, agent_name: str, error_message: str, error_type: str = "GENERIC_ERROR") -> None:
        """Records an error without corrupting state."""
        self.errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent_name,
            "error_type": error_type,
            "message": error_message
        })
        self.log_event(agent_name, "ERROR", error_message, {"error_type": error_type})

    def add_source(self, source_dict: Dict[str, Any]) -> str:
        """Adds a source if not already registered (deduplicating by URL)."""
        url = source_dict.get("url", "").strip()
        for existing in self.sources:
            if existing.get("url") == url:
                return existing.get("source_id", "")
        
        if not source_dict.get("source_id"):
            source_dict["source_id"] = f"SRC_{len(self.sources) + 1:03d}"
        
        self.sources.append(source_dict)
        return source_dict["source_id"]

    def add_rejected_source(self, rejected_dict: Dict[str, Any]) -> None:
        """Records a rejected source with explicit reason."""
        if not rejected_dict.get("source_id"):
            rejected_dict["source_id"] = f"REJ_{len(self.rejected_sources) + 1:03d}"
        self.rejected_sources.append(rejected_dict)

    def add_evidence_item(self, evidence_dict: Dict[str, Any]) -> str:
        """Registers an atomic evidence item to the ledger with deduplication."""
        claim_text = evidence_dict.get("claim", "") or evidence_dict.get("claim_text", "")
        for existing in self.evidence:
            ex_claim = existing.get("claim", "") or existing.get("claim_text", "")
            if ex_claim.lower().strip() == claim_text.lower().strip():
                return existing.get("evidence_id", "")
        
        if not evidence_dict.get("evidence_id"):
            evidence_dict["evidence_id"] = f"EVD_{len(self.evidence) + 1:03d}"
        
        self.evidence.append(evidence_dict)
        return evidence_dict["evidence_id"]

    def update_coverage(self, question_id: str, status: str, evidence_ids: List[str], missing_info: List[str] = None) -> None:
        """Updates coverage status for a specific subquestion."""
        self.coverage[question_id] = {
            "status": status,
            "evidence_ids": evidence_ids,
            "missing_information": missing_info or []
        }

    def increment_retry(self, key: str) -> int:
        """Increments and returns retry count for a subquestion or step."""
        current = self.retry_counts.get(key, 0) + 1
        self.retry_counts[key] = current
        return current

    def to_research_run(self) -> ResearchRun:
        """
        Converts ResearchState to ResearchRun for backward compatibility with existing views.
        """
        from models.schemas import ResearchPlan, ResearchQuestion, SearchRound, FinalReport, ResearchAudit
        
        plan_obj = None
        if self.research_plan:
            subqs = []
            for q in self.research_plan.get("research_questions", []):
                subqs.append(ResearchQuestion(
                    question_id=q.get("question_id", "Q1"),
                    question_text=q.get("question", ""),
                    importance=q.get("priority", "high"),
                    required_evidence=q.get("required_evidence", []),
                    completion_criteria=q.get("completion_criteria", []),
                    status=CoverageStatus(self.coverage.get(q.get("question_id"), {}).get("status", "planned").lower()) if self.coverage.get(q.get("question_id")) else CoverageStatus.PLANNED
                ))
            plan_obj = ResearchPlan(
                original_question=self.original_query,
                subquestions=subqs
            )

        sources_dict = {}
        for s in self.sources:
            sid = s.get("source_id", f"SRC_{len(sources_dict)+1:03d}")
            sources_dict[sid] = Source(
                source_id=sid,
                title=s.get("title", ""),
                url=s.get("url", ""),
                publisher=s.get("publisher"),
                published_at=s.get("published_at"),
                snippet=s.get("snippet", ""),
                extracted_content=s.get("extracted_content", ""),
                retrieval_status=s.get("retrieval_status", "FULL_TEXT_RETRIEVED"),
                relevance_score=s.get("relevance_score", 80.0),
                accepted=s.get("accepted", True),
                rejection_reason=s.get("rejection_reason")
            )

        rej_dict = {}
        for r in self.rejected_sources:
            rid = r.get("source_id", f"REJ_{len(rej_dict)+1:03d}")
            rej_dict[rid] = Source(
                source_id=rid,
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("snippet", ""),
                relevance_score=r.get("relevance_score", 20.0),
                accepted=False,
                rejection_reason=r.get("rejection_reason", "Low relevance")
            )

        ev_dict = {}
        for e in self.evidence:
            eid = e.get("evidence_id", f"EVD_{len(ev_dict)+1:03d}")
            c_text = e.get("claim", "") or e.get("claim_text", "")
            stat_val = e.get("verification_status", "unverified")
            if isinstance(stat_val, str):
                try:
                    stat_enum = VerificationStatus(stat_val.lower())
                except Exception:
                    stat_enum = VerificationStatus.UNVERIFIED
            else:
                stat_enum = stat_val

            ev_dict[eid] = Evidence(
                claim_id=eid,
                evidence_id=eid,
                claim_text=c_text,
                claim=c_text,
                question_id=e.get("question_id", "Q1"),
                source_id=e.get("source_id"),
                source_ids=[e.get("source_id")] if e.get("source_id") else [],
                supporting_excerpt=e.get("supporting_excerpt"),
                supporting_excerpts=[e.get("supporting_excerpt")] if e.get("supporting_excerpt") else [],
                evidence_type=e.get("evidence_type", "direct"),
                retrieval_status=e.get("retrieval_status", "FULL_TEXT_RETRIEVED"),
                verification_status=stat_enum,
                verification_reason=e.get("verification_reason", "")
            )

        qg_obj = None
        if self.quality_gate_result:
            try:
                qg_obj = QualityGateResult(**self.quality_gate_result)
            except Exception:
                pass

        final_rep = None
        if self.final_report:
            try:
                final_rep = FinalReport(**self.final_report)
            except Exception:
                pass

        audit_obj = None
        if self.research_audit:
            try:
                audit_obj = ResearchAudit(**self.research_audit)
            except Exception:
                pass

        return ResearchRun(
            run_id=self.run_id,
            original_question=self.original_query,
            created_at=self.created_at,
            completed_at=self.completed_at,
            status="completed" if self.completed_at else "in_progress",
            query_intent=QueryIntent(**self.query_intent) if self.query_intent else None,
            research_plan=plan_obj,
            sources=sources_dict,
            rejected_sources=rej_dict,
            evidence_records=ev_dict,
            final_report=final_rep,
            research_audit=audit_obj,
            quality_gate_result=qg_obj,
            execution_logs=self.audit_log
        )
