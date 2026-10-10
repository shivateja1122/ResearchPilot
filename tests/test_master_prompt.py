from __future__ import annotations
import pytest
from models.schemas import (
    ResearchPlan, ResearchQuestion, Source, Evidence,
    CoverageStatus, VerificationStatus, QueryIntent
)
from storage.research_store import ResearchStore
from tools.page_extractor import PageExtractor
from tools.source_filter import SourceFilter
from agent.query_analyzer import QueryAnalyzer
from agent.planner import ResearchPlanner
from agent.analyst import ResearchAnalyst
from agent.report_generator import ReportGenerator
from agent.quality_gate import QualityGate
from agent.orchestrator import ResearchOrchestrator


def test_master_a_camera_phone_intent_and_ev_rejection():
    """
    Test A: Camera phone recommendation
    - Camera quality is primary criterion.
    - India-specific constraints are identified.
    - Irrelevant EV battery articles are REJECTED by source filter.
    """
    analyzer = QueryAnalyzer()
    intent = analyzer.analyze("Suggest me a good camera mobile under ₹30,000 in India.")

    assert intent.domain == "smartphones"
    assert any("camera" in c.lower() for c in intent.primary_criteria)
    assert intent.explicit_constraints.get("max_budget") == 30000
    assert intent.explicit_constraints.get("geo") == "India"
    assert "electric vehicles" in [x.lower() for x in intent.excluded_topics]

    # Test that EV battery article is REJECTED by strict source filter
    ev_article = {
        "title": "New Geotab data shows EV battery health remains strong as fast charging use increases",
        "snippet": "Analysis shows average EV battery degradation rate of 2.3% due to high-power DC fast charging in commercial fleets.",
        "url": "https://markets.businessinsider.com/news/stocks/ev-battery-health-1035706587"
    }
    accepted, rejected = SourceFilter.filter_and_rank([ev_article], intent=intent)
    assert len(accepted) == 0, "EV article must not be accepted for smartphone query"
    assert len(rejected) == 1
    assert "Off-topic" in rejected[0]["rejection_reason"] or "domain mismatch" in rejected[0]["rejection_reason"].lower()

    # Test that genuine camera phone article is ACCEPTED
    phone_article = {
        "title": "Best Camera Phones Under Rs 30,000 in India (2026): Motorola Edge 50 Pro, Realme 13 Pro+",
        "snippet": "The Motorola Edge 50 Pro features a 50MP Sony LYT sensor with OIS, offering class-leading daylight HDR and natural low-light shots.",
        "url": "https://www.91mobiles.com/best-camera-phones-under-30000-india"
    }
    accepted_phone, _ = SourceFilter.filter_and_rank([phone_article], intent=intent)
    assert len(accepted_phone) == 1
    assert accepted_phone[0]["relevance_score"] >= 65.0


def test_master_b_programming_laptop_intent_and_plan():
    """
    Test B: Programming laptop under 60k
    - Programming requirements drive the comparison.
    - RAM, processor, keyboard are prioritized over gaming.
    """
    analyzer = QueryAnalyzer()
    intent = analyzer.analyze("Suggest a laptop under ₹60,000 for programming.")

    assert intent.domain == "laptops"
    assert intent.explicit_constraints.get("max_budget") == 60000
    assert any("cpu" in c.lower() or "ram" in c.lower() or "performance" in c.lower() for c in intent.primary_criteria)

    planner = ResearchPlanner()
    plan = planner.create_plan(intent.original_query, intent=intent)
    assert len(plan.subquestions) >= 3
    # Check that questions focus on programming/specs rather than gaming
    q_texts = " ".join([q.question_text.lower() for q in plan.subquestions])
    assert "programming" in q_texts or "performance" in q_texts or "ram" in q_texts


def test_master_c_research_paper_search():
    """
    Test C: Research paper search
    - Identifies literature_review intent and academic domain.
    - Requires dates and peer review.
    """
    analyzer = QueryAnalyzer()
    intent = analyzer.analyze("Find recent research papers on computer vision object detection.")

    assert intent.domain == "academic_research"
    assert intent.main_intent == "literature_review"
    assert "recent" in intent.time_sensitivity.lower() or "202" in intent.time_sensitivity


def test_master_d_conflicting_evidence_evaluation():
    """
    Test D: Conflicting evidence
    - Conflicting assertions are properly distinguished.
    """
    analyst = ResearchAnalyst()
    claim = "The Motorola Edge 50 Pro exhibits superior low-light camera clarity."
    
    supporting_excerpt = "In night testing, the Motorola Edge 50 Pro captured sharper low-light details with lower noise than competitors."
    contradicting_excerpt = "In low-light scenarios, the Motorola Edge 50 Pro failed to capture sharp details and exhibited significant sensor noise."

    stat_sup, _ = analyst.verify_claim(claim, supporting_excerpt)
    assert stat_sup in (VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED)

    stat_con, _ = analyst.verify_claim(claim, contradicting_excerpt)
    assert stat_con == VerificationStatus.CONTRADICTED


def test_master_e_insufficient_evidence_unanswered_handling():
    """
    Test E: Insufficient evidence
    - Coverage tracker marks question as UNANSWERED or PARTIALLY_ANSWERED when evidence is missing.
    - Quality gate requires acknowledgment of unresolved questions in limitations.
    """
    store = ResearchStore()
    run = store.init_run("Unobtainium market valuation in 2045")
    planner = ResearchPlanner()
    plan = planner.create_plan(run.original_question)
    store.set_plan(plan, run.run_id)

    # Subquestion with no evidence must be marked UNANSWERED
    q = plan.subquestions[0]
    store.update_question_status(q.question_id, CoverageStatus.UNANSWERED, unresolved_reason="No public pricing data exists.")

    generator = ReportGenerator()
    report = generator.generate(run)
    store.set_final_report(report, run.run_id)

    # Quality Gate check
    qg = QualityGate().evaluate_and_repair(run)
    assert qg.checks["unresolved_questions_acknowledged"] is True


def test_master_f_broken_or_inaccessible_source_handling():
    """
    Test F: Broken or inaccessible source
    - Page extractor records failure rather than pretending full page was read.
    """
    extractor = PageExtractor(timeout_seconds=2)
    res = extractor.extract("https://nonexistent-broken-domain-999.xyz/page")
    assert res["status"] == "failed"
    assert res["error_message"] is not None


def test_master_g_citation_integrity():
    """
    Test G: Citation integrity
    - Claim supported by unrelated passage fails verification (UNVERIFIED).
    - Claim supported by relevant passage passes (SUPPORTED).
    """
    analyst = ResearchAnalyst()
    claim = "Realme 13 Pro+ features a 50MP Sony LYT-701 periscope telephoto camera."
    
    irrelevant_passage = "Tesla reported delivery numbers of 450,000 electric vehicles for the quarter."
    relevant_passage = "The Realme 13 Pro+ features a 50MP Sony LYT-701 sensor with periscope zoom and OIS."

    stat_bad, reason_bad = analyst.verify_claim(claim, irrelevant_passage)
    assert stat_bad in (VerificationStatus.UNVERIFIED, VerificationStatus.CONTRADICTED)

    stat_good, _ = analyst.verify_claim(claim, relevant_passage)
    assert stat_good == VerificationStatus.SUPPORTED
