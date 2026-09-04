from magi.intake import Classification, QuestionClass


class TestClassificationModel:
    def test_decision_parses(self):
        c = Classification(question_class=QuestionClass.DECISION, options=[])
        assert c.question_class == QuestionClass.DECISION
        assert c.options == []

    def test_choice_with_options(self):
        c = Classification(
            question_class=QuestionClass.CHOICE,
            options=["Swift", "React Native"],
        )
        assert c.question_class == QuestionClass.CHOICE
        assert len(c.options) == 2

    def test_noise(self):
        c = Classification(question_class=QuestionClass.NOISE, options=[])
        assert c.question_class == QuestionClass.NOISE

    def test_from_json(self):
        raw = '{"question_class": "open", "options": []}'
        c = Classification.model_validate_json(raw)
        assert c.question_class == QuestionClass.OPEN

    def test_choice_from_json(self):
        raw = '{"question_class": "choice", "options": ["Miami", "Austin", "Denver"]}'
        c = Classification.model_validate_json(raw)
        assert c.question_class == QuestionClass.CHOICE
        assert c.options == ["Miami", "Austin", "Denver"]

    def test_prediction_class(self):
        c = Classification(question_class=QuestionClass.PREDICTION, options=[])
        assert c.question_class == QuestionClass.PREDICTION


class TestNoiseGuard:
    """Statements are how undecided people talk. They must reach the council."""

    def test_statement_is_never_noise(self):
        from magi.intake import _settle
        c = Classification(question_class=QuestionClass.NOISE, options=[])
        out = _settle(c, "i keep putting off calling the dentist")
        assert out.question_class == QuestionClass.DECISION

    def test_greeting_stays_noise(self):
        from magi.intake import _settle
        c = Classification(question_class=QuestionClass.NOISE, options=[])
        assert _settle(c, "hey").question_class == QuestionClass.NOISE
        c = Classification(question_class=QuestionClass.NOISE, options=[])
        assert _settle(c, "ok thanks").question_class == QuestionClass.NOISE
        c = Classification(question_class=QuestionClass.NOISE, options=[])
        assert _settle(c, "asdf").question_class == QuestionClass.NOISE

    def test_framing_with_invented_figure_is_dropped(self):
        from magi.intake import _settle
        c = Classification(question_class=QuestionClass.DECISION, options=[],
                           decision="should I quit my $90k job")
        assert _settle(c, "im thinking about quitting my job").decision == ""

    def test_framing_in_users_words_is_kept(self):
        from magi.intake import _settle
        c = Classification(question_class=QuestionClass.DECISION, options=[],
                           decision='"should I quit my job"')
        assert _settle(c, "im thinking about quitting my job").decision == "should I quit my job"

    def test_frame_lands_in_question_text(self):
        from magi.core import Deliberation
        d = Deliberation(["MELCHIOR", "BALTHASAR"])
        d.add_user_message("im thinking about quitting my job")
        d.frame("should I quit my job")
        assert "The decision on the table: should I quit my job?" in d.question_text
        assert d.turn == 1
