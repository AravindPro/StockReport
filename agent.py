#!/usr/bin/env python3
import os
import sys
import logging
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchResults
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware

from custom_tools import fetch_webpage, get_groww_mcp_tools
from utils import retry


class RetryModelCalls(AgentMiddleware):
    """Retry failed model calls without rerunning tools or the full agent."""

    def wrap_model_call(self, request, handler):
        @retry(max_retries=3, delay_seconds=1.0)
        def call_model():
            return handler(request)

        return call_model()

    async def awrap_model_call(self, request, handler):
        @retry(max_retries=3, delay_seconds=1.0)
        async def call_model():
            return await handler(request)

        return await call_model()


def load_system_prompt(filename: str) -> str:
    """Read the editable system prompt stored beside this module."""
    prompt_path = Path(__file__).parent / f"system_prompts/{filename}"
    if not prompt_path.exists():
        logging.warning("System prompt file was not found; using the default prompt")
        return "You are a helpful assistant."
    logging.info("Loaded system prompt")
    return prompt_path.read_text(encoding="utf-8").strip()


def build_agent(model=None, filename: str = "system.md", extra_tools: list | None = None):
    api_key = os.getenv("OPEN_ROUTER_API")
    if not api_key:
        logging.error("OpenRouter API key is not configured")
        sys.exit("OPEN_ROUTER_API not set. Add it to .env.")

    model = model or os.getenv("OPENROUTER_MODEL")
    if not model:
        logging.error("OpenRouter model is not configured")
        sys.exit("OPENROUTER_MODEL not set. Add it to .env.")

    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        model=model,
    )

    search = DuckDuckGoSearchResults(output_format="list")
    tools = [search, fetch_webpage, *(extra_tools or [])]
    # mcp_tools = asyncio.run(get_groww_mcp_tools())
    # tools.extend(mcp_tools)
    middlewares = [RetryModelCalls()]

    logging.info(
        "Building agent with %d tools using model %s: %s",
        len(tools),
        model,
        [tool.name for tool in tools],
    )
    return create_agent(
        llm,
        tools=tools,
        system_prompt=load_system_prompt(filename),
        middleware=middlewares,
    )
