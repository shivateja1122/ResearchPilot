from __future__ import annotations
import pytest
from models.schemas import (
    ResearchPlan, ResearchQuestion, Source, Evidence,
    CoverageStatus, VerificationStatus, SearchRound
)
from storage.research_store import ResearchStore
from tools.page_extractor import PageExtractor
from tools.source_filter import SourceFilter
from tools.web_search import WebSearchTool
from agent.planner import ResearchPlanner
from agent.analyst import ResearchAnalyst
from agent.report_generator import ReportGenerator
from agent.orchestrator import ResearchOrchestrator
from agent.llm_client import LLMClient


def test_fr01_research_planning():
    """
    FR-01 Acceptance Criteria:
    - Broad query generates non-empty plan with 4-6 subquestions.
    - Subquestions have unique IDs and dimension tagging.
    """
    planner = ResearchPlanner()
    plan = planner.create_plan("What are the benefits and risks of generative AI in healthcare?")
    
    assert len(plan.subquestions) >= 4
    assert len(plan.subquestions) <= 6
    ids = [q.question_id for q in plan.subquestions]
    assert len(ids) == len(set(ids)), "Subquestion IDs must be unique"
    for q in plan.subquestions:
        assert q.dimension is not None
        assert len(q.question_text) > 10


def test_fr02_source_collection_and_deduplication():
    """
    FR-02 Acceptance Criteria:
    - Normalizes URLs and prevents duplicate sources.
    - Preserves stable source IDs.
    """
    store = ResearchStore()
    run = store.init_run("Quantum computing commercial viability")
    
    url1 = "https://www.example.com/article?utm_source=twitter&utm_medium=social"
    url2 = "https://example.com/article"  # Same URL after normalization
    
    s1 = store.add_source(title="Article 1", url=url1, snippet="Snippet 1", run_id=run.run_id)
    s2 = store.add_source(title="Article 1 Duplicate", url=url2, snippet="Snippet 2", run_id=run.run_id)
    
    assert s1.source_id == s2.source_id, "Normalized URLs must deduplicate to the same source ID"
    assert len(run.sources) == 1


def test_scenario_d_citation_mismatch():
    """
    Test Scenario D & FR-03:
    A claim paired with an irrelevant source passage must be flagged (e.g., Unverified)
    rather than accepted as supported.
    """
    analyst = ResearchAnalyst()
    
    claim = "Small hospitals achieved 35% margin improvement using automated clinical AI."
    irrelevant_excerpt = "The recipe requires two cups of flour and one tablespoon of vanilla extract."
    
    status, reason = analyst.verify_claim(claim, irrelevant_excerpt)
    assert status in (VerificationStatus.UNVERIFIED, VerificationStatus.CONTRADICTED)
    assert "not contain relevant" in reason.lower() or "insufficient" in reason.lower()


def test_scenario_c_conflicting_evidence():
    """
    Test Scenario C & FR-03:
    Two sources with genuinely differing assertions are evaluated accurately.
    """
    analyst = ResearchAnalyst()
    
    claim = "Clinical GenAI reduces physician documentation time."
    supporting_excerpt = "Physicians using clinical GenAI tools documented patient visits 40% faster."
    contradicting_excerpt = "Clinical GenAI tools failed to reduce documentation time and increased audit errors."
    
    status_supp, _ = analyst.verify_claim(claim, supporting_excerpt)
    assert status_supp in (VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED)
    
    status_contra, _ = analyst.verify_claim(claim, contradicting_excerpt)
    assert status_contra == VerificationStatus.CONTRADICTED


def test_scenario_e_search_and_extraction_failure_resilience():
    """
    Test Scenario E & FR-02:
    Failed URL extractions or invalid pages must not crash the application
    and must record failure status gracefully.
    """
    extractor = PageExtractor(timeout_seconds=2)
    # Non-existent or invalid domain
    res = extractor.extract("https://this-is-an-invalid-nonexistent-domain-test-xyz.org")
    
    assert res["status"] == "failed"
    assert res["error_message"] is not None
    assert isinstance(res["content"], str)


