from unittest.mock import patch

import pytest

from magi.core import PersonaResponse
from magi.providers import (
    ProviderError,
    _clean_schema_for_anthropic,
    _require_key,
    get_api_key,
    is_local,
    parse_model_spec,
)


class TestParseModelSpec:
    def test_bare_name_is_local_ollama(self):
        assert parse_model_spec("qwen3:14b") == ("ollama", "qwen3:14b")

    def test_explicit_ollama_prefix(self):
        assert parse_model_spec("ollama/qwen3:14b") == ("ollama", "qwen3:14b")

    def test_anthropic(self):
        assert parse_model_spec("anthropic/claude-opus-4-8") == ("anthropic", "claude-opus-4-8")

    def test_groq(self):
        assert parse_model_spec("groq/llama-3.3-70b-versatile") == ("groq", "llama-3.3-70b-versatile")

    def test_openrouter_model_with_slash(self):
        assert parse_model_spec("openrouter/meta-llama/llama-3.3-70b-instruct:free") == (
            "openrouter", "meta-llama/llama-3.3-70b-instruct:free",
        )

    def test_unknown_prefix_treated_as_local_name(self):
        # e.g. an Ollama model namespaced like "library/model" stays local
        assert parse_model_spec("someuser/custom-model") == ("ollama", "someuser/custom-model")

    def test_is_local(self):
        assert is_local("qwen3:14b")
        assert is_local("someuser/custom")
        assert not is_local("groq/llama-3.3-70b-versatile")
        assert not is_local("ollama-cloud/deepseek-v3.1:671b")


class TestApiKeys:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env")
        with patch("magi.providers.load_config", return_value={"providers": {"groq": {"api_key": "gsk_cfg"}}}):
            assert get_api_key("groq") == "gsk_env"

    def test_config_fallback(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with patch("magi.providers.load_config", return_value={"providers": {"groq": {"api_key": "gsk_cfg"}}}):
            assert get_api_key("groq") == "gsk_cfg"

    def test_missing_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with patch("magi.providers.load_config", return_value={}):
            assert get_api_key("anthropic") is None

    def test_require_key_raises_with_guidance(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with patch("magi.providers.load_config", return_value={}):
            with pytest.raises(ProviderError, match="GROQ_API_KEY"):
                _require_key("groq")


class TestAnthropicSchemaCleaning:
    def test_strips_length_constraints_and_locks_objects(self):
        schema = PersonaResponse.model_json_schema()
        cleaned = _clean_schema_for_anthropic(schema)

        def assert_clean(node):
            if isinstance(node, dict):
                assert "minLength" not in node
                assert "maxLength" not in node
                if node.get("type") == "object" and "properties" in node:
                    assert node["additionalProperties"] is False
                    assert set(node["required"]) == set(node["properties"].keys())
                for v in node.values():
                    assert_clean(v)
            elif isinstance(node, list):
                for v in node:
                    assert_clean(v)

        assert_clean(cleaned)

    def test_original_schema_not_mutated(self):
        schema = PersonaResponse.model_json_schema()
        before = repr(schema)
        _clean_schema_for_anthropic(schema)
        assert repr(schema) == before


class TestOllamaRequestBody:
    """These two fields are silently ignored when they sit in the wrong place,
    and the failure is invisible: the request still returns HTTP 200."""

    def _body(self):
        from magi.providers import _ollama_body

        return _ollama_body(
            "qwen3:4b", "system", [{"role": "user", "content": "hi"}],
            {"type": "object"}, 0.7, 1200, "30m",
        )

    def test_think_is_top_level_not_an_option(self):
        body = self._body()
        assert body["think"] is False
        # inside options it is ignored, and a reasoning model burns the whole
        # num_predict budget on hidden chain-of-thought and returns nothing
        assert "think" not in body["options"]

    def test_context_window_is_pinned(self):
        from magi.providers import NUM_CTX

        body = self._body()
        assert body["options"]["num_ctx"] == NUM_CTX
        # a model advertising 128k makes Ollama reserve a KV cache to match
        assert NUM_CTX <= 32768

    def test_keep_alive_passed_through(self):
        assert self._body()["keep_alive"] == "30m"

    def test_schema_is_sent_as_format(self):
        assert self._body()["format"] == {"type": "object"}


class TestWarmupMatchesDeliberation:
    """Warming a model at a different context size than the deliberation asks
    for makes Ollama unload and reload it on the first real call."""

    def test_warmup_pins_the_same_context_window(self):
        from magi.providers import NUM_CTX, _ollama_body
        from magi.warmup import warmup_body

        warm = warmup_body("hermes3:8b")
        real = _ollama_body("hermes3:8b", "s", [], {}, 0.7, 1200, "30m")
        assert warm["options"]["num_ctx"] == real["options"]["num_ctx"] == NUM_CTX

    def test_warmup_keeps_the_model_resident(self):
        from magi.core import KEEP_ALIVE
        from magi.warmup import warmup_body

        assert warmup_body("hermes3:8b")["keep_alive"] == KEEP_ALIVE
