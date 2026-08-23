from magi.core import (
    ChoiceResponse,
    PersonaResponse,
    RecommendResponse,
    Verdict,
    synthesize,
    synthesize_choice,
    synthesize_recommend,
)


def vote(verdict, reasoning, finding="a specific lens finding", confidence=3, condition=""):
    return PersonaResponse(
        verdict=verdict,
        reasoning=reasoning,
        lens_finding=finding,
        confidence=confidence,
        condition=condition,
    )


def pick(option, reasoning, finding="a specific lens finding", confidence=3):
    return ChoiceResponse(
        chosen_option=option,
        reasoning=reasoning,
        lens_finding=finding,
        confidence=confidence,
    )


class TestSynthesizeDecision:
    def test_consensus_accept(self):
        positions = {
            "MELCHIOR": vote(Verdict.ACCEPT, "The data supports this move clearly."),
            "BALTHASAR": vote(Verdict.ACCEPT, "Long-term this is sustainable and healthy."),
            "CASPER": vote(Verdict.ACCEPT, "This aligns with what they actually want."),
        }
        result = synthesize(positions, outcome="consensus")
        assert "CONSENSUS" in result
        assert "YES" in result
        assert "3A" in result

    def test_consensus_reject(self):
        positions = {
            "MELCHIOR": vote(Verdict.REJECT, "The numbers do not add up at all."),
            "BALTHASAR": vote(Verdict.REJECT, "This would damage key relationships irreparably."),
            "CASPER": vote(Verdict.REJECT, "They do not actually want this outcome."),
        }
        result = synthesize(positions, outcome="consensus")
        assert "CONSENSUS" in result
        assert "NO" in result

    def test_two_one_is_a_decision_not_a_deadlock(self):
        """A 2-1 vote is the council deciding. Reporting it as a hung jury was
        the system-level version of refusing to vote."""
        positions = {
            "MELCHIOR": vote(Verdict.ACCEPT, "Strong data case for proceeding now."),
            "BALTHASAR": vote(Verdict.ACCEPT, "Sustainable path with good upside."),
            "CASPER": vote(Verdict.CONDITIONAL, "Close call but one blocker remains.",
                           condition="Only if they negotiate the equity split first"),
        }
        result = synthesize(positions, outcome="auto")
        assert "MAJORITY" in result
        assert "YES" in result
        assert "DEADLOCK" not in result
        assert "your call" not in result

    def test_three_way_split_resolves_on_conviction(self):
        positions = {
            "MELCHIOR": vote(Verdict.ACCEPT, "Data says go for it now.", confidence=5),
            "BALTHASAR": vote(Verdict.REJECT, "Too risky for their current life stage.", confidence=2),
            "CASPER": vote(Verdict.CONDITIONAL, "The timing is everything, September is the cutoff.",
                           confidence=2, condition="Only if they start before September 2026"),
        }
        result = synthesize(positions, outcome="auto")
        assert "CALL" in result
        assert "YES" in result
        assert "conviction" in result
        assert "your call" not in result

    def test_dead_even_goes_to_the_desire_lens(self):
        positions = {
            "MELCHIOR": vote(Verdict.REJECT, "The runway math does not clear.", confidence=3),
            "BALTHASAR": vote(Verdict.CONDITIONAL, "One irreversible cost sits in the way.",
                              confidence=3, condition="Only if their lease ends before the move"),
            "CASPER": vote(Verdict.ACCEPT, "They already decided, they want permission.", confidence=3),
        }
        result = synthesize(positions, outcome="auto")
        assert "CALL" in result
        assert "YES" in result  # CASPER's ACCEPT breaks the tie
        assert "your call" not in result

    def test_incomplete(self):
        positions = {"MELCHIOR": vote(Verdict.ACCEPT, "The evidence is clear on this one.")}
        result = synthesize(positions, outcome="incomplete")
        assert "INCOMPLETE" in result

    def test_auto_detection_consensus(self):
        positions = {
            "MELCHIOR": vote(Verdict.REJECT, "Terrible risk-reward ratio here."),
            "BALTHASAR": vote(Verdict.REJECT, "Would cause lasting damage to wellbeing."),
        }
        result = synthesize(positions, outcome="auto")
        assert "CONSENSUS" in result
        assert "NO" in result

    def test_legacy_deadlock_outcome_still_resolves(self):
        """Journal entries written before 0.13 carry outcome='deadlock'."""
        positions = {
            "MELCHIOR": vote(Verdict.ACCEPT, "Numbers check out for this move.", confidence=4),
            "BALTHASAR": vote(Verdict.REJECT, "Cost to relationships is too high.", confidence=2),
        }
        result = synthesize(positions, outcome="deadlock")
        assert "DEADLOCK" not in result
        assert "YES" in result


