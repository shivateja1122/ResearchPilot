from __future__ import annotations
import pytest
from models.schemas import (
    ResearchPlan, ResearchQuestion, Source, Evidence,
    CoverageStatus, VerificationStatus, CitationStatus,
    CitationValidation, ContradictionRecord, QualityGateResult,
    QueryIntent, FinalReport, CriticalFailure
)
from storage.research_store import ResearchStore
from tools.source_filter import SourceFilter
from tools.page_extractor import PageExtractor
from agent.query_analyzer import QueryAnalyzer
from agent.planner import ResearchPlanner
from agent.analyst import ResearchAnalyst
from agent.claim_verifier import ClaimVerifier
from agent.citation_validator import CitationValidator
from agent.contradiction_detector import ContradictionDetector
from agent.gap_recovery import GapRecoveryEngine
from agent.quality_gate import QualityGate
from agent.report_generator import ReportGenerator
from agent.orchestrator import ResearchOrchestrator


def test_scenario_1_irrelevant_source_injection():
    """
    Test 1: Irrelevant source injection
    Query: "Suggest a good camera phone under ₹30,000 in India."
    Mock search results include smartphone camera reviews and an electric-vehicle battery article.
    Expected:
    - EV article is rejected as irrelevant (score < 40 or negative boundary matched).
    - It cannot support smartphone camera claims.
    - Rejection is recorded in store / audit.
    """
    analyzer = QueryAnalyzer()
    intent = analyzer.analyze("Suggest a good camera phone under ₹30,000 in India.")

    store = ResearchStore()
    run = store.init_run(intent.original_query)
    store.set_query_intent(intent, run_id=run.run_id)

    ev_result = {
        "title": "Geotab data reveals EV battery health and degradation patterns in fleet vehicles",
        "snippet": "Study of electric vehicle batteries shows degradation is slower with AC charging compared to DC fast charging.",
        "url": "https://www.businessinsider.com/ev-battery-health-report"
    }
    phone_result = {
        "title": "Best Camera Phones Under Rs 30,000 in India: Realme 13 Pro+ & Moto Edge 50 Pro",
        "snippet": "Motorola Edge 50 Pro offers a 50MP OIS camera with excellent low-light clarity and natural skin tones.",
        "url": "https://www.91mobiles.com/best-camera-phones-under-30000"
    }

    accepted, rejected = SourceFilter.filter_and_rank([ev_result, phone_result], intent=intent, threshold=60.0)

    # EV article must be rejected
    assert len(rejected) == 1
    assert "businessinsider.com" in rejected[0]["url"]
    assert "Off-topic" in rejected[0]["rejection_reason"] or "domain" in rejected[0]["rejection_reason"].lower()

    # Store rejected source
    rej_source = store.add_rejected_source(
        title=rejected[0]["title"],
        url=rejected[0]["url"],
        snippet=rejected[0]["snippet"],
        relevance_score=rejected[0]["relevance_score"],
        rejection_reason=rejected[0]["rejection_reason"],
        run_id=run.run_id
    )
    assert rej_source.accepted is False
    assert rej_source.source_id in run.rejected_sources

    # Phone article must be accepted
    assert len(accepted) == 1
    assert "91mobiles.com" in accepted[0]["url"]


def test_scenario_2_unsupported_comparative_claim():
    """
    Test 2: Unsupported comparative claim
    Claim: "This is the best camera phone under ₹30,000."
    Evidence: An official spec page confirms only main camera megapixel count (50 MP).
    Expected:
    - Claim fails comparative verification (UNVERIFIED) because spec alone does not establish comparative superiority.
    """
    verifier = ClaimVerifier()

    claim = "This is the best camera phone under ₹30,000 in India."
    spec_evidence = "The smartphone features a 50 MP primary rear sensor with f/1.8 aperture and LED flash."

    result = verifier.verify(
        claim_text=claim,
        supporting_excerpt=spec_evidence,
        source_type="official_specs"
    )

    assert result.status == VerificationStatus.UNVERIFIED
    assert "comparative" in result.verification_reason.lower()


def test_scenario_3_invalid_citation():
    """
    Test 3: Invalid citation
    Claim: "The smartphone includes optical image stabilization (OIS) for steady video."
    Evidence: The cited page discusses only battery capacity and charging wattage.
    Expected:
    - Citation validation flags INVALID or claim_supported=False.
    """
    validator = CitationValidator()
    store = ResearchStore()
    run = store.init_run("Smartphone camera verification")

    # Add source with battery text only
    source = store.add_source(
        title="Battery Life and Charging Speed Review",
        url="https://example.com/battery-test",
        snippet="The device includes a 5,000 mAh battery supporting 68W TurboPower charging.",
        extracted_content="The device includes a 5,000 mAh battery supporting 68W TurboPower charging.",
        run_id=run.run_id
    )

    claim = "The smartphone includes optical image stabilization (OIS) for steady video."

    v = validator.validate_citation(
        citation_id="CIT_001",
        claim_id="CLM_001",
        claim_text=claim,
        source_id=source.source_id,
        run=run,
        supporting_excerpt="The device includes a 5,000 mAh battery supporting 68W TurboPower charging."
    )

    assert v.citation_status in (CitationStatus.INVALID, CitationStatus.PARTIALLY_VALID)
    assert v.claim_supported is False


