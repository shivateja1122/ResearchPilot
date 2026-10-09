from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
from models.schemas import VerificationStatus, Source, ResearchQuestion
from agent.llm_client import LLMClient


class ExtractedClaimItem(BaseModel):
    claim_text: str = Field(description="A concise factual claim extracted from the source content")
    supporting_excerpt: str = Field(description="The exact or near-exact excerpt from the source text that supports this claim")


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

    def extract_claims(self, question: ResearchQuestion, source: Source) -> List[Tuple[str, str]]:
        """
        Extracts factual claims and supporting excerpts from the source.
        Returns list of tuples: [(claim_text, supporting_excerpt)]
        """
        content_to_analyze = source.extracted_content if source.extracted_content else source.snippet
        if not content_to_analyze:
            return []

        # Limit context to avoid token bloat
        context_sample = content_to_analyze[:3500]

        prompt = (
            f"Research Subquestion: {question.question_text}\n"
            f"Source Title: {source.title}\n"
            f"Source Content:\n{context_sample}\n\n"
            f"Extract 1 to 3 distinct, verifiable factual claims from this text that help answer the research subquestion. "
            f"For each claim, copy the exact or near-exact supporting excerpt from the text."
        )
        system_prompt = (
            "You are an evidence extraction analyst. Extract only factual statements directly present in the source text. "
            "Do NOT hallucinate or extrapolate beyond the provided text."
        )

        try:
            result = self.llm.generate_json(prompt, system_prompt, ClaimExtractionResult)
            if result and result.claims:
                claims = []
                for item in result.claims:
                    if item.claim_text and item.supporting_excerpt:
                        claims.append((item.claim_text.strip(), item.supporting_excerpt.strip()))
                if claims:
                    return claims
        except Exception:
            pass

        # Robust heuristic fallback claim extraction
        return self._heuristic_extract_claims(question.question_text, content_to_analyze)

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
        Rule-based extraction of key factual sentences based on question keywords.
        """
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", content) if len(s.strip()) > 35]
        q_tokens = set(re.findall(r"\w{4,}", question_text.lower()))

        scored_sentences = []
        for s in sentences:
            s_tokens = set(re.findall(r"\w{4,}", s.lower()))
            overlap = len(q_tokens.intersection(s_tokens))
            if overlap > 0:
                scored_sentences.append((overlap, s))

        scored_sentences.sort(key=lambda x: x[0], reverse=True)

        claims = []
        for _, s in scored_sentences[:2]:
            claims.append((s, s))

        if not claims and sentences:
            claims.append((sentences[0], sentences[0]))

        return claims

    def _heuristic_verify(self, claim: str, excerpt: str) -> Tuple[VerificationStatus, str]:
        """
        Deterministic verification analysis for testing and fallback mode.
        Detects mismatch, contradictions, and word overlap.
        """
        c_words = set(re.findall(r"\w{4,}", claim.lower()))
        e_words = set(re.findall(r"\w{4,}", excerpt.lower()))

        if not c_words:
            return (VerificationStatus.UNVERIFIED, "Claim contains insufficient specific terms.")

        overlap = len(c_words.intersection(e_words))
        overlap_ratio = overlap / len(c_words)

        # Check for citation mismatch (Test D scenario)
        if overlap_ratio < 0.2:
            return (
                VerificationStatus.UNVERIFIED,
                "Supporting excerpt does not contain relevant terms or context to substantiate this claim."
            )

        # Check for contradiction words
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

        if overlap_ratio >= 0.5:
            return (
                VerificationStatus.SUPPORTED,
                "Retrieved excerpt directly aligns with the core factual assertions of the claim."
            )
        else:
            return (
                VerificationStatus.PARTIALLY_SUPPORTED,
                "Excerpt provides partial thematic corroboration but lacks complete verification of all claim details."
            )