def test_fr04_and_fr05_coverage_tracker_and_adaptive_loop():
    """
    Test Scenario B, FR-04 & FR-05:
    Unresolved questions trigger targeted follow-up searches in Round 2.
    The orchestrator respects round budget limits.
    """
    store = ResearchStore()
    orchestrator = ResearchOrchestrator(
        store=store,
        max_research_rounds=2,
        max_follow_up_searches=2
    )
    
    run = orchestrator.run_research("Should small rural hospitals adopt generative AI?")
    
    assert run.research_plan is not None
    assert len(run.research_plan.subquestions) >= 4
    
    # Verify search rounds occurred
    assert len(run.search_rounds) >= 1
    assert len(run.search_rounds) <= 2, "Must not exceed max configured research rounds"
    
    # Check coverage status exists on every subquestion
    for q in run.research_plan.subquestions:
        assert q.status in [CoverageStatus.SUPPORTED, CoverageStatus.PARTIAL, CoverageStatus.UNRESOLVED]
    
    # Verify final report was generated
    assert run.final_report is not None
    assert run.final_report.title != ""
    assert len(run.final_report.key_findings) > 0
    assert len(run.final_report.references) > 0


def test_fr06_structured_report_generation():
    """
    FR-06 Acceptance Criteria:
    - Report includes all 9 required sections:
      Title, Executive Summary, Scope & Methodology, Key Findings,
      Evidence & Citations, Comparison/Conflicting Evidence,
      Recommendations, Limitations & Unresolved Questions, References.
    """
    store = ResearchStore()
    run = store.init_run("Post-quantum cryptography migration challenges")
    
    # Set up plan
    planner = ResearchPlanner()
    plan = planner.create_plan(run.original_question)
    store.set_plan(plan, run.run_id)
    
    # Add source
    source = store.add_source(
        title="NIST Post-Quantum Cryptography Report",
        url="https://csrc.nist.gov/projects/post-quantum-cryptography",
        snippet="NIST standardized ML-KEM and ML-DSA to withstand quantum cryptanalysis.",
        extracted_content="NIST standardized ML-KEM and ML-DSA to withstand quantum cryptanalysis.",
        run_id=run.run_id
    )
    
    # Add verified evidence
    store.add_evidence(
        claim_text="NIST has standardized ML-KEM and ML-DSA algorithms for post-quantum defense.",
        question_id=plan.subquestions[0].question_id,
        source_ids=[source.source_id],
        supporting_excerpts=["NIST standardized ML-KEM and ML-DSA to withstand quantum cryptanalysis."],
        verification_status=VerificationStatus.SUPPORTED,
        verification_reason="Direct alignment with NIST publication.",
        run_id=run.run_id
    )
    
    generator = ReportGenerator()
    report = generator.generate(run)
    
    md = report.markdown_content
    assert "# Evidence-Driven Research Report" in md
    assert "## 1. Executive Summary" in md
    assert "## 2. Research Scope and Methodology" in md
    assert "## 3. Key Findings" in md
    assert "## 4. Evidence and Citations" in md
    assert "## 5. Comparison of Findings & Conflicting Evidence" in md
    assert "## 6. Recommendations" in md
    assert "## 7. Limitations and Unresolved Questions" in md
    assert "## 8. Research Audit & Budget Summary" in md
    assert "## 9. References" in md


