"""Launch the Streamlit UI for the OpenRouter agent."""

import os
import subprocess
import sys
from pathlib import Path


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


def main() -> int:
    """Run the web UI, which uses agent.build_agent as its backend."""
    load_env_file()
    app_path = Path(__file__).with_name("webapp_streamlit.py")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_path)])


if __name__ == "__main__":
    raise SystemExit(main())
