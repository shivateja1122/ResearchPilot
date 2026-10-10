from __future__ import annotations
import re
import os
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, Tuple

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ERROR_PATTERNS = [
    r"warning:\s*target url returned error 40[0-9]",
    r"warning:\s*target url returned error 50[0-9]",
    r"\baccess denied\b",
    r"you don't have permission to access",
    r"oops,?\s*something went wrong",
    r"\b403 forbidden\b",
    r"\battention required!?\s*\|\s*cloudflare\b",
    r"please verify you are a human"
]

NOISE_LINE_PATTERNS = [
    r"^\[skip to (navigation|main content|right column)\]",
    r"^#+ (yahoo finance|trending tickers|notifications)",
    r"^\*?\s*!\[image \d+:.*\]",
    r"^\[selected edition\]",
    r"^(october prime day|prime big deal days|gift ideas|shopping guides)",
    r"^\[(home|news|finance|sports|entertainment|lifestyle|shopping|weather|video)\]\(",
    r"^\*\s*\[(us|politics|world|tech|science|markets|research|community)\]\(",
    r"(cookie (policy|consent|settings)|privacy policy|terms of (service|use)|all rights reserved)",
    r"(affiliate disclosure|when you purchase through links|may earn an affiliate commission)",
    r"^(\*|\-)?\s*\[?(phone finder|compare mobiles|add to compare|view photos|user reviews|read full review|check price)\]?",
    r"^(sign up|subscribe|newsletter|follow us on|advertisement|sponsored content)\b",
    r"^\[(compare|specs|deals|reviews|price in india|buy now)\]\(",
    r"^\*\s*\[\d+\.\s*$",
]


