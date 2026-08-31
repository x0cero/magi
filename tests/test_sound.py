"""Console tones.

The one hard rule is that audio never gets in the way of a decision: a missing
player, an unwritable cache or a bad env value must all degrade to silence
rather than to an exception or a wait.
"""

import wave

from magi import sound


class TestEnabledSwitch:
    def test_on_by_default(self, monkeypatch):
        monkeypatch.delenv("MAGI_SOUND", raising=False)
        assert sound.enabled()

    def test_the_obvious_off_values(self, monkeypatch):
        for value in ("0", "off", "false", "no", "", "OFF"):
            monkeypatch.setenv("MAGI_SOUND", value)
            assert not sound.enabled(), f"{value!r} should silence the console"

    def test_read_at_call_time_not_import_time(self, monkeypatch):
        monkeypatch.setenv("MAGI_SOUND", "0")
        assert not sound.enabled()
        monkeypatch.setenv("MAGI_SOUND", "1")
        assert sound.enabled()


class TestSynthesis:
    def test_every_cue_is_built(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sound, "SOUND_DIR", tmp_path / "sounds")
        assert sound.ensure_sounds()
        for name in sound._build_names():
            assert (sound.SOUND_DIR / f"{name}.wav").exists(), name

    def test_the_files_are_playable_wavs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sound, "SOUND_DIR", tmp_path / "sounds")
        sound.ensure_sounds()
        with wave.open(str(sound.SOUND_DIR / "boot.wav")) as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == sound.SAMPLE_RATE
            assert w.getnframes() > 0

    def test_existing_files_are_not_rebuilt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sound, "SOUND_DIR", tmp_path / "sounds")
        sound.ensure_sounds()
        path = sound.SOUND_DIR / "report.wav"
        stamped = path.stat().st_mtime_ns
        sound.ensure_sounds()
        assert path.stat().st_mtime_ns == stamped

    def test_samples_stay_inside_the_16_bit_range(self):
        for name, samples in sound._build().items():
            assert max(abs(s) for s in samples) <= 1.0, f"{name} would clip on write"


class TestNeverGetsInTheWay:
    def test_muted_play_does_nothing(self, monkeypatch):
        monkeypatch.setenv("MAGI_SOUND", "0")
        monkeypatch.setattr(sound, "_player", lambda: (_ for _ in ()).throw(AssertionError("probed while muted")))
        sound.play("boot")

    def test_no_player_is_silent_not_fatal(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAGI_SOUND", "1")
        monkeypatch.setattr(sound, "SOUND_DIR", tmp_path / "sounds")
        monkeypatch.setattr(sound, "_PLAYER", False)
        monkeypatch.setattr(sound, "_player", lambda: None)
        sound.play("boot")

    def test_an_unknown_cue_is_ignored(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAGI_SOUND", "1")
        monkeypatch.setattr(sound, "SOUND_DIR", tmp_path / "sounds")
        monkeypatch.setattr(sound, "_PLAYER", ["true"])
        sound.play("no-such-cue")


class TestOutcomeCues:
    def test_every_outcome_the_renderer_can_emit_has_a_cue(self):
        from magi.render import OUTCOME_PLATE

        for outcome in OUTCOME_PLATE:
            assert outcome in sound.OUTCOME_CUE, f"{outcome} would fall back silently"
            assert sound.OUTCOME_CUE[outcome] in sound._build_names()

    def test_unanimity_and_a_tiebreak_do_not_sound_the_same(self):
        assert sound.OUTCOME_CUE["consensus"] != sound.OUTCOME_CUE["tiebreak"]
