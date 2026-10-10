from __future__ import annotations
import os
import time
import json
import streamlit as st
from datetime import datetime, timezone

from models.schemas import (
    ResearchRun, CoverageStatus, VerificationStatus,
    ResearchQuestion, Evidence, Source
)
from storage.research_store import ResearchStore
from agent.orchestrator import ResearchOrchestrator
from agent.llm_client import LLMClient

# Set Page Config
st.set_page_config(
    page_title="ResearchPilot AI — Reliable Multi-Step Research Assistant",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .reportview-container {
        background: #f8fafc;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #475569;
        margin-bottom: 1.5rem;
    }
    .hero-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #ffffff;
        padding: 24px 28px;
        border-radius: 12px;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(15,23,42,0.12);
    }
    .finding-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #3b82f6;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .rec-card {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-left: 4px solid #22c55e;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .limitation-card {
        background: #fffbeb;
        border: 1px solid #fde68a;
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .badge-supported {
        background-color: #d1fae5;
        color: #065f46;
        padding: 3px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
        display: inline-block;
    }
    .badge-partial {
        background-color: #fef3c7;
        color: #92400e;
        padding: 3px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
        display: inline-block;
    }
    .badge-contradicted {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 3px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
        display: inline-block;
    }
    .badge-unverified {
        background-color: #f1f5f9;
        color: #475569;
        padding: 3px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
        display: inline-block;
    }
    .badge-dimension {
        background-color: #e0e7ff;
        color: #3730a3;
        padding: 2px 8px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.75rem;
        text-transform: uppercase;
    }
    .card-box {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)


# Initialize Session State
if "store" not in st.session_state:
    st.session_state.store = ResearchStore()
if "current_run_id" not in st.session_state:
    st.session_state.current_run_id = None
if "run_in_progress" not in st.session_state:
    st.session_state.run_in_progress = False


# Sidebar Configuration
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/search-in-list.png", width=64)
    st.title("ResearchPilot AI")
    st.caption("Reliable Multi-Step Research Assistant")
    st.markdown("---")

    st.subheader("🔌 Connected Services")
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_tavily = bool(os.getenv("TAVILY_API_KEY"))
    has_jina = bool(os.getenv("READER_API_KEY"))

    st.markdown(f"{'🟢' if has_gemini else '⚪'} **LLM:** {'Gemini 3.8 Flash' if has_gemini else 'Heuristic / Local'}")
    st.markdown(f"{'🟢' if has_tavily else '⚪'} **Search:** {'Tavily AI Search' if has_tavily else 'DuckDuckGo'}")
    st.markdown(f"{'🟢' if has_jina else '⚪'} **Reader:** {'Jina Reader (Markdown)' if has_jina else 'BeautifulSoup'}")

    st.markdown("---")
    st.subheader("⚙️ Agent & LLM Settings")
    llm_provider = st.selectbox(
        "LLM Provider",
        options=["auto", "gemini", "openai", "heuristic"],
        index=0,
        help="Select AI reasoning backend or 'auto' to auto-detect."
    )

    api_key_input = st.text_input(
        "API Key (Optional override)",
        type="password",
        value="",
        placeholder="Loaded from .env" if (has_gemini or has_tavily) else "Enter key...",
    )

    custom_model = st.text_input(
        "Custom Model Name (Optional)",
        value="gemini-3.8-flash" if has_gemini else "",
        placeholder="e.g. gemini-3.8-flash or gpt-4o-mini"
    )

    st.markdown("---")
    st.subheader("🎯 Research Budget Limits")
    max_rounds = st.slider("Max Research Rounds", min_value=1, max_value=3, value=2, help="Round 1 = Initial search. Round 2 = Targeted gap recovery.")
    max_follow_ups = st.slider("Max Follow-Up Queries", min_value=1, max_value=6, value=4, help="Budget for targeted follow-up searches.")
    timeout_sec = st.slider("Search/Extraction Timeout (s)", min_value=5, max_value=20, value=10)

    st.markdown("---")
    if st.button("🔄 Reset / Clear Session", use_container_width=True):
        st.session_state.store = ResearchStore()
        st.session_state.current_run_id = None
        st.session_state.run_in_progress = False
        st.rerun()


