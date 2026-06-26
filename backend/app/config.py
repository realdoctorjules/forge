"""Local config + Anthropic API key handling.

Single-user local tool: the key lives in forge/backend/.env (gitignored). It can
be set via the env var, the .env file, or the in-app settings field.
"""
from __future__ import annotations
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


def _load_env() -> None:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def get_anthropic_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def set_anthropic_key(key: str) -> None:
    key = key.strip()
    lines = []
    if ENV_FILE.exists():
        lines = [ln for ln in ENV_FILE.read_text().splitlines()
                 if not ln.startswith("ANTHROPIC_API_KEY=")]
    lines.append(f"ANTHROPIC_API_KEY={key}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    os.environ["ANTHROPIC_API_KEY"] = key
