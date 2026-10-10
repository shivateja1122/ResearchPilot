"""
Researcher Agent (Agent 2).
Retrieves relevant web sources, applies strict relevance and negative-boundary filtering,
extracts full page contents, scrubs noise, and collects traceable evidence items.
"""
from __future__ import annotations
import re
import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from tools.web_search import WebSearchTool
from tools.source_filter import SourceFilter
from tools.page_extractor import PageExtractor
from agent.analyst import ResearchAnalyst
from agent.llm_client import LLMClient
from models.schemas import QueryIntent, ResearchQuestion, Source, Evidence


class ResearcherAgent:
    """
    Agent 2: Researcher Agent.
    Interacts with external search and extraction tools to gather verifiable evidence.
    Does not hallucinate sources or claim support from model memory.
    """
    def __init__(
        self,
        search_tool: Optional[WebSearchTool] = None,
        page_extractor: Optional[PageExtractor] = None,
        llm_client: Optional[LLMClient] = None,
        search_timeout: int = 10,
        page_timeout: int = 8
    ):
        self.search_tool = search_tool or WebSearchTool(timeout_seconds=search_timeout)
        self.page_extractor = page_extractor or PageExtractor(timeout_seconds=page_timeout)
        self.llm = llm_client or LLMClient()
        self.analyst = ResearchAnalyst(self.llm)

    def _build_search_query(self, task: Dict[str, Any], intent: Optional[Dict[str, Any]] = None) -> str:
        """Formulates a concise search query avoiding conversational filler words."""
        q_text = task.get("question", "") or task.get("question_text", "")
        topic = (intent.get("topic") if intent else "") or (intent.get("original_query") if intent else "") or q_text
        geo = (intent.get("geographic_scope") if intent else "") or ""
        
        budget_str = ""
        constraints = (intent.get("constraints") or intent.get("explicit_constraints") or {}) if intent else {}
        if constraints.get("max_budget"):
            curr = constraints.get("currency", "")
            b_val = constraints.get("max_budget")
            budget_str = f"under {curr} {b_val}".strip()

        # If this is a targeted follow-up task, incorporate missing criteria
        if task.get("is_follow_up") and task.get("missing_criteria"):
            missing = task["missing_criteria"]
            return f"{topic} {geo} {task.get('dimension', '')} {missing}"[:95].strip()

        # Extract 3-5 core search terms from question text
        q_words = [w for w in re.findall(r"\w{3,}", q_text.lower())
                   if w not in ("what", "which", "how", "these", "each", "across", "compare", "options", "does", "have", "with", "from")]

        key_terms = " ".join(q_words[:4])
        query_parts = [topic, budget_str, geo, key_terms]
        clean_parts = [p.strip() for p in query_parts if p.strip()]
        return " ".join(clean_parts)[:100]

    def execute_task(
        self,
        task: Dict[str, Any],
        intent_dict: Optional[Dict[str, Any]] = None,
        max_sources: int = 3,
        relevance_threshold: float = 58.0
    ) -> Dict[str, Any]:
        """
        Executes web retrieval, strict relevance filtering, page extraction,
        and atomic evidence extraction for a research question.
        Conforms strictly to the Agent 2 output schema.
        """
        task_id = task.get("task_id", f"TASK_{uuid.uuid4().hex[:6].upper()}")
        question_id = task.get("question_id", "Q1")
        q_text = task.get("question", "") or task.get("question_text", "")

        intent_obj = None
        if intent_dict:
            try:
                intent_obj = QueryIntent(**intent_dict)
            except Exception:
                pass

        subq_obj = ResearchQuestion(
            question_id=question_id,
            question_text=q_text,
            dimension=task.get("dimension"),
            importance=task.get("priority", "high"),
            required_evidence=task.get("required_evidence", []),
            completion_criteria=task.get("completion_criteria", [])
        )

        sources_out: List[Dict[str, Any]] = []
        evidence_out: List[Dict[str, Any]] = []
        unresolved_info: List[str] = []
        errors_out: List[str] = []

        # 1. Formulate Search Query
        search_query = self._build_search_query(task, intent_dict)

        # 2. Call Search Tool
        try:
            raw_results = self.search_tool.search(search_query, max_results=max_sources + 2)
        except Exception as e:
            errors_out.append(f"Search provider error for query '{search_query}': {str(e)}")
            raw_results = []

        if not raw_results:
            unresolved_info.append(f"No web search results returned for question {question_id}")
            return {
                "task_id": task_id,
                "question_id": question_id,
                "query_executed": search_query,
                "sources": [],
                "evidence": [],
                "unresolved_information": unresolved_info,
                "errors": errors_out
            }

        # 3. Strict Relevance Filtering (Against intent, negative patterns, and subquestion)
        accepted_sources, rejected_sources = SourceFilter.filter_and_rank(
            raw_results,
            intent=intent_obj,
            question=subq_obj,
            max_sources=max_sources,
            threshold=relevance_threshold
        )

        # Record rejected sources
        for rej in rejected_sources:
            sources_out.append({
                "source_id": f"SRC_REJ_{uuid.uuid4().hex[:4].upper()}",
                "title": rej.get("title", ""),
                "url": rej.get("url", ""),
                "publisher": rej.get("publisher"),
                "published_at": rej.get("published_at"),
                "retrieval_status": "rejected",
                "relevance_score": rej.get("relevance_score", 20.0),
                "accepted": False,
                "rejection_reason": rej.get("rejection_reason", "Failed relevance gate")
            })

        # 4. Extract Full Content for Accepted Sources
        for item in accepted_sources:
            url = item.get("url", "")
            try:
                extracted = self.page_extractor.extract(url)
            except Exception as e:
                extracted = {"status": "failed", "content": "", "error_message": str(e)}
                errors_out.append(f"Extraction error for {url}: {str(e)}")

            retrieval_status = extracted.get("status", "failed")
            content = extracted.get("content", "")
            err = extracted.get("error_message")

            # Fallback to snippet if full extraction blocked
            if retrieval_status == "failed" and item.get("snippet"):
                retrieval_status = "snippet_only"
                content = item["snippet"]

            source_id = f"SRC_{uuid.uuid4().hex[:6].upper()}"
            source_record = {
                "source_id": source_id,
                "title": item.get("title") or extracted.get("title") or "Source",
                "url": url,
                "publisher": item.get("publisher"),
                "published_at": item.get("published_at") or extracted.get("publication_date"),
                "retrieval_status": "FULL_TEXT_RETRIEVED" if retrieval_status == "success" else retrieval_status.upper(),
                "relevance_score": item.get("relevance_score", 80.0),
                "accepted": True,
                "rejection_reason": None,
                "extracted_content": content,
                "snippet": item.get("snippet", "")
            }
            sources_out.append(source_record)

            # 5. Extract Atomic Evidence & Excerpts
            source_schema = Source(
                source_id=source_id,
                title=source_record["title"],
                url=url,
                snippet=source_record["snippet"],
                extracted_content=content,
                retrieval_status=retrieval_status
            )
            extracted_claims = self.analyst.extract_claims_with_verification(
                subq_obj, source_schema, intent=intent_obj
            )

            for c_text, ex, ver_stat, reason, ev_type, conf in extracted_claims:
                evidence_id = f"EVD_{uuid.uuid4().hex[:6].upper()}"
                evidence_out.append({
                    "evidence_id": evidence_id,
                    "source_id": source_id,
                    "source_url": url,
                    "question_id": question_id,
                    "claim": c_text,
                    "supporting_excerpt": ex,
                    "evidence_type": ev_type,
                    "initial_status": ver_stat,
                    "initial_reason": reason,
                    "confidence": conf
                })

        if not evidence_out:
            unresolved_info.append(f"No verifiable evidence items extracted for {question_id}")

        return {
            "task_id": task_id,
            "question_id": question_id,
            "query_executed": search_query,
            "sources": sources_out,
            "evidence": evidence_out,
            "unresolved_information": unresolved_info,
            "errors": errors_out
        }
