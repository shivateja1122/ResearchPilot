"""
Generate a professional, publication-quality PDF for the ResearchPilot AI Architecture Deep Dive.
Uses ReportLab Platypus with NumberedCanvas, custom styling, tables, code blocks, and callouts.
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

# Define Palette
C_PRIMARY = colors.HexColor("#0F172A")       # Dark Slate / Navy
C_PRIMARY_LIGHT = colors.HexColor("#1E293B") # Secondary Slate
C_ACCENT = colors.HexColor("#1D4ED8")        # Royal Blue
C_ACCENT_BG = colors.HexColor("#EFF6FF")     # Soft Blue Light
C_CARD_BG = colors.HexColor("#F8FAFC")       # Off-white / light slate
C_BORDER = colors.HexColor("#CBD5E1")        # Slate border
C_TEXT = colors.HexColor("#1E293B")          # Charcoal text
C_TEXT_MUTED = colors.HexColor("#64748B")    # Slate Muted
C_SUCCESS = colors.HexColor("#16A34A")       # Emerald green
C_WARNING = colors.HexColor("#D97706")       # Amber
C_DANGER = colors.HexColor("#DC2626")        # Crimson red
C_CODE_BG = colors.HexColor("#0F172A")       # Dark background for code
C_CODE_TEXT = colors.HexColor("#38BDF8")     # Light cyan for code

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and draw total page count and header/footer rules."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        # Top Header (omitted on cover/first page)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(C_TEXT_MUTED)
            self.drawString(40, 755, "RESEARCHPILOT AI")
            self.setFont("Helvetica", 8)
            self.drawRightString(572, 755, "End-to-End Architectural Deep Dive — System Reference")
            self.setStrokeColor(C_BORDER)
            self.setLineWidth(0.6)
            self.line(40, 747, 572, 747)

        # Bottom Footer (on all pages)
        self.setStrokeColor(C_BORDER)
        self.setLineWidth(0.6)
        self.line(40, 42, 572, 42)
        
        self.setFont("Helvetica", 7.5)
        self.setFillColor(C_TEXT_MUTED)
        self.drawString(40, 30, "CONFIDENTIAL & PROPRIETARY — SYSTEM ARCHITECTURE & VERIFICATION MANUAL")
        
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(572, 30, page_str)
        self.restoreState()


def build_pdf(filename="ResearchPilot_Architecture_Deep_Dive.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=50,
        bottomMargin=50
    )

    printable_w = 532  # 612 - 80

    styles = getSampleStyleSheet()

    # Custom Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=C_PRIMARY,
        alignment=TA_LEFT,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=14,
        textColor=C_ACCENT,
        alignment=TA_LEFT,
        spaceAfter=10
    )

    meta_style = ParagraphStyle(
        'MetaText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=C_TEXT_MUTED
    )

    h1_style = ParagraphStyle(
        'SecH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=C_PRIMARY,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'SecH2',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=13.5,
        textColor=C_ACCENT,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    h3_style = ParagraphStyle(
        'SecH3',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=C_PRIMARY_LIGHT,
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=C_TEXT,
        alignment=TA_JUSTIFY,
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=C_TEXT,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3
    )

    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.2,
        leading=9.2,
        textColor=C_CODE_TEXT
    )

    th_style = ParagraphStyle(
        'TH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=TA_LEFT
    )

    td_style = ParagraphStyle(
        'TD',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=C_TEXT,
        alignment=TA_LEFT
    )

    td_bold_style = ParagraphStyle(
        'TDBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=C_PRIMARY,
        alignment=TA_LEFT
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11,
        textColor=C_PRIMARY_LIGHT
    )

    story = []

    # -------------------------------------------------------------
    # HERO HEADER / COVER BLOCK
    # -------------------------------------------------------------
    story.append(Paragraph("ResearchPilot AI — Architecture Deep Dive", title_style))
    story.append(Paragraph("Technical Specification, Multi-Agent Orchestration, Evidence Verification, and Quality Controls", subtitle_style))
    
    meta_html = (
        "<b>Architecture Paradigm:</b> Hierarchical Supervisor Pattern (Not AI Swarm) &nbsp;|&nbsp; "
        "<b>Language:</b> Python 3.11+ &nbsp;|&nbsp; <b>Framework:</b> Modular Agentic Toolchain<br/>"
        "<b>Model Backend:</b> Multi-Tier Gemini 2.5 Flash / Pro &nbsp;|&nbsp; "
        "<b>Gatekeeper:</b> 9-Point Verification & 12-Check Quality Gate &nbsp;|&nbsp; "
        "<b>Document Version:</b> 1.0 (Production Blueprint)"
    )
    meta_table = Table([[Paragraph(meta_html, meta_style)]], colWidths=[printable_w])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CARD_BG),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Executive Overview
    story.append(Paragraph("Executive Summary & Core Paradigm", h1_style))
    story.append(Paragraph(
        "ResearchPilot AI is an evidence-grounded research automation architecture designed to produce factual, verifiable, "
        "and reproducible research reports from complex inquiries. Unlike conventional generative chatbots that rely on internal parametric memory, "
        "ResearchPilot AI decouples statement formulation from factual truth by enforcing a strict <b>Evidence Ledger</b>, multi-tier web extraction, "
        "adversarial source filtering, claim-level passage verification, and an autonomous adaptive feedback loop.",
        body_style
    ))
    
    # Hierarchical Supervisor vs AI Swarm
    story.append(Paragraph("Why Hierarchical Supervisor Instead of an AI Swarm?", h2_style))
    story.append(Paragraph(
        "The system intentionally avoids unconstrained peer-to-peer <i>AI Swarms</i>. In an AI swarm, independent agents negotiate arbitrarily without "
        "deterministic bounds, frequently introducing latency, runaway token expenditure, circular reasoning, and uninspected error propagation. "
        "ResearchPilot AI utilizes a <b>Hierarchical Multi-Stage Orchestrated Workflow (Supervisor Pattern)</b> governed by the central "
        "<code>ResearchOrchestrator</code>. The supervisor maintains state via a thread-safe <code>ResearchStore</code>, executing deterministic "
        "validation gates before advancing through pipeline phases.",
        body_style
    ))

    # Core Principles Table
    principles_data = [
        [Paragraph("Core Principle", th_style), Paragraph("Architectural Rationale & Enforcement", th_style)],
        [
            Paragraph("<b>1. Evidence Grounding Over Memory</b>", td_bold_style),
            Paragraph("A statement is treated as factual only if substantiated by an audited excerpt in the Evidence Ledger. Parametric memory is restricted to syntactic structuring.", td_style)
        ],
        [
            Paragraph("<b>2. URL Non-Equivalence to Truth</b>", td_bold_style),
            Paragraph("The presence of a source URL does not validate a claim. The exact text must be retrieved, sanitized, and proven to substantiate the adjacent statement.", td_style)
        ],
        [
            Paragraph("<b>3. Negative Boundary Enforcement</b>", td_bold_style),
            Paragraph("Off-topic domains (e.g. EV batteries during a smartphone search) are filtered deterministically at search formulation, source scoring, extraction, and quality gate stages.", td_style)
        ],
        [
            Paragraph("<b>4. Rejection of Unsubstantiated Superlatives</b>", td_bold_style),
            Paragraph("Technical specifications ('features 50 MP sensor') cannot prove comparative superiority ('best camera phone'). Superlatives require comparative test evidence.", td_style)
        ],
        [
            Paragraph("<b>5. Aspect & Freshness Separation</b>", td_bold_style),
            Paragraph("Daylight photography results cannot substantiate low-light claims. Stale pricing from outdated articles cannot substantiate current market availability.", td_style)
        ],
        [
            Paragraph("<b>6. Separation of Concerns</b>", td_bold_style),
            Paragraph("Final user reports provide direct answers with clean links; raw execution logs and rejection reasons are kept isolated in a separate machine-readable Research Audit.", td_style)
        ]
    ]
    p_table = Table(principles_data, colWidths=[150, 382])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_CARD_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(p_table)
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------
    # END-TO-END PIPELINE PHASES
    # -------------------------------------------------------------
    story.append(Paragraph("End-to-End Pipeline Phases", h1_style))
    pipeline_data = [
        [Paragraph("Phase", th_style), Paragraph("Component", th_style), Paragraph("Input & Action", th_style), Paragraph("Output & Storage", th_style)],
        [
            Paragraph("<b>Phase 1: Ingestion & Planning</b>", td_bold_style),
            Paragraph("<code>QueryAnalyzer</code><br/><code>ResearchPlanner</code>", td_style),
            Paragraph("Raw user query string. Extracts intent, constraints, primary criteria, and generates 3–6 research subquestions.", td_style),
            Paragraph("<code>QueryIntent</code> & <code>ResearchPlan</code> stored in <code>ResearchStore</code>", td_style)
        ],
        [
            Paragraph("<b>Phase 2: Retrieval & Filtering</b>", td_bold_style),
            Paragraph("<code>WebSearchTool</code><br/><code>SourceFilter</code><br/><code>PageExtractor</code>", td_style),
            Paragraph("Targeted keyword queries sent to Tavily/DDG. Dual-stage filter applies negative patterns and 0–100 credibility scoring (cut-off: 58). Jina Reader extracts clean Markdown.", td_style),
            Paragraph("Accepted sources registered; rejected sources logged in audit with exact score.", td_style)
        ],
        [
            Paragraph("<b>Phase 3: Extraction & Verification</b>", td_bold_style),
            Paragraph("<code>ResearchAnalyst</code><br/><code>ClaimVerifier</code><br/><code>GapRecoveryEngine</code>", td_style),
            Paragraph("Scans text, extracts atomic claims + verbatim excerpts. Executes 9-point verification check. Audits question completion criteria.", td_style),
            Paragraph("<code>Evidence</code> ledger items with statuses: <code>SUPPORTED</code>, <code>CONTRADICTED</code>, etc.", td_style)
        ],
        [
            Paragraph("<b>Phase 4: Adaptive Recovery</b>", td_bold_style),
            Paragraph("<code>ResearchOrchestrator</code> Feedback Loop", td_style),
            Paragraph("Detects unresolved subquestions. Formulates Round 2 keyword queries with missing criteria and queries web dynamically.", td_style),
            Paragraph("New evidence ledgered; coverage updated to <code>ANSWERED</code>.", td_style)
        ],
        [
            Paragraph("<b>Phase 5: Integrity & Quality Gate</b>", td_bold_style),
            Paragraph("<code>CitationValidator</code><br/><code>ContradictionDetector</code><br/><code>QualityGate</code>", td_style),
            Paragraph("Validates citation passage and quote fidelity. Analyzes conflicting reviews. 12-point Quality Gate applies bounded auto-repairs.", td_style),
            Paragraph("<code>CitationValidation</code>, <code>ContradictionRecord</code>, <code>QualityGateResult</code>", td_style)
        ],
        [
            Paragraph("<b>Phase 6: Synthesis & Presentation</b>", td_bold_style),
            Paragraph("<code>ReportGenerator</code><br/>Streamlit UI (<code>app.py</code>)", td_style),
            Paragraph("Synthesizes direct-answer executive report with comparative table and verified citations. Builds separate JSON audit.", td_style),
            Paragraph("Rendered in UI; exported to Markdown and Audit JSON files.", td_style)
        ]
    ]
    pipe_table = Table(pipeline_data, colWidths=[90, 105, 185, 152])
    pipe_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_CARD_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(pipe_table)
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------
    # DETAILED STEP-BY-STEP BREAKDOWN
    # -------------------------------------------------------------
    story.append(Paragraph("Detailed Step-by-Step Architecture", h1_style))

    # Step 1
    story.append(Paragraph("Step 1: Ingestion & Query Analysis (QueryAnalyzer)", h2_style))
    story.append(Paragraph(
        "<b>Source:</b> <code>agent/query_analyzer.py</code> &nbsp;|&nbsp; <b>Output:</b> <code>QueryIntent</code><br/>"
        "The query analyzer deconstructs the raw user query into structured semantic components. It avoids generic query expansion "
        "and identifies hard boundaries to protect subsequent search stages from semantic drift.",
        body_style
    ))
    story.append(Paragraph(
        "• <b>Semantic Parsing:</b> Emits <code>main_intent</code> (e.g. <code>product_recommendation</code>), <code>domain</code> (e.g. <code>smartphones</code>), "
        "<code>explicit_constraints</code> (e.g. <code>max_budget: 30000, currency: INR, geo: India</code>).<br/>"
        "• <b>Criteria Isolation:</b> Distinguishes <code>primary_criteria</code> ('camera quality, low-light, OIS') from <code>secondary_criteria</code> ('battery, display'). Non-requested dimensions (e.g. gaming refresh rate) are explicitly deprioritized.<br/>"
        "• <b>Negative Boundary Extraction:</b> Generates <code>excluded_topics</code>. For smartphone queries, adds regex terms like <code>['electric vehicles', 'ev battery', 'charging stations', 'commercial fleet']</code> to reject false keyword matches.<br/>"
        "• <b>Deterministic Heuristic Fallback:</b> In case of LLM rate limits (HTTP 429), regular expressions extract currency symbols (Rs, $, INR), numeric ceilings, and geographic tokens.",
        bullet_style
    ))
    story.append(Spacer(1, 6))

    # Step 2
    story.append(Paragraph("Step 2: Dynamic Criteria-Driven Research Planning (ResearchPlanner)", h2_style))
    story.append(Paragraph(
        "<b>Source:</b> <code>agent/planner.py</code> &nbsp;|&nbsp; <b>Output:</b> <code>ResearchPlan</code> & <code>List[ResearchQuestion]</code><br/>"
        "Transforms the <code>QueryIntent</code> into 3 to 6 targeted, criteria-driven subquestions. Rather than broad explorations, "
        "every question defines a concrete dimension, justification, required evidence, and completion criteria.",
        body_style
    ))
    q_schema_text = (
        "<b>Subquestion Schema:</b> <code>question_id</code> (Q1, Q2...) &nbsp;|&nbsp; "
        "<code>dimension</code> ('sensor_ois', 'low_light_benchmarks', 'market_pricing')<br/>"
        "<code>reason:</code> Why this question must be resolved to answer the user's inquiry.<br/>"
        "<code>required_evidence:</code> The specific technical facts or metrics required.<br/>"
        "<code>completion_criteria:</code> Objective criteria to mark the question resolved (e.g. 'At least 2 verified devices with validated sensor and OIS details')."
    )
    q_box = Table([[Paragraph(q_schema_text, td_style)]], colWidths=[printable_w])
    q_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CARD_BG),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(q_box)
    story.append(Spacer(1, 6))

    # Step 3
    story.append(Paragraph("Step 3: Targeted Search Formulation & Retrieval (WebSearchTool)", h2_style))
    story.append(Paragraph(
        "<b>Source:</b> <code>tools/web_search.py</code> & <code>agent/orchestrator.py</code><br/>"
        "Formulates focused search queries rather than conversational phrases:<br/>"
        "<b>Search Query Construction:</b> <code>[Topic] + [Constraint] + [Geographic Scope] + [Subquestion Keywords]</code><br/>"
        "Conversational tokens ('what', 'which', 'compare', 'options') are stripped, and query strings are capped at 100 characters. "
        "Supports a 3-tier retrieval hierarchy: <b>Tier 1 (Tavily AI Search API)</b> for high-signal technical retrieval, "
        "<b>Tier 2 (DuckDuckGo Live Search)</b> for rate-limit failover, and <b>Tier 3 (Offline Mock Fallback)</b> for deterministic test suites. "
        "All retrieved URLs are normalized by stripping tracking parameters (<code>utm_source</code>, <code>ref</code>, <code>fbclid</code>).",
        body_style
    ))
    story.append(Spacer(1, 6))

    # Step 4
    story.append(Paragraph("Step 4: Dual-Stage Strict Source Relevance Filtering (SourceFilter)", h2_style))
    story.append(Paragraph(
        "<b>Source:</b> <code>tools/source_filter.py</code> &nbsp;|&nbsp; <b>Threshold:</b> <code>SCORE >= 58.0 / 100</code><br/>"
        "Prevents SEO spam, irrelevant domains, and low-credibility aggregators from polluting the evidence pool via a dual-stage gatekeeper:",
        body_style
    ))
    filter_data = [
        [Paragraph("Filtering Stage", th_style), Paragraph("Evaluation Mechanism", th_style), Paragraph("Outcome & Scoring Impact", th_style)],
        [
            Paragraph("<b>Stage 1: Negative Filter</b>", td_bold_style),
            Paragraph("Evaluates title, URL, and snippet against domain negative patterns (e.g. EV battery regex) and user-excluded topics.", td_style),
            Paragraph("Immediate rejection. Score capped at 15.0/100. Logged in audit as 'Off-topic negative filter match'.", td_style)
        ],
        [
            Paragraph("<b>Stage 2: Authority Score</b>", td_bold_style),
            Paragraph("Domain credibility evaluation (0–40 pts). .gov/.edu = 40; known tech reviewers (gsmarena, 91mobiles) = 36; social media = 8.", td_style),
            Paragraph("Prevents user-generated unverified social claims from dominating technical research.", td_style)
        ],
        [
            Paragraph("<b>Stage 2: Topical Overlap</b>", td_bold_style),
            Paragraph("Calculates proportional overlap with core topic words (0–35 pts) plus primary criteria bonus (+5) and geographic match (+5).", td_style),
            Paragraph("Ensures retrieved page directly addresses user constraints.", td_style)
        ],
        [
            Paragraph("<b>Stage 2: Subquestion Fit</b>", td_bold_style),
            Paragraph("Measures specific keyword alignment with the active research subquestion dimension (0–20 pts).", td_style),
            Paragraph("High relevance sources (score &gt;= 58.0) pass to PageExtractor; lower scores logged in audit with exact point tally.", td_style)
        ]
    ]
    f_table = Table(filter_data, colWidths=[110, 222, 200])
    f_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_CARD_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(f_table)
    story.append(Spacer(1, 6))

    # Step 5
    story.append(Paragraph("Step 5: Web Content Extraction & Noise Scrubbing (PageExtractor)", h2_style))
    story.append(Paragraph(
        "<b>Source:</b> <code>tools/page_extractor.py</code><br/>"
        "• <b>Jina Reader Primary:</b> Routes URLs through <code>https://r.jina.ai/&lt;url&gt;</code> with Bearer authentication. Cloud headless rendering bypasses client-side JavaScript, ads, and popups.<br/>"
        "• <b>BeautifulSoup4 Fallback:</b> Direct HTTP GET requests with custom browser headers parse semantic HTML (<code>&lt;article&gt;, &lt;main&gt;</code>) while stripping scripts, styles, navs, and footers.<br/>"
        "• <b>Error & Captcha Rejection:</b> Evaluates content against regex patterns for <i>403 Forbidden, Cloudflare captcha, Access Denied</i>. Fails fast rather than extracting captcha error text as evidence.<br/>"
        "• <b>Noise Sanitization Engine:</b> Strips Jina metadata headers, cookie banners, navigation breadcrumbs, and transforms complex markdown tables into concise key-value spec strings.",
        bullet_style
    ))
    story.append(Spacer(1, 6))

    # Step 6
    story.append(Paragraph("Step 6: Atomic Claim Extraction & Evidence Ledgering (ResearchAnalyst)", h2_style))
    story.append(Paragraph(
        "<b>Source:</b> <code>agent/analyst.py</code> & <code>storage/research_store.py</code><br/>"
        "Extracts discrete factual assertions and pairs them with exact supporting quotes into the thread-safe <b>Evidence Ledger</b>:<br/>"
        "• <code>claim_text</code>: Concise factual assertion (&lt;= 250 characters) directly addressing the subquestion.<br/>"
        "• <code>supporting_excerpt</code>: Verbatim sentence from source page (&lt;= 200 characters) containing the exact factual substantiation.<br/>"
        "• <code>evidence_type</code>: Explicitly labeled as <code>direct</code> (measured spec/test) or <code>inference</code> (reasoned deduction).<br/>"
        "• <b>Deduplication:</b> Normalizes text strings across multiple sources to avoid redundant claims and registers each under a unique ID (<code>EVD_001</code>).",
        bullet_style
    ))
    story.append(Spacer(1, 6))

    # Step 7
    story.append(Paragraph("Step 7: Rigorous 9-Point Claim-Level Verification (ClaimVerifier)", h2_style))
    story.append(Paragraph(
        "<b>Source:</b> <code>agent/claim_verifier.py</code><br/>"
        "Every claim in the Evidence Ledger must undergo 9 adversarial verification checks before it can be cited in recommendations:",
        body_style
    ))
    v9_data = [
        [Paragraph("Verification Check", th_style), Paragraph("Evaluation Objective", th_style), Paragraph("Enforcement Rule & Failure State", th_style)],
        [
            Paragraph("<b>1. Exact Passage Support</b>", td_bold_style),
            Paragraph("Does the excerpt substantiate the claim?", td_style),
            Paragraph("Semantic alignment + keyword overlap &gt;= 60%. Failure -&gt; UNVERIFIED.", td_style)
        ],
        [
            Paragraph("<b>2. Entity & Variant Match</b>", td_bold_style),
            Paragraph("Does excerpt discuss the exact model/subject?", td_style),
            Paragraph("Named entity match (e.g. Motorola Edge 50 Pro). Failure -&gt; UNVERIFIED.", td_style)
        ],
        [
            Paragraph("<b>3. Scope Completeness</b>", td_bold_style),
            Paragraph("Does excerpt substantiate all parts of the claim?", td_style),
            Paragraph("Missing sub-metrics result in PARTIALLY_SUPPORTED.", td_style)
        ],
        [
            Paragraph("<b>4. Unmentioned Details</b>", td_bold_style),
            Paragraph("Does claim introduce unmentioned details?", td_style),
            Paragraph("External details absent from excerpt -&gt; flagged UNVERIFIED.", td_style)
        ],
        [
            Paragraph("<b>5. Superlatives Check</b>", td_bold_style),
            Paragraph("Does comparative claim have comparative proof?", td_style),
            Paragraph("'Best camera' backed only by spec sheets -&gt; UNVERIFIED.", td_style)
        ],
        [
            Paragraph("<b>6. Aspect Alignment</b>", td_bold_style),
            Paragraph("Does excerpt cover the specific aspect claimed?", td_style),
            Paragraph("Low-light claim backed only by daylight review -&gt; UNVERIFIED.", td_style)
        ],
        [
            Paragraph("<b>7. Price Freshness</b>", td_bold_style),
            Paragraph("Is current price backed by fresh data?", td_style),
            Paragraph("Stale prices from articles &gt; 1 yr old -&gt; UNVERIFIED.", td_style)
        ],
        [
            Paragraph("<b>8. Contradiction Check</b>", td_bold_style),
            Paragraph("Does excerpt refute the claim?", td_style),
            Paragraph("Excerpts containing negation patterns ('failed to') -&gt; CONTRADICTED.", td_style)
        ],
        [
            Paragraph("<b>9. Confidence Calibration</b>", td_bold_style),
            Paragraph("Is confidence properly scaled?", td_style),
            Paragraph("Supported facts score &gt;= 0.85; Partial facts score &lt;= 0.70.", td_style)
        ]
    ]
    v_table = Table(v9_data, colWidths=[110, 192, 230])
    v_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_CARD_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(v_table)
    story.append(Spacer(1, 6))

    # Step 8 & 9
    story.append(Paragraph("Steps 8 & 9: Coverage Auditing & Adaptive Feedback Loop (GapRecoveryEngine)", h2_style))
    story.append(Paragraph(
        "<b>Sources:</b> <code>agent/gap_recovery.py</code> & <code>agent/orchestrator.py</code><br/>"
        "• <b>Coverage Evaluation:</b> Subquestions are classified into <code>ANSWERED</code> (&gt;= 2 supported facts), "
        "<code>PARTIALLY_ANSWERED</code> (1 supported fact or partial facts), or <code>UNANSWERED</code>.<br/>"
        "• <b>Autonomous Trigger:</b> If unresolved gaps remain and search round &lt; <code>max_search_rounds</code> (default: 2), "
        "the orchestrator enters the <b>Adaptive Recovery Loop</b>.<br/>"
        "• <b>Targeted Follow-up Formulation:</b> Rather than repeating the initial search, the engine isolates the exact missing criteria:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<i>Round 1 Query:</i> 'camera smartphones under INR 30000 India models'<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<i>Round 2 Gap Query:</i> 'camera smartphones India low_light_performance comparative test results night mode'<br/>"
        "• Follow-up search results pass through the same strict filtering, extraction, and verification pipelines until coverage criteria are satisfied.",
        body_style
    ))
    story.append(Spacer(1, 6))

    # Step 10 & 11
    story.append(Paragraph("Steps 10 & 11: Citation Validation & Contradiction Detection", h2_style))
    story.append(Paragraph(
        "<b>Sources:</b> <code>agent/citation_validator.py</code> & <code>agent/contradiction_detector.py</code><br/>"
        "• <b>Citation Integrity (<code>CitationValidator</code>):</b> Verifies 5 factors before publication: 1) Source URL exists in storage; "
        "2) Quoted text appears verbatim in source body; 3) Supporting excerpt is present; 4) Named entities match; 5) Factual overlap exists. "
        "Emits statuses: <code>VALID</code>, <code>PARTIALLY_VALID</code>, <code>INVALID</code>, or <code>SOURCE_UNAVAILABLE</code>.<br/>"
        "• <b>Contradiction Analysis (<code>ContradictionDetector</code>):</b> Compares pairwise evidence within each dimension. When opposing "
        "assessments appear (e.g. 'sharp night shots' vs 'soft low-light photos'), the detector examines publication dates (detecting firmware changes), "
        "testing methodologies (lab chart vs handheld), and variant discrepancies. Generates structured <code>ContradictionRecord</code> objects with "
        "<code>resolution_status = 'UNRESOLVED_DISCLOSED'</code> for inclusion in Section 5 of the report.",
        body_style
    ))
    story.append(Spacer(1, 6))

    # Step 12
    story.append(Paragraph("Step 12: Independent 12-Point Final Quality Gate (QualityGate)", h2_style))
    story.append(Paragraph(
        "<b>Source:</b> <code>agent/quality_gate.py</code> &nbsp;|&nbsp; <b>Requirement:</b> <code>Score >= 0.80 AND Critical Failures == 0</code><br/>"
        "An independent post-generation auditor that inspects the synthesized report against the Evidence Ledger:",
        body_style
    ))
    q12_data = [
        [Paragraph("12 Quality Gate Audit Checks", th_style), Paragraph("Bounded Automated Repair Mechanism", th_style)],
        [
            Paragraph(
                "1. Direct Inquiry Answered &nbsp;|&nbsp; 2. Hard Constraints Respected<br/>"
                "3. Claims Backed by Ledger &nbsp;|&nbsp; 4. Citations Point to Valid URLs<br/>"
                "5. Excerpts Substantiate Claims &nbsp;|&nbsp; 6. Negative Domains Excluded<br/>"
                "7. Comparative Claims Grounded &nbsp;|&nbsp; 8. Disagreements Disclosed<br/>"
                "9. Stale Details Timestamped &nbsp;|&nbsp; 10. Research Gaps Acknowledged<br/>"
                "11. Recommendations Grounded &nbsp;|&nbsp; 12. Standalone Coherence",
                td_style
            ),
            Paragraph(
                "• <b>Off-Topic Pruning:</b> Automatically detects and removes off-topic findings (e.g. commercial vehicle insertions) from report text.<br/>"
                "• <b>Superlative Qualification:</b> Automatically qualifies unbacked comparative claims.<br/>"
                "• <b>Gap Injection:</b> Injects explicit uncertainty disclosures for unresolved questions.<br/>"
                "• <b>Decision Rule:</b> If repairs resolve issues, report is approved (<code>report_passed = True</code>); otherwise rejected.",
                td_style
            )
        ]
    ]
    q12_table = Table(q12_data, colWidths=[270, 262])
    q12_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [C_CARD_BG]),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(q12_table)
    story.append(Spacer(1, 6))

    # Steps 13, 14, 15
    story.append(Paragraph("Steps 13, 14 & 15: Synthesis, Research Audit & UI Presentation", h2_style))
    story.append(Paragraph(
        "<b>Sources:</b> <code>agent/report_generator.py</code>, <code>models/schemas.py</code>, <code>app.py</code><br/>"
        "• <b>Report Synthesis (Step 13):</b> Assembles a user-facing Markdown document structured across 9 sections: Executive Direct Answer, "
        "Scope & Methodology, Key Findings & Candidate Comparison Matrix, Evidence Table with clickable links (<code>[Publisher](url)</code>), "
        "Trade-offs & Conflicting Evidence, Actionable Recommendations, and Uncertainty Disclosures.<br/>"
        "• <b>Machine-Readable Audit (Step 14):</b> Emits a complete JSON file (<code>ResearchAudit</code>) detailing query intent, planned subquestions, "
        "every query executed, accepted sources, rejected sources with exact scores and reasons, evidence ledger entries, and quality gate scores.<br/>"
        "• <b>UI Presentation (Step 15):</b> Streamlit frontend renders an Executive Hero Banner, interactive comparison matrices, and a "
        "dedicated <i>Research Audit Tab</i> featuring metric cards, source rejection inspectors, and one-click JSON/Markdown downloads.",
        body_style
    ))
    story.append(Spacer(1, 10))

    # -------------------------------------------------------------
    # STATE TRANSITIONS TABLE
    # -------------------------------------------------------------
    story.append(Paragraph("State Transitions & Data Schema Matrix", h1_style))
    state_data = [
        [Paragraph("Pipeline Stage", th_style), Paragraph("Component", th_style), Paragraph("Output Schema", th_style), Paragraph("Store Destination", th_style)],
        [Paragraph("<b>Step 1: Analysis</b>", td_bold_style), Paragraph("QueryAnalyzer", td_style), Paragraph("QueryIntent", td_style), Paragraph("run.query_intent", td_style)],
        [Paragraph("<b>Step 2: Planning</b>", td_bold_style), Paragraph("ResearchPlanner", td_style), Paragraph("ResearchPlan & Questions", td_style), Paragraph("run.research_plan", td_style)],
        [Paragraph("<b>Step 3: Retrieval</b>", td_bold_style), Paragraph("WebSearchTool", td_style), Paragraph("Raw Search Dicts", td_style), Paragraph("In-memory query buffer", td_style)],
        [Paragraph("<b>Step 4: Filtering</b>", td_bold_style), Paragraph("SourceFilter", td_style), Paragraph("Accepted vs Rejected", td_style), Paragraph("run.sources / rejected_sources", td_style)],
        [Paragraph("<b>Step 5: Extraction</b>", td_bold_style), Paragraph("PageExtractor", td_style), Paragraph("Sanitized Markdown", td_style), Paragraph("Source.extracted_content", td_style)],
        [Paragraph("<b>Step 6: Ledgering</b>", td_bold_style), Paragraph("ResearchAnalyst", td_style), Paragraph("Evidence / EvidenceItem", td_style), Paragraph("run.evidence_records", td_style)],
        [Paragraph("<b>Step 7: Verification</b>", td_bold_style), Paragraph("ClaimVerifier", td_style), Paragraph("VerifiedClaim (9-point)", td_style), Paragraph("Evidence.verification_status", td_style)],
        [Paragraph("<b>Step 8: Auditing</b>", td_bold_style), Paragraph("GapRecoveryEngine", td_style), Paragraph("Coverage Status", td_style), Paragraph("ResearchQuestion.status", td_style)],
        [Paragraph("<b>Step 9: Feedback</b>", td_bold_style), Paragraph("Orchestrator Loop", td_style), Paragraph("SearchRound (Round 2)", td_style), Paragraph("run.search_rounds", td_style)],
        [Paragraph("<b>Step 10: Citations</b>", td_bold_style), Paragraph("CitationValidator", td_style), Paragraph("CitationValidation", td_style), Paragraph("run.citation_validations", td_style)],
        [Paragraph("<b>Step 11: Conflicts</b>", td_bold_style), Paragraph("ContradictionDetector", td_style), Paragraph("ContradictionRecord", td_style), Paragraph("run.contradictions", td_style)],
        [Paragraph("<b>Step 12: Quality Gate</b>", td_bold_style), Paragraph("QualityGate", td_style), Paragraph("QualityGateResult", td_style), Paragraph("run.quality_gate_result", td_style)],
        [Paragraph("<b>Step 13: Synthesis</b>", td_bold_style), Paragraph("ReportGenerator", td_style), Paragraph("FinalReport (Markdown)", td_style), Paragraph("run.final_report", td_style)],
        [Paragraph("<b>Step 14: Audit Log</b>", td_bold_style), Paragraph("ReportGenerator", td_style), Paragraph("ResearchAudit (JSON)", td_style), Paragraph("run.research_audit", td_style)],
        [Paragraph("<b>Step 15: UI</b>", td_bold_style), Paragraph("Streamlit app.py", td_style), Paragraph("Two-Pane Interactive Web UI", td_style), Paragraph("Browser Presentation Screen", td_style)],
    ]
    st_table = Table(state_data, colWidths=[90, 110, 150, 182])
    st_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_CARD_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(st_table)
    story.append(Spacer(1, 10))

    # Concluding System Reliability Callout
    callout_html = (
        "<b>System Reliability & Verification Guarantee:</b> ResearchPilot AI is engineered to minimize hallucinations through "
        "rigorous relevance gating, claim-level passage alignment, citation verification, contradiction detection, research gap recovery, "
        "and post-generation quality gate auditing. While these mechanisms eliminate ungrounded speculative output across standard web research, "
        "AI systems operating over open-web corpora cannot claim zero hallucinations. All production deployments preserve explicit uncertainty "
        "disclosures and source traceability."
    )
    c_table = Table([[Paragraph(callout_html, callout_style)]], colWidths=[printable_w])
    c_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_ACCENT_BG),
        ('BOX', (0,0), (-1,-1), 1, C_ACCENT),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(c_table)

    # Build Document using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF: {filename}")


if __name__ == "__main__":
    out_pdf = "ResearchPilot_Architecture_Deep_Dive.pdf"
    if len(sys.argv) > 1:
        out_pdf = sys.argv[1]
    build_pdf(out_pdf)