# Main View Header
st.markdown("<div class='main-header'>🔬 ResearchPilot AI — Multi-Agent Research System</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-header'>"
    "Coordinated 4-agent research architecture: Agent 1 (Planner) &bull; Agent 2 (Researcher) &bull; "
    "Agent 3 (Evidence Analyst) &bull; Agent 4 (Report Writer) governed by Central Orchestrator & 12-point Quality Gate."
    "</div>",
    unsafe_allow_html=True
)

# Multi-Agent Architecture Chips
ag_c1, ag_c2, ag_c3, ag_c4, ag_c5 = st.columns(5)
with ag_c1:
    st.info("🧠 **Agent 1: Planner**\n\nIntent & Constraints")
with ag_c2:
    st.info("🔎 **Agent 2: Researcher**\n\nRetrieval & Strict Gate")
with ag_c3:
    st.info("⚖️ **Agent 3: Analyst**\n\n9-Pt Claim Verification")
with ag_c4:
    st.info("✍️ **Agent 4: Writer**\n\nDirect Answer & Citations")
with ag_c5:
    st.info("🛡️ **Quality Gate**\n\n12 Checks & Auto-Repair")

# Demo Query Presets
DEMO_PRESETS = [
    "Suggest me a good camera mobile under 30k in india",
    "Suggest a laptop under 60k for programming",
    "What are the benefits, risks, and adoption challenges of generative AI in healthcare?",
    "What is the commercial viability timeline and risk profile of post-quantum cryptography migration?"
]

col_input, col_preset = st.columns([3, 1.3])

with col_preset:
    selected_preset = st.selectbox("💡 Quick Presets", options=["Select a sample prompt..."] + DEMO_PRESETS)

with col_input:
    default_text = selected_preset if selected_preset != "Select a sample prompt..." else DEMO_PRESETS[0]
    user_query = st.text_area(
        "Research Question",
        value=default_text,
        height=72,
        placeholder="Enter a broad or specific research question..."
    )

start_button = st.button("🚀 Start Evidence-Driven Research", type="primary", use_container_width=True, disabled=st.session_state.run_in_progress)

# Execution Logic
if start_button and user_query.strip():
    st.session_state.run_in_progress = True
    
    provider_arg = None if llm_provider == "auto" else llm_provider
    key_arg = api_key_input.strip() if api_key_input.strip() else None
    model_arg = custom_model.strip() if custom_model.strip() else None
    
    llm_client = LLMClient(provider=provider_arg, api_key=key_arg, model_name=model_arg)
    
    orchestrator = ResearchOrchestrator(
        store=st.session_state.store,
        llm_client=llm_client,
        max_research_rounds=max_rounds,
        max_follow_up_searches=max_follow_ups,
        search_timeout=timeout_sec,
        page_timeout=timeout_sec
    )

    progress_bar = st.progress(0.0)
    status_text = st.empty()
    log_expander = st.expander("📡 Live Execution Logs", expanded=True)
    log_area = log_expander.empty()
    accumulated_logs = []

    def on_progress(stage: str, msg: str, pct: float, extra: dict):
        progress_bar.progress(min(pct, 1.0))
        status_text.markdown(f"**Current Phase:** {stage.upper().replace('_', ' ')} — *{msg}*")
        accumulated_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] [{stage.upper()}] {msg}")
        log_area.code("\n".join(accumulated_logs[-12:]), language="log")

    try:
        run = orchestrator.run_research(user_query.strip(), progress_callback=on_progress)
        st.session_state.current_run_id = run.run_id
        st.success(f"✅ Research completed for Run ID: `{run.run_id}`")
    except Exception as e:
        st.error(f"❌ Error during research execution: {str(e)}")
    finally:
        st.session_state.run_in_progress = False
        st.rerun()


# Display Results if a Run Exists
run: ResearchRun = st.session_state.store.get_run(st.session_state.current_run_id)

