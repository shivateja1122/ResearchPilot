from __future__ import annotations
import time
from typing import Optional, Callable, Dict, Any, List
from models.schemas import (
    ResearchRun, ResearchPlan, ResearchQuestion, SearchRound,
    CoverageStatus, VerificationStatus, FinalReport
)
from storage.research_store import ResearchStore
from tools.web_search import WebSearchTool
from tools.page_extractor import PageExtractor
from tools.source_filter import SourceFilter
from agent.planner import ResearchPlanner
from agent.analyst import ResearchAnalyst
from agent.report_generator import ReportGenerator
from agent.llm_client import LLMClient


class ResearchOrchestrator:
    """
    Coordinates planning, web research, page extraction, evidence verification,
    the adaptive research loop, and report generation with explicit budget limits.
    """
    def __init__(
        self,
        store: Optional[ResearchStore] = None,
        llm_client: Optional[LLMClient] = None,
        max_research_rounds: int = 2,
        max_follow_up_searches: int = 4,
        search_timeout: int = 10,
        page_timeout: int = 8
    ):
        self.store = store or ResearchStore()
        self.llm = llm_client or LLMClient()
        self.planner = ResearchPlanner(self.llm)
        self.analyst = ResearchAnalyst(self.llm)
        self.report_generator = ReportGenerator(self.llm)
        self.search_tool = WebSearchTool(timeout_seconds=search_timeout)
        self.page_extractor = PageExtractor(timeout_seconds=page_timeout)
        
        self.max_research_rounds = max_research_rounds
        self.max_follow_up_searches = max_follow_up_searches

    def run_research(
        self,
        research_question: str,
        progress_callback: Optional[Callable[[str, str, float, Dict[str, Any]], None]] = None
    ) -> ResearchRun:
        """
        Executes end-to-end evidence-driven research workflow.
        """
        def notify(stage: str, msg: str, pct: float, extra: Optional[Dict[str, Any]] = None):
            if progress_callback:
                progress_callback(stage, msg, pct, extra or {})

        # 1. Initialize Run
        run = self.store.init_run(research_question)
        run_id = run.run_id
        notify("init", f"Initiating research investigation: '{research_question}'", 0.05, {"run_id": run_id})

        # 2. Plan Generation (FR-01)
        notify("planning", "Generating structured research plan with 4-6 dimension-focused subquestions...", 0.15)
        plan = self.planner.create_plan(research_question)
        self.store.set_plan(plan, run_id=run_id)
        notify("planning_done", f"Created {len(plan.subquestions)} tracked research subquestions.", 0.20, {"plan": plan})

        # 3. Initial Web Research (Round 1) (FR-02)
        notify("search_round_1", "Starting Round 1: Gathering web sources across all subquestions...", 0.25)
        round_1_queries = []
        new_sources_count = 0

        for idx, subq in enumerate(plan.subquestions, start=1):
            subq.status = CoverageStatus.RESEARCHING
            self.store.update_question_status(subq.question_id, CoverageStatus.RESEARCHING, run_id=run_id)

            query = f"{research_question} {subq.question_text}"
            round_1_queries.append(query)
            notify("searching", f"Searching for {subq.question_id}: '{subq.question_text[:50]}...'", 0.25 + (idx * 0.04))

            raw_results = self.search_tool.search(query, max_results=4)
            filtered = SourceFilter.filter_and_rank(raw_results, max_sources=3)

            for item in filtered:
                url = item["url"]
                # Attempt page extraction
                extracted = self.page_extractor.extract(url)
                retrieval_status = extracted["status"]
                content = extracted.get("content", "")
                err = extracted.get("error_message")

                # If full extraction failed, fallback to snippet
                if retrieval_status == "failed" and item.get("snippet"):
                    retrieval_status = "snippet_only"
                    content = item["snippet"]

                source = self.store.add_source(
                    title=item.get("title") or extracted.get("title") or "Source",
                    url=url,
                    snippet=item.get("snippet", ""),
                    extracted_content=content,
                    retrieval_status=retrieval_status,
                    error_message=err,
                    question_id=subq.question_id,
                    run_id=run_id
                )
                new_sources_count += 1

                # 4. Evidence Extraction & Verification (FR-03)
                verified_claims = self.analyst.extract_claims_with_verification(subq, source)
                for claim_text, excerpt, ver_status, reason in verified_claims:
                    self.store.add_evidence(
                        claim_text=claim_text,
                        question_id=subq.question_id,
                        source_ids=[source.source_id],
                        supporting_excerpts=[excerpt],
                        verification_status=ver_status,
                        verification_reason=reason,
                        run_id=run_id
                    )

        # Record Search Round 1
        self.store.add_search_round(
            SearchRound(
                round_number=1,
                round_type="initial",
                queries_executed=round_1_queries,
                sources_found=new_sources_count,
                gaps_targeted=[]
            ),
            run_id=run_id
        )

        # 5. Evaluate Initial Coverage (FR-04)
        notify("evaluating_coverage", "Evaluating evidence coverage across subquestions...", 0.50)
        self._evaluate_coverage(run_id)

        # 6. Adaptive Research Loop (FR-05)
        notify("adaptive_loop", "Checking research gaps and adaptive follow-up requirements...", 0.60)
        unresolved_questions = self._get_unresolved_subquestions(run_id)

        if unresolved_questions and self.max_research_rounds > 1:
            notify(
                "adaptive_trigger",
                f"Adaptive Loop triggered! Found {len(unresolved_questions)} subquestions with incomplete evidence.",
                0.65,
                {"unresolved": [q.question_id for q in unresolved_questions]}
            )
            self._execute_adaptive_round(run_id, unresolved_questions, notify)
        else:
            notify("adaptive_skip", "All essential questions supported or single-round limit reached.", 0.75)

        # Re-evaluate final coverage
        self._evaluate_coverage(run_id, final_round=True)

        # 7. Final Report Generation (FR-06)
        notify("generating_report", "Synthesizing structured 9-section evidence-backed research report...", 0.85)
        updated_run = self.store.get_run(run_id)
        report = self.report_generator.generate(updated_run)
        self.store.set_final_report(report, run_id=run_id)

        notify("completed", "Research investigation completed successfully!", 1.0, {"report": report})
        return self.store.get_run(run_id)

    def _evaluate_coverage(self, run_id: str, final_round: bool = False):
        """
        Evaluates coverage considering evidence quality, support status, and relevance.
        (A simple source count alone does not determine coverage, as required by FR-04).
        """
        run = self.store.get_run(run_id)
        if not run or not run.research_plan:
            return

        for subq in run.research_plan.subquestions:
            # Collect evidence for this subquestion
            q_evidence = [
                ev for ev in run.evidence_records.values()
                if ev.question_id == subq.question_id
            ]

            supported_claims = [e for e in q_evidence if e.verification_status == VerificationStatus.SUPPORTED]
            partial_claims = [e for e in q_evidence if e.verification_status == VerificationStatus.PARTIALLY_SUPPORTED]
            contradicted_claims = [e for e in q_evidence if e.verification_status == VerificationStatus.CONTRADICTED]

            if len(supported_claims) >= 2 or (len(supported_claims) >= 1 and len(partial_claims) >= 1):
                # Well supported
                self.store.update_question_status(subq.question_id, CoverageStatus.SUPPORTED, run_id=run_id)
            elif len(supported_claims) == 1 or len(partial_claims) >= 1:
                # Partial evidence available
                if final_round:
                    # In final round, mark unresolved if criteria not satisfied
                    self.store.update_question_status(
                        subq.question_id,
                        CoverageStatus.PARTIAL,
                        unresolved_reason="Evidence partially available but critical metrics or primary sources remain unconfirmed.",
                        run_id=run_id
                    )
                else:
                    self.store.update_question_status(subq.question_id, CoverageStatus.PARTIAL, run_id=run_id)
            else:
                # Insufficient or contradicted
                reason = "No sufficiently verified evidence retrieved from online sources."
                if contradicted_claims:
                    reason = "Retrieved sources contain contradictory assertions without consensus."
                self.store.update_question_status(
                    subq.question_id,
                    CoverageStatus.UNRESOLVED if final_round else CoverageStatus.PARTIAL,
                    unresolved_reason=reason,
                    run_id=run_id
                )

    def _get_unresolved_subquestions(self, run_id: str) -> List[ResearchQuestion]:
        run = self.store.get_run(run_id)
        if not run or not run.research_plan:
            return []
        return [
            q for q in run.research_plan.subquestions
            if q.status in (CoverageStatus.PARTIAL, CoverageStatus.UNRESOLVED, CoverageStatus.RESEARCHING)
        ]

    def _execute_adaptive_round(
        self,
        run_id: str,
        unresolved_questions: List[ResearchQuestion],
        notify: Callable
    ):
        """
        Executes targeted follow-up searches for identified research gaps.
        """
        run = self.store.get_run(run_id)
        follow_up_limit = min(len(unresolved_questions), self.max_follow_up_searches)
        targeted_qs = unresolved_questions[:follow_up_limit]

        follow_up_queries = []
        new_sources_count = 0

        for idx, subq in enumerate(targeted_qs, start=1):
            # Formulate targeted query specifically focusing on the gap
            targeted_query = f"{run.original_question} {subq.dimension} {subq.question_text} detailed metrics analysis"
            follow_up_queries.append(targeted_query)

            notify(
                "adaptive_search",
                f"Round 2 Follow-Up for [{subq.question_id}]: '{targeted_query[:60]}...'",
                0.65 + (idx * 0.05)
            )

            raw_results = self.search_tool.search(targeted_query, max_results=3)
            filtered = SourceFilter.filter_and_rank(raw_results, max_sources=2)

            for item in filtered:
                url = item["url"]
                extracted = self.page_extractor.extract(url)
                retrieval_status = extracted["status"]
                content = extracted.get("content", "")
                if retrieval_status == "failed" and item.get("snippet"):
                    retrieval_status = "snippet_only"
                    content = item["snippet"]

                source = self.store.add_source(
                    title=item.get("title") or extracted.get("title") or "Follow-up Source",
                    url=url,
                    snippet=item.get("snippet", ""),
                    extracted_content=content,
                    retrieval_status=retrieval_status,
                    error_message=extracted.get("error_message"),
                    question_id=subq.question_id,
                    run_id=run_id
                )
                new_sources_count += 1

                # Extract and verify new claims
                verified_claims = self.analyst.extract_claims_with_verification(subq, source)
                for claim_text, excerpt, ver_status, reason in verified_claims:
                    self.store.add_evidence(
                        claim_text=claim_text,
                        question_id=subq.question_id,
                        source_ids=[source.source_id],
                        supporting_excerpts=[excerpt],
                        verification_status=ver_status,
                        verification_reason=reason,
                        run_id=run_id
                    )

        # Record Round 2
        self.store.add_search_round(
            SearchRound(
                round_number=2,
                round_type="adaptive_follow_up",
                queries_executed=follow_up_queries,
                sources_found=new_sources_count,
                gaps_targeted=[q.question_id for q in targeted_qs]
            ),
            run_id=run_id
        )