def test_scenario_4_stale_pricing():
    """
    Test 4: Stale pricing
    Claim: "The phone costs ₹27,999 in India."
    Evidence: An outdated article from 2022 lists that price.
    Expected:
    - Current-price claim remains unverified (UNVERIFIED) due to outdated source date.
    """
    verifier = ClaimVerifier()

    claim = "The phone costs ₹27,999 in India."
    outdated_excerpt = "The device is priced at ₹27,999 for the base 8GB/128GB variant."

    result = verifier.verify(
        claim_text=claim,
        supporting_excerpt=outdated_excerpt,
        source_date="2022-08-15"
    )

    assert result.status == VerificationStatus.UNVERIFIED
    assert "outdated" in result.verification_reason.lower() or "price" in result.verification_reason.lower()


def test_scenario_5_contradictory_reviews():
    """
    Test 5: Contradictory reviews
    Two independent reviews disagree about low-light performance.
    Expected:
    - Disagreement is detected and recorded in ContradictionRecord.
    - Preserves unresolved conflict in audit.
    """
    detector = ContradictionDetector()
    store = ResearchStore()
    run = store.init_run("Camera performance test")

    s1 = store.add_source(
        title="TechRadar Review",
        url="https://techradar.com/phone-review",
        publication_date="2025-06-10",
        run_id=run.run_id
    )
    s2 = store.add_source(
        title="GSMArena Review",
        url="https://gsmarena.com/phone-review",
        publication_date="2025-08-15",
        run_id=run.run_id
    )

    # Add opposing evidence items
    ev1 = store.add_evidence(
        claim_text="The camera delivers strong low-light clarity and impressive noise control.",
        question_id="Q1",
        source_ids=[s1.source_id],
        supporting_excerpts=["The camera delivers strong low-light clarity and impressive noise control."],
        verification_status=VerificationStatus.SUPPORTED,
        run_id=run.run_id
    )

    ev2 = store.add_evidence(
        claim_text="The camera exhibits poor low-light detail and suffers from noisy output.",
        question_id="Q1",
        source_ids=[s2.source_id],
        supporting_excerpts=["The camera exhibits poor low-light detail and suffers from noisy output."],
        verification_status=VerificationStatus.SUPPORTED,
        run_id=run.run_id
    )

    conflicts = detector.detect_conflicts(run)
    assert len(conflicts) >= 1
    c = conflicts[0]
    assert c.resolution_status == "UNRESOLVED_DISCLOSED"
    assert "divergence" in c.disagreement_description.lower() or "conflict" in c.disagreement_description.lower()


def test_scenario_6_missing_evidence_and_gap_recovery():
    """
    Test 6: Missing evidence
    A research question remains unanswered after initial search.
    Expected:
    - Gap recovery identifies missing aspect, determines cause, and formulates targeted follow-up query.
    - Question status reflects PARTIALLY_ANSWERED or UNANSWERED honestly.
    """
    engine = GapRecoveryEngine()
    store = ResearchStore()
    run = store.init_run("Smartphone market inquiry")

    q = ResearchQuestion(
        question_id="Q3",
        question_text="What is the current retail price and discount availability in India?",
        dimension="pricing",
        required_evidence="current retail price in INR"
    )
    intent = QueryIntent(
        original_query="Camera phones under 30k",
        topic="Motorola Edge 50 Pro",
        geographic_scope="India"
    )

    status, conf, missing, cause = engine.evaluate_question_status(q, run, is_final_round=False)
    assert status == CoverageStatus.PARTIALLY_ANSWERED
    assert cause == "missing_sources"

    follow_up_query = engine.formulate_follow_up_query(q, intent, missing)
    assert "Motorola Edge 50 Pro" in follow_up_query
    assert "India" in follow_up_query
    assert "pricing" in follow_up_query or "price" in follow_up_query


def test_scenario_7_fabricated_quotation():
    """
    Test 7: Fabricated quotation
    The model generates a claim containing a quotation that does not appear in the source passage.
    Expected:
    - Exact-quote validation fails (INVALID).
    """
    validator = CitationValidator()
    store = ResearchStore()
    run = store.init_run("Quotation verification")

    source = store.add_source(
        title="Review Excerpt",
        url="https://example.com/camera",
        snippet="The camera produces natural colors under bright daylight conditions.",
        extracted_content="The camera produces natural colors under bright daylight conditions.",
        run_id=run.run_id
    )

    # Claim contains a fake direct quotation
    fabricated_claim = 'Reviewers noted "the sensor destroys all competition in dark night shots" with zero noise.'

    v = validator.validate_citation(
        citation_id="CIT_001",
        claim_id="CLM_001",
        claim_text=fabricated_claim,
        source_id=source.source_id,
        run=run,
        supporting_excerpt=source.extracted_content
    )

    assert v.citation_status == CitationStatus.INVALID
    assert "quotation" in v.reason.lower() or "verbatim" in v.reason.lower()


