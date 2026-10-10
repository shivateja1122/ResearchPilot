"""
Multi-Agent Test Suite (Phase 11).
Tests all 10 scenarios required by the Master Prompt:
1. Research planning
2. Irrelevant sources
3. Unsupported claim
4. Citation mismatch
5. Gap recovery
6. Conflicting evidence
7. Tool failure
8. Final quality gate
9. State integrity
10. End-to-end multi-agent workflow
"""
import pytest
from unittest.mock import MagicMock, patch
from state import ResearchState
from orchestrator import ResearchOrchestrator
from agents.research_planner import ResearchPlannerAgent
from agents.researcher import ResearcherAgent
from agents.evidence_analyst import EvidenceAnalystAgent
from agents.report_writer import ReportWriterAgent
from tools.source_filter import SourceFilter
from agent.claim_verifier import ClaimVerifier
from agent.citation_validator import CitationValidator
from agent.contradiction_detector import ContradictionDetector
from agent.quality_gate import QualityGate
from models.schemas import (
    ResearchRun, ResearchPlan, ResearchQuestion, Source,
    Evidence, VerifiedClaim, CoverageStatus, VerificationStatus,
    CitationStatus, QueryIntent, FinalReport
)
from storage.research_store import ResearchStore


def test_1_research_planning():
    """Test 1: Research Planning Agent extracts constraints, criteria, and query-specific questions."""
    planner = ResearchPlannerAgent()
    query = "Suggest a good camera phone under ₹30,000 in India."
    plan = planner.plan(query)

    assert plan["plan_id"].startswith("PLAN_")
    assert plan["original_query"] == query
    assert "camera" in " ".join(plan.get("primary_criteria", [])).lower()
    
    constraints = plan.get("constraints", {})
    assert constraints.get("max_budget") == 30000 or "30000" in str(constraints)
    assert plan.get("geographic_scope") == "India" or constraints.get("geo") == "India"
    
    # Must have 3 to 7 focused research questions
    assert 3 <= len(plan["research_questions"]) <= 7
    for q in plan["research_questions"]:
        assert q["question_id"].startswith("Q")
        assert len(q["question"]) > 10
        assert q["status"] == "PLANNED"


def test_2_irrelevant_sources():
    """Test 2: Dual-stage filter rejects unrelated EV battery articles from smartphone camera research."""
    intent = QueryIntent(
        original_query="Suggest a good camera phone under ₹30,000 in India.",
        domain="smartphones",
        topic="smartphones under 30000 in India with good camera",
        primary_criteria=["camera quality", "OIS"],
        excluded_topics=["electric vehicles", "ev battery", "charging station"]
    )
    subq = ResearchQuestion(
        question_id="Q1",
        question_text="Which smartphones have optical image stabilization and Sony sensors?",
        dimension="camera_sensor_ois"
    )

    test_sources = [
        {
            "title": "Top Camera Phones Under 30,000 in India - 91Mobiles",
            "url": "https://www.91mobiles.com/top-camera-phones-under-30000",
            "snippet": "Motorola Edge 50 Pro and Realme 12 Pro Plus offer 50MP Sony sensors with optical image stabilization (OIS) in India under 30000."
        },
        {
            "title": "Electric Commercial Vehicle Battery Charging Station Specifications",
            "url": "https://www.fleet-ev.com/charging-stations",
            "snippet": "High power 350kW commercial electric vehicle fast charging station infrastructure for logistics fleet batteries."
        }
    ]

    accepted, rejected = SourceFilter.filter_and_rank(test_sources, intent=intent, question=subq, threshold=58.0)

    # EV article must be rejected
    rejected_urls = [r["url"] for r in rejected]
    assert "https://www.fleet-ev.com/charging-stations" in rejected_urls
    
    # Check that rejection reason indicates off-topic/negative filter
    ev_rejection = next(r for r in rejected if "fleet-ev.com" in r["url"])
    assert "off-topic" in ev_rejection["rejection_reason"].lower() or "negative" in ev_rejection["rejection_reason"].lower() or "low relevance" in ev_rejection["rejection_reason"].lower()

    # Camera article must be accepted
    accepted_urls = [a["url"] for a in accepted]
    assert "https://www.91mobiles.com/top-camera-phones-under-30000" in accepted_urls


def test_3_unsupported_claim():
    """Test 3: Comparative superlatives cannot be marked SUPPORTED solely by spec sheets."""
    verifier = ClaimVerifier()
    
    claim = "The Motorola Edge 50 Pro is the best camera phone under ₹30,000."
    # Excerpt only mentions specs, not comparative proof
    spec_excerpt = "The Motorola Edge 50 Pro features a 50MP main camera with f/1.4 aperture and 125W charging."

    result = verifier.verify(claim, spec_excerpt)

    # Must NOT be marked supported
    assert result.status != VerificationStatus.SUPPORTED
    assert result.status in [VerificationStatus.UNVERIFIED, VerificationStatus.PARTIALLY_SUPPORTED]
    assert any("comparative" in lim.lower() or "superlative" in lim.lower() for lim in result.limitations) or "comparative" in result.verification_reason.lower()


