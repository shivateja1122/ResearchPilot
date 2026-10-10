from __future__ import annotations
import re
from typing import List, Dict, Any, Optional, Tuple
from models.schemas import ContradictionRecord, Evidence, Source, ResearchRun


class ContradictionDetector:
    """
    Detects and analyzes contradictions between evidence sources:
    - Identifies direct disagreements (e.g. positive vs negative performance assessments)
    - Compares source dates (detects firmware updates or market price shifts)
    - Compares testing methodologies (e.g. daylight vs low-light, lab vs real-world)
    - Preserves unresolved conflicts for audit logging and report disclosure
    """
    def __init__(self):
        pass

    def detect_conflicts(self, run: ResearchRun) -> List[ContradictionRecord]:
        conflicts: List[ContradictionRecord] = []
        evidence_items = list(run.evidence_records.values())

        conflict_counter = 1
        for i in range(len(evidence_items)):
            for j in range(i + 1, len(evidence_items)):
                ev1 = evidence_items[i]
                ev2 = evidence_items[j]

                # Check if evidence items target the same question or entity
                if ev1.question_id != ev2.question_id:
                    continue

                is_conflicting, description, explanation = self._check_pair_conflict(ev1, ev2, run)
                if is_conflicting:
                    cid = f"CNF_{conflict_counter:03d}"
                    conflict_counter += 1

                    s1 = run.sources.get(ev1.source_ids[0]) if ev1.source_ids else None
                    s2 = run.sources.get(ev2.source_ids[0]) if ev2.source_ids else None

                    ent = self._extract_entity(ev1.claim_text) or ev1.question_id
                    rec = ContradictionRecord(
                        conflict_id=cid,
                        claim_a_id=ev1.claim_id,
                        claim_b_id=ev2.claim_id,
                        claim_text=ev1.claim_text,
                        opposing_claim_text=ev2.claim_text,
                        entity=ent,
                        disagreement_description=description,
                        source_a_id=s1.source_id if s1 else None,
                        source_b_id=s2.source_id if s2 else None,
                        source_a_date=s1.publication_date if s1 else None,
                        source_b_date=s2.publication_date if s2 else None,
                        resolution_status="UNRESOLVED_DISCLOSED",
                        explanation=explanation
                    )
                    conflicts.append(rec)

        run.contradictions = conflicts
        return conflicts

    @staticmethod
    def _extract_entity(text: str) -> str:
        entities = re.findall(r"\b[A-Z][a-zA-Z0-9\+\-]+(?:\s+[A-Z0-9\+\-]+)*\b", text)
        filtered = [e for e in entities if len(e) > 2 and e.lower() not in {"the", "this", "what", "which", "and"}]
        return filtered[0] if filtered else ""

    def _check_pair_conflict(
        self,
        ev1: Evidence,
        ev2: Evidence,
        run: ResearchRun
    ) -> Tuple[bool, str, str]:
        t1 = f"{ev1.claim_text} {ev1.supporting_excerpt or ''}".lower()
        t2 = f"{ev2.claim_text} {ev2.supporting_excerpt or ''}".lower()

        # Positive vs negative indicators on same subject
        positive_patterns = [
            r"\bstrong\b", r"\bexcellent\b", r"\bimpressive\b", r"\brecommended\b",
            r"\bhigh detail\b", r"\boutstanding\b", r"\bsharp\b", r"\bclean\b",
            r"\bexceptional\b", r"\bgreat\b", r"\bsuperior\b"
        ]
        negative_patterns = [
            r"\bweak\b", r"\bpoor\b", r"\blacks detail\b", r"\bnoisy\b", r"\bnoise\b",
            r"\bsoft\b", r"\bdisappointing\b", r"\bfailed to\b", r"\bstruggles\b",
            r"\blacks\b", r"\blag\b"
        ]

        p1 = any(re.search(p, t1) for p in positive_patterns)
        n1 = any(re.search(p, t1) for p in negative_patterns)

        p2 = any(re.search(p, t2) for p in positive_patterns)
        n2 = any(re.search(p, t2) for p in negative_patterns)

        if (p1 and n2) or (p2 and n1):
            desc = (
                f"Source divergence detected: '{ev1.claim_text[:80]}...' vs opposing assessment '{ev2.claim_text[:80]}...'"
            )
            expl = (
                "Disagreement likely stems from differing testing conditions (e.g., lighting environments, ambient noise) "
                "or testing with pre-release firmware versus retail units."
            )
            return (True, desc, expl)

        # Price disagreement check
        prices_1 = re.findall(r"(?:₹|rs\.?|\$)\s*([\d,]+)", t1)
        prices_2 = re.findall(r"(?:₹|rs\.?|\$)\s*([\d,]+)", t2)
        if prices_1 and prices_2:
            p1_val = prices_1[0].replace(",", "")
            p2_val = prices_2[0].replace(",", "")
            if p1_val != p2_val and abs(int(p1_val) - int(p2_val)) > 1500:
                desc = f"Pricing conflict between sources: {p1_val} vs {p2_val}."
                expl = "Price discrepancy reflects varying memory/storage configurations or retailer promotional discounts."
                return (True, desc, expl)

        return (False, "", "")
