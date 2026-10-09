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
    page_title="ResearchPilot AI — Evidence-Driven AI Research Assistant",
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
    st.caption("Evidence-Driven Autonomous Research Agent")
    st.markdown("---")

    st.subheader("⚙️ Agent & LLM Settings")
    llm_provider = st.selectbox(
        "LLM Provider",
        options=["auto", "gemini", "openai", "heuristic"],
        index=0,
        help="Select the AI reasoning backend or 'auto' to auto-detect from keys."
    )

    api_key_input = st.text_input(
        "API Key (Optional)",
        type="password",
        value=os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or "",
        help="Google Gemini or OpenAI API Key. If empty, uses intelligent heuristic research reasoning."
    )

    custom_model = st.text_input(
        "Custom Model Name (Optional)",
        value="",
        placeholder="e.g. gemini-2.5-flash or gpt-4o-mini"
    )

    st.markdown("---")
    st.subheader("🎯 Research Budget Limits")
    max_rounds = st.slider("Max Research Rounds", min_value=1, max_value=3, value=2, help="Round 1 = Initial search. Round 2 = Adaptive gap resolution.")
    max_follow_ups = st.slider("Max Follow-Up Queries", min_value=1, max_value=6, value=4, help="Budget limit for targeted follow-up searches in Round 2.")
    timeout_sec = st.slider("Search/Extraction Timeout (s)", min_value=5, max_value=20, value=8)

    st.markdown("---")
    if st.button("🔄 Reset / Clear Session", use_container_width=True):
        st.session_state.store = ResearchStore()
        st.session_state.current_run_id = None
        st.session_state.run_in_progress = False
        st.rerun()


# Main View Header
st.markdown("<div class='main-header'>🔬 ResearchPilot AI</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-header'>"
    "Multi-step research assistant that plans inquiries, extracts and verifies factual claims against online sources, "
    "tracks question coverage, and executes adaptive follow-ups for unresolved gaps."
    "</div>",
    unsafe_allow_html=True
)

# Demo Query Presets
DEMO_PRESETS = [
    "What are the benefits, risks, and adoption challenges of generative AI in healthcare?",
    "Should small hospitals adopt generative AI?",
    "What is the commercial viability timeline and risk profile of post-quantum cryptography migration?",
    "What are the environmental impacts and efficiency tradeoffs of small modular nuclear reactors?"
]

