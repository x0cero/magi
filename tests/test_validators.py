import pytest
from pydantic import ValidationError

from magi.core import (
    ChoiceResponse,
    PersonaResponse,
    Rebuttal,
    RecommendResponse,
    Verdict,
    _condition_is_vague,
    _normalize_option,
    _recommendation_is_vague,
    _strip_persona_prefixes,
)


class TestConditionVagueness:
    def test_empty_is_vague(self):
        assert _condition_is_vague("")

    def test_whitespace_is_vague(self):
        assert _condition_is_vague("   ")

    def test_banned_phrase_detected(self):
        assert _condition_is_vague("They need a clear plan before proceeding")

    def test_concrete_condition_passes(self):
        assert not _condition_is_vague("Need to see the Q3 revenue report showing >$50k MRR")

    def test_all_banned_phrases(self):
        from magi.core import _BANNED_CONDITION_PHRASES
        for phrase in _BANNED_CONDITION_PHRASES:
            assert _condition_is_vague(f"The user needs {phrase} first"), f"missed: {phrase}"


class TestRecommendationVagueness:
    def test_short_is_vague(self):
        assert _recommendation_is_vague("thing")

    def test_banned_phrase_detected(self):
        assert _recommendation_is_vague("something you're passionate about")

    def test_consider_building_detected(self):
        assert _recommendation_is_vague("Consider building a project that helps people")

    def test_consider_exploring_detected(self):
        assert _recommendation_is_vague("Consider exploring new frameworks for web development")

    def test_concrete_recommendation_passes(self):
        assert not _recommendation_is_vague("A personal finance tracker with bank API integration")


class TestPersonaResponseCoercion:
    def test_vague_conditional_coerced_to_accept(self):
        r = PersonaResponse(
            verdict=Verdict.CONDITIONAL,
            reasoning="This is a reasonable approach with some caveats.",
            lens_finding="freelance invoices clear 45 days after delivery",
            condition="They need a clear plan",
        )
        assert r.verdict == Verdict.ACCEPT
        assert r.condition == ""

    def test_empty_conditional_coerced_to_accept(self):
        r = PersonaResponse(
            verdict=Verdict.CONDITIONAL,
            reasoning="This is a reasonable approach with some caveats.",
            lens_finding="freelance invoices clear 45 days after delivery",
            condition="",
        )
        assert r.verdict == Verdict.ACCEPT

    def test_concrete_conditional_kept(self):
        r = PersonaResponse(
            verdict=Verdict.CONDITIONAL,
            reasoning="The numbers are tight but workable under one scenario.",
            lens_finding="rent is 60 percent of current monthly burn",
            condition="Only if their landlord agrees to extend the lease past June 2026",
        )
        assert r.verdict == Verdict.CONDITIONAL
        assert "landlord" in r.condition

    def test_accept_passes_through(self):
        r = PersonaResponse(
            verdict=Verdict.ACCEPT,
            reasoning="This is clearly the right move given the data.",
            lens_finding="churn drops below 3 percent at the new price",
        )
        assert r.verdict == Verdict.ACCEPT

    def test_reject_passes_through(self):
        r = PersonaResponse(
            verdict=Verdict.REJECT,
            reasoning="The risk profile is unacceptable at this stage.",
            lens_finding="one client is 70 percent of revenue",
        )
        assert r.verdict == Verdict.REJECT

    def test_short_reasoning_rejected(self):
        with pytest.raises(ValidationError):
            PersonaResponse(verdict=Verdict.ACCEPT, reasoning="No.", lens_finding="x marks it")


class TestRebuttalCoercion:
    def test_vague_conditional_coerced(self):
        r = Rebuttal(
            response="MELCHIOR is right about the timeline but wrong about scope.",
            final_verdict=Verdict.CONDITIONAL,
            condition="manageable scope",
        )
        assert r.final_verdict == Verdict.ACCEPT
        assert r.condition == ""


