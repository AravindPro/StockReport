"""Launch the Streamlit UI or run an agent configured in YAML."""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import yaml

from agent import build_agent
from custom_tools import CUSTOM_TOOLS
from forwarder import FORWARDERS, TelegramForwarder
from app_logging import configure_logging


configure_logging()


def load_env_file() -> None:
    """Load local .env settings without replacing existing variables."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def run_configured_agent(config_path: Path, prompt: str = "") -> None:
    """Build, run, and forward an agent described by a YAML configuration."""
    load_env_file()
    config_path = config_path.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Agent configuration must be a YAML mapping: {config_path}")

    prompt_path_value = config.get("system_prompt")
    if not isinstance(prompt_path_value, str) or not prompt_path_value.strip():
        raise ValueError("Agent configuration must include a system_prompt path.")
    prompt_path = Path(prompt_path_value)
    if not prompt_path.is_absolute():
        prompt_path = config_path.parent / prompt_path
    if not prompt_path.is_file():
        raise FileNotFoundError(f"System prompt file not found: {prompt_path}")

    tool_names = config.get("tools", [])
    if not isinstance(tool_names, list) or not all(
        isinstance(name, str) for name in tool_names
    ):
        raise ValueError("The tools setting must be a list of tool names.")
    unknown_tools = sorted(set(tool_names) - CUSTOM_TOOLS.keys())
    if unknown_tools:
        raise ValueError(
            f"Unknown tool(s): {', '.join(unknown_tools)}. "
            f"Available tools: {', '.join(sorted(CUSTOM_TOOLS))}"
        )

    forwarder_config = config.get("forwarder")
    if not isinstance(forwarder_config, dict):
        raise ValueError("Agent configuration must include a forwarder mapping.")
    forwarder_name = forwarder_config.get("type")
    if not isinstance(forwarder_name, str) or forwarder_name not in FORWARDERS:
        raise ValueError(
            f"Unknown forwarder {forwarder_name!r}. "
            f"Available forwarders: {', '.join(sorted(FORWARDERS))}"
        )
    forwarder = FORWARDERS[forwarder_name]()

    include_description = forwarder_config.get(
        "include_chat_description_in_prompt",
        False,
    )
    if not isinstance(include_description, bool):
        raise ValueError("include_chat_description_in_prompt must be true or false.")
    if include_description:
        if not isinstance(forwarder, TelegramForwarder):
            raise ValueError(
                "include_chat_description_in_prompt is only supported by the Telegram forwarder."
            )
        description = forwarder.get_chat_description()
        if description:
            prompt = prompt or ""
            prompt = f"{prompt.strip()}\n\nAdditional description:\n\n{description.strip()}"

    agent = build_agent(
        filename=str(prompt_path),
        extra_tools=[CUSTOM_TOOLS[name] for name in tool_names],
    )
    logging.info("Invoking configured agent")
    logging.debug("Agent prompt: %s", prompt)
    response = agent.invoke({"messages": [("user", prompt)]})
    for message in response.get("messages", []):
        if type(message).__name__ == "ToolMessage":
            logging.info(
                "Agent executed tool: %s (id=%s)",
                getattr(message, "name", "unknown"),
                getattr(message, "tool_call_id", "unknown"),
            )
        for tool_call in getattr(message, "tool_calls", None) or []:
            logging.info(
                "Agent tool call: %s (id=%s)",
                tool_call.get("name"),
                tool_call.get("id"),
            )
            logging.debug("Agent tool arguments: %r", tool_call.get("args"))

        content = getattr(message, "content", None)
        if type(message).__name__ != "ToolMessage" and content:
            logging.debug("Agent message content: %s", content)

    logging.info("Configured agent invocation completed")
    result = next(
        (
            content.strip()
            for message in reversed(response.get("messages", []))
            if isinstance((content := getattr(message, "content", None)), str)
            and content.strip()
        ),
        None,
    )
    if result is None:
        raise RuntimeError("The agent returned no text to forward.")

    forwarder_options = {
        key: value
        for key, value in forwarder_config.items()
        if key not in {"type", "include_chat_description_in_prompt"}
    }
    if forwarder_name == "notion" and "title" not in forwarder_options:
        forwarder_options["title"] = "Agent response"
    forwarder.forward(result, **forwarder_options)
    logging.info("Result: %s", result)


def main() -> int:
    """Run a YAML-configured agent, or launch the web UI by default."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        help="YAML agent configuration (omit to launch the Streamlit UI)",
    )
    parser.add_argument("--prompt", help="Prompt to send instead of prompting interactively")
    args = parser.parse_args()

    if args.config is not None:
        run_configured_agent(args.config, args.prompt)
        return 0

    load_env_file()
    app_path = Path(__file__).with_name("webapp_streamlit.py")
    logging.info("Starting Streamlit web application")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_path)])


if __name__ == "__main__":
    raise SystemExit(main())
