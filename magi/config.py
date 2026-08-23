"""Config loading and merging."""

import os
import sys
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from magi.personas import SPECIALIST_DEFAULT_MODELS, SPECIALIST_NAMES

CONFIG_DIR = Path.home() / ".config" / "magi"
CONFIG_PATH = CONFIG_DIR / "config.toml"


def _validated_ollama_host() -> str:
    raw = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        print(f"warning: OLLAMA_HOST scheme must be http or https, got {raw!r}", file=sys.stderr)
        raw = "http://localhost:11434"
    if parsed.hostname not in (None, "localhost", "127.0.0.1", "::1"):
        print(f"warning: OLLAMA_HOST points to non-local host ({parsed.hostname}) — your questions will be sent there", file=sys.stderr)
    return raw


OLLAMA_HOST = _validated_ollama_host()

_EXAMPLE_CONFIG = """\
# MAGI configuration
# CLI flags and env vars override these values.

[models]
# Bare names are local Ollama. Prefix with a provider for cloud (BYOK):
#   anthropic/claude-opus-4-8, openai/gpt-4o, groq/llama-3.3-70b-versatile,
#   openrouter/<model>, gemini/gemini-2.0-flash, ollama-cloud/<model>
# melchior = "qwen3:14b"
# balthasar = "groq/llama-3.3-70b-versatile"
# casper = "hermes3:8b"

[providers]
# API keys for cloud members. Env vars (GROQ_API_KEY, ANTHROPIC_API_KEY,
# OPENAI_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY, OLLAMA_API_KEY) win
# over these values.
# [providers.groq]
# api_key = "gsk_..."

[specialists]
# Auto-invite these specialists into every deliberation.
# invite = ["banker"]

# Override specialist models:
# [specialists.models]
# banker = "qwen2.5:7b"
# therapist = "mistral:latest"

[options]
# classifier_model = "qwen3:4b"
# max_rounds = 2   # 1 = vote only, no debate round
"""


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def apply_config(
    models: dict[str, str],
    cli_overrides: dict[str, str | None],
) -> tuple[dict[str, str], list[str]]:
    """Merge config file → CLI overrides into final model dict.
    Returns (models, auto_invite_specialists)."""
    cfg = load_config()

    cfg_models = cfg.get("models", {})
    for name in ("melchior", "balthasar", "casper"):
        canonical = name.upper()
        if canonical in models and cfg_models.get(name):
            models[canonical] = cfg_models[name]

    for key, val in cli_overrides.items():
        if val is not None:
            models[key.upper()] = val

    auto_invite: list[str] = []
    specialists_cfg = cfg.get("specialists", {})
    for spec_name in specialists_cfg.get("invite", []):
        canonical = spec_name.upper()
        if canonical in SPECIALIST_NAMES and canonical not in models:
            spec_models = specialists_cfg.get("models", {})
            models[canonical] = spec_models.get(spec_name, SPECIALIST_DEFAULT_MODELS.get(canonical, "qwen2.5:7b"))
            auto_invite.append(canonical)

    return models, auto_invite


def max_rounds(default: int) -> int:
    """Deliberation rounds from [options] max_rounds, clamped to something
    sane. One round is a vote with no debate; past three the members restate."""
    value = load_config().get("options", {}).get("max_rounds", default)
    try:
        return max(1, min(6, int(value)))
    except (TypeError, ValueError):
        return default


def init_config() -> bool:
    """Write example config if it doesn't exist. Returns True if created."""
    if CONFIG_PATH.exists():
        return False
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(CONFIG_PATH), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, _EXAMPLE_CONFIG.encode())
    finally:
        os.close(fd)
    return True


def config_path_display() -> str:
    return str(CONFIG_PATH)
