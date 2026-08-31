"""Search engine: DuckDuckGo via ddgs + page fetch.

Researcher's deterministic legs. Every failure degrades gracefully
(empty results or skipped page) instead of crashing the pipeline.
"""
import re
import time

import httpx
from ddgs import DDGS

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")


def _strip_html(raw: str, limit: int = 3000) -> str:
    raw = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"&nbsp;", " ", raw)
    raw = re.sub(r"&amp;", "&", raw)
    raw = re.sub(r"&lt;", "<", raw)
    raw = re.sub(r"&gt;", ">", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:limit]


def search(query: str, max_results: int = 5, retries: int = 2) -> list[dict]:
    """Return [{title, href, body}] from DuckDuckGo. Never raises."""
    for attempt in range(retries + 1):
        try:
            out = list(DDGS().text(query, max_results=max_results))
            results = []
            for item in out:
                href = item.get("href") or ""
                if href.startswith("//"):
                    href = "https:" + href
                results.append({
                    "title": (item.get("title") or "").strip(),
                    "href": href,
                    "body": (item.get("body") or "").strip(),
                })
            return results
        except Exception:
            if attempt >= retries:
                return []
            time.sleep(1.5 * (attempt + 1))
    return []


def fetch_page(url: str, timeout: float = 12.0, limit: int = 2500) -> str:
    """Fetch one page as plain text. Never raises - returns '' on failure."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as client:
            resp = client.get(url)
        if resp.status_code != 200 or not resp.text:
            return ""
        return _strip_html(resp.text, limit)
    except Exception:
        return ""


def research_notes(topic: str) -> str:
    """Full deterministic research leg: search + fetch top pages -> raw notes."""
    results = search(topic, max_results=5)
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']} - {r['href']}")
        if r["body"]:
            lines.append(f"   snippet: {r['body']}")
        if i <= 3:  # fetch body for top 3 only (cost/robustness balance)
            text = fetch_page(r["href"])
            if text:
                lines.append(f"   excerpt: {text[:600]}")
    return "\n".join(lines) if lines else f"No search results found for topic: {topic}"
