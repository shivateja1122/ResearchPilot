"""
Central Orchestrator for ResearchPilot AI Multi-Agent Architecture.
Coordinates four specialized agents (ResearchPlannerAgent, ResearcherAgent,
EvidenceAnalystAgent, ReportWriterAgent), manages authoritative shared state,
executes adaptive gap recovery, and runs the independent Quality Gate.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Any, List

from state import ResearchState
from models.schemas import (
    ResearchRun, ResearchPlan, ResearchQuestion, SearchRound,
    CoverageStatus, VerificationStatus, FinalReport, QueryIntent,
    QualityGateResult, ResearchAudit
)
from storage.research_store import ResearchStore
from tools.web_search import WebSearchTool
from tools.page_extractor import PageExtractor
from tools.source_filter import SourceFilter
from agent.llm_client import LLMClient
from agent.claim_verifier import ClaimVerifier
from agent.citation_validator import CitationValidator
from agent.contradiction_detector import ContradictionDetector
from agent.gap_recovery import GapRecoveryEngine
from agent.report_generator import ReportGenerator
from agent.quality_gate import QualityGate

from agents.research_planner import ResearchPlannerAgent
from agents.researcher import ResearcherAgent
from agents.evidence_analyst import EvidenceAnalystAgent
from agents.report_writer import ReportWriterAgent


class ResearchOrchestrator:
    """
    Central Supervisor / Orchestrator.
    Coordinates specialized agents, updates shared research state, enforces
    conditional routing, and invokes the independent QualityGate.
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
        self.max_research_rounds = max_research_rounds
        self.max_follow_up_searches = max_follow_up_searches

        # Shared Tools & Utilities
        self.search_tool = WebSearchTool(timeout_seconds=search_timeout)
        self.page_extractor = PageExtractor(timeout_seconds=page_timeout)
        self.claim_verifier = ClaimVerifier(self.llm)
        self.citation_validator = CitationValidator()
        self.contradiction_detector = ContradictionDetector()
        self.gap_recovery = GapRecoveryEngine(max_rounds=max_research_rounds)
        self.report_generator = ReportGenerator(self.llm)
        self.quality_gate = QualityGate()

        # Four Specialized AI Agents
        self.planner_agent = ResearchPlannerAgent(self.llm)
        self.researcher_agent = ResearcherAgent(
            search_tool=self.search_tool,
            page_extractor=self.page_extractor,
            llm_client=self.llm,
            search_timeout=search_timeout,
            page_timeout=page_timeout
        )
        self.analyst_agent = EvidenceAnalystAgent(
            claim_verifier=self.claim_verifier,
            citation_validator=self.citation_validator,
            contradiction_detector=self.contradiction_detector,
            gap_recovery=self.gap_recovery,
            llm_client=self.llm
        )
        self.writer_agent = ReportWriterAgent(
            report_generator=self.report_generator,
            llm_client=self.llm
        )

    # -------------------------------------------------------------
    # Explicit Orchestration Stage Functions (Phase 3 Interface)
    # -------------------------------------------------------------

    def plan_research(self, query: str, state: ResearchState) -> Dict[str, Any]:
        """Invokes Agent 1: Research Planner Agent and updates state."""
        state.log_event("ResearchPlannerAgent", "START_PLANNING", f"Analyzing query: '{query}'")
        plan_output = self.planner_agent.plan(query, context=state.context)
        state.research_plan = plan_output
        state.query_intent = plan_output.get("intent_obj") or {
            "original_query": query,
            "main_intent": plan_output.get("intent", "general_research"),
            "domain": plan_output.get("domain", "general"),
            "topic": plan_output.get("topic") or query,
            "explicit_constraints": plan_output.get("constraints", {}),
            "primary_criteria": plan_output.get("primary_criteria", []),
            "secondary_criteria": plan_output.get("secondary_criteria", []),
            "geographic_scope": plan_output.get("geographic_scope"),
            "excluded_topics": plan_output.get("excluded_topics", [])
        }
        state.log_event(
            "ResearchPlannerAgent",
            "PLAN_COMPLETED",
            f"Created plan {plan_output.get('plan_id')} with {len(plan_output.get('research_questions', []))} questions"
        )
        return plan_output

    def execute_research(self, task: Dict[str, Any], state: ResearchState) -> Dict[str, Any]:
        """Invokes Agent 2: Researcher Agent for a specific task and registers evidence."""
        qid = task.get("question_id", "Q1")
        state.log_event("ResearcherAgent", "START_TASK", f"Executing research task for question {qid}")
        
        research_output = self.researcher_agent.execute_task(
            task=task,
            intent_dict=state.query_intent,
            max_sources=3,
            relevance_threshold=58.0 if not task.get("is_follow_up") else 55.0
        )

        # Ingest accepted and rejected sources into state
        for s in research_output.get("sources", []):
            if s.get("accepted"):
                state.add_source(s)
            else:
                state.add_rejected_source(s)

        # Ingest extracted evidence items into state
        for ev in research_output.get("evidence", []):
            state.add_evidence_item(ev)

        # Record any tool/retrieval errors
        for err in research_output.get("errors", []):
            state.add_error("ResearcherAgent", err, "RETRIEVAL_ERROR")

        state.log_event(
            "ResearcherAgent",
            "TASK_COMPLETED",
            f"Retrieved {len(research_output.get('sources', []))} sources and {len(research_output.get('evidence', []))} evidence items"
        )
        return research_output

    def analyze_evidence(self, state: ResearchState, is_final: bool = False) -> Dict[str, Any]:
        """Invokes Agent 3: Evidence Analyst Agent across all collected evidence."""
        state.log_event("EvidenceAnalystAgent", "START_ANALYSIS", f"Analyzing {len(state.evidence)} evidence items")
        analysis_output = self.analyst_agent.analyze(
            research_plan=state.research_plan or {},
            sources=state.sources,
            evidence_items=state.evidence,
            is_final_round=is_final
        )

        # Update verified claims in state
        state.verified_claims = analysis_output.get("verified_claims", [])
        state.citation_validations = analysis_output.get("citations", [])
        state.conflicts = analysis_output.get("conflicts", [])
        state.coverage = analysis_output.get("coverage", {})
        state.follow_up_tasks = analysis_output.get("follow_up_tasks", [])

        state.log_event(
            "EvidenceAnalystAgent",
            "ANALYSIS_COMPLETED",
            f"Verified {len(state.verified_claims)} claims; Identified {len(state.follow_up_tasks)} follow-up tasks"
        )
        return analysis_output

    def recover_research_gaps(
        self,
        state: ResearchState,
        notify_fn: Optional[Callable[[str, str, float, Dict[str, Any]], None]] = None
    ) -> bool:
        """
        Executes bounded adaptive follow-up loop (Round 2) for unresolved research questions.
        Returns True if gaps were recovered, False if none or limit reached.
        """
        if not state.follow_up_tasks or self.max_research_rounds <= 1:
            return False

        round_num = 2
        gaps_to_target = state.follow_up_tasks[:self.max_follow_up_searches]
        state.log_event(
            "CentralOrchestrator",
            "GAP_RECOVERY_STARTED",
            f"Starting Round {round_num} targeted gap recovery for {len(gaps_to_target)} questions"
        )

        for idx, task in enumerate(gaps_to_target, start=1):
            qid = task.get("question_id", "Q1")
            retries = state.increment_retry(f"gap_recovery_{qid}")
            if retries > 3:
                state.log_event("CentralOrchestrator", "RETRY_LIMIT_EXCEEDED", f"Max retries reached for {qid}")
                continue

            if notify_fn:
                notify_fn(
                    "adaptive_gap_recovery",
                    f"Round 2 Targeted Search for {qid}: '{task.get('missing_criteria')}'",
                    0.70 + (idx * 0.03),
                    {"task": task}
                )

            # Delegate targeted research to Agent 2
            self.execute_research(task, state)

        # Re-run Evidence Analyst Agent on new evidence
        self.analyze_evidence(state, is_final=True)
        return True

    def generate_report(self, state: ResearchState) -> Dict[str, Any]:
        """Invokes Agent 4: Report Writer Agent using verified findings in state."""
        state.log_event("ReportWriterAgent", "START_REPORT_SYNTHESIS", "Synthesizing direct Markdown report")
        report_output = self.writer_agent.write_report(state)
        state.final_report = report_output
        state.log_event("ReportWriterAgent", "REPORT_SYNTHESIZED", f"Report title: '{report_output.get('title')}'")
        return report_output

    def validate_final_report(self, report_dict: Dict[str, Any], state: ResearchState) -> QualityGateResult:
        """Runs the independent 12-point Quality Gate post-generation."""
        state.log_event("QualityGate", "START_VALIDATION", "Validating synthesized report against 12 quality criteria")
        
        # Convert state to ResearchRun format expected by QualityGate
        run_obj = state.to_research_run()
        qg_result: QualityGateResult = self.quality_gate.evaluate_and_repair(run_obj)

        state.quality_gate_result = qg_result.model_dump()
        state.quality_status = "PASSED" if qg_result.report_passed else "PASSED_WITH_LIMITATIONS"

        # If repairs were applied, update the report content in state
        if qg_result.repairs_applied and run_obj.final_report:
            state.final_report["key_findings"] = run_obj.final_report.key_findings
            state.final_report["markdown_content"] = run_obj.final_report.markdown_content

        state.log_event(
            "QualityGate",
            "VALIDATION_COMPLETED",
            f"QualityGate result: passed={qg_result.report_passed}, score={qg_result.score}, repairs={len(qg_result.repairs_applied)}"
        )
        return qg_result

    # -------------------------------------------------------------
    # Full End-to-End Orchestrated Pipeline
    # -------------------------------------------------------------

    def run_research(
        self,
        research_question: str,
        progress_callback: Optional[Callable[[str, str, float, Dict[str, Any]], None]] = None
    ) -> ResearchRun:
        """
        Executes the full multi-agent research pipeline from user query to verified report.
        Maintains complete state provenance and updates ResearchStore for UI/test access.
        """
        def notify(stage: str, msg: str, pct: float, extra: Optional[Dict[str, Any]] = None):
            if progress_callback:
                progress_callback(stage, msg, pct, extra or {})

        # 1. Initialize State and Store Run
        clean_query = research_question.strip()
        state = ResearchState(original_query=clean_query)
        run_id = state.run_id
        
        # Register in storage for existing frontend and persistence
        store_run = self.store.init_run(clean_query)
        # Match run_id for sync
        state.run_id = store_run.run_id
        run_id = store_run.run_id

        notify("init", f"Initiating Multi-Agent Research System: '{clean_query}'", 0.05, {"run_id": run_id})

        # 2. Planning Phase (Agent 1: Research Planner Agent)
        notify("planning", "Agent 1 (Research Planner): Analyzing intent, constraints, and research subquestions...", 0.15)
        plan_dict = self.plan_research(clean_query, state)
        
        # Sync plan to store
        intent_obj = QueryIntent(**state.query_intent) if state.query_intent else None
        if intent_obj:
            self.store.set_query_intent(intent_obj, run_id=run_id)
        
        subqs_for_store = [
            ResearchQuestion(
                question_id=q["question_id"],
                question_text=q["question"],
                dimension=q.get("dimension"),
                importance=q.get("priority", "high"),
                required_evidence=q.get("required_evidence", []),
                completion_criteria=q.get("completion_criteria", []),
                status=CoverageStatus.PLANNED
            )
            for q in plan_dict.get("research_questions", [])
        ]
        self.store.set_plan(ResearchPlan(original_question=clean_query, subquestions=subqs_for_store), run_id=run_id)
        notify("planning_done", f"Agent 1 generated {len(subqs_for_store)} research questions.", 0.25, {"plan": plan_dict})

        # 3. Retrieval & Extraction Phase (Agent 2: Researcher Agent - Round 1)
        notify("researching", "Agent 2 (Researcher): Executing targeted searches with strict relevance gating...", 0.30)
        round_1_queries = []
        new_sources_count = 0

        for idx, q_dict in enumerate(plan_dict.get("research_questions", []), start=1):
            qid = q_dict["question_id"]
            self.store.update_question_status(qid, CoverageStatus.IN_PROGRESS, run_id=run_id)
            
            notify("searching", f"Agent 2 researching {qid}: {q_dict['question'][:45]}...", 0.30 + (idx * 0.05))
            res_output = self.execute_research(q_dict, state)
            
            if res_output.get("query_executed"):
                round_1_queries.append(res_output["query_executed"])

            # Sync newly discovered sources and evidence to store
            for s in res_output.get("sources", []):
                if s.get("accepted"):
                    self.store.add_source(
                        title=s.get("title", ""),
                        url=s.get("url", ""),
                        snippet=s.get("snippet", ""),
                        extracted_content=s.get("extracted_content", ""),
                        retrieval_status=s.get("retrieval_status", "FULL_TEXT_RETRIEVED"),
                        relevance_score=s.get("relevance_score", 80.0),
                        accepted=True,
                        question_id=qid,
                        run_id=run_id
                    )
                    new_sources_count += 1
                else:
                    self.store.add_rejected_source(
                        title=s.get("title", ""),
                        url=s.get("url", ""),
                        snippet=s.get("snippet", ""),
                        relevance_score=s.get("relevance_score", 20.0),
                        rejection_reason=s.get("rejection_reason", "Low relevance"),
                        question_id=qid,
                        run_id=run_id
                    )

            for ev in res_output.get("evidence", []):
                self.store.add_evidence(
                    claim_text=ev.get("claim", ""),
                    question_id=qid,
                    source_ids=[ev.get("source_id")] if ev.get("source_id") else [],
                    supporting_excerpts=[ev.get("supporting_excerpt")] if ev.get("supporting_excerpt") else [],
                    evidence_type=ev.get("evidence_type", "direct"),
                    extraction_confidence=ev.get("confidence", 0.90),
                    run_id=run_id
                )

        # Store Search Round 1
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

        # 4. Evidence Analysis Phase (Agent 3: Evidence Analyst Agent - Round 1)
        notify("analyzing", "Agent 3 (Evidence Analyst): Performing 9-point claim verification and coverage auditing...", 0.60)
        self.analyze_evidence(state, is_final=False)

        # Sync verification statuses to store
        for clm in state.verified_claims:
            cid = clm.get("claim_id")
            if cid in self.store.get_run(run_id).evidence_records:
                self.store.get_run(run_id).evidence_records[cid].verification_status = VerificationStatus(clm.get("status", "unverified").lower())
                self.store.get_run(run_id).evidence_records[cid].verification_reason = clm.get("verification_reason", "")

        for qid, cov in state.coverage.items():
            self.store.update_question_status(
                qid,
                CoverageStatus(cov.get("status", "planned").lower()),
                unresolved_reason="; ".join(cov.get("missing_information", [])) or None,
                run_id=run_id
            )

        # 5. Adaptive Research Gap Recovery Loop (Round 2)
        if state.follow_up_tasks and self.max_research_rounds > 1:
            notify(
                "adaptive_gap_recovery",
                f"Conditional Gap Recovery: Formulating targeted follow-up queries for {len(state.follow_up_tasks)} questions...",
                0.68,
                {"gaps": [t["question_id"] for t in state.follow_up_tasks]}
            )
            self.recover_research_gaps(state, notify_fn=notify)

            # Record Search Round 2 in store
            round_2_queries = [t.get("missing_criteria", "") for t in state.follow_up_tasks]
            self.store.add_search_round(
                SearchRound(
                    round_number=2,
                    round_type="adaptive_follow_up",
                    queries_executed=round_2_queries,
                    sources_found=len(state.sources) - new_sources_count,
                    gaps_targeted=[t["question_id"] for t in state.follow_up_tasks]
                ),
                run_id=run_id
            )

            # Re-sync final coverage to store
            for qid, cov in state.coverage.items():
                self.store.update_question_status(
                    qid,
                    CoverageStatus(cov.get("status", "planned").lower()),
                    unresolved_reason="; ".join(cov.get("missing_information", [])) or None,
                    run_id=run_id
                )

        # 6. Report Generation Phase (Agent 4: Report Writer Agent)
        notify("writing_report", "Agent 4 (Report Writer): Synthesizing direct Markdown answer with citations and comparison matrix...", 0.82)
        report_dict = self.generate_report(state)
        
        # Sync final report to store
        rep_obj = FinalReport(
            title=report_dict.get("title", "Research Report"),
            executive_summary=report_dict.get("executive_summary", ""),
            scope_and_methodology=report_dict.get("scope_and_methodology", ""),
            key_findings=report_dict.get("key_findings", []),
            evidence_and_citations=list(self.store.get_run(run_id).evidence_records.values()),
            conflicting_evidence=report_dict.get("conflicting_evidence"),
            recommendations=report_dict.get("recommendations", []),
            limitations_and_unresolved=report_dict.get("limitations_and_unresolved", []),
            references=list(self.store.get_run(run_id).sources.values()),
            markdown_content=report_dict.get("markdown_content", ""),
            direct_answer=report_dict.get("direct_answer"),
            comparison_table_markdown=report_dict.get("comparison_table_markdown")
        )
        self.store.set_final_report(rep_obj, run_id=run_id)

        # 7. Independent Quality Gate & Bounded Repairs
        notify("quality_gate", "Independent Quality Gate: Validating report against 12 verification criteria...", 0.90)
        qg_result = self.validate_final_report(report_dict, state)
        self.store.set_quality_gate(qg_result, run_id=run_id)

        # If repairs updated report text, sync back
        if qg_result.repairs_applied and state.final_report:
            rep_obj.key_findings = state.final_report.get("key_findings", rep_obj.key_findings)
            rep_obj.markdown_content = state.final_report.get("markdown_content", rep_obj.markdown_content)
            self.store.set_final_report(rep_obj, run_id=run_id)

        # 8. Build Isolated Machine-Readable Research Audit
        notify("audit_log", "Building complete machine-readable Research Audit JSON...", 0.96)
        updated_run = self.store.get_run(run_id)
        audit_obj = self.report_generator.build_audit(updated_run)
        self.store.set_research_audit(audit_obj, run_id=run_id)
        state.research_audit = audit_obj.model_dump()
        state.completed_at = datetime.now(timezone.utc).isoformat()

        notify("completed", "Multi-Agent Research Investigation completed successfully!", 1.0, {"report": rep_obj})
        return self.store.get_run(run_id)

    def generate_pdf_report(
        self,
        run_or_run_id: Union[ResearchRun, str],
        output_path: Optional[str] = None
    ) -> bytes:
        """
        Generates a professional publication-quality PDF report from a completed ResearchRun.
        """
        if isinstance(run_or_run_id, str):
            run = self.store.get_run(run_or_run_id)
        else:
            run = run_or_run_id

        if not run:
            raise ValueError(f"Research run not found: {run_or_run_id}")
        if not run.final_report:
            raise ValueError(f"Final report has not been generated for run: {run.run_id}")

        return self.report_generator.generate_pdf(run, output_path=output_path)

