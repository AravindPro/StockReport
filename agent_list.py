from __future__ import annotations

from datetime import datetime
import logging
from agent import build_agent
from custom_tools import fetch_yahoo_finance_news, get_stock_ticker
from logging_config import configure_logging

configure_logging()

def extract_final_text(response: dict) -> str:
    """Return the last non-empty message produced by the LangChain agent."""
    for message in reversed(response.get("messages", [])):
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
    raise RuntimeError("The agent returned no text to forward.")


def generate_report() -> str:
    prompt = f"Generate the stock report for today {datetime.now().strftime('%Y-%m-%d')} under 1000 words"
    agent = build_agent(filename="stockreport.md")
    response = agent.invoke({"messages": [("user", prompt)]})
    return extract_final_text(response)

def run_stock_agent_tool(description: str):
    logging.info("Creating ticker-summary agent with Yahoo Finance news tool")
    agent = build_agent(
        filename="tickersummary.md",
        extra_tools=[fetch_yahoo_finance_news],
    )
    prompt = (
        f"Generate today's ticker summaries. {description}. "
        "Use the Yahoo Finance news tool to fetch context for every ticker, "
        "then summarize the key developments and cite source links."
    )
    logging.info("Starting ticker-summary agent for %s", description)
    logging.debug("Ticker-summary prompt: %s", prompt)

    messages = []
    for update in agent.stream(
        {"messages": [("user", prompt)]},
        stream_mode="updates",
    ):
        for node, data in update.items():
            logging.info("Agent step: %s", node)
            for message in data.get("messages", []):
                messages.append(message)
                if node == "tools" and type(message).__name__ == "ToolMessage":
                    logging.info(
                        "Agent executed tool: %s (id=%s)",
                        getattr(message, "name", "unknown"),
                        getattr(message, "tool_call_id", "unknown"),
                    )
                tool_calls = getattr(message, "tool_calls", None) or []
                for tool_call in tool_calls:
                    logging.info(
                        "Agent tool call: %s (id=%s)",
                        tool_call.get("name"),
                        tool_call.get("id"),
                    )
                    logging.debug("Agent tool arguments: %r", tool_call.get("args"))

                if type(message).__name__ != "ToolMessage" and getattr(message, "content", None):
                    content = getattr(message, "content")
                    logging.debug("Agent message content: %s", content)

    response = {"messages": messages}
    report = extract_final_text(response)
    logging.info("Ticker-summary agent completed (%d characters)", len(report))
    return report
