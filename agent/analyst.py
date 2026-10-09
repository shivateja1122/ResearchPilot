from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
from models.schemas import VerificationStatus, Source, ResearchQuestion
from agent.llm_client import LLMClient

NOISE_PATTERNS = [
    r"title:\s*",
    r"url source:\s*",
    r"markdown content:\s*",
    r"published time:\s*",
    r"warning:\s*target url returned error",
    r"skip to (navigation|main content)",
    r"\baccess denied\b",
    r"\b403\b",
    r"\bforbidden\b",
    r"oops,?\s*something went wrong",
    r"you don't have permission to access",
    r"prime (day|deals)",
    r"trending tickers",
    r"stock quote",
    r"delta's (q[1-4]|earnings)",
    r"cookie (policy|consent)",
    r"terms of (service|use)"
]


class ExtractedClaimItem(BaseModel):
    claim_text: str = Field(description="A concise factual claim extracted from the source content answering the research inquiry")
    supporting_excerpt: str = Field(description="The exact supporting excerpt from the source text that substantiates this claim")
    status: Optional[str] = Field(default="supported", description="'supported', 'partially_supported', 'contradicted', or 'unverified'")
    reason: Optional[str] = Field(default="Substantiated by retrieved excerpt.", description="Explanation of verification status")


class ClaimExtractionResult(BaseModel):
    claims: List[ExtractedClaimItem] = Field(default_factory=list)


class VerificationResult(BaseModel):
    status: str = Field(description="'supported', 'partially_supported', 'contradicted', or 'unverified'")
    reason: str = Field(description="Explanation of why this status was assigned")


