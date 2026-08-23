from unittest.mock import patch

from magi.memory import MemoryHit, _similarity, _tokenize, build_context, detect_patterns, search


class TestTokenize:
    def test_removes_stop_words(self):
        tokens = _tokenize("should I take the job")
        assert "should" not in tokens
        assert "the" not in tokens
        assert "take" in tokens
        assert "job" in tokens

    def test_removes_short_words(self):
        tokens = _tokenize("go to LA or NY")
        assert "go" not in tokens
        assert "to" not in tokens


class TestSimilarity:
    def test_identical(self):
        assert _similarity("should I take the job", "should I take the job") == 1.0

    def test_similar(self):
        s = _similarity("should I take the job offer", "should I accept the job")
        assert s >= 0.2

    def test_unrelated(self):
        s = _similarity("should I take the job", "what game should I play")
        assert s < 0.2

    def test_empty(self):
        assert _similarity("", "hello") == 0.0


class TestSearch:
    def test_finds_similar(self):
        fake_entries = [
            {"id": "abc", "question": "should I take the job offer", "outcome": "consensus",
             "synthesis": "YES", "user_outcome": "took it", "timestamp": "2026-05-01T00:00:00"},
            {"id": "def", "question": "what should I eat for dinner", "outcome": "picks",
             "synthesis": "3 picks", "user_outcome": None, "timestamp": "2026-05-02T00:00:00"},
        ]
        with patch("magi.memory.load_entries", return_value=fake_entries):
            hits = search("should I accept the job")
            assert len(hits) == 1
            assert hits[0].entry_id == "abc"

    def test_no_matches(self):
        fake_entries = [
            {"id": "abc", "question": "what color should I paint the wall", "outcome": "consensus",
             "synthesis": "blue", "user_outcome": None, "timestamp": "2026-05-01T00:00:00"},
        ]
        with patch("magi.memory.load_entries", return_value=fake_entries):
            hits = search("should I quit my job")
            assert len(hits) == 0


class TestBuildContext:
    def test_empty(self):
        assert build_context([]) == ""

    def test_with_hits(self):
        hits = [MemoryHit("abc", "should I take the job", "consensus", "YES", "took it, no regrets", 0.8, "2026-05-01")]
        ctx = build_context(hits)
        assert "COUNCIL MEMORY" in ctx
        assert "took it, no regrets" in ctx
        assert "CURRENT QUESTION" in ctx


class TestDetectPatterns:
    def test_detects_repeat(self):
        fake_entries = [
            {"question": "should I take the job offer", "outcome": "consensus",
             "user_outcome": None, "final_verdicts": {}, "rounds": 1},
        ]
        with patch("magi.memory.load_entries", return_value=fake_entries):
            p = detect_patterns("should I take the job")
            assert p.repeat_question is True

    def test_no_repeat(self):
        fake_entries = [
            {"question": "what game should I play", "outcome": "picks",
             "user_outcome": None, "final_verdicts": {}, "rounds": 1},
        ]
        with patch("magi.memory.load_entries", return_value=fake_entries):
            p = detect_patterns("should I take the job")
            assert p.repeat_question is False

    def test_deadlock_streak(self):
        fake_entries = [
            {"question": "q1", "outcome": "deadlock", "user_outcome": None, "final_verdicts": {}, "rounds": 3},
            {"question": "q2", "outcome": "split", "user_outcome": None, "final_verdicts": {}, "rounds": 3},
            {"question": "q3", "outcome": "consensus", "user_outcome": None, "final_verdicts": {}, "rounds": 1},
        ]
        with patch("magi.memory.load_entries", return_value=fake_entries):
            p = detect_patterns("anything")
            assert p.deadlock_streak == 2


class TestContextDoesNotFeedBackVerdicts:
    """Live failure: the council read its own two prior verdicts on the same
    question as "a 100% success rate in prior deployments"."""

    def _hit(self, **kw):
        from magi.memory import MemoryHit

        base = dict(
            entry_id="abc123",
            timestamp="2026-08-10",
            question="should i push a database migration to prod at 5pm on friday",
            outcome="majority",
            synthesis="MAJORITY - YES  (2A / 0C / 1R)",
            similarity=0.9,
            user_outcome=None,
        )
        base.update(kw)
        return MemoryHit(**base)

    def test_past_verdict_is_never_shown(self):
        from magi.memory import build_context

        ctx = build_context([self._hit(user_outcome="shipped it")])
        assert "MAJORITY" not in ctx
        assert "YES" not in ctx
        assert "2A" not in ctx

    def test_the_question_itself_is_shown(self):
        from magi.memory import build_context

        ctx = build_context([self._hit(user_outcome="shipped it")])
        assert "database migration" in ctx

    def test_recorded_outcome_is_shown_because_it_is_evidence(self):
        from magi.memory import build_context

        ctx = build_context([self._hit(user_outcome="shipped it, broke checkout for 3 hours")])
        assert "broke checkout" in ctx
        assert "afterwards" in ctx

    def test_a_hit_with_no_recorded_outcome_sends_nothing(self):
        """"They never recorded what they did" was itself enough to poison a
        deliberation: a member cited it as "a pattern of unrecorded actions,
        which creates a high risk of failure" on a database migration."""
        from magi.memory import build_context

        assert build_context([self._hit()]) == ""

    def test_journalling_habits_are_never_mentioned(self):
        from magi.memory import build_context

        ctx = build_context([self._hit(), self._hit(user_outcome="shipped it, went fine")])
        assert "never recorded" not in ctx
        assert "unrecorded" not in ctx

    def test_only_hits_with_outcomes_are_included(self):
        from magi.memory import build_context

        ctx = build_context([
            self._hit(question="a question they never followed up on"),
            self._hit(question="the one they reported back on", user_outcome="did it"),
        ])
        assert "never followed up" not in ctx
        assert "reported back on" in ctx

    def test_council_is_told_its_own_verdicts_are_not_evidence(self):
        from magi.memory import build_context

        ctx = build_context([self._hit(user_outcome="did it, no regrets")])
        assert "not a precedent" in ctx or "success rate" in ctx
