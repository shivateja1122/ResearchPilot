from __future__ import annotations
import re
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class PageExtractor:
    """
    Retrieves web page contents, strips boilerplate and markup,
    and returns sanitized text excerpts with robust error handling.
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
        import os
        reader_key = os.getenv("READER_API_KEY")
        if reader_key:
            try:
                jina_result = self._extract_jina(url, reader_key)
                if jina_result and jina_result.get("status") == "success":
                    return jina_result
            except Exception:
                pass

        try:
            response = requests.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=self.timeout,
                allow_redirects=True
            )
            response.raise_for_status()

            # Verify content type is HTML or text
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

            # Prefer main article or main content tags if present
            main_element = soup.find("article") or soup.find("main") or soup.find("div", {"id": re.compile(r"content|main", re.I)}) or soup.body
            
            raw_text = main_element.get_text(separator="\n", strip=True) if main_element else soup.get_text(separator="\n", strip=True)

            # Clean and normalize whitespace
            lines = [line.strip() for line in raw_text.splitlines() if len(line.strip()) > 20]
            clean_text = "\n".join(lines)

            # Truncate to maximum length safely
            if len(clean_text) > self.max_content_length:
                clean_text = clean_text[:self.max_content_length] + "\n...[truncated for length]"

            if not clean_text:
                return {
                    "url": url,
                    "title": title or "Untitled Page",
                    "content": "",
                    "status": "failed",
                    "error_message": "Extracted page contained no substantial body text."
                }

            return {
                "url": url,
                "title": title or "Web Article",
                "content": clean_text,
                "status": "success",
                "error_message": None
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
        except requests.exceptions.RequestException as e:
            return {
                "url": url,
                "title": "",
                "content": "",
                "status": "failed",
                "error_message": f"Network error: {str(e)}"
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
            text = resp.text
            # Extract title if present in Jina output (e.g. Title: ...)
            title = ""
            title_match = re.search(r"Title:\s*(.+)", text)
            if title_match:
                title = title_match.group(1).strip()
            
            clean_content = text
            if len(clean_content) > self.max_content_length:
                clean_content = clean_content[:self.max_content_length] + "\n...[truncated for length]"

            return {
                "url": url,
                "title": title or "Web Article",
                "content": clean_content,
                "status": "success",
                "error_message": None
            }
        return None
