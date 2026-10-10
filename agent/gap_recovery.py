from __future__ import annotations
import re
from typing import List, Dict, Any, Optional, Tuple
from models.schemas import ResearchQuestion, CoverageStatus, VerificationStatus, QueryIntent, ResearchRun


class GapRecoveryEngine:
    """
    Evaluates research question completion criteria and formulates
    highly targeted follow-up searches for unresolved research questions.
    """
    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds

    def evaluate_question_status(
        self,
        question: ResearchQuestion,
        run: ResearchRun,
        is_final_round: bool = False
    ) -> Tuple[CoverageStatus, float, Optional[str], Optional[str]]:
        """
        Returns (status, confidence, missing_fact, gap_cause)
        """
        q_evidence = [
            ev for ev in run.evidence_records.values()
            if ev.question_id == question.question_id
        ]

        supported = [e for e in q_evidence if e.verification_status == VerificationStatus.SUPPORTED]
        partial = [e for e in q_evidence if e.verification_status == VerificationStatus.PARTIALLY_SUPPORTED]
        contradicted = [e for e in q_evidence if e.verification_status == VerificationStatus.CONTRADICTED]
        unverified = [e for e in q_evidence if e.verification_status == VerificationStatus.UNVERIFIED]

        # 1. Sufficient verified evidence
        if len(supported) >= 2 or (len(supported) >= 1 and len(partial) >= 1):
            return (CoverageStatus.ANSWERED, 0.92, None, None)

        # 2. Partial verified evidence
        if len(supported) == 1 or len(partial) >= 1:
            if is_final_round:
                return (CoverageStatus.ANSWERED, 0.80, None, None)
            missing = f"Secondary comparative metrics for {question.dimension or 'this feature'}"
            cause = "missing_sources"
            return (CoverageStatus.PARTIALLY_ANSWERED, 0.65, missing, cause)

        # 3. Contradicted evidence without consensus
        if contradicted:
            missing = f"Consensus resolution on {question.question_text}"
            cause = "conflicting_evidence"
            st = CoverageStatus.UNANSWERED if is_final_round else CoverageStatus.PARTIALLY_ANSWERED
            return (st, 0.40, missing, cause)

        # 4. Irrelevant sources rejected
        rejected_for_q = [
            s for s in run.rejected_sources.values()
            if question.question_id in s.relevant_questions or question.question_id in s.relevant_question_ids
        ]
        if rejected_for_q and not q_evidence:
            missing = f"Direct evidence satisfying criteria: {question.completion_criteria or question.question_text}"
            cause = "irrelevant_sources"
            st = CoverageStatus.UNANSWERED if is_final_round else CoverageStatus.PARTIALLY_ANSWERED
            return (st, 0.20, missing, cause)

        # 5. Missing / No sources
        missing = f"Verified facts addressing {question.question_text}"
        cause = "missing_sources"
        st = CoverageStatus.UNANSWERED if is_final_round else CoverageStatus.PARTIALLY_ANSWERED
        return (st, 0.15, missing, cause)

    def formulate_follow_up_query(
        self,
        question: ResearchQuestion,
        intent: Optional[QueryIntent],
        missing_fact: Optional[str] = None
    ) -> str:
        topic = intent.topic if intent and intent.topic else "smartphone"
        geo = intent.geographic_scope if intent and intent.geographic_scope else ""
        dim = question.dimension or "review"
        criteria = question.required_evidence or ""
        if isinstance(criteria, list):
            criteria = " ".join(criteria)

        # Target the missing aspect specifically
        query_parts = [topic, geo, dim, criteria]
        clean_terms = [p.strip() for p in query_parts if p.strip()]
        return " ".join(clean_terms)[:90]
