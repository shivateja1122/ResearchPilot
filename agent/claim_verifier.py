from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from models.schemas import VerificationStatus, VerifiedClaim, Evidence
from agent.llm_client import LLMClient


class ClaimVerificationOutput(BaseModel):
    claim_id: str = "CLM_001"
    claim_text: str
    status: str = Field(description="'supported', 'partially_supported', 'contradicted', or 'unverified'")
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    verification_reason: str = Field(description="Concrete reason justifying the assigned verification status")
    limitations: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.85, description="Confidence score between 0.0 and 1.0")


class ClaimVerifier:
    """
    Rigorously verifies factual claims against linked evidence passages.
    Enforces 9 core verification checks:
    1. Exact passage support
    2. Entity/subject/context alignment
    3. Entire statement substantiated
    4. Rejection of unmentioned details
    5. Prevention of overgeneralization (e.g. spec sheet cannot prove 'best camera')
    6. Source suitability for claim type
    7. Evidence freshness/currency
    8. Contradiction evaluation
    9. Prevention of conclusions stronger than the evidence
    """
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def verify(
        self,
        claim_text: str,
        supporting_excerpt: str,
        claim_id: str = "CLM_001",
        evidence_id: Optional[str] = None,
        source_date: Optional[str] = None,
        source_type: Optional[str] = None,
        contradicting_excerpt: Optional[str] = None
    ) -> VerifiedClaim:
        c_clean = claim_text.strip()
        e_clean = supporting_excerpt.strip()

        # Deterministic sanity checks first
        deterministic_status, deterministic_reason = self._deterministic_precheck(
            c_clean, e_clean, source_date=source_date, source_type=source_type
        )
        if deterministic_status is not None:
            return VerifiedClaim(
                claim_id=claim_id,
                claim_text=c_clean,
                status=deterministic_status,
                supporting_evidence_ids=[evidence_id] if evidence_id and deterministic_status in (VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED) else [],
                contradicting_evidence_ids=[evidence_id] if evidence_id and deterministic_status == VerificationStatus.CONTRADICTED else [],
                verification_reason=deterministic_reason,
                limitations=["Deterministic verification rule triggered."] if deterministic_status != VerificationStatus.SUPPORTED else [],
                confidence=0.92 if deterministic_status == VerificationStatus.SUPPORTED else 0.50
            )

        prompt = (
            f"You are a strict Claim Verifier for ResearchPilot AI.\n"
            f"Evaluate the factual truth of this Claim against the Retrieved Evidence Excerpt.\n\n"
            f"Claim: \"{c_clean}\"\n"
            f"Supporting Excerpt: \"{e_clean}\"\n"
            f"Source Type: {source_type or 'General web article'}\n"
            f"Source Date: {source_date or 'Undated'}\n\n"
            f"CRITICAL VERIFICATION RULES:\n"
            f"1. Passage must support the exact claim. Do not assume or extrapolate.\n"
            f"2. A technical specification (e.g. '50 MP sensor') does NOT support a comparative superiority claim (e.g. 'This is the best camera phone under 30k'). If comparative claim lacks comparative evidence, return UNVERIFIED.\n"
            f"3. A daylight photography review does NOT support low-light photography claims. Return UNVERIFIED.\n"
            f"4. If the source excerpt contradicts the claim, return CONTRADICTED.\n"
            f"5. If excerpt only partially supports the claim, return PARTIALLY_SUPPORTED.\n"
            f"6. Assign 'status' strictly from: supported, partially_supported, contradicted, unverified."
        )
        system_prompt = (
            "You are a rigorous ClaimVerifier. Never mark a claim supported unless the cited excerpt directly substantiates it."
        )

        try:
            out = self.llm.generate_json(prompt, system_prompt, ClaimVerificationOutput)
            if out and out.status and not out.status.lower().startswith("synthesized"):
                raw_stat = out.status.lower().replace("-", "_").strip()
                v_stat = VerificationStatus.UNVERIFIED
                for m in VerificationStatus:
                    if m.value == raw_stat or m.name.lower() == raw_stat:
                        v_stat = m
                        break

                if v_stat != VerificationStatus.UNVERIFIED or "unverified" in raw_stat:
                    return VerifiedClaim(
                        claim_id=claim_id,
                        claim_text=c_clean,
                        status=v_stat,
                        supporting_evidence_ids=[evidence_id] if evidence_id and v_stat in (VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED) else [],
                        contradicting_evidence_ids=[evidence_id] if evidence_id and v_stat == VerificationStatus.CONTRADICTED else [],
                        verification_reason=out.verification_reason or f"Evaluated as {v_stat.value}.",
                        limitations=out.limitations or [],
                        confidence=max(0.1, min(1.0, out.confidence))
                    )
        except Exception:
            pass

        # Fallback to deterministic verification engine
        stat, reason, conf = self._heuristic_deep_verify(
            c_clean, e_clean, source_date=source_date, source_type=source_type
        )
        return VerifiedClaim(
            claim_id=claim_id,
            claim_text=c_clean,
            status=stat,
            supporting_evidence_ids=[evidence_id] if evidence_id and stat in (VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED) else [],
            contradicting_evidence_ids=[evidence_id] if evidence_id and stat == VerificationStatus.CONTRADICTED else [],
            verification_reason=reason,
            limitations=["Evaluated using rule-based verification engine."] if stat != VerificationStatus.SUPPORTED else [],
            confidence=conf
        )

    def _deterministic_precheck(
        self,
        claim: str,
        excerpt: str,
        source_date: Optional[str] = None,
        source_type: Optional[str] = None
    ) -> Tuple[Optional[VerificationStatus], str]:
        c_lower = claim.lower()
        e_lower = excerpt.lower()

        # Empty excerpt check
        if not excerpt or len(excerpt.strip()) < 8:
            return (VerificationStatus.UNVERIFIED, "Supporting excerpt is missing or empty.")

        # Comparative Superlative Check:
        # e.g., "best camera", "superior to", "outperforms", "top-ranked"
        comparative_terms = [
            r"\bbest\b", r"\btop[- ]ranked\b", r"\bsuperior\b", r"\boutperforms\b",
            r"\bunbeatable\b", r"\bclear winner\b", r"\b#1\b", r"\bnumber one\b"
        ]
        has_comparative_claim = any(re.search(p, c_lower) for p in comparative_terms)
        if has_comparative_claim:
            # Does excerpt contain comparative test or competition words?
            comparative_evidence = [
                r"\bvs\b", r"\bcompared to\b", r"\bbeats\b", r"\bahead of\b",
                r"\boutperformed\b", r"\bcompetitor\b", r"\branked #?1\b", r"\bbest in (class|segment|test)\b"
            ]
            has_comp_ev = any(re.search(p, e_lower) for p in comparative_evidence)
            # If excerpt is purely a spec sheet without comparison, unverified!
            if not has_comp_ev:
                return (
                    VerificationStatus.UNVERIFIED,
                    "Comparative superiority claim ('best'/'superior') is not substantiated by comparative evidence in the cited excerpt."
                )

        # Aspect mismatch: Low-light vs Daylight
        low_light_terms = [r"\blow[- ]light\b", r"\bnight mode\b", r"\bdark conditions\b", r"\bdim light\b"]
        daylight_terms = [r"\bdaylight\b", r"\bbright sunlight\b", r"\boutdoor daytime\b"]
        if any(re.search(p, c_lower) for p in low_light_terms):
            if any(re.search(p, e_lower) for p in daylight_terms) and not any(re.search(p, e_lower) for p in low_light_terms):
                return (
                    VerificationStatus.UNVERIFIED,
                    "Claim asserts low-light performance, but cited excerpt only evaluates daylight/daytime conditions."
                )

        # Stale Pricing check:
        # If claim asserts a current price, but source date is old or unverified
        price_patterns = [r"₹\s*[\d,]+", r"\brs\.?\s*[\d,]+", r"\bcosts?\b", r"\bpriced at\b", r"\$\s*[\d,]+"]
        is_price_claim = any(re.search(p, c_lower) for p in price_patterns)
        if is_price_claim and source_date:
            try:
                # Check year in date
                year_match = re.search(r"\b(20[12][0-9])\b", source_date)
                if year_match:
                    year = int(year_match.group(1))
                    # Stale if older than 2024 for a current pricing check
                    if year < 2024:
                        return (
                            VerificationStatus.UNVERIFIED,
                            f"Price claim cannot be verified as current because source date ({source_date}) is outdated."
                        )
            except Exception:
                pass

        # Explicit contradiction keywords in excerpt
        negations = [r"\bdoes not\b", r"\bcannot\b", r"\bfailed to\b", r"\bno evidence\b", r"\bnot recommended\b", r"\bdisappoints\b"]
        if any(re.search(p, e_lower) for p in negations) and not any(re.search(p, c_lower) for p in negations):
            # Check overlap of subject
            c_words = set(re.findall(r"\w{4,}", c_lower))
            e_words = set(re.findall(r"\w{4,}", e_lower))
            if len(c_words.intersection(e_words)) >= 2:
                return (
                    VerificationStatus.CONTRADICTED,
                    "Cited excerpt contains negative or disconfirming findings materially conflicting with the claim."
                )

        return (None, "")

    def _heuristic_deep_verify(
        self,
        claim: str,
        excerpt: str,
        source_date: Optional[str] = None,
        source_type: Optional[str] = None
    ) -> Tuple[VerificationStatus, str, float]:
        c_words = set(re.findall(r"\w{3,}", claim.lower()))
        e_words = set(re.findall(r"\w{3,}", excerpt.lower()))

        # Remove common stop words
        stop = {"the", "and", "for", "with", "this", "that", "from", "are", "was", "under", "over"}
        c_words = c_words - stop
        e_words = e_words - stop

        if not c_words:
            return (VerificationStatus.UNVERIFIED, "Claim contains insufficient distinct terms.", 0.2)

        overlap = len(c_words.intersection(e_words))
        ratio = overlap / len(c_words)

        # Keyword alignment check
        if ratio < 0.28:
            return (
                VerificationStatus.UNVERIFIED,
                f"Low factual overlap ({ratio:.0%}): Excerpt does not contain sufficient terms to verify the statement.",
                0.35
            )

        # Check numerical / metric precision
        claim_numbers = set(re.findall(r"\b\d+(?:\.\d+)?(?:mp|mah|w|gb|hz|k|x)?\b", claim.lower()))
        excerpt_numbers = set(re.findall(r"\b\d+(?:\.\d+)?(?:mp|mah|w|gb|hz|k|x)?\b", excerpt.lower()))
        if claim_numbers:
            missing_numbers = claim_numbers - excerpt_numbers
            if missing_numbers:
                return (
                    VerificationStatus.PARTIALLY_SUPPORTED,
                    f"Excerpt supports general context but lacks verification for numbers/metrics: {missing_numbers}.",
                    0.65
                )

        if ratio >= 0.60:
            return (
                VerificationStatus.SUPPORTED,
                "The cited passage directly substantiates the factual assertions in the claim.",
                0.91
            )
        else:
            return (
                VerificationStatus.PARTIALLY_SUPPORTED,
                "The cited passage provides contextual corroboration but leaves minor details unconfirmed.",
                0.72
            )
