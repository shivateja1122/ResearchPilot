# 🔬 ResearchPilot AI — Coordinated Multi-Agent Research System

ResearchPilot AI is a production-grade, multi-agent autonomous research assistant. It coordinates four specialized AI agents under a centralized supervisor orchestrator, shares authoritative state, gathers evidence from live web search and full-page scrapers, rigorously verifies factual claims and citations, detects contradictions and gaps, executes an adaptive recovery loop, and validates reports against an independent 12-point Quality Gate.

---

## 🌟 Multi-Agent Architecture Overview

ResearchPilot AI replaces monolithic workflows with a coordinated, modular multi-agent system:

```text
                                  User Query
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   ResearchOrchestrator    │
                        │   (Supervisor / Router)   │
                        └─────────────┬─────────────┘
                                      │
               ┌──────────────────────┼──────────────────────┐
               │                      │                      │
               ▼                      ▼                      ▼
    ┌──────────────────────┐┌──────────────────┐┌──────────────────────┐
    │ ResearchPlannerAgent ││ ResearcherAgent  ││ EvidenceAnalystAgent │
    │       (Agent 1)      ││    (Agent 2)     ││       (Agent 3)      │
    └──────────┬───────────┘└─────────┬────────┘└──────────┬───────────┘
               │                      │                    │
               │ (Plan & Criteria)    │ (Sources & Evidence│ (Claims, Gaps,
               │                      │  Extraction)       │  Contradictions)
               └──────────────────────┼────────────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │  Shared Authoritative     │
                        │  ResearchState (state.py) │
                        └─────────────┬─────────────┘
                                      │
                       [Coverage Gaps Detected?]
                        ├── YES (Round < Max) ──► Adaptive Round 2 Targeted Search
                        │
                        └── NO (Or Budget Reached)
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   ReportWriterAgent       │
                        │       (Agent 4)           │
                        └─────────────┬─────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │ Independent QualityGate   │
                        │ (12-Point Audit & Repair) │
                        └─────────────┬─────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │ Verified Markdown Report  │
                        │ + Research Audit JSON     │
                        └───────────────────────────┘
```

---

## 🤖 The 4 Specialized AI Agents

### Agent 1: ResearchPlannerAgent (`agents/research_planner.py`)
- **Role**: Query interpretation, scope definition, and criteria-driven research decomposition.
- **Responsibilities**:
  - Analyzes intent, explicit criteria, constraints (price, category, region), and excluded topics.
  - Produces structured research plans (`plan_id`, `intent`, `constraints`, `primary_criteria`, `excluded_topics`).
  - Formulates 3–7 criteria-driven questions with dimension tags and measurable completion criteria.
  - Generates initial targeted search queries.

### Agent 2: ResearcherAgent (`agents/researcher.py`)
- **Role**: Retrieval, content extraction, and initial candidate evidence harvesting.
- **Responsibilities**:
  - Synthesizes targeted queries for each subquestion.
  - Executes live web searches via **Tavily Search API** with automatic fallback to **DuckDuckGo**.
  - Applies dual-stage relevance gating (`SourceFilter`) checking domain reputation and topic relevance.
  - Extracts full page text using **Jina Reader API** with resilient local BeautifulSoup parsing.
  - Distills atomic evidence items (`claim`, `quote`, `source_url`, `relevance_score`, `question_id`).

### Agent 3: EvidenceAnalystAgent (`agents/evidence_analyst.py`)
- **Role**: Cross-source synthesis, claim verification, citation validation, and gap detection.
- **Responsibilities**:
  - Validates factual claims against retrieved excerpts (`SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`).
  - Audits citations (`CitationValidator`) confirming quote overlap, context relevance, and URI integrity.
  - Detects contradictions (`ContradictionDetector`) between competing sources and marks them `UNRESOLVED_DISCLOSED`.
  - Audits dimension coverage (`GapRecoveryEngine`) and generates focused Round 2 recovery tasks.

### Agent 4: ReportWriterAgent (`agents/report_writer.py`)
- **Role**: Final report drafting, comparative matrix synthesis, and citation formatting.
- **Responsibilities**:
  - Synthesizes direct executive answers directly resolving the user's primary criteria.
  - Generates comparative analysis matrices with quantitative specs and pros/cons.
  - Embeds verified inline citations formatted as `[Publisher](url)`.
  - Discloses unresolved questions, contradictions, and empirical research limitations.

---

## 🏛️ Central Orchestrator (`orchestrator.py`)

