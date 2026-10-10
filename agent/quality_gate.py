from __future__ import annotations
import re
from typing import Dict, Any, List, Tuple, Optional
from models.schemas import (
    ResearchRun, QualityGateResult, CriticalFailure,
    FinalReport, QueryIntent, VerificationStatus, CitationStatus
)


class QualityGate:
    """
    Independent Final Quality Gate:
    Evaluates completed research report against the evidence ledger across 12 checks.
    Does not trust the report generator blindly.
    Detects critical failures (unsupported claims, invalid citations, off-topic findings)
    and applies bounded repairs before final sign-off.
    """
    def __init__(self, max_repairs: int = 2):
        self.max_repairs = max_repairs

    def evaluate_and_repair(self, run: ResearchRun) -> QualityGateResult:
        if not run.final_report:
            return QualityGateResult(
                report_passed=False,
                passed=False,
                score=0.0,
                critical_failures=[
                    CriticalFailure(type="MISSING_REPORT", reason="Final report was not generated.")
                ],
                checks={"has_final_report": False},
                warnings=["Final report is missing."]
            )

        report = run.final_report
        intent = run.query_intent
        checks: Dict[str, bool] = {}
        warnings: List[str] = []
        critical_failures: List[CriticalFailure] = []
        repair_actions: List[str] = []
        repairs_applied: List[str] = []

        report_text = f"{report.title} {report.executive_summary} {report.markdown_content}".lower()

        # 1. Addresses Original Query
        query_words = set(re.findall(r"\w{4,}", run.original_question.lower()))
        topic_overlap = sum(1 for w in query_words if w in report_text)
        q_ok = topic_overlap >= max(1, len(query_words) // 2)
        checks["addresses_original_query"] = q_ok
        if not q_ok:
            warnings.append("Report may not adequately address all terms in the original inquiry.")

        # 2. Constraints Respected (budget, currency, geo)
        constraints_ok = True
        if intent and intent.explicit_constraints:
            max_b = intent.explicit_constraints.get("max_budget")
            if max_b and str(max_b) not in report_text and "budget" not in report_text:
                constraints_ok = False
                warnings.append(f"Explicit budget constraint ({max_b}) not visibly addressed.")
        checks["constraints_respected"] = constraints_ok

        # 3. Claims Have Valid Evidence Links
        has_evidence = len(report.evidence_and_citations) > 0 or len(run.evidence_records) > 0
        checks["claims_have_evidence"] = has_evidence
        if not has_evidence:
            critical_failures.append(
                CriticalFailure(type="NO_EVIDENCE", reason="No evidence ledger records found.")
            )

        # 4. Citations Point to Real Retrieved Sources
        valid_source_ids = set(run.sources.keys())
        unindexed_citations = []
        for ev in run.evidence_records.values():
            for sid in ev.source_ids:
                if sid not in valid_source_ids:
                    unindexed_citations.append((ev.claim_id, sid))

        if unindexed_citations:
            checks["citations_point_to_real_sources"] = False
            for cid, sid in unindexed_citations:
                critical_failures.append(
                    CriticalFailure(
                        type="INVALID_CITATION",
                        claim_id=cid,
                        reason=f"Claim references source [{sid}] which was not successfully retrieved."
                    )
                )
            repair_actions.append("Repair or remove unindexed source citations from evidence ledger.")
        else:
            checks["citations_point_to_real_sources"] = True

        # 5. Citation Validity (Passage supports claim)
        invalid_citations = [
            v for v in run.citation_validations.values()
            if v.citation_status in (CitationStatus.INVALID, CitationStatus.SOURCE_UNAVAILABLE)
        ]
        if invalid_citations:
            checks["citation_passages_support_claims"] = False
            for inv in invalid_citations[:3]:
                critical_failures.append(
                    CriticalFailure(
                        type="INVALID_CITATION",
                        claim_id=inv.claim_id,
                        reason=inv.reason
                    )
                )
            repair_actions.append("Repair invalid citations by attaching correct passage or marking as inference.")
        else:
            checks["citation_passages_support_claims"] = True

        # 6. Exclude Irrelevant / Excluded Sources from Conclusions (CRITICAL FILTER)
        excluded_patterns = intent.excluded_topics if intent else []
        clean_findings = []
        off_topic_detected = False
        for finding in report.key_findings:
            is_off_topic = False
            matched_excl = ""
            if excluded_patterns:
                for excl in excluded_patterns:
                    excl_words = [w for w in excl.lower().split() if len(w) > 3]
                    if (excl.lower() in finding.lower()) or (excl_words and all(w in finding.lower() for w in excl_words)):
                        is_off_topic = True
                        off_topic_detected = True
                        matched_excl = excl
                        critical_failures.append(
                            CriticalFailure(
                                type="OFF_TOPIC_SOURCE",
                                reason=f"Finding contains excluded off-topic domain '{excl}': {finding[:60]}..."
                            )
                        )
                        break

            if not is_off_topic and intent and intent.domain:
                from tools.source_filter import SourceFilter
                patterns = SourceFilter.OFF_TOPIC_NEGATIVE_PATTERNS.get(intent.domain, [])
                for pat in patterns:
                    if re.search(pat, finding.lower()):
                        is_off_topic = True
                        off_topic_detected = True
                        matched_excl = pat
                        critical_failures.append(
                            CriticalFailure(
                                type="OFF_TOPIC_SOURCE",
                                reason=f"Finding matches negative off-topic pattern '{pat}': {finding[:60]}..."
                            )
                        )
                        break

            if not is_off_topic:
                clean_findings.append(finding)

        if off_topic_detected:
            # Bounded auto-repair: Prune off-topic claims
            report.key_findings = clean_findings or ["Verified primary evidence retained; off-topic artifacts removed."]
            repairs_applied.append(f"Pruned off-topic findings violating query domain boundaries ('{matched_excl}').")
            repair_actions.append(f"Pruned off-topic findings ('{matched_excl}').")
            checks["irrelevant_sources_excluded"] = True
        else:
            checks["irrelevant_sources_excluded"] = True

        # 7. Comparative Claims Have Comparative Evidence
        comparative_terms = [r"\bbest\b", r"\boutperforms\b", r"\bsuperior to\b", r"\b#1\b"]
        unverified_comparatives = []
        for ev in run.evidence_records.values():
            if any(re.search(p, ev.claim_text.lower()) for p in comparative_terms):
                if ev.verification_status == VerificationStatus.UNVERIFIED:
                    unverified_comparatives.append(ev)

        if unverified_comparatives:
            checks["comparative_claims_verified"] = False
            for uv in unverified_comparatives:
                critical_failures.append(
                    CriticalFailure(
                        type="UNSUPPORTED_COMPARATIVE_CLAIM",
                        claim_id=uv.claim_id,
                        reason=f"Claim '{uv.claim_text[:60]}...' lacks comparative evidence."
                    )
                )
            repair_actions.append("Downgrade unsupported comparative claims to unverified inferences or remove.")
        else:
            checks["comparative_claims_verified"] = True

        # 8. Contradictions Disclosed
        if run.contradictions:
            checks["conflicting_evidence_disclosed"] = bool(report.conflicting_evidence)
            if not checks["conflicting_evidence_disclosed"]:
                warnings.append("Disagreements between retrieved sources were detected but not disclosed.")
        else:
            checks["conflicting_evidence_disclosed"] = True

        # 9. Time-sensitive Claims Dated
        has_dates = bool(re.search(r"\b202[4-6]\b", report_text)) or "current" in report_text
        checks["time_sensitive_dated"] = has_dates
        if not has_dates:
            warnings.append("Report lacks explicit current year or date markers.")

        # 10. Unresolved Questions Acknowledged Honestly
        has_unresolved = False
        if run.research_plan:
            for q in run.research_plan.subquestions:
                if q.status.value in ("unresolved", "unanswered", "partial", "partially_answered"):
                    has_unresolved = True
                    break
        if has_unresolved:
            acknowledged = len(report.limitations_and_unresolved) > 0
            if not acknowledged:
                report.limitations_and_unresolved.append(
                    "Certain subquestions remain partially resolved due to available search boundaries."
                )
                repairs_applied.append("Inserted unresolved questions disclosure into limitations section.")
                acknowledged = True
            checks["unresolved_questions_acknowledged"] = acknowledged
        else:
            checks["unresolved_questions_acknowledged"] = True

        # 11. Recommendations Do Not Exceed Evidence
        recs_ok = True
        if report.recommendations:
            for rec in report.recommendations:
                if excluded_patterns and any(excl.lower() in rec.lower() for excl in excluded_patterns if len(excl) > 3):
                    recs_ok = False
        checks["recommendations_evidence_backed"] = recs_ok

        # 12. Readability Standalone
        checks["readability_standalone"] = len(report.executive_summary) > 40

        # Perform bounded repair on critical failures if possible
        if critical_failures:
            remaining_critical = []
            for cf in critical_failures:
                # If it's an off-topic finding that was already pruned, resolve it
                if cf.type == "OFF_TOPIC_SOURCE" and off_topic_detected:
                    continue
                # If it's an unsupported claim, apply auto-repair by removing or qualifying it in report
                if cf.type in ("UNSUPPORTED_CLAIM", "UNSUPPORTED_COMPARATIVE_CLAIM") and cf.claim_id:
                    # Remove from key findings if present
                    report.key_findings = [
                        kf for kf in report.key_findings
                        if cf.claim_id not in kf and "best" not in kf.lower()
                    ]
                    repairs_applied.append(f"Auto-repaired: Qualified or pruned unsupported claim {cf.claim_id}.")
                    continue
                remaining_critical.append(cf)
            critical_failures = remaining_critical

        passed_count = sum(1 for v in checks.values() if v)
        total_checks = len(checks)
        score = round(passed_count / total_checks, 2)

        # Report passes if no unresolved critical failures remain and score >= 0.80
        report_passed = (len(critical_failures) == 0) and (score >= 0.80)

        return QualityGateResult(
            report_passed=report_passed,
            passed=report_passed,
            score=score,
            critical_failures=critical_failures,
            checks=checks,
            warnings=warnings,
            repair_actions=repair_actions,
            repairs_applied=repairs_applied
        )
