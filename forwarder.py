"""Custom SMTP email forwarder for agent-generated reports.

All configuration is supplied through environment variables so that mail
credentials never need to live in source control.  See ``.env.example`` for
the supported variables.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Mapping
import dotenv
from pathlib import Path
import json
import logging

dotenv.load_dotenv(Path(__file__).parent / ".env")


TELEGRAM_MESSAGE_LIMIT = 3900


def _utf16_length(text: str) -> int:
    """Count Telegram's UTF-16 code units, leaving room under its 4096 limit."""
    return len(text.encode("utf-16-le")) // 2


def _split_long_paragraph(paragraph: str, limit: int) -> list[str]:
    """Split an oversized paragraph at whitespace, preserving every character."""
    pieces: list[str] = []
    remaining = paragraph
    while _utf16_length(remaining) > limit:
        units = 0
        cut = 0
        for index, char in enumerate(remaining):
            char_units = _utf16_length(char)
            if units + char_units > limit:
                break
            units += char_units
            cut = index + 1

        boundary = remaining.rfind(" ", 0, cut)
        if boundary > 0:
            cut = boundary
        pieces.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    if remaining:
        pieces.append(remaining)
    return pieces


def _chunk_telegram_message(text: str, subject: str | None = None) -> list[str]:
    """Pack whole paragraphs into Telegram-sized messages where possible."""
    prefix = f"{subject}\n\n" if subject else ""
    chunks: list[str] = []
    current = prefix
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n")]

    for paragraph in paragraphs:
        if not paragraph:
            continue

        separator = "" if not current or current.endswith("\n\n") else "\n\n"
        candidate = f"{current}{separator}{paragraph}"
        if _utf16_length(candidate) <= TELEGRAM_MESSAGE_LIMIT:
            current = candidate
            continue

        # If adding a paragraph would overflow, send the accumulated content
        # first. The first chunk reserves space for its subject prefix.
        if current and not (prefix and current == prefix and not chunks):
            chunks.append(current)
            current = ""

        pieces = _split_long_paragraph(paragraph, TELEGRAM_MESSAGE_LIMIT)
        if prefix and not chunks and current == prefix and pieces:
            first_limit = TELEGRAM_MESSAGE_LIMIT - _utf16_length(prefix)
            if _utf16_length(pieces[0]) > first_limit:
                first_pieces = _split_long_paragraph(pieces.pop(0), first_limit)
                pieces = first_pieces + pieces
            current = prefix + pieces.pop(0)
            if pieces:
                chunks.append(current)
                chunks.extend(pieces[:-1])
                current = pieces[-1]
        elif pieces:
            chunks.extend(pieces[:-1])
            current = pieces[-1]
        elif not current:
            current = paragraph

    if current:
        chunks.append(current)
    return chunks



@dataclass(frozen=True)
class TelegramForwarder:
    """Send plain-text report messages to a Telegram chat via the Bot API."""

    bot_token: str
    chat_id: str
    base_url: str = "https://api.telegram.org"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "TelegramForwarder":
        """Build a forwarder from the TELEGRAM_* environment variables."""
        env = os.environ if environ is None else environ
        required = ("TELEGRAM_STOCK_BOT_API", "TELEGRAM_STOCK_BOT_CHAT_ID")
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise ValueError(f"Missing Telegram configuration: {', '.join(missing)}")

        return cls(
            bot_token=env["TELEGRAM_STOCK_BOT_API"],
            chat_id=env["TELEGRAM_STOCK_BOT_CHAT_ID"],
        )

    def get_chat_description(self):
        """Retrieves the description of a Telegram chat or channel.

        Args:
            token (str): Telegram Bot API token.
            chat_id (str | int): Unique identifier of the chat or channel.

        Returns:
            Optional[str]: Chat description if available, otherwise a message indicating
                that no description is set. Returns None if the
                API request fails.
        """
        url = f"https://api.telegram.org/bot{self.bot_token}/getChat"

        payload = json.dumps({"chat_id": self.chat_id}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            if data.get("ok"):
                chat_info = data.get("result", {})
                description = chat_info.get("description")

                return description

            return None

        except Exception as e:
            return None

    def forward(self, text: str, *, subject: str | None = None) -> None:
        """Send a report as plain text to Telegram."""
        if not text.strip():
            raise ValueError("Refusing to forward an empty report.")

        url = f"{self.base_url}/bot{self.bot_token}/sendMessage"
        chunks = _chunk_telegram_message(text, subject)
        for index, chunk in enumerate(chunks, start=1):
            payload: dict[str, str] = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
            }
            data = urllib.parse.urlencode(payload).encode("utf-8")
            request = urllib.request.Request(url, data=data, method="POST")

            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                logging.error(
                    "Telegram chunk %d/%d failed (HTTP %s): %s",
                    index,
                    len(chunks),
                    exc.code,
                    error_body,
                )
                raise
            except urllib.error.URLError as exc:
                logging.error(
                    "Could not connect to Telegram for chunk %d/%d: %s",
                    index,
                    len(chunks),
                    exc.reason,
                )
                raise

            if '"ok":true' not in body:
                logging.error(
                    "Telegram chunk %d/%d returned an unsuccessful response: %s",
                    index,
                    len(chunks),
                    body,
                )
                raise RuntimeError(f"Telegram API did not ok chunk {index}/{len(chunks)}: {body}")
            logging.info("Sent Telegram chunk %d/%d", index, len(chunks))

@dataclass(frozen=True)
class NotionForwarder:
    """Upload Markdown reports to a Notion page via the Notion API."""

    api_key: str
    parent_page_id: str
    base_url: str = "https://api.notion.com"
    notion_version: str = "2025-09-03"

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "NotionForwarder":
        """Build a forwarder from NOTION_* environment variables."""

        env = os.environ if environ is None else environ

        required = (
            "NOTION_API_KEY",
            "NOTION_STOCK_REPORTS_PAGE_ID",
        )

        missing = [name for name in required if not env.get(name)]

        if missing:
            raise ValueError(
                f"Missing Notion configuration: {', '.join(missing)}"
            )

        return cls(
            api_key=env["NOTION_API_KEY"],
            parent_page_id=env["NOTION_STOCK_REPORTS_PAGE_ID"],
        )

    def forward(
        self,
        text: str,
        title: str
    ) -> str:
        """Create a new Notion page containing the Markdown report."""

        if not text.strip():
            raise ValueError(
                "Refusing to forward an empty report."
            )


        payload = {
            "parent": {
                "page_id": self.parent_page_id,
            },
            "markdown": text,
            "properties": {
                "title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {
                                "content": title,
                            },
                        }
                    ]
                }
            },
        }

        data = json.dumps(payload).encode("utf-8")

        url = f"{self.base_url}/v1/pages"

        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Notion-Version": self.notion_version,
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:

                body = response.read().decode("utf-8")

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8")

            raise RuntimeError(
                f"Notion API error {exc.code}: {error_body}"
            ) from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Failed to connect to Notion API: {exc.reason}"
            ) from exc

        result = json.loads(body)

        if not result.get("id"):
            raise RuntimeError(
                f"Notion API returned an invalid response: {body}"
            )

        page_url = result.get("url")

        if not page_url:
            raise RuntimeError(
                f"Notion page URL missing from response: {body}"
            )

        return page_url
