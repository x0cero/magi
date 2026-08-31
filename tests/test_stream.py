"""The wire format the Mac app renders against.

This is a contract with another codebase, so the tests pin the shape rather
than the prose: a field that quietly changes name here becomes a blank panel
over there, with no error on either side.
"""

import json

import pytest

from magi.core import ChoiceResponse, PersonaResponse, RecommendResponse, Verdict
from magi.stream import PROTOCOL_VERSION, emit, position


def vote(verdict=Verdict.ACCEPT, confidence=4) -> PersonaResponse:
    return PersonaResponse(
        verdict=verdict,
        reasoning="the migration runs inside one transaction and reverts cleanly",
        lens_finding="MECHANISM: one transaction",
        confidence=confidence,
    )


class TestEmit:
    def test_one_json_object_per_line(self, capsys):
        emit("vote", member="MELCHIOR", verdict="ACCEPT")
        emit("end")
        lines = capsys.readouterr().out.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "vote"
        assert json.loads(lines[1]) == {"event": "end"}

    def test_a_line_never_contains_a_raw_newline(self, capsys):
        emit("vote", member="CASPER", reasoning="first line\nsecond line")
        out = capsys.readouterr().out
        assert out.count("\n") == 1, "a multi-line field would split one event into two"
        assert json.loads(out)["reasoning"] == "first line\nsecond line"

    def test_unserialisable_values_do_not_kill_the_stream(self, capsys):
        emit("vote", member="MELCHIOR", confidence=object())
        assert json.loads(capsys.readouterr().out)["member"] == "MELCHIOR"


class TestPosition:
    def test_a_decision_carries_its_verdict(self):
        data = position("MELCHIOR", vote(Verdict.REJECT))
        assert data["verdict"] == Verdict.REJECT.value
        assert data["verdict_key"] == "REJECT"
        assert data["lens"] == "MECHANISM"
        assert data["confidence"] == 4

    def test_a_choice_carries_its_option(self):
        picked = ChoiceResponse(
            chosen_option="rust",
            reasoning="the parser is the hot path and the rewrite pays for itself",
            lens_finding="MECHANISM: hot path",
            confidence=4,
        )
        data = position("MELCHIOR", picked)
        assert data["option"] == "rust"
        assert "verdict" not in data

    def test_a_recommendation_carries_its_pick(self):
        rec = RecommendResponse(
            recommendation="finish the eval harness first",
            reasoning="everything else is guesswork until the numbers are trustworthy",
            lens_finding="MECHANISM: measurement first",
            confidence=4,
        )
        data = position("BALTHASAR", rec)
        assert data["recommendation"] == "finish the eval harness first"

    def test_a_failed_member_is_marked_not_silently_empty(self):
        data = position("CASPER", RuntimeError("boom"))
        assert data["failed"] is True
        assert data["error"] == "RuntimeError"
        assert "verdict" not in data

    def test_the_error_text_itself_is_not_leaked(self):
        """Provider errors can carry a host or a key fragment."""
        data = position("CASPER", RuntimeError("connect to http://10.0.0.4:11434 failed"))
        assert "10.0.0.4" not in json.dumps(data)

    def test_a_condition_only_appears_when_there_is_one(self):
        assert "condition" not in position("MELCHIOR", vote())
        conditional = PersonaResponse(
            verdict=Verdict.CONDITIONAL,
            reasoning="acceptable only with a rehearsed rollback in place first",
            lens_finding="MECHANISM: rollback",
            confidence=3,
            condition="a rehearsed rollback exists",
        )
        assert position("MELCHIOR", conditional)["condition"] == "a rehearsed rollback exists"

    def test_every_position_is_json_serialisable(self):
        json.dumps(position("MELCHIOR", vote()))
        json.dumps(position("CASPER", RuntimeError("x")))


class TestProtocol:
    def test_the_version_is_pinned(self):
        """Bumping this is a breaking change for the app; it should be a
        deliberate edit with a matching change on the Swift side."""
        assert PROTOCOL_VERSION == 1

    @pytest.mark.parametrize("key", ["reasoning", "finding", "lens", "confidence"])
    def test_the_keys_the_app_draws_are_always_present(self, key):
        assert key in position("MELCHIOR", vote())
