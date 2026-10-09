from __future__ import annotations
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from models.schemas import ResearchPlan, ResearchQuestion, CoverageStatus
from agent.llm_client import LLMClient


class SubquestionOutput(BaseModel):
    question_id: str = Field(description="Unique identifier, e.g. Q1, Q2")
    question_text: str = Field(description="Focused research subquestion")
    dimension: str = Field(description="Dimension: benefits, risks, costs, alternatives, or limitations/regulations")


class PlanOutput(BaseModel):
    subquestions: List[SubquestionOutput] = Field(description="List of 4 to 6 focused subquestions")


class ResearchPlanner:
    """
    Transforms broad user research queries into 4-6 focused, dimension-tagged subquestions.
    """
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def create_plan(self, original_question: str) -> ResearchPlan:
        clean_q = original_question.strip()
        if not clean_q:
            raise ValueError("Research question cannot be empty.")

        prompt = (
            f"You are the Research Planner for ResearchPilot AI.\n"
            f"Given the primary research inquiry: '{clean_q}', break it down into exactly 4 to 6 "
            f"highly focused, distinct subquestions covering key dimensions: "
            f"1. Benefits & capabilities\n"
            f"2. Risks, safety & ethical challenges\n"
            f"3. Implementation costs & operational feasibility\n"
            f"4. Regulatory, compliance & governance requirements\n"
            f"5. Alternatives & strategic comparative tradeoffs\n\n"
            f"Assign each subquestion a unique ID: Q1, Q2, Q3, etc."
        )
        system_prompt = (
            "You are an expert research methodologist. Return structured JSON with 4-6 subquestions. "
            "Ensure every subquestion is precise, verifiable, and directly relevant."
        )

        try:
            plan_out: PlanOutput = self.llm.generate_json(prompt, system_prompt, PlanOutput)
            if plan_out and len(plan_out.subquestions) >= 3:
                subqs = []
                for idx, item in enumerate(plan_out.subquestions[:6], start=1):
                    qid = f"Q{idx}"
                    subqs.append(
                        ResearchQuestion(
                            question_id=qid,
                            question_text=item.question_text,
                            dimension=item.dimension.lower() if item.dimension else "general",
                            status=CoverageStatus.NOT_STARTED,
                            source_ids=[],
                            evidence_ids=[]
                        )
                    )
                return ResearchPlan(original_question=clean_q, subquestions=subqs)
        except Exception:
            pass

        # Robust heuristic fallback planning if LLM fails or is in mock mode
        return self._heuristic_plan(clean_q)

    def _heuristic_plan(self, question: str) -> ResearchPlan:
        """
        Generates 4-5 domain-relevant subquestions deterministically.
        """
        q_lower = question.lower()
        subqs = []

        if "health" in q_lower or "hospital" in q_lower or "medical" in q_lower:
            subqs = [
                ResearchQuestion(
                    question_id="Q1",
                    question_text=f"What are the demonstrated clinical and operational benefits of generative AI in healthcare?",
                    dimension="benefits",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q2",
                    question_text=f"What are the primary patient safety, liability, and hallucination risks associated with clinical GenAI?",
                    dimension="risks",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q3",
                    question_text=f"What are the capital expenditures, integration costs, and staff training overheads for healthcare institutions?",
                    dimension="costs",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q4",
                    question_text=f"What regulatory and compliance mandates (e.g., HIPAA, FDA, EU AI Act) govern medical AI deployment?",
                    dimension="regulations",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q5",
                    question_text=f"What are current adoption barriers and comparative alternatives for small or resource-constrained hospitals?",
                    dimension="alternatives",
                    status=CoverageStatus.NOT_STARTED
                )
            ]
        elif "quantum" in q_lower or "crypt" in q_lower:
            subqs = [
                ResearchQuestion(
                    question_id="Q1",
                    question_text=f"What are the anticipated commercial benefits and performance advantages of quantum computing?",
                    dimension="benefits",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q2",
                    question_text=f"What security risks does quantum decryption pose to RSA and ECC public-key cryptography?",
                    dimension="risks",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q3",
                    question_text=f"What are the migration timelines, hardware costs, and standards (NIST PQC) for post-quantum transition?",
                    dimension="costs",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q4",
                    question_text=f"What hardware scaling limitations (coherence time, error correction) delay commercial quantum deployment?",
                    dimension="limitations",
                    status=CoverageStatus.NOT_STARTED
                )
            ]
        else:
            subqs = [
                ResearchQuestion(
                    question_id="Q1",
                    question_text=f"What are the primary benefits, performance enhancements, and core use cases for: {question}?",
                    dimension="benefits",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q2",
                    question_text=f"What are the major technical, operational, and ethical risks or hazards associated with {question}?",
                    dimension="risks",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q3",
                    question_text=f"What are the financial costs, infrastructure investments, and implementation overheads required for {question}?",
                    dimension="costs",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q4",
                    question_text=f"What regulatory standards, governance guidelines, and compliance requirements apply to {question}?",
                    dimension="regulations",
                    status=CoverageStatus.NOT_STARTED
                ),
                ResearchQuestion(
                    question_id="Q5",
                    question_text=f"What are current alternatives, market tradeoffs, and unresolved limitations for {question}?",
                    dimension="alternatives",
                    status=CoverageStatus.NOT_STARTED
                )
            ]

        return ResearchPlan(original_question=question, subquestions=subqs)
