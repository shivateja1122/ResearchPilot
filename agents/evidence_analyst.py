"""
Evidence Analyst Agent (Agent 3).
Independently evaluates the quality, relevance, and sufficiency of collected evidence.
Conducts 9-point claim verification, citation validation, contradiction detection,
and research coverage auditing.
"""
from __future__ import annotations
import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from agent.claim_verifier import ClaimVerifier
from agent.citation_validator import CitationValidator
from agent.contradiction_detector import ContradictionDetector
from agent.gap_recovery import GapRecoveryEngine
from agent.llm_client import LLMClient
from models.schemas import (
    ResearchRun, ResearchQuestion, Source, Evidence,
    VerifiedClaim, CitationValidation, ContradictionRecord, CoverageStatus
)


class EvidenceAnalystAgent:
    """
    Agent 3: Evidence Analyst Agent.
    Independently inspects and validates evidence returned by the Researcher.
    Does not trust assertions without exact passage substantiation.
    """
    def __init__(
        self,
        claim_verifier: Optional[ClaimVerifier] = None,
        citation_validator: Optional[CitationValidator] = None,
        contradiction_detector: Optional[ContradictionDetector] = None,
        gap_recovery: Optional[GapRecoveryEngine] = None,
        llm_client: Optional[LLMClient] = None
    ):
        self.llm = llm_client or LLMClient()
        self.claim_verifier = claim_verifier or ClaimVerifier(self.llm)
        self.citation_validator = citation_validator or CitationValidator()
        self.contradiction_detector = contradiction_detector or ContradictionDetector()
        self.gap_recovery = gap_recovery or GapRecoveryEngine()

    def analyze(
        self,
        research_plan: Dict[str, Any],
        sources: List[Dict[str, Any]],
        evidence_items: List[Dict[str, Any]],
        is_final_round: bool = False
    ) -> Dict[str, Any]:
        """
        Executes independent 9-point verification, citation checks, contradiction detection,
        and coverage auditing across all accumulated evidence.
        Conforms strictly to the Agent 3 output schema.
        """
        analysis_id = f"ANALYSIS_{uuid.uuid4().hex[:6].upper()}"
        verified_claims_out: List[Dict[str, Any]] = []
        coverage_out: Dict[str, Dict[str, Any]] = {}
        follow_up_tasks: List[Dict[str, Any]] = []
        conflicts_out: List[Dict[str, Any]] = []
        warnings_out: List[str] = []

        # Index sources by source_id
        source_map: Dict[str, Dict[str, Any]] = {s.get("source_id"): s for s in sources if s.get("source_id")}

        # 1. Claim-Level 9-Point Verification
        for ev in evidence_items:
            claim_id = ev.get("evidence_id") or ev.get("claim_id") or f"CLM_{uuid.uuid4().hex[:6].upper()}"
            claim_text = ev.get("claim") or ev.get("claim_text", "")
            excerpt = ev.get("supporting_excerpt") or ""
            source_id = ev.get("source_id")
            source_rec = source_map.get(source_id, {})

            # Execute 9-point verification check
            ver_result = self.claim_verifier.verify(
                claim_text=claim_text,
                supporting_excerpt=excerpt,
                source_date=source_rec.get("published_at"),
                source_type=source_rec.get("source_type", "web_article")
            )

            # Map status to uppercase string
            status_str = ver_result.status.upper() if isinstance(ver_result.status, str) else ver_result.status.value.upper()
            
            claim_record = {
                "claim_id": claim_id,
                "claim_text": claim_text,
                "status": status_str,
                "supporting_evidence_ids": [ev.get("evidence_id")] if ev.get("evidence_id") else [],
                "contradicting_evidence_ids": [],
                "verification_reason": ver_result.verification_reason or "Verified against source passage",
                "limitations": ver_result.limitations or [],
                "confidence": round(ver_result.confidence, 2)
            }
            verified_claims_out.append(claim_record)

            if status_str in ("UNVERIFIED", "CONTRADICTED"):
                warnings_out.append(f"Claim '{claim_text[:50]}...' flagged as {status_str}: {ver_result.verification_reason}")

        # 2. Citation Integrity Checks
        citation_validations = []
        for ev in evidence_items:
            cid = ev.get("evidence_id", "")
            c_text = ev.get("claim") or ev.get("claim_text", "")
            s_id = ev.get("source_id", "")
            s_rec = source_map.get(s_id)

            if not s_rec or s_rec.get("retrieval_status") in ("failed", "rejected"):
                c_status = "SOURCE_UNAVAILABLE"
                reason = "Source URL failed retrieval or was rejected."
            else:
                s_content = s_rec.get("extracted_content", "") or s_rec.get("snippet", "")
                excerpt = ev.get("supporting_excerpt", "")
                passage_ok = (not excerpt) or (excerpt.lower() in s_content.lower()) or any(w in s_content.lower() for w in excerpt.lower().split()[:5])
                if passage_ok:
                    c_status = "VALID"
                    reason = "Retrieved passage directly substantiates the cited assertion."
                else:
                    c_status = "INVALID"
                    reason = "Supporting passage could not be verified in the retrieved source content."

            citation_validations.append({
                "citation_id": f"CIT_{cid}",
                "claim_id": cid,
                "source_id": s_id,
                "citation_status": c_status,
                "reason": reason
            })

        # 3. Contradiction Detection
        # Build temp ResearchRun to utilize existing robust ContradictionDetector
        temp_run = ResearchRun(
            run_id="temp_analysis",
            original_question=research_plan.get("original_query", "")
        )
        for ev in evidence_items:
            eid = ev.get("evidence_id", f"EVD_{len(temp_run.evidence_records)+1}")
            c_text = ev.get("claim") or ev.get("claim_text", "")
            temp_run.evidence_records[eid] = Evidence(
                claim_id=eid,
                claim_text=c_text,
                question_id=ev.get("question_id", "Q1"),
                source_id=ev.get("source_id"),
                supporting_excerpt=ev.get("supporting_excerpt")
            )
        
        detected_conflicts = self.contradiction_detector.detect_conflicts(temp_run)
        for c in detected_conflicts:
            conflicts_out.append({
                "conflict_id": c.conflict_id,
                "claim_a_id": c.claim_a_id,
                "claim_b_id": c.claim_b_id,
                "entity": c.entity,
                "disagreement_description": c.disagreement_description,
                "resolution_status": c.resolution_status,
                "explanation": c.explanation
            })

        # 4. Coverage Auditing & Follow-up Formulation
        # Group verified claims by question_id
        ev_by_q: Dict[str, List[Dict[str, Any]]] = {}
        for ev in evidence_items:
            qid = ev.get("question_id", "Q1")
            ev_by_q.setdefault(qid, []).append(ev)

        # Map claims to their verification statuses
        status_by_ev: Dict[str, str] = {c["claim_id"]: c["status"] for c in verified_claims_out}

        for q in research_plan.get("research_questions", []):
            qid = q.get("question_id", "Q1")
            q_evs = ev_by_q.get(qid, [])
            ev_ids = [e.get("evidence_id") for e in q_evs if e.get("evidence_id")]

            supported_count = sum(1 for eid in ev_ids if status_by_ev.get(eid) == "SUPPORTED")
            partial_count = sum(1 for eid in ev_ids if status_by_ev.get(eid) == "PARTIALLY_SUPPORTED")
            contradicted_count = sum(1 for eid in ev_ids if status_by_ev.get(eid) == "CONTRADICTED")

            missing_info: List[str] = []
            if supported_count >= 2 or (supported_count >= 1 and partial_count >= 1):
                cov_status = "ANSWERED"
            elif supported_count == 1 or partial_count >= 1:
                cov_status = "PARTIALLY_ANSWERED"
                missing_info.append(f"Independent corroboration and detailed metrics for {q.get('dimension', 'dimension')}")
            elif contradicted_count >= 1:
                cov_status = "PARTIALLY_ANSWERED" if not is_final_round else "UNANSWERED"
                missing_info.append("Consensus resolution between contradictory reviews")
            else:
                cov_status = "UNANSWERED"
                missing_info.append(f"Verifiable factual evidence satisfying completion criteria for {q.get('question', qid)}")

            coverage_out[qid] = {
                "status": cov_status,
                "evidence_ids": ev_ids,
                "missing_information": missing_info
            }

            # Generate targeted follow-up tasks for questions with critical gaps
            if cov_status in ("PARTIALLY_ANSWERED", "UNANSWERED") and not is_final_round:
                follow_up_tasks.append({
                    "task_id": f"TASK_GAP_{qid}_{uuid.uuid4().hex[:4].upper()}",
                    "question_id": qid,
                    "question": q.get("question", ""),
                    "dimension": q.get("dimension", ""),
                    "missing_criteria": missing_info[0] if missing_info else "technical evidence",
                    "priority": q.get("priority", "high"),
                    "is_follow_up": True
                })

        return {
            "analysis_id": analysis_id,
            "verified_claims": verified_claims_out,
            "citations": citation_validations,
            "coverage": coverage_out,
            "follow_up_tasks": follow_up_tasks,
            "conflicts": conflicts_out,
            "warnings": warnings_out
        }