def test_4_citation_mismatch():
    """Test 4: Citation validator fails when cited excerpt discusses battery instead of OIS."""
    validator = CitationValidator()
    
    run = ResearchRun(
        run_id="test_mismatch",
        original_question="Camera stabilization test"
    )
    run.sources["SRC_BATTERY"] = Source(
        source_id="SRC_BATTERY",
        title="Battery Life Review",
        url="https://example.com/battery-review",
        extracted_content="The device packs a 5000 mAh battery that easily lasts 1.5 days on a single charge."
    )
    run.evidence_records["EVD_OIS"] = Evidence(
        claim_id="EVD_OIS",
        claim_text="The phone features hardware optical image stabilization (OIS) for blur-free photography.",
        question_id="Q1",
        source_id="SRC_BATTERY",
        supporting_excerpt="The device packs a 5000 mAh battery that easily lasts 1.5 days on a single charge."
    )

    validator.validate_all(run)

    cit_result = run.citation_validations.get("EVD_OIS")
    assert cit_result is not None
    assert cit_result.citation_status == CitationStatus.INVALID
    assert not cit_result.claim_supported


def test_5_gap_recovery():
    """Test 5: Unanswered research questions create targeted follow-up tasks and respect retry bounds."""
    analyst = EvidenceAnalystAgent()

    plan = {
        "original_query": "Camera smartphones under 30000",
        "research_questions": [
            {
                "question_id": "Q1",
                "question": "Which phones offer 50MP Sony sensors?",
                "dimension": "sensor_specs",
                "priority": "high"
            },
            {
                "question_id": "Q2",
                "question": "How do these phones perform in night/low-light mode?",
                "dimension": "low_light_performance",
                "priority": "high"
            }
        ]
    }
    
    # Q1 has supported evidence, Q2 has NO evidence
    evidence = [
        {
            "evidence_id": "EVD_001",
            "source_id": "SRC_001",
            "question_id": "Q1",
            "claim": "Motorola Edge 50 Pro has a 50MP sensor with OIS.",
            "supporting_excerpt": "Motorola Edge 50 Pro features a 50MP primary sensor with OIS."
        },
        {
            "evidence_id": "EVD_002",
            "source_id": "SRC_002",
            "question_id": "Q1",
            "claim": "Realme 12 Pro Plus has a 50MP Sony IMX890 sensor.",
            "supporting_excerpt": "Realme 12 Pro Plus features a 50MP Sony IMX890 sensor."
        }
    ]
    sources = [
        {"source_id": "SRC_001", "url": "https://example.com/1", "extracted_content": "features a 50MP primary sensor with OIS"},
        {"source_id": "SRC_002", "url": "https://example.com/2", "extracted_content": "features a 50MP Sony IMX890 sensor"}
    ]

    analysis = analyst.analyze(plan, sources, evidence, is_final_round=False)

    # Q1 should be ANSWERED, Q2 should be UNANSWERED
    assert analysis["coverage"]["Q1"]["status"] == "ANSWERED"
    assert analysis["coverage"]["Q2"]["status"] == "UNANSWERED"

    # Must generate a targeted follow-up task for Q2
    q2_follow_up = next((t for t in analysis["follow_up_tasks"] if t["question_id"] == "Q2"), None)
    assert q2_follow_up is not None
    assert q2_follow_up["dimension"] == "low_light_performance"


def test_6_conflicting_evidence():
    """Test 6: Disagreements between sources are recorded with UNRESOLVED_DISCLOSED status."""
    detector = ContradictionDetector()
    run = ResearchRun(run_id="test_conflict", original_question="Camera testing")
    
    run.evidence_records["EVD_A"] = Evidence(
        claim_id="EVD_A",
        claim_text="The Motorola Edge 50 Pro produces exceptionally sharp and clean low-light photos.",
        question_id="Q1",
        source_id="SRC_1"
    )
    run.evidence_records["EVD_B"] = Evidence(
        claim_id="EVD_B",
        claim_text="The Motorola Edge 50 Pro exhibits excessive noise and soft details in low-light night mode.",
        question_id="Q1",
        source_id="SRC_2"
    )

    conflicts = detector.detect_conflicts(run)

    assert len(conflicts) >= 1
    conflict = conflicts[0]
    assert conflict.resolution_status == "UNRESOLVED_DISCLOSED"
    assert "Motorola Edge 50 Pro" in conflict.entity or "Motorola" in conflict.entity


