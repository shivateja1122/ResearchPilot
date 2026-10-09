# 🔬 ResearchPilot AI — Evidence-Driven AI Research Assistant

ResearchPilot AI is a multi-step autonomous AI research assistant that plans research inquiries, gathers information from credible online sources, audits and verifies factual claims against retrieved passages, tracks coverage status at the subquestion level, and executes an adaptive research loop to resolve identified gaps.

Built for the 20-hour hackathon MVP based on the Product Requirements Document (PRD v1.0).

---

## 🌟 Core Differentiators (PRD P0 Requirements)

1. **Claim-to-Evidence Verification (FR-03)**:
   - Connects factual claims to retrieved source excerpts.
   - Classifies verification status into: `Supported`, `Partially Supported`, `Contradicted`, and `Unverified`.
   - Never fabricates citations; all sources resolve to actual retrieved web records.
   - Flags citation mismatches and conflicting evidence.

2. **Research Coverage Tracker (FR-04)**:
   - Tracks research progress per subquestion: `Not Started` ➔ `Researching` ➔ `Partial` ➔ `Supported` / `Unresolved`.
   - Evaluates coverage based on evidence quality, direct excerpt support, and dimension breadth—not merely source counts.

3. **Adaptive Research Loop (FR-05)**:
   - Evaluates evidence coverage after Round 1.
   - Automatically detects subquestions with incomplete evidence.
   - Formulates targeted follow-up queries and executes Round 2 web research.
   - Enforces strict search budget controls (max rounds, max follow-ups, timeouts).

4. **Structured 9-Section Verifiable Report (FR-06)**:
   - Executive Summary
   - Scope & Methodology (with subquestion coverage audit)
   - Key Findings (with embedded claim IDs)
   - Evidence & Citations (audited claims table with excerpts)
   - Comparison & Conflicting Evidence
   - Recommendations
   - Limitations & Unresolved Questions (explicit gap disclosure)
   - Research Audit & Budget Summary
   - References (traceable source metadata and links)

---

## 🏗️ Architecture

```text
User Query
    │
    ▼
Research Planner (4–6 dimension-tagged subquestions)
    │
    ▼
Research Orchestrator
    ├── Web Search Tool (DuckDuckGo live retrieval / search APIs)
    │       │
    │       ▼
    │   Page Extractor (Resilient BeautifulSoup HTML parsing)
    │       │
    │       ▼
    │   Source Store (Normalized URL deduplication & stable IDs)
    │
    ▼
Evidence Extraction & Verification (Claim-to-excerpt auditing)
    │
    ▼
Research Coverage Tracker (Supported / Partial / Unresolved)
    │
    ▼
Adaptive Research Decision
    ├── Gaps Found ──► Targeted Follow-up Search (Round 2)
    │                        │
    │                        ▼
    │                   Update Evidence & Coverage
    │
    └── Adequate or Budget Exhausted
                             │
                             ▼
                      Report Generator
                             │
                             ▼
                  9-Section Evidence-Backed Report
```

---

## 🚀 Quickstart Guide

### 1. Installation

Ensure Python 3.10+ is installed:

```bash
git clone https://github.com/your-username/ResearchPilot.git
cd ResearchPilot
pip install -r requirements.txt
```

### 2. Environment Configuration (Optional)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

To use Google Gemini:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

To use OpenAI or compatible endpoints:
```env
OPENAI_API_KEY=your_openai_api_key_here
```

> **Note:** ResearchPilot AI operates smoothly even without external API keys thanks to built-in heuristic reasoning and live DuckDuckGo web scraping!

### 3. Run Automated Tests

Run the full pytest suite verifying FR-01 through FR-06 and test scenarios A through E:

```bash
python -m pytest -v
```

### 4. Launch the Streamlit Web Application

```bash
streamlit run app.py
```

The application will be accessible at `http://localhost:8501`.

---

## 🎯 3-Minute Hackathon Demo Script

Follow this sequence for the 3-minute hackathon presentation (PRD Section 13):

1. **0:00 - 0:30 (Planning):**
   - Select the preset: *"What are the benefits, risks, and adoption challenges of generative AI in healthcare?"*
   - Click **Start Evidence-Driven Research**.
   - Show the automatically generated research plan featuring 5 subquestions tagged by dimension (`benefits`, `risks`, `costs`, `regulations`, `alternatives`).

2. **0:30 - 1:15 (Live Search & Source Collection):**
   - Observe live DuckDuckGo web searches retrieving real sources (McKinsey, NCBI, NEJM, etc.).
   - Switch to the **Sources Store** tab to show normalized URL deduplication and clean page extraction.

3. **1:15 - 2:00 (Adaptive Loop & Coverage Tracker):**
   - Switch to the **Research Coverage Tracker** tab to view status progression.
   - Point out how the **Adaptive Loop** identified gaps in implementation costs or regulatory guidance and triggered targeted Round 2 follow-up queries.

4. **2:00 - 2:30 (Claim Verification Inspector):**
   - Switch to the **Claim-to-Evidence Inspector** tab.
   - Filter claims by status (`supported`, `partially_supported`, `contradicted`, `unverified`).
   - Open a claim to reveal the supporting excerpt quote, verification reason, and clickable source reference.

5. **2:30 - 3:00 (Final Report & Export):**
   - Switch to the **Final Report** tab.
   - Highlight the 9 structured sections, including the **Limitations and Unresolved Questions** callout.
   - Demonstrate the one-click **Download Markdown** export.

---

## 🧪 Verified Test Scenarios (PRD Section 11)

- **Test A (Sufficient Evidence):** Clear queries produce grounded reports without exceeding configured budgets.
- **Test B (Missing Evidence & Adaptive Loop):** Incomplete subquestions trigger targeted follow-up searches in Round 2.
- **Test C (Conflicting Evidence):** Divergent sources are classified and represented fairly.
- **Test D (Citation Mismatch):** Claims paired with irrelevant passages are flagged as `Unverified` rather than accepted.
- **Test E (Search Failure Resilience):** Inaccessible or invalid URLs record failures gracefully without crashing.
