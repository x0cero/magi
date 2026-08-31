"""Council order must not depend on which model answered first.

Members are consulted concurrently and collected as they finish, so the raw
result dict arrives in whatever order the GPU happened to produce. That order
used to leak into the round-2 prompt (which lists the other members) and into
the truncated list of unverified terms, which made identical code score 12, 13
and 17 fabricated premises across three runs.
"""

from magi.core import (
    DEFAULT_MODELS,
    MAX_UNVERIFIED_TERMS,
    PersonaResponse,
    Verdict,
    _in_council_order,
    _unverified_terms,
)


def position(reasoning: str) -> PersonaResponse:
    return PersonaResponse(
        verdict=Verdict.ACCEPT,
        reasoning=reasoning,
        lens_finding="MECHANISM: the migration runs in one transaction",
        confidence=4,
    )


class TestCouncilOrder:
    def test_arrival_order_is_normalized(self):
        arrived = {"CASPER": 1, "MELCHIOR": 2, "BALTHASAR": 3}
        assert list(_in_council_order(arrived, DEFAULT_MODELS)) == list(DEFAULT_MODELS)

    def test_any_arrival_order_gives_the_same_result(self):
        orders = [
            {"MELCHIOR": 1, "BALTHASAR": 2, "CASPER": 3},
            {"CASPER": 3, "BALTHASAR": 2, "MELCHIOR": 1},
            {"BALTHASAR": 2, "CASPER": 3, "MELCHIOR": 1},
        ]
        results = [list(_in_council_order(o, DEFAULT_MODELS).items()) for o in orders]
        assert results[0] == results[1] == results[2]

    def test_a_missing_member_does_not_drop_the_others(self):
        """Two survivors of a failed round still come back in council order."""
        arrived = {"CASPER": 3, "MELCHIOR": 1}
        assert list(_in_council_order(arrived, DEFAULT_MODELS)) == ["MELCHIOR", "CASPER"]

    def test_an_unknown_member_is_kept_not_discarded(self):
        """Specialists are not in DEFAULT_MODELS; losing one would be worse
        than ordering it last."""
        arrived = {"BANKER": 9, "MELCHIOR": 1}
        ordered = _in_council_order(arrived, DEFAULT_MODELS)
        assert list(ordered) == ["MELCHIOR", "BANKER"]
        assert ordered["BANKER"] == 9


class TestUnverifiedTermsAreStable:
    QUESTION = "should i push a database migration to prod at 5pm on friday"

    def _positions(self, order: list[str]) -> dict:
        texts = {
            "MELCHIOR": "they have a tested rollback window and a staging rehearsal",
            "BALTHASAR": "the oncall rotation and the incident budget both cover this",
            "CASPER": "their team retro and the quarterly roadmap say ship it",
        }
        return {name: position(texts[name]) for name in order}

    def test_same_terms_whatever_the_arrival_order(self):
        forward = _unverified_terms(
            self._positions(["MELCHIOR", "BALTHASAR", "CASPER"]), self.QUESTION)
        backward = _unverified_terms(
            self._positions(["CASPER", "BALTHASAR", "MELCHIOR"]), self.QUESTION)
        assert forward == backward, (
            "the round-2 prompt names a different set of invented specifics "
            "depending on who finished first"
        )

    def test_the_list_is_capped(self):
        terms = _unverified_terms(
            self._positions(["MELCHIOR", "BALTHASAR", "CASPER"]), self.QUESTION)
        assert len(terms) <= MAX_UNVERIFIED_TERMS


class TestStanceChangesAreCountedByMember:
    """The metric used to zip two lists, so it counted dict ordering rather
    than anyone changing their mind. Pinning positions to council order made it
    report 24-26 stance changes on runs that really had 2-5."""

    def _result(self, round1: dict, final: dict) -> dict:
        return {
            "id": "q", "mode": "decision", "expect_mode": "decision",
            "divergent": True, "rounds": 2, "outcome": "majority",
            "round1_positions": {n: {"verdict": v, "reasoning": "", "lens_finding": ""}
                                 for n, v in round1.items()},
            "final_positions": {n: {"verdict": v, "reasoning": "", "lens_finding": ""}
                                for n, v in final.items()},
            "elapsed": 1.0, "error": None, "text": "should i ship it",
        }

    def test_nobody_moved_counts_zero_whatever_the_key_order(self):
        from evals.metrics import score_result
        held = {"MELCHIOR": "ACCEPT", "BALTHASAR": "REJECT", "CASPER": "CONDITIONAL"}
        reordered = {"CASPER": "CONDITIONAL", "MELCHIOR": "ACCEPT", "BALTHASAR": "REJECT"}
        assert score_result(self._result(held, reordered))["stance_changes"] == 0

    def test_a_real_change_is_still_counted(self):
        from evals.metrics import score_result
        before = {"MELCHIOR": "CONDITIONAL", "BALTHASAR": "REJECT", "CASPER": "REJECT"}
        after = {"MELCHIOR": "ACCEPT", "BALTHASAR": "REJECT", "CASPER": "REJECT"}
        assert score_result(self._result(before, after))["stance_changes"] == 1

    def test_a_member_who_dropped_out_is_not_a_change(self):
        from evals.metrics import score_result
        before = {"MELCHIOR": "ACCEPT", "BALTHASAR": "REJECT", "CASPER": "REJECT"}
        after = {"MELCHIOR": "ACCEPT", "BALTHASAR": "REJECT"}
        assert score_result(self._result(before, after))["stance_changes"] == 0