def test_page_extractor_sanitization_and_error_detection():
    """
    Verifies that:
    1. Jina Reader metadata headers and navigation links are stripped.
    2. 403 Forbidden / Access Denied error pages are flagged as failures rather than valid content.
    """
    extractor = PageExtractor()

    # Case 1: 403 Forbidden error page
    error_raw = (
        "Title: Access Denied\n"
        "URL Source: https://www.mckinsey.com/test\n"
        "Warning: Target URL returned error 403: Forbidden\n\n"
        "You don't have permission to access this server.\n"
    )
    title, body, status, err = extractor._sanitize_and_validate(error_raw, "Fallback")
    assert status == "failed"
    assert "403" in err or "access denied" in err.lower()
    assert body == ""

    # Case 2: Jina headers + navigation noise + real article text
    dirty_content = (
        "Title: Generative AI in Healthcare (2026): Trends, Benefits, Challenges\n"
        "URL Source: https://www.example.com/blog/generative-ai\n"
        "Published Time: 2026-05-12\n"
        "Markdown Content:\n"
        "[Skip to navigation]\n"
        "[Skip to main content]\n"
        "# Trending Tickers\n"
        "SPCX 160.57 (-4.19%)\n"
        "October Prime Day deals are almost gone\n\n"
        "Generative artificial intelligence is transforming clinical diagnostics and automated documentation.\n"
        "Hospitals adopting clinical LLMs report measurable reductions in administrative burnout and billing errors.\n"
    )
    title, clean_body, status, err = extractor._sanitize_and_validate(dirty_content, "Fallback")
    assert status == "success"
    assert "Title:" not in clean_body
    assert "URL Source:" not in clean_body
    assert "Markdown Content:" not in clean_body
    assert "Skip to navigation" not in clean_body
    assert "Trending Tickers" not in clean_body
    assert "SPCX" not in clean_body
    assert "Prime Day" not in clean_body
    assert "Generative artificial intelligence is transforming clinical diagnostics" in clean_body


def test_analyst_noise_rejection_and_relevance():
    """
    Verifies that:
    1. Off-topic noise (Delta Airlines, 403 Forbidden, Jina metadata) is flagged as noise.
    2. Verification classifies noise claims as UNVERIFIED rather than SUPPORTED.
    3. Claim extraction only extracts relevant sentences answering the subquestion.
    """
    analyst = ResearchAnalyst()

    # Noise detection check
    assert analyst.is_noise("Title: Generative AI in Healthcare")
    assert analyst.is_noise("URL Source: https://finance.yahoo.com")
    assert analyst.is_noise("Delta's Q3 results missed expectations Friday as higher fuel prices outweighed premium strength.")
    assert analyst.is_noise("Warning: Target URL returned error 403: Forbidden")
    assert not analyst.is_noise("Clinical generative AI significantly reduces documentation time for hospital physicians.")

    # Verification of noise claim must be UNVERIFIED
    noise_claim = "Delta's Q3 results missed expectations Friday as higher fuel prices outweighed premium strength."
    noise_excerpt = "Delta's Q3 results missed expectations Friday as higher fuel prices outweighed premium strength."
    stat, reason = analyst.verify_claim(noise_claim, noise_excerpt)
    assert stat == VerificationStatus.UNVERIFIED
    assert "boilerplate" in reason.lower() or "scraping" in reason.lower()

    # Extraction with relevance gating
    q = ResearchQuestion(
        question_id="Q1",
        question_text="What are the clinical and operational benefits of generative AI in healthcare?",
        dimension="benefits"
    )
    mixed_content = (
        "Trending Tickers: SPCX 160.57. Delta's Q3 results missed expectations due to higher fuel prices.\n"
        "Clinical generative AI automates discharge summaries and reduces physician documentation overhead by 40%.\n"
        "Shopping guides for October Prime Day feature top tech deals.\n"
    )
    extracted = analyst._heuristic_extract_claims(q.question_text, mixed_content)
    assert len(extracted) >= 1
    # Ensure extracted claim is the clinical AI sentence, not Delta Airlines or Prime Day
    claim_text = extracted[0][0]
    assert "generative ai" in claim_text.lower() or "clinical" in claim_text.lower()
    assert "delta" not in claim_text.lower()
    assert "prime day" not in claim_text.lower()
