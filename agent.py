#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_community.tools import DuckDuckGoSearchResults
from langchain.agents import create_agent

from custom_tools import fetch_webpage


def load_system_prompt() -> str:
    """Read the editable system prompt stored beside this module."""
    prompt_path = Path(__file__).with_name("system.md")
    if not prompt_path.exists():
        return "You are a helpful assistant."
    return prompt_path.read_text(encoding="utf-8").strip()


def build_agent(model=None):
    api_key = os.getenv("OPEN_ROUTER_API")
    if not api_key:
        sys.exit("OPEN_ROUTER_API not set. Add it to .env.")

    model = model or os.getenv("OPENROUTER_MODEL")
    if not model:
        sys.exit("OPENROUTER_MODEL not set. Add it to .env.")

    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        model=model,
    )

    search = DuckDuckGoSearchResults(output_format="list")
    tools = [search, fetch_webpage]

    return create_agent(
        llm,
        tools=tools,
        system_prompt=load_system_prompt(),
    )