class TestSynthesizeChoice:
    def test_consensus(self):
        positions = {
            "MELCHIOR": pick("Swift", "Native performance is non-negotiable for this app."),
            "BALTHASAR": pick("Swift", "Better long-term investment for iOS career."),
            "CASPER": pick("Swift", "They genuinely want to learn Swift anyway."),
        }
        result = synthesize_choice(positions, "consensus", ["Swift", "React Native"])
        assert "CONSENSUS" in result
        assert "Swift" in result

    def test_winner(self):
        positions = {
            "MELCHIOR": pick("Swift", "Performance edge matters here."),
            "BALTHASAR": pick("Swift", "Deeper ecosystem for what they need."),
            "CASPER": pick("React Native", "They value shipping fast over polish."),
        }
        result = synthesize_choice(positions, "auto", ["Swift", "React Native"])
        assert "WINNER" in result
        assert "Swift" in result

    def test_tie_is_broken_by_conviction(self):
        positions = {
            "MELCHIOR": pick("Miami", "Lower taxes, better for the business long-term.", confidence=5),
            "BALTHASAR": pick("Austin", "Stronger support network in Austin.", confidence=2),
        }
        result = synthesize_choice(positions, "auto", ["Miami", "Austin"])
        assert "Miami" in result
        assert "your call" not in result
        assert "TIE" not in result

    def test_tie_on_conviction_goes_to_desire_lens(self):
        positions = {
            "MELCHIOR": pick("Miami", "Lower taxes, better for the business long-term.", confidence=3),
            "CASPER": pick("Austin", "Austin is the life they keep describing.", confidence=3),
        }
        result = synthesize_choice(positions, "auto", ["Miami", "Austin"])
        assert "Austin" in result
        assert "your call" not in result


class TestSynthesizeRecommend:
    def test_distinct_picks(self):
        positions = {
            "MELCHIOR": RecommendResponse(recommendation="A personal finance dashboard with Plaid integration", reasoning="Addresses a real need and teaches API work."),
            "BALTHASAR": RecommendResponse(recommendation="A neighborhood mutual aid app", reasoning="Builds community and has low technical risk."),
            "CASPER": RecommendResponse(recommendation="A generative art tool using local Stable Diffusion", reasoning="Matches their creative side that has been dormant."),
        }
        result = synthesize_recommend(positions)
        assert "DISTINCT PICKS" in result

    def test_consensus(self):
        positions = {
            "MELCHIOR": RecommendResponse(recommendation="habit tracker", reasoning="Simple scope, concrete deliverable."),
            "BALTHASAR": RecommendResponse(recommendation="habit tracker", reasoning="Builds a healthy routine simultaneously."),
            "CASPER": RecommendResponse(recommendation="habit tracker", reasoning="Something they will actually use daily."),
        }
        result = synthesize_recommend(positions)
        assert "CONSENSUS" in result

    def test_incomplete(self):
        positions = {
            "MELCHIOR": RecommendResponse(recommendation="A budget CLI tool", reasoning="Practical and shippable in a weekend."),
        }
        result = synthesize_recommend(positions)
        assert "INCOMPLETE" in result