class PageExtractor:
    """
    Retrieves web page contents, strips boilerplate, metadata headers,
    and returns sanitized text excerpts with robust error and noise detection.
    """
    def __init__(self, timeout_seconds: int = 8, max_content_length: int = 10000):
        self.timeout = timeout_seconds
        self.max_content_length = max_content_length

    def extract(self, url: str) -> Dict[str, Any]:
        """
        Fetches the target URL and extracts clean textual content.
        Never throws unhandled exceptions; returns 'status' and 'error_message'.
        """
        if not url or not url.startswith(("http://", "https://")):
            return {
                "url": url,
                "title": "",
                "content": "",
                "status": "failed",
                "error_message": "Invalid or missing URL scheme."
            }

        # 1. Attempt Jina Reader if READER_API_KEY is configured
        reader_key = os.getenv("READER_API_KEY")
        if reader_key:
            try:
                jina_result = self._extract_jina(url, reader_key)
                if jina_result and jina_result.get("status") == "success":
                    return jina_result
            except Exception:
                pass

        # 2. Fallback to direct HTTP + BeautifulSoup
        try:
            response = requests.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=self.timeout,
                allow_redirects=True
            )
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "text/plain" not in content_type:
                return {
                    "url": url,
                    "title": "",
                    "content": "",
                    "status": "failed",
                    "error_message": f"Unsupported Content-Type: {content_type}"
                }

            html = response.text
            soup = BeautifulSoup(html, "html.parser")

            # Extract title
            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            elif soup.find("h1"):
                title = soup.find("h1").get_text(strip=True)

            # Strip non-content tags
            for unwanted in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form"]):
                unwanted.decompose()

            main_element = (
                soup.find("article") or
                soup.find("main") or
                soup.find("div", {"id": re.compile(r"content|main", re.I)}) or
                soup.body
            )
            raw_text = main_element.get_text(separator="\n", strip=True) if main_element else soup.get_text(separator="\n", strip=True)

            clean_title, clean_body, status, err = self._sanitize_and_validate(raw_text, title or "Web Article")
            return {
                "url": url,
                "title": clean_title,
                "content": clean_body,
                "status": status,
                "error_message": err
            }

        except requests.exceptions.Timeout:
            return {
                "url": url,
                "title": "",
                "content": "",
                "status": "failed",
                "error_message": f"Connection timed out after {self.timeout}s."
            }
        except requests.exceptions.HTTPError as e:
            return {
                "url": url,
                "title": "",
                "content": "",
                "status": "failed",
                "error_message": f"HTTP Error: {e.response.status_code if e.response else str(e)}"
            }
        except Exception as e:
            return {
                "url": url,
                "title": "",
                "content": "",
                "status": "failed",
                "error_message": f"Extraction error: {str(e)}"
            }

    def _extract_jina(self, url: str, api_key: str) -> Optional[Dict[str, Any]]:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/markdown",
            "X-Timeout": str(self.timeout)
        }
        resp = requests.get(jina_url, headers=headers, timeout=self.timeout)
        if resp.status_code == 200 and resp.text:
            raw_text = resp.text
            
            # Extract title if present in Jina header
            parsed_title = ""
            title_match = re.search(r"^Title:\s*(.+)$", raw_text, re.MULTILINE)
            if title_match:
                parsed_title = title_match.group(1).strip()

            clean_title, clean_body, status, err = self._sanitize_and_validate(raw_text, parsed_title or "Web Article")
            return {
                "url": url,
                "title": clean_title,
                "content": clean_body,
                "status": status,
                "error_message": err
            }
        return None

    def _sanitize_and_validate(self, raw_text: str, default_title: str) -> Tuple[str, str, str, Optional[str]]:
        """
        Strips Jina metadata headers, detects 403/Forbidden error pages,
        and removes boilerplate navigation noise.
        """
        if not raw_text or len(raw_text.strip()) < 40:
            return default_title, "", "failed", "Empty or negligible body content."

        first_chunk = raw_text[:800].lower()
        for err_pat in ERROR_PATTERNS:
            if re.search(err_pat, first_chunk):
                return default_title, "", "failed", "Page returned error/access denied (e.g., 403 Forbidden or captcha)."

        clean_lines = []
        in_content = False

        for line in raw_text.splitlines():
            s_line = line.strip()
            if not s_line:
                continue

            # Strip Jina Reader header block
            if re.match(r"^(Title:|URL Source:|Published Time:|Warning:)\s*", s_line):
                continue
            if s_line == "Markdown Content:":
                in_content = True
                continue

            # Check noise line patterns
            if any(re.search(pat, s_line, re.IGNORECASE) for pat in NOISE_LINE_PATTERNS):
                continue

            # Skip table separator lines e.g. |---|---| or |:---|:---|
            if re.match(r"^\|?[\s\-:|]+\|?$", s_line) and "-" in s_line:
                continue

            # Skip lines that are just dividers, ticker price changes, or empty list numbering
            if re.match(r"^[-=_*~]{3,}$", s_line):
                continue
            if re.match(r"^[A-Z]{2,5}\s+\d+\.\d+\s+\([+-]?\d+\.\d+%\)$", s_line):
                continue
            if re.match(r"^\*?\s*\[?\d+\.\]?\s*$", s_line):
                continue

            # Convert markdown links [Anchor Text](http...) to just Anchor Text
            s_line = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s_line)

            # Convert markdown table rows into clean key-value text lines
            if s_line.startswith("|") and s_line.endswith("|"):
                cols = [c.strip() for c in s_line.strip("|").split("|") if c.strip()]
                if cols:
                    s_line = " — ".join(cols)

            # Strip dangling orphan brackets from broken links/buttons
            s_line = re.sub(r"\[(view photos|add to compare|compare|read more|buy now)\]", "", s_line, flags=re.IGNORECASE).strip()

            # Keep substantive lines
            if len(s_line) > 25 or s_line.startswith("#"):
                clean_lines.append(s_line)

        clean_body = "\n\n".join(clean_lines).strip()

        # Final sanity check: if the remaining body is too short or lacks substantive sentences
        if len(clean_body) < 80:
            return default_title, "", "failed", "Content was mostly navigation or boilerplate."

        if len(clean_body) > self.max_content_length:
            clean_body = clean_body[:self.max_content_length] + "\n...[truncated for length]"

        return default_title, clean_body, "success", None