def test_7_tool_failure_resilience():
    """Test 7: Search provider errors are recorded in errors array without fabricating evidence."""
    mock_search = MagicMock()
    mock_search.search.side_effect = TimeoutError("Search upstream connection timed out after 10s")

    researcher = ResearcherAgent(search_tool=mock_search)
    task = {
        "task_id": "TASK_TIMEOUT",
        "question_id": "Q1",
        "question": "What is the low light performance?"
    }

    output = researcher.execute_task(task)

    # Error must be recorded
    assert len(output["errors"]) >= 1
    assert "timed out" in output["errors"][0].lower()
    
    # Must NOT fabricate evidence
    assert len(output["evidence"]) == 0
    assert len(output["unresolved_information"]) >= 1


def test_8_final_quality_gate_repair():
    """Test 8: Quality Gate detects off-topic insertions and repairs the report text."""
    qg = QualityGate()
    
    run = ResearchRun(
        run_id="test_qg_repair",
        original_question="Suggest a good camera phone under ₹30,000 in India."
    )
    run.query_intent = QueryIntent(
        original_query="Suggest a good camera phone under ₹30,000 in India.",
        domain="smartphones",
        topic="smartphones camera under 30000 in India",
        excluded_topics=["electric vehicles", "ev battery", "commercial fleet"]
    )
    run.final_report = FinalReport(
        title="Best Camera Phones Under 30000",
        executive_summary="Direct answer recommending Motorola Edge 50 Pro.",
        scope_and_methodology="Tested across multiple reviews.",
        key_findings=[
            "**Motorola Edge 50 Pro**: Best camera phone under 30000 with 50MP OIS sensor. ([GSM](https://gsmarena.com))",
            "**Electric Vehicle Commercial Fleet**: Heavy duty commercial fleet battery fast charging stations. ([EV](https://ev.com))"
        ],
        references=[Source(source_id="SRC_1", title="GSM", url="https://gsmarena.com")]
    )

    result = qg.evaluate_and_repair(run)

    # Check that repair action was executed to prune off-topic item
    assert len(result.repairs_applied) >= 1 or len(result.critical_failures) >= 1
    # Verify that the off-topic commercial fleet was removed from key_findings
    findings_text = " ".join(run.final_report.key_findings).lower()
    assert "commercial fleet" not in findings_text


def test_9_state_integrity():
    """Test 9: ResearchState maintains deduplication, provenance, and thread isolation."""
    state1 = ResearchState(original_query="Query 1")
    state2 = ResearchState(original_query="Query 2")

    # Ensure separate runs have unique IDs
    assert state1.run_id != state2.run_id

    # Add same source URL twice to state1 - must deduplicate
    sid1 = state1.add_source({"url": "https://example.com/test", "title": "Test 1"})
    sid2 = state1.add_source({"url": "https://example.com/test", "title": "Test 1 Dupe"})
    assert sid1 == sid2
    assert len(state1.sources) == 1

    # Add evidence to state1 - state2 must remain empty
    state1.add_evidence_item({"claim": "Fact 1", "supporting_excerpt": "Excerpt 1"})
    assert len(state1.evidence) == 1
    assert len(state2.evidence) == 0


def test_10_end_to_end_multi_agent_workflow():
    """Test 10: End-to-end multi-agent execution with four specialized agents, orchestrator, and QualityGate."""
    store = ResearchStore()
    orchestrator = ResearchOrchestrator(
        store=store,
        max_research_rounds=2,
        max_follow_up_searches=2
    )

    run = orchestrator.run_research("Suggest a good camera phone under ₹30,000 in India.")

    # 1. Planner Agent Output Verified
    assert run.query_intent is not None
    assert run.research_plan is not None
    assert len(run.research_plan.subquestions) >= 3

    # 2. Researcher Agent Output Verified
    assert len(run.sources) > 0 or len(run.rejected_sources) > 0
    assert len(run.evidence_records) > 0

    # 3. Evidence Analyst Output Verified
    for ev in run.evidence_records.values():
        assert ev.verification_status in [
            VerificationStatus.SUPPORTED,
            VerificationStatus.PARTIALLY_SUPPORTED,
            VerificationStatus.UNVERIFIED,
            VerificationStatus.CONTRADICTED
        ]

    # 4. Report Writer Output Verified
    assert run.final_report is not None
    assert run.final_report.title != ""
    assert len(run.final_report.key_findings) > 0
    assert run.final_report.direct_answer is not None or run.final_report.executive_summary != ""

    # 5. Quality Gate Verified
    assert run.quality_gate_result is not None
    assert run.quality_gate_result.score >= 0.70

    # 6. Audit Log Verified
    assert run.research_audit is not None
    assert run.research_audit.run_id == run.run_id
    assert len(run.research_audit.planned_questions) >= 3