def test_scenario_8_correctly_supported_claim():
    """
    Test 8: Correctly supported claim
    An inspected official specification explicitly confirms a specific product feature.
    Expected:
    - Claim passes verification with SUPPORTED status.
    """
    verifier = ClaimVerifier()

    claim = "The Motorola Edge 50 Pro features a 50 MP main camera with optical image stabilization."
    spec = "Motorola Edge 50 Pro features a 50 MP main camera with optical image stabilization (OIS) and f/1.4 aperture."

    result = verifier.verify(
        claim_text=claim,
        supporting_excerpt=spec,
        source_type="official_specs"
    )

    assert result.status == VerificationStatus.SUPPORTED
    assert result.confidence >= 0.85


def test_scenario_9_tool_failure_resilience():
    """
    Test 9: Tool failure
    The page extraction encounters a 403 Forbidden or network timeout.
    Expected:
    - Failure is cleanly recorded.
    - System does not pretend missing page was inspected.
    """
    extractor = PageExtractor()

    # 403 error page
    error_raw = "Warning: Target URL returned error 403: Forbidden\nAccess denied."
    title, body, status, err = extractor._sanitize_and_validate(error_raw, "Fallback")

    assert status == "failed"
    assert "403" in err or "access denied" in err.lower()
    assert body == ""

    # CitationValidator treats failed page as SOURCE_UNAVAILABLE
    store = ResearchStore()
    run = store.init_run("Tool failure test")
    s_failed = store.add_source(
        title="Inaccessible Page",
        url="https://example.com/blocked",
        snippet="",
        retrieval_status="failed",
        error_message="HTTP 403 Forbidden",
        run_id=run.run_id
    )

    validator = CitationValidator()
    val = validator.validate_citation(
        citation_id="CIT_FAIL",
        claim_id="CLM_001",
        claim_text="Some claim",
        source_id=s_failed.source_id,
        run=run
    )
    assert val.citation_status == CitationStatus.SOURCE_UNAVAILABLE


def test_scenario_10_final_quality_gate_critical_check_and_bounded_repair():
    """
    Test 10: Final quality gate critical check & bounded repair
    The report contains an unsupported comparative claim and an off-topic finding.
    Expected:
    - Quality gate detects critical failures.
    - Bounded repair auto-prunes off-topic finding and repairs the report.
    - Repaired report passes with transparent audit trail.
    """
    qg = QualityGate()
    store = ResearchStore()
    run = store.init_run("Suggest a good camera mobile under ₹30,000 in India.")

    intent = QueryIntent(
        original_query=run.original_question,
        topic="Smartphones under 30k",
        excluded_topics=["electric vehicles", "automotive batteries"]
    )
    run.query_intent = intent

    source = store.add_source(
        title="Motorola Edge 50 Pro Review",
        url="https://91mobiles.com/moto-review",
        run_id=run.run_id
    )
    ev = store.add_evidence(
        claim_text="Motorola Edge 50 Pro features a 50MP OIS camera with natural color science.",
        question_id="Q1",
        source_ids=[source.source_id],
        supporting_excerpts=["Motorola Edge 50 Pro features a 50MP OIS camera with natural color science."],
        verification_status=VerificationStatus.SUPPORTED,
        run_id=run.run_id
    )

    # Final report containing an off-topic finding from EV domain
    report = FinalReport(
        title="Evidence-Driven Research Report: Camera Mobile",
        executive_summary="Motorola Edge 50 Pro and Realme 13 Pro+ offer the best camera setups in India under 30k.",
        scope_and_methodology="Tested across multiple criteria.",
        key_findings=[
            "Motorola Edge 50 Pro features a 50MP OIS camera with natural color science.",
            "EV battery degradation averages 2.3% in electric commercial delivery vehicles."  # Deliberate off-topic finding!
        ],
        evidence_and_citations=[ev],
        conflicting_evidence="None",
        recommendations=["Choose Motorola Edge 50 Pro for camera quality."],
        limitations_and_unresolved=["Pricing may fluctuate."],
        references=[source]
    )
    run.final_report = report

    # Evaluate and repair
    result = qg.evaluate_and_repair(run)

    # Off-topic finding must be auto-pruned
    assert any("electric vehicles" in rep.lower() or "off-topic" in rep.lower() for rep in result.repairs_applied)
    assert not any("electric vehicle" in kf.lower() for kf in report.key_findings)
    assert result.report_passed is True
