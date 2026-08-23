"""Provider layer: routes model specs to local Ollama or BYOK cloud APIs.

A model spec is either a bare Ollama model name ("qwen3:14b") or a
"provider/model" string:

    anthropic/claude-opus-4-8
    openai/gpt-4o
    groq/llama-3.3-70b-versatile
    openrouter/meta-llama/llama-3.3-70b-instruct:free
    gemini/gemini-2.0-flash
    ollama-cloud/deepseek-v3.1:671b

Local Ollama needs no key. Cloud providers read their key from the standard
env var, falling back to [providers] in ~/.config/magi/config.toml.
"""

import copy
import json
import os

import httpx

from magi.config import OLLAMA_HOST, load_config

MAX_RESPONSE_BYTES = 1_048_576


class OllamaUnavailable(Exception):
    """Raised when local Ollama can't be reached."""

    def __init__(self, host: str = OLLAMA_HOST):
        super().__init__(
            f"cannot connect to Ollama at {host}\n\n"
            "  install:  https://ollama.com\n"
            "  start:    ollama serve\n"
            "  custom:   OLLAMA_HOST=http://host:port magi"
        )


class ProviderError(Exception):
    """A cloud provider call failed in a way worth showing the user."""


# provider -> (base_url, env var). All except anthropic speak the
# OpenAI-compatible /chat/completions protocol; ollama-cloud speaks Ollama's.
_OPENAI_COMPAT = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
}
_OLLAMA_CLOUD_HOST = "https://ollama.com"

KNOWN_PROVIDERS = ("ollama", "anthropic", "ollama-cloud") + tuple(_OPENAI_COMPAT)

_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama-cloud": "OLLAMA_API_KEY",
    **{p: env for p, (_, env) in _OPENAI_COMPAT.items()},
}


def parse_model_spec(spec: str) -> tuple[str, str]:
    """Split a model spec into (provider, model). Bare names are local ollama.

    Only splits on a known provider prefix, so OpenRouter-style model names
    that themselves contain '/' still work after their provider prefix.
    """
    if "/" in spec:
        prefix, rest = spec.split("/", 1)
        if prefix in KNOWN_PROVIDERS and rest:
            return ("ollama", rest) if prefix == "ollama" else (prefix, rest)
    return "ollama", spec


def is_local(spec: str) -> bool:
    return parse_model_spec(spec)[0] == "ollama"


def get_api_key(provider: str) -> str | None:
    env = _KEY_ENV_VARS.get(provider)
    if env and os.environ.get(env):
        return os.environ[env]
    keys = load_config().get("providers", {})
    val = keys.get(provider, {}).get("api_key") if isinstance(keys.get(provider), dict) else keys.get(provider)
    return val if isinstance(val, str) and val else None


def _require_key(provider: str) -> str:
    key = get_api_key(provider)
    if not key:
        env = _KEY_ENV_VARS[provider]
        raise ProviderError(
            f"no API key for {provider} — set {env} or add it under [providers] in config.toml"
        )
    return key


def _check_response(response: httpx.Response) -> None:
    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response too large ({content_length} bytes, cap {MAX_RESPONSE_BYTES})")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response too large ({len(response.content)} bytes, cap {MAX_RESPONSE_BYTES})")
    ct = response.headers.get("content-type", "")
    if ct and "json" not in ct and "text" not in ct:
        raise ValueError(f"unexpected content-type: {ct[:60]}")


def _raise_for_status(provider: str, response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    detail = ""
    try:
        body = response.json()
        detail = body.get("error", {}).get("message") or body.get("error") or ""
        if not isinstance(detail, str):
            detail = json.dumps(detail)[:200]
    except Exception:
        detail = response.text[:200]
    if response.status_code in (401, 403):
        raise ProviderError(f"{provider}: auth failed ({response.status_code}) — check your API key")
    if response.status_code == 429:
        raise ProviderError(f"{provider}: rate limited — wait a moment and retry")
    raise ProviderError(f"{provider}: HTTP {response.status_code} {detail}".strip())


# A deliberation turn is a ~1.5k-token system prompt plus a short history, but
# models advertising a 128k window make Ollama reserve a KV cache to match —
# hermes3:8b alone reserved 21GB of it. Pinning the window is the difference
# between the council fitting on a laptop and thrashing.
NUM_CTX = int(os.environ.get("MAGI_NUM_CTX", "8192"))

# `think` is a TOP-LEVEL field on /api/chat, not an option. Passing it inside
# options is silently ignored, and a reasoning model then spends its whole
# num_predict budget on hidden chain-of-thought and returns empty content —
# measured at 1200 tokens and nothing usable, versus 100 tokens and a clean
# verdict with the flag in the right place.
def _ollama_body(model: str, system: str, messages: list[dict], schema: dict,
                 temperature: float, num_predict: int, keep_alive: str | None) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "format": schema,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": NUM_CTX,
        },
    }
    if keep_alive:
        body["keep_alive"] = keep_alive
    return body


