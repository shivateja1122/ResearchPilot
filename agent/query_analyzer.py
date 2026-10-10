from __future__ import annotations
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from models.schemas import QueryIntent
from agent.llm_client import LLMClient


class QueryAnalysisOutput(BaseModel):
    main_intent: str = Field(description="E.g. product_recommendation, scientific_evaluation, technical_comparison, literature_review, policy_analysis")
    domain: str = Field(description="E.g. smartphones, laptops, healthcare_ai, cryptography, computer_vision, programming, business")
    topic: str = Field(description="Core subject under investigation")
    subtopics: List[str] = Field(default_factory=list, description="Specific subtopics or feature areas to investigate")
    explicit_constraints: Dict[str, Any] = Field(default_factory=dict, description="Constraints such as max_budget, currency, geography, or time limit")
    primary_criteria: List[str] = Field(default_factory=list, description="Top decision factors requested or implied (e.g. camera quality, OIS, low-light)")
    secondary_criteria: List[str] = Field(default_factory=list, description="Secondary considerations (e.g. battery life, software updates, value for money)")
    geographic_scope: Optional[str] = Field(default=None, description="E.g. India, US, Global")
    time_sensitivity: Optional[str] = Field(default=None, description="E.g. current 2025-2026 market, latest research")
    expected_answer_format: str = Field(default="structured_recommendation", description="E.g. ranked_recommendations, comparative_analysis, synthesis")
    required_evidence_types: List[str] = Field(default_factory=list, description="E.g. real-world camera reviews, retail price quotes, benchmark tests")
    excluded_topics: List[str] = Field(default_factory=list, description="Unrelated topics to reject (e.g. electric vehicles, automotive charging, desktop PCs)")
    ambiguities: List[str] = Field(default_factory=list, description="Any ambiguities in the query")


