from __future__ import annotations
import threading
import uuid
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from models.schemas import (
    ResearchRun, ResearchPlan, ResearchQuestion, Source,
    Evidence, SearchRound, FinalReport, CoverageStatus, VerificationStatus,
    QueryIntent, QualityGateResult, ResearchAudit
)


class ResearchStore:
    """
    Thread-safe in-memory store for managing research runs, sources,
    evidence, coverage states, report outputs, and audit logs.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._runs: Dict[str, ResearchRun] = {}
        self._active_run_id: Optional[str] = None
        self._url_to_source_id: Dict[str, Dict[str, str]] = {}  # run_id -> (normalized_url -> source_id)

    @staticmethod
    def normalize_url(url: str) -> str:
        if not url:
            return ""
        try:
            parsed = urlparse(url.strip())
            scheme = parsed.scheme.lower() or "https"
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            
            path = parsed.path.rstrip("/")
            if not path:
                path = "/"

            tracking_params = {
                "utm_source", "utm_medium", "utm_campaign", "utm_term",
                "utm_content", "ref", "fbclid", "gclid", "msclkid", "source"
            }
            query_pairs = [
                (k, v) for k, v in parse_qsl(parsed.query)
                if k.lower() not in tracking_params
            ]
            clean_query = urlencode(sorted(query_pairs))
            normalized = urlunparse((scheme, netloc, path, "", clean_query, ""))
            return normalized
        except Exception:
            return url.strip().rstrip("/")

    def init_run(self, original_question: str) -> ResearchRun:
        with self._lock:
            run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            new_run = ResearchRun(
                run_id=run_id,
                original_question=original_question.strip(),
                status="planning",
            )
            self._runs[run_id] = new_run
            self._active_run_id = run_id
            self._url_to_source_id[run_id] = {}
            self.log_event("init", f"Initialized new research run for: '{original_question}'", run_id=run_id)
            return new_run

    def get_run(self, run_id: Optional[str] = None) -> Optional[ResearchRun]:
        with self._lock:
            target_id = run_id or self._active_run_id
            if not target_id:
                return None
            return self._runs.get(target_id)

    def set_query_intent(self, intent: QueryIntent, run_id: Optional[str] = None) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                raise ValueError("No active research run found.")
            run.query_intent = intent
            self.log_event("query_analysis", f"Analyzed query intent: {intent.main_intent} | Domain: {intent.domain}", run_id=run.run_id)

    def set_plan(self, plan: ResearchPlan, run_id: Optional[str] = None) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                raise ValueError("No active research run found.")
            run.research_plan = plan
            run.status = "plan_created"
            self.log_event("planning", f"Research plan generated with {len(plan.subquestions)} subquestions.", run_id=run.run_id)

    def add_source(
        self,
        title: str,
        url: str,
        snippet: str = "",
        extracted_content: str = "",
        publisher: Optional[str] = None,
        publication_date: Optional[str] = None,
        retrieval_status: str = "success",
        error_message: Optional[str] = None,
        source_type: str = "web_article",
        relevance_score: float = 80.0,
        credibility_assessment: str = "standard",
        accepted: bool = True,
        rejection_reason: Optional[str] = None,
        question_id: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Source:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                raise ValueError("No active research run found.")

            norm_url = self.normalize_url(url)
            run_url_map = self._url_to_source_id[run.run_id]

            if not publisher and url:
                try:
                    publisher = urlparse(url).netloc.replace("www.", "")
                except Exception:
                    publisher = "Web Source"

            # Check if source already exists
            if norm_url and norm_url in run_url_map:
                existing_id = run_url_map[norm_url]
                source = run.sources.get(existing_id) or run.rejected_sources.get(existing_id)
                if source:
                    if extracted_content and not source.extracted_content:
                        source.extracted_content = extracted_content
                        source.retrieval_status = retrieval_status
                    if question_id:
                        self._link_source_to_question(run, question_id, source.source_id)
                    return source

            count = len(run.sources) + len(run.rejected_sources) + 1
            source_id = f"SRC_{count:03d}"

            source = Source(
                source_id=source_id,
                title=title.strip() or f"Source {count}",
                url=url.strip(),
                publisher=publisher,
                publication_date=publication_date,
                published_at=publication_date,
                snippet=snippet.strip(),
                extracted_content=extracted_content.strip(),
                retrieval_status=retrieval_status,
                error_message=error_message,
                source_type=source_type,
                relevance_score=relevance_score,
                credibility_assessment=credibility_assessment,
                accepted=accepted,
                rejection_reason=rejection_reason,
                relevant_questions=[question_id] if question_id else []
            )

            if accepted:
                run.sources[source_id] = source
                if norm_url:
                    run_url_map[norm_url] = source_id
                if question_id:
                    self._link_source_to_question(run, question_id, source.source_id)
                self.log_event(
                    "source_collection",
                    f"Accepted source [{source_id}] '{source.title[:50]}' (Rel: {relevance_score}/100)",
                    run_id=run.run_id
                )
            else:
                run.rejected_sources[source_id] = source
                self.log_event(
                    "source_rejection",
                    f"Rejected source [{source_id}] '{source.title[:50]}': {rejection_reason}",
                    run_id=run.run_id
                )

            return source

    def add_rejected_source(
        self,
        title: str,
        url: str,
        snippet: str = "",
        relevance_score: float = 20.0,
        rejection_reason: str = "Off-topic or low relevance",
        question_id: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Source:
        return self.add_source(
            title=title,
            url=url,
            snippet=snippet,
            relevance_score=relevance_score,
            accepted=False,
            rejection_reason=rejection_reason,
            question_id=question_id,
            run_id=run_id
        )

    def _link_source_to_question(self, run: ResearchRun, question_id: str, source_id: str):
        if run.research_plan:
            for q in run.research_plan.subquestions:
                if q.question_id == question_id:
                    if source_id not in q.source_ids:
                        q.source_ids.append(source_id)
                    break

    def add_evidence(
        self,
        claim_text: str,
        question_id: str,
        source_ids: List[str],
        supporting_excerpts: List[str],
        verification_status: VerificationStatus = VerificationStatus.UNVERIFIED,
        verification_reason: str = "Awaiting evidence evaluation",
        evidence_type: str = "direct",
        extraction_confidence: float = 0.88,
        run_id: Optional[str] = None
    ) -> Evidence:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                raise ValueError("No active research run found.")

            clean_claim = re.sub(r"\s+", " ", claim_text).strip()
            norm_new = re.sub(r"[^\w\s]", "", clean_claim.lower()).strip()

            # Deduplicate against existing claims in this run
            for existing_ev in run.evidence_records.values():
                norm_existing = re.sub(r"[^\w\s]", "", existing_ev.claim_text.lower()).strip()
                if norm_new == norm_existing:
                    for sid in source_ids:
                        if sid not in existing_ev.source_ids:
                            existing_ev.source_ids.append(sid)
                    if run.research_plan:
                        for q in run.research_plan.subquestions:
                            if q.question_id == question_id and existing_ev.claim_id not in q.evidence_ids:
                                q.evidence_ids.append(existing_ev.claim_id)
                    return existing_ev

            count = len(run.evidence_records) + 1
            claim_id = f"claim_{count:03d}"
            ev_id = f"EVD_{count:03d}"

            evidence = Evidence(
                claim_id=claim_id,
                evidence_id=ev_id,
                claim_text=clean_claim,
                claim=clean_claim,
                question_id=question_id,
                research_question_id=question_id,
                source_ids=source_ids,
                source_id=source_ids[0] if source_ids else None,
                supporting_excerpts=supporting_excerpts,
                supporting_excerpt=supporting_excerpts[0] if supporting_excerpts else None,
                evidence_type=evidence_type,
                extraction_confidence=extraction_confidence,
                verification_status=verification_status,
                verification_reason=verification_reason.strip()
            )
            run.evidence_records[claim_id] = evidence

            # Link to question
            if run.research_plan:
                for q in run.research_plan.subquestions:
                    if q.question_id == question_id:
                        if claim_id not in q.evidence_ids:
                            q.evidence_ids.append(claim_id)
                        break

            self.log_event(
                "evidence_verification",
                f"Evaluated [{claim_id}]: {verification_status.value} - '{clean_claim[:60]}...'",
                run_id=run.run_id
            )
            return evidence

    def update_question_status(
        self,
        question_id: str,
        status: CoverageStatus,
        confidence: float = 0.0,
        unresolved_reason: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run or not run.research_plan:
                return
            for q in run.research_plan.subquestions:
                if q.question_id == question_id:
                    old_status = q.status
                    q.status = status
                    if confidence > 0.0:
                        q.confidence = confidence
                    if unresolved_reason:
                        q.unresolved_reason = unresolved_reason
                    self.log_event(
                        "coverage_tracker",
                        f"Question [{question_id}] coverage changed: {old_status.value} -> {status.value}",
                        run_id=run.run_id
                    )
                    break

    def add_search_round(self, search_round: SearchRound, run_id: Optional[str] = None) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return
            run.search_rounds.append(search_round)
            self.log_event(
                "search_round",
                f"Completed round {search_round.round_number} ({search_round.round_type}): "
                f"{len(search_round.queries_executed)} queries, {search_round.sources_found} sources found.",
                run_id=run.run_id
            )

    def set_final_report(self, report: FinalReport, run_id: Optional[str] = None) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return
            run.final_report = report
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc).isoformat()
            self.log_event("reporting", "Final research report successfully generated and saved.", run_id=run.run_id)

    def set_research_audit(self, audit: ResearchAudit, run_id: Optional[str] = None) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return
            run.research_audit = audit
            self.log_event("audit", f"Research audit log finalized ({len(audit.accepted_sources)} accepted, {len(audit.rejected_sources)} rejected).", run_id=run.run_id)

    def add_citation_validation(self, val: Any, run_id: Optional[str] = None) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return
            run.citation_validations[val.citation_id] = val
            self.log_event("citation_validation", f"Validated citation [{val.citation_id}]: {val.citation_status.value}", run_id=run.run_id)

    def add_contradiction(self, conflict: Any, run_id: Optional[str] = None) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return
            run.contradictions.append(conflict)
            self.log_event("contradiction_detected", f"Recorded conflict [{conflict.conflict_id}]: {conflict.disagreement_description[:60]}", run_id=run.run_id)

    def get_evidence_ledger(self, run_id: Optional[str] = None) -> List[Evidence]:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return []
            return list(run.evidence_records.values())

    def set_quality_gate(self, qg: QualityGateResult, run_id: Optional[str] = None) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return
            run.quality_gate_result = qg
            self.log_event("quality_gate", f"Quality gate passed: {qg.passed} (Score: {qg.score})", run_id=run.run_id)

    def log_event(
        self,
        stage: str,
        message: str,
        level: str = "INFO",
        details: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None
    ) -> None:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "message": message,
                "level": level,
                "details": details or {}
            }
            run.execution_logs.append(entry)

    def get_summary_stats(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return {}

            total_subquestions = len(run.research_plan.subquestions) if run.research_plan else 0
            supported_count = 0
            partial_count = 0
            unresolved_count = 0

            if run.research_plan:
                for q in run.research_plan.subquestions:
                    if q.status in (CoverageStatus.SUPPORTED, CoverageStatus.ANSWERED):
                        supported_count += 1
                    elif q.status in (CoverageStatus.PARTIAL, CoverageStatus.PARTIALLY_ANSWERED):
                        partial_count += 1
                    elif q.status in (CoverageStatus.UNRESOLVED, CoverageStatus.UNANSWERED, CoverageStatus.BLOCKED):
                        unresolved_count += 1

            total_claims = len(run.evidence_records)
            claim_status_counts = {
                VerificationStatus.SUPPORTED.value: 0,
                VerificationStatus.PARTIALLY_SUPPORTED.value: 0,
                VerificationStatus.CONTRADICTED.value: 0,
                VerificationStatus.UNVERIFIED.value: 0,
            }
            for ev in run.evidence_records.values():
                val = ev.verification_status.value
                claim_status_counts[val] = claim_status_counts.get(val, 0) + 1

            return {
                "run_id": run.run_id,
                "status": run.status,
                "total_subquestions": total_subquestions,
                "supported_subquestions": supported_count,
                "partial_subquestions": partial_count,
                "unresolved_subquestions": unresolved_count,
                "total_sources": len(run.sources),
                "rejected_sources_count": len(run.rejected_sources),
                "total_claims": total_claims,
                "claim_statuses": claim_status_counts,
                "search_rounds_count": len(run.search_rounds),
            }

    def export_json(self, run_id: Optional[str] = None) -> str:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                return "{}"
            return run.model_dump_json(indent=2)