col_input, col_preset = st.columns([3, 1.2])

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
    
    # Configure LLM Client
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

    # Progress UI Elements
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
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Subquestions", f"{stats.get('total_subquestions', 0)}")
    with m2:
        st.metric("Sources Retrieved", f"{stats.get('total_sources', 0)}")
    with m3:
        st.metric("Claims Audited", f"{stats.get('total_claims', 0)}")
    with m4:
        supported_claims = stats.get('claim_statuses', {}).get('supported', 0)
        st.metric("Supported Claims", f"{supported_claims}")
    with m5:
        rounds_count = stats.get('search_rounds_count', 0)
        st.metric("Search Rounds", f"{rounds_count}")

    # Tabs for observable workflow
    tab_report, tab_coverage, tab_claims, tab_sources, tab_adaptive, tab_audit = st.tabs([
        "📄 Final Report",
        "🎯 Research Coverage Tracker",
        "🔍 Claim-to-Evidence Inspector",
        "🌐 Sources Store",
        "🔁 Adaptive Loop Monitor",
        "📋 Audit Trail & JSON"
    ])

    # Tab 1: Final Report
    with tab_report:
        if run.final_report:
            st.subheader(run.final_report.title)
            
            # Export Options
            col_d1, col_d2 = st.columns([1, 4])
            with col_d1:
                st.download_button(
                    label="📥 Download Markdown",
                    data=run.final_report.markdown_content,
                    file_name=f"research_report_{run.run_id}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
            
            st.markdown(run.final_report.markdown_content)
        else:
            st.info("Report generation pending...")

    # Tab 2: Coverage Tracker (FR-04)
    with tab_coverage:
        st.subheader("Subquestion Coverage & Status")
        st.markdown(
            "ResearchPilot AI monitors evidence sufficiency per subquestion and decides "
            "whether questions are resolved or require follow-up searches."
        )

        if run.research_plan:
            for q in run.research_plan.subquestions:
                status_class = f"badge-{q.status.value.replace('_', '-')}"
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
                        <div style='margin-top: 10px; font-size: 0.85rem; color: #64748b;'>
                            <strong>Sources linked:</strong> {len(q.source_ids)} | <strong>Evidence claims:</strong> {len(q.evidence_ids)}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if q.unresolved_reason:
                        st.caption(f"⚠️ **Coverage Note / Limitation:** {q.unresolved_reason}")

    # Tab 3: Claim-to-Evidence Inspector (FR-03)
    with tab_claims:
        st.subheader("Claim-to-Evidence Verification Inspector")
        st.markdown(
            "Every major factual claim is mapped directly to source excerpts and classified into "
            "`Supported`, `Partially Supported`, `Contradicted`, or `Unverified`."
        )

        claims = list(run.evidence_records.values())
        if not claims:
            st.info("No claims recorded yet.")
        else:
            # Filter by status
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
                    st.markdown(f"**Claim ID:** `{c.claim_id}` | **Question:** `{c.question_id}` | **Status:** {badge_html}", unsafe_allow_html=True)
                    st.markdown(f"**Factual Claim:**\n> {c.claim_text}")
                    
                    excerpt = c.supporting_excerpts[0] if c.supporting_excerpts else "No excerpt available."
                    st.markdown(f"**Retrieved Supporting Excerpt:**\n> *\"{excerpt}\"*")
                    st.markdown(f"**Verification Audit Reason:** {c.verification_reason}")
                    
                    # Source Links
                    if c.source_ids:
                        st.markdown("**Cited Sources:**")
                        for sid in c.source_ids:
                            src = run.sources.get(sid)
                            if src:
                                st.markdown(f"- **[{src.source_id}]** [{src.title}]({src.url}) *(Publisher: {src.publisher})*")

    # Tab 4: Sources Store (FR-02)
    with tab_sources:
        st.subheader("Deduplicated Sources Store")
        st.markdown(
            "Sources collected from web retrieval, deduplicated by normalized URL with preserved stable source IDs."
        )

        sources = list(run.sources.values())
        if not sources:
            st.info("No sources stored yet.")
        else:
            for s in sources:
                with st.expander(f"[{s.source_id}] {s.title} ({s.publisher or 'Web'})"):
                    st.markdown(f"**URL:** [{s.url}]({s.url})")
                    st.markdown(f"**Retrieval Status:** `{s.retrieval_status}` | **Retrieved At:** `{s.retrieved_at}`")
                    if s.error_message:
                        st.warning(f"Retrieval Warning: {s.error_message}")
                    if s.snippet:
                        st.markdown(f"**Search Snippet:**\n> {s.snippet}")
                    if s.extracted_content:
                        with st.popover("View Extracted Page Content"):
                            st.text_area("Sanitized Body Text", s.extracted_content, height=250)

    # Tab 5: Adaptive Loop Monitor (FR-05)
    with tab_adaptive:
        st.subheader("Adaptive Research Loop & Round Monitor")
        st.markdown(
            "Inspect how the agent evaluated initial evidence, recognized missing coverage, and formulated targeted follow-up queries."
        )

        if not run.search_rounds:
            st.info("No search rounds recorded.")
        else:
            for rnd in run.search_rounds:
                st.markdown(f"### Round {rnd.round_number}: {rnd.round_type.upper().replace('_', ' ')}")
                st.markdown(f"- **Timestamp:** `{rnd.timestamp}`")
                st.markdown(f"- **Sources Discovered:** `{rnd.sources_found}`")
                if rnd.gaps_targeted:
                    st.markdown(f"- **Gaps Targeted:** `{', '.join(rnd.gaps_targeted)}`")
                
                st.markdown("**Executed Search Queries:**")
                for q in rnd.queries_executed:
                    st.code(q, language="text")
                st.markdown("---")

    # Tab 6: Audit Trail & JSON Export
    with tab_audit:
        st.subheader("Audit Trail & Traceability")
        st.download_button(
            label="💾 Download Complete Run JSON",
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
