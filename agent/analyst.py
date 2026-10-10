from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
from models.schemas import VerificationStatus, Source, ResearchQuestion, QueryIntent, VerifiedClaim, Evidence
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
    r"terms of (service|use)",
    r"affiliate (disclosure|commission)",
    r"phone finder",
    r"compare mobiles",
    r"finding the best .* is now easier",
    r"here is a list of",
    r"welcome to our guide",
]


class ExtractedClaimItem(BaseModel):
    claim_text: str = Field(description="A concise, human-readable factual claim (under 250 chars) answering the research inquiry")
    supporting_excerpt: str = Field(description="The exact supporting excerpt from the source text (under 200 chars) that substantiates this claim")
    status: Optional[str] = Field(default="supported", description="'supported', 'partially_supported', 'contradicted', or 'unverified'")
    evidence_type: str = Field(default="direct", description="'direct' or 'inference'")
    reason: Optional[str] = Field(default="Substantiated by retrieved excerpt.", description="Explanation of verification status")
    confidence: float = Field(default=0.88, description="Evidence confidence score between 0.0 and 1.0")


class ClaimExtractionResult(BaseModel):
    claims: List[ExtractedClaimItem] = Field(default_factory=list)


class VerificationResult(BaseModel):
    status: str = Field(description="'supported', 'partially_supported', 'contradicted', or 'unverified'")
    reason: str = Field(description="Explanation of why this status was assigned")
    confidence: float = Field(default=0.85, description="Confidence score between 0.0 and 1.0")


