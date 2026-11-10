from functools import lru_cache
from typing import Optional, Literal
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import yfinance as yf
from bs4 import BeautifulSoup
from markdownify import markdownify as md

try:
    from langchain_core.tools import BaseTool, tool
except ImportError:
    from langchain.tools import BaseTool, tool

import logging

from langchain_mcp_adapters.client import MultiServerMCPClient



@lru_cache(maxsize=32)
def _fetch_page_html(url: str) -> str:
    """Download and cache the raw HTML for a webpage.

    Args:
        url (str): The fully qualified HTTP or HTTPS URL to download.

    Returns:
        str: The response body decoded as UTF-8. Invalid byte sequences are
            replaced so callers always receive text.
    """
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8", errors="ignore")


def html_to_markdown(
    html: str,
    source_url: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
) -> str:
    """Convert HTML into readable Markdown and return an optional line range.

    Args:
        html (str): Raw HTML content to clean and convert.
        source_url (str): URL of the fetched page. Relative links are resolved
            against this URL before conversion to Markdown.
        start_line (int): One-based first Markdown line to return. Defaults to 1.
        end_line (Optional[int]): One-based final Markdown line to return,
            inclusive. When omitted, returns up to 6,000 lines from
            ``start_line``.

    Returns:
        str: Cleaned Markdown content, an optional truncated line range, or a
        human-readable message when no content or no requested lines exist.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for tag in soup.find_all(["a", "img"]):
        attribute = "href" if tag.name == "a" else "src"
        value = tag.get(attribute)
        if value:
            tag[attribute] = urljoin(source_url, value)

    markdown = md(str(soup), heading_style="ATX")
    cleaned_lines = []
    previous_blank = False
    for line in markdown.splitlines():
        line = line.rstrip()
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        cleaned_lines.append(line)
        previous_blank = is_blank

    markdown = "\n".join(cleaned_lines).strip()
    if not markdown:
        return "No readable content found."

    lines = markdown.splitlines()
    start = max(1, start_line or 1) - 1
    end = start + 6000 if end_line is None else min(len(lines), max(1, end_line))

    if start >= len(lines) or end <= start:
        return "No content in the requested line range."

    result = "\n".join(lines[start:end])
    if start > 0:
        result = "-----truncated-----\n" + result
    if end < len(lines):
        result += "\n-----truncated-----"
    return result


@tool
def fetch_webpage(url: str, start_line: int = 1, end_line: Optional[int] = None, return_format: Literal['html', 'text'] = 'text') -> str:
    """Fetch raw HTML or readable, line-paginated text from a webpage.

    Args:
        url (str): The fully qualified HTTP or HTTPS URL to fetch.
        start_line (int): One-based first line of extracted text to return.
            Defaults to 1. Ignored when ``return_format`` is ``"html"``.
        end_line (Optional[int]): One-based final line of extracted text to
            return, inclusive. When omitted, returns up to 6,000 lines from
            ``start_line``. Ignored when ``return_format`` is ``"html"``.
        return_format (Literal["html", "text"]): ``"text"`` removes scripts,
            styles, and markup, then converts the page to Markdown; ``"html"``
            returns the raw downloaded HTML.
            Defaults to ``"text"``.

    Returns:
        str: The requested HTML or readable Markdown. Markdown may include a
            ``-----truncated-----`` marker when pagination omits content. A
            human-readable error message is returned if the request fails or
            the requested range is invalid.
    """
    if return_format not in ['html', 'text']:
        return f"Error: {return_format!r} is not a valid return format."
    try:
        html = _fetch_page_html(url)
    except Exception as exc:  # pragma: no cover
        logging.warning("Webpage fetch failed")
        return f"Error fetching webpage: {exc}"

    if return_format == 'html':
        return html

    return html_to_markdown(html, url, start_line, end_line)

@tool
def fetch_yahoo_finance_news(ticker: str) -> str:
    """Fetch combined Yahoo Finance latest news and press releases
    for a stock ticker, formatted as Markdown with clickable links.
    """
    ticker = ticker.strip().upper()

    urls = {
        "Latest News": (
            f"https://finance.yahoo.com/quote/{ticker}/latest-news/"
        ),
        "Press Releases": (
            f"https://finance.yahoo.com/quote/{ticker}/press-releases/"
        ),
    }

    output = []

    try:
        for section, url in urls.items():
            html = _fetch_page_html(url)

            soup = BeautifulSoup(html, "html.parser")

            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()

            markdown = md(
                str(soup),
                heading_style="ATX",
                base_url=url,
            ).strip()

            output.append(f"# {section}\n\n{markdown}")

        return f"## Ticker {ticker}\n\n---\n\n".join(output)

    except Exception as exc:
        return f"Error fetching Yahoo Finance news for {ticker}: {exc}"

@tool
def get_stock_ticker(company_name: str) -> str:
    """Find the Yahoo Finance ticker symbol for a company.

    Args:
        company_name (str): Short or commonly used company name, such as
            "Apple", "Microsoft", or "Reliance".

    Returns:
        str: The ticker symbol of the first Yahoo Finance search result.
    """
    try:
        results = yf.Search(company_name.strip())

        if not results.quotes:
            return f"No ticker found for {company_name}."

        quote = results.quotes[0]
        ticker = quote.get("symbol")

        if not ticker:
            return f"No ticker found for {company_name}."

        return ticker

    except Exception as exc:
        logging.warning("Ticker lookup failed for %s: %s", company_name, exc)
        return f"Error fetching ticker for {company_name}: {exc}"

async def get_groww_mcp_tools() -> list[BaseTool]:
    """Connect to Groww's remote MCP server and load its LangChain tools.

    This function starts ``mcp-remote`` through ``npx`` using the configured
    stdio transport, which may open an authentication flow if Groww requires
    login.

    Returns:
        list[BaseTool]: The LangChain-compatible tool instances exposed by the
        Groww MCP server. These can be appended to an agent's ``tools`` list.
    """
    client = MultiServerMCPClient({
        "groww": {
            "transport": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "mcp-remote@0.1.35",
                "https://mcp.groww.in/mcp",
                "52155",
            ],
        }
    })

    logging.info("Connecting to Groww MCP server")
    logging.info("Groww authentication may open a browser flow")

    tools = await client.get_tools()

    logging.info("Loaded %d Groww MCP tools", len(tools))
    for tool in tools:
        logging.debug("Groww MCP tool available: %s", tool.name)

    return tools