async def _chat_ollama(client: httpx.AsyncClient, model: str, system: str,
                       messages: list[dict], schema: dict, temperature: float,
                       num_predict: int, timeout: float, keep_alive: str) -> str:
    try:
        response = await client.post(
            f"{OLLAMA_HOST}/api/chat",
            json=_ollama_body(model, system, messages, schema, temperature, num_predict, keep_alive),
            timeout=timeout,
        )
    except httpx.ConnectError:
        raise OllamaUnavailable()
    response.raise_for_status()
    _check_response(response)
    return response.json()["message"]["content"]


async def _chat_ollama_cloud(client: httpx.AsyncClient, model: str, system: str,
                             messages: list[dict], schema: dict, temperature: float,
                             num_predict: int, timeout: float) -> str:
    key = _require_key("ollama-cloud")
    response = await client.post(
        f"{_OLLAMA_CLOUD_HOST}/api/chat",
        json=_ollama_body(model, system, messages, schema, temperature, num_predict, None),
        headers={"Authorization": f"Bearer {key}"},
        timeout=timeout,
    )
    _raise_for_status("ollama-cloud", response)
    _check_response(response)
    return response.json()["message"]["content"]


def _schema_instruction(schema: dict) -> str:
    keys = ", ".join(schema.get("properties", {}).keys())
    return (
        "\n\n== OUTPUT FORMAT ==\n"
        f"Respond with ONLY a single JSON object with these keys: {keys}. "
        "No prose, no markdown fences. Do NOT output the schema itself — "
        "output an INSTANCE that validates against it:\n"
        f"{json.dumps(schema)}"
    )


def _looks_like_schema_echo(content: str) -> bool:
    """Small models sometimes parrot the schema back instead of an instance."""
    try:
        obj = json.loads(content)
    except Exception:
        return False
    return isinstance(obj, dict) and "properties" in obj and obj.get("type") == "object"


async def _chat_openai_compat(client: httpx.AsyncClient, provider: str, model: str,
                              system: str, messages: list[dict], schema: dict,
                              temperature: float, num_predict: int, timeout: float) -> str:
    key = _require_key(provider)
    base, _ = _OPENAI_COMPAT[provider]
    # json_object mode is supported across all four providers; strict
    # json_schema mode is not, so the schema rides in the system prompt and
    # pydantic validates the result.
    convo = [{"role": "system", "content": system + _schema_instruction(schema)}] + messages
    for attempt in range(2):
        body: dict = {
            "model": model,
            "messages": convo,
            "response_format": {"type": "json_object"},
        }
        if provider == "openai":
            body["max_completion_tokens"] = num_predict
        else:
            body["max_tokens"] = num_predict
            body["temperature"] = temperature
        response = await client.post(
            f"{base}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )
        _raise_for_status(provider, response)
        _check_response(response)
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"{provider}: unexpected response shape")
        if attempt == 0 and _looks_like_schema_echo(content):
            convo = convo + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    "You output the JSON schema itself. Wrong. Output an INSTANCE: "
                    "a JSON object with ONLY the required keys and your actual answers as values."
                )},
            ]
            continue
        return content
    return content


def _clean_schema_for_anthropic(schema: dict) -> dict:
    """Structured outputs reject string-length constraints; strip them and
    lock objects down the way the API requires."""
    schema = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            node.pop("minLength", None)
            node.pop("maxLength", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                if "properties" in node:
                    node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


async def _chat_anthropic(client: httpx.AsyncClient, model: str, system: str,
                          messages: list[dict], schema: dict,
                          num_predict: int, timeout: float) -> str:
    key = _require_key("anthropic")
    response = await client.post(
        "https://api.anthropic.com/v1/messages",
        json={
            "model": model,
            "max_tokens": max(num_predict, 4096),
            "system": system,
            "messages": messages,
            "output_config": {
                "format": {"type": "json_schema", "schema": _clean_schema_for_anthropic(schema)}
            },
        },
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        timeout=timeout,
    )
    _raise_for_status("anthropic", response)
    _check_response(response)
    data = response.json()
    if data.get("stop_reason") == "refusal":
        raise ProviderError("anthropic: request was refused by safety filters")
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block["text"]
    raise ProviderError("anthropic: no text in response")


async def chat(
    client: httpx.AsyncClient,
    model_spec: str,
    system: str,
    messages: list[dict],
    schema: dict,
    temperature: float = 0.7,
    num_predict: int = 1200,
    timeout: float = 180.0,
    keep_alive: str = "30m",
) -> str:
    """One structured-output chat turn against whatever backend the spec names.
    Returns the raw content string (callers sanitize + validate)."""
    provider, model = parse_model_spec(model_spec)
    if provider == "ollama":
        return await _chat_ollama(client, model, system, messages, schema,
                                  temperature, num_predict, timeout, keep_alive)
    if provider == "ollama-cloud":
        return await _chat_ollama_cloud(client, model, system, messages, schema,
                                        temperature, num_predict, timeout)
    if provider == "anthropic":
        return await _chat_anthropic(client, model, system, messages, schema,
                                     num_predict, timeout)
    return await _chat_openai_compat(client, provider, model, system, messages,
                                     schema, temperature, num_predict, timeout)
