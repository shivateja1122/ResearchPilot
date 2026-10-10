from __future__ import annotations
import re
from typing import Dict, Any, List, Optional, Tuple
from models.schemas import CitationStatus, CitationValidation, Evidence, Source, ResearchRun


class CitationValidator:
    """
    Validates citation integrity before publication:
    - Verifies source was actually retrieved
    - Validates URL and source ID mapping
    - Confirms source passage exists in stored evidence ledger
    - Checks entity/topic alignment between claim and cited source
    - Validates that quotations are reproduced accurately
    - Flags INVALID or SOURCE_UNAVAILABLE citations for automated repair
    """
    def __init__(self):
        pass

    def validate_citation(
        self,
        citation_id: str,
        claim_id: str,
        claim_text: str,
        source_id: str,
        run: ResearchRun,
        supporting_excerpt: Optional[str] = None
    ) -> CitationValidation:
        # 1. Check if source exists in run's retrieved sources
        source = run.sources.get(source_id)
        if not source:
            # Check if it was rejected or missing
            is_rejected = source_id in run.rejected_sources
            return CitationValidation(
                citation_id=citation_id,
                claim_id=claim_id,
                source_id=source_id,
                passage_verified=False,
                entity_match=False,
                claim_supported=False,
                citation_status=CitationStatus.SOURCE_UNAVAILABLE,
                reason=f"Source [{source_id}] was {'rejected for low relevance' if is_rejected else 'never retrieved or indexed'}."
            )

        # 2. Check if retrieval succeeded
        if source.retrieval_status == "failed" and not source.snippet:
            return CitationValidation(
                citation_id=citation_id,
                claim_id=claim_id,
                source_id=source_id,
                passage_verified=False,
                entity_match=False,
                claim_supported=False,
                citation_status=CitationStatus.SOURCE_UNAVAILABLE,
                reason=f"Source [{source_id}] failed during web extraction ({source.error_message or 'network error'})."
            )

        # 3. Passage presence verification
        source_text = f"{source.extracted_content} {source.snippet}".lower()
        excerpt = supporting_excerpt or ""
        passage_verified = True
        if excerpt:
            # Check if excerpt words appear in source text
            ex_words = [w for w in re.findall(r"\w{4,}", excerpt.lower()) if len(w) > 3]
            if ex_words:
                found_count = sum(1 for w in ex_words if w in source_text)
                passage_verified = (found_count / len(ex_words)) >= 0.50
            else:
                passage_verified = excerpt.lower() in source_text

        # 4. Quotation exactness check
        quotes = re.findall(r'"([^"]{10,})"', claim_text)
        quote_verified = True
        if quotes:
            for q in quotes:
                if q.lower() not in source_text:
                    quote_verified = False
                    break

        # 5. Entity / Subject match
        claim_entities = self._extract_key_entities(claim_text)
        entity_match = True
        if claim_entities:
            # At least one major entity should be in source text
            entity_match = any(e.lower() in source_text for e in claim_entities)

        # 6. Claim support check
        c_words = set(re.findall(r"\w{4,}", claim_text.lower()))
        s_words = set(re.findall(r"\w{4,}", source_text))
        overlap = len(c_words.intersection(s_words))
        claim_supported = overlap >= max(1, len(c_words) * 0.35)

        # 7. Overall status determination
        if not quote_verified:
            return CitationValidation(
                citation_id=citation_id,
                claim_id=claim_id,
                source_id=source_id,
                passage_verified=passage_verified,
                entity_match=entity_match,
                claim_supported=False,
                citation_status=CitationStatus.INVALID,
                reason="Fabricated or altered quotation: Quoted text does not appear verbatim in retrieved source."
            )

        if not entity_match or not passage_verified:
            return CitationValidation(
                citation_id=citation_id,
                claim_id=claim_id,
                source_id=source_id,
                passage_verified=passage_verified,
                entity_match=entity_match,
                claim_supported=claim_supported,
                citation_status=CitationStatus.INVALID,
                reason="Cited source does not discuss the entity or passage referenced in the claim."
            )

        if not claim_supported:
            return CitationValidation(
                citation_id=citation_id,
                claim_id=claim_id,
                source_id=source_id,
                passage_verified=passage_verified,
                entity_match=entity_match,
                claim_supported=False,
                citation_status=CitationStatus.PARTIALLY_VALID,
                reason="Source discusses the entity but lacks sufficient evidence to substantiate the specific claim."
            )

        return CitationValidation(
            citation_id=citation_id,
            claim_id=claim_id,
            source_id=source_id,
            passage_verified=True,
            entity_match=True,
            claim_supported=True,
            citation_status=CitationStatus.VALID,
            reason="Retrieved source and passage directly substantiate the associated claim."
        )

    def validate_all(self, run: ResearchRun) -> List[CitationValidation]:
        validations = []
        cit_counter = 1
        for ev in run.evidence_records.values():
            sids = ev.source_ids or ([ev.source_id] if ev.source_id else [])
            for sid in sids:
                cid = f"CIT_{cit_counter:03d}"
                cit_counter += 1
                v = self.validate_citation(
                    citation_id=cid,
                    claim_id=ev.claim_id,
                    claim_text=ev.claim_text,
                    source_id=sid,
                    run=run,
                    supporting_excerpt=ev.supporting_excerpt or (ev.supporting_excerpts[0] if ev.supporting_excerpts else "")
                )
                validations.append(v)
                run.citation_validations[cid] = v
                run.citation_validations[ev.claim_id] = v
        return validations

    @staticmethod
    def _extract_key_entities(text: str) -> List[str]:
        # Extract capitalized multi-word sequences or alphanumeric model codes (e.g. Realme 13 Pro+, iPhone 16, NIST)
        entities = re.findall(r"\b[A-Z][a-zA-Z0-9\+\-]+(?:\s+[A-Z0-9\+\-]+)*\b", text)
        return [e for e in entities if len(e) > 2 and e.lower() not in {"the", "this", "what", "which", "and"}]
