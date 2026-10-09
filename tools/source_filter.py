from __future__ import annotations
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Tuple


class SourceFilter:
    """
    Filters, deduplicates, and assesses the domain credibility of retrieved sources.
    """
    HIGH_CREDIBILITY_DOMAINS = {
        "nih.gov", "ncbi.nlm.nih.gov", "cdc.gov", "who.int", "fda.gov",
        "nature.com", "science.org", "sciencedirect.com", "nejm.org", "thelancet.com",
        "ieee.org", "acm.org", "arxiv.org", "biorxiv.org", "medrxiv.org",
        "mit.edu", "stanford.edu", "harvard.edu", "ox.ac.uk", "cam.ac.uk",
        "mckinsey.com", "gartner.com", "reuters.com", "bloomberg.com", "ft.com",
        "brookings.edu", "pewresearch.org", "oecd.org"
    }

    LOW_CREDIBILITY_DOMAINS = {
        "reddit.com", "quora.com", "pinterest.com", "facebook.com", "instagram.com",
        "twitter.com", "x.com", "tiktok.com", "buzzfeed.com"
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
        """
        Returns (tier, score between 0.0 and 1.0)
        Tiers: 'high', 'academic_gov', 'reputable_industry', 'standard', 'low'
        """
        domain = cls.get_domain(url)
        if not domain:
            return ("unknown", 0.3)

        if domain.endswith(".gov") or domain.endswith(".edu") or domain.endswith(".mil"):
            return ("academic_gov", 0.95)

        for high in cls.HIGH_CREDIBILITY_DOMAINS:
            if domain == high or domain.endswith("." + high):
                return ("high", 0.9)

        for low in cls.LOW_CREDIBILITY_DOMAINS:
            if domain == low or domain.endswith("." + low):
                return ("low", 0.2)

        return ("standard", 0.6)

    @classmethod
    def filter_and_rank(cls, search_results: List[Dict[str, Any]], max_sources: int = 5) -> List[Dict[str, Any]]:
        """
        Deduplicates results by normalized URL, filters out low quality/social sites if alternatives exist,
        and ranks by credibility score.
        """
        seen_urls = set()
        candidates = []

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
            tier, score = cls.evaluate_credibility(url)

            # Demote results with empty title and snippet
            if not title and not snippet:
                continue

            candidates.append({
                "title": title or "Source Reference",
                "url": url,
                "snippet": snippet,
                "tier": tier,
                "credibility_score": score
            })

        # Sort by credibility score descending, while keeping high relevance
        candidates.sort(key=lambda x: x["credibility_score"], reverse=True)
        return candidates[:max_sources]
