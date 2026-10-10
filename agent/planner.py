from __future__ import annotations
import json
import re
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from models.schemas import ResearchPlan, ResearchQuestion, CoverageStatus, QueryIntent
from agent.llm_client import LLMClient
from agent.query_analyzer import QueryAnalyzer


class SubquestionOutputItem(BaseModel):
    question_id: str = Field(description="Unique ID e.g. Q1, Q2, Q3")
    question_text: str = Field(description="Focused research question directly targeting the user's need")
    dimension: str = Field(description="Specific research dimension or category")
    reason: str = Field(description="Why this question is essential to answering the user's inquiry")
    required_evidence: str = Field(description="Specific evidence or metrics needed to satisfy this question")
    preferred_source_types: List[str] = Field(default_factory=list, description="E.g. independent_reviews, tech_publications, official_specs, retail_pricing")
    completion_criteria: str = Field(description="Condition under which this question is considered answered")


class PlanOutput(BaseModel):
    subquestions: List[SubquestionOutputItem] = Field(description="List of 3 to 6 focused research questions")


class ResearchPlanner:
    """
    Transforms user inquiries and parsed query intent into 3-6 focused,
    domain-tailored research subquestions with explicit completion criteria.
    """
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.analyzer = QueryAnalyzer(self.llm)

    def create_plan(self, original_question: str, intent: Optional[QueryIntent] = None) -> ResearchPlan:
        clean_q = original_question.strip()
        if not clean_q:
            raise ValueError("Research question cannot be empty.")

        query_intent = intent or self.analyzer.analyze(clean_q)

        prompt = (
            f"You are the Senior Research Planner for ResearchPilot AI.\n\n"
            f"User Query: \"{clean_q}\"\n"
            f"Parsed Intent: {query_intent.main_intent} | Domain: {query_intent.domain}\n"
            f"Primary Decision Criteria: {', '.join(query_intent.primary_criteria) or 'None'}\n"
            f"Secondary Criteria: {', '.join(query_intent.secondary_criteria) or 'None'}\n"
            f"Explicit Constraints: {query_intent.explicit_constraints}\n"
            f"Geographic Scope: {query_intent.geographic_scope or 'Global'}\n\n"
            f"REQUIREMENTS:\n"
            f"1. Generate 3 to 5 highly focused research questions tailored SPECIFICALLY to the user's primary criteria and constraints.\n"
            f"2. DO NOT generate questions about unrelated criteria. (For example, if the user asks for a camera phone, prioritize camera sensors, daylight/low-light comparisons, portraits, and local pricing. DO NOT ask about gaming benchmarks or enterprise servers).\n"
            f"3. For each question specify: unique ID (Q1, Q2, etc.), question_text, reason, required_evidence, preferred_source_types, and completion_criteria.\n"
            f"4. Ensure each question directly aids in constructing the final recommendation or answer."
        )
        system_prompt = (
            "You are a rigorous research planner. Create targeted, evidence-driven subquestions strictly aligned with user priorities."
        )

        try:
            plan_out: PlanOutput = self.llm.generate_json(prompt, system_prompt, PlanOutput)
            if plan_out and len(plan_out.subquestions) >= 3 and not plan_out.subquestions[0].question_text.startswith("Synthesized"):
                subqs = []
                for idx, item in enumerate(plan_out.subquestions[:6], start=1):
                    qid = f"Q{idx}"
                    subqs.append(
                        ResearchQuestion(
                            question_id=qid,
                            question_text=item.question_text,
                            dimension=item.dimension.lower() if item.dimension else "general",
                            reason=item.reason,
                            required_evidence=item.required_evidence,
                            preferred_source_types=item.preferred_source_types or ["independent_review", "tech_publication"],
                            completion_criteria=item.completion_criteria,
                            status=CoverageStatus.PLANNED,
                            confidence=0.0,
                            source_ids=[],
                            evidence_ids=[]
                        )
                    )
                return ResearchPlan(original_question=clean_q, query_intent=query_intent, subquestions=subqs)
        except Exception:
            pass

        return self._heuristic_plan(clean_q, query_intent)

    def _heuristic_plan(self, question: str, intent: QueryIntent) -> ResearchPlan:
        subqs = []
        domain = intent.domain
        constraints = intent.explicit_constraints
        geo = intent.geographic_scope or "India" if "india" in question.lower() else "the target market"
        budget_str = f"under {constraints.get('currency', '')} {constraints.get('max_budget', '')}".strip() if constraints.get('max_budget') else "in this price segment"

        if domain == "smartphones" and any("camera" in c.lower() for c in intent.primary_criteria + [intent.topic]):
            subqs = [
                ResearchQuestion(
                    question_id="Q1",
                    question_text=f"Which smartphone models {budget_str} in {geo} are recognized by camera reviews as having the strongest camera hardware (e.g. Sony LYT/IMX sensors, OIS)?",
                    dimension="camera_top_picks",
                    reason="Identifies the primary camera-focused candidate devices within budget.",
                    required_evidence="Expert camera reviews identifying top candidate models with main camera sensor specifications and OIS support.",
                    preferred_source_types=["independent_review", "tech_publication", "official_specs"],
                    completion_criteria="At least 2 verified candidate phones identified with primary camera specs.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q2",
                    question_text=f"How do these top camera phones compare in real-world daylight clarity, dynamic range, and low-light / night photography tests?",
                    dimension="low_light_performance",
                    reason="Evaluates actual image quality beyond megapixels in challenging lighting conditions.",
                    required_evidence="Comparative test results for daylight HDR and low-light / night photography samples.",
                    preferred_source_types=["independent_review", "camera_comparison"],
                    completion_criteria="Direct daylight and low-light comparative findings between leading options.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q3",
                    question_text=f"How do the portrait edge detection, front selfie camera, and 4K video recording with stabilization compare across these models?",
                    dimension="portrait_video_quality",
                    reason="Assesses secondary photographic features (portraits, selfies, video stability).",
                    required_evidence="Test observations on portrait skin tones, edge detection, and video EIS/OIS stability.",
                    preferred_source_types=["independent_review", "video_tests"],
                    completion_criteria="Comparative notes on portrait and video recording performance.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q4",
                    question_text=f"What are the current verified retail prices, variant availability, and key non-camera tradeoffs (e.g. battery life, software updates) for each candidate in {geo}?",
                    dimension="pricing_tradeoffs",
                    reason="Ensures all recommended options strictly comply with the user's budget and highlights important practical tradeoffs.",
                    required_evidence="Current retail prices in local currency and documented battery/software support terms.",
                    preferred_source_types=["tech_publication", "retail_pricing", "independent_review"],
                    completion_criteria="Verified prices in local currency and key drawbacks documented for each model.",
                    status=CoverageStatus.PLANNED
                )
            ]
        elif domain == "laptops":
            subqs = [
                ResearchQuestion(
                    question_id="Q1",
                    question_text=f"What are the top-rated laptop models {budget_str} in {geo} for programming and multitasking?",
                    dimension="top_picks",
                    reason="Identifies leading laptop models matching budget and user needs.",
                    required_evidence="Benchmark reviews and developer recommendations.",
                    preferred_source_types=["tech_publication", "independent_review"],
                    completion_criteria="At least 2 candidate models verified with CPU and RAM specifications.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q2",
                    question_text=f"How do the processor benchmarks (single/multicore), RAM capacity (16GB), and SSD speeds compare for software development?",
                    dimension="performance_specs",
                    reason="Determines compilation speeds, IDE responsiveness, and multitasking headroom.",
                    required_evidence="Geekbench/Cinebench scores and RAM configuration details.",
                    preferred_source_types=["benchmark_database", "independent_review"],
                    completion_criteria="Verified CPU benchmarks and RAM configurations.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q3",
                    question_text=f"How do keyboard comfort, display quality (FHD/IPS), battery endurance, and port selection compare across options?",
                    dimension="usability_display",
                    reason="Ensures comfortable long-session typing and adequate portable battery life.",
                    required_evidence="Measured battery runtimes, display color accuracy, and keyboard travel reviews.",
                    preferred_source_types=["independent_review"],
                    completion_criteria="Documented battery life and display specs for candidates.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q4",
                    question_text=f"What are the verified retail prices and key drawbacks or upgrade limitations for each laptop in {geo}?",
                    dimension="pricing_limitations",
                    reason="Verifies price compliance and highlights upgradeability tradeoffs.",
                    required_evidence="Current pricing and RAM/storage upgradeability details.",
                    preferred_source_types=["retail_pricing", "tech_publication"],
                    completion_criteria="Current retail prices and key limitations documented.",
                    status=CoverageStatus.PLANNED
                )
            ]
        elif domain == "healthcare_ai":
            subqs = [
                ResearchQuestion(
                    question_id="Q1",
                    question_text=f"What are the demonstrated clinical and operational benefits of generative AI in healthcare?",
                    dimension="benefits",
                    reason="Evaluates empirical productivity and diagnostic improvements.",
                    required_evidence="Peer-reviewed studies or clinical trials documenting time savings or diagnostic accuracy.",
                    preferred_source_types=["peer_reviewed_paper", "institutional_report"],
                    completion_criteria="At least 2 verified evidence points on clinical or operational impact.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q2",
                    question_text=f"What are the primary patient safety, clinical liability, and hallucination risks of medical GenAI?",
                    dimension="risks",
                    reason="Assesses patient safety vulnerabilities and clinical failure modes.",
                    required_evidence="Documented medical hallucination rates and safety analyses.",
                    preferred_source_types=["peer_reviewed_paper", "regulatory_guideline"],
                    completion_criteria="Documented risks and mitigation strategies.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q3",
                    question_text=f"What are the capital expenditures, integration costs, and IT infrastructure overheads for hospitals adopting GenAI?",
                    dimension="costs",
                    reason="Assesses financial feasibility and total cost of ownership.",
                    required_evidence="Economic analyses and implementation cost breakdowns.",
                    preferred_source_types=["health_economics_study", "industry_report"],
                    completion_criteria="Economic and implementation cost estimates.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q4",
                    question_text=f"What regulatory and compliance mandates (e.g. HIPAA, FDA, EU AI Act) govern clinical deployment?",
                    dimension="regulations",
                    reason="Identifies mandatory legal and data governance requirements.",
                    required_evidence="Statutory guidelines and health data compliance mandates.",
                    preferred_source_types=["government_publication", "legal_analysis"],
                    completion_criteria="Relevant regulatory mandates and compliance checklists.",
                    status=CoverageStatus.PLANNED
                )
            ]
        elif domain == "academic_research":
            subqs = [
                ResearchQuestion(
                    question_id="Q1",
                    question_text=f"What are the most recent peer-reviewed and preprint publications on: {question}?",
                    dimension="recent_papers",
                    reason="Gathers the latest literature published in 2024-2026.",
                    required_evidence="Paper titles, publication dates, author affiliations, and arXiv / journal links.",
                    preferred_source_types=["peer_reviewed_paper", "arxiv_preprint"],
                    completion_criteria="At least 3 verified recent papers with verified dates and URLs.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q2",
                    question_text=f"What core architectural methodologies and innovations do these recent papers introduce?",
                    dimension="methodologies",
                    reason="Explains the technical contributions of each approach.",
                    required_evidence="Methodological descriptions and algorithmic formulations.",
                    preferred_source_types=["peer_reviewed_paper"],
                    completion_criteria="Key technical innovations summarized with citations.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q3",
                    question_text=f"How do their benchmark performances compare on standardized evaluation datasets, and what are their noted limitations?",
                    dimension="benchmarks_limitations",
                    reason="Provides objective performance comparison and identifies research frontiers.",
                    required_evidence="Quantitative benchmark metrics (e.g. mAP, accuracy) and disclosed limitations.",
                    preferred_source_types=["peer_reviewed_paper"],
                    completion_criteria="Comparative benchmark numbers and stated limitations.",
                    status=CoverageStatus.PLANNED
                )
            ]
        else:
            subqs = [
                ResearchQuestion(
                    question_id="Q1",
                    question_text=f"What are the primary options, core concepts, and leading solutions for: {question}?",
                    dimension="overview",
                    reason="Establishes baseline landscape and top candidate answers.",
                    required_evidence="Authoritative overviews and documented leading options.",
                    preferred_source_types=["credible_publication", "independent_review"],
                    completion_criteria="At least 2 verified options or core findings.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q2",
                    question_text=f"What are the verified performance metrics, real-world efficacy, and evidence for {question}?",
                    dimension="performance",
                    reason="Gathers objective empirical data on effectiveness.",
                    required_evidence="Quantitative metrics and verified comparative data.",
                    preferred_source_types=["independent_study", "benchmark"],
                    completion_criteria="Documented empirical performance metrics.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q3",
                    question_text=f"What are the critical costs, tradeoffs, and limitations associated with each option?",
                    dimension="tradeoffs",
                    reason="Identifies downsides, budget constraints, and risk factors.",
                    required_evidence="Documented costs and known operational limitations.",
                    preferred_source_types=["credible_publication", "user_reviews"],
                    completion_criteria="Identified costs and tradeoffs.",
                    status=CoverageStatus.PLANNED
                ),
                ResearchQuestion(
                    question_id="Q4",
                    question_text=f"What are the comparative tradeoffs and recommended final verdict?",
                    dimension="verdict",
                    reason="Synthesizes evidence into a clear, actionable conclusion.",
                    required_evidence="Comparative synthesis and decision criteria evaluation.",
                    preferred_source_types=["expert_analysis", "credible_publication"],
                    completion_criteria="Synthesized recommendation with supporting reasoning.",
                    status=CoverageStatus.PLANNED
                )
            ]

        return ResearchPlan(original_question=question, query_intent=intent, subquestions=subqs)