if run:
    st.markdown("---")
    stats = st.session_state.store.get_summary_stats(run.run_id)

    # Metrics Bar
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1:
        st.metric("Subquestions", f"{stats.get('total_subquestions', 0)}")
    with m2:
        st.metric("Accepted Sources", f"{stats.get('total_sources', 0)}")
    with m3:
        st.metric("Rejected Sources", f"{stats.get('rejected_sources_count', 0)}")
    with m4:
        st.metric("Verified Claims", f"{stats.get('total_claims', 0)}")
    with m5:
        qg_score = run.quality_gate_result.score if run.quality_gate_result else 1.0
        st.metric("Quality Gate", f"{int(qg_score * 100)}%")
    with m6:
        st.metric("Search Rounds", f"{stats.get('search_rounds_count', 0)}")

    tab_report, tab_coverage, tab_claims, tab_sources, tab_audit = st.tabs([
        "📄 Research Report",
        "🎯 Coverage & Questions",
        "🔍 Verified Claims Inspector",
        "🌐 Sources & Relevance Filter",
        "🔬 Research Audit & Quality Gate"
    ])

    # Tab 1: Research Report
    with tab_report:
        if run.final_report:
            col_v1, col_v2, col_v3 = st.columns([2.0, 1.3, 1.0])
            with col_v1:
                view_mode = st.radio(
                    "Report View Mode",
                    ["✨ Direct Answer & Visual Findings", "📄 Complete Markdown Document"],
                    horizontal=True,
                    label_visibility="collapsed"
                )
            with col_v2:
                try:
                    from agent.pdf_generator import ReportPDFGenerator
                    pdf_gen = ReportPDFGenerator()
                    pdf_bytes = pdf_gen.generate_pdf(run)
                    st.download_button(
                        label="📄 Download Professional PDF",
                        data=pdf_bytes,
                        file_name=f"research_report_{run.run_id}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                except Exception as pdf_err:
                    st.error(f"⚠️ PDF generation error: {str(pdf_err)}")
            with col_v3:
                st.download_button(
                    label="📥 Download Markdown",
                    data=run.final_report.markdown_content,
                    file_name=f"research_report_{run.run_id}.md",
                    mime="text/markdown",
                    use_container_width=True
                )

            # Display Research Status Notice if incomplete or draft
            if run.quality_gate_result and not run.quality_gate_result.report_passed:
                st.warning("⚠️ **Research Draft Notice:** Quality Gate identified unresolved critical items. This document is flagged as an incomplete research draft.")

            if view_mode == "✨ Direct Answer & Visual Findings":
                # Executive Answer Hero Banner
                st.markdown(f"""
                <div class='hero-banner'>
                    <div style='font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; font-weight: 600; margin-bottom: 6px;'>Direct Answer & Executive Verdict</div>
                    <div style='font-size: 1.35rem; font-weight: 700; color: #ffffff; margin-bottom: 12px;'>{run.final_report.title}</div>
                    <div style='font-size: 0.98rem; line-height: 1.6; color: #f1f5f9;'>{run.final_report.direct_answer or run.final_report.executive_summary}</div>
                </div>
                """, unsafe_allow_html=True)

                # Comparison Table (if generated)
                if run.final_report.comparison_table_markdown:
                    st.markdown("### 📊 Candidate Comparison & Specs")
                    st.markdown(run.final_report.comparison_table_markdown)
                    st.markdown("---")

                # Top Findings / Recommendations
                st.markdown("### 🔍 Verified Findings & Recommendations")
                st.caption("Backed by audited online sources. Click the source pills to view original articles directly:")
                for item in run.final_report.key_findings:
                    st.markdown(f"""
                    <div class='finding-card'>
                        <div style='font-size: 0.95rem; color: #1e293b; line-height: 1.5;'>
                            {item}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                # Actionable Recommendations
                if run.final_report.recommendations:
                    st.markdown("### 💡 Practical Takeaways & Buying Advice")
                    for rec in run.final_report.recommendations:
                        st.markdown(f"""
                        <div class='rec-card'>
                            <div style='font-size: 0.92rem; color: #166534; line-height: 1.5;'>
                                <strong>👉</strong> {rec}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                # Limitations & Unresolved
                if run.final_report.limitations_and_unresolved:
                    st.markdown("### ⚠️ Disclosures & Remaining Gaps")
                    for lim in run.final_report.limitations_and_unresolved:
                        st.markdown(f"""
                        <div class='limitation-card'>
                            <div style='font-size: 0.9rem; color: #92400e; line-height: 1.4;'>
                                <strong>Notice:</strong> {lim}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                # Sources
                st.markdown("### 🌐 Credible Sources Consulted")
                for s in run.final_report.references:
                    st.markdown(f"- **[{s.source_id}]** [{s.title}]({s.url}) &nbsp; *(Publisher: {s.publisher or 'Web'} | Status: `{s.retrieval_status}`)*")

            else:
                st.markdown(run.final_report.markdown_content)

        else:
            st.info("Report generation pending...")

    # Tab 2: Coverage & Subquestions
    with tab_coverage:
        st.subheader("Criteria-Driven Subquestions Coverage")
        st.markdown(
            "ResearchPilot AI monitors evidence sufficiency per subquestion and evaluates "
            "whether questions are resolved or require targeted gap recovery."
        )

        if run.research_plan:
            for q in run.research_plan.subquestions:
                status_val = q.status.value.replace("_", "-")
                status_class = f"badge-{status_val}"
                badge_html = f"<span class='{status_class}'>{q.status.value.upper()}</span>"
                dim_html = f"<span class='badge-dimension'>{q.dimension.upper()}</span>" if q.dimension else ""
                
                with st.container():
                    st.markdown(f"""
                    <div class='card-box'>
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
                            <div><strong>{q.question_id}</strong> &nbsp; {dim_html}</div>
                            <div>{badge_html}</div>
                        </div>
                        <div style='font-size: 1.05rem; font-weight: 500; color: #1e293b;'>{q.question_text}</div>
                        <div style='margin-top: 8px; font-size: 0.88rem; color: #475569;'>
                            <strong>Reason:</strong> {q.reason or 'Evaluate key inquiry criteria'}
                        </div>
                        <div style='margin-top: 4px; font-size: 0.85rem; color: #64748b;'>
                            <strong>Required Evidence:</strong> {q.required_evidence or 'Empirical data'} | <strong>Confidence:</strong> {int(q.confidence * 100)}%
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if q.unresolved_reason:
                        st.caption(f"⚠️ **Coverage Note:** {q.unresolved_reason}")

    # Tab 3: Verified Claims Inspector
    with tab_claims:
        st.subheader("Claim-to-Evidence Verification Inspector")
        st.markdown(
            "Every factual claim is audited against retrieved source excerpts and classified into "
            "`Supported`, `Partially Supported`, `Contradicted`, or `Unverified`."
        )

        claims = list(run.evidence_records.values())
        if not claims:
            st.info("No claims recorded yet.")
        else:
            filter_status = st.selectbox(
                "Filter by Verification Status",
                options=["All", "supported", "partially_supported", "contradicted", "unverified"],
                index=0
            )

            filtered_claims = [
                c for c in claims
                if filter_status == "All" or c.verification_status.value == filter_status
            ]

            for c in filtered_claims:
                status_class = f"badge-{c.verification_status.value.replace('_', '-')}"
                badge_html = f"<span class='{status_class}'>{c.verification_status.value.upper()}</span>"
                
                with st.expander(f"[{c.claim_id}] {c.claim_text[:80]}... — {c.verification_status.value.upper()}"):
                    st.markdown(f"**Claim ID:** `{c.claim_id}` | **Question:** `{c.question_id}` | **Status:** {badge_html} | **Type:** `{c.evidence_type}`", unsafe_allow_html=True)
                    st.markdown(f"**Factual Claim:**\n> {c.claim_text}")
                    
                    excerpt = c.supporting_excerpts[0] if c.supporting_excerpts else "No excerpt available."
                    st.markdown(f"**Retrieved Supporting Excerpt:**\n> *\"{excerpt}\"*")
                    st.markdown(f"**Verification Reason:** {c.verification_reason}")
                    
                    if c.source_ids:
                        st.markdown("**Cited Sources:**")
                        for sid in c.source_ids:
                            src = run.sources.get(sid)
                            if src:
                                st.markdown(f"- **[{src.source_id}]** [{src.title}]({src.url}) *(Publisher: {src.publisher})*")

    # Tab 4: Sources & Relevance Filter
    with tab_sources:
        col_s1, col_s2 = st.columns([1, 1])
        with col_s1:
            st.subheader(f"✅ Accepted Sources ({len(run.sources)})")
            st.caption("Passed strict relevance gating (Score ≥ 58/100, topic-aligned):")
            for s in run.sources.values():
                with st.expander(f"[{s.source_id}] {s.title[:55]}... ({int(s.relevance_score)}/100)"):
                    st.markdown(f"**URL:** [{s.url}]({s.url})")
                    st.markdown(f"**Publisher:** {s.publisher} | **Credibility:** `{s.credibility_assessment}`")
                    st.markdown(f"**Snippet:**\n> {s.snippet[:250]}...")

        with col_s2:
            st.subheader(f"⛔ Rejected Off-Topic Sources ({len(run.rejected_sources)})")
            st.caption("Pruned by negative domain filter or low relevance (preventing off-topic noise):")
            if not run.rejected_sources:
                st.info("No sources rejected in this run.")
            else:
                for s in run.rejected_sources.values():
                    with st.expander(f"[{s.source_id}] {s.title[:55]}... (Rel: {int(s.relevance_score)}/100)"):
                        st.error(f"**Rejection Reason:** {s.rejection_reason}")
                        st.markdown(f"**URL:** [{s.url}]({s.url})")
                        st.markdown(f"**Snippet:**\n> {s.snippet[:200]}...")

    # Tab 5: Research Audit & Quality Gate
    with tab_audit:
        st.subheader("Research Audit & Quality Gate Traceability")
        
        col_a1, col_a2 = st.columns([1, 1])
        with col_a1:
            if run.query_intent:
                st.markdown("### 🎯 Parsed Query Intent")
                st.markdown(f"- **Main Intent:** `{run.query_intent.main_intent}`")
                st.markdown(f"- **Domain:** `{run.query_intent.domain}`")
                st.markdown(f"- **Topic:** `{run.query_intent.topic}`")
                st.markdown(f"- **Primary Criteria:** `{', '.join(run.query_intent.primary_criteria)}`")
                if run.query_intent.explicit_constraints:
                    st.markdown(f"- **Explicit Constraints:** `{run.query_intent.explicit_constraints}`")
                if run.query_intent.excluded_topics:
                    st.markdown(f"- **Excluded Off-Topic:** `{', '.join(run.query_intent.excluded_topics)}`")

        with col_a2:
            if run.quality_gate_result:
                st.markdown("### 🛡️ Quality Gate Validation")
                qg = run.quality_gate_result
                status_pill = "🟢 PASSED" if qg.passed else "🔴 FAILED"
                st.markdown(f"**Status:** {status_pill} &nbsp; | &nbsp; **Score:** `{int(qg.score * 100)}%`")
                for check_name, passed in qg.checks.items():
                    icon = "✅" if passed else "❌"
                    st.markdown(f"- {icon} `{check_name}`")
                if qg.repairs_applied:
                    st.markdown("**Automated Repairs Applied:**")
                    for rep in qg.repairs_applied:
                        st.info(rep)

        st.markdown("---")
        st.download_button(
            label="💾 Download Complete Run JSON Audit",
            data=st.session_state.store.export_json(run.run_id),
            file_name=f"research_run_{run.run_id}.json",
            mime="application/json"
        )

        st.markdown("### Execution Event Stream")
        st.dataframe(
            run.execution_logs,
            column_config={
                "timestamp": "Time",
                "stage": "Stage",
                "message": "Event",
                "level": "Level"
            },
            use_container_width=True,
            hide_index=True
        )