class TestRecommendResponse:
    def test_vague_recommendation_rejected(self):
        with pytest.raises(ValidationError):
            RecommendResponse(
                recommendation="something you're passionate about",
                reasoning="Follow your heart on this one, the answer is within.",
            )

    def test_concrete_recommendation_passes(self):
        r = RecommendResponse(
            recommendation="Build a CLI habit tracker with SQLite persistence",
            reasoning="Small scope, ship in a weekend, and it scratches a real itch.",
        )
        assert "habit tracker" in r.recommendation


class TestChoiceResponse:
    def test_valid_choice(self):
        r = ChoiceResponse(
            chosen_option="Swift",
            reasoning="Native performance matters more than cross-platform speed for this app.",
            lens_finding="SwiftUI ships the same feature in half the code here",
        )
        assert r.chosen_option == "Swift"

    def test_empty_choice_rejected(self):
        with pytest.raises(ValidationError):
            ChoiceResponse(
                chosen_option="",
                reasoning="Can't decide between these two equally valid options.",
            )


class TestNormalizeOption:
    def test_exact_match(self):
        assert _normalize_option("Swift", ["Swift", "React Native"]) == "Swift"

    def test_case_insensitive(self):
        assert _normalize_option("swift", ["Swift", "React Native"]) == "Swift"

    def test_substring_match(self):
        assert _normalize_option("React", ["Swift", "React Native"]) == "React Native"

    def test_no_match_returns_raw(self):
        assert _normalize_option("Flutter", ["Swift", "React Native"]) == "Flutter"

    def test_empty_returns_empty(self):
        assert _normalize_option("", ["Swift", "React Native"]) == ""


class TestStripPersonaPrefixes:
    def test_strips_name_prefix(self):
        assert _strip_persona_prefixes("CASPER: Build a habit tracker") == "Build a habit tracker"

    def test_strips_recommendation_prefix(self):
        assert _strip_persona_prefixes("MELCHIOR's recommendation: A data tool") == "A data tool"

    def test_strips_verdict_prefix(self):
        assert _strip_persona_prefixes("ACCEPT - This is the right call") == "This is the right call"

    def test_strips_nested(self):
        assert _strip_persona_prefixes("CASPER: ACCEPT - Do it") == "Do it"

    def test_leaves_clean_text(self):
        assert _strip_persona_prefixes("Build a habit tracker app") == "Build a habit tracker app"


class TestSentenceTrimming:
    """A chatty model runs to the token cap, and the tail is where sign-offs
    and invented personal experience live."""

    def test_long_reasoning_is_trimmed_to_three_sentences(self):
        from magi.core import _trim_to_sentences

        text = (
            "You are looking for a fresh experience. Returnal offers a unique blend. "
            "It strikes a balance. Start it today and let me know! "
            "I believe it will reignite your passion given how much I've personally enjoyed it."
        )
        out = _trim_to_sentences(text)
        assert out.endswith("It strikes a balance.")
        assert "let me know" not in out
        assert "I've personally enjoyed" not in out

    def test_short_reasoning_is_untouched(self):
        from magi.core import _trim_to_sentences

        text = "The runway does not clear. Two months is one month after invoicing lag."
        assert _trim_to_sentences(text) == text

    def test_empty_is_safe(self):
        from magi.core import _trim_to_sentences

        assert _trim_to_sentences("") == ""
        assert _trim_to_sentences(None) == ""

    def test_persona_response_trims_on_construction(self):
        from magi.core import PersonaResponse, Verdict

        r = PersonaResponse(
            verdict=Verdict.REJECT,
            reasoning="One sentence here. Two sentences here. Three sentences here. Four is too many.",
            lens_finding="invoices clear 45 days out",
        )
        assert "Four is too many" not in r.reasoning

    def test_recommend_response_trims_on_construction(self):
        from magi.core import RecommendResponse

        r = RecommendResponse(
            recommendation="Disco Elysium",
            reasoning="It fits the itch. The writing carries it. The loop is short. Let me know how it goes!",
        )
        assert "Let me know" not in r.reasoning


