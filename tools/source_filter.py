from __future__ import annotations
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Tuple, Optional
from models.schemas import QueryIntent, ResearchQuestion, Source


class SourceFilter:
    """
    Strict source relevance filter that evaluates retrieved sources against BOTH
    the overall QueryIntent and the specific ResearchQuestion.
    Rejects off-topic, promotional, or domain-mismatched sources with explicit reasons.
    """
    HIGH_CREDIBILITY_DOMAINS = {
        # Academic & Gov
        "nih.gov", "ncbi.nlm.nih.gov", "cdc.gov", "who.int", "fda.gov", "nist.gov",
        "nature.com", "science.org", "sciencedirect.com", "nejm.org", "thelancet.com",
        "ieee.org", "acm.org", "arxiv.org", "biorxiv.org", "medrxiv.org",
        "mit.edu", "stanford.edu", "harvard.edu", "ox.ac.uk", "cam.ac.uk",
        # Established Tech & Review Publications
        "gsmarena.com", "91mobiles.com", "smartprix.com", "gadgets360.com", "androidcentral.com",
        "androidauthority.com", "theverge.com", "techradar.com", "wired.com", "tomsguide.com",
        "tomshardware.com", "anandtech.com", "notebookcheck.net", "moneycontrol.com", "digit.in",
        "beebom.com", "xda-developers.com", "cnet.com", "pcmag.com",
        # Business & News
        "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "brookings.edu", "pewresearch.org"
    }

    LOW_CREDIBILITY_DOMAINS = {
        "reddit.com", "quora.com", "pinterest.com", "facebook.com", "instagram.com",
        "twitter.com", "x.com", "tiktok.com", "buzzfeed.com", "stocktitan.net"
    }

    OFF_TOPIC_NEGATIVE_PATTERNS = {
        "smartphones": [
            r"\belectric vehicle\b", r"\bev battery\b", r"\bcharging station\b", r"\bfleet\b",
            r"\bautomotive\b", r"\bads-tec\b", r"\bgeotab\b", r"\bgrid capacity\b", r"\bcar battery\b",
            r"\bstock quote\b", r"\bwall street\b", r"\bnasdaq:\s*[a-z]{3,5}\b"
        ],
        "laptops": [
            r"\belectric vehicle\b", r"\bcar battery\b", r"\bsmartphone camera\b", r"\bstock quote\b"
        ],
        "healthcare_ai": [
            r"\bcelebrity\b", r"\biphone case\b", r"\bmovie review\b", r"\bgaming rig\b"
        ],
        "cryptography": [
            r"\bmemecoin\b", r"\bbitcoin pump\b", r"\bcrypto casino\b"
        ]
    }

    @staticmethod
    def get_domain(url: str) -> str:
        try:
            domain = urlparse(url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    @classmethod
    def evaluate_credibility(cls, url: str) -> Tuple[str, float]:
        domain = cls.get_domain(url)
        if not domain:
            return ("unknown", 0.4)

        if domain.endswith(".gov") or domain.endswith(".edu") or domain.endswith(".mil"):
            return ("strong", 0.95)

        for high in cls.HIGH_CREDIBILITY_DOMAINS:
            if domain == high or domain.endswith("." + high):
                return ("strong", 0.90)

        for low in cls.LOW_CREDIBILITY_DOMAINS:
            if domain == low or domain.endswith("." + low):
                return ("weak", 0.20)

        return ("standard", 0.65)

    @classmethod
    def evaluate_relevance(
        cls,
        title: str,
        snippet: str,
        url: str,
        intent: Optional[QueryIntent] = None,
        question: Optional[ResearchQuestion] = None,
        threshold: float = 65.0
    ) -> Tuple[bool, float, str, Optional[str]]:
        """
        Evaluates source against QueryIntent and ResearchQuestion.
        Returns (accepted: bool, relevance_score: float, credibility: str, rejection_reason: Optional[str]).
        """
        cred_tier, cred_score = cls.evaluate_credibility(url)
        text_sample = f"{title} {snippet}".lower()
        domain = cls.get_domain(url)

        # 1. Negative domain / off-topic topic checks
        if intent and intent.domain in cls.OFF_TOPIC_NEGATIVE_PATTERNS:
            for pat in cls.OFF_TOPIC_NEGATIVE_PATTERNS[intent.domain]:
                if re.search(pat, text_sample):
                    return (
                        False,
                        15.0,
                        cred_tier,
                        f"Off-topic negative filter match ('{pat}'): Source discusses unrelated domain ({pat}) rather than {intent.domain}."
                    )

        # Check explicit excluded topics from query intent
        if intent and intent.excluded_topics:
            for excl in intent.excluded_topics:
                if excl.lower() in text_sample and len(excl) > 3:
                    return (
                        False,
                        20.0,
                        cred_tier,
                        f"Matched excluded topic ('{excl}'): Source content conflicts with inquiry boundaries."
                    )

        # 2. Base score starting from domain credibility
        score = cred_score * 40.0  # max 40 pts

        # 3. Topic match with QueryIntent (max 35 pts)
        if intent:
            topic_words = set(re.findall(r"\w{4,}", intent.topic.lower()))
            overlap_topic = sum(1 for w in topic_words if w in text_sample)
            if topic_words:
                score += min(35.0, (overlap_topic / len(topic_words)) * 35.0)

            # Bonus for primary criteria match
            for crit in intent.primary_criteria:
                crit_words = re.findall(r"\w{4,}", crit.lower())
                if any(cw in text_sample for cw in crit_words):
                    score += 5.0
                    break

            # Geographic match bonus
            if intent.geographic_scope and intent.geographic_scope.lower() in text_sample:
                score += 5.0
        else:
            score += 20.0

        # 4. Question match with specific ResearchQuestion (max 20 pts)
        if question:
            q_words = set(re.findall(r"\w{4,}", question.question_text.lower()))
            overlap_q = sum(1 for w in q_words if w in text_sample)
            if q_words:
                score += min(20.0, (overlap_q / len(q_words)) * 20.0)
        else:
            score += 15.0

        # Cap score at 100
        score = min(100.0, round(score, 1))

        # Check threshold
        if score >= threshold:
            return (True, score, cred_tier, None)
        else:
            reason = f"Low relevance score ({score}/{threshold}): Snippet lacks sufficient topical overlap with research criteria."
            return (False, score, cred_tier, reason)

    @classmethod
    def filter_and_rank(
        cls,
        search_results: List[Dict[str, Any]],
        intent: Optional[QueryIntent] = None,
        question: Optional[ResearchQuestion] = None,
        max_sources: int = 4,
        threshold: float = 60.0
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Filters results. Returns (accepted_sources, rejected_sources).
        """
        seen_urls = set()
        accepted = []
        rejected = []

        for item in search_results:
            url = item.get("url") or item.get("href") or ""
            if not url or not url.startswith(("http://", "https://")):
                continue

            clean_url = url.split("?")[0].rstrip("/").lower()
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            title = item.get("title", "").strip()
            snippet = item.get("snippet") or item.get("body") or ""

            is_acc, score, cred, rej_reason = cls.evaluate_relevance(
                title=title,
                snippet=snippet,
                url=url,
                intent=intent,
                question=question,
                threshold=threshold
            )

            record = {
                "title": title or "Source Reference",
                "url": url,
                "snippet": snippet,
                "relevance_score": score,
                "credibility_assessment": cred,
                "accepted": is_acc,
                "rejection_reason": rej_reason
            }

            if is_acc:
                accepted.append(record)
            else:
                rejected.append(record)

        # Rank accepted by relevance score descending
        accepted.sort(key=lambda x: x["relevance_score"], reverse=True)
        return (accepted[:max_sources], rejected)
