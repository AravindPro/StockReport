from functools import lru_cache
from typing import Optional
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

try:
    from langchain_core.tools import tool
except ImportError:
    from langchain.tools import tool


@lru_cache(maxsize=32)
def _fetch_page_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8", errors="ignore")


@tool
def fetch_webpage(url: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """Fetch the visible text from a webpage URL, optionally paginated by line range."""
    try:
        html = _fetch_page_html(url)
    except Exception as exc:  # pragma: no cover
        return f"Error fetching webpage: {exc}"

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = "\n".join(line.strip() for line in soup.get_text("\n", strip=True).splitlines() if line.strip())
    if not text:
        return "No readable text found."

    lines = text.splitlines()
    if not lines:
        return "No readable text found."

    start = max(1, start_line or 1) - 1
    end = start+6000 if end_line is None else min(len(lines), max(1, end_line))

    if start >= len(lines):
        return "No content in the requested line range."
    if end <= start:
        return "No content in the requested line range."

    paged = "\n".join(lines[start:end])
    if start > 0:
        paged = "-----truncated-----\n" + paged
    if end < len(lines):
        paged = paged + "\n-----truncated-----"
    return paged if paged else "No content in the requested line range."

