"""Models served through the local daemon but running on Ollama's servers.

A `:cloud` tag reaches the same endpoint as a local model and nothing in the
spec distinguishes them, but it behaves differently in three ways that each
broke the council: it ignores the structured-output schema and answers in
prose, it narrates its reasoning before the answer, and it cannot be warmed.
"""

import json

import pytest

from magi.providers import _ollama_body, extract_json_object, is_cloud_tag, is_local


class TestCloudTagDetection:
    @pytest.mark.parametrize("spec", ["glm-5.3:cloud", "kimi-k3:cloud", "glm-5.3-flash:cloud"])
    def test_a_cloud_tag_is_recognised(self, spec):
        assert is_cloud_tag(spec)

    @pytest.mark.parametrize("spec", ["qwen3:4b", "hermes3:8b", "dolphin3:8b"])
    def test_a_local_model_is_not(self, spec):
        assert not is_cloud_tag(spec)

    def test_a_cloud_tag_is_not_local(self):
        """It answers on localhost, but the question leaves the machine and it
        must not be warmed."""
        assert not is_local("glm-5.3:cloud")
        assert is_local("qwen3:4b")

    def test_a_prefixed_provider_is_still_not_local(self):
        assert not is_local("groq/llama-3.3-70b-versatile")


class TestRequestShape:
    def _body(self, model):
        return _ollama_body(model, "system", [{"role": "user", "content": "q"}],
                            {"type": "object"}, 0.7, 1200, None)

    def test_a_local_model_gets_the_schema_as_a_parameter(self):
        assert "format" in self._body("qwen3:4b")

    def test_a_cloud_model_gets_it_in_the_prompt_instead(self):
        """It drops `format` on the floor, so a schema sent that way constrains
        nothing and every seat using one failed validation."""
        body = self._body("glm-5.3:cloud")
        assert "format" not in body
        assert "JSON" in body["messages"][0]["content"]


class TestExtractingTheAnswer:
    def test_a_clean_object_is_returned_as_is(self):
        assert json.loads(extract_json_object('{"verdict": "ACCEPT"}'))["verdict"] == "ACCEPT"

    def test_prose_before_the_answer_is_cut_away(self):
        raw = 'Let me think about this.\n\nMy lens is mechanism.\n{"verdict": "REJECT"}'
        assert json.loads(extract_json_object(raw))["verdict"] == "REJECT"

    def test_braces_in_the_prose_do_not_confuse_it(self):
        raw = 'Consider the set {a, b} and the case {\n{"verdict": "ACCEPT"}'
        assert json.loads(extract_json_object(raw))["verdict"] == "ACCEPT"

    def test_an_unbalanced_quote_in_the_prose_does_not_break_it(self):
        """Brace counting was the first approach and this is what killed it."""
        raw = 'The user asks "should i deploy\n{"verdict": "ACCEPT"}'
        assert json.loads(extract_json_object(raw))["verdict"] == "ACCEPT"

    def test_a_brace_inside_a_string_value_does_not_end_the_object(self):
        raw = 'thinking\n{"reasoning": "the set {x} matters", "verdict": "ACCEPT"}'
        parsed = json.loads(extract_json_object(raw))
        assert parsed["verdict"] == "ACCEPT"
        assert "{x}" in parsed["reasoning"]

    def test_a_markdown_fence_is_stripped(self):
        assert json.loads(extract_json_object('```json\n{"verdict": "ACCEPT"}\n```'))["verdict"] == "ACCEPT"

    def test_text_with_no_object_comes_back_untouched(self):
        """The caller validates and reports the failure; this must not invent
        an answer or raise."""
        assert extract_json_object("no json here") == "no json here"

    def test_the_last_object_wins(self):
        """Reasoning sometimes sketches a draft answer before the real one."""
        raw = '{"verdict": "ACCEPT"}\nactually, on reflection:\n{"verdict": "REJECT"}'
        assert json.loads(extract_json_object(raw))["verdict"] == "REJECT"
