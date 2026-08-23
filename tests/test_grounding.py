"""Fabricated-premise detection, pinned to real council output.

Every string here was actually produced by the council in a live session or an
eval run. The distinction being drawn is narrow and easy to get wrong in either
direction: asserting a specific the user never gave is the failure, naming that
same specific as missing is the job.
"""

from magi.grounding import figures, novel_terms, premise_hits, stems

QUESTION = "should i push a database migration to prod at 5pm on friday"
Q_STEMS, Q_FIGURES = stems(QUESTION), figures(QUESTION)


def asserted(text: str) -> list[str]:
    return premise_hits(text, Q_STEMS, Q_FIGURES)[0]


def demanded(text: str) -> list[str]:
    return premise_hits(text, Q_STEMS, Q_FIGURES)[1]


class TestRealFabrications:
    def test_invented_rollback_window(self):
        """The original failure. Nothing in the question mentions staging."""
        assert asserted(
            "The mechanism for success is a 24-hour rollback window with "
            "pre-migration testing in staging."
        )

    def test_invented_track_record(self):
        """The council reading its own past verdicts as a success rate."""
        assert asserted(
            "The user has previously been advised to proceed with a similar action "
            "in 2:01 PM on Friday with a 100% success rate in the past."
        )

    def test_invented_planned_break(self):
        assert asserted(
            "You want to push this migration to avoid having it linger into next "
            "week when you're back from a planned break."
        )

    def test_assertion_with_a_negation_hanging_off_the_end(self):
        """Sentence-wide negation scope let this through: one 'no' suppressed
        the whole sentence, including the assertion in front of it."""
        text = (
            "The user has already confirmed the migration is ready for deployment "
            "with no pending rollbacks or test failures"
        )
        assert "deployment" in asserted(text)


class TestHealthyOutput:
    def test_naming_a_fact_as_missing(self):
        """Same nouns as the fabrication, under negation. This is the job."""
        assert not asserted(
            "There is no mention of rollback plans, testing, or timing details "
            "that would prevent downtime."
        )

    def test_stating_an_absence(self):
        text = "The user has no rollback plan and no staging environment stated."
        assert not asserted(text)
        assert demanded(text)

    def test_requiring_something_before_yes(self):
        assert not asserted("They would need a tested rollback before this is safe.")

    def test_ordinary_lens_reasoning(self):
        assert not asserted(
            "Deploying this close to the end of the workday leads to rushed decisions."
        )

    def test_a_fact_the_user_actually_gave(self):
        q = "should i move across the country for my girlfriend after 8 months of dating"
        qs, qf = stems(q), figures(q)
        text = "Their girlfriend of 8 months is the whole basis for uprooting everything."
        assert not premise_hits(text, qs, qf)[0]

    def test_a_forward_looking_projection_is_not_a_premise(self):
        """'in five years' is BALTHASAR's lens, not a claim about today."""
        assert not asserted("In five years this is the decision they will point at.")

    def test_world_knowledge_is_allowed(self):
        """Members are supposed to bring outside knowledge. The sin is
        inventing facts about THIS user, not knowing things."""
        assert not asserted(
            "Friday deploys are the single most common source of weekend incidents."
        )


class TestNovelTerms:
    def test_seeds_the_round_two_anchor(self):
        terms = novel_terms(
            "a 24-hour rollback window with staging tests", Q_STEMS, Q_FIGURES
        )
        assert "rollback" in terms

    def test_question_facts_are_not_novel(self):
        assert "5pm" not in novel_terms("pushing at 5pm on friday", Q_STEMS, Q_FIGURES)


class TestFigureNormalisation:
    def test_equivalent_spellings_compare_equal(self):
        assert figures("$99 a month") == figures("99 months")

    def test_clock_times(self):
        assert "5pm" in figures("at 5pm on friday")

    def test_percentages(self):
        assert "90%" in figures("v2 has 90 percent of traffic")