class QueryAnalyzer:
    """
    Analyzes research queries across arbitrary domains to extract intent,
    explicit constraints, primary/secondary criteria, and off-topic boundaries.
    """
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def analyze(self, query: str) -> QueryIntent:
        clean_q = query.strip()
        if not clean_q:
            return QueryIntent(original_query=query, main_intent="unspecified", topic="")

        prompt = (
            f"Analyze the research intent, constraints, and criteria for this query:\n"
            f"User Query: \"{clean_q}\"\n\n"
            f"Analyze:\n"
            f"1. Main Intent: (e.g. product_recommendation, technical_comparison, scientific_evaluation, academic_survey)\n"
            f"2. Domain: (e.g. smartphones, laptops, healthcare, cryptography, programming)\n"
            f"3. Topic and Subtopics\n"
            f"4. Explicit Constraints: (budget limits, currencies, brands, geographic scope)\n"
            f"5. Primary Criteria: What the user explicitly prioritized (e.g., if user asks for 'camera mobile', camera quality and low-light is primary! DO NOT make processor or gaming primary unless requested).\n"
            f"6. Secondary Criteria: Useful supporting factors (battery, display, OS updates).\n"
            f"7. Geographic Scope & Time Sensitivity: (e.g. India, 2025-2026 current market)\n"
            f"8. Excluded Topics: List topics that could cause false keyword matches (e.g. for phone battery/charging: exclude 'electric vehicles', 'EV batteries', 'automotive').\n"
            f"9. Required Evidence Types: (e.g. camera sample reviews, retail price verifications in local currency)."
        )
        system_prompt = (
            "You are an expert research query analyzer. Accurately identify the user's actual needs, priorities, constraints, and off-topic hazards. Return valid JSON."
        )

        try:
            out: QueryAnalysisOutput = self.llm.generate_json(prompt, system_prompt, QueryAnalysisOutput)
            if out and out.topic and not out.topic.startswith("Synthesized"):
                return QueryIntent(
                    original_query=clean_q,
                    main_intent=out.main_intent or "general_research",
                    domain=out.domain or "general",
                    topic=out.topic,
                    subtopics=out.subtopics or [],
                    explicit_constraints=out.explicit_constraints or {},
                    primary_criteria=out.primary_criteria or [],
                    secondary_criteria=out.secondary_criteria or [],
                    geographic_scope=out.geographic_scope,
                    time_sensitivity=out.time_sensitivity or "current",
                    expected_answer_format=out.expected_answer_format or "structured_recommendation",
                    required_evidence_types=out.required_evidence_types or [],
                    excluded_topics=out.excluded_topics or [],
                    ambiguities=out.ambiguities or []
                )
        except Exception:
            pass

        return self._heuristic_analyze(clean_q)

    def _heuristic_analyze(self, query: str) -> QueryIntent:
        q_lower = query.lower()
        
        # Check constraints: Budget & Currency
        budget = None
        currency = None
        budget_match = re.search(r"(?:under|below|budget of|within)\s*(?:₹|rs\.?|inr)?\s*([0-9]+(?:,[0-9]+)?)\s*(?:k|thousand)?", q_lower)
        if budget_match:
            raw_val = budget_match.group(1).replace(",", "")
            try:
                num = float(raw_val)
                if "k" in q_lower[budget_match.start():budget_match.end()+3]:
                    num *= 1000
                elif num < 500:
                    num *= 1000
                budget = int(num)
                currency = "INR" if ("₹" in query or "rs" in q_lower or "inr" in q_lower or "india" in q_lower) else "USD"
            except Exception:
                pass

        # Check Geography
        geo = None
        if "india" in q_lower:
            geo = "India"
        elif "us" in q_lower or "usa" in q_lower or "united states" in q_lower:
            geo = "United States"
        elif "uk" in q_lower or "europe" in q_lower:
            geo = "Europe"

        # Domain & Criteria detection
        if any(w in q_lower for w in ["camera mobile", "camera phone"]):
            return QueryIntent(
                original_query=query,
                main_intent="product_recommendation",
                domain="smartphones",
                topic="camera smartphones",
                subtopics=["daylight photography", "low-light & night mode", "portrait & selfie cameras", "video stabilization (OIS)", "retail pricing"],
                explicit_constraints={"max_budget": budget or 30000, "currency": currency or "INR", "geo": geo or "India"},
                primary_criteria=["camera sensor quality", "optical image stabilization (OIS)", "low-light photography", "portrait edge detection", "4K video recording"],
                secondary_criteria=["battery life", "display quality", "software updates", "overall value"],
                geographic_scope=geo or "India",
                time_sensitivity="2025-2026 market",
                expected_answer_format="ranked_recommendations_with_comparison_table",
                required_evidence_types=["camera comparison reviews", "daylight and low-light test results", "sensor specifications", "verified retail pricing"],
                excluded_topics=["electric vehicles", "ev battery", "automotive charging", "commercial fleet", "stock quotes", "gaming desktops"]
            )
        elif any(w in q_lower for w in ["phone", "mobile", "smartphone"]):
            return QueryIntent(
                original_query=query,
                main_intent="product_recommendation",
                domain="smartphones",
                topic="smartphones",
                subtopics=["performance & chipset", "display & battery", "camera quality", "pricing & value"],
                explicit_constraints={"max_budget": budget, "currency": currency, "geo": geo},
                primary_criteria=["overall performance", "value for money", "display quality", "battery endurance"],
                secondary_criteria=["charging speed", "camera setup", "software updates"],
                geographic_scope=geo,
                time_sensitivity="current market",
                expected_answer_format="ranked_recommendations",
                required_evidence_types=["benchmark test results", "pricing in local currency", "independent reviews"],
                excluded_topics=["electric vehicles", "ev battery", "automotive charging"]
            )
        elif "laptop" in q_lower or "pc" in q_lower:
            is_coding = any(w in q_lower for w in ["program", "coding", "developer", "software"])
            primary = ["CPU single/multicore performance", "RAM capacity (16GB+)", "keyboard & display quality", "battery life"] if is_coding else ["performance", "display", "build quality"]
            return QueryIntent(
                original_query=query,
                main_intent="product_recommendation",
                domain="laptops",
                topic="laptops for " + ("programming" if is_coding else "general use"),
                subtopics=["processor & compilation speed", "RAM & storage upgradeability", "battery & display", "pricing in market"],
                explicit_constraints={"max_budget": budget or 60000, "currency": currency or "INR", "geo": geo or "India"},
                primary_criteria=primary,
                secondary_criteria=["build quality", "port selection", "portability", "thermal performance"],
                geographic_scope=geo or "India",
                time_sensitivity="current 2025-2026 market",
                expected_answer_format="ranked_recommendations_with_specs_table",
                required_evidence_types=["laptop benchmark benchmarks", "developer reviews", "retail pricing"],
                excluded_topics=["automotive", "smartphone chips", "tablet accessories"]
            )
        elif any(w in q_lower for w in ["paper", "papers", "literature", "arxiv", "study", "research on"]):
            return QueryIntent(
                original_query=query,
                main_intent="literature_review",
                domain="academic_research",
                topic=query,
                subtopics=["methodologies", "recent publication milestones", "benchmark achievements", "limitations"],
                explicit_constraints={},
                primary_criteria=["relevance to topic", "publication date recency", "peer review/citation count", "novelty"],
                secondary_criteria=["code availability", "dataset benchmarks"],
                time_sensitivity="recent publications (2024-2026)",
                expected_answer_format="annotated_paper_summary",
                required_evidence_types=["peer-reviewed papers", "arxiv preprints", "dataset benchmarks"],
                excluded_topics=["commercial consumer ads", "unrelated news"]
            )
        elif any(w in q_lower for w in ["healthcare", "hospital", "clinical", "medical"]):
            return QueryIntent(
                original_query=query,
                main_intent="scientific_evaluation",
                domain="healthcare_ai",
                topic=query,
                subtopics=["clinical efficacy", "patient safety & hallucination risks", "implementation & integration costs", "HIPAA/FDA compliance"],
                explicit_constraints={},
                primary_criteria=["clinical accuracy", "patient safety", "regulatory compliance", "economic feasibility"],
                secondary_criteria=["staff training", "workflow integration", "vendor lock-in"],
                expected_answer_format="evidence_based_executive_report",
                required_evidence_types=["clinical trial data", "health economics studies", "regulatory guidelines"],
                excluded_topics=["consumer gadget reviews", "social media posts"]
            )
        elif any(w in q_lower for w in ["quantum", "cryptography"]):
            return QueryIntent(
                original_query=query,
                main_intent="technical_evaluation",
                domain="cryptography",
                topic=query,
                subtopics=["algorithm standards (NIST)", "timeline to cryptanalytic threat", "implementation migration costs", "hardware scaling constraints"],
                explicit_constraints={},
                primary_criteria=["post-quantum algorithm security", "migration timelines", "NIST standardization status"],
                secondary_criteria=["hardware performance overhead", "hybrid protocol adoption"],
                expected_answer_format="technical_report",
                required_evidence_types=["NIST standards documents", "peer-reviewed cryptographic analyses"],
                excluded_topics=["cryptocurrency price speculation", "blockchain meme coins"]
            )
        else:
            return QueryIntent(
                original_query=query,
                main_intent="general_research",
                domain="general",
                topic=query,
                subtopics=["overview & core options", "key performance metrics", "cost & feasibility", "challenges & tradeoffs"],
                explicit_constraints={"geo": geo},
                primary_criteria=["factual accuracy", "relevance to inquiry", "empirical evidence"],
                secondary_criteria=["practical feasibility", "limitations"],
                geographic_scope=geo,
                expected_answer_format="structured_report",
                required_evidence_types=["credible industry or academic sources", "independent reviews"],
                excluded_topics=[]
            )
