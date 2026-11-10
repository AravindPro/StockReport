"""Generate one stock-market report with the agent and email it.

Examples:
    python stockreport.py
    python stockreport.py --prompt "Summarise today's news for AAPL and MSFT"
    python stockreport.py --dry-run
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from agent import build_agent
from forwarder import NotionForwarder, TelegramForwarder
import logging
from agent_list import run_stock_agent_tool

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
    force=True,
)

DEFAULT_TICKERS = [
    "ATHERENERG.NS",
    "ETERNAL.NS",
    "TSLA",
    "NVDA",
    "CRWD",
    "ARM",
    "XRP-USD",
    "ETH-USD",
    "AMD",
    "CRWV",
    "AMZN",
    "AAPL",
    "GOOG",
    "META",
    "INTC",
    "EWZ", 
]
def main() -> None:
    # Load the local configuration before agent.py reads OPEN_ROUTER_API.
    load_dotenv(Path(__file__).with_name(".env"))
    logging.info("Starting stock report")
    forwarder = TelegramForwarder.from_environment()
    description = forwarder.get_chat_description() or ",".join(DEFAULT_TICKERS)
    report = run_stock_agent_tool(description)
    logging.debug(f"Report: {report}")
    logging.info("Generated stock report (%d characters)", len(report))

    title = f"Stock report — {datetime.now().strftime('%Y-%m-%d')}"
    forwarder.forward(report, subject=title)
    logging.info("Report forwarded successfully.")


if __name__ == "__main__":
    main()
