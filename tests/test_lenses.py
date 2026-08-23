"""Tests for the machinery that keeps three lenses from becoming one voice."""

from magi.core import (
    ChoiceResponse,
    PersonaResponse,
    Verdict,
    _find_echoes,
    _member_schema,
    _resolve,
)
from magi.personas import LENS_FIELD, get_decision_prompt, lens_field_label
from magi.textsim import is_echo, longest_shared_phrase, overlap


def vote(verdict, reasoning, finding="", confidence=3):
    return PersonaResponse(
        verdict=verdict,
        reasoning=reasoning,
        lens_finding=finding or "a finding",
        confidence=confidence,
    )


class TestTextSimilarity:
    def test_identical_text_is_an_echo(self):
        t = "Two months of savings is insufficient runway for freelance income."
        assert is_echo(t, t)

    def test_the_real_world_collapse_case(self):
        """Verbatim from a live v0.12 run: MELCHIOR and BALTHASAR made the same
        argument on 'should i quit my warehouse job'."""
        melchior = (
            "Two months of savings is insufficient runway to transition from a stable "
            "job to freelance income, which is inherently unpredictable and delayed."
        )
        balthasar = (
            "Two months of savings is insufficient runway, risking financial instability. "
            "Transitioning from a stable job without a concrete plan for consistent income "
            "could lead to long-term stress."
        )
        assert is_echo(melchior, balthasar)
        # "months savings insufficient runway" survives stopword removal intact
        assert longest_shared_phrase(melchior, balthasar) >= 4
        assert overlap(melchior, balthasar) >= 0.28

    def test_distinct_lenses_are_not_echoes(self):
        melchior = "Freelance invoices clear 45 days out, so two months of savings is really one."
        casper = "They already quit in their head, they are here asking for permission."
        assert not is_echo(melchior, casper)
        assert overlap(melchior, casper) < 0.2

    def test_empty_text_is_never_an_echo(self):
        assert not is_echo("", "anything at all here")


class TestEchoDetection:
    def test_later_member_is_flagged_not_the_first(self):
        positions = {
            "MELCHIOR": vote(Verdict.REJECT, "Two months of savings is insufficient runway for this."),
            "BALTHASAR": vote(Verdict.REJECT, "Two months of savings is insufficient runway, risking instability."),
            "CASPER": vote(Verdict.ACCEPT, "They already decided and want permission to go."),
        }
        echoes = _find_echoes(positions, ["MELCHIOR", "BALTHASAR", "CASPER"])
        assert "BALTHASAR" in echoes
        assert echoes["BALTHASAR"][0] == "MELCHIOR"
        assert "MELCHIOR" not in echoes
        assert "CASPER" not in echoes

    def test_clean_council_has_no_echoes(self):
        positions = {
            "MELCHIOR": vote(Verdict.REJECT, "Invoices clear 45 days out, so the buffer is half what they think."),
            "BALTHASAR": vote(Verdict.CONDITIONAL, "Their partner carries the mortgage if this stalls."),
            "CASPER": vote(Verdict.ACCEPT, "They are asking permission, not asking a question."),
        }
        assert _find_echoes(positions, list(positions)) == {}

    def test_lens_finding_counts_toward_the_comparison(self):
        positions = {
            "MELCHIOR": vote(Verdict.REJECT, "The runway does not clear.", finding="two months of savings covers one month of real burn"),
            "BALTHASAR": vote(Verdict.REJECT, "The buffer is thinner than they think.", finding="two months of savings covers one month of real burn"),
        }
        echoes = _find_echoes(positions, list(positions))
        assert "BALTHASAR" in echoes