The supervisor orchestrator manages workflow execution, state persistence, and error handling:
1. `plan_research(query)`: Invokes Agent 1 to decompose the query.
2. `execute_research(tasks)`: Dispatches Agent 2 for parallel or sequential web queries.
3. `analyze_evidence(plan, sources, evidence)`: Dispatches Agent 3 to verify claims and assess coverage.
4. `recover_research_gaps(plan, coverage, rounds)`: Conditionally triggers targeted Round 2 queries.
5. `generate_report(state, plan, analysis)`: Invokes Agent 4 to draft the report.
6. `validate_final_report(run)`: Enforces the independent 12-point Quality Gate.

---

## 📊 Authoritative Shared State (`state.py`)

All agents communicate through a typed, centralized `ResearchState`:
- **State Schema**:
  - `run_id`, `query`, `created_at`, `status`
  - `plan`: Structured plan with constraints and subquestions.
  - `sources`: Normalized list of accepted sources with metadata.
  - `rejected_sources`: Deduplicated rejected sources with audit rejection reasons.
  - `evidence`: Atomic extracted evidence records with verbatim quotes.
  - `claims`: Verified claims with supporting citation IDs.
  - `contradictions`: Recorded conflicts between sources.
  - `audit_events`: Chronological event trail tracking agent actions.
  - `errors`: Upstream search and scraping error log.
- **Methods**: `add_source()`, `reject_source()`, `add_evidence_item()`, `record_audit_event()`, `record_error()`, and `to_research_run()` bridge for backward compatibility.

---

## 🛡️ Independent 12-Point Quality Gate

Before any report is finalized, the Quality Gate validates:
1. **Direct Answer Coverage**: Primary query directly answered.
2. **Criteria Fulfillment**: Target constraints (e.g., budget, features) met.
3. **No Unverified Citations**: Every cited claim backed by verified evidence.
4. **URL Integrity**: Every citation references an accepted source.
5. **No Hallucinated URLs**: No invented links or empty references.
6. **Contradiction Disclosure**: Detected conflicting facts disclosed.
7. **Coverage Threshold**: At least 70% of subquestions answered.
8. **Excerpt Grounding**: Verbatim quotes present in evidence store.
9. **Comparative Depth**: Side-by-side matrices included for comparison queries.
10. **Limitations Section**: Uncertainty, exclusions, and gaps explicitly disclosed.
11. **Traceable Audit Log**: Audit trail recorded for all stages.
12. **Budget Compliance**: Execution kept within query and round limits.

---

## 🚀 Quickstart Guide

### 1. Installation

Ensure Python 3.10+ is installed:

```bash
git clone https://github.com/your-username/ResearchPilot.git
cd ResearchPilot
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy `.env.example` to `.env` and configure your API keys:

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
READER_API_KEY=your_jina_reader_key_here
```

> **Note:** ResearchPilot AI operates smoothly with heuristics and live DuckDuckGo scraping even if API keys are not provided.

### 3. Run Automated Tests

Run the full pytest suite (36 tests across all 4 suites):

```bash
python -m pytest -v
```

To run only the multi-agent test suite:

```bash
python -m pytest tests/test_multi_agent.py -v
```

### 4. Run the Streamlit UI

```bash
streamlit run app.py
```

The web dashboard displays live agent cards for the Planner, Researcher, Analyst, Writer, and Quality Gate.

---

## 🧪 Automated Test Suite (36 Tests)

| Test File | Test Count | Scope |
| :--- | :---: | :--- |
| `tests/test_multi_agent.py` | 10 | 4-agent delegation, schemas, recovery loops, Quality Gate |
| `tests/test_master_prompt_v2.py` | 10 | Anti-hallucination, strict source gating, citation validation |
| `tests/test_master_prompt.py` | 7 | Relevance scoring, intent alignment, audit generation |
| `tests/test_workflow.py` | 9 | End-to-end integration, coverage tracking, export features |

---

## 📈 Benchmark Results

Tested on the benchmark query:
> *"Suggest me a good camera mobile under INR 30,000 in India."*

- **Report Output**: `camera_report_output.md`
- **Audit Output**: `camera_audit_output.json`
- **Accepted Sources**: 7 authoritative review sites (91mobiles, Smartprix, Cashify, MySmartPrice, etc.)
- **Rejected Sources**: 4 irrelevant/out-of-budget pages
- **Quality Gate Score**: **92.0%** (Passed with 7 auto-repairs applied)
- **Hallucinated Citations**: 0
