from __future__ import annotations
import threading
import uuid
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from models.schemas import (
    ResearchRun, ResearchPlan, ResearchQuestion, Source,
    Evidence, SearchRound, FinalReport, CoverageStatus, VerificationStatus
)


class ResearchStore:
    """
    Thread-safe in-memory store for managing research runs, sources,
    evidence, coverage states, and report outputs.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._runs: Dict[str, ResearchRun] = {}
        self._active_run_id: Optional[str] = None
        self._url_to_source_id: Dict[str, Dict[str, str]] = {}  # run_id -> (normalized_url -> source_id)

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normalize URL by removing tracking query parameters (utm_*, ref, etc.),
        lowercasing host, and stripping trailing slash.
        """
        if not url:
            return ""
        try:
            parsed = urlparse(url.strip())
            # Lowercase scheme and netloc
            scheme = parsed.scheme.lower() or "https"
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            
            path = parsed.path.rstrip("/")
            if not path:
                path = "/"

            # Filter out tracking query parameters
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
        question_id: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Source:
        """
        Deduplicates sources using normalized URLs and preserves stable source IDs.
        """
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                raise ValueError("No active research run found.")

            norm_url = self.normalize_url(url)
            run_url_map = self._url_to_source_id[run.run_id]

            # Check if source already exists
            if norm_url and norm_url in run_url_map:
                existing_id = run_url_map[norm_url]
                source = run.sources[existing_id]
                # Update content if existing had no content and new has content
                if extracted_content and not source.extracted_content:
                    source.extracted_content = extracted_content
                    source.retrieval_status = retrieval_status
                if question_id:
                    self._link_source_to_question(run, question_id, source.source_id)
                return source

            # Create new source
            count = len(run.sources) + 1
            source_id = f"SRC_{count:03d}"
            
            # Extract publisher from domain if not provided
            if not publisher and url:
                try:
                    publisher = urlparse(url).netloc.replace("www.", "")
                except Exception:
                    publisher = "Web Source"

            source = Source(
                source_id=source_id,
                title=title.strip() or f"Source {count}",
                url=url.strip(),
                publisher=publisher,
                publication_date=publication_date,
                snippet=snippet.strip(),
                extracted_content=extracted_content.strip(),
                retrieval_status=retrieval_status,
                error_message=error_message,
            )
            run.sources[source_id] = source
            if norm_url:
                run_url_map[norm_url] = source_id

            if question_id:
                self._link_source_to_question(run, question_id, source.source_id)

            self.log_event(
                "source_collection",
                f"Stored source [{source_id}] '{source.title[:60]}' ({retrieval_status})",
                run_id=run.run_id
            )
            return source

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
        run_id: Optional[str] = None
    ) -> Evidence:
        with self._lock:
            run = self.get_run(run_id)
            if not run:
                raise ValueError("No active research run found.")

            count = len(run.evidence_records) + 1
            claim_id = f"claim_{count:03d}"

            evidence = Evidence(
                claim_id=claim_id,
                claim_text=claim_text.strip(),
                question_id=question_id,
                source_ids=source_ids,
                supporting_excerpts=supporting_excerpts,
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
                f"Evaluated [{claim_id}]: {verification_status.value} - '{claim_text[:60]}...'",
                run_id=run.run_id
            )
            return evidence

    def update_question_status(
        self,
        question_id: str,
        status: CoverageStatus,
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
            researching_count = 0
            not_started_count = 0

            if run.research_plan:
                for q in run.research_plan.subquestions:
                    if q.status == CoverageStatus.SUPPORTED:
                        supported_count += 1
                    elif q.status == CoverageStatus.PARTIAL:
                        partial_count += 1
                    elif q.status == CoverageStatus.UNRESOLVED:
                        unresolved_count += 1
                    elif q.status == CoverageStatus.RESEARCHING:
                        researching_count += 1
                    elif q.status == CoverageStatus.NOT_STARTED:
                        not_started_count += 1

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