class TestResolve:
    def test_unanimous(self):
        p = {n: vote(Verdict.ACCEPT, "x" * 25) for n in ("MELCHIOR", "BALTHASAR", "CASPER")}
        assert _resolve(p) == ("consensus", Verdict.ACCEPT)

    def test_majority_wins(self):
        p = {
            "MELCHIOR": vote(Verdict.REJECT, "x" * 25),
            "BALTHASAR": vote(Verdict.REJECT, "y" * 25),
            "CASPER": vote(Verdict.ACCEPT, "z" * 25),
        }
        outcome, winner = _resolve(p)
        assert outcome == "majority"
        assert winner == Verdict.REJECT

    def test_conviction_breaks_a_headcount_tie(self):
        p = {
            "MELCHIOR": vote(Verdict.ACCEPT, "x" * 25, confidence=5),
            "BALTHASAR": vote(Verdict.REJECT, "y" * 25, confidence=2),
        }
        outcome, winner = _resolve(p)
        assert outcome == "conviction"
        assert winner == Verdict.ACCEPT

    def test_desire_lens_breaks_a_conviction_tie(self):
        p = {
            "MELCHIOR": vote(Verdict.REJECT, "x" * 25, confidence=3),
            "CASPER": vote(Verdict.ACCEPT, "y" * 25, confidence=3),
        }
        outcome, winner = _resolve(p)
        assert outcome == "tiebreak"
        assert winner == Verdict.ACCEPT

    def test_never_returns_an_undecided_outcome(self):
        """Whatever the split, resolution names a winner."""
        combos = [
            [Verdict.ACCEPT, Verdict.REJECT, Verdict.CONDITIONAL],
            [Verdict.ACCEPT, Verdict.ACCEPT, Verdict.REJECT],
            [Verdict.CONDITIONAL, Verdict.REJECT, Verdict.REJECT],
            [Verdict.ACCEPT, Verdict.REJECT],
        ]
        for verdicts in combos:
            names = ["MELCHIOR", "BALTHASAR", "CASPER"][: len(verdicts)]
            p = {n: vote(v, "x" * 25) for n, v in zip(names, verdicts)}
            outcome, winner = _resolve(p)
            assert winner is not None, verdicts
            assert outcome in ("consensus", "majority", "conviction", "tiebreak"), verdicts

    def test_works_for_choice_positions(self):
        p = {
            "MELCHIOR": ChoiceResponse(chosen_option="Swift", reasoning="x" * 25, lens_finding="native APIs", confidence=4),
            "CASPER": ChoiceResponse(chosen_option="React Native", reasoning="y" * 25, lens_finding="ships faster", confidence=2),
        }
        outcome, winner = _resolve(p)
        assert winner == "Swift"


class TestPerMemberSchema:
    def test_each_member_gets_its_own_lens_instruction(self):
        mel = _member_schema(PersonaResponse, "MELCHIOR")["properties"]["lens_finding"]["description"]
        cas = _member_schema(PersonaResponse, "CASPER")["properties"]["lens_finding"]["description"]
        assert mel != cas
        assert "mechanism" in mel.lower()
        assert "want" in cas.lower()

    def test_unknown_member_still_gets_a_usable_schema(self):
        desc = _member_schema(PersonaResponse, "NOBODY")["properties"]["lens_finding"]["description"]
        assert desc

    def test_schema_injection_does_not_mutate_the_model(self):
        _member_schema(PersonaResponse, "MELCHIOR")
        fresh = PersonaResponse.model_json_schema()["properties"]["lens_finding"]["description"]
        assert "MECHANISM" not in fresh
        assert "only YOUR lens" in fresh

    def test_every_member_has_a_lens_field(self):
        from magi.personas import all_member_names

        for name in all_member_names():
            assert name in LENS_FIELD, name
            assert lens_field_label(name).isupper()


class TestPersonaPrompts:
    def test_prompt_names_the_territory_the_member_does_not_own(self):
        casper = get_decision_prompt("CASPER")
        assert "NOT YOURS" in casper
        assert "MELCHIOR" in casper

    def test_prompt_carries_the_members_own_finding_label(self):
        assert "MECHANISM" in get_decision_prompt("MELCHIOR")
        assert "COST" in get_decision_prompt("BALTHASAR")
        assert "WANT" in get_decision_prompt("CASPER")

    def test_confidence_is_explained(self):
        assert "confidence" in get_decision_prompt("MELCHIOR")


class TestOffLensDetection:
    def test_balthasar_caught_arguing_from_money(self):
        from magi.core import _find_off_lens

        positions = {
            "BALTHASAR": vote(Verdict.REJECT, "This poses a high risk to your financial stability."),
            "CASPER": vote(Verdict.ACCEPT, "They already decided and want permission to go."),
        }
        found = _find_off_lens(positions)
        assert found.get("BALTHASAR") == "financial"
        assert "CASPER" not in found

    def test_casper_caught_saying_its_risky(self):
        from magi.core import _find_off_lens

        positions = {
            "CASPER": vote(Verdict.REJECT, "Quitting without a safety net is reckless right now."),
        }
        assert _find_off_lens(positions)["CASPER"] in ("safety net", "reckless")

    def test_melchior_owns_the_numbers(self):
        from magi.core import _find_off_lens

        positions = {
            "MELCHIOR": vote(Verdict.REJECT, "Two months of savings is one month after invoicing lag."),
        }
        assert _find_off_lens(positions) == {}

    def test_lens_appropriate_argument_passes(self):
        from magi.core import _find_off_lens

        positions = {
            "BALTHASAR": vote(Verdict.REJECT, "The door back into that warehouse closes quietly."),
            "CASPER": vote(Verdict.ACCEPT, "They are asking permission, not asking a question."),
        }
        assert _find_off_lens(positions) == {}


