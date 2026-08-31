"""The console frame must never tear.

Kanji occupy two terminal cells and Latin one, so any line built with `len()`
instead of a measured width silently shortens by exactly the number of kanji on
it. The frame is the whole look, and a frame that ragged-edges on one member's
verdict is worse than no frame, so every state gets its width asserted.
"""

from rich.cells import cell_len

from magi import nerv
from magi.core import DEFAULT_MODELS, PersonaResponse, Verdict


def widths(text) -> set[int]:
    return {cell_len(line) for line in text.plain.split("\n")}


def vote(verdict: Verdict) -> PersonaResponse:
    return PersonaResponse(
        verdict=verdict,
        reasoning="the migration runs inside one transaction and reverts cleanly",
        lens_finding="MECHANISM: one transaction",
        confidence=4,
    )


class TestFrameHoldsItsWidth:
    def test_empty_council(self):
        assert len(widths(nerv.magi_display(DEFAULT_MODELS, {}))) == 1

    def test_every_verdict_plate(self):
        for verdict in Verdict:
            display = nerv.magi_display(DEFAULT_MODELS, {n: vote(verdict) for n in DEFAULT_MODELS})
            assert len(widths(display)) == 1, f"{verdict} tore the frame"

    def test_mixed_verdicts(self):
        results = dict(zip(DEFAULT_MODELS, [vote(v) for v in Verdict]))
        assert len(widths(nerv.magi_display(DEFAULT_MODELS, results))) == 1

    def test_a_failed_unit(self):
        results = {"MELCHIOR": RuntimeError("boom"), "BALTHASAR": vote(Verdict.ACCEPT)}
        assert len(widths(nerv.magi_display(DEFAULT_MODELS, results))) == 1

    def test_a_long_choice_is_truncated_not_overflowed(self):
        class Pick:
            chosen_option = "rewrite the whole parser in rust over the next two quarters"

        display = nerv.magi_display(DEFAULT_MODELS, {"CASPER": Pick()}, mode="choice")
        assert len(widths(display)) == 1

    def test_an_invited_specialist_does_not_break_the_triangle(self):
        models = dict(DEFAULT_MODELS, BANKER="qwen3:4b")
        assert len(widths(nerv.magi_display(models, {}))) == 1

    def test_two_specialists_fill_the_extra_row(self):
        models = dict(DEFAULT_MODELS, BANKER="qwen3:4b", THERAPIST="hermes3:8b")
        assert len(widths(nerv.magi_display(models, {}))) == 1

    def test_a_long_model_name_still_fits(self):
        models = dict(DEFAULT_MODELS, MELCHIOR="groq/llama-3.3-70b-versatile-preview")
        assert len(widths(nerv.magi_display(models, {}))) == 1


class TestBusAlignsWithTheUnits:
    def test_the_junction_sits_under_the_third_unit(self):
        lines = nerv.magi_display(DEFAULT_MODELS, {}).plain.split("\n")
        junction = next(line for line in lines if "┬" in line).index("┬")
        casper = next(line for line in lines if "CASPER" in line)
        centre = (casper.index("╱") + casper.rindex("╲")) / 2
        assert abs(junction - centre) <= 1, "the bus feeds a unit it does not point at"

    def test_the_drops_sit_under_the_top_units(self):
        lines = nerv.magi_display(DEFAULT_MODELS, {}).plain.split("\n")
        top = next(line for line in lines if "MELCHIOR" in line)
        drop = next(line for line in lines if line.count("│") == 2 and "─" not in line and "╱" not in line)
        left = (top.index("╱") + top.index("╲")) / 2
        right = (top.rindex("╱") + top.rindex("╲")) / 2
        assert abs(drop.index("│") - left) <= 1
        assert abs(drop.rindex("│") - right) <= 1


class TestPlates:
    def test_a_verdict_maps_to_its_kanji(self):
        assert nerv.VERDICT_PLATE["ACCEPT"][0] == nerv.PLATE_ACCEPT
        assert nerv.VERDICT_PLATE["REJECT"][0] == nerv.PLATE_REJECT

    def test_an_unreported_unit_shows_the_phase_not_a_verdict(self):
        display = nerv.magi_display(DEFAULT_MODELS, {}).plain
        assert nerv.PLATE_THINKING in display
        assert nerv.PLATE_ACCEPT not in display


class TestTheStampSaysWhatWasDecided:
    """The outcome says HOW the council decided, the plate says WHAT. A
    unanimous NO is still 否決, and a substring check on " NO" also matches
    "NOT", which is why this reads the word back out of the known format."""

    def test_every_verdict_word_round_trips(self):
        from magi.core import _VERDICT_WORD
        from magi.render import _WORD_PLATE, _decided_word

        for word in _VERDICT_WORD.values():
            assert word in _WORD_PLATE, f"{word} has no plate"
            assert _decided_word(f"CONSENSUS — {word}  (3A · 0C · 0R)") == word

    def test_each_outcome_prefix_is_recognised(self):
        from magi.render import _decided_word

        for prefix in ("CONSENSUS", "MAJORITY", "CALL"):
            assert _decided_word(f"{prefix} — NO  (0A · 0C · 3R)") == "NO"

    def test_lines_that_name_no_verdict_fall_back(self):
        from magi.render import _decided_word

        assert _decided_word("INCOMPLETE — only 1 council member(s) responded") is None
        assert _decided_word("3 DISTINCT PICKS  ·  your call") is None

    def test_a_unanimous_reject_is_not_stamped_approved(self):
        from magi.render import _WORD_PLATE, OUTCOME_PLATE, _decided_word

        line = "CONSENSUS — NO  (0A · 0C · 3R)"
        assert OUTCOME_PLATE["consensus"][0] == nerv.PLATE_ACCEPT
        assert _WORD_PLATE[_decided_word(line)] == nerv.PLATE_REJECT
