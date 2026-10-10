"""
ResearchPilot AI — Specialized Multi-Agent Package.
Contains:
- ResearchPlannerAgent: Analyzes queries and formulates structured research plans.
- ResearcherAgent: Retrieves relevant web sources, filters noise, and extracts atomic evidence.
- EvidenceAnalystAgent: Independently verifies claims, citations, contradictions, and coverage.
- ReportWriterAgent: Synthesizes direct answers, candidate comparison matrices, and citations.
- ResearchOrchestrator: Coordinates multi-agent workflow, state updates, retries, and quality gates.
"""
from agents.research_planner import ResearchPlannerAgent
from agents.researcher import ResearcherAgent
from agents.evidence_analyst import EvidenceAnalystAgent
from agents.report_writer import ReportWriterAgent

__all__ = [
    "ResearchPlannerAgent",
    "ResearcherAgent",
    "EvidenceAnalystAgent",
    "ReportWriterAgent",
]