class TestFindingTrimming:
    def test_abbreviation_is_not_a_sentence_end(self):
        """Regression: a period-based splitter guillotined
        'Target income per hour vs. client acquisition rate' into 'vs.'"""
        from magi.core import _trim_finding

        text = "Target income per hour vs. client acquisition rate"
        assert _trim_finding(text) == text

    def test_short_finding_untouched(self):
        from magi.core import _trim_finding

        text = "Invoices clear 45 days after delivery"
        assert _trim_finding(text) == text

    def test_rambling_finding_cut_to_first_claim(self):
        from magi.core import _trim_finding

        text = (
            "The desire you're hiding is to relax and do nothing. You don't actually want "
            "the freelance life or the hustle. You just want the money part without the work part."
        )
        out = _trim_finding(text)
        assert out == "The desire you're hiding is to relax and do nothing."

    def test_one_very_long_sentence_is_word_capped(self):
        from magi.core import MAX_FINDING_WORDS, _trim_finding

        text = " ".join(["word"] * 60)
        out = _trim_finding(text)
        assert len(out.split()) <= MAX_FINDING_WORDS + 1
        assert out.endswith("...")


class TestRebuttalPrefixStripping:
    """dolphin3:8b opened a live rebuttal with the literal string 'BALTHASAR:'.
    The stripper existed but was only wired into recommend mode."""

    def test_decision_rebuttal_strips_own_name(self):
        from magi.core import Rebuttal, Verdict

        r = Rebuttal(
            response="BALTHASAR: While the others disagree, the weekend risk still stands.",
            final_verdict=Verdict.REJECT,
        )
        assert not r.response.startswith("BALTHASAR")
        assert r.response.startswith("While the others")

    def test_choice_rebuttal_strips_own_name(self):
        from magi.core import ChoiceRebuttal

        r = ChoiceRebuttal(
            response="CASPER: Swift is still the pick for what they actually want here.",
            final_choice="Swift",
        )
        assert not r.response.startswith("CASPER")

    def test_ordinary_rebuttal_untouched(self):
        from magi.core import Rebuttal, Verdict

        text = "MELCHIOR is right about the timeline but wrong about the scope of it."
        r = Rebuttal(response=text, final_verdict=Verdict.ACCEPT)
        assert r.response == text


class TestFindingCutsCleanly:
    """A finding that stops mid-phrase looks broken. Live example:
    "...results in a prolonged outage or data integrity..." where the clean
    cut was a comma fifteen words earlier."""

    LIVE = (
        "The silent sacrifice is the long-term reputation and stability of your "
        "service, which may irreversibly suffer if this high-risk deployment "
        "results in a prolonged outage or data integrity failure."
    )

    def test_cuts_at_the_comma_not_mid_phrase(self):
        from magi.core import _trim_finding

        out = _trim_finding(self.LIVE)
        assert out == "The silent sacrifice is the long-term reputation and stability of your service"
        assert not out.endswith("...")

    def test_cuts_before_a_subordinate_clause(self):
        from magi.core import _trim_finding

        out = _trim_finding(
            "You want the excitement and freedom that comes with being your own "
            "boss and the ability to set your own hours without anyone telling "
            "you what to do ever again"
        )
        assert "that comes with" not in out
        assert not out.endswith("...")

    def test_a_long_unbroken_line_still_gets_an_ellipsis(self):
        from magi.core import MAX_FINDING_WORDS, _trim_finding

        out = _trim_finding(" ".join(["word"] * 60))
        assert out.endswith("...")
        assert len(out.split()) <= MAX_FINDING_WORDS + 1

    def test_never_leaves_a_stub(self):
        from magi.core import MIN_FINDING_WORDS, _trim_finding

        out = _trim_finding(
            "Runway, which is the only thing that decides whether any of this "
            "matters at all in the end for them and everyone involved here"
        )
        assert len(out.split()) >= MIN_FINDING_WORDS

    def test_short_findings_are_untouched(self):
        from magi.core import _trim_finding

        for text in (
            "No rollback plan or post-migration validation",
            "Target income per hour vs. client acquisition rate",
            "Invoices clear 45 days after delivery",
        ):
            assert _trim_finding(text) == text