class ResearchAnalyst:
    """
    Performs claim extraction from retrieved source texts and rigorous
    claim-to-evidence verification against source passages.
    """
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    @staticmethod
    def is_noise(text: str) -> bool:
        if not text or len(text.strip()) < 20:
            return True
        text_lower = text.lower()
        for pat in NOISE_PATTERNS:
            if re.search(pat, text_lower):
                return True
        return False

    def extract_claims_with_verification(
        self, question: ResearchQuestion, source: Source
    ) -> List[Tuple[str, str, VerificationStatus, str]]:
        """
        Extracts factual claims and performs immediate verification in a single pass.
        Returns list of (claim_text, supporting_excerpt, verification_status, reason).
        """
        content_to_analyze = source.extracted_content if source.extracted_content else source.snippet
        if not content_to_analyze:
            return []

        # Discard if source itself is an error or forbidden page
        if self.is_noise(content_to_analyze[:300]):
            return []

        context_sample = content_to_analyze[:3500]

        prompt = (
            f"Research Subquestion: {question.question_text}\n"
            f"Source Title: {source.title}\n"
            f"Source Content:\n{context_sample}\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"1. Extract 1 to 2 distinct, verifiable factual statements answering the subquestion.\n"
            f"2. DO NOT extract website metadata, headers ('Title:', 'URL Source:', 'Markdown Content:'), stock quotes, error messages ('Access Denied'), or navigation links.\n"
            f"3. If the source content does not contain substantive facts answering this subquestion, return an empty list of claims [].\n"
            f"4. Assign rigorous status ('supported', 'partially_supported', 'contradicted', 'unverified') and reason."
        )
        system_prompt = (
            "You are a rigorous factual research auditor. Extract only substantive, topical claims and assign strict status."
        )

        try:
            result = self.llm.generate_json(prompt, system_prompt, ClaimExtractionResult)
            if result and result.claims:
                verified_items = []
                for item in result.claims:
                    c_text = item.claim_text.strip() if item.claim_text else ""
                    ex_text = item.supporting_excerpt.strip() if item.supporting_excerpt else ""
                    
                    # Filter out any hallucinated noise
                    if not c_text or not ex_text or self.is_noise(c_text) or self.is_noise(ex_text):
                        continue

                    stat = VerificationStatus.SUPPORTED
                    raw_status = (item.status or "supported").lower().replace("-", "_").strip()
                    for member in VerificationStatus:
                        if member.value == raw_status:
                            stat = member
                            break
                    verified_items.append((
                        c_text,
                        ex_text,
                        stat,
                        item.reason or "Audited against source passage."
                    ))
                if verified_items:
                    return verified_items
        except Exception:
            pass

        # Robust heuristic fallback
        raw_claims = self._heuristic_extract_claims(question.question_text, content_to_analyze)
        res = []
        for c_text, ex_text in raw_claims:
            st_val, r_val = self._heuristic_verify(c_text, ex_text)
            res.append((c_text, ex_text, st_val, r_val))
        return res

    def extract_claims(self, question: ResearchQuestion, source: Source) -> List[Tuple[str, str]]:
        """
        Extracts factual claims and supporting excerpts from the source.
        Returns list of tuples: [(claim_text, supporting_excerpt)]
        """
        items = self.extract_claims_with_verification(question, source)
        return [(c, e) for c, e, _, _ in items]

    def verify_claim(self, claim_text: str, supporting_excerpt: str) -> Tuple[VerificationStatus, str]:
        """
        Compares claim with supporting excerpt and classifies relationship.
        Returns (VerificationStatus, verification_reason).
        """
        claim_clean = claim_text.strip()
        excerpt_clean = supporting_excerpt.strip()

        if not excerpt_clean or len(excerpt_clean) < 10:
            return (
                VerificationStatus.UNVERIFIED,
                "Supporting excerpt is empty or insufficiently informative to substantiate the claim."
            )

        if self.is_noise(claim_clean) or self.is_noise(excerpt_clean):
            return (
                VerificationStatus.UNVERIFIED,
                "Claim or excerpt appears to be non-topical boilerplate, navigation, or scraping noise."
            )

        prompt = (
            f"Evaluate the factual relationship between this Claim and the Supporting Excerpt.\n\n"
            f"Claim: \"{claim_clean}\"\n\n"
            f"Supporting Excerpt: \"{excerpt_clean}\"\n\n"
            f"Classification criteria:\n"
            f"- 'supported': Excerpt clearly and sufficiently substantiates the claim.\n"
            f"- 'partially_supported': Excerpt supports part of the claim or introduces significant caveats.\n"
            f"- 'contradicted': Excerpt materially conflicts with or disproves the claim.\n"
            f"- 'unverified': Excerpt is off-topic, irrelevant, or fails to establish whether the claim is true.\n"
        )
        system_prompt = (
            "You are a rigorous research auditor. Respond with JSON containing 'status' and 'reason'."
        )

        try:
            ver_res = self.llm.generate_json(prompt, system_prompt, VerificationResult)
            if ver_res and ver_res.status:
                status_str = ver_res.status.lower().replace("-", "_").strip()
                for member in VerificationStatus:
                    if member.value == status_str or member.name.lower() == status_str:
                        return (member, ver_res.reason or f"Evaluated as {member.value}.")
        except Exception:
            pass

        # Heuristic verification
        return self._heuristic_verify(claim_clean, excerpt_clean)

    def _heuristic_extract_claims(self, question_text: str, content: str) -> List[Tuple[str, str]]:
        """
        Rule-based extraction of key factual sentences with strict relevance gating.
        """
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", content) if len(s.strip()) > 40]
        q_tokens = set(re.findall(r"\w{4,}", question_text.lower()))

        scored_sentences = []
        for s in sentences:
            if self.is_noise(s):
                continue
            s_tokens = set(re.findall(r"\w{4,}", s.lower()))
            overlap = len(q_tokens.intersection(s_tokens))
            # Require at least 2 key term overlaps for topical relevance
            if overlap >= 2:
                scored_sentences.append((overlap, s))

        scored_sentences.sort(key=lambda x: x[0], reverse=True)

        claims = []
        for _, s in scored_sentences[:2]:
            claims.append((s, s))

        # Never append noise or first arbitrary sentence if no relevant sentences found
        return claims

    def _heuristic_verify(self, claim: str, excerpt: str) -> Tuple[VerificationStatus, str]:
        """
        Deterministic verification analysis for testing and fallback mode.
        Detects noise, citation mismatch, contradictions, and word overlap.
        """
        if self.is_noise(claim) or self.is_noise(excerpt):
            return (
                VerificationStatus.UNVERIFIED,
                "Statement or cited passage contains non-topical boilerplate or scraping artifact."
            )

        c_words = set(re.findall(r"\w{4,}", claim.lower()))
        e_words = set(re.findall(r"\w{4,}", excerpt.lower()))

        if not c_words:
            return (VerificationStatus.UNVERIFIED, "Claim contains insufficient specific terms.")

        overlap = len(c_words.intersection(e_words))
        overlap_ratio = overlap / len(c_words)

        # Citation mismatch (Test D scenario)
        if overlap_ratio < 0.25:
            return (
                VerificationStatus.UNVERIFIED,
                "Supporting excerpt does not contain relevant terms or context to substantiate this claim."
            )

        # Contradiction check
        contradiction_patterns = [
            r"\bdoes not\b", r"\bcannot\b", r"\bfailed to\b", r"\bno evidence\b",
            r"\bunproven\b", r"\bcontrary to\b", r"\brefuted\b"
        ]
        has_negation = any(re.search(p, excerpt.lower()) for p in contradiction_patterns)
        if has_negation and not any(re.search(p, claim.lower()) for p in contradiction_patterns):
            return (
                VerificationStatus.CONTRADICTED,
                "Excerpt contains negative or qualifying statements that materially conflict with the claim."
            )

        if overlap_ratio >= 0.55:
            return (
                VerificationStatus.SUPPORTED,
                "Retrieved excerpt directly aligns with the core factual assertions of the claim."
            )
        else:
            return (
                VerificationStatus.PARTIALLY_SUPPORTED,
                "Excerpt provides partial thematic corroboration but lacks complete verification of all claim details."
            )