class ResearchAnalyst:
    """
    Performs claim extraction from retrieved source texts and rigorous
    claim-to-evidence verification against source passages.
    Rejects claims that deviate from the research question and query boundaries.
    """
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    @staticmethod
    def is_noise(text: str) -> bool:
        if not text or len(text.strip()) < 20:
            return True
        # Filter out multi-column table dumps, run-on scraper blocks, and broken link fragments
        if text.count("|") >= 2 or len(text) > 400:
            return True
        if "](" in text or text.strip().startswith("* ["):
            return True
        text_lower = text.lower()
        for pat in NOISE_PATTERNS:
            if re.search(pat, text_lower):
                return True
        return False

    def extract_claims_with_verification(
        self,
        question: ResearchQuestion,
        source: Source,
        intent: Optional[QueryIntent] = None
    ) -> List[Tuple[str, str, VerificationStatus, str, str, float]]:
        """
        Extracts factual claims and performs immediate verification in a single pass.
        Returns list of (claim_text, supporting_excerpt, verification_status, reason, evidence_type, confidence).
        """
        content_to_analyze = source.extracted_content if source.extracted_content else source.snippet
        if not content_to_analyze:
            return []

        # Discard if source itself is an error or forbidden page
        if self.is_noise(content_to_analyze[:300]):
            return []

        context_sample = content_to_analyze[:3500]

        intent_context = ""
        if intent:
            intent_context = (
                f"Overall Query Topic: {intent.topic}\n"
                f"Primary Criteria: {', '.join(intent.primary_criteria)}\n"
                f"Explicit Excluded Off-Topic: {', '.join(intent.excluded_topics)}\n"
            )

        prompt = (
            f"Research Subquestion: {question.question_text}\n"
            f"Subquestion Reason: {question.reason or 'Answer research inquiry'}\n"
            f"{intent_context}"
            f"Source Title: {source.title}\n"
            f"Source Content:\n{context_sample}\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"1. Extract 1 to 2 distinct, concise (under 250 chars), clear factual claims directly answering this subquestion.\n"
            f"2. Every claim MUST state concrete details (e.g., specific models, benchmark numbers, camera sensor names/OIS, prices, test comparisons) in clear, plain language that any user can easily understand.\n"
            f"3. STRICT RELEVANCE: Reject statements about off-topic domains (e.g. electric vehicles, automotive energy, generic desktop PCs, stock quote movements) if this inquiry is about mobile phones or other specific topics.\n"
            f"4. DO NOT extract website metadata, headers ('Title:', 'URL Source:'), raw markdown tables, pipe characters '|', navigation buttons, or generic filler.\n"
            f"5. Supporting excerpt MUST be a clean, single sentence from the source (under 200 chars).\n"
            f"6. If the source content does not contain substantive facts answering this subquestion, return an empty list of claims [].\n"
            f"7. Assign rigorous status ('supported', 'partially_supported', 'contradicted', 'unverified'), evidence_type ('direct' or 'inference'), and confidence (0.0 to 1.0)."
        )
        system_prompt = (
            "You are a rigorous factual research auditor. Extract only substantive, topical claims directly answering the inquiry and assign strict status."
        )

        try:
            result = self.llm.generate_json(prompt, system_prompt, ClaimExtractionResult)
            if result and result.claims and not result.claims[0].claim_text.startswith("Synthesized"):
                verified_items = []
                for item in result.claims:
                    c_text = item.claim_text.strip() if item.claim_text else ""
                    ex_text = item.supporting_excerpt.strip() if item.supporting_excerpt else ""
                    
                    if not c_text or not ex_text or self.is_noise(c_text) or self.is_noise(ex_text):
                        continue

                    # Check excluded topics
                    if intent and intent.excluded_topics:
                        if any(excl.lower() in c_text.lower() for excl in intent.excluded_topics if len(excl) > 3):
                            continue

                    stat = VerificationStatus.SUPPORTED
                    raw_status = (item.status or "supported").lower().replace("-", "_").strip()
                    for member in VerificationStatus:
                        if member.value == raw_status:
                            stat = member
                            break

                    ev_type = item.evidence_type if item.evidence_type in ("direct", "inference") else "direct"
                    conf = max(0.1, min(1.0, item.confidence or 0.85))

                    verified_items.append((
                        c_text,
                        ex_text,
                        stat,
                        item.reason or "Audited against source passage.",
                        ev_type,
                        conf
                    ))
                if verified_items:
                    return verified_items
        except Exception:
            pass

        # Robust heuristic fallback
        raw_claims = self._heuristic_extract_claims(question.question_text, content_to_analyze, intent)
        res = []
        for c_text, ex_text in raw_claims:
            st_val, r_val = self._heuristic_verify(c_text, ex_text)
            res.append((c_text, ex_text, st_val, r_val, "direct", 0.85))
        return res

    def extract_claims(self, question: ResearchQuestion, source: Source) -> List[Tuple[str, str]]:
        items = self.extract_claims_with_verification(question, source)
        return [(c, e) for c, e, _, _, _, _ in items]

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
            f"- 'supported': Excerpt clearly and sufficiently substantiates the complete claim on the same subject.\n"
            f"- 'partially_supported': Excerpt supports part of the claim or introduces significant caveats.\n"
            f"- 'contradicted': Excerpt materially conflicts with or disproves the claim.\n"
            f"- 'unverified': Excerpt is off-topic, irrelevant, or fails to establish whether the claim is true.\n"
        )
        system_prompt = (
            "You are a rigorous research auditor. Respond with JSON containing 'status', 'reason', and 'confidence'."
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

    def _heuristic_extract_claims(
        self,
        question_text: str,
        content: str,
        intent: Optional[QueryIntent] = None
    ) -> List[Tuple[str, str]]:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", content) if 40 < len(s.strip()) <= 280]
        q_tokens = set(re.findall(r"\w{4,}", question_text.lower()))

        scored_sentences = []
        for s in sentences:
            if self.is_noise(s):
                continue
            if "|" in s or "](" in s or s.startswith(("*", "-", "#")):
                continue
            if re.search(r"^(finding the best|here is a list|welcome to|in this guide|click here|read more)", s.lower()):
                continue

            # Excluded topic filter
            if intent and intent.excluded_topics:
                if any(excl.lower() in s.lower() for excl in intent.excluded_topics if len(excl) > 3):
                    continue

            s_tokens = set(re.findall(r"\w{4,}", s.lower()))
            overlap = len(q_tokens.intersection(s_tokens))
            if overlap >= 2:
                scored_sentences.append((overlap, s))

        scored_sentences.sort(key=lambda x: x[0], reverse=True)

        claims = []
        seen_texts = set()
        for _, s in scored_sentences[:2]:
            clean_s = re.sub(r"\s+", " ", s).strip()
            if clean_s.lower() not in seen_texts:
                seen_texts.add(clean_s.lower())
                claims.append((clean_s, clean_s))

        return claims

    def _heuristic_verify(self, claim: str, excerpt: str) -> Tuple[VerificationStatus, str]:
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

        # Citation mismatch
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
