"""
Report Writer Agent (Agent 4).
Converts verified claims, comparison tables, and evidence records into a
comprehensive, direct, cited Markdown research report with explicit uncertainty disclosures.
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List

from agent.report_generator import ReportGenerator
from agent.llm_client import LLMClient
from models.schemas import ResearchRun, FinalReport
from state import ResearchState


class ReportWriterAgent:
    """
    Agent 4: Report Writer Agent.
    Transforms verified findings from the Evidence Ledger into an authoritative,
    user-facing research report without hallucinating citations or claims.
    """
    def __init__(
        self,
        report_generator: Optional[ReportGenerator] = None,
        llm_client: Optional[LLMClient] = None
    ):
        self.llm = llm_client or LLMClient()
        self.generator = report_generator or ReportGenerator(self.llm)

    def write_report(self, state: ResearchState) -> Dict[str, Any]:
        """
        Synthesizes the final Markdown report from verified findings in ResearchState.
        """
        # Convert state to ResearchRun format expected by generator
        run_obj = state.to_research_run()

        # Generate report
        report: FinalReport = self.generator.generate(run_obj)

        references_out = [
            {
                "source_id": s.source_id,
                "title": s.title,
                "url": s.url,
                "publisher": s.publisher,
                "published_at": s.published_at or s.publication_date
            }
            for s in report.references
        ]

        return {
            "title": report.title,
            "executive_summary": report.executive_summary,
            "direct_answer": report.direct_answer or report.executive_summary,
            "scope_and_methodology": report.scope_and_methodology,
            "key_findings": report.key_findings,
            "comparison_table_markdown": report.comparison_table_markdown,
            "conflicting_evidence": report.conflicting_evidence,
            "recommendations": report.recommendations,
            "limitations_and_unresolved": report.limitations_and_unresolved,
            "markdown_content": report.markdown_content,
            "references": references_out
        }