class TestGrounding:
    """The council inventing facts it then votes on. See magi/grounding.py."""

    QUESTION = "should i push a database migration to prod at 5pm on friday"

    def test_the_real_fabrication_is_caught(self):
        from magi.core import _find_ungrounded

        positions = {
            "MELCHIOR": vote(
                Verdict.ACCEPT,
                "The mechanism for success is a 24-hour rollback window with pre-migration testing in staging.",
                finding="24-hour rollback window with pre-migration testing in staging",
            ),
        }
        assert "MELCHIOR" in _find_ungrounded(positions, self.QUESTION)

    def test_naming_the_missing_fact_is_not_a_fabrication(self):
        """Same nouns, under negation. This is the council doing its job."""
        from magi.core import _find_ungrounded

        positions = {
            "MELCHIOR": vote(
                Verdict.REJECT,
                "There's no mention of rollback plans, testing, or timing details that would prevent downtime.",
                finding="no rollback plan was stated",
            ),
        }
        assert _find_ungrounded(positions, self.QUESTION) == {}

    def test_lens_language_is_not_a_fabrication(self):
        from magi.core import _find_ungrounded

        positions = {
            "BALTHASAR": vote(
                Verdict.REJECT,
                "Deploying this close to the end of the workday leads to rushed decisions.",
                finding="delayed system stability over a weekend",
            ),
            "CASPER": vote(
                Verdict.ACCEPT,
                "You are asking permission rather than asking a question here.",
                finding="you want it off your plate before the weekend",
            ),
        }
        assert _find_ungrounded(positions, self.QUESTION) == {}

    def test_facts_the_user_gave_are_not_fabrications(self):
        from magi.core import _find_ungrounded

        question = "should i move across the country for my girlfriend after 8 months of dating"
        positions = {
            "BALTHASAR": vote(
                Verdict.REJECT,
                "Their girlfriend of 8 months is the whole basis for uprooting everything.",
                finding="8 months is early to make it irreversible",
            ),
        }
        assert _find_ungrounded(positions, question) == {}

    def test_a_bare_question_is_exempt(self):
        """Too little text to tell invention from inference."""
        from magi.core import _find_ungrounded

        positions = {"MELCHIOR": vote(Verdict.ACCEPT, "Their runway covers the transition period.")}
        assert _find_ungrounded(positions, "hi") == {}

    def test_unverified_terms_feed_the_round_two_anchor(self):
        from magi.core import _unverified_terms

        positions = {
            "MELCHIOR": vote(
                Verdict.ACCEPT,
                "The mechanism for success is a 24-hour rollback window with staging tests.",
                finding="24-hour rollback window",
            ),
        }
        terms = _unverified_terms(positions, self.QUESTION)
        assert terms
        assert len(terms) <= 5

    def test_no_question_means_no_anchor(self):
        from magi.core import _unverified_terms

        positions = {"MELCHIOR": vote(Verdict.ACCEPT, "Something asserted about a rollback plan.")}
        assert _unverified_terms(positions, "") == []


class TestRetryDispatch:
    """Regression: only echoes were dispatched, so the off-lens retry that was
    computed right above it never actually ran."""

    def test_all_three_offence_types_are_dispatched(self):
        import inspect

        from magi import core

        source = inspect.getsource(core._break_echoes)
        assert "(*echoes, *off_lens, *ungrounded)" in source


class TestOptionNormalisation:
    """A single typo used to mint a phantom fourth option in the tally."""

    OPTIONS = ["magi on pypi", "github install"]

    def test_typo_snaps_to_the_real_option(self):
        from magi.core import _normalize_option

        assert _normalize_option("magi on p:pyi", self.OPTIONS) == "magi on pypi"

    def test_exact_match_wins(self):
        from magi.core import _normalize_option

        assert _normalize_option("github install", self.OPTIONS) == "github install"

    def test_case_and_whitespace_ignored(self):
        from magi.core import _normalize_option

        assert _normalize_option("  GitHub Install ", self.OPTIONS) == "github install"

    def test_substring_still_matches(self):
        from magi.core import _normalize_option

        assert _normalize_option("pypi", self.OPTIONS) == "magi on pypi"

    def test_a_genuinely_different_answer_is_not_forced(self):
        from magi.core import _normalize_option

        assert _normalize_option("neither, vendor it", self.OPTIONS) == "neither, vendor it"

    def test_swift_versus_react_native(self):
        from magi.core import _normalize_option

        options = ["Swift", "React Native"]
        assert _normalize_option("swfit", options) == "Swift"
        assert _normalize_option("React-Native", options) == "React Native"
