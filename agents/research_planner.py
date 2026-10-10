"""
Research Planner Agent (Agent 1).
Understands the user query, extracts intent, constraints, decision criteria,
and formulates a structured research plan with 3-7 criteria-driven research questions.
"""
from __future__ import annotations
import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from agent.llm_client import LLMClient
from agent.query_analyzer import QueryAnalyzer
from agent.planner import ResearchPlanner
from models.schemas import QueryIntent, ResearchPlan, ResearchQuestion


class ResearchPlannerAgent:
    """
    Agent 1: Research Planner Agent.
    Responsible for analyzing user inquiries and structuring research plans
    without inventing factual findings.
    """
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.analyzer = QueryAnalyzer(self.llm)
        self.planner = ResearchPlanner(self.llm)

    def plan(
        self,
        query: str,
        context: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes query analysis and generates a structured research plan.
        Returns validated structured data conforming to the master prompt schema.
        """
        clean_q = query.strip()
        if not clean_q:
            raise ValueError("Research query cannot be empty.")

        # 1. Analyze user query intent and boundaries
        intent: QueryIntent = self.analyzer.analyze(clean_q)
        
        # Attach context if provided
        if context:
            intent.ambiguities.append(f"User context provided: {context}")

        # 2. Generate focused research questions
        research_plan_obj: ResearchPlan = self.planner.create_plan(clean_q, intent=intent)

        # 3. Format into the strict Agent 1 schema
        plan_id = f"PLAN_{uuid.uuid4().hex[:6].upper()}"
        formatted_questions: List[Dict[str, Any]] = []

        for q in research_plan_obj.subquestions:
            # Normalize required_evidence to list
            req_ev = q.required_evidence
            if isinstance(req_ev, str):
                req_ev = [req_ev]
            elif not req_ev:
                req_ev = ["Verified benchmark or technical specification"]

            # Normalize completion_criteria to list
            comp_crit = q.completion_criteria
            if isinstance(comp_crit, str):
                comp_crit = [comp_crit]
            elif not comp_crit:
                comp_crit = ["At least 2 verified sources corroborating the requirement"]

            formatted_questions.append({
                "question_id": q.question_id,
                "question": q.question_text,
                "dimension": q.dimension or "technical_evaluation",
                "reason": q.reason or "Essential dimension for query resolution",
                "priority": q.importance or "high",
                "required_evidence": req_ev,
                "completion_criteria": comp_crit,
                "status": "PLANNED"
            })

        output: Dict[str, Any] = {
            "plan_id": plan_id,
            "original_query": clean_q,
            "intent": intent.main_intent,
            "domain": intent.domain,
            "topic": intent.topic or clean_q,
            "constraints": intent.explicit_constraints,
            "primary_criteria": intent.primary_criteria,
            "secondary_criteria": intent.secondary_criteria,
            "geographic_scope": intent.geographic_scope,
            "excluded_topics": intent.excluded_topics,
            "research_questions": formatted_questions,
            "intent_obj": intent.model_dump()
        }

        return output
